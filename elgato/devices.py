"""Elgato product inventory from OS interfaces, with explicit capability levels."""
from __future__ import annotations

from pathlib import Path


# Current device families from Elgato's downloads page. Names describe products,
# while capability states below describe only what OmaGato can actually control.
FAMILIES = (
    ('deck', 'Stream Deck', ('Stream Deck Mini', 'Stream Deck', 'Stream Deck MK.2',
                            'Stream Deck XL', 'Stream Deck Neo', 'Stream Deck +',
                            'Stream Deck + XL', 'Stream Deck + Lever', 'Stream Deck Pedal', 'Stream Deck Studio',
                            'Galleon 100 SD')),
    ('light', 'Lighting', ('Key Light Neo', 'Key Light', 'Key Light Air',
                          'Key Light Air MK.2', 'Key Light Mini', 'Ring Light',
                          'Light Strip', 'Light Strip Pro')),
    ('camera', 'Camera & Prompter', ('Facecam', 'Facecam MK.2', 'Facecam Neo',
                                    'Facecam Pro', 'Facecam 4K', 'Cam Link',
                                    'Cam Link 4K', 'Prompter', 'Prompter XL')),
    ('audio', 'Audio', ('Wave:1', 'Wave:3', 'Wave:3 MK.2', 'Wave Neo',
                       'Wave XLR', 'Wave XLR MK.2', 'Wave XLR Pro',
                       'XLR Dock', 'XLR Dock MK.2')),
    ('capture', 'Capture', ('Game Capture Neo', '4K X', '4K S', 'HD60 S+',
                            'HD60 X', '4K60 Pro', 'Video Capture')),
)


def usb_devices(root=Path('/sys/bus/usb/devices')):
    """Read vendor/product without requiring libusb access or root."""
    found = []
    for node in root.glob('*'):
        try:
            if (node / 'idVendor').read_text().strip().lower() != '0fd9':
                continue
            name = (node / 'product').read_text().strip()
            found.append({'name': name or 'Elgato USB',
                          'id': (node / 'idProduct').read_text().strip().lower(),
                          'path': node.name})
        except OSError:
            continue
    return found


def family_for(name):
    name = name.casefold()
    if 'stream deck' in name or 'galleon' in name:
        return 'deck'
    if any(part in name for part in ('key light', 'ring light', 'light strip')):
        return 'light'
    if any(part in name for part in ('facecam', 'cam link', 'prompter')):
        return 'camera'
    if any(part in name for part in ('wave', 'xlr dock')):
        return 'audio'
    if any(part in name for part in ('capture', 'hd60', '4k x', '4k s', '4k60')):
        return 'capture'
    return 'other'


def inventory(worker, cameras, lights, audio=(), usb=None, prompter=None, xlr=None):
    """Merge USB, driver and network sightings; report control honestly."""
    usb = usb_devices() if usb is None else usb
    seen = {}

    def add(family, name, key, level, detail=''):
        if key not in seen or (seen[key]['level'] == 'detected' and level != 'detected'):
            seen[key] = {'family': family, 'name': name, 'level': level,
                         'detail': detail, 'connected': True}

    for item in usb:
        name = item['name']
        family = family_for(name)
        add(family, name, 'name:' + name.casefold(), 'detected', 'USB ' + item['id'])

    for deck in worker.get('decks', []):
        add('deck', deck['name'], 'name:' + deck['name'].casefold(), 'control',
            str(deck['keys']) + ' keys' + (', ' + str(deck['dials']) + ' dials' if deck.get('dials') else ''))
    for camera in cameras:
        family = family_for(camera['name'])
        add('capture' if family == 'capture' else 'camera', camera['name'],
            'name:' + camera['name'].casefold(), 'control', camera['node'])
    for node in audio:
        add('audio', node['name'], 'name:' + node['name'].casefold(), 'control', node['kind'])
    if xlr and xlr.get('connected') and xlr.get('device'):
        name = xlr['device']
        add('audio', name, 'name:' + name.casefold(), 'control', 'OpenXLR')
    if prompter and prompter.get('connected'):
        add('camera', 'Prompter', 'name:prompter', 'control', prompter.get('name', ''))
    for light in lights:
        add('light', light['name'], 'light:' + light['host'],
            'detected' if light.get('error') else 'control', light['host'])

    result = []
    for family, label, variants in FAMILIES:
        devices = [item for item in seen.values() if item['family'] == family]
        connected_names = {item['name'].casefold() for item in devices}
        result.append({'id': family, 'label': label, 'connected': bool(devices),
                       'devices': devices, 'variants': [name for name in variants
                                                      if name.casefold() not in connected_names]})
    others = [item for item in seen.values() if item['family'] == 'other']
    if others:
        result.append({'id': 'other', 'label': 'Other Elgato', 'connected': True,
                       'devices': others, 'variants': []})
    return result
