"""build mapping.json from data tree + patient_ids.json.
mapping.json is the single source of truth for file<->patient-visit links.
Without --apply, prints what would change but does not write.
"""
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ExifTags

# EXIF tag id for DateTimeOriginal (camera capture time), resolved once.
DATETIME_ORIGINAL = next(k for k, v in ExifTags.TAGS.items() if v == 'DateTimeOriginal')
IMG_EXTS = {'.jpg', '.jpeg', '.png', '.heic'}

DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
TIME_RE = re.compile(r'(\d{2})-(\d{2})')
PATIENT_INITIALS = re.compile(r'^\w+-\w+$')


def find_initials(stem):
    for part in stem.split('_'):
        if PATIENT_INITIALS.match(part):
            return part.upper()
    return None


def photo_time(stem):
    """HH:MM from a photo stem, ignoring the date portion. None on miss."""
    stem_without_date = DATE_RE.sub('', stem)
    time_match = TIME_RE.search(stem_without_date)
    if not time_match:
        return None
    return f'{time_match.group(1)}:{time_match.group(2)}'


def slot_for_initials(ids, date, initials):
    """Find (slot_time, pid) for initials on date. (None, None) on miss or ambiguity."""
    slots = ids.get(date, {})
    hits = [(t, slot[initials]) for t, slot in slots.items()
            if initials in slot and t != '-']
    if len(hits) != 1:
        return None, None
    return hits[0]


def slot_for_time(ids, date, hhmm):
    """Last slot on date whose start <= hhmm. (None, None, None) on miss."""
    slots = ids.get(date, {})
    candidate_times = [t for t in slots if t <= hhmm and t != '-']
    if not candidate_times:
        return None, None, None
    chosen = max(candidate_times)
    initials, pid = next(iter(slots[chosen].items()))
    return chosen, initials, pid


def resolve_form_or_note(root, pattern, date_idx, ftype, ids):
    """Yield (pid, initials, date, slot_time, ftype, path) for each resolvable file."""
    for f in root.glob(pattern):
        date_match = DATE_RE.search(f.parts[date_idx])
        if not date_match:
            yield None, f, 'bad folder date'
            continue
        date = date_match.group(0)
        initials = find_initials(f.stem)
        if not initials:
            yield None, f, 'no initials in filename'
            continue
        slot_time, pid = slot_for_initials(ids, date, initials)
        if pid is None:
            yield None, f, f'{initials} not in patient_ids.json for {date} (or ambiguous)'
            continue
        yield (pid, initials, date, slot_time, ftype, f), None, None


def resolve_photo(root, ids):
    for f in root.glob('zdjecia/*/*'):
        if not f.is_file() or f.suffix.lower() == '.zip':
            continue
        date_match = DATE_RE.search(f.parts[-2])
        if not date_match:
            yield None, f, 'bad folder date'
            continue
        date = date_match.group(0)
        hhmm = photo_time(f.stem)
        if hhmm is None:
            yield None, f, 'no time in filename'
            continue
        slot_time, initials, pid = slot_for_time(ids, date, hhmm)
        if pid is None:
            why = (f'slot at {slot_time} on {date} has unresolved patient id ({initials})'
                   if slot_time is not None
                   else f'no slot for photo at {hhmm} on {date}')
            yield None, f, why
            continue
        yield (pid, initials, date, slot_time, 'slitlamp', f), None, None


def exif_capture(path):
    try:
        exif = Image.open(path)._getexif() or {}
    except Exception:
        return None, None
    raw = exif.get(DATETIME_ORIGINAL)
    if not raw or len(raw) < 16:
        return None, None
    date = raw[:10].replace(':', '-')
    hhmm = raw[11:16]
    if not DATE_RE.fullmatch(date) or not re.fullmatch(r'\d{2}:\d{2}', hhmm):
        return None, None
    return date, hhmm


def resolve_smartphone(root, ids):
    for f in root.glob('smartfon/**/*'):
        if not f.is_file() or f.suffix.lower() not in IMG_EXTS:
            continue
        date, hhmm = exif_capture(f)
        if date is None:
            yield None, f, 'no DateTimeOriginal in image metadata'
            continue
        slot_time, initials, pid = slot_for_time(ids, date, hhmm)
        if pid is None:
            why = (f'slot at {slot_time} on {date} has unresolved patient id ({initials})'
                   if slot_time is not None
                   else f'no slot for capture at {hhmm} on {date}')
            yield None, f, why
            continue
        yield (pid, initials, date, slot_time, 'smartfon', f), None, None


def build_mapping(root, ids):
    """Returns (mapping_dict, unresolved_list)."""
    # pid -> (date, slot_time) -> {initials, files: {ftype: path | [paths]}}
    visits = defaultdict(lambda: defaultdict(lambda: {'files': defaultdict(list)}))
    pid_initials = {}
    unresolved = []

    multi_types = {'slitlamp', 'smartfon'}

    sources = [
        resolve_form_or_note(root, 'formularze/*/kwestionariusze/*.jpg', -3, 'form', ids),
        resolve_form_or_note(root, 'formularze/*/zakresy/*.jpg', -3, 'form_scope', ids),
        resolve_form_or_note(root, 'notatki/*/*.[pP][nN][gG]', -2, 'notes', ids),
        resolve_photo(root, ids),
        resolve_smartphone(root, ids),
    ]
    for source in sources:
        for resolved, bad_file, why in source:
            if resolved is None:
                unresolved.append((bad_file, why))
                continue
            pid, initials, date, slot_time, ftype, path = resolved
            entry = visits[pid][(date, slot_time)]
            entry['initials'] = initials
            rel = str(path.relative_to(root))
            if ftype in multi_types:
                entry['files'][ftype].append(rel)
            else:
                entry['files'][ftype] = rel
            pid_initials[pid] = initials

    mapping = {}
    for pid in sorted(visits.keys()):
        visit_list = []
        for (date, slot_time) in sorted(visits[pid].keys()):
            entry = visits[pid][(date, slot_time)]
            visit_list.append({
                'date': date,
                'time': slot_time,
                **{ftype: paths for ftype, paths in sorted(entry['files'].items())},
            })
        mapping[pid] = {'initials': pid_initials[pid], 'visits': visit_list}
    return mapping, unresolved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data_root', type=Path)
    ap.add_argument('--apply', action='store_true',
                    help='write mapping.json; without this, only print the plan')
    args = ap.parse_args()

    root = args.data_root.resolve()
    out_path = root / 'mapping.json'
    ids_json = root / 'patient_ids.json'
    if not ids_json.exists():
        print(f'ERROR: {ids_json} not found; run assign_ids.py first', file=sys.stderr)
        sys.exit(2)
    ids = json.loads(ids_json.read_text())

    mapping, unresolved = build_mapping(root, ids)

    n_visits = sum(len(v['visits']) for v in mapping.values())
    n_files = sum(
        1 if isinstance(val, str) else len(val)
        for v in mapping.values() for visit in v['visits']
        for key, val in visit.items() if key not in ('date', 'time')
    )
    print(f'{len(mapping)} patients, {n_visits} visits, {n_files} files mapped')

    for f, why in unresolved:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        print(f'  ! {rel}  ({why})')
    print(f'{len(unresolved)} unresolved')

    if args.apply:
        out_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + '\n')
        print(f'\nwrote {out_path}')
    else:
        print(f'\n(dry run; pass --apply to write {out_path})')

    sys.exit(1 if unresolved else 0)


if __name__ == '__main__':
    main()