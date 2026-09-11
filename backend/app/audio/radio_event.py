"""WO-065 — Final radio event -> operational observation integration seam.

This module establishes the final canonical radio-event seam:

    Recording Evidence (WO-058 / WO-062)
            |
            v
    Transcript Evidence (WO-063)  --  content_id = <rid>|transcript
            |
            v
    Enrichment Evidence (WO-064)  --  content_id = <rid>|transcript|enrichment
            |
            v
    FINAL Radio Event (WO-065)    --  canonical input (RAW dict)
            |
            v
    existing AdapterRuntime  (sole RAW -> canonical Event boundary, CONTRACT-2)
            |
            v
    existing EventPipeline
            |
            v
    Durable Journal
            |
            v
    Operational Observation

WO-065 does NOT create a second EventFactory, a second Event identity system,
a second Observation model, a second journal, a parallel radio-event table, a
parallel persistence path, a new event bus, or a new wall-specific event type.
It consumes the WO-064 :class:`~app.audio.transcript_enrichment.EnrichmentResult`
and produces the canonical RAW input (a ``SourceEnvelope``) that the EXISTING
canonical ingestion boundary (``AdapterRuntime`` -> ``EventFactory`` ->
``EventPipeline``) turns into the final Radio Event and, downstream, an
Operational Observation.

Architectural boundary (WO-050 CONTRACT-2):
    ``AdapterRuntime`` is the SOLE production RAW -> ``EventFactory`` boundary.
    This module therefore NEVER calls ``EventFactory.create_event``, NEVER
    constructs an ``app.event.event.Event``, NEVER imports the canonical Event
    layer, and NEVER calls ``save`` / a repository.  It is a producer-only
    seam (mirroring ``AudioEventOrchestrator``, CONTRACT-7): it emits the
    canonical RAW dict and leaves the canonical Event construction to the
    existing runtime.

The final event RAW dict:
  * uses the EXISTING canonical identity material (the enrichment
    ``content_id`` = ``<rid>|transcript|enrichment``) so the deterministic
    ``event_id`` derived by ``EventIdentityResolver`` (WO-025) is
    ``radio|content|<rid>|transcript|enrichment`` — distinct from the recording
    (``radio|content|<rid>``) and the transcript
    (``radio|content|<rid>|transcript``);
  * preserves the recording identity (``audio_recording_id``) verbatim;
  * preserves the transcript identity (``<rid>|transcript``) verbatim;
  * preserves the enrichment identity (``<rid>|transcript|enrichment``) verbatim;
  * preserves provenance (``wav_sha256``, transcript text, detected callsigns,
    detection method, confidence);
  * carries a ``recording`` block that REFERENCES the authoritative recording
    (``audio_recording_id``, ``content_id``, ``wav_sha256``, ``source``).  This
    is a provenance reference, NOT fabricated recording content.  The existing
    ``CanonicalEventToObservationAdapter`` (WO-059) classifies any source
    ``radio`` event carrying a ``recording`` block as ``radio.recording``,
    which requires no frequency/callsign and therefore reaches the Operational
    Observation without inventing transmission metadata.

The seam is deterministic and idempotent: the same enrichment always yields the
same RAW dict and therefore the same canonical ``event_id``, so the durable
repository's ``UNIQUE(event_id)`` constraint and the observation's
``UNIQUE(immutable_id)`` constraint together prevent duplicate operational
observations.

WO-065 never mutates the input enrichment (source immutability) and never
fabricates speaker / frequency / location / unit / rank / organization /
severity / priority / operational classification / confidence meaning beyond
the existing callsign-detector contract.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.audio.transcript_enrichment import EnrichmentResult
from app.event_sources.identity.event_identity import EventIdentityResolver

logger = logging.getLogger(__name__)


class RadioEventError(Exception):
    """Base error for the final radio event integration seam."""


class FinalEventInvalidError(RadioEventError):
    """The enrichment evidence cannot produce a valid final radio event.

    Raised when the input is not a valid :class:`EnrichmentResult`, or when a
    required identity field is missing/empty.  No partial event is ever built.
    """


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RadioEventResult:
    """The canonical integration result for one enrichment result.

    Attributes:
        event_id: the deterministic canonical event identity
            (``radio|content|<rid>|transcript|enrichment``, a UUID5 string).
        raw: the final radio-event canonical RAW dict (the input for the
            existing ``EventFactory``).
        audio_recording_id: original recording identity (preserved, never altered).
        transcript_content_id: original transcript identity
            (``<rid>|transcript``; preserved, never altered).
        enrichment_content_id: derived enrichment identity
            (``<rid>|transcript|enrichment``; preserved, never altered).
        wav_sha256: original verified WAV SHA-256 (preserved, never altered).
        transcript_text: original transcript text (preserved verbatim).
        detected_callsigns: unique detected callsigns in order of appearance.
        detection_method: short label for the strategy used.
        confidence: detection confidence in ``[0.0, 1.0]``.
        callsign: primary callsign, or ``None`` when none was detected.
    """

    event_id: str
    raw: dict[str, Any]
    audio_recording_id: str
    transcript_content_id: str
    enrichment_content_id: str
    wav_sha256: str | None
    transcript_text: str
    detected_callsigns: list[str]
    detection_method: str
    confidence: float
    callsign: str | None


# --------------------------------------------------------------------------- #
# Integrator
# --------------------------------------------------------------------------- #


class RadioEventIntegrator:
    """Connect a WO-064 enrichment result into the canonical Event path.

    Args:
        identity_resolver: the existing :class:`EventIdentityResolver`.  When
            ``None`` (default) the canonical resolver is used.

    The integrator is a LEAF producer seam.  It never owns an ``EventFactory``,
    never constructs an ``Event``, never persists, and never touches the
    observation database.  It only produces the canonical RAW input
    (``build_raw``) and the deterministic canonical identity
    (``resolve_event_id``); the caller forwards the RAW through the existing
    ``AdapterRuntime`` (the sole RAW -> Event boundary) via ``integrate`` or
    the existing composition root.
    """

    def __init__(self, identity_resolver: EventIdentityResolver | None = None) -> None:
        self._identity_resolver = identity_resolver or EventIdentityResolver()

    # -- seam ---------------------------------------------------------------

    def build_raw(self, enrichment: EnrichmentResult) -> dict[str, Any]:
        """Build the canonical final radio-event RAW dict from one enrichment.

        The returned RAW dict is shaped for ``EventFactory.create_event`` and is
        the canonical input for the existing ingestion boundary.  The enrichment
        (and its ``raw`` dict) is never mutated.

        Raises:
            FinalEventInvalidError: the input is not a valid
                :class:`EnrichmentResult` or a required identity is missing.
        """
        self._validate(enrichment)

        raw = enrichment.raw
        audio_recording_id = enrichment.audio_recording_id
        transcript_content_id = enrichment.transcript_content_id
        enrichment_content_id = enrichment.content_id

        # The enrichment content_id (``<rid>|transcript|enrichment``) is the
        # identity material, so the canonical event_id is distinct from the
        # recording (``radio|content|<rid>``) and the transcript
        # (``radio|content|<rid>|transcript``).
        final_raw: dict[str, Any] = {
            "timestamp": raw.get("timestamp"),
            "occurred_at": raw.get("occurred_at"),
            "audio_recording_id": audio_recording_id,
            "content_id": enrichment_content_id,
            "correlation_id": raw.get("correlation_id", audio_recording_id),
            "source": "radio",
            # WO-065 provenance reference to the authoritative recording.
            # The existing adapter (WO-059) classifies a source ``radio`` event
            # carrying a ``recording`` block as ``radio.recording``, so the
            # final event reaches the Operational Observation without any
            # fabricated frequency/callsign.
            "recording": {
                "audio_recording_id": audio_recording_id,
                "content_id": audio_recording_id,
                "wav_sha256": enrichment.wav_sha256,
                "source": "radio",
            },
            # Derived evidence, preserved verbatim (never overwritten).
            "transcript": dict(raw["transcript"]),
            "enrichment": dict(raw["enrichment"]),
            # Explicit traceability chain.
            "transcript_content_id": transcript_content_id,
            "enrichment_content_id": enrichment_content_id,
            # WO-038 callsign contract preserved at the top level.
            "detected_callsigns": list(enrichment.detected_callsigns),
            "confidence": enrichment.confidence,
            "detection_method": enrichment.detection_method,
        }
        if enrichment.callsign is not None:
            final_raw["callsign"] = enrichment.callsign

        return final_raw

    def resolve_event_id(self, enrichment: EnrichmentResult) -> str:
        """Resolve the deterministic canonical ``event_id`` (WO-025).

        The identity is a pure function of the enrichment ``content_id`` and the
        ``radio`` source policy.  The same enrichment always yields the same
        ``event_id``, which is what makes end-to-end idempotency possible.

        Raises:
            FinalEventInvalidError: the identity could not be resolved (the
                radio source always resolves a content_id, so this is a fail-
                closed guard, never a silent UUID4 fallback).
        """
        final_raw = self.build_raw(enrichment)
        resolved = self._identity_resolver.resolve(final_raw, "radio")
        if resolved is None:
            raise FinalEventInvalidError(
                "final radio event identity could not be resolved"
            )
        return resolved

    def integrate(
        self,
        enrichment: EnrichmentResult,
        runtime: Any,
    ) -> RadioEventResult:
        """Build the final RAW and forward it through an existing runtime.

        Args:
            enrichment: the WO-064 :class:`EnrichmentResult` to integrate.
            runtime: an existing ``AdapterRuntime`` (the sole RAW -> canonical
                Event boundary, CONTRACT-2).  The runtime owns the
                ``EventFactory`` and ``EventPipeline``; this module never calls
                ``EventFactory.create_event`` directly.

        Returns:
            A :class:`RadioEventResult` carrying the deterministic event identity
            and the canonical RAW dict.

        Raises:
            FinalEventInvalidError: the input is invalid (no RAW is produced).
            Any runtime/pipeline error propagates to the caller.
        """
        final_raw = self.build_raw(enrichment)
        runtime._process_raw(final_raw)
        return RadioEventResult(
            event_id=self.resolve_event_id(enrichment),
            raw=final_raw,
            audio_recording_id=enrichment.audio_recording_id,
            transcript_content_id=enrichment.transcript_content_id,
            enrichment_content_id=enrichment.content_id,
            wav_sha256=enrichment.wav_sha256,
            transcript_text=enrichment.transcript_text,
            detected_callsigns=list(enrichment.detected_callsigns),
            detection_method=enrichment.detection_method,
            confidence=enrichment.confidence,
            callsign=enrichment.callsign,
        )

    # -- validation ---------------------------------------------------------

    @staticmethod
    def _validate(enrichment: EnrichmentResult) -> None:
        """Validate that the enrichment can produce a final radio event."""
        if not isinstance(enrichment, EnrichmentResult):
            raise FinalEventInvalidError(
                "enrichment must be an EnrichmentResult, got "
                f"{type(enrichment).__name__}"
            )
        if not isinstance(enrichment.audio_recording_id, str) or not (
            enrichment.audio_recording_id.strip()
        ):
            raise FinalEventInvalidError(
                "final radio event missing valid audio_recording_id"
            )
        if not isinstance(enrichment.transcript_content_id, str) or not (
            enrichment.transcript_content_id.strip()
        ):
            raise FinalEventInvalidError(
                "final radio event missing valid transcript identity"
            )
        if not isinstance(enrichment.content_id, str) or not (
            enrichment.content_id.strip()
        ):
            raise FinalEventInvalidError(
                "final radio event missing valid enrichment identity"
            )
        if not isinstance(enrichment.transcript_text, str):
            raise FinalEventInvalidError(
                "final radio event transcript text must be a string"
            )
        raw = getattr(enrichment, "raw", None)
        if not isinstance(raw, dict):
            raise FinalEventInvalidError(
                "final radio event missing enrichment raw dict"
            )
        if not isinstance(raw.get("transcript"), dict):
            raise FinalEventInvalidError(
                "final radio event missing transcript block"
            )
        if not isinstance(raw.get("enrichment"), dict):
            raise FinalEventInvalidError(
                "final radio event missing enrichment block"
            )
