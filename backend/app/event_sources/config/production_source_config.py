"""
TACTICAL CORE — WO-036 Production Source Configuration

Implements ADR-010 (Option B — Static Python source catalog module).

This module closes the documented production ``SOURCE_CONFIGURATION_GAP`` by
supplying the concrete production pieces mandated by ADR-010 while reusing the
existing source-configuration contracts unchanged:

    * ``ISourceConfigProvider``   (abstract contract, reused)
    * ``SourceDefinition``        (immutable definition, reused)
    * ``AdapterFactory``          (plugin registry, reused)
    * ``register_*_adapter()``    (existing adapter registration helpers, reused)

The production provider is backed by a static, deterministic Python catalog of
``SourceDefinition`` objects.  It is NOT YAML/JSON/TOML, NOT database-backed,
NOT plugin-discovered, and NOT dynamically imported from arbitrary modules.

ADR-010 fail-closed semantics:
    * missing / unreadable catalog  -> FAIL CLOSED (raises; never silently empty)
    * malformed catalog             -> FAIL CLOSED (raises)
    * duplicate source names        -> FAIL CLOSED (raises)
    * unknown adapter type          -> handled by AdapterFactory (AdapterTypeError)
    * empty catalog                 -> valid zero-source configuration
    * disabled-only catalog         -> valid zero active sources

``credentials_ref`` remains reference-only.  No secret value is ever stored in
the catalog; no new secret-management subsystem is introduced.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .adapter_factory import AdapterFactory
from .errors import DuplicateSourceError, SourceConfigError, SourceNotFoundError
from .provider import ISourceConfigProvider
from .source_definition import SourceDefinition

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..adapters.signal_transport import SignalTransport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Static Python source catalog (ADR-010 Option B)
# ---------------------------------------------------------------------------
# The production source catalog is an explicit, deterministic list of
# ``SourceDefinition`` objects.  An embedding deployment edits THIS list to
# declare which real sources the production process should register.
#
# By default the catalog declares the production multicast radio source
# (WO-056) and the production Signal messaging source (WO-075) so
# ``main()`` -> ``register_sources()`` genuinely registers and instantiates the
# ``multicast_audio`` and ``signal`` adapters through the canonical
# registration path.  A missing catalog is still a hard error, NOT an empty
# catalog — that distinction is enforced by the provider (see
# ``ProductionSourceConfigProvider``).
#
# WO-056-CORRECTIVE scope note: this entry makes the production *composition*
# real.  It does NOT prove live multicast reception.  The address/port below are
# the configured production declaration; an embedding deployment overrides them
# for the actual radio.  STT is intentionally left disabled (no ``stt`` block)
# so the adapter is fail-closed (no transcript), exactly as production behaves
# when no acoustic engine is provisioned.
#
# WO-058: recording/VAD is now ACTIVATED (``vad_enabled: True``) so the
# production radio source engages the existing
# RTP -> FlowRouter -> per-flow recorder -> VAD -> WAV -> recording-raw
# -> canonical pipeline.  All remaining recording parameters fall back to the
# documented ``RecordingConfig`` defaults (activation, not VAD tuning).
def _production_radio_source() -> SourceDefinition:
    """Build the production ``multicast_audio`` source definition (WO-056).

    The ``adapter_type`` must match the adapter type registered by
    ``register_multicast_audio_adapter`` (``MULTICAST_AUDIO_ADAPTER_TYPE``),
    i.e. ``"multicast_audio"``.
    """
    return SourceDefinition(
        name="radio",
        adapter_type="multicast_audio",
        enabled=True,
        config={
            "multicast_address": "239.233.18.30",
            "multicast_port": 5033,
            "protocol": "rtp",
            "codec": "pcm_alaw",
            "sample_rate": 8000,
            "channels": 1,
            "source_name": "radio",
            # WO-058: activate the existing recording/VAD/WAV path.  The
            # remaining recording parameters (vad_adaptive, pre/post_roll_ms,
            # silence_timeout_ms, min_speech_ms, audio_archive_root,
            # mp3_enabled, ...) intentionally use the documented
            # ``RecordingConfig`` defaults.
            "vad_enabled": True,
        },
        credentials_ref=None,
    )


def _production_signal_source() -> SourceDefinition:
    """Build the production ``signal`` source definition (WO-075).

    This declares the Signal messaging source in the SAME static production
    catalog that declares the radio source, so the Signal adapter is built and
    registered through the REAL production composition path
    (``PRODUCTION_SOURCE_CATALOG`` -> ``ProductionSourceConfigProvider`` ->
    ``ProductionSourceRegistrar`` -> ``AdapterFactory`` -> ``AdapterSupervisor``
    -> ``AdapterRuntime``) instead of being a test-only artifact.

    The ``adapter_type`` must match the adapter type registered by
    ``register_signal_adapter`` (``SIGNAL_ADAPTER_TYPE``), i.e. ``"signal"``.

    ``enabled=True`` is the explicit production declaration: the production
    registrar only registers enabled sources, so composition genuinely builds
    the Signal source.  It does NOT prove live Signal connectivity: the
    adapter is driven by an INJECTABLE transport
    (``build_production_adapter_factory(signal_transport=...)``), and with no
    transport injected the adapter is a passive queue (no producer).

    Secrets: ``credentials_ref`` is a REFERENCE to the embedding deployment's
    credential store entry only — never a secret value (ADR-010).  The config
    carries no credentials, no account identifiers, and no PII: just the
    logical source name and the logical ingestion channel label the adapter
    reads.
    """
    return SourceDefinition(
        name="signal",
        adapter_type="signal",
        enabled=True,
        config={
            "source_name": "signal",
            # Logical ingestion channel label (opaque to the config layer;
            # read by SignalSourceAdapter).  Not a credential and not an
            # account identifier.
            "channel": "signal-canonical",
        },
        # Reference-only: the name of the credential-store entry an embedding
        # deployment provisions for the real Signal transport.
        credentials_ref="signal/production",
    )


PRODUCTION_SOURCE_CATALOG: list[SourceDefinition] = [
    _production_radio_source(),
    _production_signal_source(),
]


def build_whatsapp_source_definition() -> SourceDefinition:
    """Build the ``whatsapp`` source definition for the WO-080 ingress process.

    This is an ADDITIVE builder (WO-080).  It is deliberately NOT appended to
    ``PRODUCTION_SOURCE_CATALOG``: the WhatsApp Cloud API webhook ingress is a
    SEPARATE process with its own composition (ADR-015 §5), so the durable-core
    production process (``backend/main.py``) must not gain a producer-less
    WhatsApp source.  The ingress composition registers it through the SAME
    existing mechanism (``SourceDefinition`` -> ``AdapterFactory`` ->
    ``ProductionSourceRegistrar`` -> ``AdapterSupervisor``/``AdapterRuntime``)
    by passing a single-source catalog to ``build_production_source_provider``.

    ``adapter_type`` must match the type registered by
    ``register_whatsapp_adapter`` (``WHATSAPP_ADAPTER_TYPE`` == ``"whatsapp"``).

    Secrets: ``credentials_ref`` is a REFERENCE to the embedding deployment's
    credential entry only — never a secret value (ADR-010).  The App Secret and
    Verify Token are owned by the ingress process environment (ADR-015 §12) and
    are NOT carried in the catalog or in ``config``.
    """
    return SourceDefinition(
        name="whatsapp",
        adapter_type="whatsapp",
        enabled=True,
        config={
            "source_name": "whatsapp",
            # Logical webhook path label (non-secret; informational).
            "webhook_path": "/webhook",
        },
        # Reference-only: the name of the credential-store entry an embedding
        # deployment provisions for the Meta app.  No secret value here.
        credentials_ref="whatsapp/production",
    )


class ProductionSourceConfigProvider(ISourceConfigProvider):
    """Concrete production ``ISourceConfigProvider`` backed by a static catalog.

    Fail-closed: malformed or duplicate definitions are rejected at ``load()``.
    A catalog that cannot be read (e.g. the module is unavailable) raises a
    ``SourceConfigError`` rather than being silently treated as empty.
    """

    def __init__(self, catalog: list[SourceDefinition] | None = None) -> None:
        # ``None`` means "catalog unavailable" -> load() FAILS CLOSED.
        # An explicit empty list means "valid zero-source catalog".
        if catalog is None:
            self._catalog_available = False
            self._definitions: list[SourceDefinition] = []
        else:
            self._catalog_available = True
            self._definitions = list(catalog)
        self._loaded = False

    # -- ISourceConfigProvider contract ------------------------------------
    def load(self) -> None:
        """Load (or reload) the static catalog into memory (fail-closed).

        Raises:
            SourceConfigError: If the catalog is unavailable (missing/unreadable).
            DuplicateSourceError: If two sources share a name.
            SourceDefinitionError: If any definition is malformed (propagated
                from ``SourceDefinition`` validation).
        """
        if not self._catalog_available:
            raise SourceConfigError(
                "WO-036: production source catalog is unavailable; failing "
                "closed rather than silently starting with zero sources"
            )
        seen: set[str] = set()
        for definition in self._definitions:
            if not isinstance(definition, SourceDefinition):
                raise SourceConfigError(
                    "WO-036: malformed catalog entry (expected SourceDefinition)"
                )
            if definition.name in seen:
                raise DuplicateSourceError(
                    f"WO-036: duplicate source name '{definition.name}' in "
                    "production catalog"
                )
            seen.add(definition.name)
        self._loaded = True
        logger.info("WO-036: loaded %d production source definition(s).", len(self._definitions))

    def list_sources(self) -> list[SourceDefinition]:
        """Return all configured source definitions."""
        if not self._loaded:
            # Deterministic: a provider that has not been loaded yields nothing.
            return []
        return list(self._definitions)

    def get_source(self, name: str) -> SourceDefinition:
        """Return the source definition for the given name.

        Raises:
            SourceNotFoundError: If no such source exists.
        """
        for definition in self._definitions:
            if definition.name == name:
                return definition
        raise SourceNotFoundError(f"source '{name}' not found")


def build_production_source_provider(
    catalog: list[SourceDefinition] | None = None,
) -> ProductionSourceConfigProvider:
    """Construct the production source-configuration provider.

    Args:
        catalog: The static source catalog.  Defaults to the module-level
            ``PRODUCTION_SOURCE_CATALOG``.  Passing ``None`` explicitly marks
            the catalog as unavailable (fail-closed at ``load()``).

    Returns:
        A configured ``ProductionSourceConfigProvider``.
    """
    if catalog is None:
        catalog = PRODUCTION_SOURCE_CATALOG
    return ProductionSourceConfigProvider(catalog=catalog)


def build_production_adapter_factory(
    signal_transport: "SignalTransport | None" = None,
) -> AdapterFactory:
    """Construct the production ``AdapterFactory`` with all six adapter types.

    Registers exactly the six known production adapter types through the
    existing registration helpers (ADR-010): atak, mqtt, signal, radio,
    telegram, multicast_audio.  No dynamic plugin discovery, no new registry.

    ``multicast_audio`` (WO-056) is the real RTP multicast radio source
    adapter (``MulticastAudioSourceAdapter``); it is registered here so the
    production composition can build the production radio path and the radio
    source is not an isolated test-only subsystem.

    WO-075 — injectable Signal transport: when ``signal_transport`` is
    supplied it is bound to every Signal adapter the factory builds (through
    the existing ``register_signal_adapter`` builder contract), so the
    production composition owns the Signal producer seam without any parallel
    registry or runtime.  When omitted (default), the Signal adapter is
    registered exactly as before (passive queue / no producer).

    Args:
        signal_transport: Optional ``SignalTransport`` implementation
            (``app.event_sources.adapters.signal_transport.SignalTransport``).
            Injection only; no live Signal connectivity is established here.

    Returns:
        An ``AdapterFactory`` able to resolve all six adapter types.
    """
    from ..adapters.atak_adapter_registration import register_atak_adapter
    from ..adapters.mqtt_adapter_registration import register_mqtt_adapter
    from ..adapters.radio_adapter_registration import register_radio_adapter
    from ..adapters.signal_adapter_registration import register_signal_adapter
    from ..adapters.telegram_adapter_registration import register_telegram_adapter
    from app.audio.registration import register_multicast_audio_adapter

    factory = AdapterFactory()
    register_atak_adapter(factory)
    register_mqtt_adapter(factory)
    register_signal_adapter(factory, transport=signal_transport)
    register_radio_adapter(factory)
    register_telegram_adapter(factory)
    register_multicast_audio_adapter(factory)
    return factory
