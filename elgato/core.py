"""Configuration, actions and discovery for the Omarchy Elgato plugin."""
from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import tomllib
from urllib.request import Request, urlopen

CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'omarchy-elgato'
CONFIG_FILE = CONFIG_DIR / 'config.json'
THEME_FILE = Path.home() / '.local/state/omarchy/current/theme/colors.toml'


def default_config():
    return {'version': 1, 'brightness': 70, 'pages': [{'name': 'Start', 'keys': {}}],
            'lights': [], 'dials': {}, 'language': 'auto', 'icon_theme': 'auto',
            'empty_default': {'style': 'theme', 'icon': 'blank', 'label': ''}}


def load_config():
    if not CONFIG_FILE.exists():
        return default_config()
    data = json.loads(CONFIG_FILE.read_text())
    if data.get('version') != 1 or not isinstance(data.get('pages'), list) or not data['pages']:
        raise ValueError('Ungültige Konfiguration')
    defaults = default_config()
    for key in ('lights', 'dials', 'language', 'icon_theme', 'empty_default'):
        data.setdefault(key, defaults[key])
    return data


def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.config-', dir=CONFIG_DIR)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, CONFIG_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def palette():
    base = {'background': '#1a1b26', 'foreground': '#c0caf5', 'accent': '#7aa2f7', 'muted': '#414868'}
    try:
        values = tomllib.loads(THEME_FILE.read_text())
        for key in base:
            value = values.get(key)
            if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                base[key] = value
    except (OSError, ValueError):
        pass
    return base


def installed_apps(language=None):
    roots = [Path.home() / '.local/share/applications']
    roots += [Path(root) / 'applications' for root in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if root]
    found = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*.desktop'):
            ident = path.relative_to(root).as_posix().replace('/', '-')
            if ident in found:
                continue
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read(path, encoding='utf-8')
                item = parser['Desktop Entry']
                if item.get('Type') != 'Application' or item.getboolean('Hidden', fallback=False) or item.getboolean('NoDisplay', fallback=False):
                    continue
                if not item.get('Exec') and not item.get('DBusActivatable') == 'true':
                    continue
                localized = item.get(f'Name[{language}]') if language else None
                found[ident] = {'id': ident, 'name': localized or item.get('Name', ident), 'icon': item.get('Icon', '')}
            except (OSError, configparser.Error, KeyError, ValueError):
                continue
    suggested = ('firefox', 'chromium', 'brave', 'files', 'nautilus', 'terminal', 'alacritty', 'kitty', 'obs studio', 'spotify')
    def rank(app):
        name = app['name'].casefold()
        return (next((index for index, word in enumerate(suggested) if name == word or name.startswith(word + ' ')), len(suggested)), name)
    return sorted(found.values(), key=rank)


def cameras():
    result = []
    for node in sorted(Path('/sys/class/video4linux').glob('video*')):
        try:
            name = (node / 'name').read_text().strip()
        except OSError:
            continue
        if any(term in name.casefold() for term in ('elgato', 'facecam', 'cam link', 'game capture', 'hd60', '4k x', '4k s')):
            result.append({'node': '/dev/' + node.name, 'name': name})
    return result


def audio_nodes():
    """Find Elgato audio endpoints exposed by PipeWire."""
    try:
        data = json.loads(subprocess.run(['pw-dump'], capture_output=True, text=True,
                                         timeout=4, check=True).stdout)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    result = []
    for item in data:
        if item.get('type') != 'PipeWire:Interface:Node':
            continue
        props = item.get('info', {}).get('props', {})
        if props.get('media.class') not in ('Audio/Source', 'Audio/Sink'):
            continue
        name = props.get('node.description') or props.get('node.name') or ''
        identity = ' '.join(str(props.get(key, '')) for key in
                            ('device.vendor.name', 'device.product.name', 'node.description', 'node.name')).casefold()
        if not any(term in identity for term in ('elgato', 'wave:1', 'wave:3', 'wave xlr', 'wave neo', 'xlr dock')):
            continue
        ident = item.get('id')
        if not isinstance(ident, int) or ident < 0:
            continue
        volume = 1.0
        muted = False
        try:
            output = subprocess.run(['wpctl', 'get-volume', str(ident)], capture_output=True,
                                    text=True, timeout=2, check=True).stdout
            match = re.search(r'Volume:\s*([\d.]+)', output)
            if match:
                volume = float(match.group(1))
            muted = '[MUTED]' in output
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        result.append({'id': ident, 'name': name, 'kind': 'input' if props['media.class'] == 'Audio/Source' else 'output',
                       'volume': volume, 'muted': muted})
    return result


def set_audio(ident, field, value):
    ident = int(ident)
    if ident not in {item['id'] for item in audio_nodes()}:
        raise ValueError('Elgato Audiogerät nicht gefunden')
    if field == 'volume':
        level = max(0, min(1.5, float(value)))
        command = ['wpctl', 'set-volume', str(ident), str(level)]
    elif field == 'mute':
        command = ['wpctl', 'set-mute', str(ident), '1' if int(value) else '0']
    else:
        raise ValueError('Unbekannter Audioregler')
    subprocess.run(command, timeout=3, check=True)


def camera_controls(node):
    if node not in [item['node'] for item in cameras()]:
        raise ValueError('Kamera nicht gefunden')
    proc = subprocess.run(['v4l2-ctl', '-d', node, '--list-ctrls-menus'],
                          capture_output=True, text=True, timeout=4, check=True)
    controls = []
    pattern = re.compile(r'^\s*([A-Za-z0-9_]+)\s+0x[0-9a-fA-F]+\s+\(([^)]+)\)\s*:\s*(.*)$')
    option = re.compile(r'^\s+(-?\d+):\s+(.+)$')
    for line in proc.stdout.splitlines():
        match = pattern.match(line)
        if match:
            name, kind, tail = match.groups()
            kind = kind.lower()
            fields = {key: int(value) for key, value in
                      re.findall(r'(min|max|step|default|value)=(-?\d+)', tail)}
            flags = re.search(r'flags=([^\s]+)', tail)
            disabled = any(flag in (flags.group(1).split(',') if flags else ())
                           for flag in ('inactive', 'grabbed', 'read-only', 'disabled'))
            controls.append({'id': name, 'type': kind, 'options': [],
                             'writable': not disabled and kind in
                             ('int', 'integer', 'int64', 'bool', 'boolean', 'menu', 'intmenu', 'button', 'bitmask'),
                             **fields})
        elif controls and (choice := option.match(line)) and controls[-1]['type'] in ('menu', 'intmenu'):
            controls[-1]['options'].append({'value': int(choice.group(1)), 'label': choice.group(2).strip()})
    return controls


def set_camera(node, control, value):
    allowed = {item['id']: item for item in camera_controls(node)}
    if control not in allowed:
        raise ValueError('Kameraregler nicht verfügbar')
    item = allowed[control]
    if not item['writable']:
        raise ValueError('Kameraregler ist nicht beschreibbar')
    value = int(value, 0) if str(value).lower().startswith('0x') else int(value)
    if item['type'] in ('bool', 'boolean') and value not in (0, 1):
        raise ValueError('Wert außerhalb des Bereichs')
    if item['type'] in ('menu', 'intmenu') and item['options'] and value not in {x['value'] for x in item['options']}:
        raise ValueError('Menüwert nicht verfügbar')
    if item['type'] not in ('button', 'bitmask') and {'min', 'max'} <= item.keys() and not item['min'] <= value <= item['max']:
        raise ValueError('Wert außerhalb des Bereichs')
    subprocess.run(['v4l2-ctl', '-d', node, '--set-ctrl', f'{control}={value}'], timeout=4, check=True)


def validate_light(host):
    # An IP or .local name only. Avoid using URL schemes and arbitrary ports.
    if not re.fullmatch(r'[a-zA-Z0-9.-]+', host) or host.startswith('-') or '..' in host:
        raise ValueError('Ungültige Licht-Adresse')
    return host


def light_request(host, method='GET', payload=None):
    host = validate_light(host)
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(f'http://{host}:9123/elgato/lights', data=data, method=method,
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def light_state(host):
    data = light_request(host)
    lights = data.get('lights') or []
    if not lights:
        raise ValueError('Keine Leuchte an dieser Adresse')
    return lights[0]


def light_info(host):
    host = validate_light(host)
    request = Request(f'http://{host}:9123/elgato/accessory-info',
                      headers={'Accept': 'application/json'})
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def rename_light(host, name):
    host = validate_light(host)
    name = str(name).strip()
    if not name or len(name) > 64:
        raise ValueError('Lichtname muss 1 bis 64 Zeichen lang sein')
    request = Request(f'http://{host}:9123/elgato/accessory-info',
                      data=json.dumps({'displayName': name}).encode(), method='PUT',
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=2) as response:
        response.read()


def identify_light(host):
    host = validate_light(host)
    request = Request(f'http://{host}:9123/elgato/identify', data=b'', method='POST')
    with urlopen(request, timeout=2) as response:
        response.read()


def set_light(host, *, on=None, brightness=None, temperature=None):
    current = light_state(host)
    if on is not None:
        current['on'] = int(bool(on))
    if brightness is not None:
        current['brightness'] = max(1, min(100, int(brightness)))
    if temperature is not None:
        current['temperature'] = max(143, min(344, int(temperature)))
    return light_request(host, 'PUT', {'numberOfLights': 1, 'lights': [current]})


def discover_lights():
    # avahi-browse output is escaped in the name fields; only consume the IP field.
    if not shutil_which('avahi-browse'):
        return []
    found = {}
    for service in ('_elg._tcp', '_elgato._tcp'):
        try:
            output = subprocess.run(['avahi-browse', '-rtp', service], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in output.splitlines():
            fields = line.split(';')
            if len(fields) >= 9 and fields[0] == '=' and re.fullmatch(r'(?:\d{1,3}\.){3}\d{1,3}', fields[7]):
                found[fields[7]] = {'host': fields[7], 'name': fields[3]}
    return list(found.values())


def shutil_which(name):
    from shutil import which
    return which(name)


def media_action(value):
    methods = {'play-pause': 'PlayPause', 'next': 'Next',
               'previous': 'Previous', 'stop': 'Stop'}
    if value not in methods:
        raise ValueError('Unbekannte Medienaktion')
    if shutil_which('playerctl'):
        subprocess.Popen(['playerctl', value], start_new_session=True)
        return
    if not shutil_which('busctl'):
        raise ValueError('Mediensteuerung benötigt playerctl oder busctl')
    listing = subprocess.run(['busctl', '--user', '--no-legend', 'list'],
                             capture_output=True, text=True, timeout=3, check=True)
    players = [line.split()[0] for line in listing.stdout.splitlines()
               if line.startswith('org.mpris.MediaPlayer2.')]
    if not players:
        raise ValueError('Kein Mediaplayer gefunden')
    chosen = players[0]
    for player in players:
        status = subprocess.run(['busctl', '--user', 'get-property', player,
                                 '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player',
                                 'PlaybackStatus'], capture_output=True, text=True, timeout=2)
        if status.returncode == 0 and '"Playing"' in status.stdout:
            chosen = player
            break
    subprocess.run(['busctl', '--user', 'call', chosen,
                    '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player',
                    methods[value]], capture_output=True, text=True, timeout=3, check=True)


def run_action(action, config=None):
    kind = action.get('type', '')
    value = action.get('value', '')
    if kind == 'app':
        if value not in {app['id'] for app in installed_apps()}:
            raise ValueError('App ist nicht installiert')
        subprocess.Popen(['gtk-launch', value], start_new_session=True)
    elif kind == 'script':
        path = Path(value).expanduser()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError('Script fehlt oder ist nicht ausführbar')
        subprocess.Popen([str(path)], start_new_session=True)
    elif kind == 'command':
        argv = shlex.split(value)
        if not argv:
            raise ValueError('Leerer Befehl')
        subprocess.Popen(argv, start_new_session=True)
    elif kind == 'url':
        if not value.startswith(('https://', 'http://')):
            raise ValueError('Nur HTTP(S)-Adressen sind erlaubt')
        subprocess.Popen(['xdg-open', value], start_new_session=True)
    elif kind == 'media':
        media_action(value)
    elif kind == 'volume':
        if value == 'mute':
            subprocess.Popen(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'], start_new_session=True)
        elif value in ('up', 'down'):
            subprocess.Popen(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '5%+' if value == 'up' else '5%-'], start_new_session=True)
        else:
            raise ValueError('Unbekannte Lautstärkeaktion')
    elif kind == 'workspace':
        number = int(value)
        if number < 1 or number > 20:
            raise ValueError('Ungültiger Workspace')
        subprocess.Popen(['hyprctl', 'dispatch', 'workspace', str(number)], start_new_session=True)
    elif kind == 'light':
        host = action.get('host', '')
        if value == 'toggle':
            set_light(host, on=not bool(light_state(host).get('on')))
        elif value in ('brighter', 'dimmer'):
            current = light_state(host)
            set_light(host, brightness=int(current.get('brightness', 50)) + (10 if value == 'brighter' else -10))
        elif value in ('warmer', 'cooler'):
            current = light_state(host)
            set_light(host, temperature=int(current.get('temperature', 250)) + (10 if value == 'warmer' else -10))
        else:
            raise ValueError('Unbekannte Lichtaktion')
    elif kind == 'camera':
        set_camera(action.get('node', ''), action.get('control', ''), value)
    elif kind == 'prompter':
        from . import prompter
        prompter.command(value)
    elif kind == 'multi':
        steps = action.get('steps', [])
        if not isinstance(steps, list) or len(steps) > 12:
            raise ValueError('Maximal 12 Aktionen pro Makro')
        for step in steps:
            if step.get('type') in ('multi', 'page'):
                raise ValueError('Verschachtelte Makros und Seitenwechsel sind nicht erlaubt')
            if step.get('type') == 'command':
                argv = shlex.split(step.get('value', ''))
                if not argv:
                    raise ValueError('Leerer Befehl im Makro')
                subprocess.run(argv, check=True, timeout=60)
            elif step.get('type') == 'script':
                path = Path(step.get('value', '')).expanduser()
                if not path.is_file() or not os.access(path, os.X_OK):
                    raise ValueError('Script im Makro fehlt oder ist nicht ausführbar')
                subprocess.run([str(path)], check=True, timeout=60)
            else:
                run_action(step, config)
    else:
        raise ValueError('Unbekannter Aktionstyp')
