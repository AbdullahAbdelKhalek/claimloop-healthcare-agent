"""Loads ACI-Bench encounters from the local data directory.

Run scripts/fetch_data.py once to populate data/. The data itself is never
committed to the repository.
"""

from functools import lru_cache

import pandas as pd

from . import config

SPLIT_FILES = {
    "train": "train",
    "valid": "valid",
    "test1": "clinicalnlp_taskB_test1",
    "test2": "clinicalnlp_taskC_test2",
    "test3": "clef_taskC_test3",
}


def data_present() -> bool:
    return (config.ACI_DIR / "challenge_data" / "valid.csv").exists()


@lru_cache(maxsize=None)
def load_split(split: str) -> list[dict]:
    stem = SPLIT_FILES[split]
    base = config.ACI_DIR / "challenge_data"
    df = pd.read_csv(base / f"{stem}.csv")
    meta = pd.read_csv(base / f"{stem}_metadata.csv").set_index("encounter_id")

    encounters = []
    for _, row in df.iterrows():
        eid = row["encounter_id"]
        m = meta.loc[eid].to_dict() if eid in meta.index else {}
        encounters.append({
            "encounter_id": eid,
            "dataset": row.get("dataset", ""),
            "split": split,
            "dialogue": row["dialogue"],
            "note": row["note"],
            "meta": {k: ("" if pd.isna(v) else v) for k, v in m.items()},
        })
    return encounters


def load_encounters(splits: list[str] | None = None) -> list[dict]:
    out = []
    for split in splits or config.SPLITS:
        out.extend(load_split(split))
    return out


def preview(enc: dict) -> dict:
    m = enc["meta"]
    return {
        "encounter_id": enc["encounter_id"],
        "split": enc["split"],
        "dataset": enc["dataset"],
        "chief_complaint": m.get("cc", ""),
        "patient": f"{m.get('patient_firstname', '')} {m.get('patient_familyname', '')}".strip(),
        "age": m.get("patient_age", ""),
        "gender": m.get("patient_gender", ""),
        "dialogue_chars": len(enc["dialogue"]),
    }
