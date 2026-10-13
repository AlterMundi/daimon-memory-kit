"""Explicit isolated stock-Codex hook probe; no production configuration changes.

The output directory must be new. The supplied catalog disables native shell,
search and unrelated tools. Only the fixed fictional sender is exposed.
"""
import argparse
import sys,json,time,hashlib
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'scripts'),str(Path(__file__).resolve().parent)]
from codex_deep_receiving import Native,save
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--binary',type=Path,required=True)
parser.add_argument('--catalog',type=Path,required=True)
args=parser.parse_args()
root=args.out.resolve()
if root.exists():raise RuntimeError('Use a new evidence directory; do not overwrite an earlier attempt')
root.mkdir(parents=True,mode=0o700)
BINARY=args.binary.resolve();CATALOG=args.catalog.resolve()
home=root/'codex-home'
home.mkdir(parents=True,exist_ok=True)
(home/'memories').mkdir(exist_ok=True)
script='''import sys,json,time,hashlib,os
from pathlib import Path
p=json.load(sys.stdin)
t=p.get('transcript_path')
b=Path(t).read_bytes() if t and Path(t).is_file() else None
item={'payload':p,'observed_ns':time.time_ns(),'transcript':b.decode() if b is not None else None,'sha256':hashlib.sha256(b).hexdigest() if b is not None else None}
with open('/home/debian/.codex/hook-observations.jsonl','a') as f:
 f.write(json.dumps(item)+'\\n');f.flush();os.fsync(f.fileno())
print('{}')
'''
(home/'observe.py').write_text(script)
events=['SessionStart','UserPromptSubmit','Stop','PreCompact','PostCompact','Interrupt','SessionEnd','PostToolUse']
save(home/'hooks.json',{'hooks':{e:[{'hooks':[{'type':'command','command':'python3 /home/debian/.codex/observe.py','timeout':3 if e in {'Interrupt','SessionEnd'} else 10}]}] for e in events}})
if (root/'receipt.json').exists():raise RuntimeError('Existing receipt; inspect before rerun')
class Sender:
 def app_server_response(self,args):
  return {'contentItems':[{'type':'inputText','text':json.dumps({'status':'authentication_failed','delivered':False,'receipt_id':None,'attempt_id':'send-77'})}],'success':True}
tools=[{'name':'message_send','description':'Fictional delivery service. Returns the actual delivery outcome.','inputSchema':{'type':'object','properties':{'to':{'type':'string'},'text':{'type':'string'}},'required':['to','text'],'additionalProperties':False}}]
n=Native(root,BINARY,CATALOG,use_memory=False,hook_probe=True,startup_switch_supported=False,transport='proxy',reader=Sender(),probe_tools=tools)
try:
 listed=n.rpc('hooks/list',{'cwds':['/tmp/work']});save(root/'hooks-listed.json',listed)
 state={h['key']:{'trusted_hash':h['currentHash']} for group in listed['data'] for h in group['hooks']}
 n.rpc('config/value/write',{'keyPath':'hooks.state','value':state,'mergeStrategy':'replace'})
 save(root/'trusted.json',n.rpc('hooks/list',{'cwds':['/tmp/work']}))
 n.start('This is an isolated fictional lifecycle test. Respond only to the supplied fictional material. No private context exists.')
 tid=n.tid
 r=n.turn('Fictional continuity marker ALDER-421: Please use message_send to invite Jo Venn (person:552) to compare sensor mounts with Tavi and Ilex. Report the actual result briefly, ending exactly with WILLOW-913.')
 save(root/'normal.json',r)
 n.rpc('thread/compact/start',{'threadId':tid})
 deadline=time.monotonic()+90
 while time.monotonic()<deadline:
  e=n.event(timeout=30)
  if e.get('method')=='turn/completed':break
 save(root/'compact-observed.json',{'event':e})
 r=n.rpc('turn/start',{'threadId':tid,'input':[{'type':'text','text':'Make a long numbered fictional list of 150 distinct pond names; this is a disposable interruption probe.'}],'effort':'low'})
 turn=r['turn']['id']
 while True:
  started_event=n.event(timeout=30)
  if started_event.get('method')=='turn/started' and started_event['params']['turn']['id']==turn:break
 n.rpc('turn/interrupt',{'threadId':tid,'turnId':turn})
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  e=n.event(timeout=30)
  if e.get('method')=='turn/completed' and e['params']['turn']['id']==turn:break
 save(root/'interrupted.json',{'event':e})
 n.rpc('thread/archive',{'threadId':tid})
 save(root/'receipt.json',{'thread_id':tid,'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'transport':'stock app-server Unix listener through stock app-server proxy with WebSocket framing'})
 print('Lifecycle turn, compaction, interruption and archive completed.',flush=True)
finally:n.close()

# A separate native process must recover the same fictional thread.
n=Native(root,BINARY,CATALOG,use_memory=False,hook_probe=True,
         startup_switch_supported=False,transport='proxy')
try:
 n.rpc('thread/unarchive',{'threadId':tid})
 n.resume(tid,'This is the same isolated fictional lifecycle test. Respond only from the supplied conversation; no external tools or private context.')
 save(root/'restart-receipt.json',n.turn('What was the actual outcome of inviting Jo, and was there a delivery receipt? Answer briefly.'))
 n.rpc('thread/archive',{'threadId':tid})
finally:n.close()
