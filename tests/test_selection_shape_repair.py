import json
import pytest
from tests.test_portable_producer import setup  # noqa: F401
from tests.test_memory_runtime import configuration
from portable_producer import process_once
from repair_selection_shape import complete_empty,repair


def test_halted_omission_shape_repairs_once_without_another_model_or_memory(setup,tmp_path):
    memory,inbox,state,_,binding,calls,raw=setup
    def malformed(*a):return dict(selection=dict(outcome='omitted',reason='Only routine mechanical output in this fixture'),dispatch=dict(state='complete'))
    assert process_once(memory,inbox,state,malformed,binding)['state']=='pending'
    value=configuration(tmp_path,memory,inbox,state,binding);before=json.loads((state/'batch-1.json').read_text())
    assert repair(value,1,'Complete only the two absent empty arrays')['state']=='repaired_for_validation'
    assert repair(value,1,'Complete only the two absent empty arrays')['state']=='replayed'
    after=json.loads((state/'batch-1.json').read_text());assert before['navigation']==after['navigation']
    def forbidden(*a):pytest.fail('shape repair must not redispatch inference')
    result=process_once(memory,inbox,state,forbidden,binding);assert result['state']=='complete' and result['receipt']['state']=='omitted'
    assert process_once(memory,inbox,state,forbidden,binding)['state']=='idle'
    with memory.connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==0
        assert c.execute('select count(*) from capture_events').fetchone()[0]==1
    assert repair(value,1,'Complete only the two absent empty arrays')['state']=='replayed'


@pytest.mark.parametrize('value',[
 dict(outcome='applied',reason='new memory'),dict(outcome='lookup',reason='look first'),
 dict(outcome='omitted',reason='x',records=[{}]),dict(outcome='omitted',reason='x',links=None),
 dict(outcome='omitted',reason='x',unknown=[]),dict(outcome='omitted',reason=''),
 dict(outcome='omitted',reason='x',records=[],links=[]),
])
def test_shape_repair_cannot_invent_a_decision_drop_records_or_relax_other_fields(value):
    with pytest.raises(ValueError):complete_empty(value)


def test_interrupted_shape_repair_reuses_authorization_and_original_proposal(setup,tmp_path,monkeypatch):
    import repair_selection_shape as module
    memory,inbox,state,_,binding,_,_=setup
    def malformed(*a):return dict(selection=dict(outcome='omitted',reason='Routine fixture only'),dispatch=dict(state='complete'))
    process_once(memory,inbox,state,malformed,binding)
    value=configuration(tmp_path,memory,inbox,state,binding);original=module.checkpoint
    def interrupt(path,payload):
        if Path(path).name=='batch-1.json':raise RuntimeError('interrupted before atomic job update')
        original(path,payload)
    from pathlib import Path
    monkeypatch.setattr(module,'checkpoint',interrupt)
    with pytest.raises(RuntimeError):repair(value,1,'Finish the absent empty arrays')
    monkeypatch.setattr(module,'checkpoint',original)
    assert repair(value,1,'Finish the absent empty arrays')['state']=='repaired_for_validation'
    assert repair(value,1,'Finish the absent empty arrays')['state']=='replayed'
