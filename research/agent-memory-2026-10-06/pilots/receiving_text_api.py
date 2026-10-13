"""Finite stateless DeepSeek/Nous text dispatch for fictional receiving requests.

Credentials remain in the caller. No implicit retry, tools, native harness,
retrieval, private session, provider fallback or production integration occurs.
"""
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

import receiving_exchange as exchange
from provider_status import classify

ENDPOINTS = {
    'deepseek': 'https://api.deepseek.com/v1/chat/completions',
    'nous': 'https://inference-api.nousresearch.com/v1/chat/completions',
}
MODELS = {'deepseek': {'deepseek-flash'}, 'nous': {'openai/gpt-6.1-sol'}}


def parameters(request, provider, generation_limit=12000, review_limit=32768):
    receiving = (request.get('format') == 'hmk-fictional-receiving-request/v1'
                 and request.get('phase') in {'narrative_generation','narrative_revision','narrative_review'})
    operation = (provider == 'deepseek' and request.get('fictional') is True
                 and request.get('format') == 'hmk-fictional-memory-operation/v1'
                 and request.get('phase') in {'capture','capture_review','recall','consolidation','consolidation_review'})
    if (provider not in MODELS or request.get('model') not in MODELS[provider]
            or not (receiving or operation)
            or request.get('reasoning_effort') not in (
                {'low', 'high', 'none'} if provider == 'deepseek' else {'low', 'high'})
            or request.get('fresh_context') is not True
            or request.get('tools_allowed') is not False
            or request.get('native_memory_allowed') is not False):
        raise ValueError('explicit supported fictional text profile required')
    if any(type(n) is not int or not 1 <= n <= 32768 for n in (generation_limit, review_limit)):
        raise ValueError('invalid explicit output limits')
    operation_limit = request.get('output_token_limit')
    if operation_limit is not None and (
            not operation or type(operation_limit) is not int or not 1 <= operation_limit <= 32768):
        raise ValueError('explicit output token override requires a supported fictional operation')
    messages = request['messages']
    if (not isinstance(messages, list) or not messages or messages[0].get('role') != 'system'
            or any(set(m) != {'role', 'content'} or not isinstance(m['content'], str)
                   or m['role'] not in {'system', 'user', 'assistant'} for m in messages)):
        raise ValueError('only supplied textual roles/content are supported')
    messages = [dict(messages[0], content=messages[0]['content'] +
        '\nReturn only JSON conforming to this output schema. This constrains '
        'syntax, not evidence or truth:\n' + json.dumps(request['response_schema'])),
        *messages[1:]]
    value = dict(model=request['model'], messages=messages,
        reasoning_effort=request['reasoning_effort'], response_format={'type': 'json_object'},
        max_tokens=(operation_limit if operation_limit is not None else
                    review_limit if request['phase'] == 'narrative_review' else generation_limit))
    if provider == 'deepseek':
        value['thinking'] = {'type': 'disabled' if request['reasoning_effort'] == 'none' else 'enabled'}
        if request['reasoning_effort'] == 'none':
            del value['reasoning_effort']
    # No temperature/reasoning budget: the selected reasoning modes do not
    # establish those controls. Local semantic and schema gates are unchanged.
    return value


def dispatch(request_path, root, api_key, provider, opener=urllib.request.urlopen,
             generation_limit=12000, review_limit=32768):
    request_path, root = Path(request_path), Path(root)
    request = json.loads(request_path.read_text())
    key_hash = exchange.pilot.digest(request)
    if request_path.stem != key_hash:
        raise ValueError('request filename/hash mismatch')
    payload = parameters(request, provider, generation_limit, review_limit)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError('explicit configured inference credential required')
    receipt_path = root/'dispatches'/(key_hash+'.json')
    response_path = root/'responses'/(key_hash+'.json')
    if receipt_path.exists() or response_path.exists():
        raise ValueError('preserve observed or unresolved dispatch; no implicit retry')
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = dict(request_sha256=key_hash, provider=provider, endpoint=ENDPOINTS[provider],
        parameters=payload, parameters_sha256=exchange.pilot.digest(payload),
        fresh_context_basis='one stateless text-only HTTP request with only these messages',
        native_memory_basis='no native harness is invoked', state='started', usage=None,
        qualification=False, transport_timeout_seconds=300)
    exchange.pilot.save(receipt_path, receipt)
    started = time.monotonic()
    call = urllib.request.Request(ENDPOINTS[provider], data=json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer '+api_key, 'Content-Type': 'application/json'})
    try:
        with opener(call, timeout=300) as response:
            receipt['http_status'] = response.status
            result = json.load(response)
        choice = result['choices'][0]
        message = choice['message']
        receipt.update(state='completed', response_id=result.get('id'),
            response_model=result.get('model'), response_provider=result.get('provider'),
            usage=result.get('usage'), finish_reason=choice.get('finish_reason'),
            content=message.get('content'), tool_calls_observed=message.get('tool_calls') or [])
    except BaseException as error:
        # Include interrupted and incomplete-body attempts. Re-raise unchanged;
        # store only the class, never exception text or partial response bytes.
        receipt.update(state='failed', error_type=type(error).__name__)
        receipt['problem'] = classify(error)
        if isinstance(error, urllib.error.HTTPError):
            receipt['http_status'] = error.code
        raise
    finally:
        receipt['seconds'] = time.monotonic()-started
        exchange.pilot.save(receipt_path, receipt)
    if receipt['tool_calls_observed'] or not isinstance(receipt['content'], str):
        raise ValueError('unexpected tool request or missing final text; preserve receipt')
    response_path.parent.mkdir(exist_ok=True)
    exchange.pilot.save(response_path, dict(request_sha256=key_hash,
        requested_model=request['model'], response_model=receipt['response_model'],
        fresh_context=True, tool_calls_observed=[], dispatch_receipt=str(receipt_path),
        usage=receipt['usage'], seconds=receipt['seconds'], content=receipt['content'],
        finish_reason=receipt['finish_reason']))
    return receipt_path
