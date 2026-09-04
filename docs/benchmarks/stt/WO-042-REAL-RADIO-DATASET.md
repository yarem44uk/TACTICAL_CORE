# WO-042 — Real Radio Speech Dataset & Ground-Truth Acquisition

**Work Order:** WO-042
**Date:** 2026-09-04
**Baseline:** `80f9431e25764125205de35d2144318b27ecc33a`
**Status:** GATE **FAIL** — dataset prerequisite NOT satisfied

---

## BLUF

WO-042 builds the auditable, reproducible benchmark-dataset tooling required for
the next STT benchmark stage. The tooling, manifest schema, deterministic
validator, and targeted tests are complete and validated. However, **no real
radio speech transmission exists on this host**, so the dataset gate is
**FAIL** (`valid_real_transmissions = 0`, minimum required `50`). No real
transmission was invented, no test tone was relabelled as real, and no ground
truth was fabricated (WO-042 §19).

---

## Dataset provenance

| Field | Value |
| --- | --- |
| Repository | `yarem44uk/TACTICAL_CORE` |
| Baseline | `80f9431e25764125205de35d2144318b27ecc33a` |
| Dataset area | `docs/benchmarks/stt/` |
| Manifest | `docs/benchmarks/stt/wo042_dataset_manifest.csv` |
| Validator | `docs/benchmarks/stt/wo042_validate_dataset.py` |
| Manifest builder | `docs/benchmarks/stt/wo042_build_manifest.py` |
| Targeted tests | `docs/benchmarks/stt/test_wo042_validate_dataset.py` |

## Acquisition method

A full-host search was performed for real radio recordings (`.wav`, `.flac`,
`.pcap`, `.pcapng`) under `/opt/data`, `/mnt/data`, and the repository:

```bash
find /opt/data -type f \( -iname "*.wav" -o -iname "*.flac" \
  -o -iname "*.pcap" -o -iname "*.pcapng" \)
find /mnt/data -type f \( -iname "*.wav" -o -iname "*.flac" \
  -o -iname "*.pcap" -o -iname "*.pcapng" \)
find . -type f \( -iname "*.wav" -o -iname "*.flac" \
  -o -iname "*.pcap" -o -iname "*.pcapng" \)
```

### REAL AUDIO SOURCE

```
REAL AUDIO SOURCE = NONE (no real radio speech transmission on this host)
```

The only radio WAV masters present are under `/opt/data/wo041_evidence/`:

| Path | SHA-256 | Classification |
| --- | --- | --- |
| `/opt/data/wo041_evidence/master_prod.wav` | `bccc30487732c43802f041b1ac92eb7f19e1bfb672bf064a79c07b37018c98e1` | fixture (WO-039-B/C test tone) |
| `/opt/data/wo041_evidence/master_reader.wav` | `bccc30487732c43802f041b1ac92eb7f19e1bfb672bf064a79c07b37018c98e1` | fixture (duplicate content) |
| `/opt/data/wo041_evidence/radio_rtp_master.wav` | `bccc30487732c43802f041b1ac92eb7f19e1bfb672bf064a79c07b37018c98e1` | fixture (duplicate content) |

All three are byte-identical (same SHA-256) and decode to a constant-amplitude
PCM **carrier tone** — no speech, no words, no callsigns. They are the WO-039-B/C
unit-test fixtures (provenance `WO-039-B/C unit-test fixture`). The WO-041 real
RTP capture (`/opt/data/wo041_evidence/radio_rtp.pcapng`) decoded to continuous
carrier noise/hiss, not intelligible speech.

### Classification of candidate files

| Candidate | Classification | Reason |
| --- | --- | --- |
| `/opt/data/wo041_evidence/*.wav` | fixture | WO-039-B/C test tone; no speech; not a real transmission |
| `/opt/data/wo041_evidence/*.pcapng`, `*.s16le`, `*.alaw` | fixture / capture | RTP carrier capture; no intelligible speech |
| `/opt/data/uploads/*/test.pcapng` | fixture | WO-041 RTP test captures |
| `/tmp/pytest-of-hermes/**` | fixture | pytest synthetic fixtures |
| `/usr/lib/libreoffice/**/*.wav` | non-radio | gallery sound effects |
| `/opt/hermes/tools/neutts_samples/jo.wav` | non-radio | tool sample, not radio |

No candidate is an intelligible real radio speech transmission. Unknown /
non-radio content is excluded from the validated dataset (WO-042 §4, §11).

## Audio master rule

Each transmission must have an immutable master. Recommended benchmark master
format is WAV / PCM / mono / 16-bit / 8000 Hz, but no blind normalization is
performed when the source capture has a different native format (§5). The WAV
masters are **external to Git** and are opened read-only; the master bytes are
never rewritten after the SHA-256 is computed. The `wo042_build_manifest.py`
tool computes SHA-256, duration, sample rate, channels, and sample width from
the header without modifying the file.

## Transmission identity

`audio_id` is stable and deterministic: `RADIO-NNNN` derived from sorted path
order (§6). No random IDs. Duplicate content is identified by SHA-256: identical
SHA = duplicate = not a new transmission.

## Manifest

`wo042_dataset_manifest.csv` uses the WO-042 schema (§7):

```
audio_id, audio_path, sha256, source_type, real_transmission,
capture_timestamp, duration_seconds, sample_rate, channels, sample_width_bits,
codec, speaker_or_source, transcript, callsigns_present,
ground_truth_verified, independent_verification, verification_method,
provenance, notes
```

Unknown values use the literal `UNKNOWN`; nothing is guessed. The current
manifest documents the 3 discoverable radio WAV masters (all fixtures). No field
was populated with an unverifiable value.

## Ground-truth process

Ground truth must be manual (§8): listen to the real transmission, write a
verbatim transcript only as far as it is genuinely intelligible, use documented
notation for unintelligible audio, preserve spoken tactical terminology exactly,
never "improve" the transcript, and never use STT output as final truth. Because
no real speech recording exists, **no transcript was created** — nothing was
fabricated (§19).

## Callsign annotation

`callsigns_present` must be a JSON array (`[]` when no callsign is audible, or
`["ALPHA-21"]`). A callsign is admitted only if actually heard (§9). No callsign
was inferred from context, speaker identity, filename, or STT. The current
manifest rows all carry `[]` and are non-real.

## Exclusion rules

Automatically excluded (§11): synthetic audio, test tones, unit fixtures,
duplicate SHA, corrupt WAV, missing transcript, missing verification, unknown
provenance, non-radio audio, empty audio. These may be present in a raw
acquisition area but never count toward `valid_real_transmissions`.

## Duplicate rules

Identical SHA-256 = duplicate; duplicate content counts once (§6, §11). The
manifest documents the 3 masters as 1 distinct content with 2 duplicate rows.

## Verification rules

For a transmission to count it must satisfy (§10, §12):

```
real audio
+ manual transcript
+ callsign annotation
+ independent verification
```

`ground_truth_created`, `ground_truth_verified`, and `independent_verification`
are distinct states. A counted row must be flagged both
`ground_truth_verified=true` and `independent_verification=true`.

## Validation

The deterministic validator `wo042_validate_dataset.py` checks: required
columns; file existence; WAV validity; SHA-256 integrity; duplicate SHA;
`real_transmission` flag; transcript presence; callsign schema; verification
flags; provenance validity; audio properties; and the count gate. It is
stdlib-only, offline, read-only, and engine-neutral (WO-042 §13, §17).

Run:

```bash
python3 docs/benchmarks/stt/wo042_validate_dataset.py \
    --manifest docs/benchmarks/stt/wo042_dataset_manifest.csv
```

## Dataset counts

```
VALIDATION RESULT
==============================
manifest_rows: 3
real_transmissions: 0
fixture_rows: 3
duplicates: 2
verified_real_transmissions: 0
invalid_rows: 0

DATASET GATE:
FAIL

minimum_required: 50
valid_real_transmissions: 0
duplicate sha ids:
  RADIO-0002, RADIO-0003
```

## Gate result

```
valid_real_transmissions = 0
minimum_required         = 50
DATASET GATE             = FAIL
```

The gate is FAIL because the host contains **no** real radio speech
transmission. The 3 WO-039-B/C fixtures are correctly excluded; they are not
relabelled as real (WO-042 §19).

## Reproducibility

Validation is deterministic: the same manifest always yields the same result.
No timestamps or randomness affect identity or the gate (§14).

## Historical note (WO-041)

The repository already contains prior WO-041 dataset evidence
(`docs/benchmarks/stt/dataset_manifest.csv`, `validate_dataset.py`,
`STT-DATASET-REPORT.md`, etc.). That WO-041 history is **preserved untouched**;
it is not overwritten or reinterpreted (WO-042 §16). The WO-041 record itself
documents a `0/50` gate FAIL from 2026-09-02. WO-042 extends the dataset area
with its own tooling and manifest rather than mutating the historical files.

## ADR-014 boundary

WO-042 does **not** select Faster-Whisper or Vosk, does not benchmark STT
engines, does not modify production STT, does not register an STT engine, and
does not change ADR-014 (WO-042 §17). The dataset prerequisite is not satisfied,
so ADR-014 remains NOT SATISFIED.

## Limitations

1. No real radio speech audio exists on this host. The repository itself
   contains no WAV masters.
2. The 3 WO-039-B/C fixtures are test tones and cannot be relabelled as real
   transmissions.
3. No ground-truth transcript can be produced for a tone that contains no
   speech; nothing was synthesized.
4. The audio corpus is external to Git and not reproducible from the repository
   alone (WO-042 §5).
5. The dataset gate is FAIL; WO-042 is technically complete for tooling and
   evidence, but the benchmark prerequisite is not met.

---

**DATASET READY FOR NEXT STAGE: NO**
**STT ENGINE SELECTED: NO**
**PRODUCTION STT MODIFIED: NO**
**ADR-014 GATE SATISFIED: NO**
