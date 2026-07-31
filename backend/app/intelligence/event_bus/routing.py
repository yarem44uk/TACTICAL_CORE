"""Event Routing Module.

Provides routing logic for event distribution.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4

from app.intelligence.event_bus.patterns import MatchResult, MultiMatcher
from app.intelligence.event_bus.subscriptions import Subscription


class RoutingStrategy(str, Enum):
    """Event routing strategies."""

    BROADCAST = "broadcast"
    ROUND_ROBIN = "round_robin"
    PRIORITY = "priority"
    LOAD_BALANCED = "load_balanced"


@dataclass
class RoutingRule:
    """Defines a routing rule for event distribution.

    Attributes:
        id: Unique rule identifier.
        name: Human-readable rule name.
        source: Source filter pattern.
        event_type: Event type filter.
        destination: Destination pattern.
        priority: Rule priority (higher = earlier).
        enabled: Whether rule is active.
        conditions: Additional conditions.
        transformations: Payload transformations.
    """

    id: str
    name: str
    source: Optional[str] = None
    event_type: Optional[str] = None
    destination: Optional[str] = None
    priority: int = 0
    enabled: bool = True
    conditions: Dict[str, Any] = field(default_factory=dict)
    transformations: List[Callable] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def matches(
        self,
        event_type: str,
        source: Optional[str] = None,
    ) -> bool:
        """Check if rule matches an event.

        Args:
            event_type: Event type to check.
            source: Event source to check.

        Returns:
            True if rule matches.
        """
        if not self.enabled:
            return False

        # Check event type
        if self.event_type and self.event_type != event_type:
            return False

        # Check source
        if self.source and source:
            matcher = MultiMatcher()
            if not matcher.match_all([self.source], source):
                return False

        return True

    def transform(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Apply transformations to payload.

        Args:
            payload: Event payload.

        Returns:
            Transformed payload.
        """
        result = payload.copy()
        for transform in self.transformations:
            result = transform(result)
        return result


class RoutingTable:
    """Maintains routing rules and provides routing decisions.

    Attributes:
        rules: All routing rules.
    """

    def __init__(self) -> None:
        """Initialize the RoutingTable."""
        self._rules: Dict[str, RoutingRule] = {}
        self._round_robin_index: Dict[str, int] = {}

    def add_rule(self, rule: RoutingRule) -> None:
        """Add a routing rule.

        Args:
            rule: Rule to add.
        """
        self._rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a routing rule.

        Args:
            rule_id: Rule identifier.

        Returns:
            True if removed, False if not found.
        """
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[RoutingRule]:
        """Get a routing rule by ID.

        Args:
            rule_id: Rule identifier.

        Returns:
            RoutingRule if found, None otherwise.
        """
        return self._rules.get(rule_id)

    def find_matching_rules(
        self,
        event_type: str,
        source: Optional[str] = None,
    ) -> List[RoutingRule]:
        """Find all rules matching an event.

        Args:
            event_type: Event type.
            source: Event source.

        Returns:
            List of matching rules sorted by priority.
        """
        matches = [
            rule for rule in self._rules.values()
            if rule.matches(event_type, source)
        ]
        matches.sort(key=lambda r: r.priority, reverse=True)
        return matches

    def get_all_rules(self) -> List[RoutingRule]:
        """Get all routing rules.

        Returns:
            List of all rules.
        """
        return list(self._rules.values())


class EventRouter:
    """Routes events to appropriate destinations.

    Implements routing strategies and rule-based routing.

    Attributes:
        routing_table: Routing table.
        strategy: Routing strategy.
        matcher: Pattern matcher instance.
    """

    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
    ) -> None:
        """Initialize the EventRouter.

        Args:
            strategy: Default routing strategy.
        """
        self.routing_table = RoutingTable()
        self.strategy = strategy
        self.matcher = MultiMatcher()
        self._destinations: Dict[str, Set[str]] = {}

    def add_destination(
        self,
        pattern: str,
        destination: str,
    ) -> None:
        """Add a routing destination.

        Args:
            pattern: Pattern to match.
            destination: Destination identifier.
        """
        if pattern not in self._destinations:
            self._destinations[pattern] = set()
        self._destinations[pattern].add(destination)

    def remove_destination(
        self,
        pattern: str,
        destination: str,
    ) -> None:
        """Remove a routing destination.

        Args:
            pattern: Pattern.
            destination: Destination to remove.
        """
        if pattern in self._destinations:
            self._destinations[pattern].discard(destination)

    def get_destinations(
        self,
        event_type: str,
        source: Optional[str] = None,
    ) -> Set[str]:
        """Get destinations for an event.

        Args:
            event_type: Event type.
            source: Event source.

        Returns:
            Set of destination identifiers.
        """
        destinations: Set[str] = set()

        # Check pattern destinations
        for pattern, dests in self._destinations.items():
            if self.matcher.match_all([pattern], event_type):
                destinations.update(dests)

        # Apply routing rules
        rules = self.routing_table.find_matching_rules(event_type, source)
        for rule in rules:
            if rule.destination:
                destinations.add(rule.destination)

        return destinations

    def route(
        self,
        event_type: str,
        source: Optional[str] = None,
        subscriptions: Optional[List[Subscription]] = None,
    ) -> List[Subscription]:
        """Route event to appropriate subscriptions.

        Args:
            event_type: Event type.
            source: Event source.
            subscriptions: Available subscriptions.

        Returns:
            List of subscriptions to notify.
        """
        if subscriptions is None:
            return []

        matching_subs = []
        for sub in subscriptions:
            if not sub.is_active:
                continue

            # Check event type
            if sub.event_types and event_type not in sub.event_types:
                continue

            # Check patterns
            if sub.patterns:
                pattern_match = False
                for pattern in sub.patterns:
                    match_result = self.matcher.match_any([pattern], event_type)
                    if any(r.matched for r in match_result):
                        pattern_match = True
                        break
                if not pattern_match:
                    continue

            matching_subs.append(sub)

        # Apply routing strategy
        if self.strategy == RoutingStrategy.BROADCAST:
            return matching_subs
        elif self.strategy == RoutingStrategy.PRIORITY:
            return sorted(matching_subs, key=lambda s: s.priority, reverse=True)
        elif self.strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin(matching_subs)
        else:
            return matching_subs

    def _round_robin(
        self,
        subscriptions: List[Subscription],
    ) -> List[Subscription]:
        """Apply round-robin routing.

        Args:
            subscriptions: Available subscriptions.

        Returns:
            Rotated list of subscriptions.
        """
        if not subscriptions:
            return []

        key = id(subscriptions)
        current_index = self._round_robin_index.get(key, 0)
        rotated = subscriptions[current_index:] + subscriptions[:current_index]
        self._round_robin_index[key] = (current_index + 1) % len(subscriptions)
        return rotated
