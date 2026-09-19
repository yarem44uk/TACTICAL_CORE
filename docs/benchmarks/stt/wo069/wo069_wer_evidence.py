"""WO-069-CORRECTIVE — WER/CER measurement evidence (benchmark-only, READ-ONLY).

This module answers exactly one question, with evidence:

    Can WER and CER be calculated for Faster-Whisper and Vosk against the
    human-reviewed WO-068 reference transcripts — without modifying the
    human-review artifact?

Design rules (WO-069-CORRECTIVE):

  * the human-review artifact is READ-ONLY evidence — it is hashed, never
    written, and no transcript / callsign / language / confidence value is
    invented, normalized in place or repaired;
  * a reference transcript is used ONLY when the human-review artifact itself
    carries one for that message.  An engine hypothesis is NEVER promoted to a
    reference and a callsign is NEVER used to repair a transcript;
  * WER/CER are computed per record ONLY where BOTH a human reference and an
    engine hypothesis exist.  Every other record is reported explicitly as
    excluded with a machine-readable reason — never silently skipped, never
    estimated, never extrapolated;
  * one deterministic normalization function (``wo069_metrics.normalize``) is
    used for every engine and is published as evidence
    (``wer_cer_normalization.json``).

The module is a pure, engine-agnostic post-processor over an already-produced
benchmark result document.  It does not import, modify or route anything
through EventFactory / EventPipeline / Observation / the journal / Operator Wall
and it never selects a production engine.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import json
import os

import wo069_metrics as M

NOT_MEASURED = "NOT_MEASURED"
UNAVAILABLE = "UNAVAILABLE"

#: Accuracy status vocabulary.
MEASURED = "MEASURED"
NOT_MEASURABLE = "NOT_MEASURABLE"

#: Per-record outcome vocabulary.
EVALUATED = "EVALUATED"
EXCLUDED_NO_HUMAN_REFERENCE = "EXCLUDED_NO_HUMAN_REFERENCE_TRANSCRIPT"
EXCLUDED_NO_HYPOTHESIS = "EXCLUDED_NO_ENGINE_HYPOTHESIS"

#: Deterministic serialization schemas (asserted by the tests).
HYPOTHESIS_MATRIX_FIELDS = (
    "message_id",
    "wav_path",
    "reference_transcript_available",
    "faster_whisper_output_available",
    "vosk_output_available",
)

WER_RESULT_FIELDS = (
    "engine",
    "message_id",
    "status",
    "reference_available",
    "hypothesis_available",
    "reference",
    "hypothesis",
    "wer",
    "cer",
    "reference_token_count",
    "hypothesis_token_count",
    "exclusion_reason",
)

WER_SUMMARY_FIELDS = (
    "engine",
    "records_total",
    "records_with_reference",
    "records_with_hypothesis",
    "evaluated_records",
    "excluded_records",
    "wer",
    "cer",
    "wer_status",
    "cer_status",
)

#: The engines this corrective action is required to cover, in deterministic order.
REQUIRED_ENGINES = ("faster_whisper", "vosk")

NORMALIZATION_POLICY_ID = "wo069-normalization-v1"


def normalization_policy() -> dict:
    """Publish the exact, deterministic normalization applied to BOTH sides.

    Only surface-level, semantics-free operations are permitted.  No word is
    corrected, no name or callsign is repaired, no intended text is inferred.
    """
    return {
        "policy_id": NORMALIZATION_POLICY_ID,
        "function": "wo069_metrics.normalize",
        "applies_to": ["human_reference_transcript", "engine_hypothesis"],
        "identical_for_all_engines": True,
        "steps": [
            "unicode NFKC normalization",
            "lowercase (str.lower)",
            "apostrophes unified to ' (U+0027)",
            "dashes unified to - (U+002D)",
            "all characters outside [word char, whitespace, apostrophe, "
            "Cyrillic block, hyphen] replaced by a space",
            "whitespace collapsed to single spaces and stripped",
        ],
        "tokenization": {
            "wer": "whitespace split of the normalized text",
            "cer": "character sequence of the normalized text with spaces removed",
        },
        "distance": "Levenshtein (unit-cost substitution/insertion/deletion)",
        "forbidden_operations_not_performed": [
            "correcting Ukrainian or Russian words",
            "correcting names or callsigns",
            "inferring intended words",
            "manually improving engine output",
            "rewriting the human reference in the source artifact",
        ],
        "note": "the human-review artifact is never rewritten; normalization is "
                "computed in memory only",
    }


def _engine_map(results: dict) -> dict[str, dict]:
    """Map engine name -> engine result document (deterministic order)."""
    return {e["engine"]: e for e in results.get("engines", [])}


def _per_message_text(engine_result: dict) -> dict[str, str]:
    """Map message_id -> raw hypothesis text for one engine (unmodified)."""
    return {r["message_id"]: (r.get("text") or "") for r in engine_result.get("records", [])}


def _reference_of(human) -> str | None:
    """The human reference transcript, or None.  Never inferred, never repaired."""
    if human is None or not getattr(human, "reference_available", False):
        return None
    value = getattr(human, "human_reference_transcript", None)
    return value if value else None


def build_hypothesis_matrix(results: dict, records_by_id: dict) -> list[dict]:
    """Explicit 67-row hypothesis availability matrix (WO-069-CORRECTIVE §5).

    Execution success alone is NOT treated as proof that usable output exists:
    a column is ``true`` only when the engine actually emitted non-empty text
    for that message.
    """
    engines = _engine_map(results)
    fw = _per_message_text(engines.get("faster_whisper", {}))
    vosk = _per_message_text(engines.get("vosk", {}))
    rows: list[dict] = []
    for message_id in sorted(records_by_id):
        human = records_by_id[message_id]
        rows.append(
            {
                "message_id": message_id,
                "wav_path": getattr(human, "wav_path", ""),
                "reference_transcript_available": _reference_of(human) is not None,
                "faster_whisper_output_available": bool(fw.get(message_id, "").strip()),
                "vosk_output_available": bool(vosk.get(message_id, "").strip()),
            }
        )
    return rows


def evaluate(results: dict, records_by_id: dict) -> dict:
    """Compute per-record WER/CER where both sides exist; exclude the rest.

    Returns ``{"rows": [...], "summary": [...]}`` with deterministic ordering
    (engine name, then message_id).
    """
    engines = _engine_map(results)
    rows: list[dict] = []
    for engine in sorted(engines):
        per_message = _per_message_text(engines[engine])
        for message_id in sorted(records_by_id):
            human = records_by_id[message_id]
            reference = _reference_of(human)
            raw_hypothesis = per_message.get(message_id, "")
            hypothesis = raw_hypothesis.strip()

            if reference is None:
                outcome, reason = EXCLUDED_NO_HUMAN_REFERENCE, EXCLUDED_NO_HUMAN_REFERENCE
            elif not hypothesis:
                outcome, reason = EXCLUDED_NO_HYPOTHESIS, EXCLUDED_NO_HYPOTHESIS
            else:
                outcome, reason = EVALUATED, ""

            wer_value = M.NOT_MEASURED
            cer_value = M.NOT_MEASURED
            ref_tokens = M.NOT_MEASURED
            hyp_tokens = M.NOT_MEASURED
            if outcome == EVALUATED:
                wer_value = M.wer(reference, hypothesis)
                cer_value = M.cer(reference, hypothesis)
                ref_tokens = len(M.normalize(reference).split())
                hyp_tokens = len(M.normalize(hypothesis).split())

            rows.append(
                {
                    "engine": engine,
                    "message_id": message_id,
                    "status": outcome,
                    "reference_available": reference is not None,
                    "hypothesis_available": bool(hypothesis),
                    "reference": reference if reference is not None else UNAVAILABLE,
                    "hypothesis": raw_hypothesis if raw_hypothesis else UNAVAILABLE,
                    "wer": wer_value,
                    "cer": cer_value,
                    "reference_token_count": ref_tokens,
                    "hypothesis_token_count": hyp_tokens,
                    "exclusion_reason": reason,
                }
            )
    return {"rows": rows, "summary": _summarize(rows)}


def _mean(values: list[float]):
    if not values:
        return NOT_MEASURED
    return round(sum(values) / len(values), 6)


def _summarize(rows: list[dict]) -> list[dict]:
    """Aggregate per engine.  WER/CER stay NOT_MEASURED when nothing scored."""
    summary: list[dict] = []
    for engine in sorted({r["engine"] for r in rows}):
        subset = [r for r in rows if r["engine"] == engine]
        evaluated = [r for r in subset if r["status"] == EVALUATED]
        with_reference = [r for r in subset if r["reference_available"]]
        with_hypothesis = [r for r in subset if r["hypothesis_available"]]
        excluded = [r for r in subset if r["status"] != EVALUATED]

        wer_values = [r["wer"] for r in evaluated if isinstance(r["wer"], float)]
        cer_values = [r["cer"] for r in evaluated if isinstance(r["cer"], float)]
        summary.append(
            {
                "engine": engine,
                "records_total": len(subset),
                "records_with_reference": len(with_reference),
                "records_with_hypothesis": len(with_hypothesis),
                "evaluated_records": len(evaluated),
                "excluded_records": len(excluded),
                "excluded_no_reference": sum(
                    1 for r in excluded if r["status"] == EXCLUDED_NO_HUMAN_REFERENCE
                ),
                "excluded_no_hypothesis": sum(
                    1 for r in excluded if r["status"] == EXCLUDED_NO_HYPOTHESIS
                ),
                "wer": _mean(wer_values),
                "cer": _mean(cer_values),
                "wer_status": MEASURED if wer_values else NOT_MEASURABLE,
                "cer_status": MEASURED if cer_values else NOT_MEASURABLE,
                "note": "mean of per-record WER/CER over the evaluated records only; "
                        "no value is estimated for excluded records",
            }
        )
    return summary


def build_diagnostic(results: dict, records_by_id: dict) -> dict:
    """Fail-closed diagnostic: prove exactly what evidence is missing (WO-069-CORRECTIVE §9)."""
    evaluation = evaluate(results, records_by_id)
    summary = evaluation["summary"]
    engines = _engine_map(results)

    reference_count = sum(1 for r in records_by_id.values() if _reference_of(r) is not None)
    wer_measured = any(s["wer_status"] == MEASURED for s in summary)
    cer_measured = any(s["cer_status"] == MEASURED for s in summary)

    missing: list[str] = []
    if reference_count == 0:
        missing.append(
            "no human reference transcript exists for any of the "
            f"{len(records_by_id)} records; the human listening review records "
            "categorical labels only (audible_voice / intelligible / radio_style / "
            "speaker / dialogue_candidate / voice_type / confidence) and carries no "
            "verbatim transcript column"
        )
        missing.append(
            "the WO-068 ground-truth sidecar is UNAVAILABLE with an empty entries[] "
            "list and WO-068 forbids inventing ground truth"
        )
    missing.append(
        "the reference transcript for each record must be entered by a human "
        "listening to the audio and written into the human-review artifact"
    )

    return {
        "schema": "wo069-wer-cer-diagnostic-v1",
        "reference_source": "human_review_artifact:transcript",
        "hypothesis_source": "engine_run_ledger:record.text (raw, unmodified)",
        "normalization_policy": NORMALIZATION_POLICY_ID,
        "records_total": len(records_by_id),
        "reference_transcripts_available": reference_count,
        "wer_status": MEASURED if wer_measured else NOT_MEASURABLE,
        "cer_status": MEASURED if cer_measured else NOT_MEASURABLE,
        "engines": {
            name: {
                "hypotheses_available": sum(
                    1 for v in _per_message_text(engines[name]).values() if v.strip()
                ),
                "records_total": len(records_by_id),
            }
            for name in sorted(engines)
        },
        "missing_evidence": missing,
        "required_next_step": (
            "a human listening review that writes a verbatim transcript per message "
            "into the human-review artifact (or a human-sourced ground-truth sidecar) "
            "is required before WER/CER can be measured; until then WER/CER remain "
            "NOT_MEASURED and are not estimated"
        ),
    }


def _fmt(value) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _write_csv(path: str, fieldnames: tuple, rows: list[dict]) -> str:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in fieldnames})
    return path


def _write_json(path: str, document: dict) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    return path


def write_wer_evidence(outdir: str, results: dict, records_by_id: dict) -> dict:
    """Write the WO-069-CORRECTIVE WER/CER evidence set; return the written paths.

    Files (all regenerable, byte-deterministic for identical inputs):

      * ``wer_cer_results.csv``            — per engine × record, with exclusions
      * ``wer_cer_summary.csv``            — per-engine aggregate
      * ``wer_cer_normalization.json``     — the published normalization policy
      * ``wer_cer_diagnostic.json``        — fail-closed reason trace
      * ``hypothesis_availability_matrix.csv`` — 67-row availability matrix
    """
    os.makedirs(outdir, exist_ok=True)
    evaluation = evaluate(results, records_by_id)
    diagnostic = build_diagnostic(results, records_by_id)
    matrix = build_hypothesis_matrix(results, records_by_id)

    return {
        "wer_cer_results.csv": _write_csv(
            os.path.join(outdir, "wer_cer_results.csv"), WER_RESULT_FIELDS, evaluation["rows"]
        ),
        "wer_cer_summary.csv": _write_csv(
            os.path.join(outdir, "wer_cer_summary.csv"), WER_SUMMARY_FIELDS, evaluation["summary"]
        ),
        "wer_cer_normalization.json": _write_json(
            os.path.join(outdir, "wer_cer_normalization.json"), normalization_policy()
        ),
        "wer_cer_diagnostic.json": _write_json(
            os.path.join(outdir, "wer_cer_diagnostic.json"), diagnostic
        ),
        "hypothesis_availability_matrix.csv": _write_csv(
            os.path.join(outdir, "hypothesis_availability_matrix.csv"),
            HYPOTHESIS_MATRIX_FIELDS,
            matrix,
        ),
    }
