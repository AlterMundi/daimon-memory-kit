"""Finite processing: durable retry, bounded batches and no inference for metadata."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import embedding_health
import embedding_space
from capture_inbox import Inbox
from portable_producer import process_once


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('HMK_AGENT_MEMORY_BASE',str(tmp_path/'canon'))
    monkeypatch.setenv('HMK_DB_PATH',str(tmp_path/'canon/library.db'))
    spec=importlib.util.spec_from_file_location('producer_memory',SCRIPTS/'memoryctl.py')
    memory=importlib.util.module_from_spec(spec);spec.loader.exec_module(memory);memory.init_db()
    binding={'subject':'fixture:ilex','source_instance':'fixture:desk'}
    inbox=Inbox(tmp_path/'capture.sqlite',binding)
    raw=(json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'Jo taught a clamp technique on June 3.'}]}})+'\n').encode()
    inbox.observe('session-a',{'hook_event_name':'Stop'},raw)
    calls=[]
    def propose(request,path):
        calls.append(request)
        sources=json.loads(request['messages'][1]['content'])['sources']
        return {'selection':dict(outcome='applied',reason='Significant encounter',records=[
            dict(key='jo',operation='add',shelf='episodes',title='Jo',source_ids=[sources[0]['id']])],links=[]),
            'dispatch':{'model':'fixture','calls':1}}
    return memory,inbox,tmp_path/'processor',propose,binding,calls,raw


def run(setup,**kwargs):
    memory,inbox,state,propose,binding,_,_=setup
    return process_once(memory,inbox,state,propose,binding,**kwargs)


@pytest.mark.parametrize('point',['after_stage','after_canon_commit'])
def test_uncertain_commit_resumes_without_new_inference_or_duplicate_memory(setup,point):
    def crash(at):
        if at==point:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):run(setup,_fault=crash)
    receipt=run(setup)
    assert receipt['state']=='complete' and not receipt['proposer_invoked']
    assert len(setup[5])==1
    with setup[0].connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==1
        assert c.execute('select count(*) from native_learning_artifacts').fetchone()[0]==1
    assert run(setup)['state']=='idle'


def test_capture_can_continue_and_lifecycle_only_batch_needs_no_model(setup):
    memory,inbox,state,propose,binding,calls,raw=setup
    first=run(setup,limit=1)
    inbox.observe('session-a',{'hook_event_name':'SessionEnd'},raw)
    second=run(setup,limit=1)
    assert first['processed_through']==1 and second['processed_through']==2
    assert not second['proposer_invoked'] and len(calls)==1
    assert second['receipt']['state']=='omitted' and second['artifact_id'] is None
    with memory.connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==1
        assert c.execute('select count(*) from native_learning_artifacts').fetchone()[0]==1


def test_provider_unavailable_retains_frozen_job_for_resume(setup):
    memory,inbox,state,propose,binding,calls,raw=setup
    def unavailable(*args):raise ConnectionError('provider unavailable')
    with pytest.raises(ConnectionError):process_once(memory,inbox,state,unavailable,binding)
    assert (state/'batch-1.json').exists() and not (state/'index.json').exists()
    assert run(setup)['state']=='complete' and len(calls)==1


def test_incomplete_prompt_does_not_advance_past_missing_input(setup):
    memory,inbox,state,propose,binding,calls,raw=setup
    inbox.observe('session-a',{'hook_event_name':'UserPromptSubmit','prompt':'A later report'},raw)
    assert run(setup)['state']=='deferred' and not calls
    assert not (state/'index.json').exists()


def test_bound_destination_and_missing_dependency_fail_before_model(setup,tmp_path):
    memory,inbox,state,propose,binding,calls,raw=setup
    run(setup)
    with pytest.raises(ValueError,match='different producer destination'):
        process_once(memory,inbox,tmp_path/'other',propose,binding)
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'later'},raw+b'{"type":"event_msg","payload":{}}\n')
    with inbox.connect() as c:c.execute('update revisions set delta=? where id=1',(b'altered',))
    with pytest.raises(ValueError,match='altered'):run(setup)
    assert len(calls)==1


def test_early_prompt_resolves_from_later_snapshot_past_batch_boundary(setup):
    memory,inbox,state,propose,binding,calls,raw=setup
    run(setup)
    text='A later report'
    inbox.observe('session-a',{'hook_event_name':'UserPromptSubmit','prompt':text},raw)
    assert run(setup,limit=1)['state']=='deferred'
    raw+=(json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}})+'\n').encode()
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'next'},raw)
    def omit(request,path):
        assert any(s['content']==text for s in json.loads(request['messages'][1]['content'])['sources'])
        return {'selection':dict(outcome='omitted',reason='Routine report',records=[],links=[])}
    assert process_once(memory,inbox,state,omit,binding,limit=1)['processed_through']==2
    assert run(setup,limit=1)['proposer_invoked'] is False


def test_explicit_reprepare_preserves_invalid_proposal_without_advancing(setup):
    from portable_producer import reprepare_pending
    memory,inbox,state,propose,binding,calls,raw=setup
    def invalid(request,path):return {'selection':dict(outcome='applied',reason='bad',records=[{}],links=[])}
    pending=process_once(memory,inbox,state,invalid,binding)
    assert pending['state']=='pending' and 'two corrections' in pending['reason']
    result=reprepare_pending(memory,inbox,state,'Fix invalid selection representation')
    assert Path(result['preserved_job']).is_file() and not result['cursor_advanced']
    assert run(setup)['state']=='complete'


def test_reprepare_cannot_discard_an_uncertain_canonical_commit(setup):
    from portable_producer import reprepare_pending
    def crash(at):
        if at=='after_canon_commit':raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):run(setup,_fault=crash)
    with pytest.raises(ValueError,match='staged work'):
        reprepare_pending(setup[0],setup[1],setup[2],'must not reset')
    assert run(setup)['state']=='complete'


def test_one_processor_while_capture_continues_from_another_session(setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    memory,inbox,state,propose,binding,calls,raw=setup
    entered,release=Event(),Event()
    def held(request,path):
        entered.set();assert release.wait(5)
        return propose(request,path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(process_once,memory,inbox,state,held,binding)
        assert entered.wait(5)
        try:
            with pytest.raises(BlockingIOError):run(setup)
            inbox.observe('session-b',{'hook_event_name':'Stop'},raw.replace(b'Jo taught',b'Rin taught'))
        finally:release.set()
        assert future.result()['processed_through']==1
    def next_session(request,path):
        sources=json.loads(request['messages'][1]['content'])['sources']
        assert len(sources)==1 and 'Rin taught' in sources[0]['content']
        return {'selection':dict(outcome='applied',reason='Another encounter',records=[dict(key='rin',operation='add',shelf='episodes',title='Rin',source_ids=[sources[0]['id']])],links=[])}
    assert process_once(memory,inbox,state,next_session,binding)['processed_through']==2
    with memory.connect() as con:assert con.execute('select count(*) from chapters').fetchone()[0]==2


def test_lost_source_dependency_detected_and_recovered_from_verified_snapshot(setup,tmp_path):
    from sqlite_snapshot import verified_snapshot
    import shutil
    memory,inbox,state,propose,binding,calls,raw=setup
    backup=tmp_path/'inbox-snapshot.sqlite';verified_snapshot(inbox.path,backup)
    with inbox.connect() as con:con.execute('update revisions set delta=? where id=1',(b'lost',))
    with pytest.raises(ValueError,match='altered'):run(setup)
    assert not calls
    shutil.copy2(inbox.path,tmp_path/'damaged-preserved.sqlite')
    shutil.copy2(backup,inbox.path)
    assert run(setup)['state']=='complete'
    assert inbox.restore(1)==raw


def test_out_of_order_source_cannot_hide_newer_pending_bytes(setup):
    memory,inbox,state,propose,binding,calls,raw=setup
    newer=raw+(json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'Jo later corrected the clamp account.'}]}})+'\n').encode()
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'newer'},newer)
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'late-old'},raw)
    result=run(setup)
    assert result['state']=='deferred' and 'branch' in result['reason']
    assert not calls and not (state/'index.json').exists()
    # A recovered complete snapshot covers both earlier acknowledged versions.
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'recovered'},newer)
    assert run(setup)['processed_through']==4
    assert len(calls)==1
    sources=json.loads(calls[0]['messages'][1]['content'])['sources']
    assert any('corrected' in s['content'] for s in sources)


@pytest.fixture
def selected(setup, tmp_path, monkeypatch):
    run(setup)
    memory, inbox, state, _, binding, *_ = setup
    env = tmp_path / 'embedding.env'
    env.write_text('HERMES_EMBED_PROVIDER=model2vec\nHERMES_EMBED_MODEL=fixture\nHERMES_EMBED_OUTPUT_DIMS=3\n')
    monkeypatch.setattr(memory, 'HERMES_ENV_PATH', env)
    binding_path = tmp_path / 'binding.json'
    binding_path.write_text(json.dumps(binding))
    config = dict(binding=str(binding_path), inbox=str(inbox.path), context=binding,
                  embedding_env_file=str(env), state_dir=str(state))
    monkeypatch.setattr(embedding_health, 'load_memory', lambda _: memory)
    monkeypatch.setattr(embedding_space, 'load_memory', lambda _: memory)
    real_embed = lambda provider, texts, **args: [[0., 1., 0.] if 'luna' in text else [1., 0., 0.] for text in texts]
    monkeypatch.setattr(memory, 'embed_texts', real_embed)
    return config, memory, inbox


def test_offline_health_fails_then_repairs_exactly_once(selected, monkeypatch):
    config, memory, _ = selected
    embed = memory.embed_texts
    def offline(**args):
        raise memory.EmbeddingBackendError('secret diagnostic')
    monkeypatch.setattr(memory, 'embed_texts', offline)
    assert embedding_health.check(config) == {'state': 'unavailable'}
    monkeypatch.setattr(memory, 'embed_texts', embed)
    result = embedding_health.check(config)
    assert result['state'] == 'healthy' and result['repaired'] == 1
    assert embedding_health.check(config)['repaired'] == 0
    with memory.connect() as con:
        assert con.execute('SELECT count(*) FROM chapters').fetchone()[0] == 1


def test_cutover_preserves_cursor_and_preimage(selected, tmp_path):
    config, memory, inbox = selected
    with inbox.connect() as con:
        owner = json.loads(con.execute('SELECT value FROM producer_owner').fetchone()[0])
    cursor = Path(config['state_dir']) / 'embedding-index.json'
    old_space = memory.embeddings_runtime_config()
    old_cursor = dict(owner=owner, space=old_space, after=31)
    cursor.write_text(json.dumps(old_cursor))
    target = dict(old_space, model='target-fixture')
    receipts = tmp_path/'receipts'
    with pytest.raises(ValueError, match='missing or outdated'):
        embedding_space.select_space(config, target, receipts)
    assert not receipts.exists()
    env = Path(config['embedding_env_file']).read_bytes()
    assert memory.backfill_embeddings(provider='model2vec', model='target-fixture')['processed'] == 1
    output = embedding_space.select_space(config, target, receipts)
    assert output['preserved_cursors'] == {'embedding-index.json': 31}
    assert json.loads(cursor.read_bytes()) == dict(old_cursor, space=target)
    assert json.loads((receipts/'embedding-index.json.before').read_bytes()) == old_cursor
    assert (receipts/'embedding-environment.before').read_bytes() == env
