# WO-071A — CSA STT AUTHORIZATION DECISION: DEFERRED

**Repository:** `yarem44uk/TACTICAL_CORE`
**Branch:** `wo-071a-csa-stt-authorization-deferred`
**Base:** `origin/main`
**Main baseline:** `4cddf848fa2ff959a13817002d684ee5320e06c1`
**Document class:** documentation-only decision record
**Production impact:** none

---

## Executive decision

```text
CSA_DECISION: AUTHORIZE_NO_PRODUCTION_STT_ENGINE
DECISION_STATE: DEFERRED
```

No production STT engine or model is authorized at this time.

---

## 1. Decision interpretation

This decision means:

- **Evidence accepted.** The WO-069 runtime benchmark, WO-070A engine-selection
  evidence package, WO-070B human-reference accuracy benchmark, and the WO-071
  authorization package are accepted as valid engineering evidence.
- **No production engine selected.** Neither Faster-Whisper nor Vosk is
  authorized for production use by this decision.
- **No engine rejected permanently.** This is an intentional architectural
  deferral, **not** a benchmark failure and **not** a rejection of either
  candidate. No engine is disqualified.
- **Engine/model selection deferred** until a concrete production requirement
  exists, against which a future engine or model can be validated and
  explicitly authorized.

The decision is a deliberate architectural hold. It does **not** mean the STT
architecture is abandoned.

---

## 2. Evidence basis

This decision references the completed STT evidence chain:

| Evidence | Subject | Repository location |
|---|---|---|
| WO-069 | Real-radio STT runtime benchmark (67/67 execution both engines) | `docs/benchmarks/stt/wo069/` |
| WO-070A | Preliminary CSA STT engine-selection evidence package | `docs/work_orders/WO-070A*`, `docs/benchmarks/stt/` |
| WO-070B | Human-reference STT accuracy benchmark (WER/CER vs human transcripts) | `docs/benchmarks/stt/wo070b/WO-070B-STT-ACCURACY-REPORT.md` |
| WO-071 | CSA STT engine authorization decision package (state: `DECISION_PENDING`) | `docs/work_orders/WO-071-CSA-STT-ENGINE-AUTHORIZATION.md` |

WO-071 recorded the authorization state as `DECISION_PENDING` because no
explicit CSA authorization had been supplied at that time. **WO-071A records the
explicit CSA decision that resolves that pending state.**

The measured results remain descriptive facts and are not by themselves the
basis of this decision:

- Faster-Whisper — WER 1.062937, CER 0.774924 (61 records evaluated)
- Vosk — WER 0.594406, CER 0.498489 (61 records evaluated)

These measurements are valid against the human reference, but as recorded in
§6 (provenance) they do not independently establish RF provenance. They are not
converted into an authorization here.

---

## 3. Reason for deferral

The following grounds are recorded for the deferral:

1. WO-070B provides **valid human-reference accuracy measurements** against the
   human transcripts — the evidence is real and usable.
2. The current dataset is based on a **synthetic transport topology**
   (`TRANSPORT_PROVENANCE: SYNTHETIC_TOPOLOGY`); it was not captured over a live
   RF/SDR receive chain.
3. **RF provenance remains unresolved** (`RF_PROVENANCE: UNRESOLVED`,
   `REAL_TRANSMISSION: UNRESOLVED` for all 67 records).
4. The current evidence does **not** establish the required future production
   language/model configuration.
5. Production requirements may later require a **different STT engine or model**
   than either candidate measured here.
6. **No permanent binding** to Faster-Whisper or Vosk is architecturally
   required at this stage.

Neither engine is rejected permanently by this deferral.

---

## 4. Engine/model replacement principle

```text
STT_ENGINE_IS_NOT_ARCHITECTURALLY_PERMANENT.
STT_MODEL_IS_NOT_ARCHITECTURALLY_PERMANENT.
```

The existing STT seam remains the stable architectural contract. A future Work
Order may authorize:

- Faster-Whisper,
- Vosk,
- another validated offline STT engine, or
- another model/version of an already-supported engine,

provided that the future engine/model passes the required validation and
receives explicit CSA authorization.

---

## 5. Architectural principle

```text
The STT seam is stable.
The engine/model behind the seam is replaceable.
```

### Important architectural constraint

Future engine/model replacement **MUST** occur behind the existing STT seam.
The following files are the seam and are **not** to be redesigned:

```text
backend/app/contracts/audio.py
backend/app/audio/stt_seam.py
backend/app/audio/stt_config.py
backend/app/audio/stt_worker.py
```

They may only be changed if a future, explicitly authorized Work Order
determines that the existing seam itself is insufficient.

The intended architecture is:

```text
Radio audio
    ↓
existing segmentation / VAD
    ↓
WAV
    ↓
EXISTING STT SEAM
    ↓
[authorized engine / model]
    ↓
transcript
    ↓
existing enrichment / integration pipeline
```

The engine/model is replaceable. The production event architecture is not to be
redesigned merely because the STT engine changes.

---

## 6. Future authorization process

A future production STT authorization may be opened when a concrete requirement
appears. Examples of triggering requirements:

- mandatory UA/RU/EN support;
- improved radio-domain accuracy;
- different model size;
- different CPU/RAM constraints;
- lower latency;
- improved callsign recognition;
- different deployment hardware;
- a new human-reference dataset;
- a validated RF-derived dataset.

A future WO **MUST NOT** assume that the current WO-069 / WO-070B benchmark
automatically authorizes a future engine. The future decision must be based on
the evidence applicable to that future requirement.

The future engine/model authorization flow is:

```text
candidate
→ benchmark
→ human reference
→ resource validation
→ language validation
→ provenance assessment
→ CSA authorization
→ separate production implementation WO
```

---

## 7. Production safety statement

**No production files are modified by this WO.**

This WO does not:

- modify production STT files (`backend/app/contracts/audio.py`,
  `backend/app/audio/stt_seam.py`, `backend/app/audio/stt_config.py`,
  `backend/app/audio/stt_worker.py`);
- register an engine or add `_ENGINE_FACTORIES`;
- install packages;
- download models;
- modify model files;
- change production configuration;
- modify `EventFactory`, `EventPipeline`, `RadioEventIntegrator`, `Observation`,
  Operator Wall, or the DB schema;
- activate STT.

This WO is documentation-only. Any production implementation of an authorized
engine requires a **separate production implementation Work Order** and must not
be inferred from this document.

---

## Status

```text
CSA_DECISION: AUTHORIZE_NO_PRODUCTION_STT_ENGINE
DECISION_STATE: DEFERRED
```

Production engine/model selection is intentionally deferred until a concrete
requirement requires re-validation and explicit CSA authorization. The STT
architecture is retained; only the engine/model choice is held.
