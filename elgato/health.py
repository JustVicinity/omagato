"""Read-only setup checks and a diagnostic summary safe to share."""
import importlib.metadata
import hashlib
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def runtime_revision():
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'elgato').glob('*.py')) + [ROOT / 'requirements.txt']:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def check(worker, usb):
    dependencies = []
    for name, version in re.findall(r'^([A-Za-z0-9_-]+)==([^\s\\]+)',
                                   (ROOT / 'requirements.txt').read_text(), re.M):
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = ''
        dependencies.append({'name': name, 'ready': installed == version})
    missing = [item['name'] for item in dependencies if not item['ready']]
    access = []
    for item in usb:
        if not any(name in item['name'].casefold() for name in ('stream deck', 'galleon')):
            continue
        node = Path('/sys/bus/usb/devices') / item.get('path', '')
        try:
            bus = int((node / 'busnum').read_text())
            address = int((node / 'devnum').read_text())
            access.append(os.access(f'/dev/bus/usb/{bus:03}/{address:03}', os.R_OK | os.W_OK))
        except (OSError, ValueError):
            pass
    return {'dependencies': dependencies, 'needs_install': bool(missing),
            'needs_restart': bool(worker.get('running')) and worker.get('revision') != runtime_revision(),
            'usb_access': all(access) if access else None,
            'running': bool(worker.get('running')),
            'tools': {name: bool(shutil.which(name)) for name in
                      ('v4l2-ctl', 'wpctl', 'pw-dump', 'avahi-browse', 'hyprctl', 'rsvg-convert')}}


def diagnostics(worker, usb):
    health = check(worker, usb)
    return {'schema': 1, 'setup': health,
            'usb_products': [{'name': item['name'], 'product_id': item['id']} for item in usb],
            'decks': [{'name': item['name'], 'keys': item['keys'], 'dials': item.get('dials', 0)}
                      for item in worker.get('decks', [])]}
