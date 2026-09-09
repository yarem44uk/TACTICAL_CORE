# RTP Benchmark Area (WO-043/RTP, WO-044-CORR-01)

This directory holds standalone, deterministic reference and validation tooling
for real-time transport protocol (RTP) / G.711 audio ingest and per-transmission
segmentation. It is the canonical repository home for the accepted RTP benchmark
artifacts imported under WO-043/RTP and WO-044-CORR-01.

## WO identifier collision — WO-043/STT vs WO-043/RTP

The same work-order number `WO-043` is used for two distinct benchmark domains.
The repository paths are the namespace that distinguishes them:

| Identifier | Domain | Canonical location |
| --- | --- | --- |
| `WO-043/STT` | Deterministic real-radio transmission segmentation (WAV energy/RMS -> RADIO-NNNN manifest) | `docs/benchmarks/stt/` |
| `WO-043/RTP` | Universal RTP/G.711 multicast audio ingest (pcap and live -> per-transmission WAV) | `docs/benchmarks/rtp/` |

These are separate artifact families. The STT implementation lives under
`docs/benchmarks/stt/` (`wo043_segment.py`, `test_wo043_segment.py`) and must not
be renamed, replaced, merged, or reinterpreted as the RTP family. The RTP
implementation lives under `docs/benchmarks/rtp/` and is documented here.

## Contents

| Artifact | Purpose |
| --- | --- |
| `wo043_ingest.py` | Offline RTP/G.711 ingest reference implementation. Reads a `.pcap`/`.pcapng`, auto-detects the multicast audio flows, classifies each flow by session shape (CONTINUOUS-STREAM vs SHORT-SSRC), decodes G.711 A-law (PT=8) to PCM, reconstructs one WAV per transmission, verifies ts/seq contiguity and frame counts, and writes a manifest CSV with a SHA-256 per segment. |
| `test_wo043_ingest.py` | Offline WO-043 RTP regression tests. |
| `wo043_live.py` | Live UDP multicast RTP/G.711 ingest implementation — the real-time analogue of `wo043_ingest.py`. Reads packets off a UDP multicast socket, applies the verified multicast receiver rules (per-source flow isolation, deferred cold-start boundary decision), and incorporates the accepted WO-044-CORR-01 corrections (AUTO cold-start over-split fix and socket/multicast source-flow isolation). |
| `test_wo044_corr.py` | Regression tests for the WO-044-CORR-01 live-path corrections. |

## Standalone benchmark tooling vs production

These files are **standalone benchmark/reference tooling**. They import only the
Python standard library and reimplement the RTP parse, A-law decode, and
segmentation primitives internally.

They are **NOT** the production implementation under `backend/app/audio/`.
Importing these benchmark files into Git does **not** replace, override, or modify
the production RTP code path. The production RTP receiver/decoder remains under
`backend/app/audio/`.

## Provenance

The four artifacts below were accepted through the WO-043 / WO-044-CORR-01
validation chain and imported into Git as the canonical repository copies.
SHA-256 values are preserved exactly as accepted.

```
wo043_ingest.py
d7cb50f3425497dc64ca3a2d2c56cf9f1a1f2952bcd6016be4de780244473e93

test_wo043_ingest.py
7d13f3050ff73032a7f94721f9d117a7cb010448420962814e45059586804364

wo043_live.py
04440f3342918dfd0d63bde4c018732734c944dcbfc3726c9026337165c475d9

test_wo044_corr.py
ebbd31ddf5fa544ad10f0de2c823acd3ac384ef032103e803b733f20412a4cc7
```

## Binary fixtures

Following the repository convention, large binary capture fixtures are **not**
committed as ordinary source artifacts. No `.pcap`, `.pcapng`, `.wav`, or other
binary capture file is tracked here. The offline ingest tool takes the capture
path as a CLI argument; the live tool reads directly from a UDP socket or replays
a capture passed via `--replay`.

## How to run

The tooling requires only the Python standard library.

```bash
# Offline ingest: pcap -> per-transmission WAV + manifest
python3 wo043_ingest.py <capture.pcap|.pcapng> <outdir> [--gap 1.0] \
    [--min-payload 160] [--verify-ffmpeg] [--json] [--boundary-eps 0.001]

# Live ingest: receive UDP multicast RTP/G.711 -> per-transmission WAV
python3 wo043_live.py --group 239.233.58.10 --port 5011 \
    --group 239.233.58.20 --port 5022 --outdir /opt/data/output/live \
    --gap 1.0 --interface 127.0.0.1

# Replay a capture through the same live pipeline (regression)
python3 wo043_live.py --replay /path/to/gen_traffic.pcap --outdir /opt/data/output/live_replay

# Run the regression tests
python3 test_wo043_ingest.py
python3 test_wo044_corr.py
```

The live tool supports `--shape {auto,continuous,short-ssrc}` to force the
per-flow boundary policy instead of inferring it dynamically, `--runtime N` to
run for N seconds, and repeatable `--group` / `--port` pairs (one port per
group).

## Accepted validation scope

The accepted validation covered:

- offline RTP segmentation baseline (`.pcap`/`.pcapng` ingest, per-transmission WAV reconstruction, manifest SHA-256)
- AUTO / SHORT-SSRC / CONTINUOUS boundary modes
- source-flow isolation (live socket mode keys segmentation state by the full `(src_ip, sport, dport)` flow)
- live UDP multicast validation
- WO-044-CORR-01 regression tests (AUTO cold-start over-split, socket source-flow isolation)

This does not claim broader multi-host multicast validation beyond what was
actually performed.
