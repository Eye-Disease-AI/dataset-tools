import argparse, json, re
from collections import defaultdict
from pathlib import Path

DATA_TYPES = {'kwestionariusz', 'zakres', 'zakresy', 'notatka'}
DATE = re.compile(r'(\d{2})[.\-_](\d{2})[.\-_](\d{4})|(\d{4})-(\d{2})-(\d{2})')

def iso(s):
    m = DATE.search(s)
    if not m: return None
    g = m.groups()
    return f"{g[3]}-{g[4]}-{g[5]}" if g[3] else f"{g[2]}-{g[1]}-{g[0]}"

def parse_patient_id(patient):
    if '-' in patient: return patient.upper()
    if len(patient) == 2: return f'{patient[0].upper()}-{patient[1].upper()}'
    return patient

PID_RE = re.compile(r'p\d+')

def get_patient(stem, nouns):
    parts = stem.split('_')
    for p in (parts[0], parts[-1], parts[-2] if len(parts) > 1 else ''):
        if p and p.casefold() not in nouns and not iso(p) and not PID_RE.fullmatch(p):
            return parse_patient_id(p)

parser = argparse.ArgumentParser()
parser.add_argument('data_root', type=Path)
parser.add_argument('--json', type=Path)
args = parser.parse_args()
if args.json is None:
    args.json = Path.joinpath(args.data_root, "patient_ids.json")
    
# dict[date][hour_slot][initials] -> patient ID
# allows to tell whether a patient at given date&time&initials is the same
# as the same initials in another visit
patient_id_mapping = json.loads(args.json.read_text()) if args.json.exists() else {}

kalendarze = {}
for callendars_json in args.data_root.glob('kalendarze/*.json'):
    date = iso(callendars_json.stem)
    if not date: 
        continue
    kalendarze[date] = [
        (appointment['time'], parse_patient_id(appointment['patient']))
        for appointment in json.loads(callendars_json.read_text())['appointments']
    ]

visit_hours = defaultdict(lambda: defaultdict(set))
for date, appointments in kalendarze.items():
    for time_slot, patient_initials in appointments:
        visit_hours[date][patient_initials].add(time_slot)

dates_with_callendar = set(kalendarze.keys())
patient_dates = set()

for f in args.data_root.glob('formularze/**/*.jpg'):
    date = iso(f.parts[-3])
    patient_initials = get_patient(f.stem, DATA_TYPES)
    if date and patient_initials:
        patient_dates.add((patient_initials, date))

for f in args.data_root.glob('notatki/**/*.[pP][nN][gG]'):
    date = iso(f.parts[-2])
    patient_initials = get_patient(f.stem, DATA_TYPES)
    if date and patient_initials:
        patient_dates.add((patient_initials, date))

inconsistencies = []
for patient_initials, date in patient_dates:
    if date in dates_with_callendar:
        if patient_initials not in visit_hours[date]:
            inconsistencies.append((patient_initials, date))
    else:
        visit_hours[date][patient_initials].add('-')

patients_by_initials = defaultdict(set)
for date, visits_in_date_per_slot in patient_id_mapping.items():
    for time_slot, patients_in_slot in visits_in_date_per_slot.items():
        for initials, patient_id in patients_in_slot.items():
            patients_by_initials[initials].add(patient_id)

existing_ids = {patient_id
    for (_date, slot) in patient_id_mapping.items()
    for initials_patient_map in slot.values()
    for patient_id in initials_patient_map.values()
    if patient_id
}
next_id = max(
    (
        int(i[1:])
        for i in existing_ids # p001, p002...
    ), default=0
) + 1

new_assigned = []
# when patient initials are duplicated and at least 2 occurences dont have an ID
new_unresolved = []
stale_dashes = []

for date, patients in sorted(visit_hours.items()):
    slots = patient_id_mapping.setdefault(date, {})

    for patient_initials in sorted(patients):
        for time_slot in sorted(patients[patient_initials]):
            slot = slots.setdefault(time_slot, {})

            if patient_initials in slot:
                continue

            if patients_by_initials[patient_initials]:
                slot[patient_initials] = None
                new_unresolved.append((date, time_slot, patient_initials))
            else:
                patient_id = f'p{next_id:03d}'
                next_id += 1
                slot[patient_initials] = patient_id
                patients_by_initials[patient_initials].add(patient_id)
                new_assigned.append((date, time_slot, patient_initials, patient_id))

    dash_slot = slots.get('-', {})
    real_slots = [s for t, s in slots.items() if t != '-']
    if dash_slot and real_slots:
        for patient_initials in dash_slot:
            if any(patient_initials in s for s in real_slots):
                stale_dashes.append((date, patient_initials))

# from pprint import pprint
# pprint(patients_by_initials)
# pprint(patients_in_slot)

patient_id_mapping = {date:
    {
        time_slot: dict(sorted(patient_id_map.items()))
        for time_slot, patient_id_map in sorted(appointment.items())
    }
    for date, appointment in sorted(patient_id_mapping.items())
}
args.json.write_text(json.dumps(patient_id_mapping, indent=2, ensure_ascii=False) + '\n')

print(f'{len(new_assigned)} newly assigned, {len(new_unresolved)} need review')
for date, time_slot, patient_initials, patient_id in new_assigned:
    print(f'  + {date} {time_slot} {patient_initials} -> {patient_id}')
for date, time_slot, patient_initials in new_unresolved:
    print(f'  ? {date} {time_slot} {patient_initials}  (same initials seen before, please set ID)')
for patient_initials, date in inconsistencies:
    print(f'  ! {patient_initials} on {date}: filename exists but kalendarz has no such patient')
for date, patient_initials in stale_dashes:
    print(f'  ! {patient_initials} on {date}: kalendarz now has times but "-" entry still present, migrate manually')

unresolved_total = sum(1
    for time_slot in patient_id_mapping.values()
    for by_initials in time_slot.values()
    for pid in by_initials.values()
    if pid is None
)
if unresolved_total:
    print(f'\n{unresolved_total} total unresolved entries in {args.json}')