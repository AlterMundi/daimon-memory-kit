"""Inspect a retained sleep decision and apply an explicit DMK selection."""
import argparse
from contextlib import ExitStack, closing
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3

from capture_inbox import sha, wire
from capturectl import CaptureLedger
import memory_runtime
import paired_sleep
import sleep_triage


def read_candidate(binding, root, packet_id, item, *, gateway_original=None, telegram_text=False, voice_transcripts=False):
    """Reconstruct one exact authorized human excerpt without reopening its session."""
    if not re.fullmatch(r'[0-9a-f]{64}', packet_id) or type(item) is not int or not 0 <= item < 8:
        raise ValueError('select a packet hash and a human item index')
    if binding.get('schema') != 'hmk.codex-hook-binding/v2':
        raise ValueError('explicit existing forward capture binding required')
    root = Path(root)
    path = root / 'packets' / (packet_id + '.json')
    if root.is_symlink() or root.stat().st_mode & 0o077 or path.is_symlink():
        raise ValueError('private owner-local triage state required')
    packet = json.loads(path.read_bytes())
    if packet['schema'] != sleep_triage.POLICY or packet['packet_id'] != packet_id:
        raise ValueError('packet identity differs')
    if packet['state'] not in {'classified', 'needs_review'} or item >= len(packet['sources']):
        raise ValueError('item has no retained classification')
    owner = sha(wire(binding).encode())
    cursor = json.loads((root / 'cursor.json').read_text())
    if (cursor['binding_sha256'] != owner or cursor['schema'] != sleep_triage.POLICY
                or cursor.get('gateway_originals', False) != (gateway_original is not None)
                or cursor.get('telegram_text', False) != telegram_text
                or cursor.get('voice_transcripts', False) != voice_transcripts):
        raise ValueError('triage state belongs to another capture binding')
    observation = packet['observation']
    with closing(sqlite3.connect(Path(binding['inbox']).resolve().as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        actual = con.execute('SELECT value FROM binding').fetchall()
        if len(actual) != 1 or actual[0][0] != wire(binding):
            raise ValueError('capture inbox binding differs')
        row = sleep_triage.next_observation(con, observation - 1, observation)
        fields = ('conversation', 'revision', 'file_start', 'file_end', 'delta_sha256')
        if row is None or any(row[k] != packet[k] for k in fields):
            raise ValueError('retained capture range differs or was lost')
        pages = sleep_triage.source_pages(con, row, binding, human_id=cursor.get('human_id'),
                                         gateway_original=gateway_original)
        for offset, page in enumerate(pages):
            key = sha(wire([sleep_triage.POLICY, row['event_key'], offset]).encode())
            if key == packet_id:
                break
        else:
            raise ValueError('no matching retained capture page')
        sources = [{k: v for k, v in piece.items() if k != 'text'} for piece in page]
        if sources != packet['sources']:
            raise ValueError('source pointers differ from retained page')
        context = []
        if packet['assistant_context']:
            targets = sleep_triage.context_targets(packet['decision'], page)
            if not targets:
                raise ValueError('assistant context lacks a retained request')
            context = sleep_triage.assistant_context(con, row, binding, [page[i] for i in targets])
            pointers = [{k: v for k, v in piece.items() if k != 'text'} for piece in context]
            if pointers != packet['assistant_context']:
                raise ValueError('assistant context differs from retained evidence')
    source = page[item]
    receipt = packet['decision']
    followup = packet['context_decision']
    candidate = dict(
        schema='dmk.sleep-memory-review/v1', packet_id=packet_id, item=item,
        owner=owner, state=packet['state'], revision=row['revision'],
        delta_sha256=row['delta_sha256'], model=packet['model'],
        probability=receipt['scores'].get(f'memory_{item}'),
        context_probability=(followup['scores'].get(f'memory_{item}') if followup else None),
        assistant_context=context, source=source,
    )
    return {**candidate, 'fingerprint': sha(wire(candidate).encode())}


def apply_review(ledger, binding, candidate, fingerprint, decision):
    """Use the capture ledger's existing transaction and terminal replay contract."""
    if fingerprint != candidate['fingerprint'] or fingerprint != sha(wire({
        k: v for k, v in candidate.items() if k != 'fingerprint'
    }).encode()) or candidate['owner'] != sha(wire(binding).encode()):
        raise ValueError('review must identify the exact candidate fingerprint')
    if decision.get('outcome') not in {'applied', 'omitted'}:
        raise ValueError('choose an explicit reviewed application or omission')
    if decision.get('links') and not decision.get('records'):
        raise ValueError('links must accompany a selected memory')
    if len(decision.get('records', [])) > 1:
        raise ValueError('review one memory per source item')
    for record in decision.get('records', []):
        meta = record.get('metadata') or {}
        if set(meta) & {'source_event_id', 'source_version', 'source_uri', 'source_instance',
                        'evidence', 'reported_at', 'subject', 'mode'}:
            raise ValueError('the selected source owns its attribution and exact reference')

    source = candidate['source']
    source_id, start = source['source_id'], source['start_char']
    end = start + len(source['text'])
    # The stream is per immutable source item. An identical packet replay can
    # never allocate another sequence or consume the same evidence twice.
    event_id = 'sleep-human:' + sha(wire([candidate['owner'], source_id, start, end]).encode())
    evidence = f"capture:{source_id}#chars={start}:{end}@sha256:{candidate['delta_sha256']}"
    references = [evidence]
    if ref := source.get('original_input_ref'):
        event_id = 'sleep-human:' + sha(wire([binding['subject'], ref, start, end]).encode())
        references.append(source.get('original_channel', 'conversation') + ':' + ref)
        if source['channel'] == 'human_voice_transcription':
            references.append('automatic-transcript:' + ref)
    meta = dict(mode='reported', subject=binding['subject'],
                source_instance=binding['source_instance'], source_uri=evidence,
                evidence=references)
    if source['received_at']:
        received = datetime.datetime.fromisoformat(source['received_at'])
        if received.tzinfo is None:
            raise ValueError('source receipt time lacks an explicit timezone')
        meta['reported_at'] = int(received.timestamp())
    event = dict(stream_id=event_id, sequence=1, event_id=event_id,
                 source_version=str(candidate['revision']), content=source['text'],
                 metadata=meta)
    receipt = ledger.stage(event)
    return ledger.assess(receipt['event_key'], decision)


def standalone_library(paired, binding):
    """Use the same enrolled owner library as the paired periodic backup."""
    from periodic_backups import Baselines

    database, policy = paired_sleep.owner_backup_profile(paired, binding)
    pool = Baselines(database, policy)
    if not pool.manifest_path.is_file():
        raise ValueError('existing canonical owner library enrollment required')
    pool.read()
    bound = os.environ.get('HMK_DB_PATH')
    if bound is not None and Path(bound).resolve() != pool.database:
        raise ValueError('receiving database binding differs')
    return dict(database=str(pool.database),
                memory_base=os.environ.get('HMK_AGENT_MEMORY_BASE', str(pool.database.parent)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', help='Existing canonical worker profile, when available')
    parser.add_argument('--paired-profile', help='Owner-local paired Decisions profile, if separate from the canonical worker')
    parser.add_argument('--packet', required=True)
    parser.add_argument('--item', required=True, type=int)
    parser.add_argument('--decision', help='Private JSON with fingerprint and reviewed CaptureLedger decision')
    args = parser.parse_args()
    if not args.profile and not args.paired_profile:
        parser.error('an existing worker or paired profile is required')
    profile = memory_runtime.profile(args.profile) if args.profile else None
    binding = None
    if profile is not None:
        binding = json.loads(Path(profile['binding']).read_text())
        if Path(binding['inbox']).resolve() != Path(profile['inbox']).resolve() or any(
            binding[k] != profile['context'][k] for k in ('subject', 'source_instance')
        ):
            raise ValueError('review binding differs from the selected worker')
        if not args.paired_profile:
            root = profile['sleep_triage']['state_dir']
    with ExitStack() as stack:
        resolver = None
        telegram_text = voice_transcripts = False
        if args.paired_profile:
            paired = json.loads(Path(args.paired_profile).read_text())
            paired_state = Path(paired['state_dir'])
            config = json.loads((paired_state/'binding.json').read_text())
            if config['schema'] != paired_sleep.SCHEMA:
                raise ValueError('unsupported paired binding')
            source = paired_sleep.verified_binding(paired, config)
            if (Path(source['inbox']).resolve() != (paired_state/'capture.sqlite').resolve()
                    or (binding is not None and any(source[key] != binding[key]
                                                     for key in ('subject', 'source_instance')))):
                raise ValueError('paired source differs from the canonical memory owner')
            binding, root = source, paired_state/'triage'
            if profile is None:
                profile = standalone_library(paired, binding)
            telegram_text = paired.get('telegram_text') is True
            voice_transcripts = paired.get('voice_transcripts') is True
            resolver = stack.enter_context(paired_sleep.original_resolver(paired, source, config['human_id']))
        if args.decision:
            work = stack.enter_context(open(str(Path(binding['inbox']).resolve()) + '.worker.lock', 'a+b'))
            fcntl.flock(work, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = read_candidate(binding, root, args.packet, args.item,
                                gateway_original=resolver, telegram_text=telegram_text, voice_transcripts=voice_transcripts)
        if args.decision:
            selected = json.loads(Path(args.decision).read_text())
            ledger = CaptureLedger(memory_runtime.load_memory(profile))
            result = apply_review(ledger, binding, result, **selected)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
