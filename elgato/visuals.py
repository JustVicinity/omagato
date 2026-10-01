"""Icon packs, user images, and empty-key appearance."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from functools import lru_cache
import re
import subprocess
import tempfile
import sys
import warnings

from . import core, safety

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets' / 'icon-themes'
CATALOG = json.loads((ROOT / 'assets/catalog.json').read_text())
THEMES = ('tokyo-night', 'catppuccin', 'gruvbox', 'nord')
THEME_NAME_FILE = Path.home() / '.local/state/omarchy/current/theme.name'
WALLPAPER_FILE = Path.home() / '.local/state/omarchy/current/background'
CACHE_DIR = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'omagato' / 'icons'
DEFAULT_EMPTY = {'style': 'theme', 'icon': 'blank', 'label': ''}
IMAGE_LIMIT = 10 * 1024 * 1024
PIXEL_LIMIT = 16_000_000


def open_image(path):
    """Decode one bounded snapshot, checking dimensions before allocation."""
    return decode_image(safety.read_bytes(path, IMAGE_LIMIT, nofollow=False))


def decode_image(data):
    from PIL import Image, ImageOps
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise ValueError('Use a PNG, JPEG or WebP image')
                if image.width > 8192 or image.height > 8192 or image.width * image.height > PIXEL_LIMIT:
                    raise ValueError('Image dimensions are too large (maximum 16 megapixels)')
                return ImageOps.exif_transpose(image)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Image dimensions are too large') from exc


def resolve_theme(config, palette=None):
    selected = config.get('icon_theme', 'auto')
    if selected in THEMES:
        return selected
    try:
        name = THEME_NAME_FILE.read_text().casefold()
    except OSError:
        name = ''
    for theme in THEMES:
        if theme.replace('-', ' ') in name or theme in name:
            return theme
    if 'catppuccin' in name:
        return 'catppuccin'
    # Custom Omarchy themes select the closest bundled palette.
    colors = palette or core.palette()
    options = {'tokyo-night': '#7aa2f7', 'catppuccin': '#89b4fa',
               'gruvbox': '#d8a657', 'nord': '#88c0d0'}
    accent = colors['accent']
    def distance(value):
        try:
            return sum((int(accent[i:i + 2], 16) - int(value[i:i + 2], 16)) ** 2 for i in (1, 3, 5))
        except (ValueError, IndexError):
            return 0
    return min(options, key=lambda theme: distance(options[theme]))


def catalog_id_for_app(desktop_id, app_name=''):
    target = f'{desktop_id} {app_name}'.casefold()
    for entry in CATALOG:
        if any(word in target for word in entry['matches']):
            return entry['id']
    return 'app'


def catalog_id_for_action(action):
    kind = action.get('type', '')
    if kind == 'app':
        return catalog_id_for_app(str(action.get('value', '')), str(action.get('label', '')))
    if kind in ('camera', 'prompter'):
        return 'camera'
    return kind if kind in {item['id'] for item in CATALOG} else 'app'


def asset(theme, icon):
    if theme not in THEMES or icon not in ({item['id'] for item in CATALOG} | {'background'}):
        raise ValueError('Unknown icon theme or icon')
    return ASSETS / theme / f'{icon}.png'


def imported_icon(path):
    """Return a user icon path only when it points into our managed icon store."""
    try:
        candidate = Path(path).resolve(strict=True)
        store = (core.CONFIG_DIR / 'icons').resolve()
        if candidate.parent == store and candidate.suffix == '.png':
            return candidate
    except (OSError, ValueError, TypeError):
        pass
    return None


def import_icon(path):
    source = Path(path).expanduser()
    snapshot = safety.read_bytes(source, IMAGE_LIMIT, nofollow=False)
    with decode_image(snapshot) as image:
        image.thumbnail((512, 512))
        converted = image.convert('RGBA')
        store = core.CONFIG_DIR / 'icons'
        safety.private_dir(store)
        digest = hashlib.sha256(snapshot).hexdigest()[:20]
        target = store / f'{digest}.png'
        output = BytesIO()
        converted.save(output, 'PNG')
        safety.atomic_write(target, output.getvalue())
        return str(target)


def normalize_empty(spec):
    if not isinstance(spec, dict):
        raise ValueError('Invalid empty-key appearance')
    style = spec.get('style', 'theme')
    if style not in ('theme', 'wallpaper', 'black', 'accent', 'image'):
        raise ValueError('Invalid empty-key style')
    icon = spec.get('icon', 'blank')
    if icon not in {item['id'] for item in CATALOG}:
        icon = 'blank'
    label = str(spec.get('label', ''))[:40]
    image = str(spec.get('image', ''))
    if style == 'image' and not imported_icon(image):
        raise ValueError('Import the image before assigning it')
    return {'style': style, 'icon': icon, 'label': label, 'image': image if style == 'image' else ''}


def empty_for(config, page_index, key_index):
    page = config['pages'][page_index]
    override = page.get('empty', {}).get(str(key_index))
    return override if override is not None else config.get('empty_default', DEFAULT_EMPTY)


@lru_cache(maxsize=256)
def system_icon_path(name):
    if not name:
        return None
    path = Path(name)
    if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.svg'):
        return path
    if '/' in name:
        return None
    name = path.stem if path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.svg') else name
    roots = (Path.home() / '.local/share/icons', Path('/usr/share/icons/hicolor'),
             Path('/usr/share/pixmaps'), Path('/usr/share/icons'))
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for extension in ('.png', '.webp', '.jpg', '.svg'):
            for found in root.rglob(name + extension):
                if found.is_file():
                    size = re.search(r'(\d+)x\d+', str(found))
                    score = int(size.group(1)) if size else 64
                    if found.suffix == '.svg':
                        score = 256
                    candidates.append((score, found))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


@lru_cache(maxsize=256)
def desktop_icon(desktop_id):
    return next((app['icon'] for app in core.installed_apps() if app['id'] == desktop_id), '')


def app_source(action):
    names = (str(action.get('icon', '')), str(action.get('system_icon', '')),
             desktop_icon(str(action.get('value', ''))),
             catalog_id_for_app(str(action.get('value', '')), str(action.get('label', ''))))
    for name in names:
        source = system_icon_path(name)
        if source:
            return source
    return None


def styled_app_icon(action, theme):
    """Build a tile for any installed app, with a readable fallback monogram."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    source = app_source(action)
    background = asset(theme, 'background')
    label = str(action.get('label') or action.get('value') or 'App')
    identity = f'v2|{theme}|{label}|{source}|{source.stat().st_mtime_ns if source else 0}|{background.stat().st_mtime_ns}'
    target = CACHE_DIR / (hashlib.sha256(identity.encode()).hexdigest()[:32] + '.png')
    if target.is_file():
        return target
    with Image.open(background) as image:
        tile = image.convert('RGBA')
    logo = None
    if source:
        try:
            if source.suffix.lower() == '.svg':
                renderer = core.shutil_which('rsvg-convert')
                if not renderer:
                    raise ValueError('SVG renderer unavailable')
                svg_png = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('svg_worker.py')), renderer],
                                         input=safety.read_bytes(source, IMAGE_LIMIT, nofollow=False),
                                         check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5).stdout
                logo = decode_image(svg_png).convert('RGBA')
            else:
                with open_image(source) as image:
                    logo = image.convert('RGBA')
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    if logo:
        logo = ImageOps.contain(logo, (94, 94), method=Image.Resampling.LANCZOS)
        tile.alpha_composite(logo, ((144 - logo.width) // 2, (144 - logo.height) // 2))
    else:
        mark = ''.join(part[0] for part in re.split(r'[^\w]+', label) if part)[:2].upper() or 'A'
        draw = ImageDraw.Draw(tile)
        font = None
        for candidate in ('/usr/share/fonts/liberation/LiberationSans-Regular.ttf',
                          '/usr/share/fonts/TTF/DejaVuSans.ttf',
                          '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
            try:
                font = ImageFont.truetype(candidate, 52)
                break
            except OSError:
                pass
        font = font or ImageFont.load_default(size=52)
        draw.text((72, 76), mark, anchor='mm', font=font, fill='#ffffff', stroke_width=1)
    safety.private_dir(CACHE_DIR)
    fd, temporary = tempfile.mkstemp(prefix='.tile-', suffix='.png', dir=CACHE_DIR)
    os.close(fd)
    try:
        tile.save(temporary, 'PNG')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def action_image(action, theme, force_theme=False):
    if not force_theme and action.get('icon_theme') in THEMES:
        theme = action['icon_theme']
    icon = str(action.get('icon', ''))
    if icon.startswith('pack:'):
        try:
            return asset(theme, icon[5:])
        except ValueError:
            return None
    custom = imported_icon(icon)
    if custom:
        return custom
    if action.get('type') == 'app':
        return styled_app_icon(action, theme)
    try:
        return asset(theme, catalog_id_for_action(action))
    except ValueError:
        return None


def empty_image(spec, theme):
    style = spec.get('style', 'theme')
    if style == 'theme':
        icon = spec.get('icon', 'blank')
        return asset(theme, 'background' if icon == 'blank' else icon)
    if style == 'wallpaper':
        return WALLPAPER_FILE.resolve() if WALLPAPER_FILE.is_file() else asset(theme, 'background')
    if style == 'image':
        return imported_icon(spec.get('image', ''))
    return None


def preview_data(config, key_count=32):
    theme = resolve_theme(config)
    pages = []
    for page_index, page in enumerate(config['pages']):
        previews = {}
        for key_index in range(key_count):
            action = page.get('keys', {}).get(str(key_index))
            if action:
                path = action_image(action, theme)
                style = 'action'
            else:
                spec = empty_for(config, page_index, key_index)
                path = empty_image(spec, theme)
                style = spec.get('style', 'theme')
            previews[str(key_index)] = {'path': str(path) if path else '', 'style': style,
                'variants': {choice: str(action_image(action, choice, force_theme=True))
                             for choice in THEMES} if action and action.get('type') == 'app' else {}}
        pages.append(previews)
    return {'theme': theme, 'themes': list(THEMES), 'catalog': CATALOG, 'pages': pages}
