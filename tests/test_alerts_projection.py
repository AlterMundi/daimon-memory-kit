"""The receiving projection retains no private journal payload or raw error."""
import json
import sqlite3
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from provider_status import Alerts, ProviderProblem, safe_projection
from capture_inbox import Inbox


def test_safe_projection_is_bounded_and_preserves_source_delivery(tmp_path):
    inbox=Inbox(tmp_path/'capture.sqlite',{'subject':'fictional'})
    alerts=Alerts(inbox)
    for i in range(3):
        alerts.report('private-operation-'+str(i),'index',ProviderProblem('private-provider',str(i),{'code':'payment_required'}))
    first=safe_projection(inbox,limit=2)
    assert len(first['items'])==2 and first['next_cursor']
    last=safe_projection(inbox,after=first['next_cursor'],limit=2)
    assert len(last['items'])==1 and last['next_cursor'] is None
    encoded=json.dumps(first)
    assert 'private-operation' not in encoded and 'private-provider' not in encoded
    assert all(row['work_preserved'] for row in first['items'])
    assert all(row['delivery']=='pending' for row in alerts.status()['alerts'])
    alerts.resolve('private-operation-0')
    assert safe_projection(inbox)['items'][0]['processing_state']=='resolved'
    with sqlite3.connect(inbox.path) as con:
        assert con.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==0


def test_existing_embedding_incidents_project_as_index_without_rewriting_journal(tmp_path):
    inbox=Inbox(tmp_path/'capture.sqlite',{'subject':'fictional'})
    alerts=Alerts(inbox)
    alerts.report('selected-index','embedding',ProviderProblem('nvidia','fixture',{'code':'quota_exhausted'}))
    projected=safe_projection(inbox)['items'][0]
    assert projected['phase']=='index' and projected['problem_code']=='quota_exhausted'
    assert alerts.status()['alerts'][0]['phase']=='embedding'
