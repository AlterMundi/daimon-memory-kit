"""Adapt DMK's checked decisions to Codex Responses strict structured output."""
from __future__ import annotations

import json


def decision_schema(schema, phase):
    if phase == 'consolidation' and schema == {'type': 'object', 'required': ['claims']}:
        # The old consolidation prompt already requires precisely these fields.
        # Keep its persisted request identity while closing its provider schema.
        return {'type': 'object', 'required': ['claims'], 'properties': {'claims': {
            'type': 'array', 'items': {'type': 'object', 'required': ['text', 'support'],
                                     'properties': {'text': {'type': 'string'},
                                                    'support': {'type': 'array', 'items': {'type': 'integer'}}}},
        }}}
    return schema


def alternatives(schema):
    choices = schema.get('oneOf') or schema.get('anyOf') or []
    if 'properties' not in schema:
        return choices
    base = {key: value for key, value in schema.items() if key not in ('oneOf', 'anyOf')}
    return [
        dict(base, properties={**base['properties'], **item.get('properties', {})},
             required=[*base.get('required', []), *item.get('required', [])])
        for item in choices
    ]


def strict(schema):
    choices = alternatives(schema)
    if choices:
        return {'anyOf': [strict(item) for item in choices]}

    result = {key: schema[key] for key in (
        'type', 'description', 'minimum', 'maximum', 'minItems', 'maxItems',
        'minLength', 'maxLength', 'pattern', 'enum',
    ) if key in schema}
    if 'const' in schema:
        result['enum'] = [schema['const']]
    if 'enum' in result and 'type' not in result:
        if not all(isinstance(item, str) for item in result['enum']):
            raise ValueError('an untyped native enum must contain strings')
        result['type'] = 'string'
    if schema.get('type') == 'object' or 'properties' in schema:
        required = set(schema.get('required', []))
        declared = schema.get('properties', {})
        if required - declared.keys():
            raise ValueError('required decision fields have no declaration')
        properties = {}
        for key, field in declared.items():
            projected = strict(field)
            field_type = projected.get('type', [])
            admits_null = 'null' in ([field_type] if isinstance(field_type, str) else field_type)
            if key not in required and not admits_null:
                projected = {'anyOf': [projected, {'type': 'null'}]}
            properties[key] = projected
        result.update(type='object', properties=properties, required=list(properties),
                      additionalProperties=False)
    if 'items' in schema:
        result['items'] = strict(schema['items'])
    if not result or result.get('type') is None:
        raise ValueError('unsupported native response schema field')
    return result


def for_codex(schema):
    projected = strict(schema)
    wrapped = projected.get('type') != 'object'
    if wrapped:
        projected = {
            'type': 'object', 'properties': {'result': projected},
            'required': ['result'], 'additionalProperties': False,
        }
    return projected, wrapped


def normalize(value, schema):
    choices = alternatives(schema)
    if choices:
        candidates = []
        for choice in choices:
            try:
                candidate = normalize(value, choice)
            except ValueError:
                continue
            if candidate not in candidates:
                candidates.append(candidate)
        if len(candidates) != 1:
            raise ValueError('native result is outside the selected decision branches')
        return candidates[0]
    if ('const' in schema and value != schema['const']
            or 'enum' in schema and value not in schema['enum']):
        raise ValueError('native result differs from its decision discriminator')
    if 'properties' in schema:
        properties = schema['properties']
        required = set(schema.get('required', []))
        if not isinstance(value, dict) or set(value) - properties.keys() or required - value.keys():
            raise ValueError('native result is missing decision fields')
        return {
            key: normalize(item, properties[key]) for key, item in value.items()
            if item is not None or key in required
        }
    if 'items' in schema:
        if not isinstance(value, list):
            raise ValueError('native decision array required')
        return [normalize(item, schema['items']) for item in value]
    if value is None:
        declared = schema.get('type', [])
        if 'null' not in ([declared] if isinstance(declared, str) else declared):
            raise ValueError('native result left a required decision field null')
    return value


def decode(content, original, wrapped):
    value = json.loads(content)
    if wrapped:
        if not isinstance(value, dict) or set(value) != {'result'}:
            raise ValueError('native response wrapper differs')
        value = value['result']
    return json.dumps(normalize(value, original), ensure_ascii=False, separators=(',', ':'))
