#!/usr/bin/env python3
"""WO-067 — Human-readable benchmark report generator (benchmark-only, offline).

Renders a machine-readable ``wo067_benchmark_results.json`` into
``WO-067-BENCHMARK-REPORT.md``.  It never computes a metric itself and never
names a production engine: it transcribes what was actually measured and marks
everything else NOT MEASURED / NOT AVAILABLE.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from wo067_benchmark import NOT_MEASURED


def _fmt(value) -> str:
    """Render a measurement honestly — never a number where none exists."""
    if value is None:
        return "NOT MEASURED"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _bytes_fmt(value) -> str:
    if not isinstance(value, int):
        return _fmt(value)
    return f"{value} ({value / 1024 / 1024:.1f} MiB)"


def render_report(document: dict) -> str:
    ds = document.get("dataset", {})
    env = document.get("environment", {})
    lines: list[str] = []

    lines.append("# WO-067 — REAL RADIO STT BENCHMARK REPORT")
    lines.append("")
    lines.append("**Stage:** PRE-05 — human review acceptance + benchmark implementation gate")
    lines.append(f"**Benchmark version:** {document.get('benchmark_version')}")
    lines.append(f"**Generated (UTC):** {document.get('generated_at_utc')}")
    lines.append("**Status:** measurement instrument output — engine selection DEFERRED")
    lines.append("")
    lines.append("> **Production engine decision: CSA DECISION REQUIRED (WO-068).**")
    lines.append("> This report does not select, recommend or authorize any engine.")
    lines.append("")

    lines.append("## 1. Provenance — transport vs audio (kept strictly separate)")
    lines.append("")
    prov = document.get("provenance", {})
    lines.append(f"- **TRANSPORT PROVENANCE:** {prov.get('transport_provenance')}")
    lines.append(f"- **AUDIO CONTENT PROVENANCE:** {prov.get('audio_content_provenance')}")
    lines.append(
        f"- **Real radio RF provenance claimed:** "
        f"`{'YES' if prov.get('real_radio_rf_provenance_claimed') else 'NO'}`"
    )
    lines.append(f"- **Evidence package:** `{prov.get('evidence_package')}`")
    lines.append(f"- **Source PCAP SHA-256:** `{prov.get('source_pcap_sha256')}`")
    lines.append("")
    lines.append("Transport provenance is a software test topology and carries **no** RF/SDR claim.")
    lines.append("Audio content provenance is an independent question, settled here by the")
    lines.append("accepted **human** review, not by the transport finding.")
    lines.append("")

    lines.append("## 2. Dataset identity")
    lines.append("")
    lines.append(f"- Manifest: `{ds.get('manifest_path')}`")
    lines.append(f"- Candidates: **{ds.get('candidate_count')}**")
    lines.append(f"- Stream distribution: `{ds.get('stream_distribution')}`")
    lines.append(f"- WAV integrity verified: **{ds.get('wav_integrity_verified')}**")
    lines.append(f"- Included ids: {len(ds.get('included_ids') or [])}")
    lines.append(f"- Excluded ids: {ds.get('excluded_ids') or 'none'}")
    lines.append(f"- Human review accepted: `{ds.get('human_review_accepted')}`")
    lines.append(f"- Ground-truth status: `{ds.get('ground_truth_status')}`")
    lines.append(
        f"- Candidates with human transcript GT: **{ds.get('ground_truth_transcript_count')}**"
    )
    lines.append(
        f"- Candidates with human callsign GT: **{ds.get('ground_truth_callsign_count')}**"
    )
    if ds.get("exclusion_reasons"):
        lines.append("")
        lines.append("Exclusions (never silent):")
        for ex in ds["exclusion_reasons"]:
            lines.append(f"  - `{ex.get('candidate_id')}`: {'; '.join(ex.get('problems', []))}")
    lines.append("")

    lines.append("## 3. Environment (reproducibility record)")
    lines.append("")
    lines.append(f"- OS / kernel: {env.get('os')} {env.get('os_release')} ({env.get('machine')})")
    lines.append(f"- Python: {env.get('python_version')} ({env.get('python_implementation')})")
    lines.append(f"- CPU: {env.get('cpu_model')} × {env.get('cpu_core_count')}")
    lines.append(f"- RAM: {_bytes_fmt(env.get('ram_bytes'))}")
    lines.append(f"- GPU available: `{env.get('gpu_available')}`")
    lines.append(f"- VRAM total: {_bytes_fmt(env.get('vram_total_bytes'))}")
    lines.append(f"- FFmpeg: {env.get('ffmpeg_version')}")
    lines.append(f"- Language / device: {env.get('language')} / {env.get('device')}")
    pkgs = env.get("packages", {})
    lines.append("- Package versions:")
    for name, ver in pkgs.items():
        lines.append(f"  - {name}: `{ver if ver is not None else 'NOT INSTALLED'}`")
    lines.append("")

    lines.append("## 4. Engine results")
    lines.append("")
    for idx, eng in enumerate(document.get("engines", []), start=1):
        avail = eng.get("engine_availability", {})
        model = eng.get("model", {})
        cfg = eng.get("configuration", {})
        agg = eng.get("aggregate", {})
        timing = agg.get("timing", {})
        rel = agg.get("reliability", {})
        res = agg.get("resources", {})
        acc = agg.get("accuracy", {})
        cs = eng.get("callsign_accuracy", {})

        lines.append(f"### 4.{idx} `{eng.get('engine')}`")
        lines.append("")
        lines.append(f"- Availability: **{'READY' if avail.get('ready') else 'BLOCKED'}**")
        lines.append(f"- Availability reason: {avail.get('reason')}")
        lines.append(f"- Benchmark executed: `{eng.get('benchmark_executed')}`")
        lines.append(f"- Model id / path: `{model.get('model_id')}`")
        lines.append(f"- Quantization / device / language: "
                     f"`{cfg.get('quantization')}` / `{cfg.get('device')}` / `{cfg.get('language')}`")
        lines.append(f"- Beam size / vad_filter: `{cfg.get('beam_size')}` / `{cfg.get('vad_filter')}`")
        lines.append(f"- Cold start: {_fmt(eng.get('cold_start_seconds'))} s")
        lines.append("")
        lines.append("**Timing**")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("| --- | --- |")
        lines.append(f"| median latency (s) | {_fmt(timing.get('median_latency_seconds'))} |")
        lines.append(f"| p95 latency (s) | {_fmt(timing.get('p95_latency_seconds'))} |")
        lines.append(f"| median RTF | {_fmt(timing.get('median_rtf'))} |")
        lines.append(f"| p95 RTF | {_fmt(timing.get('p95_rtf'))} |")
        lines.append(f"| RTF definition | `{timing.get('rtf_definition')}` |")
        lines.append("")
        lines.append("**Reliability**")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("| --- | --- |")
        for key in (
            "total_runs",
            "successful_runs",
            "failed_runs",
            "timeout_runs",
            "unavailable_runs",
            "exception_count",
            "failure_rate",
        ):
            lines.append(f"| {key} | {_fmt(rel.get(key))} |")
        lines.append("")
        lines.append("**System resources**")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("| --- | --- |")
        lines.append(f"| CPU user seconds total | {_fmt(res.get('cpu_user_seconds_total'))} |")
        lines.append(f"| CPU user seconds median/file | {_fmt(res.get('cpu_user_seconds_median_per_file'))} |")
        lines.append(f"| Peak RSS max | {_bytes_fmt(res.get('peak_rss_bytes_max'))} |")
        lines.append(f"| GPU utilization % | {_fmt(res.get('gpu_utilization_pct'))} |")
        lines.append(f"| VRAM used max | {_bytes_fmt(res.get('vram_used_bytes_max'))} |")
        lines.append("")
        lines.append("**Accuracy**")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("| --- | --- |")
        lines.append(f"| ground-truth scored candidates | {_fmt(acc.get('ground_truth_scored_candidates'))} |")
        lines.append(f"| WER mean | {_fmt(acc.get('wer_mean'))} |")
        lines.append(f"| WER median | {_fmt(acc.get('wer_median'))} |")
        lines.append(f"| CER mean | {_fmt(acc.get('cer_mean'))} |")
        lines.append(f"| CER median | {_fmt(acc.get('cer_median'))} |")
        lines.append(f"| exact match rate | {_fmt(acc.get('exact_match_rate'))} |")
        lines.append("")
        lines.append("**Callsign accuracy**")
        lines.append("")
        lines.append(f"- Status: `{cs.get('status')}`")
        if cs.get("status") == NOT_MEASURED:
            lines.append(f"- Reason: {cs.get('reason')}")
        else:
            lines.append(f"- Scored candidates: {_fmt(cs.get('scored_candidates'))}")
            lines.append(f"- Exact / normalized / missed / false / not present: "
                         f"{cs.get('exact_match')} / {cs.get('normalized_match')} / "
                         f"{cs.get('missed')} / {cs.get('false')} / {cs.get('not_present')}")
            lines.append(f"- Accuracy: {_fmt(cs.get('accuracy'))}")
            lines.append(f"- Normalization: {cs.get('normalization_policy')}")
        lines.append("")

    lines.append("## 5. Explicit NOT MEASURED / NOT AVAILABLE fields")
    lines.append("")
    lines.append("| field | value |")
    lines.append("| --- | --- |")
    for eng in document.get("engines", []):
        agg = eng.get("aggregate", {})
        lines.append(f"| {eng.get('engine')} WER | {_fmt(agg.get('accuracy', {}).get('wer_mean'))} |")
        lines.append(f"| {eng.get('engine')} CER | {_fmt(agg.get('accuracy', {}).get('cer_mean'))} |")
        lines.append(
            f"| {eng.get('engine')} GPU utilization | "
            f"{_fmt(agg.get('resources', {}).get('gpu_utilization_pct'))} |"
        )
        lines.append(
            f"| {eng.get('engine')} callsign accuracy | "
            f"{_fmt(eng.get('callsign_accuracy', {}).get('accuracy'))} |"
        )
    lines.append("")

    lines.append("## 6. Notes")
    lines.append("")
    for note in document.get("notes", []) or ["(none)"]:
        lines.append(f"- {note}")
    lines.append("")

    lines.append("## 7. Engine selection")
    lines.append("")
    lines.append(f"**{document.get('production_engine_selection')}**")
    lines.append("")
    lines.append(document.get("production_engine_selection_note", ""))
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wo067_report")
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--report-version", default=None)
    args = parser.parse_args(argv)

    with open(args.results, encoding="utf-8") as fh:
        document = json.load(fh)

    text = render_report(document)
    out = args.output or os.path.join(
        os.path.dirname(os.path.abspath(args.results)), "WO-067-BENCHMARK-REPORT.md"
    )
    if os.path.exists(out) and args.report_version:
        stem, ext = os.path.splitext(out)
        out = f"{stem}.{args.report_version}{ext}"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"report written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())