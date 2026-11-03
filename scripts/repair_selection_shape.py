"""Explicit model-free completion of empty omitted/deferred result arrays.

Only missing records/links arrays may be supplied. Original proposals, sources,
halt and dispatch receipts remain unchanged. Normal admission still validates.
"""
import argparse
import fcntl
import json
from pathlib import Path

from capture_inbox import Inbox, sha
from capturectl import digest, wire
from codex_coordinator import checkpoint
from memory_runtime import profile
from portable_producer import _code_hash
from portable_capture import selected_decision
from selection_navigation import effective_sources


def complete_empty(value):
    if (not isinstance(value,dict) or value.get('outcome') not in {'omitted','deferred'}
            or not {'outcome','reason'}<=set(value)<= {'outcome','reason','records','links'}
            or not isinstance(value['reason'],str) or not value['reason'].strip()
            or all(k in value for k in ('records','links'))
            or any(k in value and value[k]!=[] for k in ('records','links'))):
        raise ValueError('only missing empty arrays on explicit omitted/deferred results may be completed')
    return dict(value,records=[],links=[])


def repair(value,sequence,reason):
    if type(sequence) is not int or sequence<1 or not isinstance(reason,str) or not 1<=len(reason.strip())<=500:
        raise ValueError('exact pending sequence and bounded explicit reason required')
    state=Path(value['state_dir']).resolve();binding=json.loads(Path(value['binding']).read_text())
    if any(binding.get(k)!=value['context'][k] for k in ('subject','source_instance')):raise ValueError('receiving owner differs')
    inbox=Inbox(value['inbox'],binding)
    with open(str(inbox.path)+'.worker.lock','a+b') as worker,open(str(inbox.path)+'.producer.lock','a+b') as producer:
        fcntl.flock(worker,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(producer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=state/f'batch-{sequence}.json';job=json.loads(path.read_text())
        with inbox.connect() as c:owner=json.loads(c.execute('select value from producer_owner').fetchone()[0])
        if (job['owner']!=owner or owner['database']!=str(Path(value['database']).resolve()) or owner['state_dir']!=str(state)
                or owner['capture_binding']!=digest(binding) or owner['context']!=value['context']
                or job['input_hash']!=digest(job['inputs']) or job['code_hash']!=_code_hash()):
            raise ValueError('original source-bound pending runtime required')
        for r in job['inputs']['revisions'].values():
            if sha(inbox.restore(r['revision']))!=r['sha256']:raise ValueError('retained sources changed')
        directory=state/f'batch-{sequence}-empty-array-repair';authorization=dict(reason=reason,input_hash=job['input_hash'],navigation_hash=digest(job['navigation']),code_hash=job['code_hash'])
        if (directory/'authorization.json').exists():
            if json.loads((directory/'authorization.json').read_text())!=authorization:raise ValueError('retained repair differs')
            retained=json.loads((directory/'proposal.json').read_text())
            if 'proposal' not in job and job==json.loads((directory/'job-before.json').read_text()):
                job['proposal']=retained;job['state']='proposed';job['shape_repair']=dict(kind='missing_empty_arrays',authorization_hash=digest(authorization))
                checkpoint(path,job)
                return dict(state='repaired_for_validation',model_calls=0,cursor_advanced=False)
            if job.get('proposal')!=retained:raise ValueError('retained repaired proposal changed')
            return dict(state='replayed',model_calls=0,cursor_advanced=False)
        current=json.loads((state/'index.json').read_text())['sequence']+1 if (state/'index.json').exists() else 1
        if sequence!=current or job['state']!='prepared' or 'proposal' in job or not job['navigation'].get('halted_reason'):
            raise ValueError('current uncommitted halted selection required')
        original=job['navigation']['steps'][-1]
        if original.get('feedback',{}).get('selection_error')!='closed block-selection decision required':raise ValueError('demonstrated result shape failure required')
        candidate=json.loads(wire(original['proposal']));candidate['selection']=complete_empty(candidate['selection'])
        selected_decision(candidate['selection'],effective_sources(job),job['navigation']['canon'])
        directory.mkdir(mode=0o700,exist_ok=True)
        checkpoint(directory/'job-before.json',job);checkpoint(directory/'proposal.json',candidate);checkpoint(directory/'authorization.json',authorization)
        job['proposal']=candidate;job['state']='proposed';job['shape_repair']=dict(kind='missing_empty_arrays',authorization_hash=digest(authorization))
        checkpoint(path,job)
        return dict(state='repaired_for_validation',model_calls=0,cursor_advanced=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True);p.add_argument('--sequence',type=int,required=True);p.add_argument('--reason',required=True);a=p.parse_args()
    print(json.dumps(repair(profile(a.profile),a.sequence,a.reason)))

if __name__=='__main__':main()
