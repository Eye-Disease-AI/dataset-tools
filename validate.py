import argparse, json, re, shutil, sys
from pathlib import Path

DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')

def iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

PID_RE = re.compile(r'p\d+')

def patient(stem, noun):
    parts = stem.split('_')
    for p in (parts[0], parts[-1], parts[-2] if len(parts) > 1 else ''):
        if p and p.casefold() not in {noun, noun + 'y'} and not iso(p) and not PID_RE.fullmatch(p): return p

def canon(p):
    if '-' in p: return p.upper(), None
    if len(p) == 2: return f'{p[0].upper()}-{p[1].upper()}', None
    return p, f"patient '{p}' has {len(p)} chars and no hyphen; needs manual fix"

def pid(ids, p, d):
    sub = ids.get(p)
    if sub is None or d not in sub: return None, f"no patient ID for {p} on {d} in JSON"
    if sub[d] is None: return None, f"unresolved patient ID for {p} on {d} (null in JSON)"
    return sub[d], None

def plan(root, ids):
    for sub, noun in [('kwestionariusze', 'kwestionariusz'), ('zakresy', 'zakres')]:
        for f in root.glob(f'formularze/*/{sub}/*.jpg'):
            d = iso(f.parts[-3])
            if not d: yield f, None, None, None, f"bad folder date {f.parts[-3]}"; continue
            sd = iso(f.stem)
            if sd and sd != d: yield f, None, None, None, f"folder {d} vs stem {sd}"; continue
            p = patient(f.stem, noun)
            if not p: yield f, None, None, None, "no patient"; continue
            p, err = canon(p)
            if err: yield f, None, None, None, err; continue
            i, err = pid(ids, p, d)
            if err: yield f, None, p, d, err; continue
            yield f, Path(f'formularze/{d}/{sub}/{noun}_{d}_{p}_{i}.jpg'), p, d, None

    for date_dir in (root / 'formularze').glob('*'):
        if not date_dir.is_dir(): continue
        d = iso(date_dir.name)
        if not d: continue
        for name, base in [('detect', 'detect'), ('detect_verified', 'detect-verified')]:
            existing = next((date_dir / n for n in (f'{name}.json', f'{base}_{d}.json') if (date_dir / n).exists()), None)
            if existing: yield existing, Path(f'formularze/{d}/{base}_{d}.json'), None, None, None
            else: yield date_dir / f'{name}.json', None, None, None, f"required {name}.json missing"

    for f in root.glob('notatki/*/*.[pP][nN][gG]'):
        d = iso(f.parts[-2])
        if not d: yield f, None, None, None, f"bad folder date {f.parts[-2]}"; continue
        p = patient(f.stem, 'notatka')
        if not p: yield f, None, None, None, "no patient"; continue
        p, err = canon(p)
        if err: yield f, None, None, None, err; continue
        i, err = pid(ids, p, d)
        if err: yield f, None, p, d, err; continue
        yield f, Path(f'notatki/{d}/notatka_{d}_{p}_{i}.png'), p, d, None

    sch = {}
    for f in root.glob('kalendarze/*'):
        if f.suffix.lower() == '.zip' or not f.is_file(): continue
        d = iso(f.stem)
        if not d: yield f, None, None, None, "no date in name"; continue
        yield f, Path(f'kalendarze/kalendarz_{d}{f.suffix.lower()}'), None, d, None
        if f.suffix.lower() == '.json':
            appts = sorted((a['time'], a['patient']) for a in json.loads(f.read_text())['appointments'])
            sch[d] = []
            for t, p_raw in appts:
                p, err = canon(p_raw)
                if err: yield f, None, None, None, f"in JSON: {err}"; continue
                i, err = pid(ids, p, d)
                if err: yield f, None, p, d, f"in JSON: {err}"; continue
                yield f, None, p, d, None
                sch[d].append((t, p, i))

    for f in root.glob('zdjecia/*/*'):
        if not f.is_file() or f.suffix.lower() == '.zip': continue
        d = iso(f.parts[-2])
        if not d: continue
        rest = re.sub(r'^.*?\d{4}-\d{2}-\d{2}[ _-]*', '', f.stem).replace(' ', '_')
        p = None
        i = None
        if d in sch:
            m = re.search(r'(\d{2})-(\d{2})', rest)
            if m:
                hhmm = f'{m.group(1)}:{m.group(2)}'
                hit = next(((pp, ii) for t, pp, ii in reversed(sch[d]) if t <= hhmm), None)
                if not hit: yield f, None, None, None, f"photo at {hhmm} before all appointments on {d}"; continue
                p, i = hit
        suffix = f'_{i}' if i else ''
        if rest.endswith(suffix) and suffix: rest = rest[:-len(suffix)]
        new_stem = f'zdjecie_{d}_{rest}{suffix}' if rest else f'zdjecie_{d}{suffix}'
        yield f, Path(f'zdjecia/{d}/{new_stem}{f.suffix.lower()}'), p, d, None

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
    problems = [(s, why) for s, _, _, _, why in records if why]
    renames = [(s, d) for s, d, _, _, why in records if why is None and d]
    needs = [(s, d) for s, d in renames if s.name != d.name]
    by_pid = {}
    for _, _, p, d, why in records:
        if p and d and not why: by_pid.setdefault((p.casefold(), d), (p, d))
    pairs = sorted(by_pid.values(), key=lambda x: (x[1], x[0].casefold()))

    seen = {}
    collisions = []
    for s, d in renames:
        if d in seen: collisions.append((d, seen[d], s))
        else: seen[d] = s

    print(f'{len(needs)} need rename, {len(problems)} problems, {len(collisions)} collisions, {len(pairs)} patient-date rows')
    for s, d in needs: print(f'  {s.relative_to(root)} -> {d}')
    for s, why in problems:
        try: rel = s.relative_to(root)
        except ValueError: rel = s
        print(f'  ! {rel}  ({why})')
    for d, a, b in collisions: print(f'  X {d}  <- {a.relative_to(root)}  <- {b.relative_to(root)}')

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