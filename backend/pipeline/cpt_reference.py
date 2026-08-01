"""A deliberately tiny CPT reference for the demo payer.

Licensing note: the full CPT code set is copyrighted by the American Medical
Association and cannot be redistributed in an open repository. This file
carries only a small set of code numbers with paraphrased plain-language
descriptions, which is the standard practice in academic work. A production
system would license the full data set from the AMA.

The medical necessity map below is an illustrative demo policy written for
this project. It is NOT a real payer policy and must not be used for actual
billing decisions.
"""

# cpt -> (paraphrased description, charge in cents, requires prior auth)
FEE_SCHEDULE: dict[str, dict] = {
    # office visits, evaluation and management
    "99202": {"description": "Office visit, new patient, brief", "charge_cents": 11000, "prior_auth": False},
    "99203": {"description": "Office visit, new patient, low complexity", "charge_cents": 14500, "prior_auth": False},
    "99204": {"description": "Office visit, new patient, moderate complexity", "charge_cents": 21000, "prior_auth": False},
    "99205": {"description": "Office visit, new patient, high complexity", "charge_cents": 28000, "prior_auth": False},
    "99212": {"description": "Office visit, established patient, brief", "charge_cents": 6000, "prior_auth": False},
    "99213": {"description": "Office visit, established patient, low complexity", "charge_cents": 9500, "prior_auth": False},
    "99214": {"description": "Office visit, established patient, moderate complexity", "charge_cents": 13500, "prior_auth": False},
    "99215": {"description": "Office visit, established patient, high complexity", "charge_cents": 19000, "prior_auth": False},
    # procedures and imaging
    "20610": {"description": "Aspiration or injection of a major joint", "charge_cents": 8500, "prior_auth": False},
    "73560": {"description": "X-ray of the knee, 1 or 2 views", "charge_cents": 4500, "prior_auth": False},
    "73721": {"description": "MRI of a lower extremity joint, no contrast", "charge_cents": 45000, "prior_auth": True},
    "70551": {"description": "MRI of the brain, no contrast", "charge_cents": 52000, "prior_auth": True},
    "71046": {"description": "Chest X-ray, 2 views", "charge_cents": 5500, "prior_auth": False},
    "93000": {"description": "Electrocardiogram with interpretation", "charge_cents": 4000, "prior_auth": False},
    "96372": {"description": "Therapeutic injection, under the skin or into muscle", "charge_cents": 3000, "prior_auth": False},
    "94010": {"description": "Spirometry, breathing capacity test", "charge_cents": 6000, "prior_auth": False},
    "97110": {"description": "Therapeutic exercise, each 15 minutes", "charge_cents": 5000, "prior_auth": False},
    # labs
    "80053": {"description": "Comprehensive metabolic panel", "charge_cents": 1800, "prior_auth": False},
    "80061": {"description": "Lipid panel", "charge_cents": 2200, "prior_auth": False},
    "85025": {"description": "Complete blood count, automated", "charge_cents": 1500, "prior_auth": False},
    "83036": {"description": "Hemoglobin A1c", "charge_cents": 2000, "prior_auth": False},
    "84443": {"description": "Thyroid stimulating hormone", "charge_cents": 2500, "prior_auth": False},
    "81002": {"description": "Urinalysis without microscope", "charge_cents": 800, "prior_auth": False},
}

EM_CODES = {c for c in FEE_SCHEDULE if c.startswith("99")}

PRIOR_AUTH_REQUIRED = {c for c, v in FEE_SCHEDULE.items() if v["prior_auth"]}

# Illustrative medical necessity policy: a non-E/M procedure is covered only if
# at least one linked diagnosis starts with one of these ICD-10-CM prefixes.
MEDICAL_NECESSITY: dict[str, list[str]] = {
    "20610": ["M17", "M25.5", "M06", "M10", "M1A", "M70", "M75"],
    "73560": ["M17", "M25.5", "M23", "M22", "S83", "S82", "M79.6"],
    "73721": ["M23", "M25.5", "S83", "M17", "M76"],
    "70551": ["G43", "G44", "R51", "S06", "R42"],
    "71046": ["J18", "J44", "J45", "R05", "R07", "I50", "R06"],
    "93000": ["I48", "I10", "I50", "R00", "R07", "R55", "I25"],
    "96372": ["E53", "D51", "M54", "M79", "J45"],
    "94010": ["J44", "J45", "R06", "J43"],
    "97110": ["M54", "M25.5", "M62", "M17", "S83"],
    "80053": ["E11", "E13", "I10", "N18", "K76", "E78", "I50", "Z00"],
    "80061": ["E78", "I10", "E11", "I25", "Z13"],
    "85025": ["D64", "R50", "N39", "Z00", "R53"],
    "83036": ["E11", "E13", "R73"],
    "84443": ["E03", "E05", "R53", "E11"],
    "81002": ["N39", "R30", "R35", "E11"],
}

# Illustrative documentation policy for high level office visits: the payer
# expects the diagnosis list to reflect the visit complexity.
EM_MIN_DIAGNOSES = {
    "99205": 3,
    "99215": 3,
    "99204": 2,
    "99214": 2,
}


def fee_schedule_text() -> str:
    """Render the allowed CPT list for the coder agent's instructions."""
    lines = ["CPT | description | prior auth required"]
    for code, v in FEE_SCHEDULE.items():
        pa = "yes" if v["prior_auth"] else "no"
        lines.append(f"{code} | {v['description']} | {pa}")
    return "\n".join(lines)
