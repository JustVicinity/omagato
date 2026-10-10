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

from . import core, safety, visuals, profiles, health
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
        self.device_pages = {}
        self.device_ids = {}
        self.focused_app = None
        self.revision = health.runtime_revision()
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
        data = {'running': True, 'revision': self.revision, 'updated': time.time(), 'decks': [
            {'id': key, 'name': device_name(deck), 'keys': deck.key_count(),
             'rows': deck.key_layout()[0], 'columns': deck.key_layout()[1], 'dials': deck.dial_count(), 'profile': self.device_ids[key],
             'page': self.device_pages.get(key, 0), 'touch': bool(deck.is_touch())}
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
                self.device_ids[ident] = profiles.identity(deck)
                settings = self.settings(deck)
                self.device_pages.setdefault(ident, 0)
                if deck.is_visual():
                    deck.set_brightness(self.settings(deck).get('brightness', 70))
                deck.set_key_callback(self.on_key)
                if deck.dial_count():
                    deck.set_dial_callback(self.on_dial)
                if deck.is_touch():
                    deck.set_touchscreen_callback(self.on_touch)
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
                    self.device_ids.pop(ident, None)
                    self.device_pages.pop(ident, None)
                except Exception:
                    pass

    def settings(self, deck):
        return profiles.effective(self.config, self.device_ids.get(deck.id(), ''))

    def paint(self, deck):
        if not deck.is_visual():
            return
        with self.lock:
            settings = self.settings(deck)
            page = min(self.device_pages.get(deck.id(), 0), len(settings['pages']) - 1)
            self.device_pages[deck.id()] = page
            keys = settings['pages'][page].get('keys', {})
            colors = core.palette()
            for index in range(deck.key_count()):
                action = keys.get(str(index), {})
                try:
                    if action:
                        deck.set_key_image(index, render(deck, action, colors, settings))
                    else:
                        spec = visuals.empty_for(settings, page, index)
                        deck.set_key_image(index, render(deck, {}, colors, settings, spec))
                except Exception as exc:
                    self.record_error(f'Kachel {index + 1}: {exc}')
                    break
            if deck.is_touch():
                try:
                    self.paint_touch(deck, settings, page, colors)
                except Exception as exc:
                    self.record_error(f'Touch strip: {exc}')

    def paint_touch(self, deck, settings, page, colors):
        from PIL import Image, ImageDraw, ImageFont
        from StreamDeck.ImageHelpers import PILHelper
        width, height = deck.touchscreen_image_format()['size']
        count = max(1, deck.dial_count())
        image = Image.new('RGB', (width, height), colors['background'])
        draw = ImageDraw.Draw(image)
        theme = visuals.resolve_theme(settings, colors)
        for index in range(count):
            left, right = index * width // count, (index + 1) * width // count
            action = (settings['pages'][page].get('touch', {}).get(str(index))
                      or settings['pages'][page].get('touch_long', {}).get(str(index), {}))
            path = visuals.action_image(action, theme) if action else visuals.empty_image(settings.get('empty_default', visuals.DEFAULT_EMPTY), theme)
            if path:
                try:
                    with visuals.open_image(path) as source:
                        size = min(height, right - left)
                        image.paste(source.convert('RGB').resize((size, size)), (left + (right - left - size) // 2, 0))
                except (OSError, ValueError):
                    pass
            label = action.get('label', '')
            if label and action.get('show_label', True):
                draw.rectangle((left, height - 22, right, height), fill=colors['background'])
                draw.text(((left + right) // 2, height - 20), str(label)[:24],
                          font=ImageFont.load_default(size=14), anchor='mt', fill=colors['foreground'])
            draw.line((left, 0, left, height), fill=colors['accent'])
        deck.set_touchscreen_image(PILHelper.to_native_touchscreen_format(deck, image))

    def on_touch(self, deck, event, value):
        from StreamDeck.Devices.StreamDeck import TouchscreenEventType
        with self.lock:
            settings = self.settings(deck)
            page = min(self.device_pages.get(deck.id(), 0), len(settings['pages']) - 1)
            if event == TouchscreenEventType.DRAG:
                delta = value.get('x_out', 0) - value.get('x', 0)
                if abs(delta) >= 40:
                    self.device_pages[deck.id()] = (page + (1 if delta < 0 else -1)) % len(settings['pages'])
                    self.paint(deck)
                return
            width = deck.touchscreen_image_format()['size'][0]
            count = max(1, deck.dial_count())
            index = max(0, min(count - 1, int(value.get('x', 0)) * count // width))
            surface = 'touch_long' if event == TouchscreenEventType.LONG else 'touch'
            action = settings['pages'][page].get(surface, {}).get(str(index))
            if action and action.get('type') == 'page':
                try:
                    target = int(action.get('value', 0))
                except (TypeError, ValueError):
                    return
                if 0 <= target < len(settings['pages']):
                    self.device_pages[deck.id()] = target
                    self.paint(deck)
                return
            if action and not self.actions.submit(('touch', deck.id(), index, surface), lambda: self.execute(action, settings)):
                self.record_error('Action queue is busy')

    def on_key(self, deck, key, pressed):
        if pressed:
            return
        with self.lock:
            settings = self.settings(deck)
            page = min(self.device_pages.get(deck.id(), 0), len(settings['pages']) - 1)
            action = settings['pages'][page].get('keys', {}).get(str(key))
            if not action:
                return
            if action.get('type') == 'page':
                try:
                    target = int(action.get('value', 0))
                    if 0 <= target < len(settings['pages']):
                        self.device_pages[deck.id()] = target
                        self.paint(deck)
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
        if not self.actions.submit(('key', *ident), lambda: self.execute(action, settings)):
            self.record_error('Action queue is busy')

    def on_dial(self, deck, index, event, value):
        from StreamDeck.Devices.StreamDeck import DialEventType
        setting = self.settings(deck).get('dials', {}).get(str(index), {})
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

    def follow_app(self):
        if not any(self.settings(deck).get('app_pages') for deck in self.decks.values()):
            return
        import subprocess
        try:
            result = subprocess.run(['hyprctl', 'activewindow', '-j'], capture_output=True,
                                    text=True, timeout=1, check=True)
            if len(result.stdout) > 65536:
                return
            app = json.loads(result.stdout).get('class', '')
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        if app == self.focused_app:
            return
        self.focused_app = app
        for deck in self.decks.values():
            rules = self.settings(deck).get('app_pages', {})
            if not rules:
                continue
            target = rules.get(app, 0)
            self.device_pages[deck.id()] = target
            self.paint(deck)

    def record_error(self, message):
        with self.lock:
            message = ''.join(char if char >= ' ' else ' ' for char in str(message)[:240])
            self.errors.append(message)
            now = time.monotonic()
            if now - self.last_error_log >= 30:
                LOG.warning('Controller error: %s', message)
                self.last_error_log = now

    def execute(self, action, settings=None):
        try:
            core.run_action(action, settings or self.config)
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
                            self.focused_app = None
                            self.config_mtime = mtime
                            self.theme_mtime = theme_mtime
                            self.theme_name_mtime = name_mtime
                            self.background_signature = background_signature
                            self.page = min(self.page, len(self.config['pages']) - 1)
                            for deck in self.decks.values():
                                if deck.is_visual():
                                    deck.set_brightness(self.settings(deck).get('brightness', 70))
                                    self.paint(deck)
                        self.scan()
                        self.follow_app()
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
