"""Bounded parallel fictional narration/review with per-question checkpoints.

The runner reads only checksum-frozen receiving packets, never hidden rubrics,
source sessions or a memory database. Credentials stay in its explicit caller.
All futures are observed; saved generations, reviews and unresolved dispatches
survive resumption without resetting semantic or repair budgets.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import threading

import receiving_text_api as api


class DispatchBudgetPending(RuntimeError):
    """This invocation's finite budget is spent; phase state remains pending."""


def run(packet_root, out, *, api_key, generation_effort='low', review_effort='low',
        workers=3, max_calls=48, question_keys=None, dispatcher=api.dispatch,
        generation_references=(), response_references=(), review_protocol='passages',
        generation_model='deepseek-flash', review_model=None, revision_model=None):
    review_model = review_model or generation_model
    revision_model = revision_model or generation_model
    if any(m not in {'deepseek-flash','gpt-6.1-sol'}
           for m in (generation_model,review_model,revision_model)):
        raise ValueError('explicit qualified transport model names required')
    native_roles = 'gpt-6.1-sol' in (generation_model,review_model,revision_model)
    if native_roles and (dispatcher is api.dispatch or
            (review_model == 'gpt-6.1-sol' and review_effort != 'low') or
            ('gpt-6.1-sol' in (generation_model,revision_model) and generation_effort != 'low')):
        raise ValueError('native Sol requires explicit native routing and low effort')
    packet_root, out = Path(packet_root), Path(out)
    if not 1 <= workers <= 3 or not 0 <= max_calls <= 528:
        raise ValueError('explicit finite worker/call bounds required')
    source = json.loads((packet_root/'conditions.json').read_text())
    if (source.get('fictional') is not True or
            source['packets_sha256'] != api.exchange.checksum(packet_root/'packets.json')):
        raise ValueError('unchanged explicitly fictional packets required')
    packets = json.loads((packet_root/'packets.json').read_text())
    keys = [(p['arm'], p['answer_index']) for p in packets]
    if len(set(keys)) != len(keys) or any(arm not in {'baseline','proposed'} or
            type(index) is not int or index < 0 for arm, index in keys):
        raise ValueError('unique finite fictional question keys required')
    if generation_effort not in {'low','high','none'} or review_effort not in {'low','high','none'}:
        raise ValueError('explicit supported DeepSeek modes required')
    selected = set(keys if question_keys is None else question_keys)
    if not selected <= set(keys):
        raise ValueError('selected questions must belong to the frozen packets')
    frozen = dict(qualification=False, packets_sha256=source['packets_sha256'],
        generation_model=generation_model, review_model=review_model,
        revision_model=revision_model,
        generation_effort=generation_effort, review_effort=review_effort,
        review_protocol=review_protocol,
        generation_limit=12000, review_limit=32768, workers=workers,
        runner_sha256=api.exchange.checksum(Path(__file__)),
        dispatcher_sha256=api.exchange.checksum(Path(api.dispatch.__code__.co_filename)),
        exchange_sha256=api.exchange.checksum(Path(api.exchange.__file__)),
        narrative_sha256=api.exchange.checksum(Path(api.exchange.narrative.__file__)),
        assertion_review_sha256=api.exchange.checksum(Path(api.exchange.narrative.review_shape.__code__.co_filename)),
        independent_grading_required=True, source_access=False, tools_allowed=False,
        native_memory_allowed=False)
    if native_roles:
        import receiving_codex_native as native
        frozen['native_dispatcher_sha256'] = api.exchange.checksum(Path(native.dispatch.__code__.co_filename))
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (out/'conditions.json').exists() and json.loads((out/'conditions.json').read_text()) != frozen:
        raise ValueError('procedure changed; preserve completed and pending work')
    api.exchange.pilot.save(out/'conditions.json', frozen)
    lock = threading.Lock(); started = 0
    def process(packet):
        nonlocal started
        root = out/packet['arm']/str(packet['answer_index'])
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        answer_path = root/'answer.json'
        if answer_path.exists():
            return dict(arm=packet['arm'],answer_index=packet['answer_index'],state='saved')
        checkpoint = root/'pending.json'
        pending = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        evidence = api.exchange.pilot.answer_evidence(packet['packs'],packet['expanded'])
        context = api.exchange.narrative.supplied_context(packet['question'],evidence,packet['binding'])
        if context != packet['context']:
            raise ValueError('source adapter changed the frozen question context')
        transport = api.exchange.FileExchange(root,generation_effort,review_effort)
        trace = api.exchange.pilot.Trace(root/'trace.json'); trace.phase='recall'
        def chat(model,messages,call_trace):
            nonlocal started
            try:
                return transport(model,messages,call_trace)
            except api.exchange.ResponsePending as request:
                path = Path(str(request))
                prepared = json.loads(path.read_text())
                # Reuse raw observed responses only when the entire actual API
                # payload matches. Local decisions/budgets never migrate.
                references = list(response_references)
                if prepared['phase'] == 'narrative_generation':
                    references += list(generation_references)
                if references:
                    for reference in map(Path,references):
                        prior_path = reference/'responses'/path.name
                        if not prior_path.exists():
                            continue
                        prior = json.loads(prior_path.read_text())
                        receipt = json.loads(Path(prior['dispatch_receipt']).read_text())
                        if (receipt.get('state') != 'completed' or
                                receipt.get('parameters') != api.parameters(prepared,'deepseek') or
                                receipt.get('request_sha256') != path.stem or
                                prior.get('request_sha256') != path.stem or
                                prior.get('requested_model') != prepared['model'] or
                                prior.get('content') != receipt.get('content') or
                                prior.get('fresh_context') is not True or prior.get('tool_calls_observed') != []):
                            raise ValueError('response reuse needs identical observed provider parameters')
                        shutil.copy2(prior_path,root/'responses'/path.name)
                        api.exchange.pilot.save(root/('imported-'+path.stem+'.json'),dict(
                            request_sha256=path.stem,phase=prepared['phase'],original_response=str(prior_path),
                            original_receipt=prior['dispatch_receipt'],parameters_identical=True,
                            additional_inference_calls=0))
                        return transport(model,messages,call_trace)
                if (root/'dispatches'/path.name).exists():
                    raise RuntimeError('unresolved observed dispatch; no implicit retry')
                with lock:
                    if started >= max_calls:
                        raise DispatchBudgetPending('finite invocation budget spent')
                    started += 1
                dispatcher(path,root,api_key,'deepseek')
                return transport(model,messages,call_trace)
        try:
            value = api.exchange.narrative.answer(generation_model,packet['question'],evidence,
                packet['binding'],trace,pending,checkpoint,chat,api.exchange.pilot.save,
                review_model=review_model, revision_model=revision_model,
                review_protocol=review_protocol)
        except DispatchBudgetPending:
            return dict(arm=packet['arm'],answer_index=packet['answer_index'],state='pending_budget')
        except (api.exchange.narrative.NarrativeRejected,ValueError) as error:
            state = pending.get('narrative',{})
            if state.get('progress',{}).get('phase') != 'rejected':
                raise
            value = dict(state['generations'][-1],operational_status='rejected',error=str(error))
        finally:
            api.exchange.pilot.save(root/'trace.json',trace)
        api.exchange.pilot.save(answer_path,dict(arm=packet['arm'],answer_index=packet['answer_index'],
            case_id=packet['case_id'],question=packet['question'],context_sha256=packet['context_sha256'],
            answer=value,narrative_attempts=pending['narrative']))
        print(json.dumps(dict(arm=packet['arm'],answer_index=packet['answer_index'],
            rejected=value.get('operational_status')=='rejected',
            generations=len(pending['narrative']['generations']),
            reviews=len(pending['narrative']['reviews']))),flush=True)
        # Keep the completed checkpoint too: source/phase history is evidence.
        return dict(arm=packet['arm'],answer_index=packet['answer_index'],state='completed',
                    rejected=value.get('operational_status')=='rejected')
    results=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[(p,pool.submit(process,p)) for p in packets if (p['arm'],p['answer_index']) in selected]
        for packet,future in futures:
            try:
                results.append(future.result())
            except Exception as error:
                results.append(dict(arm=packet['arm'],answer_index=packet['answer_index'],
                    state='failed',error_type=type(error).__name__))
    completed = [json.loads((out/arm/str(index)/'answer.json').read_text())
                 for arm,index in keys if (out/arm/str(index)/'answer.json').exists()]
    api.exchange.pilot.save(out/'answers.json',completed)
    state=dict(questions=len(keys),completed_candidates=len(completed),new_dispatch_attempts=started,
               invocation_max_calls=max_calls,results=results,qualification=False)
    api.exchange.pilot.save(out/'state.json',state)
    return state
