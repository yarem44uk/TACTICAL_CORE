"""WO-038 — Deterministic callsign detection.

:class:`CallsignDetector` extracts callsigns from a transcript in a
deterministic, configurable way.  It is independent of the event repository and
NEVER alters the original transcript — the full transcript is always preserved.

Output contract (WO-038 §9):

    detected_callsigns: list[str]
    confidence: float
    detection_method: str

Detection strategies (in priority order):
  1. Explicit configured callsign tokens (``callsigns``) matched as whole tokens.
  2. Explicit configured regex patterns (``patterns``).
  3. A default deterministic heuristic for callsigns of the form
     ``<letters>-<digits>`` (e.g. ``Буревій-2``).

A real acoustic/AI detector can replace this later; the seam is the
``detect(text) -> CallsignResult`` contract.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CallsignResult:
    """Result of callsign detection for one transcript.

    Attributes:
        text: The ORIGINAL transcript, unmodified.
        detected_callsigns: Unique callsigns in order of first appearance.
        confidence: Detection confidence in ``[0.0, 1.0]``.
        detection_method: Short label for the strategy used.
    """

    text: str
    detected_callsigns: list[str] = field(default_factory=list)
    confidence: float = 1.0
    detection_method: str = "none"

    def to_dict(self) -> dict:
        """Serialisable representation (keeps the original text intact)."""
        return {
            "text": self.text,
            "detected_callsigns": list(self.detected_callsigns),
            "confidence": self.confidence,
            "detection_method": self.detection_method,
        }


# Default heuristic: a callsign is a run of Unicode letters followed by a
# hyphen and digits (e.g. "Буревій-2", "Сокіл-1").  ``[^\W\d_]`` matches any
# Unicode letter (Latin + Cyrillic + Ukrainian і/ї/є/ґ), avoiding the
# ``а-я``-range gap that would split "Буревій-2" at the 'і'.  The numeric
# suffix is required so plain words ("Говорить", "прийом") are not treated as
# callsigns.
_DEFAULT_CALLSIGN_RE = re.compile(
    r"(?<![^\W\d_])[^\W\d_]{2,}-\d+(?!\d)"
)


class CallsignDetector:
    """Deterministic, configurable callsign detector.

    Args:
        callsigns: Optional explicit list of known callsign tokens.  Matched as
            whole tokens (word-boundary, case-insensitive).
        patterns: Optional list of compiled/string regex patterns.  Matched
            against the transcript.
        confidence: Confidence reported when a configured token/pattern matches.
        heuristic_confidence: Confidence reported when the default heuristic
            matches (lower, since it is a less specific strategy).
    """

    def __init__(
        self,
        callsigns: list[str] | None = None,
        patterns: list[str] | None = None,
        confidence: float = 1.0,
        heuristic_confidence: float = 0.7,
    ) -> None:
        self._callsigns = [str(c) for c in (callsigns or [])]
        self._patterns = [re.compile(p) for p in (patterns or [])]
        self._confidence = confidence
        self._heuristic_confidence = heuristic_confidence

    def detect(self, text: str) -> CallsignResult:
        """Extract callsigns from a transcript.

        Args:
            text: The transcript text.  Never modified.

        Returns:
            A :class:`CallsignResult` preserving ``text`` unchanged.
        """
        if not text:
            return CallsignResult(text=text or "", detected_callsigns=[], confidence=0.0, detection_method="none")

        found: list[str] = []
        method = "none"
        confidence = 0.0

        # Strategy 1: explicit configured tokens (highest confidence).
        for token in self._callsigns:
            if re.search(rf"(?<![A-Za-zА-Яа-яЁё0-9]){re.escape(token)}(?![A-Za-zА-Яа-яЁё0-9])", text, re.IGNORECASE) and token not in found:
                found.append(token)
        if found:
            method = "configured-callsigns"
            confidence = self._confidence
        else:
            # Strategy 2: explicit regex patterns.
            for pattern in self._patterns:
                for m in pattern.finditer(text):
                    value = m.group(0)
                    if value and value not in found:
                        found.append(value)
            if found:
                method = "configured-pattern"
                confidence = self._confidence
            else:
                # Strategy 3: default heuristic.
                for m in _DEFAULT_CALLSIGN_RE.finditer(text):
                    value = m.group(0)
                    if value and value not in found:
                        found.append(value)
                if found:
                    method = "heuristic"
                    confidence = self._heuristic_confidence

        return CallsignResult(
            text=text,
            detected_callsigns=found,
            confidence=confidence,
            detection_method=method,
        )
