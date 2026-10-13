"""Long captures make finite progress without losing source dependencies."""
# ruff: noqa: F811
import json

import pytest

from tests.test_portable_producer import setup  # noqa: F401
from portable_producer import process_once
from source_windows import select


def block(key, text, *, status='new', dependencies=()):
    return dict(id=key,content=text,status=status,dependencies=list(dependencies))


def message(text, turn):
    return (json.dumps(dict(type='turn_context',payload=dict(turn_id=turn)))+'\n'+
        json.dumps(dict(type='response_item',payload=dict(type='message',role='user',
        content=[dict(type='input_text',text=text)])))+'\n').encode()


def omitted(request,path):
    return dict(selection=dict(outcome='omitted',reason='Fictional mechanical noise.',records=[],links=[]))


def test_dependencies_survive_across_windows_as_context_and_no_block_is_truncated():
    groups={'s':[block('opener','Why did it fail?'),block('call','send invitation',dependencies=['opener']),
                 block('result','delivery failed',dependencies=['call'])]}
    first=select(groups,{},120)
    assert [s['id'] for s in first['sources']]==['opener'] and not first['complete']
    second=select(groups,first['progress'],1000)
    assert second['complete']
    assert [(s['id'],s['status']) for s in second['sources']]==[
        ('opener','earlier_context'),('call','new'),('result','new')]
    assert second['sources'][2]['content']=='delivery failed'
    assert groups['s'][0]['status']=='new'  # Frozen source evidence never mutated.


def test_large_dependency_requests_adjustable_budget_not_a_total_source_limit():
    groups={'s':[block('a','A'*5000),block('b','Result',dependencies=['a'])]}
    too_small=select(groups,{},1000)
    assert too_small['minimum_required_bytes']>5000 and too_small['progress']=={}
    first=select(groups,{},too_small['minimum_required_bytes'])
    assert [s['id'] for s in first['sources']]==['a']
    pending=select(groups,first['progress'],1000)
    assert pending['minimum_required_bytes']>5000
    done=select(groups,first['progress'],pending['minimum_required_bytes'])
    assert done['complete'] and done['sources'][0]['status']=='earlier_context'


def test_old_unrelated_source_is_not_sent_again_but_causal_context_is():
    groups={'s':[block('old','x'*1000000,status='earlier_context'),
                 block('request','Question',status='earlier_context'),
                 block('new','Correction',dependencies=['request'])]}
    win=select(groups,{},1000)
    assert win['complete'] and [s['id'] for s in win['sources']]==['request','new']
    assert win['used_bytes']<1000


def test_missing_dependency_is_never_silently_dropped():
    with pytest.raises(ValueError,match='missing source dependency'):
        select({'s':[block('x','result',dependencies=['missing'])]}, {},1000)


def test_long_first_capture_progresses_after_crash_and_concurrent_capture(setup):
    memory,inbox,state,_,binding,_,raw=setup
    # Reuse the ordinary first observation, then a >1MiB selected source.
    large=raw+b''.join(message('Routine fixture '+str(i)+' '+'x'*20000,str(i)) for i in range(55))
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'large'},large)
    seen=[]
    def consume(request,path):
        sources=json.loads(request['messages'][1]['content'])['sources']
        assert len(json.dumps(sources).encode())<65000
        seen.extend(s['id'] for s in sources if s['status']=='new')
        return omitted(request,path)
    def crash(point):
        if point=='after_canon_commit':
            raise RuntimeError('power loss')
    with pytest.raises(RuntimeError,match='power loss'):
        process_once(memory,inbox,state,consume,binding,_fault=crash)
    first_ids=list(seen)
    # New capture does not alter the prepared group or redo its paid work.
    later=large+message('New report after the frozen batch','later')
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'later'},later)
    recovered=process_once(memory,inbox,state,consume,binding)
    assert not recovered['proposer_invoked'] and seen==first_ids
    assert recovered['processed_through']==0 and not recovered['source_group_complete']
    windows=1
    while not recovered['source_group_complete']:
        recovered=process_once(memory,inbox,state,consume,binding)
        windows+=1
        assert windows<30
    assert recovered['processed_through']==2
    assert len(seen)==len(set(seen))==56
    # Later work remains visible and is processed after the pinned group.
    recovered=process_once(memory,inbox,state,consume,binding)
    assert recovered['processed_through']==3 and recovered['source_group_complete']
    assert len(seen)==len(set(seen))==57
    assert process_once(memory,inbox,state,consume,binding)['state']=='idle'
    assert inbox.restore(3)==later
    with memory.connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==0
        assert c.execute('select count(*) from capture_events').fetchone()[0]==windows+1


def test_new_delta_ignores_large_already_processed_history(setup):
    memory,inbox,state,_,binding,_,raw=setup
    large=raw+message('Old context '+'x'*1100000,'old')
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'large'},large)
    pending=process_once(memory,inbox,state,omitted,binding)
    assert not pending['source_group_complete']
    pending=process_once(memory,inbox,state,omitted,binding)
    assert pending['state']=='pending' and pending['minimum_required_bytes']>1100000
    done=process_once(memory,inbox,state,omitted,binding,source_budget_bytes=pending['minimum_required_bytes'])
    assert done['source_group_complete']
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'new'},large+message('Jo corrected the encounter.','new'))
    def select_correction(request,path):
        sources=json.loads(request['messages'][1]['content'])['sources']
        assert len(sources)==1 and sources[0]['content']=='Jo corrected the encounter.'
        return dict(selection=dict(outcome='applied',reason='Correction',records=[
            dict(key='jo',operation='add',shelf='episodes',title='Jo',source_ids=[sources[0]['id']])],links=[]))
    result=process_once(memory,inbox,state,select_correction,binding)
    assert result['state']=='complete' and result['source_group_complete']
    assert (state/'batch-3-before.sqlite').exists()


def test_pending_group_loss_is_detected_without_replaying_or_skipping(setup):
    memory,inbox,state,_,binding,_,raw=setup
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'large'},raw+message('x'*5000,'second'))
    result=process_once(memory,inbox,state,omitted,binding,source_budget_bytes=1000)
    assert not result['source_group_complete']
    path=state/'source-group-after-0.json'
    original=path.read_bytes()
    path.unlink()
    with pytest.raises(ValueError,match='missing frozen source group'):
        process_once(memory,inbox,state,omitted,binding)
    path.write_bytes(original)
    assert process_once(memory,inbox,state,omitted,binding)['source_group_complete']


def test_prior_context_navigation_resumes_without_relearning_old_experience(setup):
    memory,inbox,state,_,binding,_,raw=setup
    process_once(memory,inbox,state,omitted,binding)
    newer=raw+message('That encounter was on June 4, not June 3.','correction')
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'correction'},newer)
    seen=[]
    def proposer(request,path):
        payload=json.loads(request['messages'][1]['content'])
        sources=payload['sources']
        seen.append(sources)
        if len(seen)==1:
            assert len(sources)==1 and 'That encounter' in sources[0]['content']
            return dict(selection=dict(outcome='lookup',requests=[dict(action='source_before',
                record_uid=sources[0]['id'],query='',offset=0,expected_revision=0)]))
        context=next(s for s in sources if s['status']=='earlier_context')
        new=next(s for s in sources if s['status']=='new')
        assert context['content']=='Jo taught a clamp technique on June 3.'
        assert sources.index(context)<sources.index(new)
        return dict(selection=dict(outcome='applied',reason='Dated correction with its original referent',
            records=[dict(key='correction',operation='add',shelf='episodes',title='That encounter',
                source_ids=[context['id'],new['id']])],links=[]))
    pending=process_once(memory,inbox,state,proposer,binding,navigation_steps=1)
    assert pending['state']=='pending' and pending['processed_through']==1
    # Another foreground invocation resumes the exact saved read context.
    done=process_once(memory,inbox,state,proposer,binding,navigation_steps=1)
    assert done['state']=='complete' and done['processed_through']==2 and len(seen)==2
    with memory.connect() as c:
        rows=c.execute('select raw from chapters').fetchall()
    assert len(rows)==1 and 'Jo taught' in rows[0][0] and 'June 4' in rows[0][0]
    assert rows[0][0].index('Jo taught')<rows[0][0].index('That encounter')
    assert process_once(memory,inbox,state,proposer,binding)['state']=='idle'


def test_source_context_reader_cannot_cross_into_unbound_or_future_data():
    from source_windows import ContextReader
    reader=ContextReader({'a':[block('old','Jo'),block('new','Correction'),block('future','Later')],
                          'other':[block('private','Other source')]},1000)
    assert reader.before('private',{'new'})['status']=='unknown_source_anchor'
    assert reader.before('future',{'new'})['status']=='unknown_source_anchor'
    answer=reader.before('new',{'new'})
    assert [s['id'] for s in answer['sources']]==['old']
    assert answer['sources'][0]['status']=='earlier_context'


def test_source_context_budget_applies_to_accumulated_evidence(setup):
    memory,inbox,state,_,binding,_,raw=setup
    process_once(memory,inbox,state,omitted,binding)
    inbox.observe('session-a',{'hook_event_name':'Stop','turn_id':'correction'},raw+message('That encounter was later.','correction'))
    calls=[]
    def proposer(request,path):
        sources=json.loads(request['messages'][1]['content'])['sources']
        calls.append(request)
        if len(calls)==1:
            return dict(selection=dict(outcome='lookup',requests=[dict(action='source_before',
                record_uid=sources[0]['id'],query='',offset=0,expected_revision=0)]))
        result=json.loads(request['messages'][-1]['content'])['lookup_results'][0]
        assert result['status']=='ok'
        assert len(sources)==2 and sources[0]['status']=='earlier_context'
        return omitted(request,path)
    pending=process_once(memory,inbox,state,proposer,binding,source_budget_bytes=500)
    assert pending['state']=='pending' and pending['processed_through']==1
    assert pending['minimum_required_bytes']>500 and len(calls)==1
    again=process_once(memory,inbox,state,proposer,binding,source_budget_bytes=500)
    assert again['state']=='pending' and not again['proposer_invoked'] and len(calls)==1
    done=process_once(memory,inbox,state,proposer,binding,source_budget_bytes=pending['minimum_required_bytes'])
    assert done['state']=='complete' and len(calls)==2
