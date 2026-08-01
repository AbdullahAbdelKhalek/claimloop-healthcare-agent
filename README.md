# ClaimLoop

An end-to-end teaching demo of the outpatient medical claims lifecycle, run by
LLM agents: a doctor-patient conversation goes in, and the system writes the
visit note, suggests ICD-10-CM and CPT codes, assembles a claim, submits it to
a simulated payer, reads the denial, and fights back through resubmission or
appeal.

Built as a graduate high-risk project for an AI in Healthcare course, and as a
working answer to a question I kept hearing from people in healthcare
operations: how much of the claims grind can a modern agent stack actually
carry, and where exactly does it break?

Author: Abdullah Abdel-Khalek.

## Why this exists

Claims processing is one of the most expensive administrative workflows in US
healthcare. Between the visit itself and the money arriving, humans transcribe
what happened, translate it into ICD-10-CM diagnoses and CPT procedure codes,
assemble a claim, and then argue with the payer when it comes back denied.
Published benchmarks show that LLMs asked to produce medical codes from memory
get them wrong most of the time, which is exactly why this pipeline treats
coding as a tool-using, verifiable, recoverable process instead of a single
prompt.

The interesting question is not "can a model emit codes" but "can an
instrumented pipeline recover when the payer says no". ClaimLoop makes that
loop observable and measurable.

## The pipeline

```
transcript -> [1 Scribe agent] -> visit note
           -> [2 Coder agent + live ICD-10-CM lookup] -> codes
           -> [3 Claim builder (plain code)] -> FHIR-shaped claim
           -> [4 Mock payer (deterministic rules)] -> accepted or CARC/RARC denial
           -> [5 Denial resolution agent] -> fix and resubmit, prior auth, appeal, or abandon
                 and back to 4, at most three submissions
```

- Agents run on the OpenAI Agents SDK over the Responses API. Orchestration is
  a plain Python loop in `backend/pipeline/orchestrator.py` because the
  workflow order never changes; agents are used only where language
  understanding is needed.
- The coder must verify every diagnosis code against the free NLM Clinical
  Tables ICD-10-CM API before using it.
- The payer is a rules engine, not an LLM. Same claim in, same verdict out.
  It denies with real public CARC/RARC code numbers (CO-16, CO-50, CO-146,
  CO-150, CO-181, CO-197, CO-18) so the denial loop has something real to
  push against.
- The resolution agent can call a mock prior authorization portal, correct
  codes, downcode visits, write an appeal letter, or give up.

## Quickstart

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        (then put your OpenAI API key in .env)
.venv\Scripts\python scripts\fetch_data.py
cd frontend && npm install && npm run build && cd ..
.venv\Scripts\python -m uvicorn backend.app:app --port 8000
```

Open http://localhost:8000, pick an encounter, and watch the claim journey.

Run the tests (offline, no API key needed):

```
.venv\Scripts\python -m pytest backend/tests -q
```

Run the evaluation batch:

```
.venv\Scripts\python scripts\run_eval.py --splits valid --concurrency 4
```

## Data

Encounters come from ACI-Bench (Yim et al., Scientific Data 2023), a public
CC BY 4.0 benchmark of simulated doctor-patient conversations written with
clinician input, distributed through Microsoft's
clinical_visit_note_summarization_corpus repository. `scripts/fetch_data.py`
downloads it at a pinned commit. Per course rules the data itself is never
committed to this repository, and no real patient data is involved anywhere.

Identifiers a claim needs but the dataset does not provide (member IDs, dates
of birth, the provider) are deterministic placeholder stubs derived from the
encounter ID, clearly marked in `backend/pipeline/demographics.py`.

## What the evaluation measures

- First-pass acceptance rate and final acceptance rate after the denial loop
- Which CARC denial categories the resolver can and cannot fix
- Appeal outcomes
- Scribe note quality as ROUGE against the ACI-Bench reference notes
- Tokens and wall time per stage and per encounter

What it deliberately does not claim: clinical correctness of code assignment.
Scoring that would require certified coders and payer-grade ground truth,
which this project does not have. The report is explicit about that boundary.

## Why this is not production ready

This is a readable demo, on purpose. To take something like this to
production you would need, at minimum:

- Real payer connectivity: X12 837/835/277 transactions through a
  clearinghouse, not a JSON mock
- The licensed AMA CPT code set, payer-specific fee schedules, NCCI edits,
  and real coverage policies instead of a tiny illustrative subset
- A human-in-the-loop review queue: coders approve or correct the agent's
  suggestions, nothing goes out the door autonomously
- Eligibility and benefits checks before the visit, not just adjudication after
- HIPAA controls end to end (this demo needs none because it touches no real
  patient data, which was a deliberate design choice)
- Auditability, retention, role-based access, rate limiting, retries, and
  observability beyond per-run JSON files

## Licensing notes

- Code: MIT
- ACI-Bench data: CC BY 4.0, fetched at setup, never redistributed here
- CPT is copyrighted by the American Medical Association. This repository
  contains only a small set of code numbers with paraphrased plain-language
  descriptions for demonstration. A real system licenses the full set.
- CARC/RARC code lists are maintained by X12; descriptions here are paraphrased.

## Disclaimer

Educational demonstration only. Not medical advice, not billing advice, and
not a compliance tool. The payer rules are illustrative fiction.
