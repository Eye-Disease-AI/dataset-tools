import argparse, json, re, shutil, sys
from pathlib import Path

DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')

def iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

PID_RE = re.compile(r'p\d+')

def make_patient_id(stem, noun):
    parts = stem.split('_')
    for p in (parts[0], parts[-1], parts[-2] if len(parts) > 1 else ''):
        if p and p.casefold() not in {noun, noun + 'y'} and not iso(p) and not PID_RE.fullmatch(p):
            return p

def canonise_patient_id(patient):
    if '-' in patient:
        return patient.upper(), None
    if len(patient) == 2:
        return f'{patient[0].upper()}-{patient[1].upper()}', None
    return patient, f"patient '{patient}' has {len(patient)} chars and no hyphen; needs manual fix"

def pid(ids, p, d, t=None):
    """Look up patient in patient_ids.json. Returns (pid, err, warn).
       Used for consistency checking only — pid value is no longer written to filenames."""
    slot = ids.get(d)
    if not slot: return None, f"no entry for date {d} in JSON", None
    if t is not None:
        by_init = slot.get(t)
        if not by_init or p not in by_init:
            return None, f"no patient ID for {p} on {d} at {t} in JSON", None
        if by_init[p] is None:
            return None, None, f"unresolved patient ID for {p} on {d} {t}"
        return by_init[p], None, None
    hits = [(t2, by_init[p]) for t2, by_init in slot.items() if p in by_init]
    if not hits:
        return None, f"no patient ID for {p} on {d} in JSON", None
    if len(hits) > 1:
        return None, f"multiple visits for {p} on {d}; can't tell which one this file is", None
    _, v = hits[0]
    if v is None:
        return None, None, f"unresolved patient ID for {p} on {d}"
    return v, None, None

def plan(root, ids):
    for sub, noun in [('kwestionariusze', 'kwestionariusz'), ('zakresy', 'zakres')]:
        for filename in root.glob(f'formularze/*/{sub}/*.jpg'):
            day = iso(filename.parts[-3])
            if not day:
                yield filename, None, None, None, f"bad folder date {filename.parts[-3]}", None
                continue
            sd = iso(filename.stem)
            if sd and sd != day:
                yield filename, None, None, None, f"folder {day} vs stem {sd}", None
                continue
            if PID_RE.search(filename.stem):
                yield filename, None, None, day, "patient id in filename; not allowed (lives in patient_ids.json)", None
                continue
            p = make_patient_id(filename.stem, noun)
            if not p:
                yield filename, None, None, None, "no patient", None
                continue
            p, err = canonise_patient_id(p)
            if err:
                yield filename, None, None, None, err, None
                continue
            _i, err, warn = pid(ids, p, day)
            if err:
                yield filename, None, p, day, err, None
                continue
            yield filename, Path(f'formularze/{day}/{sub}/{noun}_{day}_{p}.jpg'), p, day, None, warn

    for date_dir in (root / 'formularze').glob('*'):
        if not date_dir.is_dir():
            continue
        day = iso(date_dir.name)
        if not day:
            continue
        for name, base in [('detect', 'detect'), ('detect_verified', 'detect-verified')]:
            existing = next((date_dir / n for n in (f'{name}.json', f'{base}_{day}.json') if (date_dir / n).exists()), None)
            if existing:
                yield existing, Path(f'formularze/{day}/{base}_{day}.json'), None, None, None, None
            else:
                yield date_dir / f'{name}.json', None, None, None, f"required {name}.json missing", None

    for filename in root.glob('notatki/*/*.[pP][nN][gG]'):
        day = iso(filename.parts[-2])
        if not day:
            yield filename, None, None, None, f"bad folder date {filename.parts[-2]}", None
            continue
        if PID_RE.search(filename.stem):
            yield filename, None, None, day, "patient id in filename; not allowed (lives in patient_ids.json)", None
            continue
        p = make_patient_id(filename.stem, 'notatka')
        if not p:
            yield filename, None, None, None, "no patient", None
            continue
        p, err = canonise_patient_id(p)
        if err:
            yield filename, None, None, None, err, None
            continue
        _i, err, warn = pid(ids, p, day)
        if err:
            yield filename, None, p, day, err, None
            continue
        yield filename, Path(f'notatki/{day}/notatka_{day}_{p}.png'), p, day, None, warn

    schedule = {}
    for filename in root.glob('kalendarze/*'):
        if filename.suffix.lower() == '.zip' or not filename.is_file():
            continue
        day = iso(filename.stem)
        if not day:
            yield filename, None, None, None, "no date in name", None
            continue
        yield filename, Path(f'kalendarze/kalendarz_{day}{filename.suffix.lower()}'), None, day, None, None
        if filename.suffix.lower() == '.json':
            appts = sorted((a['time'], a['patient']) for a in json.loads(filename.read_text())['appointments'])
            schedule[day] = []
            for t, patient in appts:
                p, err = canonise_patient_id(patient)
                if err:
                    yield filename, None, None, None, f"in JSON: {err}", None
                    continue
                _i, err, warn = pid(ids, p, day, t)
                if err:
                    yield filename, None, p, day, f"in JSON: {err}", None
                    continue
                yield filename, None, p, day, None, warn
                schedule[day].append((t, p))

    for filename in root.glob('zdjecia/*/*'):
        if not filename.is_file() or filename.suffix.lower() == '.zip':
            continue
        day = iso(filename.parts[-2])
        if not day:
            continue
        file_basename = re.sub(r'^.*?\d{4}-\d{2}-\d{2}[ _-]*', '', filename.stem).replace(' ', '_')

        # resolve patient via calendar + photo time (for reporting only never written to filename)
        p = None
        if day in schedule:
            time_match = re.search(r'(\d{2})-(\d{2})', file_basename)
            if time_match:
                hhmm = f'{time_match.group(1)}:{time_match.group(2)}'
                hit = False
                for t, pp in reversed(schedule[day]):
                    if t <= hhmm:
                        p = pp
                        hit = True
                        break
                if not hit:
                    yield filename, None, None, None, f"photo at {hhmm} before all appointments on {day}", None
                    continue

        new_stem = f'zdjecie_{day}_{file_basename}' if file_basename else f'zdjecie_{day}'
        yield filename, Path(f'zdjecia/{day}/{new_stem}{filename.suffix.lower()}'), p, day, None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data_root', type=Path)
    ap.add_argument('--fix', action='store_true')
    ap.add_argument('--patients-csv', type=Path, dest='csv')
    ap.add_argument('--ids', type=Path, default=Path('patient_ids.json'))
    args = ap.parse_args()
    fix, csv = args.fix, args.csv
    root = args.data_root.resolve()
    new_root = root.parent / f'{root.name}_renamed'
    if not args.ids.exists():
        print(f'ERROR: {args.ids} not found; run assign_ids.py first', file=sys.stderr)
        sys.exit(2)
    ids = json.loads(args.ids.read_text())

    records = list(plan(root, ids))
    problems = [(s, why) for s, _, _, _, why, _ in records if why]
    warnings = [(s, w) for s, _, _, _, _, w in records if w]
    renames = [(s, d) for s, d, _, _, why, _ in records if why is None and d]
    needs = [(s, d) for s, d in renames if s.name != d.name]
    by_pid = {}
    for _, _, p, d, why, _ in records:
        if p and d and not why: by_pid.setdefault((p.casefold(), d), (p, d))
    pairs = sorted(by_pid.values(), key=lambda x: (x[1], x[0].casefold()))

    seen = {}
    collisions = []
    for s, d in renames:
        if d in seen: collisions.append((d, seen[d], s))
        else: seen[d] = s

    print(f'{len(needs)} need rename, {len(problems)} problems, {len(warnings)} warnings, {len(collisions)} collisions, {len(pairs)} patient-date rows')
    for s, d in needs:
        print(f'  {s.relative_to(root)} -> {d}')
    for s, why in problems:
        try: rel = s.relative_to(root)
        except ValueError: rel = s
        print(f'  ! {rel}  ({why})')
    for s, w in warnings:
        try: rel = s.relative_to(root)
        except ValueError: rel = s
        print(f'  ~ {rel}  ({w})')
    for d, a, b in collisions:
        print(f'  X {d}  <- {a.relative_to(root)}  <- {b.relative_to(root)}')

    if csv:
        csv.write_text('initials,date\n' + ''.join(f'{p},{d}\n' for p, d in pairs))
        print(f'wrote {csv}')

    if fix and not collisions and not new_root.exists():
        new_root.mkdir()
        for s, d in renames:
            (new_root / d).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, new_root / d)
        print(f'copied {len(renames)} to {new_root}')
    elif fix:
        print('refused to --fix (collisions or destination exists)')

    sys.exit(1 if problems or collisions else 0)

if __name__ == '__main__': main()