import argparse, json, re
from collections import defaultdict
from pathlib import Path

NOUNS = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')

def iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

def canon(p):
    if '-' in p: return p.upper()
    if len(p) == 2: return f'{p[0].upper()}-{p[1].upper()}'
    return p

PID_RE = re.compile(r'p\d+')

def patient(stem, nouns):
    parts = stem.split('_')
    for p in (parts[0], parts[-1], parts[-2] if len(parts) > 1 else ''):
        if p and p.casefold() not in nouns and not iso(p) and not PID_RE.fullmatch(p): return canon(p)

ap = argparse.ArgumentParser()
ap.add_argument('data_root', type=Path)
ap.add_argument('--json', type=Path, default=Path('patient_ids.json'))
args = ap.parse_args()

mapping = json.loads(args.json.read_text()) if args.json.exists() else {}

kalendarze = {}
for kj in args.data_root.glob('kalendarze/*.json'):
    d = iso(kj.stem)
    if not d: continue
    kalendarze[d] = [(a['time'], canon(a['patient'])) for a in json.loads(kj.read_text())['appointments']]

visits = defaultdict(lambda: defaultdict(set))  # date -> initials -> {times or '-'}
for d, appts in kalendarze.items():
    for t, p in appts:
        visits[d][p].add(t)

dates_with_kalendarz = set(kalendarze)
filename_pairs = set()
for f in args.data_root.glob('formularze/*/*/*.jpg'):
    d = iso(f.parts[-3])
    p = patient(f.stem, NOUNS)
    if d and p: filename_pairs.add((p, d))
for f in args.data_root.glob('notatki/*/*.[pP][nN][gG]'):
    d = iso(f.parts[-2])
    p = patient(f.stem, NOUNS)
    if d and p: filename_pairs.add((p, d))

inconsistencies = []
for p, d in filename_pairs:
    if d in dates_with_kalendarz:
        if p not in visits[d]:
            inconsistencies.append((p, d))
    else:
        visits[d][p].add('-')

initials_seen = defaultdict(set)  # initials -> set of IDs already in use
for d, slot in mapping.items():
    for t, by_init in slot.items():
        for init, pid in by_init.items():
            if pid: initials_seen[init].add(pid)

existing_ids = {pid for slot in mapping.values() for by_init in slot.values() for pid in by_init.values() if pid}
next_n = max((int(i[1:]) for i in existing_ids if re.fullmatch(r'p\d+', i)), default=0) + 1

new_assigned = []
new_unresolved = []
stale_dashes = []
for d in sorted(visits):
    slot = mapping.setdefault(d, {})
    for p in sorted(visits[d]):
        for t in sorted(visits[d][p]):
            by_init = slot.setdefault(t, {})
            if p in by_init: continue
            if initials_seen[p]:
                by_init[p] = None
                new_unresolved.append((d, t, p))
            else:
                pid = f'p{next_n:03d}'
                next_n += 1
                by_init[p] = pid
                initials_seen[p].add(pid)
                new_assigned.append((d, t, p, pid))
    if '-' in slot and any(t != '-' for t in slot):
        for p in slot.get('-', {}):
            if any(p in slot[t] for t in slot if t != '-'):
                stale_dashes.append((d, p))

mapping = {d: {t: dict(sorted(by_init.items())) for t, by_init in sorted(slot.items())} for d, slot in sorted(mapping.items())}
args.json.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + '\n')

print(f'{len(new_assigned)} newly assigned, {len(new_unresolved)} need review')
for d, t, p, pid in new_assigned: print(f'  + {d} {t} {p} -> {pid}')
for d, t, p in new_unresolved: print(f'  ? {d} {t} {p}  (same initials seen before, please set ID)')
for p, d in inconsistencies: print(f'  ! {p} on {d}: filename exists but kalendarz has no such patient')
for d, p in stale_dashes: print(f'  ! {p} on {d}: kalendarz now has times but "-" entry still present, migrate manually')
unresolved_total = sum(1 for slot in mapping.values() for by_init in slot.values() for v in by_init.values() if v is None)
if unresolved_total: print(f'\n{unresolved_total} total unresolved entries in {args.json}')