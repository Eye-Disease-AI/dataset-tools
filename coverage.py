import argparse, json, re
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
        if p.casefold() not in NOUNS and not iso(p): return p

ap = argparse.ArgumentParser()
ap.add_argument('data_root', type=Path)
ap.add_argument('--out', type=Path, default="coverage.csv")
args =  ap.parse_args()
root = args.data_root
cov = defaultdict(lambda: defaultdict(set))
date_covered = defaultdict(set)
display = {}

def add(typ, d, p):
    cov[typ][d].add(p.casefold())
    display.setdefault(p.casefold(), p)

for sub in ('kwestionariusze', 'zakresy'):
    for f in root.glob(f'formularze/*/{sub}/*.jpg'):
        d = iso(f.parts[-3])
        if d and (p := patient(f.stem)): add(sub, d, p)
        if d: date_covered[sub].add(d)

for f in root.glob('notatki/*/*.[pP][nN][gG]'):
    d = iso(f.parts[-2])
    if d and (p := patient(f.stem)): add('notatki', d, p)
    if d: date_covered['notatki'].add(d)

for f in root.glob('kalendarze/*'):
    d = iso(f.stem)
    if d: date_covered['kalendarze'].add(d)
    if f.suffix == '.json' and d:
        for a in json.loads(f.read_text())['appointments']:
            add('kalendarze', d, a['patient'])

for f in root.glob('zdjecia/*/*'):
    if f.is_file() and (d := iso(f.parts[-2])): date_covered['zdjecia'].add(d)

types = ['kwestionariusze', 'zakresy', 'notatki', 'kalendarze', 'zdjecia']
keys = sorted({(p, d) for t in cov.values() for d, ps in t.items() for p in ps})

rows = []
for p, d in keys:
    row = {'patient': display[p], 'date': d}
    for t in types:
        if p in cov[t][d]: row[t] = '+'
        elif cov[t][d]: row[t] = ''
        elif d in date_covered[t]: row[t] = '?'
        else: row[t] = ''
    rows.append(row)

df = pd.DataFrame(rows)
holes = df[df[types].eq('').any(axis=1)]
with open(args.out, "w") as f:
    df.to_csv(f, index=False)
print(df.to_string(index=False))
print(f"\n{len(holes)} holes (- = missing, ? = type has the date but no patient attribution)")