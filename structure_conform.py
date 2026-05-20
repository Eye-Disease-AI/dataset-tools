from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

DATE_ANY = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})')
DATE_ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def folder_date(name: str) -> str | None:
    m = DATE_ANY.fullmatch(name) or DATE_ISO.fullmatch(name)
    if not m:
        return None
    g = m.groups()
    if len(g[0]) == 4:
        return f"{g[0]}-{g[1]}-{g[2]}"
    return f"{g[2]}-{g[1]}-{g[0]}"


def find_date_in_stem(stem: str) -> str | None:
    m = DATE_ISO.search(stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = DATE_ANY.search(stem)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


@dataclass
class Issue:
    src: Path
    dst: Path | None
    reason: str | None


def extract_patient(stem: str, singular: str) -> str | None:
    parts = stem.split("_")
    if not parts:
        return None
    if parts[0] == singular:
        return parts[-1].upper() if parts[-1] else None
    return parts[0].upper()


def check_formularze(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    base = root / "formularze"
    if not base.exists():
        return issues

    for date_dir in sorted(base.iterdir()):
        if not date_dir.is_dir():
            issues.append(Issue(date_dir, None, "non-directory under formularze/"))
            continue
        fdate = folder_date(date_dir.name)
        if fdate is None:
            issues.append(Issue(date_dir, None, f"unrecognized folder date '{date_dir.name}'"))
            continue
        new_date_dir = Path("formularze") / fdate

        detect_target = new_date_dir / f"detect_{fdate}.json"
        verified_target = new_date_dir / f"detect-verified_{fdate}.json"
        seen_detect = False
        seen_verified = False

        for f in date_dir.iterdir():
            if not f.is_file():
                continue
            if f.name in ("detect.json", f"detect_{fdate}.json"):
                issues.append(Issue(f, detect_target, None))
                seen_detect = True
            elif f.name in ("detect_verified.json", f"detect-verified_{fdate}.json"):
                issues.append(Issue(f, verified_target, None))
                seen_verified = True
            else:
                issues.append(Issue(f, None, "unrecognized file in formularze/<date>/"))

        if not seen_detect:
            issues.append(Issue(date_dir / "detect.json", None, "required detect.json missing"))
        if not seen_verified:
            issues.append(Issue(date_dir / "detect_verified.json", None, "required detect_verified.json missing"))

        for sub_name, singular in [("kwestionariusze", "kwestionariusz"),
                                    ("zakresy", "zakres")]:
            sub = date_dir / sub_name
            if not sub.exists():
                continue
            for f in sorted(sub.iterdir()):
                if not f.is_file():
                    issues.append(Issue(f, None, f"non-file under {sub_name}/"))
                    continue
                stem = f.stem
                if "_" not in stem:
                    issues.append(Issue(f, None, "stem missing underscore separator"))
                    continue
                patient = extract_patient(stem, singular)
                if not patient:
                    issues.append(Issue(f, None, "could not extract patient from stem"))
                    continue
                stem_date = find_date_in_stem(stem)
                if stem_date is None:
                    issues.append(Issue(f, None, "no date found in filename"))
                    continue
                if stem_date != fdate:
                    issues.append(Issue(f, None,
                        f"folder date {fdate} disagrees with filename date {stem_date}"))
                    continue
                new_name = f"{singular}_{fdate}_{patient}{f.suffix.lower()}"
                issues.append(Issue(f, new_date_dir / sub_name / new_name, None))

    return issues


def check_notatki(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    base = root / "notatki"
    if not base.exists():
        return issues

    for date_dir in sorted(base.iterdir()):
        if not date_dir.is_dir():
            issues.append(Issue(date_dir, None, "non-directory under notatki/"))
            continue
        fdate = folder_date(date_dir.name)
        if fdate is None:
            issues.append(Issue(date_dir, None, f"unrecognized folder date '{date_dir.name}'"))
            continue
        new_date_dir = Path("notatki") / fdate
        for f in sorted(date_dir.iterdir()):
            if not f.is_file():
                issues.append(Issue(f, None, "non-file under notatki/<date>/"))
                continue
            stem = f.stem
            stem_date = find_date_in_stem(stem)
            if stem_date is not None and stem_date != fdate:
                issues.append(Issue(f, None,
                    f"folder date {fdate} disagrees with filename date {stem_date}"))
                continue
            parts = stem.split("_")
            if parts[0] == "notatka":
                patient = parts[-1].upper() if parts[-1] else ""
            else:
                patient = stem.upper()
            if not patient:
                issues.append(Issue(f, None, "could not extract patient from stem"))
                continue
            new_name = f"notatka_{fdate}_{patient}{f.suffix.lower()}"
            issues.append(Issue(f, new_date_dir / new_name, None))

    return issues


def check_kalendarze(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    base = root / "kalendarze"
    if not base.exists():
        return issues
    for f in sorted(base.iterdir()):
        if not f.is_file():
            issues.append(Issue(f, None, "non-file under kalendarze/"))
            continue
        if f.suffix.lower() == ".zip":
            continue
        stem_date = find_date_in_stem(f.stem)
        if stem_date is None:
            issues.append(Issue(f, None, "no date found in kalendarze filename"))
            continue
        new_name = f"kalendarz_{stem_date}{f.suffix.lower()}"
        issues.append(Issue(f, Path("kalendarze") / new_name, None))
    return issues


def check_zdjecia(root: Path, type_name: str) -> list[Issue]:
    issues: list[Issue] = []
    base = root / type_name
    if not base.exists():
        return issues

    for entry in sorted(base.iterdir()):
        if entry.is_file():
            if entry.suffix.lower() == ".zip":
                continue
            issues.append(Issue(entry, None, f"loose file under {type_name}/"))
        elif entry.is_dir():
            fdate = folder_date(entry.name)
            if fdate is None:
                issues.append(Issue(entry, None, f"unrecognized folder date '{entry.name}'"))
                continue
            new_date_dir = Path(type_name) / fdate
            for f in sorted(entry.iterdir()):
                if not f.is_file():
                    issues.append(Issue(f, None, f"non-file under {type_name}/<date>/"))
                    continue
                if f.suffix.lower() == ".zip":
                    continue
                stem = f.stem
                already_prefix = f"zdjecie_{fdate}"
                if stem == already_prefix or stem.startswith(already_prefix + "_"):
                    rest = stem[len(already_prefix):].lstrip("_")
                else:
                    stem_date = find_date_in_stem(stem)
                    if stem_date is None:
                        issues.append(Issue(f, None, "no date found in zdjecie filename"))
                        continue
                    if stem_date != fdate:
                        issues.append(Issue(f, None,
                            f"folder date {fdate} disagrees with filename date {stem_date}"))
                        continue
                    idx = stem.find(stem_date)
                    rest = (stem[:idx] + stem[idx + len(stem_date):]).strip(" _-")
                rest = rest.replace(" ", "_")
                new_stem = f"zdjecie_{fdate}_{rest}" if rest else f"zdjecie_{fdate}"
                new_name = new_stem + f.suffix.lower()
                issues.append(Issue(f, new_date_dir / new_name, None))

    return issues


def check_all(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for fn in (
        check_formularze,
        check_notatki,
        check_kalendarze,
        lambda r: check_zdjecia(r, "zdjecia"),
        lambda r: check_zdjecia(r, "zdjecia-telefon"),
    ):
        issues.extend(fn(root))
    return issues


def main() -> None:
    args = sys.argv[1:]
    fix = "--fix" in args
    args = [a for a in args if a != "--fix"]
    if len(args) != 1:
        print("usage: python validate.py <root> [--fix]", file=sys.stderr)
        sys.exit(1)
    root = Path(args[0]).resolve()
    new_root = root.parent / f"{root.name}_renamed"

    issues = check_all(root)

    renames = [i for i in issues if i.reason is None and i.dst is not None]
    problems = [i for i in issues if i.reason is not None]
    needs_rename = [i for i in renames if i.src.name != i.dst.name]
    already_ok = [i for i in renames if i.src.name == i.dst.name]

    seen: dict[Path, Path] = {}
    collisions: list[tuple[Path, Path, Path]] = []
    for i in renames:
        if i.dst in seen:
            collisions.append((i.dst, seen[i.dst], i.src))
        else:
            seen[i.dst] = i.src

    print(f"Validity check: {root}")
    print(f"  {len(already_ok)} already conform")
    print(f"  {len(needs_rename)} need rename")
    print(f"  {len(problems)} problems")
    print(f"  {len(collisions)} naming collisions")
    print()

    if needs_rename:
        print("--- NEEDS RENAME ---")
        for i in needs_rename:
            rel = i.src.relative_to(root)
            print(f"  {rel}")
            print(f"    -> {i.dst}")
        print()

    if problems:
        print("--- PROBLEMS ---")
        for i in problems:
            try:
                rel = i.src.relative_to(root)
            except ValueError:
                rel = i.src
            print(f"  {rel}  ({i.reason})")
        print()

    if collisions:
        print("--- COLLISIONS ---")
        for dst, src_a, src_b in collisions:
            print(f"  {dst}")
            print(f"    <- {src_a.relative_to(root)}")
            print(f"    <- {src_b.relative_to(root)}")
        print()

    exit_code = 0 if not (problems or collisions) else 1

    if not fix:
        if problems or collisions:
            print("FAIL — rerun with --fix once problems are resolved")
        elif needs_rename:
            print("OK — rerun with --fix to write the renamed tree")
        else:
            print("OK — nothing to do")
        sys.exit(exit_code)

    if collisions:
        print("Refusing to --fix while collisions exist.", file=sys.stderr)
        sys.exit(2)
    if new_root.exists():
        print(f"ERROR: {new_root} already exists; remove or rename it first.",
              file=sys.stderr)
        sys.exit(2)

    new_root.mkdir()
    for i in renames:
        dst_abs = new_root / i.dst
        dst_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(i.src, dst_abs)
    print(f"Wrote {len(renames)} files to {new_root}")
    if problems:
        print(f"({len(problems)} files skipped due to problems above)")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()