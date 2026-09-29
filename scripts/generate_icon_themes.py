#!/usr/bin/env python3
"""Build original 144px icon packs. Requires rsvg-convert only at build time."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'assets/catalog.json').read_text())
THEMES = {
    'tokyo-night': dict(bg='#1a1b26', surface='#24283b', fg='#c0caf5', accent='#7aa2f7', second='#bb9af7', third='#f7768e'),
    'catppuccin': dict(bg='#1e1e2e', surface='#313244', fg='#cdd6f4', accent='#89b4fa', second='#f5c2e7', third='#94e2d5'),
    'gruvbox': dict(bg='#282828', surface='#3c3836', fg='#d4be98', accent='#d8a657', second='#a9b665', third='#e1875c'),
    'nord': dict(bg='#2e3440', surface='#3b4252', fg='#d8dee9', accent='#88c0d0', second='#81a1c1', third='#ebcb8b'),
}


def motif(theme, colors):
    a, b, c = colors['accent'], colors['second'], colors['third']
    if theme == 'tokyo-night':
        return f'''<circle cx="119" cy="30" r="24" fill="{c}" opacity=".18"/>
        <path d="M0 95 Q40 62 81 93 T144 85 V144 H0Z" fill="{b}" opacity=".19"/>
        <path d="M0 116 Q54 77 99 115 T144 100 V144 H0Z" fill="{a}" opacity=".13"/>
        <path d="M40 144 Q66 90 98 144" fill="none" stroke="{c}" stroke-width="2" opacity=".48"/>'''
    if theme == 'catppuccin':
        return f'''<path d="M-10 36 C28 -6 50 88 91 44 S143 29 160 48" fill="none" stroke="{b}" stroke-width="2" opacity=".28"/>
        <path d="M-10 44 C28 2 50 96 91 52 S143 37 160 56" fill="none" stroke="{a}" stroke-width="2" opacity=".30"/>
        <path d="M-10 52 C28 10 50 104 91 60 S143 45 160 64" fill="none" stroke="{c}" stroke-width="2" opacity=".26"/>
        <circle cx="18" cy="118" r="23" fill="{b}" opacity=".10"/>'''
    if theme == 'gruvbox':
        return f'''<path d="M-4 135 Q38 110 56 80 M150 126 Q109 110 91 76" fill="none" stroke="{b}" stroke-width="3" opacity=".25"/>
        <path d="M19 120 Q24 92 43 93 Q44 113 19 120 M29 104 Q12 82 3 90 Q6 109 29 104 M119 114 Q101 93 102 83 Q126 89 119 114 M108 97 Q124 76 140 80 Q135 98 108 97" fill="{b}" opacity=".16"/>
        <path d="M0 30 Q72 12 144 34" fill="none" stroke="{c}" opacity=".17"/>'''
    return f'''<circle cx="111" cy="34" r="22" fill="{c}" opacity=".16"/>
        <path d="M0 116 L35 66 L60 98 L91 47 L144 120 V144 H0Z" fill="{b}" opacity=".18"/>
        <path d="M0 130 L44 94 L71 116 L107 68 L144 112 V144 H0Z" fill="{a}" opacity=".13"/>
        <path d="M4 48 Q73 20 142 46" fill="none" stroke="{a}" stroke-width="1.5" opacity=".2"/>'''


def glyph(icon, color):
    # Generic symbols are deliberately original; app tiles use readable monograms.
    stroke = f'fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"'
    paths = {
        'files': '<path d="M32 52 H57 L68 63 H112 V103 H32Z"/>',
        'terminal': '<path d="M38 53 L57 72 L38 91 M67 93 H105"/>',
        'browser': '<circle cx="72" cy="73" r="36"/><path d="M36 73 H108 M72 37 C51 53 51 92 72 109 M72 37 C93 53 93 92 72 109"/>',
        'mail': '<rect x="36" y="51" width="72" height="49" rx="5"/><path d="M38 54 L72 80 L106 54"/>',
        'calendar': '<rect x="38" y="48" width="68" height="57" rx="5"/><path d="M38 64 H106 M55 42 V56 M89 42 V56 M55 79 H64 M76 79 H85 M55 91 H64"/>',
        'calculator': '<rect x="45" y="39" width="54" height="72" rx="7"/><path d="M54 56 H90 M56 70 H61 M72 70 H77 M87 70 H89 M56 84 H61 M72 84 H77 M87 84 H89"/>',
        'settings': '<circle cx="72" cy="74" r="25"/><circle cx="72" cy="74" r="8"/><path d="M72 39 V45 M72 103 V109 M37 74 H43 M101 74 H107 M47 49 L52 54 M92 94 L97 99 M97 49 L92 54 M52 94 L47 99"/>',
        'camera': '<rect x="34" y="54" width="76" height="51" rx="7"/><circle cx="72" cy="79" r="16"/><path d="M45 54 L53 44 H91 L99 54"/>',
        'music': '<path d="M65 96 V51 L96 44 V89 M65 96 C59 109 43 107 42 98 C41 88 56 87 65 91 M96 89 C90 102 74 100 73 91 C72 81 87 80 96 84"/>',
        'chat': '<path d="M37 48 H107 V94 H72 L51 109 V94 H37Z"/><path d="M53 68 H91 M53 80 H78"/>',
        'video': '<rect x="35" y="48" width="74" height="57" rx="7"/><path d="M64 59 L90 77 L64 95Z"/>',
        'games': '<path d="M45 59 H99 Q111 60 115 93 Q115 109 101 102 L88 92 H56 L43 102 Q29 109 29 93 Q33 60 45 59Z"/><path d="M51 72 V88 M43 80 H59 M88 78 H89 M98 84 H99"/>',
        'editor': '<path d="M43 105 L50 83 L91 42 L103 54 L62 95Z M47 97 L58 101"/>',
        'vlc': '<path d="M72 38 L105 104 H39Z M52 80 H92 M60 62 H84"/>',
        'light': '<circle cx="72" cy="68" r="22"/><path d="M62 90 V103 H82 V90 M64 111 H80 M72 35 V28 M36 68 H29 M115 68 H108 M45 41 L39 35 M99 41 L105 35"/>',
        'volume': '<path d="M38 64 H52 L72 48 V98 L52 82 H38Z M84 60 Q97 73 84 86 M95 49 Q116 73 95 98"/>',
        'media': '<circle cx="72" cy="73" r="37"/><path d="M63 54 L88 73 L63 92Z"/>',
        'workspace': '<rect x="36" y="45" width="72" height="56" rx="5"/><path d="M72 45 V101 M36 73 H108"/>',
        'script': '<path d="M56 43 H93 L107 58 V104 H56Z M93 43 V58 H107 M44 74 L34 82 L44 90 M74 73 L84 82 L74 91"/>',
        'command': '<rect x="33" y="47" width="78" height="55" rx="6"/><path d="M45 66 L56 75 L45 84 M66 85 H91"/>',
        'url': '<circle cx="72" cy="73" r="35"/><path d="M37 73 H107 M72 38 Q47 73 72 108 M72 38 Q97 73 72 108"/>',
        'page': '<path d="M39 47 H91 L105 61 V105 H39Z M91 47 V61 H105 M50 75 H92 M50 88 H82"/>',
        'multi': '<rect x="39" y="44" width="48" height="61" rx="5"/><path d="M53 62 H96 M53 77 H103 M53 92 H91"/>',
        'app': '<rect x="37" y="45" width="70" height="62" rx="14"/><path d="M72 59 V93 M55 76 H89"/>',
    }
    if icon == 'blank':
        return f'<circle cx="72" cy="72" r="22" fill="none" stroke="{color}" stroke-width="2" opacity=".38"/><circle cx="72" cy="72" r="3" fill="{color}" opacity=".45"/>'
    if icon in paths:
        return f'<g {stroke}>{paths[icon]}</g>'
    monograms = {
        'firefox':'FF', 'chromium':'CH', 'brave':'BR', 'obs':'OBS',
        'spotify':'SP', 'discord':'DC', 'steam':'ST', 'code':'VS',
        'gimp':'GI', 'blender':'3D', 'libreoffice':'LO', 'thunderbird':'TB',
    }
    label = escape(monograms.get(icon, icon[:2].upper()))
    size = 33 if len(label) > 2 else 42
    return f'<text x="72" y="85" text-anchor="middle" fill="{color}" font-family="DejaVu Sans" font-size="{size}" font-weight="700" letter-spacing="-2">{label}</text>'


def svg(theme, icon, colors):
    center = '' if icon in ('background', 'blank') else f'<circle cx="72" cy="72" r="43" fill="{colors["bg"]}" opacity=".55"/>'
    mark = '' if icon in ('background', 'blank') else glyph(icon, colors['fg'])
    source = f'''<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 144 144">
    <defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="{colors['surface']}"/><stop offset="1" stop-color="{colors['bg']}"/></linearGradient></defs>
    <rect width="144" height="144" rx="22" fill="url(#bg)"/>
    {motif(theme, colors)}
    <rect x="3" y="3" width="138" height="138" rx="20" fill="none" stroke="{colors['accent']}" stroke-opacity=".44" stroke-width="2"/>
    {center}
    {mark}
    </svg>'''
    return '\n'.join(line.rstrip() for line in source.splitlines())


def main():
    for theme, colors in THEMES.items():
        folder = ROOT / 'assets/icon-themes' / theme
        folder.mkdir(parents=True, exist_ok=True)
        for icon in ['background', *(item['id'] for item in CATALOG)]:
            source = svg(theme, icon, colors).encode()
            subprocess.run(['rsvg-convert', '--width', '144', '--height', '144', '-o', str(folder / f'{icon}.png')],
                           input=source, check=True)
    print(f'Generated {len(CATALOG)} icons in {len(THEMES)} themes')


if __name__ == '__main__':
    main()
