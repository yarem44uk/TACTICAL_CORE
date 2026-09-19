# WO-070B — Human-Reference STT Accuracy Benchmark (WER/CER)

Benchmark-only evidence package. It measures WER/CER of the already-produced
WO-069 Faster-Whisper and Vosk hypotheses against human-entered reference
transcripts taken from the completed WO-068 artifact
`WO-068-HUMAN-REVIEW-EXTENDED.xlsx` (sheet `Human Review`, column `transcript`).

**Accuracy evidence only.** No engine was activated, ranked, selected or wired
into production. No production file, model or dependency is involved.

## Contents

| File | Role |
|---|---|
| `human_reference_transcripts.csv` | reference dataset (67 rows; 61 `HUMAN_VERIFIED`, 6 `NON_AUDIBLE`) |
| `wo069_hypotheses_faster_whisper.jsonl` | byte-identical snapshot of `/opt/data/wo069_runtime/raw_faster_whisper.jsonl` |
| `wo069_hypotheses_vosk.jsonl` | byte-identical snapshot of `/opt/data/wo069_runtime/raw_vosk.jsonl` |
| `wo070b_normalize.py` | `wo070b-normalize-v1` deterministic normalization |
| `wo070b_metrics.py` | `wo070b-levenshtein-v1` WER/CER (benchmark-local, no deps) |
| `wo070b_reference.py` | read-only XLSX → reference CSV builder |
| `wo070b_benchmark.py` | join by `message_id`, score, write outputs |
| `per_message_results.csv` | 122 rows (61 scored records × 2 engines) |
| `aggregate_results.csv` | per-engine sums and WER/CER |
| `wo070b_results.json` | machine-readable roll-up |
| `test_wo070b_benchmark.py` | 23 tests (14 required cases) |
| `WO-070B-STT-ACCURACY-REPORT.md` | the WO-070B required report |

## Reproduce

```bash
# tests
env -u PYTHONPATH PYTHONNOUSERSITE=1 \
  .venv/bin/python -m pytest docs/benchmarks/stt/wo070b -q -p no:cacheprovider

# rebuild the reference CSV from the provisioned workbook (read-only)
.venv/bin/python -c "import os; \
from docs.benchmarks.stt.wo070b import wo070b_reference as R; \
rows = R.build_reference_rows('/opt/data/uploads/1789821219-911209cd/WO-068-HUMAN-REVIEW-EXTENDED.xlsx'); \
R.write_reference_csv(rows, 'docs/benchmarks/stt/wo070b/human_reference_transcripts.csv')"

# rerun the benchmark (writes per_message_results.csv, aggregate_results.csv, wo070b_results.json)
.venv/bin/python -c "import os; \
from docs.benchmarks.stt.wo070b import wo070b_benchmark as B; \
wd='docs/benchmarks/stt/wo070b'; \
B.run(os.path.join(wd,'human_reference_transcripts.csv'), \
      {'faster_whisper': os.path.join(wd,'wo069_hypotheses_faster_whisper.jsonl'), \
       'vosk': os.path.join(wd,'wo069_hypotheses_vosk.jsonl')}, wd)"
```

Expected workbook digest:
`sha256 = 2e4a0bb66a7309a077623bf49935b6493ef607d3dccbc2fe5eb1da342a88296d`, size `16969`.

## Provenance (unchanged, carried)

```
transport_provenance = SYNTHETIC_TOPOLOGY (CubicCore traffic generator v7.19.4; no RF/SDR)
RF_provenance        = UNRESOLVED
real_transmission    = UNRESOLVED  (deliberately not converted to YES/NO)
```

WER/CER here are accuracy measurements of the models against human transcripts;
they do **not** establish that the audio is real radio traffic. That is a separate
CSA decision.
