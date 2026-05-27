"""
Source of truth for patient IDs.
Without --apply, prints what would change but does not write.
Always prints repeating-initials that need to be resolved.
"""
import argparse, json, re
from collections import defaultdict
from pathlib import Path

DATA_TYPES = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')
PID_RE = re.compile(r'p\d+')


def iso(s):
    m = DATE.search(s)
    if not m:
        return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"


def canonical_initials(patient):
    if '-' in patient:
        return patient.upper()
    if len(patient) == 2:
        return f'{patient[0].upper()}-{patient[1].upper()}'
    return patient


def find_initials_in_stem(stem):
    parts = stem.split('_')
    for p in (parts[0], parts[-1], parts[-2] if len(parts) > 1 else ''):
        if p and p.casefold() not in DATA_TYPES and not iso(p) and not PID_RE.fullmatch(p):
            return canonical_initials(p)
    return None


def load_calendars(data_root):
    """date -> [(time, initials)]"""
    out = {}
    for f in data_root.glob('kalendarze/*.json'):
        date = iso(f.stem)
        if not date:
            continue
        out[date] = [
            (a['time'], canonical_initials(a['patient']))
            for a in json.loads(f.read_text())['appointments']
        ]
    return out


def collect_file_initials(data_root):
    """Set of (initials, date) from formularze + notatki filenames."""
    pairs = set()
    for f in data_root.glob('formularze/**/*.jpg'):
        date = iso(f.parts[-3])
        initials = find_initials_in_stem(f.stem)
        if date and initials:
            pairs.add((initials, date))
    for f in data_root.glob('notatki/**/*.[pP][nN][gG]'):
        date = iso(f.parts[-2])
        initials = find_initials_in_stem(f.stem)
        if date and initials:
            pairs.add((initials, date))
    return pairs


def build_visit_hours(calendars, file_pairs):
    """date -> initials -> set of time slots ('-' if known only from files, not calendar)."""
    visit_hours = defaultdict(lambda: defaultdict(set))
    for date, appts in calendars.items():
        for time_slot, initials in appts:
            visit_hours[date][initials].add(time_slot)
    inconsistencies = []
    for initials, date in file_pairs:
        if date in calendars:
            if initials not in visit_hours[date]:
                inconsistencies.append((initials, date))
        else:
            visit_hours[date][initials].add('-')
    return visit_hours, inconsistencies


def assign(existing_mapping, visit_hours):
    """Add new IDs into a fresh copy of existing_mapping. Returns (new_mapping, assigned, unresolved, stale_dashes)."""
    mapping = json.loads(json.dumps(existing_mapping))

    # known: initials -> set of pids already assigned to them
    known_by_initials = defaultdict(set)
    existing_ids = set()
    for _date, slot in mapping.items():
        for time_slot, by_init in slot.items():
            for initials, pid in by_init.items():
                if pid:
                    known_by_initials[initials].add(pid)
                    existing_ids.add(pid)

    next_id = max((int(p[1:]) for p in existing_ids), default=0) + 1

    assigned = []
    unresolved = []

    for date in sorted(visit_hours.keys()):
        slots = mapping.setdefault(date, {})
        for initials in sorted(visit_hours[date].keys()):
            for time_slot in sorted(visit_hours[date][initials]):
                slot = slots.setdefault(time_slot, {})
                if initials in slot:
                    continue
                if known_by_initials[initials]:
                    # same initials seen before for a different visit, issue
                    slot[initials] = None
                    unresolved.append((date, time_slot, initials))
                else:
                    pid = f'p{next_id:03d}'
                    next_id += 1
                    slot[initials] = pid
                    known_by_initials[initials].add(pid)
                    assigned.append((date, time_slot, initials, pid))

    # stale '-' entries: found real calendar slots for old ambiguous visits
    stale_dashes = []
    for date, slots in mapping.items():
        dash = slots.get('-', {})
        real = [s for t, s in slots.items() if t != '-']
        if dash and real:
            for initials in dash:
                if any(initials in s for s in real):
                    stale_dashes.append((date, initials))

    mapping = {
        date: {t: dict(sorted(by_init.items())) for t, by_init in sorted(slots.items())}
        for date, slots in sorted(mapping.items())
    }
    return mapping, assigned, unresolved, stale_dashes


def repeating_initials_summary(visit_hours, mapping):
    """Split into (resolved, unresolved). Each: initials -> [(date, time, pid_or_None)]."""
    by_initials = defaultdict(list)
    for date, by_init in visit_hours.items():
        for initials, times in by_init.items():
            for t in times:
                pid = mapping.get(date, {}).get(t, {}).get(initials)
                by_initials[initials].append((date, t, pid))
    resolved = {}
    unresolved = {}
    for initials, occurrences in by_initials.items():
        if len(occurrences) <= 1:
            continue
        if any(pid is None for _, _, pid in occurrences):
            unresolved[initials] = sorted(occurrences)
        else:
            resolved[initials] = sorted(occurrences)
    return resolved, unresolved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data_root', type=Path)
    ap.add_argument('--apply', action='store_true',
                    help='write to patient_ids.json')
    args = ap.parse_args()
    json_path = Path.joinpath(args.data_root, "patient_ids.json")
    existing = json.loads(json_path.read_text()) if json_path.exists() else {}

    calendars = load_calendars(args.data_root)
    file_pairs = collect_file_initials(args.data_root)
    visit_hours, inconsistencies = build_visit_hours(calendars, file_pairs)
    new_mapping, assigned, unresolved, stale_dashes = assign(existing, visit_hours)

    print(f'{len(assigned)} would be newly assigned, {len(unresolved)} need review')
    for date, time_slot, initials, pid in assigned:
        print(f'  + {date} {time_slot} {initials} -> {pid}')
    for date, time_slot, initials in unresolved:
        print(f'  ? {date} {time_slot} {initials}  (same initials seen before, please set ID manually)')
    for initials, date in inconsistencies:
        print(f'  ! {initials} on {date}: filename exists but kalendarz has no such patient')
    for date, initials in stale_dashes:
        print(f'  ! {initials} on {date}: kalendarz now has times but "-" entry still present, migrate manually')

    resolved_repeats, unresolved_repeats = repeating_initials_summary(visit_hours, new_mapping)
    if resolved_repeats:
        print(f'\nrepeating initials, resolved ({len(resolved_repeats)}):')
        for initials, occurrences in sorted(resolved_repeats.items(), key=lambda x: (-len(x[1]), x[0])):
            details = ', '.join(f'{d} {t} -> {pid}' for d, t, pid in occurrences)
            print(f'  {initials:6}  {details}')
    if unresolved_repeats:
        print(f'\nrepeating initials, UNRESOLVED ({len(unresolved_repeats)}):')
        for initials, occurrences in sorted(unresolved_repeats.items(), key=lambda x: (-len(x[1]), x[0])):

            print(f'  {initials:6}')
            for d, t, pid in occurrences:
                print(f"\t{d} {t} -> {pid or "?"}")

        print('These need to be fixed manually. Either append more letters to initials, '
              f'or replace `null` with a new patient id in {json_path}')

    if args.apply:
        json_path.write_text(json.dumps(new_mapping, indent=2, ensure_ascii=False) + '\n')
        print(f'\nwrote {json_path}')
    else:
        print(f'\n(dry run; pass --apply to write {json_path})')


if __name__ == '__main__':
    main()