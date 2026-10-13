#!/usr/bin/env python3
"""Prepare blind receiving packets and exchange responses without model dispatch.

freeze replays already recorded question-derived plans through the selected HMK
reader. receive sees only those frozen packets, never a corpus/rubric/database.
Every model request requires a separately authorized external dispatcher. This
module starts no Codex session, subagent, timer, hook or memory integration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import durable_recall_pilot as pilot
import narrative_recall as narrative


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(path):
    """All existing canonical/history columns, except retrieval usage counters."""
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as con:
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result={}
        for table in sorted(tables & {'chapters','books','shelves','chapter_links','chapter_revisions'}):
            columns=[r[1] for r in con.execute('PRAGMA table_info('+table+')')
                     if not (table=='chapters' and r[1] in {'last_access','access_count'})]
            rows=con.execute('SELECT '+','.join(columns)+' FROM '+table+' ORDER BY rowid').fetchall()
            result[table]=dict(columns=columns,rows=len(rows),sha256=pilot.digest(rows))
        return result


def freeze(source, corpus_path, out, upgrade=False):
    corpus=json.loads(corpus_path.read_text())
    if corpus.get('fictional') is not True:
        raise ValueError('only the explicitly fictional corpus is supported')
    expected=[(case['id'],q['query']) for case in corpus['cases'] for q in case['questions']]
    conditions=json.loads((source/'conditions.json').read_text())
    if conditions['fixture_hash']!=pilot.digest(corpus):
        raise ValueError('source run does not match the frozen fictional corpus')
    reader_hash=checksum(Path(pilot.configuration.__file__))
    if reader_hash!=conditions['retrieval_sha256'] and not upgrade:
        raise ValueError('changed reader requires explicit --reader-upgrade')
    for path in (source,out):
        live=pilot.configuration.BASE_DIR.resolve() if pilot.configuration.BASE_DIR else None
        if live and (path.resolve()==live or live in path.resolve().parents):
            raise ValueError('fictional exchange cannot use the live pool')
    results={r['variant']:r for r in json.loads((source/'results.json').read_text())}
    binding=dict(being=corpus['fixture_context']['being'],receiving_body='fixture:body:voice',
        same_being_bodies=corpus['fixture_context']['same_being_bodies'],source_network_access=False,
        repository_runtime_access=False,physical_sensors=False,physical_actuators=False,
        private_session_access=False)
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    packets=[];preservation={}
    for arm in ('baseline','proposed'):
        previous=json.loads((source/arm/'answers.json').read_text())
        if [(a['case_id'],a['question']) for a in previous]!=expected:
            raise ValueError('source run must contain every recorded question, in order')
        # Start from pre-recall formation, not the previously queried receiver:
        # its ten-year access history must not warm this new comparison.
        database=source/arm/'memory/library.db'
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as con:
            tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if con.execute('SELECT 1 FROM chapters WHERE last_access IS NOT NULL OR access_count!=0').fetchone():
                raise ValueError('cold comparison requires unqueried pre-recall formation; do not reset original access history')
            if 'capture_events' in tables and con.execute(
                'SELECT 1 FROM capture_events WHERE payload_json IS NOT NULL').fetchone():
                raise ValueError('formation still contains unprocessed original capture payloads')
        pool=out/arm/'receiver';pool.mkdir(mode=0o700,parents=True)
        pilot.verified_snapshot(database,pool/'library.db')
        before=canon(database)
        memory=pilot.memory_at(pool)
        with memory.connect() as con:
            con.execute('DROP TABLE IF EXISTS capture_events')
            con.execute('DROP TABLE IF EXISTS capture_streams')
            con.commit()
        if canon(memory.DB_PATH)!=before:
            raise ValueError('reader initialization changed original canonical/history values')
        clock=results[arm]['retrieval_clock'];memory.now_ts=lambda clock=clock:clock
        pilot.instrument_embeddings(memory,out/arm/'embedding-trace.json')
        for index,old in enumerate(previous):
            packs=[memory.hybrid_pack(old['question'],budget_tokens=1500,limit=5,threshold=0.4)]
            pilot.save(out/'freeze-pending.json',dict(arm=arm,index=index,question=old['question'],
                first_pack=packs[0],recorded_plan=old['plan_attempts'][-1]))
            plan=pilot.recall_plan(old['plan_attempts'][-1],pilot.visible_ids(packs[0]),
                                  require_refinement=packs[0]['null_retrieval'])
            for query in plan['queries']:
                packs.append(memory.hybrid_pack(query,budget_tokens=1500,limit=5,threshold=0.4))
            expanded=[memory.expand(cid) for cid in plan['expand_ids']]
            if any(p['retrieval_status']!='ok' for p in packs):
                raise ValueError('packet freeze encountered degraded retrieval; retain diagnostic work')
            evidence=pilot.answer_evidence(packs,expanded)
            packet=dict(arm=arm,answer_index=index,case_id=old['case_id'],question=old['question'],
                binding=binding,clock=clock,recorded_plan=plan,packs=packs,expanded=expanded,
                context=narrative.supplied_context(old['question'],evidence,binding),
                context_sha256=pilot.digest(dict(query=old['question'],evidence=evidence,binding=binding)))
            packets.append(packet)
            pilot.save(out/'packets.json',packets)
            (out/'freeze-pending.json').unlink()
        after=canon(memory.DB_PATH)
        if before!=after:raise ValueError('retrieval changed original meaning/history')
        preservation[arm]=dict(before=before,after=after,identical=True,
            permitted_changes=['chapters.last_access','chapters.access_count'],
            source_clock=clock,questions=len(previous))
        print(arm,'frozen',len(previous),'questions',flush=True)
    pilot.save(out/'preservation.json',preservation)
    pilot.save(out/'conditions.json',dict(fictional=True,qualification=False,
        source_conditions=conditions,fixture_sha256=checksum(corpus_path),
        recorded_planner='source-run plans replayed without another model call',
        reader_sha256=reader_hash,reader_upgrade=upgrade,exchange_sha256=checksum(Path(__file__)),
        narrative_sha256=checksum(Path(narrative.__file__)),
        assertion_review_sha256=checksum(Path(narrative.review_shape.__code__.co_filename)),packets_sha256=checksum(out/'packets.json'),
        original_sources_available=False,context_scope='frozen-retrieval-plan narrative experiment',
        model_requests_executed=0))


class ResponsePending(RuntimeError):
    pass


class FileExchange:
    """A response transport, never a dispatcher or a semantic verifier."""
    def __init__(self,root,effort,review_effort=None):
        self.root=root;self.effort=effort;self.review_effort=review_effort or effort
        (root/'requests').mkdir(exist_ok=True)
        (root/'responses').mkdir(exist_ok=True)

    def __call__(self,model,messages,trace):
        schema=narrative.response_schema(trace.phase,messages)
        effort = self.review_effort if trace.phase == 'narrative_review' else self.effort
        request=dict(format='hmk-fictional-receiving-request/v1',model=model,phase=trace.phase,
            reasoning_effort=effort,messages=messages,response_schema=schema,
            external_dispatch_required=True,fresh_context=True,tools_allowed=False,
            native_memory_allowed=False)
        request_hash=pilot.digest(request)
        path=self.root/'requests'/(request_hash+'.json')
        if path.exists() and json.loads(path.read_text())!=request:
            raise ValueError('prepared request collision; preserve both sources')
        if not path.exists():pilot.save(path,request)
        response_path=self.root/'responses'/(request_hash+'.json')
        if not response_path.exists():
            raise ResponsePending(str(path))
        response=json.loads(response_path.read_text())
        if response.get('request_sha256')!=request_hash or response.get('requested_model')!=model:
            raise ValueError('external response belongs to another request/model')
        if response.get('tool_calls_observed')!=[] or response.get('fresh_context') is not True:
            raise ValueError('external receiving context used tools or was not fresh; preserve the response')
        if not isinstance(response.get('dispatch_receipt'),str) or not response['dispatch_receipt'].strip():
            raise ValueError('external response needs an actual dispatch receipt reference')
        usage=response.get('usage')
        if usage is not None and (not isinstance(usage,dict) or any(
            not isinstance(usage.get(k),int) or isinstance(usage[k],bool) or usage[k]<0
            for k in ('prompt_tokens','completion_tokens','total_tokens'))):
            raise ValueError('usage must be unknown or complete nonnegative provider token counts')
        content=response.get('content')
        if not isinstance(content,str):raise ValueError('external response must preserve raw final-message text')
        # A saved response may be re-read after a process interruption. It is one
        # external call, not a newly executed request. The raw response stays.
        call=next((i for i,v in enumerate(trace) if v.get('external_request_sha256')==request_hash),None)
        if call is None:
            call=trace.begin(dict(external_request_sha256=request_hash,requested_model=model,
                requested_reasoning_effort=effort,adapter='file-exchange',
                response_format_sha256=pilot.digest(schema),prompt_hash=pilot.digest(messages)))
        trace.finish(call,dict(state='completed',response_model=response.get('response_model'),
            usage=response.get('usage'),seconds=response.get('seconds'),
            dispatch_receipt=response['dispatch_receipt'],response_content=content,
            finish_reason=response.get('finish_reason')))
        if response.get('finish_reason') == 'length':
            trace.finish(call,dict(parse_error='incomplete_response'))
            return {'_invalid_json':content, '_finish_reason':'length'}
        try:return json.loads(content)
        except json.JSONDecodeError:
            trace.finish(call,dict(parse_error='invalid_json'))
            return {'_invalid_json':content}


def receive(packet_root,out,model,effort='xhigh',resume=False,review_model=None,review_effort=None):
    review_model = review_model or model
    review_effort = review_effort or effort
    conditions=json.loads((packet_root/'conditions.json').read_text())
    if conditions.get('fictional') is not True or conditions['packets_sha256']!=checksum(packet_root/'packets.json'):
        raise ValueError('frozen packet bytes changed or were not fictional')
    packets=json.loads((packet_root/'packets.json').read_text())
    frozen=dict(model=model,reasoning_effort=effort,packets_sha256=conditions['packets_sha256'],
        exchange_sha256=checksum(Path(__file__)),narrative_sha256=checksum(Path(narrative.__file__)),
        assertion_review_sha256=checksum(Path(narrative.review_shape.__code__.co_filename)),
        qualification=False,dispatch='external; this process executes no model requests')
    if review_model != model or review_effort != effort:
        frozen.update(review_model=review_model,review_reasoning_effort=review_effort)
    out.mkdir(mode=0o700,parents=True,exist_ok=resume)
    if resume:
        if json.loads((out/'conditions.json').read_text())!=frozen:
            raise ValueError('receiving comparison conditions changed; preserve pending work')
    else:pilot.save(out/'conditions.json',frozen)
    exchange=FileExchange(out,effort,review_effort);trace=pilot.Trace(out/'trace.json');trace.phase='recall'
    answers=json.loads((out/'answers.json').read_text()) if (out/'answers.json').exists() else []
    for packet in packets[len(answers):]:
        checkpoint=out/'pending.json'
        pending=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        evidence=pilot.answer_evidence(packet['packs'],packet['expanded'])
        context=narrative.supplied_context(packet['question'],evidence,packet['binding'])
        if context!=packet['context']:raise ValueError('receiving source adapter changed the frozen context')
        try:
            value=narrative.answer(model,packet['question'],evidence,packet['binding'],
                trace,pending,checkpoint,exchange,pilot.save,review_model=review_model)
        except ResponsePending as error:
            return dict(state='prepared',request=str(error),model_requests_executed_by_this_process=0,
                        completed_candidates=len(answers),qualification=False)
        except narrative.NarrativeRejected:
            state=pending['narrative'];value=dict(state['generations'][-1],
                operational_status='rejected',error=state['error'])
        answers.append(dict(arm=packet['arm'],answer_index=packet['answer_index'],
            case_id=packet['case_id'],question=packet['question'],answer=value,
            context_sha256=packet['context_sha256'],narrative_attempts=pending['narrative']))
        pilot.save(out/'answers.json',answers)
        checkpoint.unlink()
    return dict(state='candidates_complete',questions=len(answers),qualification=False,
                independent_grading_required=True,model_requests_executed_by_this_process=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    freezing=sub.add_parser('freeze')
    freezing.add_argument('--source-run',type=Path,required=True)
    freezing.add_argument('--corpus',type=Path,required=True)
    freezing.add_argument('--out',type=Path,required=True)
    freezing.add_argument('--reader-upgrade',action='store_true')
    receiving=sub.add_parser('receive')
    receiving.add_argument('--packets',type=Path,required=True)
    receiving.add_argument('--out',type=Path,required=True)
    receiving.add_argument('--model',required=True)
    receiving.add_argument('--reasoning-effort',default='xhigh')
    receiving.add_argument('--review-model',help='Reviewer only; generation/revisions keep --model')
    receiving.add_argument('--review-reasoning-effort',help='Reviewer effort only; frozen on resume')
    receiving.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if args.command=='freeze':freeze(args.source_run,args.corpus,args.out,args.reader_upgrade)
    else:print(json.dumps(receive(args.packets,args.out,args.model,args.reasoning_effort,args.resume,
                                args.review_model,args.review_reasoning_effort)))


if __name__=='__main__':main()
