"""Local Prompter scripts, monitor discovery and native OmaGato IPC."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from . import core, safety

SCRIPTS_DIR = core.CONFIG_DIR / 'prompter-scripts'
COMMANDS = ('start', 'mirror', 'stop', 'play', 'pause', 'playPause', 'faster', 'slower',
            'nextChapter', 'prevChapter', 'flip')
DEFAULTS = {'screen': '', 'source': '', 'script': '', 'speed': 75, 'font_size': 42, 'flip': False}


def monitors():
    try:
        data = json.loads(subprocess.run(['hyprctl', 'monitors', '-j'], capture_output=True,
                                         text=True, timeout=3, check=True).stdout)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    result = []
    for item in data:
        if item.get('disabled') or not item.get('name'):
            continue
        make = str(item.get('make') or '').strip().upper()
        model = str(item.get('model') or '').strip().upper()
        is_prompter = make == 'IDI' and model.startswith('ELGATO PROM')
        result.append({'name': str(item['name']), 'description': str(item.get('description') or item['name']),
                       'prompter': is_prompter, 'width': item.get('width', 0), 'height': item.get('height', 0)})
    return result


def script_path(name):
    if not isinstance(name, str) or not re.fullmatch(r'[\w -]{1,64}', name, re.UNICODE) or name.strip() != name:
        raise ValueError('Ungültiger Skriptname')
    return SCRIPTS_DIR / (name + '.md')


def script_names():
    if not SCRIPTS_DIR.exists():
        return []
    return sorted((path.stem for path in SCRIPTS_DIR.glob('*.md') if path.is_file()), key=str.casefold)[:64]


def save_script(name, content):
    if len(content.encode('utf-8')) > 60 * 1024:
        raise ValueError('Skript ist zu groß')
    path = script_path(name)
    if not path.exists() and len(script_names()) >= 64:
        raise ValueError('Maximal 64 Skripte')
    safety.atomic_write(path, content.encode('utf-8'))
    config = core.load_config()
    config['prompter'] = {**DEFAULTS, **config.get('prompter', {}), 'script': name}
    core.save_config(config)


def delete_script(name):
    path = script_path(name)
    path.unlink(missing_ok=True)
    config = core.load_config()
    settings = {**DEFAULTS, **config.get('prompter', {})}
    if settings['script'] == name:
        settings['script'] = ''
    config['prompter'] = settings
    core.save_config(config)


def set_setting(field, value):
    config = core.load_config()
    settings = {**DEFAULTS, **config.get('prompter', {})}
    if field in ('screen', 'source'):
        if value and value not in {item['name'] for item in monitors()}:
            raise ValueError('Bildschirm nicht gefunden')
        settings[field] = value
    elif field == 'script':
        if value and not script_path(value).is_file():
            raise ValueError('Skript nicht gefunden')
        settings[field] = value
    elif field == 'speed':
        settings[field] = max(10, min(300, int(value)))
    elif field == 'font_size':
        settings[field] = max(20, min(90, int(value)))
    elif field == 'flip':
        settings[field] = value in ('true', '1')
    else:
        raise ValueError('Unbekannte Prompter Einstellung')
    config['prompter'] = settings
    core.save_config(config)


def state(config):
    settings = {**DEFAULTS, **config.get('prompter', {})}
    attached = monitors()
    detected = next((item for item in attached if item['prompter']), None)
    screen = settings['screen']
    if not screen and detected:
        screen = detected['name']
    source = settings['source']
    if not source or source == screen:
        source = next((item['name'] for item in attached if item['name'] != screen), '')
    script = settings['script']
    content = ''
    if script:
        try:
            content = safety.read_bytes(script_path(script), safety.SCRIPT_LIMIT).decode('utf-8')
        except (OSError, ValueError):
            pass
    return {'connected': detected is not None, 'name': detected['description'] if detected else '',
            'monitor': detected['name'] if detected else '', 'monitors': attached,
            'scripts': script_names(), 'screen': screen, 'source': source,
            'script': script,
            'text': content, 'speed': settings['speed'], 'font_size': settings['font_size'],
            'flip': settings['flip']}


def command(name):
    if name not in COMMANDS:
        raise ValueError('Unbekannte Prompter Aktion')
    subprocess.run(['omarchy-shell', 'omagato-prompter', name], timeout=5, check=True,
                   capture_output=True, text=True)
