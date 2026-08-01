# ClaimLoop evaluation summary

Splits: ['valid'], encounters: 20, profile: balanced ({'scribe': 'gpt-5.6-luna', 'coder': 'gpt-5.6-terra', 'resolver': 'gpt-5.6-terra'}), reasoning effort: medium

## Workflow outcomes

| metric | value |
| --- | --- |
| completed runs | 20 of 20 |
| first pass acceptance | 0.95 |
| final acceptance | 1.0 |
| denied on first pass | 1 |
| recovered by the denial loop | 1 |
| abandoned | 0 |
| appeals (overturned) | 0 (0) |
| mean attempts | 1.05 |

## First-attempt denials by CARC

| CARC | denials | later fixed |
| --- | --- | --- |
| CO-150 | 1 | 1 |

## Note quality (scribe vs ACI-Bench reference)

ROUGE-1 0.548, ROUGE-2 0.2237, ROUGE-L 0.3118 (mean F1)

## Cost and latency

Mean tokens per encounter: 6180.7 in / 1696.15 out. Mean wall time 26.34 s.
Batch totals: 123614 input tokens, 33923 output tokens, estimated $0.4262 (prices per backend/pipeline/config.py).