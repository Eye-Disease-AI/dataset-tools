import argparse, re, sys
from pathlib import Path

DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')
PATIENT_INITIALS = re.compile(r'^[A-Za-z]-[A-Za-z]$')
TIME_RE = re.compile(r'\d{2}-\d{2}-\d{2}')


def iso(s):
    m = DATE.search(s)
    if not m:
        return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"


def has_initials(stem):
    return any(PATIENT_INITIALS.match(p) for p in stem.split('_'))


def check_form_or_note(f, date_idx):
    """Generic check for files where the date is in folder and initials are in name."""
    folder_date = iso(f.parts[date_idx])
    if not folder_date:
        yield f, f'bad folder date {f.parts[date_idx]}'
        return
    stem_date = iso(f.stem)
    if stem_date and stem_date != folder_date:
        yield f, f'folder date {folder_date} != filename date {stem_date}'
    if not has_initials(f.stem):
        yield f, 'no patient initials (X-Y) in filename'


def check_photo(f):
    folder_date = iso(f.parts[-2])
    if not folder_date:
        yield f, f'bad folder date {f.parts[-2]}'
        return
    stem_date = iso(f.stem)
    if stem_date and stem_date != folder_date:
        yield f, f'folder date {folder_date} != filename date {stem_date}'
    # strip date so YYYY-MM-DD does not match HH-MM-SS pattern
    stem_no_date = re.sub(r'\d{4}-\d{2}-\d{2}', '', f.stem)
    if not TIME_RE.search(stem_no_date):
        yield f, 'no HH-MM-SS time in filename'


def check_calendar(f):
    if not iso(f.stem):
        yield f, 'no date in filename'


def collect_problems(root):
    for sub in ('kwestionariusze', 'zakresy'):
        for f in root.glob(f'formularze/*/{sub}/*.jpg'):
            yield from check_form_or_note(f, -3)
    for f in root.glob('notatki/*/*.[pP][nN][gG]'):
        yield from check_form_or_note(f, -2)
    for f in root.glob('zdjecia/*/*'):
        if not f.is_file() or f.suffix.lower() == '.zip':
            continue
        yield from check_photo(f)
    for f in root.glob('kalendarze/*'):
        if not f.is_file() or f.suffix.lower() == '.zip':
            continue
        yield from check_calendar(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data_root', type=Path)
    args = ap.parse_args()
    root = args.data_root.resolve()

    problems = list(collect_problems(root))

    for f, why in problems:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        print(f'  ! {rel}  ({why})')

    print(f'\n{len(problems)} problems')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()