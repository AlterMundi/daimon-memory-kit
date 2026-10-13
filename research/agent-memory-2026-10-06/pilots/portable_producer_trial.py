"""Explicit finite fictional producer invocation; no hook-owned inference process.

The foreground operator/launcher invokes this after capture, or again to resume.
DeepSeek credentials are supplied by the caller, never discovered or persisted.
A successful response replays; unresolved/failed HTTP attempts require explicit
reconciliation, not an automatic second billable request.
"""
import argparse
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'scripts'))
from capture_inbox import Inbox
from capturectl import digest
from codex_coordinator import checkpoint
from native_producer_delivery import load_memory
from portable_producer import process_once, reprepare_pending, maintain_index_once
from provider_status import ProviderProblem
import receiving_text_api as api


def proposer(api_key, *, output_limit=6000, retry_of=None):
    def propose(request, directory):
        if retry_of is not None:
            prior = directory/'dispatches'/f'{retry_of}.json'
            observed = json.loads(prior.read_text())
            if observed.get('state') == 'completed' and observed.get('finish_reason') == 'stop':
                raise ValueError('successful dispatch is not eligible for a transport retry')
            directory = directory/('retry-of-'+retry_of)
            directory.mkdir(exist_ok=True)
        request = dict(format='hmk-fictional-memory-operation/v1',fictional=True,
            model='deepseek-flash',phase='capture',reasoning_effort='low',
            messages=request['messages'],response_schema=request['response_schema'],
            fresh_context=True,tools_allowed=False,native_memory_allowed=False,
            output_token_limit=output_limit)
        key = digest(request)
        request_path = directory/'requests'/f'{key}.json'
        request_path.parent.mkdir(exist_ok=True)
        if request_path.exists():
            if json.loads(request_path.read_text()) != request:
                raise ValueError('recorded request differs')
        else:
            checkpoint(request_path,request)
        receipt_path = directory/'dispatches'/f'{key}.json'
        if not receipt_path.exists():
            try:
                api.dispatch(request_path,directory,api_key,'deepseek')
            except Exception:
                if receipt_path.exists():
                    receipt=json.loads(receipt_path.read_text())
                    raise ProviderProblem('deepseek',key,receipt.get('problem',{'code':'dispatch_unresolved'})) from None
                raise
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get('state') != 'completed' or receipt.get('finish_reason') != 'stop'
                or receipt.get('tool_calls_observed')):
            raise ProviderProblem('deepseek',key,receipt.get('problem',{'code':
                'response_incomplete' if receipt.get('state')=='completed' else 'dispatch_unresolved'}))
        return dict(selection=json.loads(receipt['content']),dispatch=receipt)
    return propose


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inbox',type=Path,required=True)
    p.add_argument('--binding',type=Path,required=True)
    p.add_argument('--context',type=Path,required=True)
    p.add_argument('--canon',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--limit',type=int,default=32)
    p.add_argument('--index-only',action='store_true',help='Maintain committed selected records without selection or a narrator credential')
    p.add_argument('--output-token-limit',type=int,default=6000)
    p.add_argument('--reprepare-reason')
    p.add_argument('--retry-of',help='Explicit failed/incomplete dispatch hash; originals remain preserved')
    p.add_argument('--fictional-isolated-profile',action='store_true',required=True)
    a=p.parse_args()
    if not a.inbox.is_file():
        p.error('capture inbox must already exist')
    if a.index_only and (a.reprepare_reason or a.retry_of):
        p.error('index-only cannot reprepare selection or retry narrator requests')
    memory=load_memory(a.canon)
    inbox=Inbox(a.inbox,json.loads(a.binding.read_text()))
    if a.index_only:
        result=maintain_index_once(memory,inbox,a.state_dir,limit=a.limit)
        print(json.dumps(result))
        return 0 if result['state'] in {'complete','idle'} else 2
    key=os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        p.error('caller must supply DEEPSEEK_API_KEY')
    if a.reprepare_reason:
        reprepare_pending(memory,inbox,a.state_dir,a.reprepare_reason)
    result=process_once(memory,inbox,a.state_dir,proposer(key,output_limit=a.output_token_limit,retry_of=a.retry_of),
        json.loads(a.context.read_text()),limit=a.limit)
    print(json.dumps(result))
    if result['state'] not in {'complete','idle'}:
        raise SystemExit(2)


if __name__=='__main__':
    raise SystemExit(main())
