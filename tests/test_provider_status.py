"""Payment failures must retain source work and remain visibly actionable."""
# ruff: noqa: F811
import io
import json
import urllib.error

import pytest

from tests.test_portable_producer import setup  # noqa: F401
from provider_status import Alerts, ProviderProblem, classify
from portable_producer import process_once


@pytest.mark.parametrize('status,expected',[(402,'payment_required'),(401,'authentication_failed'),
    (403,'access_denied'),(429,'rate_limited'),(503,'service_unavailable')])
def test_http_failures_have_safe_actionable_categories(status, expected):
    error=urllib.error.HTTPError('https://private.invalid/token',status,'private secret',{},io.BytesIO(b'private response'))
    result=classify(error)
    assert result['code']==expected and result['action']
    assert 'private' not in json.dumps(result) and 'secret' not in json.dumps(result)


def test_quota_and_timeout_are_distinct_from_rate_limit():
    error=urllib.error.HTTPError('https://private.invalid',429,'private',{},
        io.BytesIO(b'{"error":{"code":"insufficient_quota","message":"private"}}'))
    assert classify(error)['code']=='quota_exhausted'
    assert classify(TimeoutError())['code']=='timeout'
    assert classify(urllib.error.URLError(TimeoutError()))['code']=='timeout'


@pytest.mark.parametrize('body',[b'[]',b'{"error":{"code":[]}}',b'{"error":null}'])
def test_malformed_provider_error_does_not_hide_the_http_failure(body):
    error=urllib.error.HTTPError('https://example.invalid',429,'error',{},io.BytesIO(body))
    assert classify(error)['code']=='rate_limited'


def test_payment_notice_is_durable_deduplicated_and_recovery_keeps_work(setup):
    memory,inbox,state,valid,binding,_,_=setup
    def no_credit(*args):
        raise ProviderProblem('deepseek','fixture-dispatch',{'code':'payment_required','http_status':402})
    first=process_once(memory,inbox,state,no_credit,binding)
    assert first['state']=='pending' and first['provider_problem']['code']=='payment_required'
    assert not (state/'index.json').exists()
    second=process_once(memory,inbox,state,no_credit,binding)
    assert second['alert_id']==first['alert_id']
    alerts=Alerts(inbox)
    status=alerts.status()
    assert not status['healthy'] and status['undelivered']==1 and len(status['alerts'])==1
    sent=[]
    def send(notice):
        sent.append(notice)
        assert notice['work_preserved'] is True
        return {'confirmed':True,'message_id':17,'destination_id':'fixture:human'}
    assert alerts.deliver(send)['undelivered']==0
    alerts.deliver(send)
    assert len(sent)==1  # Already acknowledged; do not spam on every invocation.
    assert not alerts.status()['healthy']  # Delivery is not a repaired provider.
    result=process_once(memory,inbox,state,valid,binding)
    assert result['state']=='complete'
    assert alerts.status()['healthy']
    assert process_once(memory,inbox,state,valid,binding)['state']=='idle'
    with memory.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM chapters').fetchone()[0]==1


def test_notification_failure_cannot_claim_delivery_or_hide_consolidation_failure(setup):
    inbox=setup[1]
    alerts=Alerts(inbox)
    alerts.report('fixture:consolidation','consolidation',ProviderProblem('deepseek','request',{'code':'service_unavailable'}))
    calls=[]
    def unavailable(notice):
        calls.append(notice)
        raise TimeoutError('No confirmed Telegram receipt')
    status=alerts.deliver(unavailable)
    assert not status['healthy'] and status['undelivered']==1
    assert status['alerts'][0]['delivery']=='uncertain'
    assert status['alerts'][0]['phase']=='consolidation'
    alerts.deliver(unavailable)
    assert len(calls)==1  # Unknown send outcome requires explicit reconciliation.


def test_launcher_delivery_receipt_is_required_in_actual_worker_path(setup):
    memory,inbox,state,_,binding,_,_=setup
    calls=[]
    def sender(notice):
        calls.append(notice)
        return {'confirmed':True,'message_id':42,'destination_id':'fixture:operator'}
    def no_credit(*args):
        raise ProviderProblem('deepseek','request',{'code':'payment_required','http_status':402})
    result=process_once(memory,inbox,state,no_credit,binding,notice_sender=sender)
    assert result['notification_delivery']=='delivered' and not result['notification_pending']
    assert calls[0]['code']=='payment_required'
    process_once(memory,inbox,state,no_credit,binding,notice_sender=sender)
    assert len(calls)==1
