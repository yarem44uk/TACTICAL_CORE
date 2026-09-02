"""WO-039-C2 — Offline STT model configuration.

:class:`SttConfig` holds the minimum configuration required for a provisioned
local (offline) speech-to-text model.  It follows the existing frozen-dataclass
config convention (``AudioConfig`` / ``RecordingConfig`` / ``VadConfig``).

Required conceptual settings (WO-039-C2):

    enabled      master switch for the STT subsystem
    engine       engine identifier (``faster_whisper`` | ``vosk``)
    model_path   local path to the provisioned model (never downloaded)
    language     language hint
    device       compute device (``cpu`` / ``cuda`` / ...)

The configuration is explicit, validated, deterministic, local-path based and
offline.  Validation never reaches the network, never downloads a model and
never executes a model file as a program.

Model-path policy:
    * resolve deterministically (expand ``~``, make absolute, canonicalise);
    * reject invalid / empty paths;
    * fail clearly when the local model is missing (no download, no network);
    * when ``model_root`` is set, reject any path that escapes it (path
      traversal guard);
    * never execute the model file as a program.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any


class SttConfigError(Exception):
    """Raised when an STT configuration is invalid or a model path is unusable."""


# Recognised engine identifiers.  Engine selection is deliberately
# NOT_YET_JUSTIFIED (WO-039-C): this is the *recognised* set, not a production
# choice between faster-whisper and Vosk.
SUPPORTED_ENGINES: frozenset[str] = frozenset({"faster_whisper", "vosk"})


def resolve_model_path(model_path: str, *, model_root: str | None = None) -> str:
    """Resolve a local model path deterministically and verify it exists.

    Steps:
        * reject an empty / whitespace-only path;
        * expand ``~`` and make the path absolute;
        * canonicalise with :func:`os.path.realpath` (symlink-safe);
        * when ``model_root`` is set, enforce containment (path-traversal guard);
        * fail clearly when the resolved path does not exist.

    This function never reaches the network, never downloads a model and never
    executes the model file as a program.

    Args:
        model_path: The configured local model path.
        model_root: Optional base directory the resolved path must be confined to.

    Returns:
        The canonical, verified absolute model path.

    Raises:
        SttConfigError: If the path is empty, escapes ``model_root``, or does not
            exist on disk.
    """
    if not model_path or not str(model_path).strip():
        raise SttConfigError("model path must not be empty")

    raw = os.path.abspath(os.path.expanduser(str(model_path).strip()))
    real = os.path.realpath(raw)

    if model_root is not None:
        root = os.path.realpath(
            os.path.abspath(os.path.expanduser(str(model_root)))
        )
        if not (real == root or real.startswith(root + os.sep)):
            raise SttConfigError(
                f"model path escapes configured model root: {real!r}"
            )

    if not os.path.exists(real):
        raise SttConfigError(f"model path does not exist: {real}")

    return real


@dataclass(frozen=True)
class SttConfig:
    """Immutable, validated configuration for the offline STT subsystem.

    Attributes:
        enabled: Master switch.  When ``False`` the STT subsystem is disabled and
            no model path / engine is required.
        engine: Engine identifier.  Must be one of :data:`SUPPORTED_ENGINES`
            when ``enabled``.
        model_path: Local path to the provisioned model.  Required when
            ``enabled``.
        language: Language hint (e.g. ``"uk"``, ``"en"``).
        device: Compute device (``"cpu"`` / ``"cuda"`` / ...).
        model_root: Optional base directory that ``model_path`` must be confined
            to (path-traversal guard).
    """

    enabled: bool = False
    engine: str = ""
    model_path: str | None = None
    language: str | None = None
    device: str = "cpu"
    model_root: str | None = None

    def with_options(self, **kwargs: Any) -> "SttConfig":
        """Return a copy with selected fields overridden (immutable config)."""
        return replace(self, **kwargs)

    @classmethod
    def from_dict(cls, config: dict[str, Any] | None) -> "SttConfig":
        """Build an ``SttConfig`` from an opaque config dict.

        Unknown keys are ignored; missing keys fall back to defaults.  This
        mirrors the ``AudioConfig`` / ``RecordingConfig`` convention.
        """
        if config is None:
            config = {}
        return cls(
            enabled=bool(config.get("enabled", False)),
            engine=str(config.get("engine", "")).strip().lower(),
            model_path=config.get("model_path"),
            language=config.get("language"),
            device=str(config.get("device", "cpu")).strip().lower() or "cpu",
            model_root=config.get("model_root"),
        )

    def resolved_model_path(self) -> str | None:
        """Return the canonical, verified local model path.

        Returns ``None`` when STT is disabled (no model required).  Otherwise
        validates the engine and model path and returns the canonical resolved
        path, raising :class:`SttConfigError` on any invalid configuration or a
        missing local model.  No download, no network, no execution.
        """
        if not self.enabled:
            return None
        if not self.engine:
            raise SttConfigError("STT engine must be set when enabled")
        if self.engine not in SUPPORTED_ENGINES:
            raise SttConfigError(
                f"unsupported STT engine {self.engine!r}; "
                f"supported: {sorted(SUPPORTED_ENGINES)}"
            )
        if not self.model_path or not str(self.model_path).strip():
            raise SttConfigError("model_path must be set when STT is enabled")
        return resolve_model_path(str(self.model_path), model_root=self.model_root)

    def validate(self) -> "SttConfig":
        """Validate the configuration, raising :class:`SttConfigError` on failure.

        Returns ``self`` on success so the call can be chained.
        """
        self.resolved_model_path()
        return self
