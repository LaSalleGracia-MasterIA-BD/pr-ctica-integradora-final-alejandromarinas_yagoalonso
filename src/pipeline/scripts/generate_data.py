"""Genera datos hospitalarios sinteticos (pacientes + ingresos) para testear el pipeline.

Produce archivos CSV con la forma de los que emitirian los sistemas fuente del
hospital, incluyendo casos borde intencionados (nulls, fechas malformadas,
duplicados, referencias huerfanas) para que los validators downstream tengan
algo significativo que rechazar.
"""
from __future__ import annotations

import argparse
import csv
import random
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

from faker import Faker

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

PATIENT_COLUMNS = (
    "external_id",
    "name",
    "birth_date",
    "gender",
    "blood_type",
)

ADMISSION_COLUMNS = (
    "patient_external_id",
    "admission_date",
    "discharge_date",
    "department",
    "diagnosis_code",
    "diagnosis_description",
    "status",
)

BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
BLOOD_TYPE_WEIGHTS = [0.34, 0.06, 0.09, 0.02, 0.04, 0.01, 0.38, 0.07]

GENDERS = ["M", "F", "Other"]
GENDER_WEIGHTS = [0.48, 0.48, 0.04]

DEPARTMENTS = [
    "Urgencias", "UCI", "Medicina Interna", "Cardiologia",
    "Neumologia", "Traumatologia", "Pediatria", "Ginecologia",
    "Oncologia", "Radiologia",
]

# Codigos ICD-10 alineados con la clasificacion triple que nos interesa
DIAGNOSES = [
    ("J18.9", "Pneumonia, unspecified"),
    ("J18.0", "Bronchopneumonia"),
    ("U07.1", "COVID-19"),
    ("J44.9", "Chronic obstructive pulmonary disease"),
    ("I21.9", "Acute myocardial infarction"),
    ("R05", "Cough"),
    ("R50.9", "Fever, unspecified"),
    ("S72.9", "Fracture of femur"),
    ("K35.80", "Acute appendicitis"),
    ("N39.0", "Urinary tract infection"),
]

STATUSES = ["admitted", "discharged", "transferred"]


@dataclass
class PatientRecord:
    external_id: str
    name: str
    birth_date: str
    gender: str
    blood_type: str


@dataclass
class AdmissionRecord:
    patient_external_id: str
    admission_date: str
    discharge_date: str
    department: str
    diagnosis_code: str
    diagnosis_description: str
    status: str


def generate_patients(
    n: int,
    output_path: Path,
    edge_case_ratio: float = 0.05,
    seed: int | None = None,
) -> list[str]:
    """Escribe un CSV de pacientes y devuelve la lista de external_ids generados."""
    rng = random.Random(seed)
    fake = Faker("es_ES")
    if seed is not None:
        Faker.seed(seed)

    records: list[PatientRecord] = []
    external_ids: list[str] = []

    for i in range(n):
        external_id = f"HOSP-{i:06d}"
        birth_date = fake.date_of_birth(minimum_age=5, maximum_age=85)

        record = PatientRecord(
            external_id=external_id,
            name=fake.name(),
            birth_date=birth_date.isoformat(),
            gender=rng.choices(GENDERS, weights=GENDER_WEIGHTS)[0],
            blood_type=rng.choices(BLOOD_TYPES, weights=BLOOD_TYPE_WEIGHTS)[0],
        )

        if rng.random() < edge_case_ratio:
            kind = rng.choice(["null_name", "null_birth", "null_gender", "bad_date"])
            if kind == "null_name":
                record.name = ""
            elif kind == "null_birth":
                record.birth_date = ""
            elif kind == "null_gender":
                record.gender = ""
            elif kind == "bad_date":
                record.birth_date = birth_date.strftime("%d/%m/%Y")

        records.append(record)
        external_ids.append(external_id)

    # Duplicar ~3% cuando los casos borde estan activos para ejercitar la logica de dedup
    if edge_case_ratio > 0 and records:
        n_duplicates = max(1, int(n * 0.03))
        duplicates = rng.sample(records, min(n_duplicates, len(records)))
        records.extend(duplicates)

    _write_csv(output_path, PATIENT_COLUMNS, records)
    logger.info("Generated %d patient rows at %s", len(records), output_path)
    return external_ids


def generate_admissions(
    patient_external_ids: list[str],
    n: int,
    output_path: Path,
    edge_case_ratio: float = 0.05,
    seed: int | None = None,
) -> None:
    """Escribe un CSV de ingresos referenciando los ids de paciente proporcionados."""
    if not patient_external_ids:
        raise ValueError("patient_external_ids must contain at least one id")

    rng = random.Random(seed)
    fake = Faker("es_ES")
    if seed is not None:
        Faker.seed(seed)

    records: list[AdmissionRecord] = []

    for _ in range(n):
        if rng.random() < edge_case_ratio:
            # Referencia huerfana: un paciente que no existe
            patient_ref = f"HOSP-{rng.randint(900_000, 999_999):06d}"
        else:
            patient_ref = rng.choice(patient_external_ids)

        admission_date = fake.date_between(start_date="-2y", end_date="today")
        status = rng.choice(STATUSES)
        discharge = ""
        if status != "admitted":
            days_later = rng.randint(1, 30)
            discharge = (admission_date + timedelta(days=days_later)).isoformat()

        code, description = rng.choice(DIAGNOSES)

        record = AdmissionRecord(
            patient_external_id=patient_ref,
            admission_date=admission_date.isoformat(),
            discharge_date=discharge,
            department=rng.choice(DEPARTMENTS),
            diagnosis_code=code,
            diagnosis_description=description,
            status=status,
        )

        if rng.random() < edge_case_ratio:
            record.admission_date = admission_date.strftime("%d/%m/%Y")

        records.append(record)

    _write_csv(output_path, ADMISSION_COLUMNS, records)
    logger.info("Generated %d admission rows at %s", len(records), output_path)


def _write_csv(output_path: Path, columns: tuple[str, ...], records: list) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic hospital data")
    parser.add_argument("--patients", type=int, default=5000)
    parser.add_argument("--admissions", type=int, default=10000)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--edge-case-ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    patient_ids = generate_patients(
        n=args.patients,
        output_path=args.output_dir / "patients.csv",
        edge_case_ratio=args.edge_case_ratio,
        seed=args.seed,
    )
    admissions_seed = (args.seed + 1) if args.seed is not None else None
    generate_admissions(
        patient_external_ids=patient_ids,
        n=args.admissions,
        output_path=args.output_dir / "admissions.csv",
        edge_case_ratio=args.edge_case_ratio,
        seed=admissions_seed,
    )


if __name__ == "__main__":
    main()
