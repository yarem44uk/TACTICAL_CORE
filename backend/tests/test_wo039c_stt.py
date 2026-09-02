"""WO-039-C1/C2 tests — offline STT seam + model configuration.

These tests validate the minimum offline STT seam (C1) and the offline model
configuration / path plumbing (C2).  No real engine is installed and no model is
downloaded: a fake adapter is registered only inside the tests to exercise the
offline-init lifecycle (model exists -> initialize -> ready).

Required cases (WO-039-C2 configuration validation):
    * valid model path
    * missing model path (fails clearly, no download / no network)
    * invalid engine (fails clearly)
    * disabled STT (no model path required)
    * language setting
    * device setting

Required seam behaviour (WO-039-C1):
    * no public ``ITranscriber`` expansion
    * a recognised engine with no registered adapter fails clearly (no silent
      fallback to ``DeterministicTestTranscriber``)
    * ``AbstractSttAdapter`` provides the offline ``initialize`` lifecycle

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any

import pytest

from app.audio.stt_config import (
    SUPPORTED_ENGINES,
    SttConfig,
    SttConfigError,
    resolve_model_path,
)
from app.audio.stt_seam import (
    AbstractSttAdapter,
    SttEngineUnavailableError,
    SttEngineUnknownError,
    build_transcriber,
    register_engine,
)


@pytest.fixture()
def model_dir() -> str:
    """A temporary directory standing in for a provisioned local model."""
    root = tempfile.mkdtemp(prefix="wo039c_model_")
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# C2 — configuration validation
# ---------------------------------------------------------------------------


def test_valid_model_path_resolves(model_dir: str) -> None:
    cfg = SttConfig(
        enabled=True,
        engine="faster_whisper",
        model_path=model_dir,
        language="uk",
        device="cpu",
    )
    resolved = cfg.resolved_model_path()
    assert resolved == os.path.realpath(model_dir)
    assert os.path.exists(resolved)
    assert cfg.validate() is cfg


def test_missing_model_path_fails_clearly() -> None:
    missing = os.path.join(tempfile.gettempdir(), "wo039c_definitely_missing_model")
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path=missing)
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_empty_model_path_fails() -> None:
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path="")
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_invalid_engine_fails_clearly(model_dir: str) -> None:
    cfg = SttConfig(enabled=True, engine="gpt4", model_path=model_dir)
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_unknown_engine_not_in_supported_set() -> None:
    assert "faster_whisper" in SUPPORTED_ENGINES
    assert "vosk" in SUPPORTED_ENGINES
    assert "gpt4" not in SUPPORTED_ENGINES


def test_disabled_stt_requires_no_model_path() -> None:
    cfg = SttConfig(enabled=False, engine="", model_path=None)
    assert cfg.resolved_model_path() is None
    assert cfg.validate() is cfg


def test_disabled_stt_ignores_engine() -> None:
    cfg = SttConfig(enabled=False, engine="faster_whisper", model_path=None)
    assert cfg.resolved_model_path() is None


def test_language_setting() -> None:
    assert SttConfig(language="uk").language == "uk"
    assert SttConfig(language="en").language == "en"
    assert SttConfig().language is None


def test_device_setting() -> None:
    assert SttConfig(device="cpu").device == "cpu"
    assert SttConfig(device="cuda").device == "cuda"
    assert SttConfig().device == "cpu"


def test_from_dict_roundtrip(model_dir: str) -> None:
    cfg = SttConfig.from_dict(
        {
            "enabled": True,
            "engine": "VOSK",  # case-insensitive, normalised
            "model_path": model_dir,
            "language": "uk",
            "device": "cpu",
            "unknown_key": "ignored",
        }
    )
    assert cfg.enabled is True
    assert cfg.engine == "vosk"
    assert cfg.model_path == model_dir
    assert cfg.language == "uk"
    assert cfg.device == "cpu"
    assert cfg.resolved_model_path() == os.path.realpath(model_dir)


def test_from_dict_none() -> None:
    cfg = SttConfig.from_dict(None)
    assert cfg.enabled is False
    assert cfg.engine == ""
    assert cfg.model_path is None


# ---------------------------------------------------------------------------
# C2 — model path security
# ---------------------------------------------------------------------------


def test_model_root_containment_accepts_inner_path(model_dir: str) -> None:
    inner = os.path.join(model_dir, "model.bin")
    with open(inner, "w") as fh:
        fh.write("x")
    cfg = SttConfig(
        enabled=True,
        engine="vosk",
        model_path=inner,
        model_root=model_dir,
    )
    assert cfg.resolved_model_path() == os.path.realpath(inner)


def test_model_root_containment_rejects_traversal(model_dir: str) -> None:
    escaping = os.path.join(model_dir, "..", "outside", "model")
    cfg = SttConfig(
        enabled=True,
        engine="vosk",
        model_path=escaping,
        model_root=model_dir,
    )
    with pytest.raises(SttConfigError):
        cfg.resolved_model_path()


def test_resolve_model_path_empty_rejected() -> None:
    with pytest.raises(SttConfigError):
        resolve_model_path("   ")


# ---------------------------------------------------------------------------
# C1 — adapter seam
# ---------------------------------------------------------------------------


class _FakeAdapter(AbstractSttAdapter):
    """A minimal non-inference adapter used to exercise the offline seam."""

    def __init__(self, config: SttConfig) -> None:
        super().__init__(config)

    def initialize(self, config: SttConfig) -> None:
        # Model must already exist locally; otherwise fail clearly.
        path = config.resolved_model_path()
        self._model = f"{config.engine}:{os.path.basename(path)}"
        self._ready = True

    @property
    def model(self) -> str:
        return self._model

    def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        return ""

    def is_ready(self) -> bool:
        return self._ready


def _register_fake(engine: str) -> None:
    register_engine(engine, lambda config: _FakeAdapter(config))


def test_register_unknown_engine_rejected() -> None:
    with pytest.raises(SttEngineUnknownError):
        register_engine("bogus_engine", lambda config: _FakeAdapter(config))


def test_recognised_engine_no_adapter_no_silent_fallback(model_dir: str) -> None:
    # faster_whisper is recognised but not registered here -> must fail clearly,
    # NOT silently return DeterministicTestTranscriber.
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path=model_dir)
    with pytest.raises(SttEngineUnavailableError):
        build_transcriber(cfg)


def test_register_and_build_offline_init_ready(model_dir: str) -> None:
    _register_fake("vosk")
    cfg = SttConfig(enabled=True, engine="vosk", model_path=model_dir)
    adapter = build_transcriber(cfg)
    assert isinstance(adapter, _FakeAdapter)
    assert adapter.is_ready() is True
    assert adapter.model == f"vosk:{os.path.basename(os.path.realpath(model_dir))}"


def test_register_and_build_missing_model_fails_before_engine(model_dir: str) -> None:
    _register_fake("vosk")
    missing = os.path.join(model_dir, "nope")
    cfg = SttConfig(enabled=True, engine="vosk", model_path=missing)
    with pytest.raises(SttConfigError):
        build_transcriber(cfg)


def test_build_disabled_stt_rejected(model_dir: str) -> None:
    cfg = SttConfig(enabled=False, engine="vosk", model_path=model_dir)
    with pytest.raises(SttConfigError):
        build_transcriber(cfg)


def test_build_unknown_engine_rejected(model_dir: str) -> None:
    cfg = SttConfig(enabled=True, engine="gpt4", model_path=model_dir)
    with pytest.raises(SttConfigError):
        build_transcriber(cfg)


def test_public_contract_not_expanded(model_dir: str) -> None:
    # The Core contract remains the three-interface-method ITranscriber.  The
    # offline lifecycle hook lives on the adapter, not the Core contract.
    cfg = SttConfig(enabled=True, engine="faster_whisper", model_path=model_dir)
    assert callable(getattr(cfg, "resolved_model_path"))
    assert not hasattr(cfg, "transcribe")  # config is not the transcriber
