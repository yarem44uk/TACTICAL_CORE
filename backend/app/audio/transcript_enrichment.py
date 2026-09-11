"""WO-064 — Transcript enrichment seam (derived callsign evidence).

This module establishes the enrichment seam between transcript evidence and the
future final operational event:

    Transcript Evidence
            |
            v
        Enrichment Engine
            |
            v
        Enrichment Result (DERIVED evidence)

The component is deterministic and testable.  It consumes a derived
transcript-evidence raw dict (the same EventFactory-compatible shape produced by
``build_transcript_raw`` and emitted by the WO-063 worker's ``on_transcript``
seam), runs deterministic callsign detection through the existing WO-038
:class:`~app.audio.callsign.CallsignDetector`, and produces an
:class:`EnrichmentResult`.

DERIVED EVIDENCE — BOUNDARY (WO-064 §5)
    The enrichment result is *derived* evidence.  It must NEVER become a
    replacement for, or mutate:

      * the original recording;
      * the recording identity (``audio_recording_id``);
      * the WAV SHA-256 (``wav_sha256``);
      * the transcript identity (``content_id = <rid>|transcript``);
      * the canonical / immutable event identity.

    The original transcript ``text`` is preserved verbatim and never modified.
    The enrichment ONLY ADDS a clearly-labelled ``enrichment`` layer and a
    distinct derived ``content_id`` (``<rid>|transcript|enrichment``).

WO-064 does NOT redesign the final Radio Event or the Operational Observation.
That remains WO-065.  This module is the isolated, auditable seam.

Established callsign contract (WO-038 / WO-057) — preserved at the top level of
the enriched raw dict so a later integration into the canonical event path
continues to work unchanged:

    * ``detected_callsigns``  (list[str])
    * ``confidence``          (float)
    * ``detection_method``    (str)
    * ``callsign``            (primary callsign, only when one is detected)

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.audio.callsign import CallsignDetector

logger = logging.getLogger(__name__)


class TranscriptEnrichmentError(Exception):
    """Base error for the transcript enrichment seam."""


class TranscriptEvidenceInvalidError(TranscriptEnrichmentError):
    """The transcript evidence is invalid / missing required identity.

    Raised when the input is not a dict, carries no ``audio_recording_id``, has
    no ``transcript`` block, or has no usable transcript ``text``.
    """


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EnrichmentResult:
    """Deterministic derived enrichment evidence for one transcript.

    Attributes:
        audio_recording_id: original recording identity (preserved, never altered).
        transcript_content_id: original transcript identity
            (``<rid>|transcript``; preserved, never altered).
        content_id: derived enrichment identity
            (``<rid>|transcript|enrichment``); distinct from both the recording
            and the transcript identities.
        wav_sha256: original verified WAV SHA-256 (preserved, never altered).
        transcript_text: original transcript text (preserved verbatim).
        detected_callsigns: unique detected callsigns in order of appearance.
        confidence: detection confidence in ``[0.0, 1.0]``.
        detection_method: short label for the strategy used.
        callsign: primary callsign, or ``None`` when none was detected.
        raw: enriched EventFactory-compatible raw dict.  It carries the original
            transcript verbatim (``raw["transcript"]``) plus the derived
            ``enrichment`` layer, and preserves the WO-038 callsign contract
            fields at the top level.
    """

    audio_recording_id: str
    transcript_content_id: str
    content_id: str
    wav_sha256: str | None
    transcript_text: str
    detected_callsigns: list[str]
    confidence: float
    detection_method: str
    callsign: str | None
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialisable representation (the original transcript stays intact)."""
        return {
            "audio_recording_id": self.audio_recording_id,
            "transcript_content_id": self.transcript_content_id,
            "content_id": self.content_id,
            "wav_sha256": self.wav_sha256,
            "transcript_text": self.transcript_text,
            "detected_callsigns": list(self.detected_callsigns),
            "confidence": self.confidence,
            "detection_method": self.detection_method,
            "callsign": self.callsign,
            "raw": dict(self.raw),
        }


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


class TranscriptEnrichmentEngine:
    """Deterministic enrichment seam between transcript and the future event.

    Args:
        detector: the WO-038 :class:`CallsignDetector` to use.  When ``None`` the
            engine uses the default deterministic heuristic detector.  It is a
            pure function of the transcript text: no engine, no model download,
            no network, no state.

    The engine NEVER mutates the input transcript evidence and NEVER fabricates a
    callsign for a transcript that has none.
    """

    def __init__(self, detector: CallsignDetector | None = None) -> None:
        self._detector = detector or CallsignDetector()

    @property
    def detector(self) -> CallsignDetector:
        """The configured callsign detector (observable, for audit)."""
        return self._detector

    def enrich(self, transcript_evidence: dict[str, Any]) -> EnrichmentResult:
        """Enrich one transcript-evidence raw dict with derived callsign info.

        Args:
            transcript_evidence: the derived transcript raw dict as produced by
                ``build_transcript_raw`` / the WO-063 worker's ``on_transcript``
                seam (keys: ``audio_recording_id``, ``content_id``,
                ``transcript.text``, ``transcript.wav_sha256``, ...).

        Returns:
            A deterministic :class:`EnrichmentResult`.  A valid transcript with
            no callsign yields an empty ``detected_callsigns`` list and
            ``callsign is None`` — it is a successful enrichment, not a failure.

        Raises:
            TranscriptEvidenceInvalidError: the evidence is not a dict, has no
                ``audio_recording_id``, no ``transcript`` block, or no usable
                transcript ``text``.
        """
        if not isinstance(transcript_evidence, dict):
            raise TranscriptEvidenceInvalidError("transcript evidence must be a dict")

        audio_recording_id = transcript_evidence.get("audio_recording_id")
        if not isinstance(audio_recording_id, str) or not audio_recording_id.strip():
            raise TranscriptEvidenceInvalidError("transcript evidence missing audio_recording_id")

        transcript = transcript_evidence.get("transcript")
        if not isinstance(transcript, dict):
            raise TranscriptEvidenceInvalidError("transcript evidence missing transcript block")

        text = transcript.get("text")
        if text is None:
            raise TranscriptEvidenceInvalidError("transcript evidence missing transcript text")
        text = str(text)

        # Preserved identities (never altered).
        transcript_content_id = transcript_evidence.get("content_id")
        if not isinstance(transcript_content_id, str) or not transcript_content_id.strip():
            transcript_content_id = f"{audio_recording_id}|transcript"
        wav_sha256 = transcript.get("wav_sha256")

        # Deterministic callsign detection (WO-038 contract).
        result = self._detector.detect(text)
        detected = list(result.detected_callsigns)
        confidence = result.confidence
        method = result.detection_method
        primary = detected[0] if detected else None

        # Distinct derived enrichment identity.
        derived_content_id = f"{audio_recording_id}|transcript|enrichment"

        # Enriched raw dict: preserve the original transcript verbatim, add a
        # clearly-labelled derived enrichment layer, and keep the WO-038
        # callsign contract fields at the top level for forward compatibility.
        enriched_raw: dict[str, Any] = {
            "timestamp": transcript_evidence.get("timestamp"),
            "occurred_at": transcript_evidence.get("occurred_at"),
            "audio_recording_id": audio_recording_id,
            "content_id": derived_content_id,
            "correlation_id": transcript_evidence.get(
                "correlation_id", audio_recording_id
            ),
            "source": transcript_evidence.get("source"),
            "transcript": dict(transcript),
            "detected_callsigns": list(detected),
            "confidence": confidence,
            "detection_method": method,
            "enrichment": {
                "content_id": derived_content_id,
                "audio_recording_id": audio_recording_id,
                "transcript_content_id": transcript_content_id,
                "wav_sha256": wav_sha256,
                "detected_callsigns": list(detected),
                "confidence": confidence,
                "detection_method": method,
            },
        }
        if primary is not None:
            enriched_raw["callsign"] = primary
            enriched_raw["enrichment"]["callsign"] = primary

        return EnrichmentResult(
            audio_recording_id=audio_recording_id,
            transcript_content_id=transcript_content_id,
            content_id=derived_content_id,
            wav_sha256=wav_sha256,
            transcript_text=text,
            detected_callsigns=detected,
            confidence=confidence,
            detection_method=method,
            callsign=primary,
            raw=enriched_raw,
        )
