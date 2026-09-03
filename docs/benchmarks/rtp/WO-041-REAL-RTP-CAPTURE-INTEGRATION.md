# WO-041 — Real RTP Capture Integration

**Repository:** yarem44uk/TACTICAL_CORE
**Branch:** wo-041-real-rtp-capture
**Baseline SHA:** ca5aa831d56df2f19e01ce33ac1a0337de6160d6
**Date:** 2026-09-03
**Author:** Tactical Core Engineering Team

---

## A. Scope

WO-041 (REAL RTP CAPTURE INTEGRATION) validates that TACTICAL_CORE can consume
the **real captured RTP radio stream** (`radio_rtp.pcapng`) through the existing
WO-039 audio path and produce a valid PCM / WAV audio master.

This WO is **NOT** about STT. It does **not** select an STT engine, does **not**
install or download a model, does **not** call any cloud STT, does **not** alter
ADR-014, and does **not** claim transcript accuracy. The deliverable is
deterministic, reproducible proof of the integration boundary:

```
REAL RTP CAPTURE
    -> RTP PACKET INPUT
    -> RTP VALIDATION
    -> G.711 A-law PAYLOAD
    -> PCM AUDIO
    -> WAV MASTER
```

---

## B. Source evidence

| Field | Value |
| --- | --- |
| Evidence file | `radio_rtp.pcapng` |
| On-disk path | `/opt/data/wo041_evidence/radio_rtp.pcapng` |
| Supplied fixture | `/opt/data/uploads/<id>/test.pcapng` (14 identical copies, one capture) |
| File SHA-256 | `971adf63787d0d815670b80bdc06d17251773e5d65205630d24ddba18aff5174` |
| File size | 464,660 bytes |
| Capture host | 64-bit Windows 11 (25H2, build 26200) |
| Capture interface | Npcap `NPF_{F0FF900A-7CAD-47BC-A02E-E7F1D13F5481}` |
| Interface description | `Підключення через локальну мережу` (Ukrainian: "connection via local network") |
| Link type | Ethernet (1) |

The capture is the real radio multicast stream (supplied as evidence). It is not
committed to the repository — it lives at the external evidence fixture path, and
the WO-041 tests fail (by design) when it is unavailable.

---

## C. RTP structure (independently verified)

Total packet blocks: **2008**. The target audio flow is:

| Field | Value |
| --- | --- |
| Source IP | `172.19.4.118` |
| Multicast destination | `239.233.18.30` |
| UDP port | `5033` (source and destination) |
| RTP version | 2 |
| Payload type | 8 (G.711 A-law / PCMA) |
| SSRC | `0x1fff2b07` = 536816391 (single, consistent) |
| Payload bytes/packet | 160 |
| RTP timestamp delta | +160 samples/packet (20 ms @ 8000 Hz) |
| Sequence start | 14033 |
| Sequence end | 16253 |
| Sequence span | 2221 |
| Captured packets | 1772 |
| Malformed packets | 0 |
| Duplicate sequence numbers | 0 |
| Out-of-order packets | 0 |

Non-target traffic present in the capture (noise, excluded from the target flow):
`172.19.4.118:5034 -> 239.233.18.30:5034` (8 packets, PT 72, marker set),
broadcast `*.5678`, and LLMNR `224.0.0.252:5355`.

**Conclusion:** the supplied values were confirmed independently. The payload is
already RTP (UDP -> RTP -> G.711 A-law); no second RTP header was added and no
UDP-to-RTP conversion was required.

---

## D. Codec

`G.711 A-law / PCMA`, `8000 Hz`, mono — confirmed independently.

- 160 A-law bytes per packet, one byte per sample -> 160 samples per 20 ms frame.
- RTP timestamp advances by 160 each packet, confirming 8000 Hz / 20 ms packetization.
- Decoded PCM is `S16LE` (16-bit little-endian), mono, 8000 Hz.
- The A-law decoder matches the reference ffmpeg `alaw` decoder **byte-for-byte**
  over the full 283,520-sample payload.

---

## E. Reconstruction

Packet ordering was preserved (capture order == sequence order), and the stream
was reconstructed in sequence order. The tracker observed **3 sequence gap bursts**
(no silent fill; missing samples are never invented):

| Gap burst | Sequence jump | Missing packets | Timestamp jump |
| --- | --- | --- | --- |
| 1 | 14272 -> 14456 | 183 | 29,440 (184 x 160) |
| 2 | 15334 -> 15482 | 147 | 23,680 (148 x 160) |
| 3 | 15823 -> 15943 | 119 | 19,200 (120 x 160) |

Total inferred lost packets: **449**. The RTP timestamp jump at each gap equals
`gap_packets * 160`, confirming a continuous sender clock and network/capture
loss (not a sender pause). No duplicates, no malformed packets, no out-of-order
packets.

---

## F. Decode

| Field | Value |
| --- | --- |
| PCM format | S16LE (16-bit signed little-endian) |
| Sample rate | 8000 Hz |
| Channels | 1 (mono) |
| Sample count | 283,520 |
| PCM bytes | 567,040 |
| Duration | 35.44 s |
| PCM SHA-256 | `f3d973f3ed51394c94104c41f6e9ff6671e0210dd82a6bae62faab1530e8450c` |
| ffmpeg reference | byte-for-byte match |

Audio profile (tone-vs-speech discrimination): `distinct=256` (expected for
A-law), lag-1 autocorrelation `0.848` (below the ~0.9 smooth-tone threshold),
strongly modulated RMS envelope (min ~8, max ~11070, std ~3649) with on/off
silence gaps. This is **not** a constant-amplitude tone and **not** continuous
carrier hiss; it is consistent with real modulated radio voice traffic. The WO
does **not** assess intelligibility or STT accuracy — that is explicitly out of
scope.

---

## G. WAV

| Field | Value |
| --- | --- |
| Format | WAV / PCM S16LE |
| Sample rate | 8000 Hz |
| Channels | 1 |
| Sample width | 16-bit |
| Frame count | 283,520 |
| Duration | 35.44 s |
| WAV SHA-256 | `bccc30487732c43802f041b1ac92eb7f19e1bfb672bf064a79c07b37018c98e1` |
| Write path | `write_wav_atomic` (atomic tmp -> os.replace, hash over final WAV bytes) |

The WAV master is deterministic: the same capture always yields the same bytes
and the same SHA-256.

---

## H. Integration

The reconstructed audio was consumed through the **existing** TACTICAL_CORE
WO-039 boundaries (no parallel architecture was created):

| Stage | Boundary |
| --- | --- |
| RTP packet input | pcapng reader (`app.audio.rtp_capture`) |
| RTP validation | `app.audio.rtp.parse_rtp_packet` / `validate_rtp_packet` |
| RTP reconstruction | `app.audio.rtp_stream.RtpStreamTracker` |
| G.711 A-law decode | `app.audio.alaw.alaw_to_pcm` |
| PCM frame | `app.audio.rtp_receiver.RtpPcmFrame` |
| VAD / recording boundary | `app.audio.recorder.TransmissionRecorder.on_pcm` |
| WAV master | `app.audio.wav_writer.write_wav_atomic` |

All 1,772 real RTP packets were parsed, validated, reconstructed, decoded to PCM,
and fed through the `TransmissionRecorder` (VAD -> WAV master). The recorder
produced a valid WAV master (SHA-256 `bccc3048...`, 35.44 s, mono/16-bit/8000 Hz).
Because the radio silence gaps in the capture are shorter than the 1000 ms
silence-timeout, the recorder segmented the stream as a single transmission
(finalized via `source_shutdown`, `complete=False`). No synthetic audio was
introduced and no STT engine was selected or invoked.

---

## I. Tests

| Test | Command | Result |
| --- | --- | --- |
| WO-041 integration | `.venv/bin/python -m pytest backend/tests/test_wo041_rtp_capture_integration.py` | **15 passed** |
| WO-039/WO-041 regression | `.venv/bin/python -m pytest backend/tests/test_wo039a_rtp_ingest.py backend/tests/test_wo039b_recording.py backend/tests/test_wo039c_stt.py backend/tests/test_wo038_audio_pipeline.py backend/tests/test_wo038_multicast_e2e.py backend/tests/test_wo038_source_adapter.py backend/tests/test_wo041_corr_stt_boundary.py` | **154 passed** |

The WO-041 suite covers: capture availability (fails when the capture is
unavailable — WO-041 §13), independent stream verification, RTP packet ordering,
packet count and 160-byte payload length, gap/duplicate detection, timestamp
progression, A-law decode validity and determinism, PCM SHA-256, ffmpeg reference
match, WAV validity and deterministic SHA-256, WAV readability, the real capture
through the recording boundary, and no-STT-engine verification.

---

## J. Gate

```
PASS
```

All WO-041 §15 criteria are satisfied:

- [x] capture available
- [x] RTP stream independently verified
- [x] RTP reconstruction succeeds
- [x] G.711 A-law decode succeeds
- [x] PCM output is valid
- [x] WAV master is valid
- [x] TACTICAL_CORE integration boundary is exercised
- [x] real-capture automated test passes
- [x] no synthetic data used as evidence
- [x] no STT engine selected
- [x] forensic verification passes

---

## Limitations / next step

- The WO does **not** assess audio intelligibility or STT accuracy; that remains
  the subject of the later acoustic STT benchmark (ADR-014 authority).
- ADR-014 was **not** modified. No STT engine was selected, installed, or invoked.
- The repository is now positioned to proceed to the acoustic STT benchmark stage
  with a verified real-capture -> PCM -> WAV integration path.
