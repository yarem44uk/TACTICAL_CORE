"""WO-038 — Multicast audio source adapter registration.

Adapter-specific wiring that makes ``MulticastAudioSourceAdapter`` discoverable
through the existing WO-013 ``AdapterFactory`` plugin mechanism, mirroring the
other source-adapter registration modules (radio, atak, mqtt, ...).

It uses ONLY the existing public API ``AdapterFactory.register_type(type,
builder)`` and does NOT modify ``AdapterFactory``, ``SourceRegistry``, or any
protected file.  The adapter type is registered under the stable identifier
``"multicast_audio"``.
"""

from __future__ import annotations

import logging

from app.audio.source_adapter import (
    MULTICAST_AUDIO_ADAPTER_TYPE,
    make_multicast_audio_adapter,
)
from app.event_sources.config.adapter_factory import AdapterFactory

logger = logging.getLogger(__name__)


def register_multicast_audio_adapter(factory: AdapterFactory) -> None:
    """Register the multicast audio source adapter with an AdapterFactory.

    Idempotent-safe: if the type is already registered, the existing
    registration is left untouched.
    """
    if factory.has_type(MULTICAST_AUDIO_ADAPTER_TYPE):
        logger.debug(
            "Multicast audio adapter type '%s' already registered; skipping",
            MULTICAST_AUDIO_ADAPTER_TYPE,
        )
        return
    factory.register_type(MULTICAST_AUDIO_ADAPTER_TYPE, make_multicast_audio_adapter)
    logger.info("Registered multicast audio source adapter type '%s'", MULTICAST_AUDIO_ADAPTER_TYPE)


def build_registered_factory() -> AdapterFactory:
    """Create an AdapterFactory with the multicast audio adapter pre-registered."""
    factory = AdapterFactory()
    register_multicast_audio_adapter(factory)
    return factory
