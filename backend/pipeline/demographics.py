"""Deterministic demo stubs for the identifiers a claim needs.

ACI-Bench metadata provides patient name, age, and gender, which are already
simulated. Everything else a claim form requires (member ID, date of birth,
provider identity) does not exist in the dataset, so this module derives
stable placeholder values from the encounter ID. Same encounter in, same
stub out, which keeps runs reproducible. These are environment stubs, not
synthetic study data, and the report discloses them.
"""

import re
import zlib

from . import config
from .schemas import Patient, Provider

# The canonical example NPI with a valid check digit, used across HL7 docs.
DEMO_PROVIDER = Provider(name="ClaimLoop Demo Clinic, Family Medicine", npi="1234567893")
DEMO_PAYER_ID = "CLP-DEMO-PAYER"


def _crc(seed: str) -> int:
    return zlib.crc32(seed.encode("utf-8"))


def parse_age(raw) -> int:
    """ACI-Bench ages arrive as '58', '45.0', or '22-month'. Be liberal."""
    s = str(raw if raw is not None else "").strip().lower()
    if not s or s == "nan":
        return 45
    if "month" in s:
        m = re.search(r"\d+", s)
        months = int(m.group()) if m else 12
        return months // 12
    try:
        return max(0, int(float(s)))
    except ValueError:
        return 45


def build_patient(encounter_id: str, meta: dict) -> Patient:
    crc = _crc(encounter_id)
    age = parse_age(meta.get("patient_age"))
    service_year = int(config.SERVICE_DATE.split("-")[0])
    dob_year = service_year - age
    dob_month = crc % 12 + 1
    dob_day = crc % 28 + 1
    first = (meta.get("patient_firstname") or "").strip() or "Sample"
    last = (meta.get("patient_familyname") or "").strip() or "Patient"
    gender = (meta.get("patient_gender") or "unknown").strip().lower()
    return Patient(
        first_name=first,
        last_name=last,
        gender=gender,
        age=age,
        date_of_birth=f"{dob_year:04d}-{dob_month:02d}-{dob_day:02d}",
        member_id=f"MBR{crc % 100_000_000:08d}",
    )
