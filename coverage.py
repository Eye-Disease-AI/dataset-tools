import argparse, json, re
from collections import defaultdict
from pathlib import Path
import pandas as pd

NOUNS = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')
PATIENT_RE = re.compile(r'(\w+)-(\w+)')
def iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

def get_patient(filename):
    parts = filename.split('_')
    for p in parts:
        if p.casefold() not in NOUNS and not iso(p) and PATIENT_RE.match(p) is not None:
            return p

parser = argparse.ArgumentParser()
parser.add_argument('data_root', type=Path)
parser.add_argument('--out', type=Path, default="coverage.csv")
args =  parser.parse_args()
root = args.data_root
coverage = defaultdict(lambda: defaultdict(set))
date_covered = defaultdict(set)
display = {}

def add_coverage(type, date, patient):
    coverage[type][date].add(patient.casefold())
    display.setdefault(patient.casefold(), patient)

# Formularze
for sub in ('kwestionariusze', 'zakresy'):
    for f in root.glob(f'formularze/*/{sub}/*.jpg'):
        date = iso(f.parts[-3])
        if date and (patient := get_patient(f.stem)):
            add_coverage(sub, date, patient)
        if date: date_covered[sub].add(date)

# Notatki
for f in root.glob('notatki/*/*.[pP][nN][gG]'):
    date = iso(f.parts[-2])
    if date and (patient := get_patient(f.stem)): add_coverage('notatki', date, patient)
    if date: date_covered['notatki'].add(date)

# Kalendarze
for f in root.glob('kalendarze/*'):
    date = iso(f.stem)
    if date: date_covered['kalendarze'].add(date)
    if f.suffix == '.json' and date:
        for appointment in json.loads(f.read_text())['appointments']:
            add_coverage('kalendarze', date, appointment['patient'])

# Zdjecia
for f in root.glob('zdjecia/*/*'):
    if f.is_file() and (date := iso(f.parts[-2])): date_covered['zdjecia'].add(date)


types = ['kwestionariusze', 'zakresy', 'notatki', 'kalendarze', 'zdjecia']
keys = sorted({(patient, date) for t in coverage.values() for date, ps in t.items() for patient in ps})

rows = []
for patient, date in keys:
    row = {'patient': display[patient], 'date': date}
    for type in types:
        if patient in coverage[type][date]: row[type] = '+'
        elif coverage[type][date]: row[type] = ''
        elif date in date_covered[type]: row[type] = '?'
        else: row[type] = ''
    rows.append(row)

df = pd.DataFrame(rows)
holes = df[df[types].eq('').any(axis=1)]
df = df.sort_values('date')
with open(args.out, "w") as f:
    df.to_csv(f, index=False)
print(df.to_string(index=False))
print(f"\n{len(holes)} holes (' ' = missing, ? = type has the date but no patient attribution)")