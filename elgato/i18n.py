"""Small, extensible catalog for the shell UI and CLI diagnostics."""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'assets/i18n.json').read_text())
SUPPORTED = ('en', 'de', 'fr', 'es')


def system_language():
    # Locale variables have precedence; an explicit C locale must not fall
    # through to a lower-priority translated LANG value.
    for value in (os.environ.get('LC_ALL'), os.environ.get('LC_MESSAGES'),
                  os.environ.get('LANGUAGE'), os.environ.get('LANG'), locale.getlocale()[0]):
        if not value:
            continue
        for candidate in value.split(':'):
            code = candidate.split('.', 1)[0].split('@', 1)[0].split('_', 1)[0].split('-', 1)[0].lower()
            if code in SUPPORTED:
                return code
            if code in ('c', 'posix'):
                return 'en'
    return 'en'


def language(config):
    selected = config.get('language', 'auto')
    return selected if selected in SUPPORTED else system_language()


def words(config):
    lang = language(config)
    english = CATALOG['en']
    return {key: CATALOG.get(lang, {}).get(key, value) for key, value in english.items()}


def tr(key, config):
    return words(config).get(key, key)


ERROR_KEYS = {
    'Ungültige Aktion': 'error_invalid_action',
    'Ungültige Seite oder Taste': 'error_invalid_key',
    'Stream Deck Abhängigkeiten fehlen. Bitte ./install.sh ausführen.': 'error_missing_deps',
    'Leuchte nicht registriert': 'error_light_missing',
    'Image missing or larger than 10 MB': 'error_image_missing',
    'Use a PNG, JPEG or WebP image': 'error_image_format',
    'Import the image before assigning it': 'error_image_import',
    'Invalid empty-key appearance': 'error_empty_style',
    'Invalid empty-key style': 'error_empty_style',
}


def error(message, config):
    key = ERROR_KEYS.get(message)
    return tr(key, config) if key else message
