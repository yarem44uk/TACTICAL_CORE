"""WO-069 — Evidence generation: CSV artifacts + human-readable report.

Writes the WO-069 evidence directory.  Every value is either measured or
explicitly ``NOT_MEASURED`` / ``NOT_AVAILABLE`` / ``UNAVAILABLE``.  The report
never declares a production winner: engine selection is a separate Chief
Systems Architect decision (ADR-014 Part 2).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

import wo069_metrics as M
import wo069_wer_evidence as W

NOT_MEASURED = "NOT_MEASURED"
UNAVAILABLE_TEXT = "UNAVAILABLE"

#: Deterministic per-file result schema (asserted by the tests).
BENCHMARK_RESULT_FIELDS = (
    "engine",
    "model",
    "message_id",
    "status",
    "reference_available",
    "transcript_available",
    "wer",
    "cer",
    "callsign_match",
    "processing_time_ms",
    "rtf",
    "error",
)


def _fmt(value) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> str:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in fieldnames})
    return path


def _write_json(path: str, document: dict) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    return path


def _speech_presence_diagnostic(engine_result: dict, records_by_id: dict) -> dict:
    """Supplemental, explicitly NON-WER diagnostic.

    Compares engine output emptiness against the human listener's categorical
    ``audible_voice`` label.  It is NOT an accuracy metric and MUST NOT be read
    as a WER surrogate.
    """
    speech = {"correct": 0, "total": 0}
    nonspeech = {"correct": 0, "total": 0}
    for record in engine_result["records"]:
        human = records_by_id.get(record["message_id"])
        if human is None:
            continue
        label = (human.human_audible_voice or "").upper()
        produced_text = bool((record.get("text") or "").strip())
        if label == "YES":
            speech["total"] += 1
            speech["correct"] += 1 if produced_text else 0
        elif label == "NO":
            nonspeech["total"] += 1
            nonspeech["correct"] += 1 if not produced_text else 0
    return {
        "metric": "SPEECH_PRESENCE_DIAGNOSTIC (not a WER substitute)",
        "speech_label_yes_with_output": f"{speech['correct']}/{speech['total']}",
        "nonspeech_label_no_with_empty_output": f"{nonspeech['correct']}/{nonspeech['total']}",
    }


def build_evidence_rows(results: dict, records_by_id: dict) -> dict:
    """Build every evidence table from the benchmark result document."""
    benchmark_rows: list[dict] = []
    transcript_rows: list[dict] = []
    callsign_rows: list[dict] = []
    runtime_rows: list[dict] = []
    resource_rows: list[dict] = []

    for engine_result in results["engines"]:
        engine = engine_result["engine"]
        model = (engine_result.get("configuration") or {}).get("model_path") or ""
        cold_start = engine_result.get("cold_start_ms", NOT_MEASURED)
        gpu_value = str(results["environment"].get("gpu", "")).upper()
        gpu_state = "NOT_AVAILABLE" if "NOT" in gpu_value and "AVAILABLE" in gpu_value else NOT_MEASURED
        vram_state = (gpu_state if gpu_state == "NOT_AVAILABLE"
                      else results["environment"].get("gpu_memory", NOT_MEASURED))

        for record in engine_result["records"]:
            human = records_by_id.get(record["message_id"])
            reference_available = bool(human.reference_available) if human else False
            hypothesis = record.get("text")
            transcript_available = bool((hypothesis or "").strip())

            wer_value = M.NOT_MEASURED
            cer_value = M.NOT_MEASURED
            if human is not None and reference_available:
                wer_value = M.wer(human.human_reference_transcript, hypothesis)
                cer_value = M.cer(human.human_reference_transcript, hypothesis)

            callsign_outcome = M.NOT_MEASURED
            if human is not None and human.callsign_reference_available:
                callsign_outcome = M.callsign_outcome(human.human_callsign, hypothesis)

            benchmark_rows.append(
                {
                    "engine": engine,
                    "model": model,
                    "message_id": record["message_id"],
                    "status": record["status"],
                    "reference_available": reference_available,
                    "transcript_available": transcript_available,
                    "wer": wer_value,
                    "cer": cer_value,
                    "callsign_match": callsign_outcome,
                    "processing_time_ms": record.get("latency_ms"),
                    "rtf": record.get("rtf"),
                    "error": record.get("error") or "",
                }
            )
            transcript_rows.append(
                {
                    "engine": engine,
                    "message_id": record["message_id"],
                    "reference_available": reference_available,
                    "human_audible_voice": human.human_audible_voice if human else "",
                    "human_intelligible": human.human_intelligible if human else "",
                    "human_voice_type": human.human_voice_type if human else "",
                    "reference_transcript": (
                        human.human_reference_transcript
                        if human is not None and reference_available
                        else UNAVAILABLE_TEXT
                    ),
                    "hypothesis_raw": hypothesis or "",
                    "hypothesis_normalized": M.normalize(hypothesis) if hypothesis else "",
                }
            )
            callsign_rows.append(
                {
                    "engine": engine,
                    "message_id": record["message_id"],
                    "callsign_reference_available": bool(
                        human.callsign_reference_available
                    ) if human else False,
                    "human_callsign": (
                        human.human_callsign if human and human.callsign_reference_available
                        else UNAVAILABLE_TEXT
                    ),
                    "callsign_outcome": callsign_outcome,
                    "note": (
                        "callsign evaluation is separate from transcript WER/CER"
                    ),
                }
            )
            runtime_rows.append(
                {
                    "engine": engine,
                    "model": model,
                    "message_id": record["message_id"],
                    "status": record["status"],
                    "audio_duration_seconds": record.get("audio_duration_seconds"),
                    "processing_time_ms": record.get("latency_ms"),
                    "latency_seconds": (
                        round(record["latency_ms"] / 1000.0, 6)
                        if record.get("latency_ms") is not None
                        else NOT_MEASURED
                    ),
                    "rtf": record.get("rtf"),
                    "cold_start_ms": cold_start,
                }
            )
            resource_rows.append(
                {
                    "engine": engine,
                    "model": model,
                    "message_id": record["message_id"],
                    "peak_rss_kb": record.get("peak_rss_kb"),
                    "cpu_user_s": record.get("cpu_user_s"),
                    "cpu_sys_s": record.get("cpu_sys_s"),
                    "gpu_utilization_pct": gpu_state,
                    "vram_bytes": vram_state,
                }
            )

        # Engine-level aggregate rows (message_id = ALL).
        aggregate = engine_result.get("aggregate", {})
        timing = aggregate.get("timing", {})
        resources = aggregate.get("resources", {})
        runtime_rows.append(
            {
                "engine": engine,
                "model": model,
                "message_id": "ALL",
                "status": engine_result["engine_status"],
                "audio_duration_seconds": results["dataset"]["total_duration_seconds"],
                "processing_time_ms": NOT_MEASURED,
                "latency_seconds": timing.get("median_latency_seconds", NOT_MEASURED),
                "rtf": timing.get("median_rtf", NOT_MEASURED),
                "cold_start_ms": cold_start,
            }
        )
        resource_rows.append(
            {
                "engine": engine,
                "model": model,
                "message_id": "ALL",
                "peak_rss_kb": resources.get("peak_rss_bytes_max", NOT_MEASURED),
                "cpu_user_s": resources.get("cpu_user_seconds_total", NOT_MEASURED),
                "cpu_sys_s": NOT_MEASURED,
                "gpu_utilization_pct": gpu_state,
                "vram_bytes": vram_state,
            }
        )

    return {
        "benchmark_results": benchmark_rows,
        "transcript_comparison": transcript_rows,
        "callsign_results": callsign_rows,
        "runtime_metrics": runtime_rows,
        "resource_metrics": resource_rows,
    }


def write_evidence(outdir: str, results: dict, records_by_id: dict) -> dict:
    """Write the full WO-069 evidence set; returns the written paths."""
    os.makedirs(outdir, exist_ok=True)
    tables = build_evidence_rows(results, records_by_id)

    paths = {
        "benchmark_results.csv": _write_csv(
            os.path.join(outdir, "benchmark_results.csv"),
            list(BENCHMARK_RESULT_FIELDS),
            tables["benchmark_results"],
        ),
        "transcript_comparison.csv": _write_csv(
            os.path.join(outdir, "transcript_comparison.csv"),
            [
                "engine", "message_id", "reference_available", "human_audible_voice",
                "human_intelligible", "human_voice_type", "reference_transcript",
                "hypothesis_raw", "hypothesis_normalized",
            ],
            tables["transcript_comparison"],
        ),
        "callsign_results.csv": _write_csv(
            os.path.join(outdir, "callsign_results.csv"),
            ["engine", "message_id", "callsign_reference_available", "human_callsign",
             "callsign_outcome", "note"],
            tables["callsign_results"],
        ),
        "runtime_metrics.csv": _write_csv(
            os.path.join(outdir, "runtime_metrics.csv"),
            ["engine", "model", "message_id", "status", "audio_duration_seconds",
             "processing_time_ms", "latency_seconds", "rtf", "cold_start_ms"],
            tables["runtime_metrics"],
        ),
        "resource_metrics.csv": _write_csv(
            os.path.join(outdir, "resource_metrics.csv"),
            ["engine", "model", "message_id", "peak_rss_kb", "cpu_user_s", "cpu_sys_s",
             "gpu_utilization_pct", "vram_bytes"],
            tables["resource_metrics"],
        ),
        "environment_manifest.json": _write_json(
            os.path.join(outdir, "environment_manifest.json"), results["environment"]
        ),
        "dataset_manifest.json": _write_json(
            os.path.join(outdir, "dataset_manifest.json"), results["dataset"]
        ),
    }
    paths["benchmark_results.json"] = _write_json(
        os.path.join(outdir, "benchmark_results.json"), results
    )
    # WO-069-CORRECTIVE — explicit WER/CER measurement evidence (fail-closed).
    paths.update(W.write_wer_evidence(outdir, results, records_by_id))
    paths["WO-069-EVIDENCE-REPORT.md"] = write_report(
        os.path.join(outdir, "WO-069-EVIDENCE-REPORT.md"), results, records_by_id
    )
    return paths


def render_report(results: dict, records_by_id: dict) -> str:
    """Render the human-readable evidence report (no production winner)."""
    dataset = results["dataset"]
    env = results["environment"]
    lines: list[str] = []
    add = lines.append

    add("# WO-069 — REAL RADIO STT BENCHMARK (CONTROLLED RE-ENTRY)")
    add("")
    add(f"**Work Order:** WO-069  ")
    add(f"**Generated (UTC):** {results['generated_at_utc']}  ")
    add(f"**Repository HEAD:** `{env.get('repo_head')}`  ")
    add(f"**Status:** {results['status']}")
    add("")
    add("---")
    add("")
    add("## BLUF")
    add("")
    add(
        f"{dataset['record_count']} of {dataset['expected_record_count']} human-reviewed "
        f"real-radio message records were located and integrity-verified read-only "
        f"({dataset['total_duration_seconds']} s total audio). "
        f"{len(results['engines'])} candidate engines were exercised on the identical "
        f"dataset. Reference transcripts available: "
        f"{dataset['reference_transcript_count']} — so WER/CER are "
        f"`NOT_MEASURED`, and the benchmark carries measured runtime, resource and "
        f"reliability evidence only. **No production engine is selected.**"
    )
    add("")
    add("## 1. Dataset")
    add("")
    add(f"- dataset root: `{dataset['dataset_root']}`")
    add(f"- records expected / actual: {dataset['expected_record_count']} / {dataset['record_count']} ({dataset['completeness']})")
    add(f"- WAV present + integrity-verified: {dataset['wav_count']}")
    add(f"- total audio duration: {dataset['total_duration_seconds']} s")
    add(f"- human-reviewed rows: {dataset['human_reviewed_count']} (pending {dataset['human_review_pending_count']})")
    add(f"- human review source: `{dataset['human_review_source_path']}` "
        f"(sha256 `{dataset['human_review_source_sha256']}`)")
    add(f"- dataset manifest sha256: `{dataset['dataset_manifest_sha256']}`")
    add(f"- reference transcripts: {dataset['reference_transcript_status']} "
        f"({dataset['reference_transcript_count']}) — {dataset['reference_transcript_reason']}")
    add(f"- reference callsigns: {dataset['reference_callsign_status']} "
        f"({dataset['reference_callsign_count']})")
    resolution = dataset.get("artifact_resolution", {})
    add("")
    add("### 1.1 Artifact resolution (named vs present)")
    add("")
    add(f"- work order names `{resolution.get('named_in_work_order')}` — "
        f"found in environment: **{resolution.get('named_artifact_found')}**")
    add(f"- dataset manifest present: {resolution.get('dataset_manifest_present')}")
    add(f"- ground-truth sidecar present: {resolution.get('ground_truth_present')}")
    add(f"- human-review CSV present: {resolution.get('human_review_csv_present')}")
    add("")
    add("## 2. Environment")
    add("")
    add(f"- python: {env.get('python_version')}  ")
    add(f"- os: {env.get('os')}  ")
    add(f"- kernel: {env.get('kernel')}  ")
    add(f"- cpu: {env.get('cpu')} ({env.get('cpu_count')} cores)  ")
    add(f"- ram: {env.get('ram')} bytes; cgroup memory.max: {env.get('cgroup_memory_max')}  ")
    add(f"- gpu: {env.get('gpu')} ({env.get('gpu_evidence')})  ")
    add(f"- dataset hash: `{env.get('dataset_hash')}`")
    add("")
    add("## 3. Engines — measured results")
    add("")
    for engine_result in results["engines"]:
        configuration = engine_result.get("configuration", {})
        aggregate = engine_result.get("aggregate", {})
        timing = aggregate.get("timing", {})
        reliability = aggregate.get("reliability", {})
        resources = aggregate.get("resources", {})
        add(f"### {engine_result['engine']}")
        add("")
        add(f"- engine_status: **{engine_result['engine_status']}**")
        add(f"- model: `{configuration.get('model_path')}`")
        add(f"- device / compute_type: {configuration.get('device')} / {configuration.get('compute_type')}")
        add(f"- sample-rate policy: {configuration.get('sample_rate_policy')}")
        add(f"- cold start (model load): {engine_result.get('cold_start_ms')} ms")
        add(f"- exit code: {engine_result.get('exit_code')}")
        if engine_result.get("failure_reason"):
            add(f"- failure_reason: {engine_result['failure_reason']}")
        if engine_result.get("oom_evidence"):
            add(f"- oom_evidence: {engine_result['oom_evidence']}")
        add(f"- success / failed / timeout: {reliability.get('successful_runs')} / "
            f"{reliability.get('failed_runs')} / {reliability.get('timeout_runs')}")
        add(f"- failure rate: {reliability.get('failure_rate')}")
        add(f"- median latency: {timing.get('median_latency_seconds')} s; "
            f"p95: {timing.get('p95_latency_seconds')} s")
        add(f"- median RTF: {timing.get('median_rtf')}; p95 RTF: {timing.get('p95_rtf')}")
        add(f"- peak RSS: {resources.get('peak_rss_bytes_max')} bytes; "
            f"cpu user total: {resources.get('cpu_user_seconds_total')} s")
        accuracy = aggregate.get("accuracy", {})
        add(f"- WER: {accuracy.get('wer_mean')} (scored candidates: "
            f"{accuracy.get('ground_truth_scored_candidates')})")
        add(f"- CER: {accuracy.get('cer_mean')}")
        callsign = engine_result.get("callsign_accuracy", {})
        add(f"- callsign accuracy: {callsign.get('accuracy')} ({callsign.get('status')})")
        diagnostic = _speech_presence_diagnostic(engine_result, records_by_id)
        add(f"- {diagnostic['metric']}: "
            f"audible=YES with output {diagnostic['speech_label_yes_with_output']}; "
            f"audible=NO with empty output {diagnostic['nonspeech_label_no_with_empty_output']}")
        add("")
    add("## 4. WER/CER measurement (WO-069-CORRECTIVE)")
    add("")
    wer_diag = W.build_diagnostic(results, records_by_id)
    wer_eval = W.evaluate(results, records_by_id)
    add(f"- WER_STATUS: **{wer_diag['wer_status']}**")
    add(f"- CER_STATUS: **{wer_diag['cer_status']}**")
    add(f"- REFERENCE_SOURCE: `{wer_diag['reference_source']}`")
    add(f"- HYPOTHESIS_SOURCE: `{wer_diag['hypothesis_source']}`")
    add(f"- NORMALIZATION_POLICY: `{wer_diag['normalization_policy']}`")
    add(f"- reference transcripts available: {wer_diag['reference_transcripts_available']}"
        f"/{wer_diag['records_total']}")
    for entry in wer_eval["summary"]:
        add(f"- **{entry['engine']}** — evaluated_records: {entry['evaluated_records']}"
            f"/{entry['records_total']}; WER: {entry['wer']} ({entry['wer_status']}); "
            f"CER: {entry['cer']} ({entry['cer_status']}); excluded: "
            f"{entry['excluded_records']} "
            f"(no reference {entry['excluded_no_reference']}, "
            f"no hypothesis {entry['excluded_no_hypothesis']})")
    add("")
    add("Excluded records: every dataset record is excluded with the explicit reason "
        "`EXCLUDED_NO_HUMAN_REFERENCE_TRANSCRIPT`, because the human-review artifact "
        "carries no verbatim transcript for any message. No WER/CER value is estimated.")
    add("")
    add("## 5. Failures and timeouts")
    add("")
    any_failure = False
    for engine_result in results["engines"]:
        failing = [r for r in engine_result["records"] if r["status"] not in ("SUCCESS",)]
        if not failing and engine_result["engine_status"] == "COMPLETED":
            continue
        any_failure = True
        add(f"- **{engine_result['engine']}** ({engine_result['engine_status']}): "
            f"{engine_result.get('failure_reason') or 'per-file failures below'}")
        for record in failing[:20]:
            add(f"    - {record['message_id']}: {record['status']} — {record.get('error')}")
        if len(failing) > 20:
            add(f"    - … {len(failing) - 20} more (see benchmark_results.csv)")
    if not any_failure:
        add("- none: every executed engine completed without a per-file failure.")
    add("")
    add("## 6. Production architecture")
    add("")
    add("- benchmark layer is isolated: no EventFactory / EventPipeline / Observation / "
        "journal / Operator Wall involvement, no production STT seam change.")
    add("- production engine selected: **NO** (ADR-014 Part 2 remains a CSA decision).")
    add("")
    add("## 7. Evidence files")
    add("")
    for name in ("benchmark_results.csv", "transcript_comparison.csv", "callsign_results.csv",
                 "runtime_metrics.csv", "resource_metrics.csv", "environment_manifest.json",
                 "dataset_manifest.json", "benchmark_results.json",
                 "wer_cer_results.csv", "wer_cer_summary.csv",
                 "wer_cer_normalization.json", "wer_cer_diagnostic.json",
                 "hypothesis_availability_matrix.csv"):
        add(f"- `{name}`")
    add("")
    add("---")
    add("")
    add(f"_Generated by the WO-069 benchmark layer at {datetime.now(timezone.utc).isoformat()}._")
    add("")
    return "\n".join(lines)


def write_report(path: str, results: dict, records_by_id: dict) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_report(results, records_by_id))
    return path
