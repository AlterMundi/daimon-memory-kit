"""Bounded fictional first-generation diagnostic, never a qualification gate.

Only frozen receiving packets enter requests. Hidden rubrics stay outside this
process. Identical observed generations may be reused without new inference;
started/failed dispatches remain unresolved rather than implicitly retried.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil

import receiving_text_api as api


def run(packet_root, out, *, api_key, references=(), max_calls=12, workers=3):
    packet_root, out = Path(packet_root), Path(out)
    if not 1 <= workers <= 3 or not 0 <= max_calls <= 44:
        raise ValueError('finite dispatch limits required')
    source = json.loads((packet_root/'conditions.json').read_text())
    if source.get('fictional') is not True or source['packets_sha256'] != api.exchange.checksum(packet_root/'packets.json'):
        raise ValueError('unchanged fictional packets required')
    packets = json.loads((packet_root/'packets.json').read_text())
    conditions = dict(scope='first generation only; independent grading pending',
        qualification=False, provider='deepseek', model='deepseek-flash',
        reasoning_effort='low', max_tokens=12000, workers=workers,
        packets_sha256=source['packets_sha256'],
        dispatcher_sha256=api.exchange.checksum(Path(api.dispatch.__code__.co_filename)),
        diagnostic_sha256=api.exchange.checksum(Path(__file__)),
        narrative_sha256=api.exchange.checksum(Path(api.exchange.narrative.__file__)),
        assertion_review_sha256=api.exchange.checksum(Path(api.exchange.narrative.review_shape.__code__.co_filename)))
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    frozen = out/'conditions.json'
    if frozen.exists() and json.loads(frozen.read_text()) != conditions:
        raise ValueError('diagnostic conditions changed; preserve existing work')
    api.exchange.pilot.save(frozen, conditions)
    transport = api.exchange.FileExchange(out, 'low')
    trace = api.exchange.pilot.Trace(out/'trace.json')
    trace.phase = 'narrative_generation'
    manifest = []
    for packet in packets:
        messages = [dict(role='system', content=api.exchange.narrative.GENERATION),
            dict(role='user', content=json.dumps(packet['context'], ensure_ascii=False))]
        try:
            transport('deepseek-flash', messages, trace)
        except api.exchange.ResponsePending:
            pass
        schema = api.exchange.narrative.response_schema('narrative_generation', messages)
        request = dict(format='hmk-fictional-receiving-request/v1', model='deepseek-flash',
            phase='narrative_generation', reasoning_effort='low', messages=messages,
            response_schema=schema, external_dispatch_required=True, fresh_context=True,
            tools_allowed=False, native_memory_allowed=False)
        request_hash = api.exchange.pilot.digest(request)
        manifest.append(dict(arm=packet['arm'], answer_index=packet['answer_index'],
            case_id=packet['case_id'], context_sha256=packet['context_sha256'],
            request_sha256=request_hash))
        response_path = out/'responses'/(request_hash+'.json')
        if response_path.exists():
            continue
        for reference in map(Path, references):
            prior_path = reference/'responses'/(request_hash+'.json')
            if not prior_path.exists():
                continue
            prior = json.loads(prior_path.read_text())
            receipt_path = Path(prior['dispatch_receipt'])
            receipt = json.loads(receipt_path.read_text())
            if receipt.get('state') != 'completed' or receipt.get('parameters') != api.parameters(request, 'deepseek'):
                raise ValueError('reused generation lacks identical actual provider parameters')
            if prior.get('fresh_context') is not True or prior.get('tool_calls_observed') != []:
                raise ValueError('reused generation is not an isolated text receiver')
            shutil.copy2(prior_path, response_path)
            break
    api.exchange.pilot.save(out/'manifest.json', manifest)
    distinct = list(dict.fromkeys(m['request_sha256'] for m in manifest))
    todo = [d for d in distinct if not (out/'responses'/(d+'.json')).exists()
            and not (out/'dispatches'/(d+'.json')).exists()][:max_calls]
    def dispatch(d):
        path = api.dispatch(out/'requests'/(d+'.json'), out, api_key, 'deepseek')
        receipt = json.loads(path.read_text())
        print(json.dumps(dict(request_sha256=d, seconds=receipt['seconds'],
            usage=receipt['usage'])), flush=True)
        return d
    completed, failures = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [(d, pool.submit(dispatch, d)) for d in todo]
        for d, future in futures:
            try:
                completed.append(future.result())
            except Exception as error:
                failures.append(dict(request_sha256=d, error_type=type(error).__name__))
    available = sum((out/'responses'/(m['request_sha256']+'.json')).exists() for m in manifest)
    result = dict(questions=len(manifest), available_generations=available,
        attempted_calls=len(todo), completed_new_calls=len(completed), failures=failures,
        qualification=False, reviewer_calls=0,
        unresolved_dispatches=[d for d in distinct if (out/'dispatches'/(d+'.json')).exists()
            and not (out/'responses'/(d+'.json')).exists()])
    api.exchange.pilot.save(out/'state.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packets', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reuse-generations', type=Path, action='append', default=[])
    parser.add_argument('--max-calls', type=int, default=12)
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(run(args.packets, args.out, api_key=os.environ.get('DEEPSEEK_API_KEY'),
        references=args.reuse_generations, max_calls=args.max_calls, workers=args.workers)))
