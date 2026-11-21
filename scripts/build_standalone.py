#!/usr/bin/env python3
"""Build a self-contained HTML for double-click use on Windows and other systems."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / 'index.html').read_text(encoding='utf-8')
css = (ROOT / 'assets/styles.css').read_text(encoding='utf-8')
# Google Fonts are optional and blocked in some offline settings.
css = css.replace("@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap');", '')
html = html.replace('  <link rel="stylesheet" href="assets/styles.css" />', '  <style>\n' + css + '\n  </style>')
for filename in ['seed.js', 'official-data.js', 'app.js']:
    html = html.replace(f'  <script src="assets/{filename}" defer></script>', '')
scripts = '\n'.join('<script>\n' + (ROOT/'assets'/f).read_text(encoding='utf-8').replace('</script', '<\\/script') + '\n</script>' for f in ['seed.js','official-data.js','app.js'])
html = html.replace('</body>', scripts + '\n</body>')
target = ROOT.parent / 'ECONINTEL_Open_In_Browser.html'
target.write_text(html, encoding='utf-8')
print('Standalone:', target, 'bytes:', target.stat().st_size)
