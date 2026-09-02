"""WO-039-C1 — Real offline STT adapter seam.

This module provides the minimum engine-independent structure that lets a real
offline STT engine (faster-whisper or Vosk) plug into the existing
``app.contracts.audio.ITranscriber`` seam *without touching the Core*:

    Real STT engine -> AbstractSttAdapter -> ITranscriber

The public ``ITranscriber`` contract is NOT expanded (WO-039-C1: prefer no
public interface expansion).  The offline lifecycle hook ``initialize(config)``
lives behind the adapter boundary on :class:`AbstractSttAdapter`.

No engine is installed and no inference is implemented here (WO-039-C).  The
seam exposes:

  * :class:`AbstractSttAdapter` — the base a real engine adapter subclasses.  It
    adds the ``initialize(config)`` offline lifecycle hook and holds a validated
    :class:`SttConfig`.
  * :func:`register_engine` / :func:`build_transcriber` — the extension point
    and factory.  A real engine is registered later; until then
    ``build_transcriber`` raises a clear :class:`SttEngineUnavailableError` for a
    *recognised* engine, so there is NEVER a silent fallback to
    ``DeterministicTestTranscriber`` in a production STT configuration.

Offline initialization semantics (WO-039-C2):

    configured local model exists   -> initialize -> ready
    configured local model missing  -> initialization fails clearly
                                       (no fallback download, no network)

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from app.contracts.audio import ITranscriber
from app.audio.stt_config import (
    SUPPORTED_ENGINES,
    SttConfig,
    SttConfigError,
)


class SttEngineError(Exception):
    """Base error for engine selection / instantiation problems."""


class SttEngineUnknownError(SttEngineError):
    """Raised for an engine identifier that is not recognised."""


class SttEngineUnavailableError(SttEngineError):
    """Raised for a recognised engine whose adapter is not yet registered."""


class AbstractSttAdapter(ITranscriber, ABC):
    """Base class for a real offline STT engine adapter.

    A real adapter (e.g. ``FasterWhisperTranscriber`` or ``VoskTranscriber``)
    subclasses this, implements the ``ITranscriber`` methods (``model`` /
    ``transcribe`` / ``is_ready``) and the :meth:`initialize` offline lifecycle
    hook.  The Core only ever depends on ``ITranscriber``; ``initialize`` is
    behind the adapter boundary.
    """

    def __init__(self, config: SttConfig) -> None:
        self._config = config
        self._ready = False

    @abstractmethod
    def initialize(self, config: SttConfig) -> None:
        """Load the configured offline model and transition to ready.

        The local model must already exist on disk.  A missing model raises
        :class:`SttConfigError` — there is no fallback download and no network
        access.
        """
        raise NotImplementedError


EngineFactory = Callable[[SttConfig], ITranscriber]

_ENGINE_FACTORIES: dict[str, EngineFactory] = {}


def register_engine(engine_id: str, factory: EngineFactory) -> None:
    """Register an engine adapter factory under a recognised engine identifier.

    Args:
        engine_id: A recognised engine identifier (see
            :data:`app.audio.stt_config.SUPPORTED_ENGINES`).
        factory: Callable ``(config: SttConfig) -> ITranscriber`` that builds a
            (possibly not-yet-initialized) adapter.

    Raises:
        SttEngineUnknownError: If ``engine_id`` is not recognised.
    """
    engine_id = engine_id.strip().lower()
    if engine_id not in SUPPORTED_ENGINES:
        raise SttEngineUnknownError(f"unsupported STT engine {engine_id!r}")
    _ENGINE_FACTORIES[engine_id] = factory


def build_transcriber(config: SttConfig) -> ITranscriber:
    """Build an ``ITranscriber`` for the given configuration (offline seam).

    The configuration is validated and the local model path verified first, so a
    missing model fails clearly before any engine is instantiated.  A recognised
    engine whose adapter is not yet registered raises
    :class:`SttEngineUnavailableError` — there is no silent fallback.

    Raises:
        SttConfigError: If STT is disabled, the engine is unsupported, or the
            local model is missing / invalid.
        SttEngineUnavailableError: If the engine is recognised but no adapter is
            registered.
    """
    if not config.enabled:
        raise SttConfigError("STT is disabled; no transcriber can be built")
    config.validate()  # raises SttConfigError on invalid engine / missing model

    factory = _ENGINE_FACTORIES.get(config.engine)
    if factory is None:
        raise SttEngineUnavailableError(
            f"STT engine {config.engine!r} is recognised but no adapter is registered"
        )

    adapter = factory(config)
    if isinstance(adapter, AbstractSttAdapter):
        adapter.initialize(config)
    return adapter
