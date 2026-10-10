"""Bounded per-device settings; legacy settings remain the shared template."""
from copy import deepcopy
import hashlib
from . import safety

FIELDS = ('pages', 'brightness', 'dials', 'empty_default', 'app_pages')


def identity(deck):
    try:
        serial = deck.get_serial_number()
    except Exception:
        serial = ''
    # Do not expose hardware serial numbers in status or diagnostics.
    value = str(serial or deck.id())
    return 'deck-' + hashlib.sha256(value.encode()).hexdigest()[:24]


def validate_id(value):
    import re
    if not isinstance(value, str) or not re.fullmatch(r'deck-[a-f0-9]{24}', value):
        raise ValueError('Invalid device identity')
    return value


def effective(config, device=''):
    return {**config, **config.get('device_profiles', {}).get(device, {})}


def editable(config, device):
    if not device:
        return config
    validate_id(device)
    profiles = config.setdefault('device_profiles', {})
    if device not in profiles:
        if len(profiles) >= 8:
            raise ValueError('At most 8 device profiles')
        profiles[device] = {key: deepcopy(config[key]) for key in FIELDS if key in config}
    return effective(config, device)


def store(config, device, settings):
    if device:
        config['device_profiles'][device] = {key: settings[key] for key in FIELDS if key in settings}


def validate(config, validate_config):
    profiles = safety.object_value(config.get('device_profiles', {}))
    if len(profiles) > 8:
        raise ValueError('At most 8 device profiles')
    for device, settings in profiles.items():
        validate_id(device)
        safety.object_value(settings)
        if any(key not in FIELDS for key in settings):
            raise ValueError('Invalid device settings')
        merged = {**config, **settings}
        merged.pop('device_profiles', None)
        validate_config(merged)
    rules = safety.object_value(config.get('app_pages', {}))
    if len(rules) > 32:
        raise ValueError('At most 32 application rules')
    for app, page in rules.items():
        safety.text_value(app, 240)
        if not app or type(page) is not int or not 0 <= page < len(config['pages']):
            raise ValueError('Invalid application page rule')
