"""Pattern Matching Module.

Provides wildcard and regex pattern matching for event routing.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import fnmatch
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Optional, Pattern, Set, Union


class PatternType(str, Enum):
    """Pattern matching types."""

    EXACT = "exact"
    WILDCARD = "wildcard"
    REGEX = "regex"
    PREFIX = "prefix"
    SUFFIX = "suffix"
    CONTAINS = "contains"


@dataclass
class MatchResult:
    """Result of pattern matching.

    Attributes:
        matched: Whether the pattern matched.
        pattern: Pattern that was checked.
        matched_value: The value that matched.
        groups: Captured groups (for regex).
        score: Match confidence score (0-100).
    """

    matched: bool
    pattern: str
    matched_value: str
    groups: List[str] = field(default_factory=list)
    score: float = 0.0

    @property
    def has_groups(self) -> bool:
        """Check if there are captured groups.

        Returns:
            True if there are groups.
        """
        return len(self.groups) > 0


class PatternMatcher(ABC):
    """Abstract base class for pattern matchers."""

    @abstractmethod
    def match(self, pattern: str, value: str) -> MatchResult:
        """Match a pattern against a value.

        Args:
            pattern: Pattern to match.
            value: Value to check.

        Returns:
            MatchResult with match information.
        """
        pass

    @abstractmethod
    def get_pattern_type(self) -> PatternType:
        """Get the pattern type.

        Returns:
            PatternType enum value.
        """
        pass


class ExactMatcher(PatternMatcher):
    """Exact string match (case-insensitive option)."""

    def __init__(self, case_sensitive: bool = True) -> None:
        """Initialize ExactMatcher.

        Args:
            case_sensitive: Whether matching is case-sensitive.
        """
        self.case_sensitive = case_sensitive

    def match(self, pattern: str, value: str) -> MatchResult:
        """Match exact string.

        Args:
            pattern: Pattern to match.
            value: Value to check.

        Returns:
            MatchResult.
        """
        if not self.case_sensitive:
            pattern_lower = pattern.lower()
            value_lower = value.lower()
        else:
            pattern_lower = pattern
            value_lower = value

        matched = pattern_lower == value_lower
        score = 100.0 if matched else 0.0

        return MatchResult(
            matched=matched,
            pattern=pattern,
            matched_value=value,
            score=score,
        )

    def get_pattern_type(self) -> PatternType:
        """Get pattern type."""
        return PatternType.EXACT


class WildcardMatcher(PatternMatcher):
    """Wildcard pattern matching using fnmatch.

    Supports:
    - * - matches everything
    - ? - matches single character
    - [seq] - matches any character in seq
    - [!seq] - matches any character not in seq
    """

    def __init__(self, case_sensitive: bool = True) -> None:
        """Initialize WildcardMatcher.

        Args:
            case_sensitive: Whether matching is case-sensitive.
        """
        self.case_sensitive = case_sensitive

    def match(self, pattern: str, value: str) -> MatchResult:
        """Match wildcard pattern.

        Args:
            pattern: Wildcard pattern.
            value: Value to check.

        Returns:
            MatchResult.
        """
        if not self.case_sensitive:
            value = value.lower()
            pattern = pattern.lower()

        matched = fnmatch.fnmatch(value, pattern)
        score = 100.0 if matched else 0.0

        return MatchResult(
            matched=matched,
            pattern=pattern,
            matched_value=value,
            score=score,
        )

    def get_pattern_type(self) -> PatternType:
        """Get pattern type."""
        return PatternType.WILDCARD


class RegexMatcher(PatternMatcher):
    """Regular expression pattern matching."""

    def __init__(self) -> None:
        """Initialize RegexMatcher."""
        self._compiled: dict[str, Pattern] = {}

    def _get_pattern(self, pattern: str) -> Pattern:
        """Get or compile regex pattern.

        Args:
            pattern: Pattern string.

        Returns:
            Compiled regex pattern.
        """
        if pattern not in self._compiled:
            self._compiled[pattern] = re.compile(pattern)
        return self._compiled[pattern]

    def match(self, pattern: str, value: str) -> MatchResult:
        """Match regex pattern.

        Args:
            pattern: Regex pattern.
            value: Value to check.

        Returns:
            MatchResult.
        """
        try:
            regex = self._get_pattern(pattern)
            match = regex.search(value)

            if match:
                groups = list(match.groups()) if match.groups() else []
                score = 100.0
                return MatchResult(
                    matched=True,
                    pattern=pattern,
                    matched_value=value,
                    groups=groups,
                    score=score,
                )
            else:
                return MatchResult(
                    matched=False,
                    pattern=pattern,
                    matched_value=value,
                    score=0.0,
                )
        except re.error:
            return MatchResult(
                matched=False,
                pattern=pattern,
                matched_value=value,
                score=0.0,
            )

    def get_pattern_type(self) -> PatternType:
        """Get pattern type."""
        return PatternType.REGEX


class PrefixMatcher(PatternMatcher):
    """Prefix matching."""

    def match(self, pattern: str, value: str) -> MatchResult:
        """Match prefix.

        Args:
            pattern: Prefix to match.
            value: Value to check.

        Returns:
            MatchResult.
        """
        matched = value.startswith(pattern)
        score = 100.0 if matched else 0.0

        return MatchResult(
            matched=matched,
            pattern=pattern,
            matched_value=value,
            score=score,
        )

    def get_pattern_type(self) -> PatternType:
        """Get pattern type."""
        return PatternType.PREFIX


class SuffixMatcher(PatternMatcher):
    """Suffix matching."""

    def match(self, pattern: str, value: str) -> MatchResult:
        """Match suffix.

        Args:
            pattern: Suffix to match.
            value: Value to check.

        Returns:
            MatchResult.
        """
        matched = value.endswith(pattern)
        score = 100.0 if matched else 0.0

        return MatchResult(
            matched=matched,
            pattern=pattern,
            matched_value=value,
            score=score,
        )

    def get_pattern_type(self) -> PatternType:
        """Get pattern type."""
        return PatternType.SUFFIX


class ContainsMatcher(PatternMatcher):
    """Contains matching."""

    def match(self, pattern: str, value: str) -> MatchResult:
        """Match if value contains pattern.

        Args:
            pattern: Substring to find.
            value: Value to check.

        Returns:
            MatchResult.
        """
        matched = pattern in value
        score = 100.0 if matched else 0.0

        return MatchResult(
            matched=matched,
            pattern=pattern,
            matched_value=value,
            score=score,
        )

    def get_pattern_type(self) -> PatternType:
        """Get pattern type."""
        return PatternType.CONTAINS


class MultiMatcher:
    """Combines multiple pattern matchers.

    Supports OR matching across different pattern types.
    Automatically detects pattern type.
    """

    def __init__(self) -> None:
        """Initialize MultiMatcher."""
        self.matchers: dict[PatternType, PatternMatcher] = {
            PatternType.EXACT: ExactMatcher(),
            PatternType.WILDCARD: WildcardMatcher(),
            PatternType.REGEX: RegexMatcher(),
            PatternType.PREFIX: PrefixMatcher(),
            PatternType.SUFFIX: SuffixMatcher(),
            PatternType.CONTAINS: ContainsMatcher(),
        }

    def match_any(
        self,
        patterns: List[str],
        value: str,
    ) -> List[MatchResult]:
        """Match value against multiple patterns.

        Args:
            patterns: List of patterns.
            value: Value to check.

        Returns:
            List of MatchResults for all patterns.
        """
        results = []
        for pattern in patterns:
            matcher = self._detect_matcher(pattern)
            results.append(matcher.match(pattern, value))
        return results

    def match_all(
        self,
        patterns: List[str],
        value: str,
    ) -> bool:
        """Check if all patterns match.

        Args:
            patterns: List of patterns.
            value: Value to check.

        Returns:
            True if all patterns match.
        """
        results = self.match_any(patterns, value)
        return all(r.matched for r in results)

    def _detect_matcher(self, pattern: str) -> PatternMatcher:
        """Detect pattern type and return appropriate matcher.

        Args:
            pattern: Pattern to analyze.

        Returns:
            Appropriate PatternMatcher.
        """
        if re.match(r"^[a-zA-Z0-9_-]+$", pattern):
            return self.matchers[PatternType.EXACT]
        elif "*" in pattern or "?" in pattern or "[" in pattern:
            return self.matchers[PatternType.WILDCARD]
        elif pattern.startswith("^") or pattern.endswith("$") or "(" in pattern:
            return self.matchers[PatternType.REGEX]
        elif pattern.startswith("*") and pattern.endswith("*"):
            return self.matchers[PatternType.CONTAINS]
        elif pattern.endswith("*"):
            return self.matchers[PatternType.PREFIX]
        elif pattern.startswith("*"):
            return self.matchers[PatternType.SUFFIX]
        else:
            return self.matchers[PatternType.EXACT]
