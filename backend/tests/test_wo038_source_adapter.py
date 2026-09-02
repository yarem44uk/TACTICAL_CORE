"""WO-038 tests — Multicast audio source adapter + registration.

Verifies the multicast audio source is represented through the existing
source/adapter architecture: ``IEventSourceAdapter`` lifecycle, the
``AdapterFactory`` registration mechanism, and the adapter's ``read_events``
path.  The full vertical slice (adapter -> EventFactory -> durable -> operator)
is covered in test_wo038_multicast_e2e.py.
"""

from __future__ import annotations

import time

import pytest
from app.audio.audio_config import AudioConfig
from app.audio.callsign import CallsignDetector
from app.audio.registration import (
    build_registered_factory,
    register_multicast_audio_adapter,
)
from app.audio.simulator import MulticastAudioSimulator
from app.audio.source_adapter import (
    MulticastAudioSourceAdapter,
    make_multicast_audio_adapter,
)
from app.audio.transcriber import DeterministicTestTranscriber
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.errors import AdapterTypeError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter

GROUP = "239.255.1.10"
PHRASE = "Буревій-2, прийом. Виходжу на позицію."
CALLSIGN = "Буревій-2"


def _definition(port: int) -> SourceDefinition:
    return SourceDefinition(
        name="radio-mc",
        adapter_type="multicast_audio",
        config={
            "multicast_address": GROUP,
            "multicast_port": port,
            "codec": "wav",
            "source_name": "radio",
            "join_interface": "127.0.0.1",
        },
    )


def _cfg(port: int) -> AudioConfig:
    return AudioConfig(
        multicast_address=GROUP,
        multicast_port=port,
        codec="wav",
        source_name="radio",
        join_interface="127.0.0.1",
    )


def test_make_adapter_returns_configured_adapter() -> None:
    adapter = make_multicast_audio_adapter(_definition(50001))
    assert isinstance(adapter, MulticastAudioSourceAdapter)
    assert isinstance(adapter, IEventSourceAdapter)
    assert isinstance(adapter, BaseEventSourceAdapter)
    assert adapter.source_name() == "radio"
    assert adapter.adapter_type == "multicast_audio"


def test_adapter_source_name_configurable() -> None:
    definition = _definition(50002)
    adapter = MulticastAudioSourceAdapter(
        definition,
        config=AudioConfig(multicast_address=GROUP, multicast_port=50002, source_name="airband"),
    )
    assert adapter.source_name() == "airband"


def test_adapter_read_events_empty_when_stopped() -> None:
    adapter = make_multicast_audio_adapter(_definition(50003))
    assert adapter.read_events() == []


def test_register_multicast_audio_adapter() -> None:
    factory = AdapterFactory()
    register_multicast_audio_adapter(factory)
    assert factory.has_type("multicast_audio")
    # Idempotent: re-register is a no-op.
    register_multicast_audio_adapter(factory)
    assert factory.has_type("multicast_audio")


def test_registered_factory_creates_adapter() -> None:
    factory = build_registered_factory()
    assert "multicast_audio" in factory.registered_types()
    adapter = factory.create(_definition(50004))
    assert isinstance(adapter, MulticastAudioSourceAdapter)


def test_unknown_adapter_type_raises() -> None:
    factory = build_registered_factory()
    with pytest.raises(AdapterTypeError):
        factory.create(
            SourceDefinition(name="x", adapter_type="does-not-exist", config={})
        )


def test_adapter_start_stop_idempotent() -> None:
    adapter = make_multicast_audio_adapter(_definition(50005))
    adapter.start()
    assert adapter.is_running is True
    assert adapter.health() is True
    adapter.start()  # idempotent
    assert adapter.is_running is True
    adapter.stop()
    assert adapter.is_running is False
    adapter.stop()  # idempotent
    assert adapter.is_running is False


def test_adapter_read_events_after_real_multicast() -> None:
    port = 50006
    adapter = MulticastAudioSourceAdapter(
        _definition(port),
        config=_cfg(port),
        transcriber=DeterministicTestTranscriber(phrase_map={"bureviy-2": PHRASE}),
        callsign_detector=CallsignDetector(callsigns=[CALLSIGN]),
    )
    adapter.start()
    time.sleep(0.4)
    sim = MulticastAudioSimulator(_cfg(port))
    sim.send("bureviy-2")
    sim.close()

    # Poll read_events until the raw event dict arrives.
    raw = None
    deadline = time.time() + 5.0
    while time.time() < deadline:
        pending = adapter.read_events()
        if pending:
            raw = pending[0]
            break
        time.sleep(0.1)
    assert raw is not None, "no raw event produced"
    assert raw["transcript"] == PHRASE
    assert raw["detected_callsigns"] == [CALLSIGN]
    assert raw["content_id"] == "bureviy-2"
    assert raw.get("source", True)
    adapter.stop()


def test_adapter_malformed_frame_isolated() -> None:
    import socket

    port = 50007
    adapter = make_multicast_audio_adapter(_definition(port))
    adapter.start()
    time.sleep(0.3)
    bad = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    bad.sendto(b"GARBAGE", (GROUP, port))
    bad.close()
    time.sleep(0.3)
    # Adapter stays alive and healthy after a malformed frame.
    assert adapter.health() is True
    assert adapter.is_running is True
    adapter.stop()
