"""Optional local OpenXLR client for Elgato Wave and XLR controls.

OpenXLR remains an independently installed daemon. Its private session token
never enters the Quickshell state, process arguments, or diagnostic output.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

BASE = 'http://127.0.0.1:37890/api/v1'
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
    token = token_path().read_text(encoding='utf-8').strip()
    if not token or len(token) > 512:
        raise ValueError('OpenXLR token is invalid')
    body = None if command is None else json.dumps(command, separators=(',', ':')).encode('utf-8')
    headers = {'Authorization': 'Bearer ' + token}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = request.Request(BASE + path, data=body, headers=headers,
                          method='GET' if body is None else 'POST')
    try:
        with request.urlopen(req, timeout=2) as response:
            data = response.read(1024 * 1024 + 1)
    except (error.URLError, TimeoutError) as exc:
        raise ValueError('OpenXLR is unavailable') from exc
    if len(data) > 1024 * 1024:
        raise ValueError('OpenXLR response is too large')
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError('Invalid OpenXLR response')
    if payload.get('ok') is False:
        messages = payload.get('messages') or []
        detail = next((m.get('message') or m.get('error') for m in messages
                       if isinstance(m, dict) and (m.get('message') or m.get('error'))), '')
        raise ValueError(str(detail)[:240] or 'OpenXLR rejected the command')
    return payload


def raw_state():
    payload = _call('/state')
    if payload.get('type') == 'state':
        return payload
    return next((item for item in payload.get('messages', [])
                 if isinstance(item, dict) and item.get('type') == 'state'), {})


def state():
    """Return UI-safe, capability-filtered controls and mixer data."""
    try:
        raw = raw_state()
    except (OSError, ValueError, json.JSONDecodeError):
        return {'available': False, 'connected': False, 'controls': [], 'mixes': []}
    caps = raw.get('capabilities') or {}
    values = raw.get('state') or {}
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
    mixer = raw.get('mixer') or {}
    return {'available': True, 'connected': bool(raw.get('connected')),
            'device': (raw.get('device') or {}).get('model', ''),
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
