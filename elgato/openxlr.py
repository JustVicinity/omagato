"""Optional local OpenXLR client for Elgato Wave and XLR controls.

OpenXLR remains an independently installed daemon. Its private session token
never enters the Quickshell state, process arguments, or diagnostic output.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

from . import network, safety

BOOLEAN = {
    'mute': 'mute', 'lowCut': 'lowCut', 'expander': 'expander',
    'voiceTune': 'voiceTune', 'phantom': 'phantom', 'clipGuard': 'clipGuard',
    'compressor': 'compressor', 'lowImpedance': 'lowImpedance',
    'auxLevelLock': 'auxInput', 'outHp1': 'outputRouting',
    'outHp2': 'outputRouting', 'outUsbAux': 'outputRouting',
    'outLineOut': 'outputRouting',
}
NUMERIC = {
    'gain': ('gain', 'gainDb', 0, 80, 1),
    'voiceTuneStrength': ('voiceTune', 'voiceTuneStrength', 0, 100, 1),
    'hpVolumeDb': ('hpVolume', 'hpVolumeDb', -60, 0, 1),
    'hp2VolumeDb': ('hpVolume', 'hp2VolumeDb', -60, 0, 1),
    'crossfade': ('crossfade', 'crossfade', 0, 200, 1),
    'auxLevelDb': ('auxInput', 'auxLevelDb', -60, 0, 1),
}


def token_path():
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if runtime:
        return Path(runtime) / 'openxlr' / 'token'
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'openxlr' / 'token'


def _call(path, command=None):
    try:
        token = safety.read_bytes(token_path(), 514, secret=True).decode('ascii').strip()
    except UnicodeError:
        raise ValueError('OpenXLR token is invalid') from None
    if not re.fullmatch(r'[!-~]{1,512}', token):
        raise ValueError('OpenXLR token is invalid')
    if path not in ('/state', '/commands'):
        raise ValueError('Invalid OpenXLR path')
    data = network.request('127.0.0.1', 37890, '/api/v1' + path,
                           method='GET' if command is None else 'POST', payload=command,
                           headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                           limit=network.OPENXLR_LIMIT, mode='loopback')
    payload = safety.object_value(safety.parse_json(data))
    # Even an endpoint echoing credentials cannot place the token in UI/errors.
    pending = [payload]
    while pending:
        item = pending.pop()
        for key in list(item) if isinstance(item, dict) else range(len(item)):
            value = item[key]
            if isinstance(value, str):
                item[key] = value.replace(token, '[redacted]')
            elif isinstance(value, (dict, list)):
                pending.append(value)
    messages = payload.get('messages', [])
    if not isinstance(messages, list) or len(messages) > 128 or any(not isinstance(m, dict) for m in messages):
        raise ValueError('Invalid OpenXLR messages')
    for message in messages:
        for field in ('message', 'error'):
            if field in message:
                safety.text_value(message[field])
    if payload.get('ok') is False:
        raise ValueError('OpenXLR rejected the command')
    return payload


def raw_state():
    payload = _call('/state')
    if payload.get('type') == 'state':
        return payload
    return next((item for item in payload.get('messages', [])
                 if isinstance(item, dict) and item.get('type') == 'state'), {})


def state():
    """Return a stable unavailable state for invalid/unavailable local responses."""
    try:
        return _state(raw_state())
    except (OSError, ValueError, RecursionError):
        return {'available': False, 'connected': False, 'controls': [], 'mixes': []}


def _state(raw):
    safety.object_value(raw)
    caps = safety.object_value({} if raw.get('capabilities') is None else raw['capabilities'])
    values = safety.object_value({} if raw.get('state') is None else raw['state'])
    for key, value in caps.items():
        if key in ('xlrInputs', 'hpOutputs'):
            if type(value) is not int or not 0 <= value <= 8:
                raise ValueError('Invalid OpenXLR capability count')
        elif key in set(BOOLEAN.values()) | {spec[0] for spec in NUMERIC.values()}:
            if type(value) is not bool:
                raise ValueError('Invalid OpenXLR capability')
    for control in BOOLEAN:
        for key in (control, control + '2'):
            if key in values and type(values[key]) is not bool:
                raise ValueError('Invalid OpenXLR switch')
    for control, (_, key, low, high, _) in NUMERIC.items():
        for field in (key, key.replace('Db', '2Db') if control == 'gain' else key + '2'):
            if field in values:
                safety.number_value(values[field], low, high)
    mixer = safety.object_value({} if raw.get('mixer') is None else raw['mixer'])
    mixes = mixer.get('mixes', [])
    if not isinstance(mixes, list) or len(mixes) > 64:
        raise ValueError('Invalid OpenXLR mixer')
    for mix in mixes:
        safety.object_value(mix)
        for field in ('id', 'name', 'kind'):
            safety.text_value(mix.get(field, ''))
        safety.number_value(mix.get('volume', 0), 0, 1.5)
        if type(mix.get('muted', False)) is not bool:
            raise ValueError('Invalid OpenXLR mute state')
    device = safety.object_value({} if raw.get('device') is None else raw['device'])
    safety.text_value(device.get('model', ''))
    if type(raw.get('connected', False)) is not bool:
        raise ValueError('Invalid OpenXLR connection state')
    for field in ('activeProfile', 'warning'):
        safety.text_value(raw.get(field) or '')
    profiles = raw.get('profiles') or []
    if not isinstance(profiles, list) or len(profiles) > 64:
        raise ValueError('Invalid OpenXLR profiles')
    for profile in profiles:
        safety.text_value(profile)
    controls = []
    for control, capability in BOOLEAN.items():
        if caps.get(capability):
            controls.append({'id': control, 'label': control, 'type': 'bool',
                             'value': bool(values.get(control, False))})
            if control in {'mute', 'lowCut', 'expander', 'voiceTune', 'phantom', 'clipGuard', 'compressor'} and caps.get('xlrInputs', 1) > 1:
                controls.append({'id': control + '2', 'label': control + ' 2',
                                 'type': 'bool', 'value': bool(values.get(control + '2', False))})
    for control, (capability, value_key, minimum, maximum, step) in NUMERIC.items():
        if not caps.get(capability) or (control == 'hp2VolumeDb' and caps.get('hpOutputs', 1) < 2):
            continue
        controls.append({'id': control, 'label': control, 'type': 'number',
                         'value': values.get(value_key, minimum), 'min': minimum,
                         'max': maximum, 'step': step})
        if control in {'gain', 'voiceTuneStrength'} and caps.get('xlrInputs', 1) > 1:
            controls.append({'id': control + '2', 'label': control + ' 2',
                             'type': 'number', 'value': values.get(value_key.replace('Db', '2Db') if control == 'gain' else value_key + '2', minimum),
                             'min': minimum, 'max': maximum, 'step': step})
    mixer = {} if raw.get('mixer') is None else raw['mixer']
    return {'available': True, 'connected': bool(raw.get('connected')),
            'device': ({} if raw.get('device') is None else raw['device']).get('model', ''),
            'controls': controls, 'mixes': [{k: mix.get(k) for k in ('id', 'name', 'kind', 'volume', 'muted')}
                                       for mix in mixer.get('mixes', []) if isinstance(mix, dict)],
            'profiles': raw.get('profiles') or [],
            'activeProfile': raw.get('activeProfile') or '',
            'warning': raw.get('warning') or ''}


def set_control(control, value):
    current = state()
    if not current['connected']:
        raise ValueError('No OpenXLR device connected')
    spec = next((item for item in current['controls'] if item['id'] == control), None)
    if spec is None:
        raise ValueError('Control is unavailable on this device')
    if spec['type'] == 'bool':
        if value not in ('0', '1', 'true', 'false'):
            raise ValueError('Expected a boolean value')
        parsed = value in ('1', 'true')
    else:
        parsed = float(value)
        if not spec['min'] <= parsed <= spec['max']:
            raise ValueError('Control value is outside its range')
    _call('/commands', {'cmd': 'set', 'control': control, 'value': parsed})


def set_mix(mix_id, field, value):
    current = state()
    mix = next((item for item in current['mixes'] if item['id'] == mix_id), None)
    if mix is None:
        raise ValueError('Unknown OpenXLR mix')
    if field == 'mute':
        if value not in ('0', '1'):
            raise ValueError('Expected 0 or 1')
        command = {'cmd': 'setMixMuted', 'mix': mix_id, 'value': value == '1'}
    elif field == 'volume':
        level = float(value)
        if not 0 <= level <= (1.5 if mix['kind'] == 'monitor' else 1):
            raise ValueError('Mix volume is outside its range')
        command = {'cmd': 'setMixVolume', 'mix': mix_id, 'value': level}
    else:
        raise ValueError('Unknown mix field')
    _call('/commands', command)
