# ClaimLoop evaluation summary

Splits: ['valid', 'test1'], encounters: 60, profile: budget ({'scribe': 'gpt-5.6-luna', 'coder': 'gpt-5.6-luna', 'resolver': 'gpt-5.6-luna'}), reasoning effort: medium

## Workflow outcomes

| metric | value |
| --- | --- |
| completed runs | 60 of 60 |
| first pass acceptance | 0.8333 |
| final acceptance | 0.9667 |
| denied on first pass | 10 |
| recovered by the denial loop | 8 |
| abandoned | 1 |
| appeals (overturned) | 2 (2) |
| mean attempts | 1.17 |

## First-attempt denials by CARC

| CARC | denials | later fixed |
| --- | --- | --- |
| CO-50 | 8 | 6 |
| CO-150 | 2 | 2 |
| CO-197 | 2 | 2 |

## Note quality (scribe vs ACI-Bench reference)

ROUGE-1 0.5434, ROUGE-2 0.218, ROUGE-L 0.312 (mean F1)

## Cost and latency

Mean tokens per encounter: 7623.2 in / 1962.18 out. Mean wall time 32.53 s.
Batch totals: 457392 input tokens, 117731 output tokens, estimated $0.2328 (prices per backend/pipeline/config.py).