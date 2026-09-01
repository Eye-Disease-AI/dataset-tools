import argparse, json, sys
from collections import Counter, defaultdict
from pathlib import Path

TYPES = ['form', 'form_scope', 'notes', 'slitlamp', 'smartphone']
MULTI_TYPES = {'slitlamp', 'smartphone'}

parser = argparse.ArgumentParser()
parser.add_argument('data_root', type=Path)
args = parser.parse_args()
root = args.data_root.resolve()

mapping_json = root / 'mapping.json'
if not mapping_json.exists():
    print(f'ERROR: {mapping_json} not found. Run map_data.py first', file=sys.stderr)
    sys.exit(2)
mapping = json.loads(mapping_json.read_text())


def pct(n, total):
    if not total:
        return '    -'
    return f'{n / total * 100:5.1f}%'


visits = []
for patient in mapping.values():
    visits.extend(patient['visits'])

dates = sorted({visit['date'] for visit in visits})
n_patients = len(mapping)
n_visits = len(visits)

print(f'{n_patients} patients, {n_visits} visits, {len(dates)} days '
      f'({dates[0]} - {dates[-1]})')

print('\ncoverage per data type:')
for type in TYPES:
    patients_with = 0
    for patient in mapping.values():
        if any(type in visit for visit in patient['visits']):
            patients_with += 1

    visits_with = 0
    files = 0
    for visit in visits:
        if type not in visit:
            continue
        visits_with += 1
        if type in MULTI_TYPES:
            files += len(visit[type])
        else:
            files += 1

    print(f'  {type:12}'
          f'  {patients_with:4}/{n_patients:<4} patients {pct(patients_with, n_patients)}'
          f'  {visits_with:4}/{n_visits:<4} visits {pct(visits_with, n_visits)}'
          f'  {files:5} files')

complete = 0
for visit in visits:
    if all(type in visit for type in TYPES):
        complete += 1
print(f'\n{complete}/{n_visits} visits have every data type {pct(complete, n_visits)}')

print('\nvisits per patient:')
visit_counts = Counter(len(patient['visits']) for patient in mapping.values())
for n, patients_with in sorted(visit_counts.items()):
    print(f'  {n} visits {patients_with:5} patients {pct(patients_with, n_patients)}')

answers = defaultdict(Counter)
n_forms = 0
for f in sorted(root.glob('formularze/*/detect-verified_*.json')):
    try:
        parsed = json.loads(f.read_text())
    except json.JSONDecodeError as e:
        print(f'  ! {f.relative_to(root)} invalid json: {e}', file=sys.stderr)
        continue
    for name, fields in parsed.items():
        if not name.startswith('kwestionariusz'):
            continue
        n_forms += 1
        for question, answer in fields.items():
            if answer is None:
                answer = ''
            answers[question][str(answer).strip()] += 1

print(f'\nquestionaire answers ({n_forms} forms, {len(answers)} questions):')
for question, counter in sorted(answers.items()):
    total = sum(counter.values())
    answered = total - counter['']
    print(f'  {question}  ({answered}/{total} answered)')
    for answer, n in counter.most_common():
        print(f'      {answer or "(none)":28} {n:4} {pct(n, total)}')
