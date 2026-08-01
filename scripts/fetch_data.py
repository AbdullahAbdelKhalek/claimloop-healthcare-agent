"""Downloads the ACI-Bench challenge data into data/ (which is gitignored).

The dataset is CC BY 4.0, published by Microsoft and the ACI-Bench authors in
the clinical_visit_note_summarization_corpus repository. Per course rules the
data is fetched at setup time and never committed or redistributed here.
A commit hash is pinned so every clone gets byte-identical data.

Usage: python scripts/fetch_data.py
"""

import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

PINNED_COMMIT = "293e454917c562361409232f65e9d870a45af026"
BASE = ("https://raw.githubusercontent.com/microsoft/"
        f"clinical_visit_note_summarization_corpus/{PINNED_COMMIT}/data/aci-bench/challenge_data")

FILES = [
    "train.csv", "train_metadata.csv",
    "valid.csv", "valid_metadata.csv",
    "clinicalnlp_taskB_test1.csv", "clinicalnlp_taskB_test1_metadata.csv",
    "clinicalnlp_taskC_test2.csv", "clinicalnlp_taskC_test2_metadata.csv",
    "clef_taskC_test3.csv", "clef_taskC_test3_metadata.csv",
]

LICENSE_NOTE = """ACI-Bench data downloaded from
https://github.com/microsoft/clinical_visit_note_summarization_corpus
at commit {commit}.

License: Creative Commons Attribution 4.0 International (CC BY 4.0).
Citation: Yim et al., "Aci-bench: a Novel Ambient Clinical Intelligence
Dataset for Benchmarking Automatic Visit Note Generation", Scientific Data 2023.

Do not commit or redistribute these files with the project repository.
"""


def main() -> int:
    target = REPO_ROOT / "data" / "aci-bench" / "challenge_data"
    target.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for name in FILES:
            dest = target / name
            if dest.exists():
                print(f"  already present: {name}")
                continue
            url = f"{BASE}/{name}"
            print(f"  downloading {name} ...")
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)

    (REPO_ROOT / "data" / "DATA_LICENSE.txt").write_text(
        LICENSE_NOTE.format(commit=PINNED_COMMIT), encoding="utf-8")

    # quick verification of row counts
    import pandas as pd
    expected_min = {"train.csv": 60, "valid.csv": 15, "clinicalnlp_taskB_test1.csv": 35}
    for name in FILES:
        if name.endswith("metadata.csv"):
            continue
        df = pd.read_csv(target / name)
        print(f"  {name}: {len(df)} encounters")
        if name in expected_min and len(df) < expected_min[name]:
            print(f"  WARNING: {name} has fewer rows than expected")
    print("Done. Data lives in data/ and stays out of git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
