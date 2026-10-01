"""Persistent Stream Deck HID worker. One process owns the USB device."""
from __future__ import annotations

from collections import deque
import fcntl
import os
import stat
import json
import logging
from pathlib import Path
import threading
import time

from . import core, safety, visuals
from .actions import ActionQueue

LOG = logging.getLogger(__name__)


def device_name(deck):
    try:
        product = Path('/sys/bus/usb/devices', deck.id().split(':', 1)[0], 'product')
        return product.read_text().strip() or deck.deck_type()
    except (OSError, ValueError):
        return deck.deck_type()
STATUS_FILE = core.CONFIG_DIR / 'status.json'
LOCK_FILE = core.CONFIG_DIR / 'daemon.lock'


def render(deck, action, colors, config, empty_spec=None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from StreamDeck.ImageHelpers import PILHelper

    width, height = deck.key_image_format()['size']
    theme = visuals.resolve_theme(config, colors)
    path = visuals.empty_image(empty_spec, theme) if empty_spec else visuals.action_image(action, theme)
    style = empty_spec.get('style', 'theme') if empty_spec else 'action'
    base_color = '#000000' if style == 'black' else colors['accent'] if style == 'accent' else colors['background']
    image = Image.new('RGB', (width, height), base_color)
    if path:
        try:
            with visuals.open_image(path) as source:
                fitted = ImageOps.fit(source.convert('RGB'), (width, height), method=Image.Resampling.LANCZOS)
                image.paste(fitted)
        except (OSError, ValueError):
            pass
    label = str((empty_spec or action).get('label', '')).strip()
    if label and action.get('show_label', True):
        draw = ImageDraw.Draw(image)
        size = max(10, min(17, height // 6))
        font = None
        for candidate in ('/usr/share/fonts/liberation/LiberationSans-Regular.ttf',
                          '/usr/share/fonts/TTF/DejaVuSans.ttf',
                          '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
            try:
                font = ImageFont.truetype(candidate, size)
                break
            except OSError:
                pass
        font = font or ImageFont.load_default(size=size)
        words = label.split()
        lines = []
        line = ''
        for word in words:
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=font) > width - 8 and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        lines = lines[:2]
        line_height = size + 2
        top = height - len(lines) * line_height - 6
        draw.rectangle((0, top - 3, width, height), fill=colors['background'])
        for offset, line in enumerate(lines):
            draw.text((width / 2, top + offset * line_height), line, font=font,
                      anchor='mt', fill=colors['foreground'])
    return PILHelper.to_native_key_format(deck, image)


class Worker:
    def __init__(self):
        self.decks = {}
        self.page = 0
        self.config = core.load_config()
        self.config_mtime = None
        self.theme_mtime = None
        self.theme_name_mtime = None
        self.background_signature = None
        self.errors = deque(maxlen=32)
        self.last_error_log = 0
        self.last_keys = {}
        self.actions = ActionQueue(self.record_error)
        self.lock = threading.RLock()

    def write_status(self):
        safety.private_dir(core.CONFIG_DIR)
        data = {'running': True, 'updated': time.time(), 'decks': [
            {'id': key, 'name': device_name(deck), 'keys': deck.key_count(),
             'rows': deck.key_layout()[0], 'columns': deck.key_layout()[1], 'dials': deck.dial_count()}
            for key, deck in self.decks.items()], 'page': self.page,
            'errors': list(self.errors)[-4:]}
        safety.atomic_write(STATUS_FILE, json.dumps(data).encode())

    def scan(self):
        from StreamDeck.DeviceManager import DeviceManager
        try:
            devices = DeviceManager().enumerate()
        except Exception as exc:
            self.record_error(f'USB: {exc}')
            return
        current = set()
        for deck in devices[:8]:
            try:
                ident = deck.id()
                current.add(ident)
                if ident in self.decks:
                    continue
                deck.open()
                deck.reset()
                if deck.is_visual():
                    deck.set_brightness(self.config.get('brightness', 70))
                deck.set_key_callback(self.on_key)
                if deck.dial_count():
                    deck.set_dial_callback(self.on_dial)
                self.decks[ident] = deck
                if deck.is_visual():
                    self.paint(deck)
            except Exception as exc:
                self.record_error(f'Stream Deck: {exc}')
                try:
                    deck.close()
                except Exception:
                    pass
        for ident in list(self.decks):
            if ident not in current:
                try:
                    self.decks.pop(ident).close()
                except Exception:
                    pass

    def paint(self, deck):
        if not deck.is_visual():
            return
        with self.lock:
            keys = self.config['pages'][self.page].get('keys', {})
            colors = core.palette()
            for index in range(deck.key_count()):
                action = keys.get(str(index), {})
                try:
                    if action:
                        deck.set_key_image(index, render(deck, action, colors, self.config))
                    else:
                        spec = visuals.empty_for(self.config, self.page, index)
                        deck.set_key_image(index, render(deck, {}, colors, self.config, spec))
                except Exception as exc:
                    self.record_error(f'Kachel {index + 1}: {exc}')
                    break

    def on_key(self, deck, key, pressed):
        if pressed:
            return
        with self.lock:
            action = self.config['pages'][self.page].get('keys', {}).get(str(key))
            if not action:
                return
            if action.get('type') == 'page':
                try:
                    target = int(action.get('value', 0))
                    if 0 <= target < len(self.config['pages']):
                        self.page = target
                        for item in self.decks.values():
                            self.paint(item)
                except (ValueError, TypeError):
                    pass
                return
        ident = (deck.id(), key)
        now = time.monotonic()
        if now - self.last_keys.get(ident, -1) < 0.15:
            return
        if len(self.last_keys) > 512:
            self.last_keys.clear()
        self.last_keys[ident] = now
        if not self.actions.submit(('key', *ident), lambda: self.execute(action)):
            self.record_error('Action queue is busy')

    def on_dial(self, deck, index, event, value):
        from StreamDeck.Devices.StreamDeck import DialEventType
        setting = self.config.get('dials', {}).get(str(index), {})
        mode = setting.get('mode', 'none')
        if mode == 'none':
            return
        if event == DialEventType.PUSH and value:
            return
        amount = int(value) if event == DialEventType.TURN else 0
        is_turn = event == DialEventType.TURN
        def apply(amount):
            if is_turn and not amount:
                return
            try:
                if mode == 'volume':
                    if not amount:
                        core.run_action({'type': 'volume', 'value': 'mute'})
                    else:
                        delta = f'{abs(amount) * 5}%' + ('+' if amount > 0 else '-')
                        core._launch(['wpctl', 'set-volume', '--limit', '1.5', '@DEFAULT_AUDIO_SINK@', delta],
                                     start_new_session=True)
                elif mode.startswith('light-'):
                    host = setting.get('host', '')
                    if not amount:
                        core.set_light(host, on=not bool(core.light_state(host).get('on')))
                    else:
                        field = 'brightness' if mode == 'light-brightness' else 'temperature'
                        current = core.light_state(host)
                        core.set_light(host, **{field: int(current.get(field, 50 if field == 'brightness' else 250)) + amount * 5})
            except Exception as exc:
                with self.lock:
                    self.record_error(str(exc))
        ident = ('dial', deck.id(), index, 'turn' if is_turn else 'push')
        if not self.actions.submit(ident, apply, max(-100, min(100, amount)), coalesce=is_turn):
            self.record_error('Action queue is busy')

    def record_error(self, message):
        with self.lock:
            message = ''.join(char if char >= ' ' else ' ' for char in str(message)[:240])
            self.errors.append(message)
            now = time.monotonic()
            if now - self.last_error_log >= 30:
                LOG.warning('Controller error: %s', message)
                self.last_error_log = now

    def execute(self, action):
        try:
            core.run_action(action, self.config)
        except Exception as exc:
            with self.lock:
                self.record_error(str(exc))

    def loop(self):
        safety.private_dir(core.CONFIG_DIR)
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'w') as lock:
            info = os.fstat(lock.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('Unsafe controller lock file')
            os.fchmod(lock.fileno(), 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            while True:
                with self.lock:
                    try:
                        mtime = core.CONFIG_FILE.stat().st_mtime_ns if core.CONFIG_FILE.exists() else 0
                        theme_mtime = core.THEME_FILE.stat().st_mtime_ns if core.THEME_FILE.exists() else 0
                        name_mtime = visuals.THEME_NAME_FILE.stat().st_mtime_ns if visuals.THEME_NAME_FILE.exists() else 0
                        background = visuals.WALLPAPER_FILE
                        background_signature = (str(background.resolve()), background.stat().st_mtime_ns) if background.exists() else None
                        if (mtime != self.config_mtime or theme_mtime != self.theme_mtime
                                or name_mtime != self.theme_name_mtime or background_signature != self.background_signature):
                            self.config = core.load_config()
                            self.config_mtime = mtime
                            self.theme_mtime = theme_mtime
                            self.theme_name_mtime = name_mtime
                            self.background_signature = background_signature
                            self.page = min(self.page, len(self.config['pages']) - 1)
                            for deck in self.decks.values():
                                if deck.is_visual():
                                    deck.set_brightness(self.config.get('brightness', 70))
                                    self.paint(deck)
                        self.scan()
                        self.write_status()
                    except Exception as exc:
                        self.record_error(str(exc))
                time.sleep(2)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        from StreamDeck.DeviceManager import DeviceManager  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise SystemExit(f'Abhängigkeit fehlt: {exc}. Bitte ./install.sh ausführen.')
    Worker().loop()
