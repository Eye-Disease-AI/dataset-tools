import argparse, json, re
from collections import defaultdict
from pathlib import Path

NOUNS = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')

def date_format_iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

def canonise_patient_initials(p):
    if '-' in p: return p.upper()
    if len(p) == 2: return f'{p[0].upper()}-{p[1].upper()}'
    return p

PID_RE = re.compile(r'p\d+')

def patient(stem, nouns):
    parts = stem.split('_')
    for p in (parts[0], parts[-1], parts[-2] if len(parts) > 1 else ''):
        if p and p.casefold() not in nouns and not date_format_iso(p) and not PID_RE.fullmatch(p): return canonise_patient_initials(p)

ap = argparse.ArgumentParser()
ap.add_argument('data_root', type=Path)
ap.add_argument('--json', type=Path, default=Path('patient_ids.json'))
args = ap.parse_args()

mapping = json.loads(args.json.read_text()) if args.json.exists() else {}

pairs = set()
for f in args.data_root.glob('formularze/*/*/*.jpg'):
    d = date_format_iso(f.parts[-3])
    p = patient(f.stem, NOUNS)
    if d and p: pairs.add((p, d))
for f in args.data_root.glob('notatki/*/*.[pP][nN][gG]'):
    d = date_format_iso(f.parts[-2])
    p = patient(f.stem, NOUNS)
    if d and p: pairs.add((p, d))
for kj in args.data_root.glob('kalendarze/*.json'):
    d = date_format_iso(kj.stem)
    if not d: continue
    for a in json.loads(kj.read_text())['appointments']:
        pairs.add((canonise_patient_initials(a['patient']), d))

existing_ids = {v for sub in mapping.values() for v in sub.values() if v}
next_n = max((int(i[1:]) for i in existing_ids if re.fullmatch(r'p\d+', i)), default=0) + 1

new_assigned = []
new_unresolved = []
for p, d in sorted(pairs):
    sub = mapping.setdefault(p, {})
    if d in sub: continue
    if sub:
        sub[d] = None
        new_unresolved.append((p, d))
    else:
        pid = f'p{next_n:04d}'
        next_n += 1
        sub[d] = pid
        new_assigned.append((p, d, pid))

mapping = {p: dict(sorted(sub.items())) for p, sub in sorted(mapping.items())}
args.json.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + '\n')

print(f'{len(new_assigned)} newly assigned, {len(new_unresolved)} need review')
for p, d, pid in new_assigned: print(f'  + {p} {d} -> {pid}')
for p, d in new_unresolved: print(f'  ? {p} {d}  (initials seen before, please set ID)')
unresolved_total = sum(1 for sub in mapping.values() for v in sub.values() if v is None)
if unresolved_total: print(f'\n{unresolved_total} total unresolved entries in {args.json}')