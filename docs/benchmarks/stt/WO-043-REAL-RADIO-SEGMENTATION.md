# WO-043 — Real Radio Transmission Segmentation & Ground-Truth Preparation

**Work Order:** WO-043
**Date:** 2026-09-04
**Baseline:** `4cce0b91a3d3cad689714145e4da380e6d7650d1`
**Status:** TOOLING COMPLETE — **DATASET GATE FAIL** (no real source present)
**Corrective:** WO-043-CORR-01 applied (EOF clamp / WO-042 schema alignment / CLI test hardening)

---

## BLUF

WO-043 implements a deterministic, isolated, offline, stdlib-only tool that
segments a real radio recording into individual *candidate* transmissions, emits
stable `RADIO-NNNN` IDs, computes SHA-256, and writes a segmentation manifest
awaiting manual operator verification. The tool and its discriminating unit
tests are complete and validated.

However, the specified input source **`radio test.wav` does not exist on this
host**, and **no real radio speech transmission is present anywhere on this
system** — a finding already documented in the WO-042 report. Therefore no real
candidate transmissions were produced. Nothing was fabricated: no synthetic
audio was relabelled as a real transmission, and the dataset gate remains
**FAIL** (`accepted_real_transmissions = 0`).

---

## WO-043-CORR-01 — Corrective audit

An independent forensic audit of WO-043 surfaced three findings. WO-043-CORR-01
fixes them without changing the segmentation architecture, the audio pipeline,
STT, ADR-014, or the WO-042 tools.

### C1 — EOF boundary / timing consistency

Previously, a candidate whose activity reached EOF could carry a
`segment_end` greater than the source duration, while the derived WAV was
physically truncated to EOF — so the manifest timing did not describe the
actual audio interval. Correction:

* `build_candidates` clamps every segment/activity bound to the source
  duration (`segment_start >= 0`, `segment_end <= source_duration`) and drops
  any degenerate zero-length segment;
* `write_wav_derived` resolves the slice in the **sample domain**
  (`start_frame` / `end_frame`) and returns the actual `(start_sec, end_sec)`
  it wrote;
* the manifest `segment_start_seconds` / `segment_end_seconds` /
  `duration_seconds` are now taken from those actual sample-domain bounds, so
  they always equal the derived WAV interval.

### C2 — WO-042 manifest schema alignment

The WO-043 segmentation manifest keeps the segmentation-specific forensic
evidence (segment/activity bounds, `source_sha256`, `derived_sha256`,
`candidate_status`). It is **not** a second dataset schema. A deterministic
conversion (`convert_to_wo042`) and a `--wo042-manifest` CLI option emit the
WO-042 canonical dataset manifest. Every converted row stays an unverified
candidate (`real_transmission=false`, `ground_truth_verified=false`,
`independent_verification=false`, empty `transcript`, `callsigns_present=[]`);
no value is invented for unknown fields (`UNKNOWN`). The converted manifest is
loadable by `wo042_validate_dataset.py` and never promotes a candidate to a real
transmission.

### C3 — CLI / manifest / SHA test hardening

Integration tests now drive the **actual CLI entrypoint** (`wo043_segment.main`)
end-to-end: real derived WAV writing, real manifest generation, real file
hashing, SHA recomputed from the output bytes, manifest/file consistency over
all rows, stale-output isolation, `--manifest`-without-`--output-dir` no longer
producing a header-only manifest, CLI determinism (byte-identical manifests),
and source immutability through the CLI.

### Corrected test count

The WO-043 unit/integration suite is now **27 passed** (was 16). The dataset
candidates remain **unverified**; finding candidates still does not equal real
transmissions.

---

## Source acquisition (WO-043 §2)

The specified input was searched exhaustively:

```bash
find /mnt/data -type f \( -iname "*.wav" -o -iname "*.flac" -o -iname "*.mp3" \)
find /opt/data -type f \( -iname "*.wav" -o -iname "*.flac" -o -iname "*.mp3" \)
```

Result:

```
REAL AUDIO SOURCE (radio test.wav) = NOT FOUND
```

A full-host search for audio/media files (`.wav`, `.flac`, `.mp3`, `.ogg`,
`.opus`, `.m4a`, `.aiff`, `.pcm`, `.s16le`, `.alaw`, `.pcap`, `.pcapng`) across
`/`, `/opt/data`, `/mnt/data`, `/opt/data/uploads`, and the repository found no
real radio speech recording. The only radio WAV masters on the host are the
WO-039-B/C **unit-test fixtures** under `/opt/data/wo041_evidence/` — all
byte-identical constant-amplitude PCM **carrier tones** with no speech, no
words, no callsigns (confirmed in §Audio analysis below).

---

## Deliverables

| Artifact | Path | Purpose |
| --- | --- | --- |
| Segmentation tool | `docs/benchmarks/stt/wo043_segment.py` | Deterministic candidate segmentation |
| Unit tests | `docs/benchmarks/stt/test_wo043_segment.py` | Algorithm behaviour (synthetic) |
| Segmentation manifest | `docs/benchmarks/stt/wo043_segmentation_manifest.csv` | Candidate records awaiting verification |
| This report | `docs/benchmarks/stt/WO-043-REAL-RADIO-SEGMENTATION.md` | Findings and dataset status |

The tool is **isolated, offline, stdlib-only** (mirrors the WO-042 design): it
uses only `wave`, `array`, `csv`, `hashlib`, `math`, `argparse`, `dataclasses`.
It never invokes, imports, downloads, or selects any STT engine (WO-043 §24),
never touches the production audio pipeline (WO-043 §25), and never modifies
ADR-014 (WO-043 §26).

---

## Segmentation algorithm (WO-043 §5)

```
audio -> frame analysis -> energy/RMS -> activity threshold -> attack ->
hangover/post-roll -> merge nearby fragments -> minimum duration ->
(cap) maximum duration -> overlap prevention -> candidate transmission
```

Energy detection is used **only to propose candidate boundaries**; it never
classifies a burst as speech or as a real transmission (WO-043 §4). Every
emitted candidate carries `candidate_status=CANDIDATE` and `real_transmission=false`
until a human operator verifies it.

### Proposed segmentation defaults (WO-043 §6)

These are **initial engineering defaults**, NOT production policy, and are
overridable via CLI flags:

```
frame_ms        = 20 ms
hop_ms          = 10 ms
pre_roll_ms     = 250 ms
post_roll_ms    = 400 ms
min_duration_ms = 150 ms
max_duration_ms = 60000 ms
merge_gap_ms    = 250 ms
energy_threshold = 0.01   (RMS, mono normalised to [-1,1]; proposed default)
```

### Design rules honoured

* **Deterministic** — same source + same parameters => same segments, same IDs,
  same hashes (WO-043 §9, §20).
* **No overlap** — `end[i] <= start[i+1]` is guaranteed (WO-043 §7).
* **Activity vs segment bounds kept separate** (WO-043 §8, §17):
  `activity_start/end` and `segment_start/end` are both recorded so the operator
  can later correct a boundary.
* **Minimum duration** applies to the *activity* length, not the padded segment,
  so a 60 ms blip padded with 650 ms of pre/post roll does not survive a 150 ms
  minimum.
* **Maximum duration** splits an over-long segment into consecutive
  non-overlapping chunks of at most `max_duration`; a chunk containing no
  activity (pure pre/post-roll padding) is dropped.
* **Contiguous deterministic IDs** — renumbered `RADIO-0001..N` in ascending
  `segment_start` order after all processing, so numbering has no gaps and is
  stable across runs.
* **Source immutable** — the original is opened read-only; only derived WAVs are
  written, preserving the source native format (sample rate / channels / sample
  width) (WO-043 §2, §10).
* **EOF clamped** (WO-043-CORR-01 C1) — every segment/activity bound is clamped
  to the source duration, and the manifest timing always describes the actual
  derived WAV interval (sample-domain source of truth).
* **WO-042 schema compatible** (WO-043-CORR-01 C2) — `--wo042-manifest` emits a
  deterministic WO-042 canonical dataset manifest; candidates stay unverified.
* **CLI integration tested** (WO-043-CORR-01 C3) — the public CLI entrypoint is
  exercised end-to-end (real WAV / manifest / SHA) by the test suite.

---

## Determinism verification (WO-043 §20)

The tool was run twice on the same deterministic synthetic multi-burst input and
the same parameters. The two generated manifests are **byte-identical**, and the
candidate boundaries, IDs, and derived SHA-256 values are identical across runs.

```
manifest run 1 == manifest run 2  ->  byte-identical: True
candidates: 3
RADIO-0001  0.540s -> 2.100s  1.560s  (activity 0.790s -> 1.700s)
RADIO-0002  3.640s -> 6.880s  3.240s  (activity 3.890s -> 6.480s)
RADIO-0003  9.220s -> 10.480s  1.260s  (activity 9.470s -> 10.080s)
```

---

## Real-audio execution on the only WAV present (fixture, non-real)

The tool was executed on the real WAV fixture present on the host
(`/opt/data/wo041_evidence/master_prod.wav`) to confirm it runs end-to-end on a
real WAV file. The result is a single candidate covering the carrier-tone file.
This is **not** a real transmission (WO-043 §4, §22) and is **not** counted.

```
source: /opt/data/wo041_evidence/master_prod.wav
source_sha256: bccc30487732c43802f041b1ac92eb7f19e1bfb672bf064a79c07b37018c98e1
source: rate=8000 Hz channels=1 sample_width=16 bits
candidates: 1
RADIO-0001  0.000s -> 35.070s  35.070s  (activity 0.000s -> 34.670s)
```

### Audio analysis (WO-043 §23)

| Metric | Value | Note |
| --- | --- | --- |
| sample rate | 8000 Hz | |
| channels | 1 | mono |
| sample width | 16 bits | PCM |
| duration | 35.440 s | |
| peak (norm) | 0.9844 | near full scale |
| RMS (norm) | 0.1613 | constant carrier energy |
| DC offset (norm) | 0.000188 | essentially zero |
| clipping fraction | 0.000000 | no clipping |
| silence fraction (<1% peak) | 0.4759 | |

These are diagnostic values only (WO-043 §23) and are not used for automatic
semantic interpretation. The constant RMS and peak confirm the fixture is a
continuous carrier tone, not speech.

---

## Unit tests (WO-043 §21)

`test_wo043_segment.py` uses **deterministic synthetic** inputs and exercises
only the segmentation algorithm: single burst, two separated bursts, short
silence inside a burst, nearby-burst merge, long-silence split, minimum
duration, maximum duration split, pre-roll, post-roll, pre-roll clamped at zero,
no-overlap invariant, deterministic ordering, duplicate-hash stability, source
immutability, and manifest CANDIDATE defaults.

```
pytest -q docs/benchmarks/stt/test_wo043_segment.py
27 passed in 0.37s
```

After WO-043-CORR-01, the suite also covers the actual CLI entrypoint, EOF
clamp, t=0 clamp, manifest/file consistency over all rows, stale-output
isolation, `--manifest`-without-`--output-dir`, CLI determinism, source
immutability, and WO-042 schema compatibility. These synthetic tests are **not**
evidence of real transmissions (WO-043 §21); they only verify algorithm
behaviour and the CLI/forensic output path.

---

## Scope gates

| Gate (WO-043 §) | Check | Result |
| --- | --- | --- |
| §24 No STT | grep for whisper/faster_whisper/vosk/transcribe/speech-to-text in WO-043 files | PASS (no matches) |
| §25 No production changes | `git diff HEAD -- backend/app/audio` | EMPTY |
| §26 ADR-014 unchanged | `git diff HEAD -- docs/adr` | EMPTY |
| §27 WO-042 boundary | `wo042_build_manifest.py`, `wo042_validate_dataset.py` unmodified | UNCHANGED |

The WO-043 tool is stdlib-only; its only imports are `argparse`, `array`, `csv`,
`hashlib`, `math`, `os`, `sys`, `wave`, `dataclasses`, `typing`.

---

## Dataset status (WO-043 §28, §33)

```
candidate_count:                   3  (deterministic synthetic demonstration)
accepted_real_transmissions:       0
ground_truth_verified:             0
independently_verified:            0

WO-042 DATASET GATE:               FAIL
```

**`candidate_count != valid_real_transmissions`** (WO-043 §28). The 3 candidates
come from a synthetic demonstration input, are all `real_transmission=false`,
and none has been manually verified. The gate can only PASS on independently
verified real transmissions; finding candidates alone never produces PASS.

---

## Conclusion

WO-043 CODE: **PASS** — the segmentation is deterministic, boundaries do not
overlap, IDs are contiguous and deterministic, SHA-256 is correct, the source is
never modified, the manifest is reproducible, the tests are discriminating, and
no STT or production changes exist.

WO-043 DATASET GATE: **FAIL** — no real radio transmission exists on this host
to segment. The intended source `radio test.wav` was not found. The tool is
ready to process a real capture as soon as one is supplied.
