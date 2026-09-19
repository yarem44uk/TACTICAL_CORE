# WO-070A — CSA STT Engine Selection Evidence Package

**Branch:** `wo-070a-csa-stt-engine-selection`
**Baseline:** `main` = `4cddf848fa2ff959a13817002d684ee5320e06c1` (WO-066)
**Status:** EVIDENCE COLLECTION COMPLETE — CSA DECISION PENDING
**Author:** Senior Software Engineer / AI Engineer (evidence-collection role)
**Date:** 2026-09-19

---

## Scope and neutrality statement

This document is an **evidence package**, not a decision. It evaluates the three
permitted outcomes — `faster_whisper`, `vosk`, `NO PRODUCTION STT ENGINE
AUTHORIZED` — **neutrally**.

* No engine is selected, ranked, scored, weighted, or recommended.
* No winner, no traffic-light grading, no A/B/C grade, no overall score.
* No production STT code, seam, configuration, or registration is changed.
* No model is downloaded, installed, or activated.
* WO-069 raw engine output is reported as execution evidence only, and is **not**
  converted into an accuracy or production-suitability claim.

The Chief Systems Architect (CSA) remains the sole decider. The decision record
at the end of this document is intentionally left unfilled.

---

## 0. Evidence sources inspected (read-only)

| Source | Location | Nature |
| --- | --- | --- |
| ADR-014 | `docs/adr/ADR-014-Real-Acoustic-STT-Engine-Selection-and-Benchmark-Gate.md` | Architecture decision (Part 1 Accepted; Part 2 DEFERRED) |
| WO-053 report | `docs/benchmarks/stt/wo053/WO-053-STT-BENCHMARK-REPORT.md` | Benchmark infrastructure gate |
| Dataset report | `docs/benchmarks/stt/STT-DATASET-REPORT.md` (WO-041) | Dataset gate |
| Engine benchmark report | `docs/benchmarks/stt/STT-ENGINE-BENCHMARK-REPORT.md` (WO-040) | Engine selection evidence gate |
| WO-069 evidence | `docs/benchmarks/stt/wo069/WO-069-EVIDENCE/*` (branch `wo-069-real-radio-stt-benchmark`, `3c4f4be`) | Executed benchmark evidence |
| WO-069 README | `docs/benchmarks/stt/wo069/README.md` | Scope/provenance |
| WO-067 README | `docs/benchmarks/stt/wo067/README.md` | Tooling + provenance |
| WO-068 report | `/opt/data/wo068_real_radio_stt_benchmark_v1/reports/WO-068-BENCHMARK-REPORT.md` | Dataset construction + provenance |
| WO-070 blocker | `docs/work_orders/WO-070-PRODUCTION-STT-ADAPTER-BLOCKED.md` | Production adapter blocker |
| Seam | `backend/app/contracts/audio.py`, `backend/app/audio/stt_seam.py`, `stt_config.py`, `stt_worker.py` | Authoritative production STT seam |
| Human review | `/opt/data/uploads/1789820496-ed09a6b7/human_review.csv` (sha256 `21c470b6…`) | Human listening artifact |
| Ground-truth sidecar | `/opt/data/wo068_real_radio_stt_benchmark_v1/dataset/ground_truth/ground_truth.json` | Empty template |
| Runtime probe | repo venv + `/opt/data/wo067_runtime_gate_v1/venv` | Live environment facts |

### 0.1 Forensic gate (executed before any change)

```text
git status --short
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500

git branch --show-current   -> wo-070-production-stt-adapter
git rev-parse HEAD          -> 873d108da0b86eb2b9469341497d6a2c36f4b6fa   (WO-070 blocker)
git rev-parse origin/main   -> 4cddf848fa2ff959a13817002d684ee5320e06c1   (WO-066)
git remote -v               -> origin git@github.com:yarem44uk/TACTICAL_CORE.git
```

Repository identity and baseline matched the WO preamble. `?? 500` and the
pre-existing `__pycache__` modification were left untouched (not reset, cleaned,
restored, or staged). The branch was created from the baseline `origin/main`
(`4cddf84`) so `git diff origin/main...HEAD` contains only this document.

---

## 1. Runtime availability (probed, no install)

| Fact | Value |
| --- | --- |
| Python (repo venv `/opt/data/tactical_core_github/.venv`) | 3.13.5 |
| Python (system) | 3.13.5 |
| `faster_whisper` importable — repo venv | **NO** (`find_spec` → None) |
| `vosk` importable — repo venv | **NO** |
| `ctranslate2` importable — repo venv | **NO** |
| `faster_whisper` importable — engine runtime venv `/opt/data/wo067_runtime_gate_v1/venv` | **YES** |
| `vosk` importable — engine runtime venv | **YES** |
| Registered STT engine factories (`stt_seam._ENGINE_FACTORIES`) | **`{}` (EMPTY)** |
| Recognised engines (`SUPPORTED_ENGINES`) | `faster_whisper`, `vosk` |
| Local models present | `faster_whisper`, `vosk_uk`, `vosk_en`, `vosk_ru` under `/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/` |
| Probed package versions (engine venv) | `faster-whisper==1.2.1`, `ctranslate2==4.8.2`, `vosk==0.3.45`, `numpy==2.5.3`, `onnxruntime==1.30.0` |

**Interpretation (fact):** neither engine is importable in the *repository*
venv; both are importable in the *dedicated benchmark runtime* venv. Per §10 of
the work order, "AVAILABLE IN RUNTIME = NO" in the repository venv is an
**environment fact only** — it does not by itself mean `PRODUCTION ENGINE = NO`.

---

## 2. Historical engine evidence — Faster-Whisper

Source: WO-069 `environment_manifest.json`, `benchmark_results.csv`,
`runtime_metrics.csv`, `resource_metrics.csv`, `WO-069-EVIDENCE-REPORT.md`;
WO-053/WO-040 reports; ADR-014.

| Item | Value / status | Evidence |
| --- | --- | --- |
| In repository dependency manifests | NOT PRESENT in the repository venv (WO-040 §8: "NOT INSTALLED") | WO-040 report |
| In current runtime | Not importable in repo venv; importable in `/opt/data/wo067_runtime_gate_v1/venv` (1.2.1) | Runtime probe |
| Model(s) referenced | `/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/faster_whisper` | `environment_manifest.json` |
| Model revision/hash documented | `model_version = "SHA256SUMS"`; `model_revision = "bundled (WO-067 OFFLINE-BUNDLE)"`. **Per-file digest value NOT AVAILABLE** in the evidence set (only the `SHA256SUMS` manifest is referenced). Bundle-level sha256 `8f023ea8…` recorded by WO-068. | `environment_manifest.json`, WO-068 §6 |
| Model size | `486,216,320` bytes | `environment_manifest.json` |
| CPU/GPU requirements documented | `device = cpu`, `compute_type = int8`; GPU `NOT_AVAILABLE` on host | `environment_manifest.json` |
| Quantization/options | `compute_type=int8` | `environment_manifest.json` |
| Language support | language auto-detect (`language = null`, recorded) | `environment_manifest.json` |
| Decoding configuration | native 8 kHz input (engine decodes natively, no resample) | `WO-069-EVIDENCE-REPORT.md` §3 |
| WO-069 execution result | `engine_status = COMPLETED`, exit code 0 | `benchmark_results.csv` |
| Non-empty hypotheses | **64 / 67** (3 records produced empty output) | `wer_cer_summary.csv`, `hypothesis_availability_matrix.csv` |
| Failure count | 0 failed, 0 timeouts, failure rate 0.0 (success 67/0/0); 3 empty outputs are not failures | `WO-069-EVIDENCE-REPORT.md` §3/§5 |
| Latency evidence | median 2.590306 s; p95 7.065627 s | `WO-069-EVIDENCE-REPORT.md` §3 |
| RTF evidence | median 1.611679; p95 7.297067 | `WO-069-EVIDENCE-REPORT.md` §3 |
| Memory evidence | peak RSS `1,278,345,216` bytes; CPU user total 371.32 s | `resource_metrics.csv` |
| Cold start | 1162.0 ms | `runtime_metrics.csv` |
| Accuracy evidence | **NOT MEASURED** — no reference transcript exists | `wer_cer_summary.csv` |
| Limitations | accuracy unmeasurable (no ground truth); ~2.6 s floor latency even on 0.18 s clips (RTF up to 13.4 on shortest clips); 1 raw hypothesis on a human-`NO`/`NON_SPEECH` clip read "Thank you for watching!" (raw engine output, displayed as-is, not adjudicated) | `runtime_metrics.csv`, `transcript_comparison.csv` |
| Reproducibility | engine/model/python/kernel/dataset hash recorded; per-file model hash NOT AVAILABLE | `environment_manifest.json` |

The WO-069 number **64/67 is a hypothesis-availability count, not an accuracy
figure** and is recorded as such.

---

## 3. Historical engine evidence — Vosk

Source: as above.

| Item | Value / status | Evidence |
| --- | --- | --- |
| In repository dependency manifests | NOT PRESENT in the repository venv (WO-040 §8: "NOT INSTALLED") | WO-040 report |
| In current runtime | Not importable in repo venv; importable in `/opt/data/wo067_runtime_gate_v1/venv` (0.3.45) | Runtime probe |
| Model(s) referenced | `/opt/data/wo067_rebuild/OFFLINE-BUNDLE/models/vosk_uk/vosk-model-uk-v3` | `environment_manifest.json` |
| Model version/hash documented | `model_version = "UNKNOWN"`; `model_revision = "vosk-model-uk-v3"`. **Digest NOT AVAILABLE.** | `environment_manifest.json` |
| Model size | `1,040,586,413` bytes | `environment_manifest.json` |
| CPU/GPU requirements documented | `device = cpu`; GPU `NOT_AVAILABLE` | `environment_manifest.json` |
| Language support | `language = "uk"` (uk-specific model) | `environment_manifest.json` |
| Sample-rate handling | **Native 8 kHz FAILS** (`conf/mfcc.conf` hardcodes `sample-frequency=16000`); deterministic linear 8 kHz→16 kHz upsample decodes `rc=0`. Original 8 kHz WAV remains input of record, never modified. | WO-067 findings (carried in WO-068 §4.1), `WO-069-EVIDENCE-REPORT.md` §3 |
| WO-069 execution result | `engine_status = COMPLETED`, exit code 0 | `benchmark_results.csv` |
| Non-empty hypotheses | **53 / 67** (14 records produced empty output) | `wer_cer_summary.csv`, `hypothesis_availability_matrix.csv` |
| Failure count | 0 failed, 0 timeouts, failure rate 0.0 (success 67/0/0) | `WO-069-EVIDENCE-REPORT.md` §3/§5 |
| Latency evidence | median 0.147892 s; p95 0.908192 s | `WO-069-EVIDENCE-REPORT.md` §3 |
| RTF evidence | median 0.098067; p95 0.188797 | `WO-069-EVIDENCE-REPORT.md` §3 |
| Memory evidence | peak RSS `1,439,416,320` bytes; CPU user total 17.03 s | `resource_metrics.csv` |
| Cold start | 2543.162 ms | `runtime_metrics.csv` |
| Accuracy evidence | **NOT MEASURED** — no reference transcript exists | `wer_cer_summary.csv` |
| Limitations | accuracy unmeasurable; requires 8→16 kHz preprocessing; RU/EN catalogue models known RESOURCE-LIMITED at 4 GiB (rc=137) from WO-067; uk model only | WO-067/WO-068 |
| Reproducibility | engine/model/python/kernel/dataset hash recorded; per-file model hash NOT AVAILABLE | `environment_manifest.json` |

The WO-069 number **53/67 is a hypothesis-availability count, not an accuracy
figure**.

---

## 4. WER / CER

```text
Human reference transcript count : 0 / 67
WER                              : NOT MEASURABLE
CER                              : NOT MEASURABLE
```

Confirmed independently from WO-069 evidence:

* `wer_cer_summary.csv` → both engines: `records_with_reference = 0`,
  `evaluated_records = 0`, `excluded_records = 67`,
  `wer_status = cer_status = NOT_MEASURABLE`.
* `wer_cer_diagnostic.json` → `reference_source = human_review_artifact:transcript`,
  `reference_transcripts_available = 0`, engine hypotheses 64/53.
* Exclusion reason (machine-readable): `EXCLUDED_NO_HUMAN_REFERENCE_TRANSCRIPT`.

**This is an evidence state, not a failure.** No reference transcript was
invented, no engine output was used as a reference, no callsign was used to
repair a transcript, and no pseudo-ground-truth was generated from categorical
human labels or confidence.

---

## 5. Human-review evidence — listening vs accuracy ground truth

Artifact: `/opt/data/uploads/1789820496-ed09a6b7/human_review.csv`
(sha256 `21c470b613f1df215b2e71bd154e4237a19462293d68af43aa29a362320af1e5`,
byte-identical to the WO-069 source file). 67 rows; 61 `REVIEWED`, 6 `PENDING`.

| Field present | Value |
| --- | --- |
| human transcript | **ABSENT** — no verbatim transcript column exists |
| callsign | **ABSENT** |
| intelligibility | PRESENT (`intelligible`: YES/NO) |
| audible voice | PRESENT (`audible_voice`: YES/NO) |
| radio style | PRESENT (`radio_style`: YES/NO/UNCERTAIN) |
| speaker category | PRESENT (`speaker`: UNKNOWN; `voice_type`: FEMALE/NONE) |
| confidence | PRESENT (`confidence`: HIGH/…) |
| reviewer identity | PRESENT (`reviewer`: e.g. `OLEH`) |
| provenance fields | `message_id`, `stream_id`, `start_time`, `end_time`, `duration_ms` |

**Classification:** this is **human listening evidence** (categorical
observations), **not** engine-accuracy ground truth. Human-entered text is not
promoted into a validated operational callsign, and reviewer confidence is not
treated as STT accuracy.

### 5.1 WO-068-HUMAN-REVIEW-EXTENDED.xlsx

```text
STATUS = EVIDENCE NOT RUNTIME-AVAILABLE
```

A runtime search found **no** `WO-068-HUMAN-REVIEW-EXTENDED.xlsx` anywhere under
`/opt/data`. Absence from the runtime is **not** evidence the artifact does not
exist, and it was not copied into Git, reconstructed, or used to derive WER/CER.
WO-069's own `dataset_manifest.json` records `named_artifact_found: false`.

### 5.2 Documentation contradiction (reported, not resolved)

`docs/benchmarks/stt/wo067/README.md` asserts the audio is *"Human speech —
confirmed by the CSA human listening review of the WO-067-PRE-04 package."* The
WO-067-PRE-04 package itself records `human_confirmed: 0` and all rows `PENDING`
(WO-068 §2.2). One statement is wrong. It is material to provenance and is
recorded here for CSA resolution.

---

## 6. Real-radio provenance

| Dimension | Classification | Basis |
| --- | --- | --- |
| RF provenance | **UNAVAILABLE** | WO-068 §2.1: "No RF/SDR provenance. No real radio capture." |
| Transport provenance | **VERIFIED (synthetic)** | CubicCore traffic generator v7.19.4 over a simulated L2/L3 topology; pickup PCAP `0c9a0716…eb20` byte-identical to a previously rejected synthetic fixture |
| Source identity | **PARTIALLY VERIFIED** | `stream_id` S1 (44) / S2 (23) recorded; field identity beyond the stream id NOT AVAILABLE |
| Recording chain | **PARTIALLY VERIFIED** | PCAP → RTP-timing-preserving master WAV → byte-exact candidate slice (WO-068 §2); not an RF capture chain |
| Capture conditions | **UNKNOWN** | no documented source/channel/noise/speaker conditions |
| `real_transmission` flag | **UNRESOLVED** for all 67 | `dataset/manifest.csv` |

Provenance was not inferred from filenames, and RF provenance was not inferred
from RTP presence. WO-068 independently reached the same position; WO-053
recorded `REAL TRANSMISSIONS IN DATASET: 0`.

---

## 7. Resource / deployment evidence

| Fact | Value | Source |
| --- | --- | --- |
| Kernel | `6.12.48+deb13-cloud-amd64` | WO-069 env manifest / live probe |
| CPU | INTEL(R) XEON(R) PLATINUM 8568Y+, 8 cores | WO-069 env manifest |
| RAM | 16,774,946,816 bytes (~15.6 GiB) | WO-069 env manifest |
| cgroup memory.max | `4,294,967,296` (4 GiB) | WO-069 env manifest (re-confirmed from WO-067/WO-068) |
| GPU | `NOT_AVAILABLE` (`nvidia-smi` not found) | WO-069 env manifest |
| VRAM | `NOT_AVAILABLE` | WO-069 env manifest |

Per-engine measured resource facts (from WO-069, on this exact host):

| Metric | Faster-Whisper | Vosk |
| --- | --- | --- |
| Model footprint (on disk) | 486,216,320 bytes | 1,040,586,413 bytes |
| Cold start | 1162.0 ms | 2543.162 ms |
| Peak RSS (run) | 1,278,345,216 bytes | 1,439,416,320 bytes |
| CPU user total (67 files) | 371.32 s | 17.03 s |
| GPU/VRAM | NOT AVAILABLE | NOT AVAILABLE |
| Offline operation | VERIFIED (local bundle) | VERIFIED (local bundle) |
| Long-run / continuous footprint | UNKNOWN | UNKNOWN |

Known resource limits carried forward from WO-067: vosk RU (`vosk-model-ru-0.42`)
and EN (`vosk-model-en-us-0.22`) catalogue models were **RESOURCE-LIMITED at the
4 GiB cgroup cap** (`rc=137`, OOM). Vosk uk (`vosk-model-uk-v3`) ran within the
cap in WO-069. WO-070A did not re-run any memory test and did not estimate any
value.

---

## 8. Operational requirements (evidence-only)

Allowed states: SUPPORTED BY EVIDENCE / NOT TESTED / UNKNOWN.

| Requirement | Faster-Whisper | Vosk |
| --- | --- | --- |
| Ukrainian speech | Ukrainian accuracy NOT TESTED (language auto-detect; no reference). | Ukrainian *model provisioned* (`vosk-model-uk-v3`); accuracy NOT TESTED. |
| Radio speech | NOT TESTED (transport synthetic) | NOT TESTED (transport synthetic) |
| Noisy audio | NOT TESTED | NOT TESTED |
| Short transmissions | input range 0.18–8.72 s processed (coverage VERIFIED); accuracy NOT TESTED | same (coverage VERIFIED); accuracy NOT TESTED |
| Variable speakers | speaker identity mostly `UNKNOWN`; vocalisation categories FEMALE/NONE only → UNKNOWN | same → UNKNOWN |
| Callsign-like speech | NOT TESTED (0 reference callsigns) | NOT TESTED (0 reference callsigns) |
| 8 kHz mono PCM | native 8 kHz decode VERIFIED to run (rc=0) | native 8 kHz FAILS (mismatch); 8→16 kHz upsample VERIFIED to run |
| Offline operation | SUPPORTED BY EVIDENCE (ran from local bundle, no network) | SUPPORTED BY EVIDENCE |
| CPU-only operation | SUPPORTED BY EVIDENCE (`device=cpu`, no GPU present) | SUPPORTED BY EVIDENCE |
| Continuous operation | NOT TESTED (single 67-file pass) | NOT TESTED |
| Fail-closed behaviour | production seam fail-closed VERIFIED; adapter-level NOT TESTED (no adapter) | same |

No engine is claimed to perform well in any category; anything without direct
evidence is `NOT TESTED` or `UNKNOWN`.

---

## 9. Architectural compatibility with the existing seam

The production STT subsystem is an **engine-neutral seam, not a running engine**
(ADR-014 Part 1). `ITranscriber` is the Core contract:
`model` property, `transcribe(audio_data: bytes, language=None) -> str`,
`is_ready() -> bool`. `AbstractSttAdapter` adds the offline `initialize(config)`
lifecycle hook behind the adapter boundary. `build_transcriber(config)` validates
config and the local model path, then dispatches via `_ENGINE_FACTORIES`;
`_ENGINE_FACTORIES` is **empty**, so a recognised engine raises
`SttEngineUnavailableError` — there is **no silent fallback** to
`DeterministicTestTranscriber`.

| Question | Faster-Whisper | Vosk |
| --- | --- | --- |
| Can it be implemented behind the existing seam? | **YES** (recognised identifier; `AbstractSttAdapter` subclass) | **YES** |

The adapter boundary that is definable **without selecting an engine**:

* **Boundary:** a subclass of `AbstractSttAdapter` registered via
  `register_engine(engine_id, factory)`; the Core depends only on `ITranscriber`.
* **Input:** the seam's `transcribe(audio_data: bytes, language)` receives PCM
  bytes from the finalized WAV master (8 kHz mono PCM16), opened read-only.
* **Output mapping:** a `str` transcript; empty/no-speech must map to the
  contract-defined empty representation — never fabricated text.
* **Error handling:** missing/invalid audio, model unavailable, init failure,
  inference exception, timeout, and malformed engine result must fail closed
  (never converted into a successful empty transcript).
* **Initialization:** `initialize(config)` validates the local model exists
  (`SttConfig`/`resolve_model_path`, path-traversal guarded) and transitions to
  ready; no network, no download.
* **Lifecycle:** the existing bounded `SttWorker` daemon-thread queue owns
  submission/back-pressure; the adapter must not spawn an unbounded or permanent
  worker.
* **Configuration:** the existing `SttConfig` (`enabled`, `engine`, `model_path`,
  `language`, `device`, `model_root`); no second configuration system.

**No contract change is proposed or required** to define this boundary.

---

## 10. Security / offline requirements

| Requirement | Status |
| --- | --- |
| Offline model availability | VERIFIED — models provisioned locally in the OFFLINE-BUNDLE (bundle sha256 `8f023ea8…`) |
| Runtime network requirement | NO network used by WO-069 execution; the production seam's `resolve_model_path` never reaches the network |
| Automatic model download behaviour | Production seam: **none** — a missing model fails clearly (`SttConfigError`), no fallback download |
| External telemetry | UNKNOWN (not documented anywhere) |
| Credentials / API keys | NONE documented (no key/endpoint referenced) |
| Supply-chain dependencies | pinned versions recorded: `faster-whisper 1.2.1`, `ctranslate2 4.8.2`, `vosk 0.3.45`, `numpy 2.5.3`, `onnxruntime 1.30.0`, `cffi 2.1.1`, `av 18.1.0`, `tokenizers 0.23.2` |

Only documented facts are reported; nothing is speculated.

---

## 11. Reproducibility

| Item | Faster-Whisper | Vosk |
| --- | --- | --- |
| Engine version | 1.2.1 (ctranslate2 4.8.2) | 0.3.45 |
| Model version | `SHA256SUMS` (bundled) | `UNKNOWN` / `vosk-model-uk-v3` |
| Model hash/revision | NOT AVAILABLE (per-file digest not captured) | NOT AVAILABLE |
| Python version | 3.13.5 | 3.13.5 |
| OS / kernel | Debian 13 / `6.12.48+deb13-cloud-amd64` | same |
| Dependency versions | recorded (see §10) | recorded (see §10) |
| Configuration | `cpu`, `int8`, language auto-detect, native 8 kHz | `cpu`, language `uk`, 8→16 kHz upsample |
| Input dataset hash | `e0f2b39eea6bb4c87f5fd4adcf23bd35116fd37de86fb062d7569a7a054e52d9` | same |
| Number of samples | 67 | 67 |
| Benchmark command | `python docs/benchmarks/stt/wo069/wo069_cli.py run --workdir /opt/data/wo069_runtime --evidence-dir …` | same |

Missing values are marked NOT AVAILABLE; none were reconstructed.

---

## 12. Decision matrix

Allowed states only. No ranking, no score, no winner column.

| Criterion | Faster-Whisper | Vosk | Evidence Source | Evidence Status |
| --- | --- | --- | --- | --- |
| Runtime availability (repo venv) | UNAVAILABLE | UNAVAILABLE | Runtime probe | VERIFIED |
| Runtime availability (engine venv) | AVAILABLE | AVAILABLE | Runtime probe | VERIFIED |
| WO-069 execution | COMPLETED (rc 0) | COMPLETED (rc 0) | `benchmark_results.csv` | VERIFIED |
| Non-empty hypotheses | 64/67 | 53/67 | `wer_cer_summary.csv` | VERIFIED |
| Human-reference transcripts | 0 | 0 | `wer_cer_summary.csv` | NOT AVAILABLE |
| WER | NOT MEASURED | NOT MEASURED | `wer_cer_diagnostic.json` | NOT MEASURED |
| CER | NOT MEASURED | NOT MEASURED | `wer_cer_diagnostic.json` | NOT MEASURED |
| Real-radio provenance | UNRESOLVED | UNRESOLVED | `dataset/manifest.csv`, WO-068 | UNKNOWN |
| Ukrainian evaluation | NOT TESTED | NOT TESTED (uk model provisioned) | WO-069 | NOT MEASURED |
| Radio-noise evaluation | NOT TESTED | NOT TESTED | WO-068 §2.1 | NOT MEASURED |
| 8 kHz evaluation | native 8 kHz ran | native fails; 16 kHz upsample ran | WO-067/WO-069 | PARTIALLY VERIFIED |
| CPU-only evidence | VERIFIED | VERIFIED | env manifest | VERIFIED |
| Memory evidence | peak RSS 1.278 GB | peak RSS 1.439 GB | `resource_metrics.csv` | VERIFIED |
| Latency evidence | median 2.590 s | median 0.148 s | `runtime_metrics.csv` | VERIFIED |
| RTF evidence | median 1.612 | median 0.098 | `runtime_metrics.csv` | VERIFIED |
| Offline operation | VERIFIED | VERIFIED | env manifest | VERIFIED |
| Model reproducibility | partial (per-file hash NOT AVAILABLE) | partial (digest NOT AVAILABLE) | env manifest | PARTIALLY VERIFIED |
| Dependency reproducibility | versions recorded | versions recorded | env manifest | PARTIALLY VERIFIED |
| Existing seam compatibility | YES (not implemented) | YES (not implemented) | `stt_seam.py` | BLOCKED (no adapter) |
| Production integration readiness | BLOCKED | BLOCKED | ADR-014 Part 2, WO-070 | BLOCKED |
| Known blockers | no ground truth; provenance unresolved; engine not registered | same + 8→16 kHz preprocessing | WO-068/WO-069/WO-070 | BLOCKED |

---

## 13. CSA decision options

The mandatory gate (ADR-014) is **not satisfied**: no ground truth, no verified
real-radio provenance, and WER/CER NOT MEASURABLE. Presenting the three permitted
outcomes does not select among them.

### OPTION A — AUTHORIZE faster_whisper

* **Evidence supporting the option:** runs offline on CPU at int8; WO-069
  COMPLETED 67/67 with 0 failures; native 8 kHz accept; measured latency/RTF/RSS;
  recognised engine identifier; adapter definable behind the existing seam.
* **Evidence missing:** any accuracy measure (WER/CER NOT MEASURABLE); Ukrainian,
  radio-noise, callsign evaluation; verified real-radio provenance; per-file model
  hash; licensing verified from an authoritative source.
* **Assumptions required:** that engine output on synthetic/undetermined audio
  predicts operational Ukrainian radio performance; that latency is acceptable
  for the operational cadence.
* **Implementation consequence:** implement one `FasterWhisperAdapter` behind
  `AbstractSttAdapter`, register it via `register_engine("faster_whisper", …)`,
  and supply `SttConfig` (cpu/int8/model_path) — a wiring-only activation, no
  seam/architecture change.

### OPTION B — AUTHORIZE vosk

* **Evidence supporting the option:** runs offline on CPU; WO-069 COMPLETED
  67/67 with 0 failures; a Ukrainian-specific model is provisioned; measured
  latency/RTF/RSS; recognised engine identifier; adapter definable behind the
  existing seam.
* **Evidence missing:** any accuracy measure; Ukrainian, radio-noise, callsign
  evaluation; verified real-radio provenance; model digest; licensing.
* **Assumptions required:** that the deterministic 8→16 kHz upsample does not
  degrade operational recognition; that the uk-only model suffices; that the
  module's native-8 kHz limitation is acceptable operationally.
* **Implementation consequence:** implement one `VoskAdapter` behind
  `AbstractSttAdapter`, register it via `register_engine("vosk", …)`, and include
  the documented resample step in the adapter — a wiring-only activation, no
  seam/architecture change.

### OPTION C — NO PRODUCTION STT ENGINE AUTHORIZED

* **Evidence supporting the option:** ADR-014 Part 2 is DEFERRED and the
  activation gate (≥50 verified real-radio transmissions with ground-truth
  transcripts, measured WER/CER, verified provenance) is **not satisfied**;
  human-reference transcripts = 0; WER/CER NOT MEASURABLE; RF provenance
  UNAVAILABLE; transport is synthetic; `real_transmission` UNRESOLVED; no engine
  is registered. Selecting an engine now would be an assumption, not an
  evidence-based decision.
* **Evidence missing:** none required to support this option — it is the
  evidence-consistent default while the gate is unmet.
* **Assumptions required:** that deferring production STT does not block the
  (already operational) recording/event/journal path; STT is an enrichment
  capability and the seam is fail-closed (`UNAVAILABLE`).
* **Implementation consequence:** no adapter is implemented; the production STT
  state remains `UNAVAILABLE` (fail-closed); a ground-truth campaign and a
  provenance determination are prerequisites before any re-entry.

---

## 14. CSA DECISION — NOT YET MADE

```text
Selected production engine:
PENDING CSA DECISION

Activation gate:
ADR-014 Part 2

Decision options:
faster_whisper
vosk
NO PRODUCTION STT ENGINE AUTHORIZED
```

The CSA fills this section explicitly. WO-070A does not choose among the options.

---

## 15. Production safety attestation (WO-070A)

```text
STT adapter implemented                     : NO
Production engine registered                : NO
_ENGINE_FACTORIES modified                  : NO (still {})
STT seam modified                           : NO
Production configuration modified           : NO
EventFactory / EventPipeline changed        : NO
RadioEventIntegrator / Observation changed  : NO
Journal / Operator Wall changed             : NO
Model downloaded / installed                : NO
Dependencies installed / modified           : NO
Engine activated                            : NO
Production code changes                     : 0
```

---

## 16. Read-only validation executed

```text
Repository identity / branch / HEAD / origin/main     : CONFIRMED (§0.1)
STT seam files present and inspected                  : CONFIRMED
Engine import availability probed                     : faster_whisper NO (repo venv), vosk NO (repo venv)
Engine registration state probed                      : _ENGINE_FACTORIES = {}
Existing STT/audio regression subset                  : 150 passed, 0 failed, 0 skipped
  cd backend && env -u PYTHONPATH PYTHONNOUSERSITE=1 ../.venv/bin/python -m pytest \
    tests/test_wo039c_stt.py tests/test_wo041_corr_stt_boundary.py \
    tests/test_wo057_callsign_integration.py tests/test_wo063_recording_stt_worker.py \
    tests/test_wo064_transcript_enrichment.py tests/test_wo038_audio_pipeline.py \
    tests/test_wo039b_recording.py -q -p no:cacheprovider
Existing WO-069 evidence read (branch 3c4f4be)        : CONFIRMED
```

No production tests for an adapter are claimed — there is no adapter in WO-070A.

---

## 17. Gaps / unknowns (for the CSA)

1. Human ground-truth transcripts (0/67) — required before WER/CER can be measured.
2. Ground-truth sidecar `ground_truth.json` is an empty template.
3. `WO-068-HUMAN-REVIEW-EXTENDED.xlsx`: EVIDENCE NOT RUNTIME-AVAILABLE.
4. RF provenance UNAVAILABLE; transport provenance synthetic; `real_transmission` UNRESOLVED.
5. `wo067/README.md` vs WO-067-PRE-04 `human_confirmed` contradiction unresolved.
6. Per-file model hashes not captured; licensing not verified from authoritative sources.
7. No evidence for Ukrainian/radio-noise/callsign accuracy for either engine.

---

## 18. Recommended follow-up (non-deciding)

* Commission the human listening campaign that writes a verbatim transcript per
  message into a ground-truth artifact (or equivalent), reviewer + review_time
  recorded.
* Obtain a CSA determination on whether CubicCore-sourced audio qualifies as
  real-radio evidence, or provision differently-sourced RF captures.
* Capture per-file model digests and verify engine/model licensing.
* Only then re-enter the ADR-014 benchmark to produce a measurable WER/CER basis.

These are recommendations for evidence completion, not an engine selection.
