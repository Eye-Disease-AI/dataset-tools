from logging import Logger
import argparse, json, re
import sys
from collections import defaultdict
from pathlib import Path
import pandas as pd
from PIL import Image, ExifTags

DATETIME_ORIGINAL = next(k for k, v in ExifTags.TAGS.items() if v == 'DateTimeOriginal')
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.heic'}

NOUNS = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')
PATIENT_RE = re.compile(r'(\w+)-(\w+)')
TIME_RE = re.compile(r'(\d{2})-(\d{2})')

logger = Logger("coverage")

def iso(s):
    m = DATE.search(s)
    if not m:
        return None
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
parser.add_argument('--all', action='store_true')
args =  parser.parse_args()
root = args.data_root
ids_json = args.data_root / "patient_ids.json"
if not ids_json.exists():
    print(f'ERROR: {ids_json} not found. Run assign_ids.py first', file=sys.stderr)
    sys.exit(2)
ids = json.loads(ids_json.read_text())
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

def photo_time(stem):
    """Pull HH:MM from photo filename, ignoring the date portion."""
    stem_without_date = re.sub(r'\d{4}-\d{2}-\d{2}', '', stem)
    time_match = TIME_RE.search(stem_without_date)
    if not time_match:
        return None
    return f'{time_match.group(1)}:{time_match.group(2)}'

def matching_slot(date, hhmm):
    """Last visit slot on `date` whose start <= hhmm. None if photo is before all visits."""
    slots = ids.get(date, {})
    candidate_times = [t for t in slots if t <= hhmm]
    if not candidate_times:
        return None
    return max(candidate_times)

for f in root.glob('zdjecia/*/*'):
    if not f.is_file():
        logger.warning(f"Missing file: {f}")
        continue
    date = iso(f.parts[-2])
    if not date:
        logger.warning(f"File missing date in name: {f}")
        continue
    date_covered['zdjecia'].add(date)

    hhmm = photo_time(f.stem)
    if hhmm is None:
        logger.warning(f"Failed to extract date from file: {f}")
        continue

    slot_time = matching_slot(date, hhmm)
    if slot_time is None:
        logger.warning(f"Error in finding matching slot for time {hhmm} for file: {f}")
        continue

    if slot_time == '-':
        logger.info(f"No matching slot for file: {f}")
        continue

    for patient in ids[date][slot_time]:
        add_coverage('zdjecia', date, patient)

def exif_capture(path):
    """(date, hhmm) from EXIF DateTimeOriginal ('YYYY:MM:DD HH:MM:SS'). (None, None) on miss."""
    try:
        exif = Image.open(path)._getexif() or {}
    except Exception:
        return None, None
    raw = exif.get(DATETIME_ORIGINAL)
    if not raw or len(raw) < 16:
        return None, None
    return raw[:10].replace(':', '-'), raw[11:16]

for f in root.glob('smartfon/**/*'):
    if not f.is_file() or f.suffix.lower() not in IMG_EXTS:
        logger.warning(f"Error in finding matching slot for time {hhmm} for file: {f}")
        continue
    date, hhmm = exif_capture(f)
    if not date:
        logger.warning(f"Failed to extract date from file: {f}")
        continue
    date_covered['smartfon'].add(date)
    slot_time = matching_slot(date, hhmm)
    if slot_time is None or slot_time == '-':
        logger.info(f"No matching slot for file: {f}")
        continue
    for patient in ids[date][slot_time]:
        add_coverage('smartfon', date, patient)


types = ['kwestionariusze', 'zakresy', 'notatki', 'kalendarze', 'zdjecia', 'smartfon']
keys = sorted({(patient, date) for t in coverage.values() for date, ps in t.items() for patient in ps})

rows = []
for patient, date in keys:
    row = {'patient': display[patient], 'date': date}
    for type in types:
        if patient in coverage[type][date]: row[type] = '+'
        elif coverage[type][date]: row[type] = ''
        elif date in date_covered[type]: row[type] = '?'
        else: row[type] = ''
    if args.all:
        rows.append(row)
    elif not all(row[type] for type in types):
        rows.append(row) # only print rows with missing data


df = pd.DataFrame(rows)
holes = df[df[types].eq('').any(axis=1)]
df = df.sort_values('date')
with open(args.out, "w") as f:
    df.to_csv(f, index=False)
print(df.to_string(index=False))
print(f"\n{len(holes)} holes (' ' = missing, ? = type has the date but no patient attribution)")