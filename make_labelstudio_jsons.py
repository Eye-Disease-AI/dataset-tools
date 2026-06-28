import argparse, json, sys
from pathlib import Path

URL_PREFIX = '/data/local-files/?d=gabinet/'

def load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(f'ERROR: expected parsed file not found: {path}')
    return json.loads(path.read_text())


def form_values(root: Path, visit: dict, pid: str, initials: str) -> dict:
    quest_path = visit.get('form')
    if quest_path is None:
        return {}
    date = visit['date']
    parsed_path = root / 'formularze' / date / f'detect-verified_{date}.json'
    parsed = load_json(parsed_path)
    qestionnaire_name = f"kwestionariusz_{date}_{initials}.jpg"
    if qestionnaire_name not in parsed:
        sys.exit(f'ERROR: {qestionnaire_name} missing from {parsed_path}')
    return parsed[qestionnaire_name]


def notes_values(root: Path, visit: dict, pid: str, initials: str) -> dict:
    return {}

def slitlamp(visit: dict) -> list[dict]:
    s = [{'url': f'{URL_PREFIX}{rel}'} for rel in visit.get('slitlamp', [])]
    return s

def smartphone(visit: dict) -> list[dict]:
    s = [{'url': f'{URL_PREFIX}{rel}'} for rel in visit.get('smartphone', [])]
    return s

def visit_task(root: Path, pid: str, initials: str, visit: dict) -> dict:
    return {'data': {
        'patient_id': pid,
        'initials': initials,
        'date': visit['date'],
        'time': visit['time'],
        'slitlamp': slitlamp(visit),
        'smarthpone': smartphone(visit),
        'form': form_values(root, visit, pid, initials),
        'notes': notes_values(root, visit, pid, initials),
    }}


def build_tasks(root: Path, mapping: dict[str, dict]) -> dict[str, list[dict]]:
    return {
        patient_id: [visit_task(root, patient_id, patient_data['initials'], visit)
            for visit in patient_data['visits']
        ]
        for patient_id, patient_data in sorted(mapping.items())
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('data_root', type=Path)
    parser.add_argument('--out', type=Path, default=None,
                    help='output dir for <pid>.json files (default: data_root/labelstudio)')
    parser.add_argument('--apply', action='store_true',
                    help='write the json files; without this, only print the plan')
    args = parser.parse_args()

    root: Path = args.data_root.resolve()
    out_dir: Path = args.out or root / 'labelstudio'

    mapping_json = root / 'mapping.json'
    if not mapping_json.exists():
        sys.exit(f'ERROR: {mapping_json} not found; run map_data.py first')

    mapping: dict[str, dict] = json.loads(mapping_json.read_text())
    by_patient = build_tasks(root, mapping)

    n_tasks = sum(len(tasks) for tasks in by_patient.values())
    n_images = sum(len(task['data']['slitlamp']) if 'slitlamp' in task['data'] else 0
                   for tasks in by_patient.values() for task in tasks)
    print(f'{len(by_patient)} patients, {n_tasks} visit-tasks, {n_images} images')
    for pid, tasks in by_patient.items():
        print(f'  {pid}: {len(tasks)} task(s) -> {out_dir / f"{pid}.json"}')

    if args.apply:
        out_dir.mkdir(parents=True, exist_ok=True)
        for pid, tasks in by_patient.items():
            (out_dir / f'{pid}.json').write_text(
                json.dumps(tasks, indent=2, ensure_ascii=False) + '\n')
        print(f'\nwrote {len(by_patient)} files to {out_dir}')
    else:
        print(f'\n(dry run; pass --apply to write files to {out_dir})')


if __name__ == '__main__':
    main()
