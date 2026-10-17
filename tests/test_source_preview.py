"""Readable navigation preserves attribution; it does not certify truth."""
import json

from source_preview import excerpt


def envelope(role, text):
    return role+'; source fixture:7; received 2030-01-02 through fixture:desk:\n'+json.dumps(text)


def test_quote_offsets_and_attribution_survive_encoded_source():
    text='Background. '*90+'Jo proposed a brace. Delivery failed, despite our first claim.'
    raw=envelope('Human report', '<environment_context>fixture</environment_context>')
    raw+='\n\n'+envelope('assistant_statement',text)
    quote=excerpt(raw,'brace delivery')
    assert quote['quote']==text[quote['quotation_offset']:quote['quotation_offset']+len(quote['quote'])]
    assert 'Delivery failed' in quote['quote'] and quote['omitted_before']
    assert quote['header'].startswith('assistant_statement;')
    assert quote['navigation_only'] and len(quote['quote'])<=500


def test_unknown_mixed_and_tool_only_sources_are_not_interpreted():
    raw=envelope('Human report','Jo was uncertain about the brace.')
    assert excerpt(raw+'\nCorrection outside envelope.','brace') is None
    assert excerpt('Plain authored account.','account') is None
    assert excerpt(envelope('tool_response','{"delivered":false}'),'delivered') is None
    assert excerpt(envelope('harness_instruction_context','private setup'),'setup') is None


def test_no_match_does_not_invent_a_quote_or_speaker():
    result=excerpt(envelope('Human report','Jo might remember.'),'absent')
    assert result['quote']=='Jo might remember.'
    assert 'Human report;' in result['header']
