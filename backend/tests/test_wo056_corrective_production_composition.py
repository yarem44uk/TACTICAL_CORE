"""WO-056-CORRECTIVE — Production radio composition gate tests.

Closes the WO-056 production-composition finding: ``PRODUCTION_SOURCE_CATALOG``
was empty, so ``main()`` -> ``register_sources()`` registered ZERO production
sources, and the original WO-056 acceptance tests bypassed the production
factory/catalog by constructing ``MulticastAudioSourceAdapter`` directly.

These tests prove the REAL production composition path is now exercised:

    PRODUCTION_SOURCE_CATALOG
        -> build_production_source_provider()
        -> register_sources()            (backend.main, ProductionSourceRegistrar)
        -> factory.create()              (build_production_adapter_factory)
        -> MulticastAudioSourceAdapter
        -> ProductionRuntime.add_source() -> AdapterRuntime

The tests do NOT construct ``MulticastAudioSourceAdapter`` directly, and they do
NOT bypass the production registration path.  They also verify the canonical
EventFactory / EventPipeline boundary is preserved (the adapter remains a leaf:
it never constructs canonical Events or persists to a repository directly).

The STT engine gate and live-multicast reception are NOT satisfied in this
environment; this gate only proves production *composition* (registration and
instantiation through the canonical path), not live radio reception.
"""

from __future__ import annotations

from app.audio.source_adapter import MulticastAudioSourceAdapter
from app.bootstrap import create_production_runtime
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_sources.config.production_source_config import (
    PRODUCTION_SOURCE_CATALOG,
    build_production_adapter_factory,
    build_production_source_provider,
)
from app.event_sources.factory.event_factory import EventFactory
import backend.main as main


def _multicast_definition():
    """Return the multicast_audio source definition declared in the catalog."""
    matches = [d for d in PRODUCTION_SOURCE_CATALOG if d.adapter_type == "multicast_audio"]
    assert matches, "production catalog must declare a multicast_audio source"
    return matches[0]


# ---------------------------------------------------------------------------
# 1. The production catalog declares the multicast_audio source
# ---------------------------------------------------------------------------
def test_production_catalog_declares_multicast_audio() -> None:
    assert len(PRODUCTION_SOURCE_CATALOG) >= 1
    definition = _multicast_definition()
    # The production composition must register this source, so it must be enabled.
    assert definition.enabled is True


def test_production_catalog_definition_is_valid() -> None:
    definition = _multicast_definition()
    assert definition.adapter_type == "multicast_audio"
    assert definition.name
    # Adapter-specific config must be parseable by the production adapter (it is
    # validated lazily on construction; here we only require the required keys).
    assert "multicast_address" in definition.config
    assert "multicast_port" in definition.config


# ---------------------------------------------------------------------------
# 2. The production factory resolves the multicast_audio adapter type
# ---------------------------------------------------------------------------
def test_production_factory_registers_and_resolves_multicast_audio() -> None:
    factory = build_production_adapter_factory()
    assert "multicast_audio" in factory.registered_types()

    # Resolution through the production factory (NOT direct construction).
    definition = _multicast_definition()
    adapter = factory.create(definition)
    assert isinstance(adapter, MulticastAudioSourceAdapter)
    assert adapter.adapter_type == "multicast_audio"


# ---------------------------------------------------------------------------
# 3. The production registration path registers the multicast source
# ---------------------------------------------------------------------------
def test_production_registration_builds_multicast_source_into_runtime() -> None:
    """Drive the real path: catalog -> provider -> register_sources() -> runtime.

    Asserts the resulting runtime contains the expected multicast source built by
    the production factory, without the test constructing the adapter directly.
    """
    provider = build_production_source_provider()
    factory = build_production_adapter_factory()
    runtime = create_production_runtime()

    registered = main.register_sources(runtime, provider, factory)

    # WO-075: the production catalog also declares the Signal source, so the
    # production registration path builds BOTH production sources.
    assert registered == ["radio", "signal"]
    assert runtime.supervisor.list_runtimes() == ["radio", "signal"]

    runtime_handle = runtime.supervisor.get_runtime("radio")
    assert runtime_handle.name == "radio"
    # The adapter inside the runtime was built by the production factory, not by
    # the test.  We only inspect it (this is the established introspection style
    # used elsewhere in the repo, e.g. adapter._recorder / aruntime._process_raw).
    adapter = runtime_handle._adapter
    assert isinstance(adapter, MulticastAudioSourceAdapter)
    assert adapter.adapter_type == "multicast_audio"


# ---------------------------------------------------------------------------
# 4. Canonical EventFactory / EventPipeline boundary preserved
# ---------------------------------------------------------------------------
def test_canonical_event_boundary_preserved() -> None:
    """The radio adapter stays a leaf: no bypass of EventFactory / EventPipeline.

    The runtime wires the adapter into the existing EventFactory -> EventPipeline
    path.  The adapter itself never constructs a canonical Event and never
    persists directly to a repository.
    """
    runtime = create_production_runtime()

    assert isinstance(runtime.event_factory, EventFactory)
    assert isinstance(runtime.pipeline, EventPipeline)

    adapter = _multicast_definition()
    built = build_production_adapter_factory().create(adapter)
    assert isinstance(built, MulticastAudioSourceAdapter)
    # The adapter only queues raw dicts; it has no repository / pipeline handle.
    assert built.pending_count() == 0
    # The adapter is a leaf: it has no pipeline or repository attribute of its own.
    assert not hasattr(built, "pipeline")
    assert not hasattr(built, "repository")
