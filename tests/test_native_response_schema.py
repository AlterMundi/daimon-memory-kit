import json

import pytest

from native_response_schema import decode, for_codex
from selection_navigation import response_schema


def test_navigation_contract_is_closed_at_every_object_and_keeps_variants():
    original = response_schema()
    encoded, wrapped = for_codex(original)
    assert wrapped and set(encoded['properties']) == {'result'}

    def check(schema):
        assert 'oneOf' not in schema and 'const' not in schema
        if schema.get('type') == 'object':
            assert schema['additionalProperties'] is False
            assert set(schema['required']) == set(schema['properties'])
            for child in schema['properties'].values():
                check(child)
        for child in schema.get('anyOf', []):
            check(child)
        if 'items' in schema:
            check(schema['items'])

    check(encoded)
    lookup = dict(outcome='lookup', requests=[
        dict(action='search', query='fixture', record_uid='', offset=0, expected_revision=0)])
    assert json.loads(decode(json.dumps({'result':lookup}), original, wrapped)) == lookup
    add = {'key':'one','operation':'add','title':'a','source_ids':['new'],
           'shelf':'episodes','expected_revision':None,'chapter_id':None,'engram_type':None}
    decision = {'outcome':'applied','reason':'a','records':[add],'links':[]}
    wire = {'result':decision}
    decoded = json.loads(decode(json.dumps(wire), original, wrapped))
    assert decoded['records'] == [{key:value for key,value in add.items() if value is not None}]
    add.update(operation='update',shelf=None)
    with pytest.raises(ValueError, match='outside'):
        decode(json.dumps(wire), original, wrapped)


def test_bounded_account_draft_has_the_closed_claim_shape_without_request_rewrite():
    from native_response_schema import decision_schema

    requested = {'type':'object','required':['claims']}
    internal = decision_schema(requested, 'consolidation')
    encoded, wrapped = for_codex(internal)
    assert not wrapped and encoded['properties']['claims']['items']['required'] == ['text', 'support']
    result = {'claims': [{'text':'Fictional claim','support':[1]}]}
    assert json.loads(decode(json.dumps(result), internal, wrapped)) == result
    assert requested == {'type':'object','required':['claims']}
