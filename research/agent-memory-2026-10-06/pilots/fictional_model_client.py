"""Explicit fictional pipeline transport; no live memory or automatic lifecycle.

The caller supplies already scoped prompts. Fixture/rubric bytes never enter a
request automatically. Every role/transport is frozen before the first call.
"""
import json
from pathlib import Path

import receiving_text_api as api
import receiving_codex_native as native


class Client:
    def __init__(self, root, fixture, api_key, catalog, *, operation_effort='low',
                 generation_model='deepseek-flash', review_model='gpt-6.1-sol',
                 revision_model='gpt-6.1-sol', dispatcher=None, operation_output_limit=None,
                 review_protocol='passages', review_effort='low'):
        self.root, self.catalog = Path(root), Path(catalog).resolve()
        self.key, self.dispatcher = api_key, dispatcher
        corpus = json.loads(Path(fixture).read_text())
        if corpus.get('fictional') is not True or operation_effort not in {'low','none'}:
            raise ValueError('explicit fictional fixture and operation effort required')
        if generation_model != 'deepseek-flash' or review_model != 'gpt-6.1-sol' or revision_model != 'gpt-6.1-sol':
            raise ValueError('explicit current Flash/native-Sol candidate roles required')
        self.operation_effort = operation_effort
        if review_effort not in {'low','medium'}:
            raise ValueError('explicit native low or medium verification effort required')
        self.review_effort = review_effort
        if review_protocol not in {'passages','assertions'}:
            raise ValueError('explicit passages or assertions review protocol required')
        self.review_protocol = review_protocol
        if operation_output_limit is not None and (
                type(operation_output_limit) is not int or not 1 <= operation_output_limit <= 32768):
            raise ValueError('explicit operation output limit must be an integer from 1 to 32768')
        self.operation_output_limit = operation_output_limit
        self.roles = dict(generation_model=generation_model,review_model=review_model,
                          revision_model=revision_model)
        frozen = dict(format='hmk-fictional-model-client/v1',fixture_sha256=api.exchange.checksum(Path(fixture)),
            operation_model='deepseek-flash',operation_effort=operation_effort,**self.roles,
            narrative_effort='low',review_protocol=review_protocol,
            client_sha256=api.exchange.checksum(Path(__file__)),
            api_sha256=api.exchange.checksum(Path(api.__file__)),
            native_sha256=api.exchange.checksum(Path(native.__file__)),
            narrative_sha256=api.exchange.checksum(Path(api.exchange.narrative.__file__)),
            assertion_review_sha256=api.exchange.checksum(Path(api.exchange.narrative.review_shape.__code__.co_filename)),
            catalog_sha256=api.exchange.checksum(self.catalog),tools_allowed=False,native_memory_allowed=False)
        if operation_output_limit is not None:
            frozen['operation_output_limit'] = operation_output_limit
        if review_effort != 'low':
            frozen['review_effort'] = review_effort
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        path = self.root/'client-conditions.json'
        if path.exists() and json.loads(path.read_text()) != frozen:
            raise ValueError('pipeline transport changed; preserve pending work')
        api.exchange.pilot.save(path,frozen)

    def chat(self, model, messages, trace):
        root = self.root/trace.path.parent.name
        root.mkdir(exist_ok=True,mode=0o700)
        if trace.phase.startswith('narrative_'):
            expected = (self.roles['review_model'] if trace.phase == 'narrative_review' else
                        self.roles['generation_model'] if trace.phase == 'narrative_generation' and len(messages) == 2 else
                        self.roles['revision_model'])
            if model != expected:
                raise ValueError('narrative call does not match frozen processing role')
            if trace.phase == 'narrative_review':
                protocol = json.loads(messages[1]['content']).get('review_protocol')
                expected_protocol = 'assertions/v2' if self.review_protocol == 'assertions' else 'passages/v1'
                if protocol != expected_protocol:
                    raise ValueError('narrative review does not match frozen support protocol')
            transport = api.exchange.FileExchange(root,'low',self.review_effort)
            try:
                return transport(model,messages,trace)
            except api.exchange.ResponsePending as pending:
                path = Path(str(pending))
                self._dispatch(path,root)
                return transport(model,messages,trace)
        if model != 'deepseek-flash':
            raise ValueError('fictional operation requires direct Flash')
        request = dict(format='hmk-fictional-memory-operation/v1',fictional=True,
            model=model,phase=trace.phase,reasoning_effort=self.operation_effort,
            messages=messages,response_schema={'type':'object'},fresh_context=True,
            tools_allowed=False,native_memory_allowed=False)
        if self.operation_output_limit is not None:
            request['output_token_limit'] = self.operation_output_limit
        d = api.exchange.pilot.digest(request)
        path = root/'requests'/(d+'.json');path.parent.mkdir(exist_ok=True)
        if path.exists() and json.loads(path.read_text()) != request:
            raise ValueError('fictional operation hash collision')
        api.exchange.pilot.save(path,request)
        response_path = root/'responses'/path.name
        if not response_path.exists():
            self._dispatch(path,root)
        response = json.loads(response_path.read_text())
        receipt = json.loads(Path(response['dispatch_receipt']).read_text())
        if (response['request_sha256'] != d or response['requested_model'] != model
                or response['fresh_context'] is not True or response['tool_calls_observed'] != []
                or receipt.get('state') != 'completed' or receipt.get('content') != response['content']
                or receipt.get('parameters') != api.parameters(request,'deepseek')):
            raise ValueError('operation response lacks matching observed parameters/content')
        existing = next((i for i,r in enumerate(trace) if r.get('external_request_sha256') == d),None)
        index = existing if existing is not None else trace.begin(dict(external_request_sha256=d,
            requested_model=model,requested_reasoning_effort=self.operation_effort,
            parameters_sha256=receipt['parameters_sha256']))
        trace.finish(index,dict(state='completed',usage=response.get('usage'),seconds=response.get('seconds'),
            dispatch_receipt=response['dispatch_receipt'],response_content=response['content'],
            finish_reason=response.get('finish_reason')))
        if response.get('finish_reason') == 'length':
            return {'_invalid_json':response['content'],'_finish_reason':'length'}
        try:
            return json.loads(response['content'])
        except json.JSONDecodeError:
            return {'_invalid_json':response['content']}

    def _dispatch(self, path, root):
        if (root/'dispatches'/path.name).exists():
            raise RuntimeError('observed or unresolved dispatch; no implicit retry')
        if self.dispatcher is not None:
            return self.dispatcher(path,root)
        request = json.loads(path.read_text())
        if request['model'] == 'gpt-6.1-sol':
            return native.dispatch(path,root,self.catalog)
        return api.dispatch(path,root,self.key,'deepseek')
