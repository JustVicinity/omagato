"""Small JSON CLI called by the Quickshell panel."""
from __future__ import annotations

import argparse
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

from . import core, devices, i18n, openxlr, prompter, visuals
from .daemon import STATUS_FILE


def status():
    try:
        data = json.loads(STATUS_FILE.read_text())
        if time.time() - data.get('updated', 0) < 6:
            return data
    except (OSError, ValueError):
        pass
    return {'running': False, 'decks': [], 'page': 0, 'errors': []}


def parse_action(text):
    action = json.loads(text)
    if not isinstance(action, dict) or action.get('type') not in (
        'app', 'script', 'command', 'url', 'media', 'volume', 'workspace',
        'light', 'camera', 'prompter', 'page', 'multi'):
        raise ValueError('Ungültige Aktion')
    if len(json.dumps(action)) > 8192:
        raise ValueError('Aktion ist zu groß')
    return action


def main(argv=None):
    parser = argparse.ArgumentParser(description='OmaGato · Omarchy Elgato Controller')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('state', 'apps', 'discover-lights', 'cameras', 'daemon', 'start', 'prompter-state'):
        sub.add_parser(name)
    item = sub.add_parser('assign')
    item.add_argument('page', type=int)
    item.add_argument('key', type=int)
    item.add_argument('action')
    item = sub.add_parser('clear')
    item.add_argument('page', type=int)
    item.add_argument('key', type=int)
    item = sub.add_parser('set-language')
    item.add_argument('value', choices=['auto', *i18n.SUPPORTED])
    item = sub.add_parser('set-icon-theme')
    item.add_argument('value', choices=['auto', *visuals.THEMES])
    item = sub.add_parser('set-empty-default')
    item.add_argument('spec')
    item = sub.add_parser('set-empty')
    item.add_argument('page', type=int)
    item.add_argument('key', type=int)
    item.add_argument('spec')
    item = sub.add_parser('clear-empty')
    item.add_argument('page', type=int)
    item.add_argument('key', type=int)
    item = sub.add_parser('import-icon')
    item.add_argument('path')
    item = sub.add_parser('brightness')
    item.add_argument('value', type=int)
    item = sub.add_parser('set-dial')
    item.add_argument('index', type=int)
    item.add_argument('mode', choices=['none', 'volume', 'light-brightness', 'light-temperature'])
    item.add_argument('host', nargs='?', default='')
    item = sub.add_parser('new-page')
    item.add_argument('name')
    item = sub.add_parser('delete-page')
    item.add_argument('page', type=int)
    item = sub.add_parser('add-light')
    item.add_argument('host')
    item.add_argument('name', nargs='?')
    item = sub.add_parser('remove-light')
    item.add_argument('host')
    item = sub.add_parser('set-light')
    item.add_argument('host')
    item.add_argument('field', choices=['on', 'brightness', 'temperature'])
    item.add_argument('value')
    item = sub.add_parser('set-all-lights')
    item.add_argument('field', choices=['on', 'brightness', 'temperature'])
    item.add_argument('value')
    item = sub.add_parser('identify-light')
    item.add_argument('host')
    item = sub.add_parser('rename-light')
    item.add_argument('host')
    item.add_argument('name')
    item = sub.add_parser('camera-controls')
    item.add_argument('node')
    item = sub.add_parser('set-camera')
    item.add_argument('node')
    item.add_argument('control')
    item.add_argument('value')
    item = sub.add_parser('set-audio')
    item.add_argument('id')
    item.add_argument('field', choices=['volume', 'mute'])
    item.add_argument('value')
    item = sub.add_parser('xlr-set')
    item.add_argument('control')
    item.add_argument('value')
    item = sub.add_parser('xlr-mix')
    item.add_argument('mix')
    item.add_argument('field', choices=['mute', 'volume'])
    item.add_argument('value')
    item = sub.add_parser('prompter')
    item.add_argument('action', choices=prompter.COMMANDS)
    item = sub.add_parser('prompter-save')
    item.add_argument('name')
    item.add_argument('content')
    item = sub.add_parser('prompter-delete')
    item.add_argument('name')
    item = sub.add_parser('prompter-set')
    item.add_argument('field', choices=['screen', 'source', 'script', 'speed', 'font_size', 'flip'])
    item.add_argument('value')
    args = parser.parse_args(argv)
    try:
        if args.command == 'daemon':
            from .daemon import main as daemon_main
            return daemon_main()
        if args.command == 'start':
            if importlib.util.find_spec('StreamDeck') is None or importlib.util.find_spec('PIL') is None:
                raise ValueError('Stream Deck Abhängigkeiten fehlen. Bitte ./install.sh ausführen.')
            if not status()['running']:
                subprocess.Popen([sys.executable, '-m', 'elgato', 'daemon'],
                                 cwd=str(Path(__file__).resolve().parent.parent),
                                 stdout=subprocess.DEVNULL, stderr=(core.CONFIG_DIR / 'daemon.log').open('a') if core.CONFIG_DIR.exists() else subprocess.DEVNULL,
                                 start_new_session=True)
            result = {'ok': True}
        elif args.command == 'apps':
            result = core.installed_apps(i18n.language(core.load_config()))
        elif args.command == 'import-icon':
            result = {'path': visuals.import_icon(args.path)}
        elif args.command == 'discover-lights':
            result = core.discover_lights()
        elif args.command == 'cameras':
            result = core.cameras()
        elif args.command == 'camera-controls':
            result = core.camera_controls(args.node)
        elif args.command == 'set-camera':
            core.set_camera(args.node, args.control, args.value)
            result = {'ok': True}
        elif args.command == 'set-audio':
            core.set_audio(args.id, args.field, args.value)
            result = {'ok': True}
        elif args.command == 'xlr-set':
            openxlr.set_control(args.control, args.value)
            result = {'ok': True}
        elif args.command == 'xlr-mix':
            openxlr.set_mix(args.mix, args.field, args.value)
            result = {'ok': True}
        elif args.command == 'prompter':
            prompter.command(args.action)
            result = {'ok': True}
        elif args.command == 'prompter-state':
            result = prompter.state(core.load_config())
        elif args.command == 'prompter-save':
            prompter.save_script(args.name, args.content)
            result = {'ok': True}
        elif args.command == 'prompter-delete':
            prompter.delete_script(args.name)
            result = {'ok': True}
        elif args.command == 'prompter-set':
            prompter.set_setting(args.field, args.value)
            result = {'ok': True}
        elif args.command == 'set-light':
            if args.host not in [light['host'] for light in core.load_config()['lights']]:
                raise ValueError('Leuchte nicht registriert')
            value = int(args.value)
            result = core.set_light(args.host, **{args.field: value})
        elif args.command == 'set-all-lights':
            hosts = [light['host'] for light in core.load_config()['lights']]
            if not hosts:
                raise ValueError('Keine Leuchten registriert')
            value = int(args.value)
            for host in hosts:
                core.set_light(host, **{args.field: value})
            result = {'ok': True}
        elif args.command == 'identify-light':
            if args.host not in [light['host'] for light in core.load_config()['lights']]:
                raise ValueError('Leuchte nicht registriert')
            core.identify_light(args.host)
            result = {'ok': True}
        elif args.command == 'rename-light':
            config = core.load_config()
            light = next((item for item in config['lights'] if item['host'] == args.host), None)
            if light is None:
                raise ValueError('Leuchte nicht registriert')
            core.rename_light(args.host, args.name)
            light['name'] = args.name.strip()
            core.save_config(config)
            result = {'ok': True}
        elif args.command == 'state':
            config = core.load_config()
            lights = []
            for light in config['lights']:
                try:
                    lights.append({**light, 'state': core.light_state(light['host'])})
                except Exception as exc:
                    lights.append({**light, 'error': str(exc)})
            worker = status()
            if not worker['running'] and (importlib.util.find_spec('StreamDeck') is None or importlib.util.find_spec('PIL') is None):
                worker['errors'] = [i18n.tr('error_missing_deps', config)]
            cameras = core.cameras()
            audio = core.audio_nodes()
            xlr = openxlr.state()
            prompter_state = prompter.state(config)
            result = {'config': config, 'worker': worker, 'lights': lights,
                      'cameras': cameras, 'audio': audio, 'xlr': xlr,
                      'prompter': prompter_state,
                      'devices': devices.inventory(worker, cameras, lights, audio, prompter=prompter_state, xlr=xlr),
                      'theme': core.palette(),
                      'language': i18n.language(config), 'words': i18n.words(config),
                      'visuals': visuals.preview_data(config, max([15, *(deck['keys'] for deck in worker['decks'])]))}
        else:
            config = core.load_config()
            if args.command == 'assign':
                if not 0 <= args.page < len(config['pages']) or not 0 <= args.key < 64:
                    raise ValueError('Ungültige Seite oder Taste')
                config['pages'][args.page]['keys'][str(args.key)] = parse_action(args.action)
            elif args.command == 'clear':
                config['pages'][args.page]['keys'].pop(str(args.key), None)
            elif args.command == 'set-language':
                config['language'] = args.value
            elif args.command == 'set-icon-theme':
                config['icon_theme'] = args.value
            elif args.command == 'set-empty-default':
                config['empty_default'] = visuals.normalize_empty(json.loads(args.spec))
            elif args.command == 'set-empty':
                if not 0 <= args.page < len(config['pages']) or not 0 <= args.key < 64:
                    raise ValueError('Ungültige Seite oder Taste')
                config['pages'][args.page].setdefault('empty', {})[str(args.key)] = visuals.normalize_empty(json.loads(args.spec))
            elif args.command == 'clear-empty':
                if not 0 <= args.page < len(config['pages']) or not 0 <= args.key < 64:
                    raise ValueError('Ungültige Seite oder Taste')
                config['pages'][args.page].setdefault('empty', {}).pop(str(args.key), None)
            elif args.command == 'brightness':
                config['brightness'] = max(0, min(100, args.value))
            elif args.command == 'set-dial':
                if not 0 <= args.index < 8:
                    raise ValueError('Ungültiger Drehregler')
                if args.mode.startswith('light-') and args.host not in [light['host'] for light in config['lights']]:
                    raise ValueError('Leuchte nicht registriert')
                config.setdefault('dials', {})[str(args.index)] = {'mode': args.mode, 'host': args.host}
            elif args.command == 'new-page':
                if len(config['pages']) >= 16:
                    raise ValueError('Maximal 16 Seiten')
                config['pages'].append({'name': args.name[:40] or 'Seite', 'keys': {}})
            elif args.command == 'delete-page':
                if len(config['pages']) == 1 or args.page == 0:
                    raise ValueError('Startseite kann nicht gelöscht werden')
                del config['pages'][args.page]
                for page in config['pages']:
                    for key, action in list(page['keys'].items()):
                        if action.get('type') == 'page':
                            target = int(action.get('value', -1))
                            if target == args.page:
                                del page['keys'][key]
                            elif target > args.page:
                                action['value'] = str(target - 1)
            elif args.command == 'add-light':
                host = core.validate_light(args.host)
                core.light_state(host)
                if host not in [light['host'] for light in config['lights']]:
                    config['lights'].append({'host': host, 'name': args.name or host})
            elif args.command == 'remove-light':
                config['lights'] = [light for light in config['lights'] if light['host'] != args.host]
            core.save_config(config)
            result = {'ok': True, 'config': config}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        try:
            config = core.load_config()
        except (OSError, ValueError):
            config = core.default_config()
        print(json.dumps({'error': i18n.error(str(exc), config)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
