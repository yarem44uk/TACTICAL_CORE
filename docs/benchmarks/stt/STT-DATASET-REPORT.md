# STT Dataset Report (WO-041)

**Date:** 2026-09-02
**Work Order:** WO-041 — Real Radio STT Benchmark Dataset & Ground Truth
**Status:** GATE FAIL — dataset prerequisite NOT satisfied

---

## Dataset objective

WO-041 acquires an auditable real-radio STT benchmark dataset of at least 50
independently verified real radio transmissions, with manually verified
ground-truth transcripts and callsign annotations, suitable for immediate use
by WO-042. WO-041 is dataset acquisition/validation only. It does not select or
implement an STT engine.

## Dataset location

- Manifest: `docs/benchmarks/stt/dataset_manifest.csv`
- Validation tooling: `docs/benchmarks/stt/validate_dataset.py`
- WAV masters: NOT in the Git repository. The only WAV masters discovered on
  this host are the WO-039-B/C unit-test fixtures under temporary directories
  (e.g. `/tmp/tmp830mejt0/2026/09/02/radio`). These are NOT committed and are
  NOT reproducible from the repository alone. The audio corpus is external to
  Git (WO-041 §20).

## Dataset size

| Metric | Value |
| --- | --- |
| Total manifest rows | 36 |
| Real transmissions (`real_transmission=true`) | 0 |
| Valid, independently verified real transmissions | 0 |
| Fixture rows | 36 |
| Duplicate rows (by SHA-256) | 0 |
| Invalid WAV files | 0 |
| Rows missing ground truth | 36 |
| Total audio duration (all fixtures) | 106.76 s |

## Valid real transmissions

**0.** No genuine real radio speech transmission was located on this host. The
only radio WAV masters present are the 36 WO-039-B/C unit-test fixtures.

## Fixture count

**36.** Every manifest row is a WO-039-B/C unit-test fixture: a constant-amplitude
PCM value fed through the real RTP → VAD → recorder → WAV pipeline to exercise
VAD / segmentation / recording logic. Each is marked `real_transmission=false`
and carries an empty ground truth. These remain excluded from the dataset gate
(WO-041 §19).

## Duplicate count

**0.** All 36 fixture WAV masters have distinct SHA-256 digests; no duplicate
content was found within the manifest.

## Ground-truth coverage

**0 rows** carry a ground-truth transcript. The fixtures contain no speech, so
no transcript exists and none was fabricated.

## Independent verification coverage

**0 rows** are flagged `ground_truth_verified=true` or
`independent_verification=true`. Because no real transmission has a reference
transcript, no independent verification could be performed (WO-041 §12/§13).

## Speaker / source distribution

None. No real transmission exists, so no speaker or radio-source distribution
could be documented. The 36 fixtures are constant-amplitude tones, not speech.

## Duration distribution (36 fixture WAVs)

- Min / median / max: 1.06 s / 1.84 s / 35.44 s
- < 2 s: 20
- 2–5 s: 14
- ≥ 5 s: 2

## Audio format distribution

All 36 fixture WAV masters are mono 16-bit 8 kHz (1 channel, 16-bit sample
width, 8000 Hz sample rate). This matches the WO-039-C3 mono 16-bit 8 kHz WAV
master requirement. No derived/normalized benchmark input was created; the
masters were opened read-only and not rewritten (WO-041 §8).

## Noise / quality observations

The WO-039 fixtures are constant-amplitude test tones (no speech, no words, no
callsigns). The underlying WO-039-A real capture decoded to a continuous
carrier noise/hiss (frame RMS min 8, median 1574, mean 4472, max 24853) — a
carrier signal, not intelligible speech. No realistic acoustic/noise speech
condition is present in the dataset.

## Callsign coverage

**0.** No callsign is present in any row; `callsigns_present` is empty
throughout. No callsign was inferred from STT output (WO-041 §11).

## Tactical vocabulary coverage

**0.** No real transmission exists, so no tactical vocabulary is represented.

## Limitations

1. No real radio speech audio exists on this host. The repository itself
   contains no WAV masters (WO-040 established the same fact).
2. The 36 WO-039 fixtures are test tones and cannot be relabelled as real
   transmissions (WO-041 §19).
3. No ground-truth transcript can be produced for a tone that contains no
   speech; nothing was synthesized (WO-041 §3, §10).
4. The audio corpus is external to Git and not reproducible from the repository
   alone (WO-041 §20).

## Dataset gate result

Per WO-041 §18, the gate counts independently verified real transmissions:

```text
valid_real_transmissions = 0
minimum_required = 50
gate = FAIL
```

Only real verified transmissions count; the 36 fixtures do not.

## ADR-014 boundary

WO-041 does not pass ADR-014. The dataset prerequisite is not satisfied. Even
if 50+ valid recordings existed, ADR-014 would remain unsatisfied until the
faster_whisper benchmark, the vosk benchmark, all required metrics, the
benchmark report, and the CSA engine decision are completed (WO-041 §28).

## Engine selection

No engine is selected. The dataset is engine-neutral. Neither
"Faster-Whisper is better" nor "Vosk is better" is asserted (WO-041 §29).

---

**DATASET READY FOR WO-042: NO**

**PRODUCTION STT ENGINE AUTHORIZED: NO**
**ENGINE SELECTION FINALIZED: NO**
**ADR-014 GATE SATISFIED: NO**
