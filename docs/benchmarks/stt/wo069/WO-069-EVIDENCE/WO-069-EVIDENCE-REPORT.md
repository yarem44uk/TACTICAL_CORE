# WO-069 — REAL RADIO STT BENCHMARK (CONTROLLED RE-ENTRY)

**Work Order:** WO-069  
**Generated (UTC):** 2026-09-19T08:48:38.310574+00:00  
**Repository HEAD:** `b5712b08d440e683e2f9af3cdceb353175d9eb99`  
**Status:** BENCHMARK EXECUTED

---

## BLUF

67 of 67 human-reviewed real-radio message records were located and integrity-verified read-only (136.36 s total audio). 2 candidate engines were exercised on the identical dataset. Reference transcripts available: 0 — so WER/CER are `NOT_MEASURED`, and the benchmark carries measured runtime, resource and reliability evidence only. **No production engine is selected.**

## 1. Dataset

- dataset root: `/opt/data/wo068_real_radio_stt_benchmark_v1`
- records expected / actual: 67 / 67 (COMPLETE)
- WAV present + integrity-verified: 67
- total audio duration: 136.36 s
- human-reviewed rows: 61 (pending 6)
- human review source: `/opt/data/uploads/1789807255-6bf70d4b/human_review.csv` (sha256 `21c470b613f1df215b2e71bd154e4237a19462293d68af43aa29a362320af1e5`)
- dataset manifest sha256: `ca6d260e0fc27ceddda30003d8b8eea9fc74ab5649de8ec70bdce067b5dafc36`
- reference transcripts: UNAVAILABLE (0) — the human listening review records categorical listening labels only (audible_voice/intelligible/voice_type/...); it carries no verbatim transcript for any message
- reference callsigns: UNAVAILABLE (0)

### 1.1 Artifact resolution (named vs present)

- work order names `WO-068-HUMAN-REVIEW-EXTENDED.xlsx` — found in environment: **False**
- dataset manifest present: True
- ground-truth sidecar present: True
- human-review CSV present: True

## 2. Environment

- python: 3.13.5  
- os: Linux-6.12.48+deb13-cloud-amd64-x86_64-with-glibc2.41  
- kernel: 6.12.48+deb13-cloud-amd64  
- cpu: INTEL(R) XEON(R) PLATINUM 8568Y+ (8 cores)  
- ram: 16774946816 bytes; cgroup memory.max: 4294967296  
- gpu: NOT_AVAILABLE (nvidia-smi not found)  
- dataset hash: `e0f2b39eea6bb4c87f5fd4adcf23bd35116fd37de86fb062d7569a7a054e52d9`

## 3. Engines — measured results

### faster_whisper

- engine_status: **COMPLETED**
- model: `/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/faster_whisper`
- device / compute_type: cpu / int8
- sample-rate policy: native 8 kHz (engine decodes natively)
- cold start (model load): 1162.0 ms
- exit code: 0
- success / failed / timeout: 67 / 0 / 0
- failure rate: 0.0
- median latency: 2.590306 s; p95: 7.065627 s
- median RTF: 1.611679; p95 RTF: 7.297067
- peak RSS: 1278345216 bytes; cpu user total: 371.32 s
- WER: NOT_MEASURED (scored candidates: 0)
- CER: NOT_MEASURED
- callsign accuracy: NOT_MEASURED (NOT_MEASURED)
- SPEECH_PRESENCE_DIAGNOSTIC (not a WER substitute): audible=YES with output 59/61; audible=NO with empty output 1/6

### vosk

- engine_status: **COMPLETED**
- model: `/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/vosk_uk/vosk-model-uk-v3`
- device / compute_type: cpu / 
- sample-rate policy: deterministic linear 8 kHz -> 16 kHz upsample (model hard-codes 16 kHz); original 8 kHz WAV is the input of record
- cold start (model load): 2543.162 ms
- exit code: 0
- success / failed / timeout: 67 / 0 / 0
- failure rate: 0.0
- median latency: 0.147892 s; p95: 0.908192 s
- median RTF: 0.098067; p95 RTF: 0.188797
- peak RSS: 1439416320 bytes; cpu user total: 17.03 s
- WER: NOT_MEASURED (scored candidates: 0)
- CER: NOT_MEASURED
- callsign accuracy: NOT_MEASURED (NOT_MEASURED)
- SPEECH_PRESENCE_DIAGNOSTIC (not a WER substitute): audible=YES with output 52/61; audible=NO with empty output 5/6

## 4. WER/CER measurement (WO-069-CORRECTIVE)

- WER_STATUS: **NOT_MEASURABLE**
- CER_STATUS: **NOT_MEASURABLE**
- REFERENCE_SOURCE: `human_review_artifact:transcript`
- HYPOTHESIS_SOURCE: `engine_run_ledger:record.text (raw, unmodified)`
- NORMALIZATION_POLICY: `wo069-normalization-v1`
- reference transcripts available: 0/67
- **faster_whisper** — evaluated_records: 0/67; WER: NOT_MEASURED (NOT_MEASURABLE); CER: NOT_MEASURED (NOT_MEASURABLE); excluded: 67 (no reference 67, no hypothesis 0)
- **vosk** — evaluated_records: 0/67; WER: NOT_MEASURED (NOT_MEASURABLE); CER: NOT_MEASURED (NOT_MEASURABLE); excluded: 67 (no reference 67, no hypothesis 0)

Excluded records: every dataset record is excluded with the explicit reason `EXCLUDED_NO_HUMAN_REFERENCE_TRANSCRIPT`, because the human-review artifact carries no verbatim transcript for any message. No WER/CER value is estimated.

## 5. Failures and timeouts

- none: every executed engine completed without a per-file failure.

## 6. Production architecture

- benchmark layer is isolated: no EventFactory / EventPipeline / Observation / journal / Operator Wall involvement, no production STT seam change.
- production engine selected: **NO** (ADR-014 Part 2 remains a CSA decision).

## 7. Evidence files

- `benchmark_results.csv`
- `transcript_comparison.csv`
- `callsign_results.csv`
- `runtime_metrics.csv`
- `resource_metrics.csv`
- `environment_manifest.json`
- `dataset_manifest.json`
- `benchmark_results.json`
- `wer_cer_results.csv`
- `wer_cer_summary.csv`
- `wer_cer_normalization.json`
- `wer_cer_diagnostic.json`
- `hypothesis_availability_matrix.csv`

---

_Generated by the WO-069 benchmark layer at 2026-09-19T09:01:11.038019+00:00._
