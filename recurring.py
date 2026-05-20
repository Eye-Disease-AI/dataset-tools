import json, re, sys
from collections import defaultdict
from pathlib import Path

NOUNS = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')

def iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

root = Path(sys.argv[1])
visits = defaultdict(lambda: defaultdict(list))   # pid -> date -> [times or None]
display = {}

def add(p, d, t=None):
    k = p.casefold()
    visits[k][d].append(t)
    display.setdefault(k, p)

for f in list(root.glob('formularze/*/*/*.jpg')) + list(root.glob('notatki/*/*.[pP][nN][gG]')):
    d = next((iso(p) for p in f.parts if iso(p)), None)
    parts = f.stem.split('_')
    c = next((p for p in (parts[0], parts[-1]) if p.casefold() not in NOUNS and not iso(p)), None)
    if d and c: add(c, d)

for kj in root.glob('kalendarze/*.json'):
    d = iso(kj.stem)
    if not d: continue
    for a in json.loads(kj.read_text())['appointments']:
        add(a['patient'], d, a['time'])

def visit_count(dates):
    """Per date: max(1 if any filename-only evidence, count of kalendarz times)."""
    n = 0
    for ts in dates.values():
        times = [t for t in ts if t]
        n += max(1, len(times))
    return n

rows = []
for k, dates in visits.items():
    n = visit_count(dates)
    if n > 1:
        details = []
        for d in sorted(dates):
            times = sorted(t for t in dates[d] if t)
            details.append(f'{d}' + (f' ({", ".join(times)})' if len(times) > 1 else ''))
        rows.append((display[k], n, details))

rows.sort(key=lambda r: (-r[1], r[0].casefold()))
for p, n, details in rows:
    print(f'{p:12} {n:3}  {"; ".join(details)}')
print(f'\n{len(rows)} patients with more than one visit')