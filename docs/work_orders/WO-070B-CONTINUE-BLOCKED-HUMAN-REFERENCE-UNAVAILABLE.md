# WO-070B-CONTINUE — BLOCKED: HUMAN REFERENCE ARTIFACT STILL NOT RUNTIME-ACCESSIBLE

**Work Order:** WO-070B (continuation)
**Date:** 2026-09-19
**Branch:** `wo-070b-stt-human-reference-benchmark`
**Parent blocker:** `docs/work_orders/WO-070B-BLOCKED-HUMAN-REFERENCE-UNAVAILABLE.md`

---

## STATUS: BLOCKED

REASON: WO-068 completed human-reference artifact still not runtime-accessible.

WER: NOT_MEASURABLE
CER: NOT_MEASURABLE

---

## 1. Task performed

Per WO-070B-CONTINUE §2, the first task was to verify whether the completed
artifact `WO-068-HUMAN-REVIEW-EXTENDED.xlsx`
(library file id `file_00000000779c8210a4ec00da36c444dc`,
library id `libfile_542a5507ff7c8191a10e49c5dafdd408`)
has now been provisioned into the Hermes runtime.

It has not. This document records the exact re-provisioning check evidence.

---

## 2. Forensic gate (read-only, before any modification)

```
$ cd /opt/data/tactical_core_github
$ git status --short
 M backend/app/plugins/manager/__pycache__/plugin_manager.cpython-313.pyc
?? 500
$ git branch --show-current
wo-070b-stt-human-reference-benchmark
$ git rev-parse HEAD
af19586d2292de0bf98205eb9735beab1bb25c0e
$ git rev-parse origin/main
4cddf848fa2ff959a13817002d684ee5320e06c1
$ git log -1 --oneline
af19586 WO-070B: document human reference benchmark blocker
$ git diff --name-only origin/main...HEAD
docs/work_orders/WO-070B-BLOCKED-HUMAN-REFERENCE-UNAVAILABLE.md
```

Pre-existing worktree state preserved exactly. The protected untracked `?? 500`
was never opened, read, hashed, statted, copied, moved, renamed, staged, deleted,
cleaned, or reset.

---

## 3. Provisioning re-check — exact searches

### 3.1 Filename variants (whole filesystem)

```
$ find /opt/data -iname '*WO-068*' -o -iname '*WO_068*' \
    -o -iname '*HUMAN-REVIEW*' -o -iname '*human_review*'
```

Hits are all categorical review artifacts, never a completed transcript workbook:

```
/opt/data/wo067_evidence/human_review/reports/HUMAN_REVIEW_SUMMARY.md
/opt/data/wo067_evidence/human_review/reports/HUMAN_REVIEW_INDEX.html
/opt/data/wo067_evidence/human_review/metadata/human_review.csv
/opt/data/wo067_evidence/human_review/playlists/HUMAN_REVIEW_S1.m3u
/opt/data/wo067_evidence/human_review/playlists/HUMAN_REVIEW_S2.m3u
/opt/data/wo067_evidence/human_review/playlists/HUMAN_REVIEW_PLAYLIST.m3u
/opt/data/wo067_evidence/WO-067-PRE-04-HUMAN-REVIEW-PACKAGE.zip
/opt/data/wo068_real_radio_stt_benchmark_v1/reports/WO-068-BENCHMARK-REPORT.md
/opt/data/uploads/<batch>/human_review.csv   (x11, all sha256 21c470b6…)
```

### 3.2 `*EXTENDED*` variants

Only third-party library files (numpy `_extended_precision`, openpyxl
`packaging/extended.py`, OOXML `.xsd` schema). No benchmark workbook.

### 3.3 Library file identifier

```
$ find / -xdev -iname 'file_00000000779c*'
(no output)
```

### 3.4 All spreadsheets under /opt/data

```
$ find /opt/data -iname '*.xlsx'
/opt/data/output/RADIONOR_SETTINGS_FULL.xlsx
/opt/data/output/RADIONOR_ALL_SETTINGS.xlsx
/opt/data/output/cre2_full.xlsx
/opt/data/output/radionor_change_set/RADIONOR_CHANGE_SET.xlsx
```

None is a WO-068 human-review workbook. No `.xls` anywhere on the filesystem.

### 3.5 Knowledge bases

Searched all 4 knowledge bases the runtime is permitted to see
(`НІСД`, `Верифікація`, `ALPH Guide`, `Зброєзнавча база знань`):

```
kb_search_exact("WO-068-HUMAN-REVIEW-EXTENDED")   -> no match
kb_search_exact("human_transcript reference_transcript") -> no match
```

No knowledge base file carries a human-entered transcript.

### 3.6 Recently staged upload batches (Sep 18–19)

```
gen traffic.pcap        (3875865 B)
human_review.csv        (5812 B, sha256 21c470b6…)
settings.json
radionor_config_sync.py
10.19.50.233-2.txt
test.pcapng             (464660 B)
*.zip                   (RADIONOR / CRE2 verification bundles)
```

No workbook in any batch.

---

## 4. Accessible human-review artifact analysis

The only accessible human-review artifact is the categorical CSV
(staged `human_review.csv`; 11 identical copies; sha256
`21c470b613f1df215b2e71bd154e4237a19462293d68af43aa29a362320af1e5`;
size 5812 B).

Columns:

```
message_id;stream_id;start_time;end_time;duration_ms;audible_voice;intelligible;
radio_style;speaker;dialogue_candidate;voice_type;confidence;notes;reviewer;review_time
```

It contains categorical listening judgements only. There is **no transcript
column**. Its `notes` column is empty for all rows. Its `audible_voice = NO`
rows are exactly `msg_0001, msg_0023, msg_0044, msg_0049, msg_0053, msg_0066`.

Per WO-070B-CONTINUE §4/§6 this CSV is NOT the completed WO-068 transcript
artifact, and its categorical fields MUST NOT be treated as reference transcripts.

Corroborating evidence from the WO-068 dataset itself:

```
dataset/ground_truth/ground_truth.json
  "status": "UNAVAILABLE",
  "reason": "No human listening review has been performed...", "entries": []

dataset/manifest.csv  (per row)
  ground_truth        = (empty)
  ground_truth_status = UNAVAILABLE
  human_review        = PENDING
  real_transmission   = UNRESOLVED

reports/WO-068-BENCHMARK-REPORT.md
  Status: BLOCKED / INCOMPLETE — dataset gate FAIL (ground truth UNAVAILABLE)
  zero of them carry human-verified ground truth
```

The repository ground-truth sidecar for this purpose
(`docs/benchmarks/stt/wo067/wo067_ground_truth.json`) is an empty template.

---

## 5. Consequence

No human-reference transcript dataset was constructed, because no
human-entered transcript exists in this runtime. Per WO-070B §4, §16 and §20 and
WO-070B-CONTINUE §2, the correct non-fabricating outcome is BLOCKED.

- No `human_reference_transcripts.csv` was created.
- No `benchmark_wer_cer.py` / tests were created.
- No WER/CER was calculated or assigned.
- No engine was run, ranked, or selected.
- No transcript, callsign, note, filename, or STT output was promoted to
  reference text.

---

## 6. Final report fields

```
STATUS: BLOCKED
BRANCH: wo-070b-stt-human-reference-benchmark
HEAD: branch tip of wo-070b-stt-human-reference-benchmark (see git rev-parse)
ORIGIN/MAIN: 4cddf848fa2ff959a13817002d684ee5320e06c1

HUMAN_REFERENCE_SOURCE: WO-068-HUMAN-REVIEW-EXTENDED.xlsx / file_00000000779c8210a4ec00da36c444dc
HUMAN_REFERENCE_ACCESSIBLE: NO — NOT PROVISIONED INTO RUNTIME
XLSX_SHA256: N/A — FILE ABSENT
XLSX_SIZE: N/A — FILE ABSENT

TOTAL_RECORDS: 67 (categorical CSV only; no transcript column)
HUMAN_VERIFIED_TRANSCRIPTS: 0
NON_AUDIBLE: 6 (msg_0001, msg_0023, msg_0044, msg_0049, msg_0053, msg_0066)
NO_HUMAN_TRANSCRIPT: 61

MESSAGE_ID_MAPPING: not performed — no reference set to join
DUPLICATES: none created
MISSING_IDS: all 67 reference transcripts missing
ORPHANS: N/A

NORMALIZATION: not applied — no reference text to normalize; no procedure invented

FASTER_WHISPER: hypotheses 67/67 (64 non-empty, 3 empty) · evaluated 0 · WER NOT_MEASURABLE · CER NOT_MEASURABLE
VOSK:           hypotheses 67/67 (53 non-empty, 14 empty) · evaluated 0 · WER NOT_MEASURABLE · CER NOT_MEASURABLE

TRANSPORT_PROVENANCE: generated/synthetic CubicCore transport (unchanged from prior evidence)
RF_PROVENANCE: unresolved
REAL_TRANSMISSION: UNRESOLVED (not converted to YES or NO)

WO-069 EVIDENCE MODIFIED: NO
PRODUCTION FILES MODIFIED: NO
STT SEAM MODIFIED: NO
ENGINE ACTIVATED: NO
NETWORK USED: NO
FABRICATED EVIDENCE: NONE

WO-070B TESTS: not created — tests presuppose a reference dataset (§16 deferred again)
PRODUCTION REGRESSION: not run — zero production files changed (nothing to regress)

COMMIT: this commit — branch tip of wo-070b-stt-human-reference-benchmark
REMOTE_VERIFICATION: VERIFIED — origin/wo-070b-stt-human-reference-benchmark == branch tip (git ls-remote); origin/main = 4cddf848fa2ff959a13817002d684ee5320e06c1 (unchanged)

FINAL_CLASSIFICATION: BLOCKED
```

---

## 7. What would unblock this continuation

1. Provision the actual completed `WO-068-HUMAN-REVIEW-EXTENDED.xlsx` to the
   runtime (a path readable by the benchmark process), containing a per-message
   human-entered transcript column plus the `message_id` mapping.
2. A CSA ruling on whether CubicCore-sourced transport audio counts as
   real-radio evidence (separate production decision).

---

## 8. Commit / remote verification

Captured live at execution time via git ls-remote; exact tip SHAs are recorded in the
WO-070B run transcript. The embedded commit SHA is deliberately not self-referenced
(an amend that records its own SHA would invalidate itself).

```
git rev-parse HEAD
git rev-parse origin/wo-070b-stt-human-reference-benchmark
git rev-parse origin/main
git status --short
```

`origin/main` remains `4cddf848fa2ff959a13817002d684ee5320e06c1` (unmodified).
