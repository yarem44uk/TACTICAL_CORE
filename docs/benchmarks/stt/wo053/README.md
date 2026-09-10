# WO-053 — STT Benchmark / Dataset Gate (tooling)

This directory holds the WO-053 STT benchmark dataset-gate tooling. It is
**benchmark-only** and offline (stdlib-only, no network, no model download). It
does NOT select a production STT engine and does NOT modify production code.
The production engine decision belongs to **WO-054 / ADR-014**.

See `WO-053-STT-BENCHMARK-REPORT.md` for the full findings and the honest
benchmark-gate state (no engine provisioned locally → benchmark not executed on
real acoustic inference; no real radio speech dataset → dataset gate FAIL).

## Artifacts and SHA-256

| Artifact | Purpose | SHA-256 |
| --- | --- | --- |
| `wo053_normalize.py` | Deterministic transcript normalization (one policy for all candidates) | `2862de4262b56d8c45336482bece9b19c30d7b39fa8ae86766a778eb8f871a5f` |
| `wo053_metrics.py` | WER / CER / exact-match (pure functions) | `b3d7b51e7cc0660e30b865ceaea51395ee2276aa6da14b7289c305cf824353e4` |
| `wo053_dataset.py` | Controlled synthetic dataset generation + manifest build/validate | `ab11cfd1de31c9a46fe2d70b31a2fd9ad478e77e74f60f752ff0b77e47d799bf` |
| `wo053_benchmark.py` | Offline candidate discovery + benchmark gate → JSON | `7a1aa2db506ebbc2df7f5256503faa6caa69b45b9578a01fd5d99da4cad0722a` |
| `wo053_validate_results.py` | Machine-readable result schema + invariant validation | `159fe014b5db65107bb0d6f6c32e0c18c9b34c512cc869cc777e5f28d3910eb8` |
| `wo053_dataset_manifest.csv` | Controlled synthetic dataset manifest | `e2aade957e97f67b1162ee9c44c56c784c9e41607191d7605027279c495955df` |
| `wo053_results.json` | Machine-readable benchmark result | `b442c588b91fcab204a7b16482303c2c8a865d13540bca0fefe082e48cf6b340` |
| `test_wo053_metrics.py` | Normalization + WER/CER mechanics tests | `221fc57355de12d992d9492be5a7d3e0d856bbc2e2a4cb34786d3ae7dbcfb4bd` |
| `test_wo053_dataset.py` | Dataset manifest mechanics tests | `a3ea801297e451f91990523536aadf54d64d58120087e88f1892a6e53d8e85b8` |
| `test_wo053_benchmark.py` | Benchmark runner mechanics tests | `b75208f87a7ab2ccc54ea3dce56db377e53b12245eb469f1c4041fb9c64fb280` |
| `WO-053-STT-BENCHMARK-REPORT.md` | Human-readable benchmark report | `d9c289a3d41f9b66fbae1b3f6bac6d927dc1787b5645ffce31660c11c84bb762` |

External synthetic audio (NOT committed, recorded in the manifest; lives at
`/opt/data/wo053_audio/`):

| audio_id | SHA-256 |
| --- | --- |
| wo053_tone_440.wav | `fbdb8188668684055f8a7cfe482e435b2a30bc5dddff13db26a83866bbf21a34` |
| wo053_tone_1000.wav | `51894d3fc07961f3d56feba56b530a1e0665d355a1f1667434548b522317744d` |
| wo053_tone_880_short.wav | `4c9685020b8990e5d1e6217076787a66e2c260894db5bab929694e9b670275d5` |
| wo053_tone_220.wav | `bfb8f0edf7a1a6f25090413365d84366f13c1517c7b95ed2c16dbb2155bc5b94` |

## Reproduce

Run from the repository root (`/opt/data/tactical_core_github`) with the
project `.venv` Python 3.13.5:

```bash
.venv/bin/python docs/benchmarks/stt/wo053/wo053_dataset.py \
    generate --output-dir /opt/data/wo053_audio \
    --manifest docs/benchmarks/stt/wo053/wo053_dataset_manifest.csv

.venv/bin/python docs/benchmarks/stt/wo053/wo053_dataset.py \
    validate --manifest docs/benchmarks/stt/wo053/wo053_dataset_manifest.csv \
    --audio-dir /opt/data/wo053_audio

.venv/bin/python docs/benchmarks/stt/wo053/wo053_benchmark.py \
    --dataset-manifest docs/benchmarks/stt/wo053/wo053_dataset_manifest.csv \
    --output-json docs/benchmarks/stt/wo053/wo053_results.json

.venv/bin/python docs/benchmarks/stt/wo053/wo053_validate_results.py \
    --results docs/benchmarks/stt/wo053/wo053_results.json

.venv/bin/python -m pytest -q \
    docs/benchmarks/stt/wo053/test_wo053_metrics.py \
    docs/benchmarks/stt/wo053/test_wo053_dataset.py \
    docs/benchmarks/stt/wo053/test_wo053_benchmark.py
```

## Scope boundaries

* **OFFLINE** — no network imports, no model download, no cloud/API call.
* **BENCHMARK-ONLY** — never registers an engine, never alters
  `ITranscriber` / `SttConfig` / `SttWorker` / production audio pipeline.
* **NO PRODUCTION SELECTION** — the report may compare candidates but must not
  select one; that is WO-054 / ADR-014.
* Prior WO-042 / WO-043 / WO-044 / WO-050 / WO-052 artifacts are untouched.
