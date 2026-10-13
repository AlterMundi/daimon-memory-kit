"""Discover actual stale accounts without redoing valid consolidation passes."""
import json

from tests.test_durable_memory_foundation import mc  # noqa: F401


def account(memory,title,source):
    row=memory._read_chapter(source)
    return memory.add_text('library',title,'An attributed derived account.',metadata={
        'mode':'inferred','evidence':[f"mem:{row['record_uid']}@{row['revision']}"]})


def test_reconciliation_follows_current_dependencies_and_stops_after_commit(mc):  # noqa: F811
    from consolidationctl import reconciliation_plan,preview,apply
    original=mc.add_text('episodes','Trial','The human reported a successful replay.')
    first=account(mc,'Project',original)
    second=account(mc,'Lesson',first)
    assert reconciliation_plan(mc)['state']=='idle'
    mc.update_chapter(original,content='The human corrected the report: some readings were lost.')
    plan=reconciliation_plan(mc,limit=1)
    assert plan['ready'][0]['chapter_id']==first
    assert plan['blocked'][0]['chapter_id']==second
    assert plan['ready_count']==plan['blocked_count']==1
    # Repeating discovery is read-only; no artificial second queue or revision.
    assert plan==reconciliation_plan(mc,limit=1)
    assert mc._read_chapter(first)['revision']==1
    for sequence,target,support in [(1,first,original),(2,second,first)]:
        hint=reconciliation_plan(mc)['ready'][0]
        assert hint['chapter_id']==target
        decision=dict(outcome='applied',reason='Preserve the later correction.',records=[dict(
            key='account',operation='update',chapter_id=target,expected_revision=hint['expected_revision'],
            title=mc._read_chapter(target)['title'],raw='The human corrected the replay report: some readings were lost.',
            engram_type='semantic')])
        apply(preview([support],mc,profile='native'),decision,memory=mc,
              supports_by_record={'account':[support]},stream_id='fixture:reconciliation',
              sequence=sequence,event_id=str(sequence),selection_version='fixture')
    assert reconciliation_plan(mc)['state']=='idle'
    assert mc.history(first)[0]['raw']=='An attributed derived account.'


def test_missing_cyclic_and_protected_support_remain_pending_without_starving_ready(mc):  # noqa: F811
    from consolidationctl import reconciliation_plan
    original=mc.add_text('episodes','Lost original','An original report.')
    missing=account(mc,'Missing evidence',original)
    mc.delete_chapter(original)
    cycle=mc.add_text('library','Cycle','Legacy cyclic account.')
    row=mc._read_chapter(cycle)
    mc.update_chapter(cycle,metadata={'mode':'inferred','evidence':[f"mem:{row['record_uid']}@2"]})
    external=mc.add_text('library','File source','Maintained by a separate source owner.',source_kind='file')
    protected=account(mc,'File-derived',external)
    mc.update_chapter(external,content='Changed externally owned source.')
    ordinary=mc.add_text('episodes','Independent','A separate original.')
    ready=account(mc,'Ready after blocked accounts',ordinary)
    # An observed/native report is not an inferred account to rewrite.
    observed=account(mc,'Observed report',ordinary)
    mc.update_chapter(observed,metadata={'mode':'reported'})
    mc.update_chapter(ordinary,content='A separate corrected original.')
    plan=reconciliation_plan(mc,limit=1)
    assert plan['ready_count']==1 and plan['blocked_count']==3
    assert plan['ready'][0]['chapter_id']==ready
    assert plan['blocked'][0]['chapter_id']==missing
    whole=reconciliation_plan(mc,limit=10)
    blocked={r['chapter_id']:r for r in whole['blocked']}
    assert blocked[cycle]['blockers'][0]['status']=='cyclic'
    assert blocked[protected]['blockers'][0]['reason']=='protected_support'
    assert observed not in [r['chapter_id'] for r in whole['ready']+whole['blocked']]
    assert 'raw' not in json.dumps(whole)
