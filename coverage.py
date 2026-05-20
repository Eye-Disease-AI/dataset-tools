import json, re, sys
from collections import defaultdict
from pathlib import Path
import pandas as pd

NOUNS = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')

def iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

def patient(stem):
    parts = stem.split('_')
    for p in (parts[0], parts[-1]):
        if p.lower() not in NOUNS and not iso(p): return p.upper()

root = Path(sys.argv[1])
cov = defaultdict(lambda: defaultdict(set))
date_covered = defaultdict(set)

for sub in ('kwestionariusze', 'zakresy'):
    for f in root.glob(f'formularze/*/{sub}/*.jpg'):
        d = iso(f.parts[-3])
        if d and (p := patient(f.stem)): cov[sub][d].add(p)
        if d: date_covered[sub].add(d)

for f in root.glob('notatki/*/*.[pP][nN][gG]'):
    d = iso(f.parts[-2])
    if d and (p := patient(f.stem)): cov['notatki'][d].add(p)
    if d: date_covered['notatki'].add(d)

for f in root.glob('kalendarze/*'):
    d = iso(f.stem)
    if d: date_covered['kalendarze'].add(d)
    if f.suffix == '.json' and d:
        for a in json.loads(f.read_text())['appointments']:
            cov['kalendarze'][d].add(a['patient'].upper())

for f in root.glob('zdjecia/*/*'):
    if f.is_file() and (d := iso(f.parts[-2])): date_covered['zdjecia'].add(d)

types = ['kwestionariusze', 'zakresy', 'notatki', 'kalendarze', 'zdjecia']
pairs = sorted({(p, d) for t in cov.values() for d, ps in t.items() for p in ps})

rows = []
for p, d in pairs:
    row = {'patient': p, 'date': d}
    for t in types:
        if p in cov[t][d]: row[t] = 'Y'
        elif cov[t][d]: row[t] = ''
        elif d in date_covered[t]: row[t] = '?'
        else: row[t] = ''
    rows.append(row)

df = pd.DataFrame(rows)
holes = df[df[types].eq('').any(axis=1)]
print(df.to_string(index=False))
with open("coverage.csv", "w") as f:
    df.to_csv(f, index=False)
print(f"\n{len(holes)} holes (- = missing, ? = type has the date but no patient attribution)")