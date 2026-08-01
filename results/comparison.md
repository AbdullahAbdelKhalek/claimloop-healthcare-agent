# Model tier comparison

Note: profiles may cover different encounter subsets; see each
results/<profile>/eval_config.json. Rates are within-profile.

| metric | budget | balanced |
| --- | --- | --- |
| encounters | 60 | 20 |
| models | gpt-5.6-luna | gpt-5.6-luna / gpt-5.6-terra |
| first pass acceptance | 0.8333 | 0.95 |
| final acceptance | 0.9667 | 1.0 |
| recovered by loop | 8 | 1 |
| mean attempts | 1.17 | 1.05 |
| ROUGE-L (note) | 0.312 | 0.3118 |
| mean seconds/encounter | 32.53 | 26.34 |
| mean cost/encounter | $0.0039 | $0.0213 |
| batch cost | $0.2328 | $0.4262 |