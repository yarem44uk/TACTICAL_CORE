"""WO-039-B — Energy / RMS adaptive-threshold voice-activity detector.

:class:`EnergyVad` implements the existing ``app.contracts.audio.IVAD`` seam
(W-039-B §5).  It is a deterministic, dependency-free VAD for the verified
radio signal (PCM S16LE, 8 kHz, mono):

    energy = RMS of the frame's 16-bit samples
    speech = energy >= threshold

Threshold modes (W-039-B §6/§13):
  * ``adaptive`` (default) — the noise floor is tracked as the low percentile of
    a bounded sliding window of recent frame energies.  Frames confidently
    classified as speech never feed the noise floor (so a speech burst cannot
    chase the floor upward until the speech is truncated), while a *prolonged
    stable constant-energy* signal (hiss/static/carrier) is eventually
    re-classified as background by the stability/persistence tracker and then
    absorbed into the floor — so sustained non-voice noise does not create an
    endless recording.  A burst of speech (energy well above the floor, and
    amplitude-modulated) is detected.
  * ``fixed_threshold`` — an absolute threshold in RMS units.  Used by the
    deterministic segmentation tests (W-039-B §14) so a long loud tone is
    stably classified as speech without the adaptive floor chasing it.

The VAD is stateful (it tracks the noise floor / energy history).  It is pure
Python with no third-party dependency.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import array
import math
from collections import deque
from dataclasses import dataclass, field

from app.contracts.audio import IVAD


@dataclass(frozen=True)
class VadConfig:
    """Configuration for :class:`EnergyVad`.

    Attributes:
        enabled: Whether VAD detection is active.
        adaptive: Use the sliding-window adaptive noise floor (``True``) or an
            absolute threshold (``False``).
        threshold_ratio: Multiplier applied to the tracked noise floor to form
            the speech threshold in adaptive mode.
        fixed_threshold: Absolute RMS speech threshold.  When set it overrides
            the adaptive floor for deterministic operation.
        absolute_min_threshold: Absolute lower bound on the speech threshold.
            Prevents near-silence (RMS ~ 0) from being classified as speech.
        noise_percentile: Percentile of the recent energy window used as the
            noise-floor estimate (e.g. ``20.0`` = 20th percentile).
        history_frames: Bounded number of recent frame energies retained for the
            noise-floor estimate.
        initial_noise_floor: Initial noise-floor estimate before enough history
            has accumulated.
    """

    enabled: bool = True
    adaptive: bool = True
    threshold_ratio: float = 2.5
    fixed_threshold: float | None = None
    absolute_min_threshold: float = 150.0
    noise_percentile: float = 20.0
    history_frames: int = 50
    initial_noise_floor: float = 100.0


def pcm_rms(pcm: bytes) -> float:
    """Return the root-mean-square amplitude of 16-bit little-endian PCM.

    Args:
        pcm: Interleaved PCM ``S16LE`` bytes.

    Returns:
        The RMS amplitude as a float (``0.0`` for empty / too-short input).
    """
    if not pcm:
        return 0.0
    count = len(pcm) // 2
    if count == 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[: count * 2])
    total = 0.0
    for s in samples:
        total += float(s) * float(s)
    return math.sqrt(total / count)


def _percentile(values: list[float], percentile: float) -> float:
    """Return the ``percentile`` value of ``values`` (nearest-rank)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(len(ordered) * percentile / 100.0)
    idx = max(0, min(idx, len(ordered) - 1))
    return ordered[idx]


class EnergyVad(IVAD):
    """RMS energy VAD with an adaptive noise floor (implements ``IVAD``).

    Args:
        config: Optional :class:`VadConfig`.  Defaults to a full adaptive VAD.
    """

    # W-039-B second corrective: a sustained constant-energy signal (carrier /
    # static / tone) must eventually be treated as background and must not
    # create an endless recording.  Speech is amplitude-modulated, so its
    # energy varies frame-to-frame; a prolonged *stable* level is the
    # fingerprint of a non-voice signal.  These parameters bound the
    # stability/persistence tracker used to distinguish the two:
    #   * _STABILITY_WINDOW       — frames of recent energy examined for spread;
    #   * _STABILITY_TOLERANCE    — max relative (max-min)/mean spread to count
    #                               as "stable" (constant);
    #   * _STABLE_BACKGROUND_FRAMES — consecutive stable frames before the
    #                               signal is deemed background, not speech.
    # The speech burst is protected (first corrective: speech frames never feed
    # the adaptive noise floor), but a *prolonged* stable level is eventually
    # absorbed as background (second corrective).  The tracker resets whenever
    # the energy varies, so a speech burst is never suppressed while it
    # modulates.
    _STABILITY_WINDOW = 8
    _STABILITY_TOLERANCE = 0.15
    _STABLE_BACKGROUND_FRAMES = 200

    def __init__(self, config: VadConfig | None = None) -> None:
        self._config = config or VadConfig()
        self._noise_floor = float(self._config.initial_noise_floor)
        self._history: deque[float] = deque(maxlen=self._config.history_frames)
        self._recent: deque[float] = deque(maxlen=self._STABILITY_WINDOW)
        self._stable_frames = 0
        self._last_energy = 0.0
        self._last_threshold = 0.0
        self._is_speech = False

    # -- IVAD interface -----------------------------------------------------

    @property
    def name(self) -> str:
        return "energy-rms-adaptive"

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    def get_energy_level(self, audio_data: bytes) -> float:
        """Return the RMS energy of ``audio_data`` (and cache it)."""
        self._last_energy = pcm_rms(audio_data)
        return self._last_energy

    def detect(self, audio_data: bytes) -> bool:
        """Return ``True`` when ``audio_data`` is classified as speech.

        In adaptive mode the noise floor is refreshed from the low percentile of
        the recent *non-speech* energy window, so sustained constant noise
        converges to non-speech while a speech burst is detected.

        Invariant (W-039-B corrective): frames that are confidently classified
        as speech are never fed back into the noise-floor estimator.  Otherwise
        a continuously active speech signal would drive the noise floor upward
        until the speech itself was classified as silence and a transmission
        would be truncated.

        Second corrective (W-039-B): a *sustained constant-energy* non-voice
        signal (carrier / static / tone) must not remain speech forever, or it
        creates an endless recording.  Such a signal is stable (its energy does
        not vary), whereas speech is amplitude-modulated.  A sufficiently long,
        sufficiently stable constant-energy signal is therefore re-classified
        as background even though its amplitude is above the speech threshold.
        Speech is protected from immediate noise-floor contamination, but a
        prolonged stable level is eventually absorbed as background.
        """
        if not self.is_enabled:
            return False
        energy = self.get_energy_level(audio_data)
        # Classify against the current threshold BEFORE updating the noise
        # floor, so a frame never influences the threshold that classifies it.
        threshold = self._compute_threshold()
        is_speech = energy >= threshold
        self._last_threshold = threshold
        # A sustained constant-energy signal is background, not speech.  This
        # runs on every adaptive frame so a prolonged stable level eventually
        # suppresses the endless-recording chain without special-casing any
        # amplitude value (it is amplitude-independent).
        if self._config.adaptive and self._is_stable_background(energy):
            is_speech = False
        self._is_speech = is_speech
        # ONLY non-speech frames teach the adaptive noise floor.  Speech frames
        # must never raise the floor, or sustained speech would be classified as
        # silence (adaptive threshold runaway).
        if self._config.adaptive and not is_speech:
            self._history.append(energy)
            if len(self._history) >= 3:
                self._noise_floor = _percentile(
                    list(self._history), self._config.noise_percentile
                )
        return is_speech

    # -- observability ------------------------------------------------------

    @property
    def noise_floor(self) -> float:
        """Current tracked noise-floor estimate."""
        return self._noise_floor

    @property
    def last_energy(self) -> float:
        """RMS energy of the last frame processed."""
        return self._last_energy

    @property
    def last_threshold(self) -> float:
        """Speech threshold used for the last frame."""
        return self._last_threshold

    @property
    def is_speech(self) -> bool:
        """Classification of the last frame processed."""
        return self._is_speech

    # -- internals ----------------------------------------------------------

    def _is_stable_background(self, energy: float) -> bool:
        """Return ``True`` when a prolonged stable constant-energy signal is present.

        W-039-B second corrective.  Tracks the relative spread ``(max-min)/mean``
        of a bounded window of recent frame energies.  A *stable* (constant)
        energy level sustained for ``_STABLE_BACKGROUND_FRAMES`` consecutive
        frames is the fingerprint of a non-voice carrier / static / tone and is
        treated as background, not speech.  The counter resets whenever the
        energy varies (speech-like modulation), so a speech burst is never
        suppressed while it modulates.  The window is bounded, so memory use is
        constant.
        """
        self._recent.append(energy)
        if len(self._recent) < self._STABILITY_WINDOW:
            return False
        lo = min(self._recent)
        hi = max(self._recent)
        mean = sum(self._recent) / len(self._recent)
        if mean <= 0.0:
            return False
        spread = (hi - lo) / mean
        if spread <= self._STABILITY_TOLERANCE:
            self._stable_frames += 1
        else:
            self._stable_frames = 0
        return self._stable_frames >= self._STABLE_BACKGROUND_FRAMES

    def _compute_threshold(self) -> float:
        """Compute the current speech threshold."""
        if self._config.fixed_threshold is not None:
            return float(self._config.fixed_threshold)
        floor = self._noise_floor
        if floor < 1.0:
            floor = self._config.absolute_min_threshold
        return max(
            floor * self._config.threshold_ratio,
            self._config.absolute_min_threshold,
        )
