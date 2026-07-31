"""Entity Type Definitions.

Defines entity types, statuses, and relation types for Intelligence Core.

Author: Tactical Core Engineering Team
Version: 2.0 (Constitutional Compliance)

CONSTITUTIONAL COMPLIANCE:
    - EntityStatus follows ENTITY-001 lifecycle states
    - No PENDING state (entities start at UNKNOWN or OBSERVED)
    - No DELETED state (physical deletion forbidden by ENTITY-001)
"""

from enum import Enum


class EntityType(str, Enum):
    """Entity type classifications.

    Defines the categories of entities managed by the system.
    Each type represents a distinct class of operational object.
    """

    UNIT = "unit"
    CONTACT = "contact"
    LOCATION = "location"
    ASSET = "asset"
    INCIDENT = "incident"
    ALERT = "alert"
    VEHICLE = "vehicle"
    WEAPON = "weapon"
    EQUIPMENT = "equipment"
    ORGANIZATION = "organization"
    TASK = "task"
    REPORT = "report"
    CUSTOM = "custom"


class EntityStatus(str, Enum):
    """Entity operational states per ENTITY-001.

    Represents the lifecycle state of an entity.

    Constitutional States (per ENTITY-001 Section 9):
    - UNKNOWN: Initial state, no assessment yet
    - OBSERVED: Seen but not identified
    - IDENTIFIED: Identity confirmed
    - CONFIRMED: Multiple sources agree
    - ACTIVE: Currently active in operational picture
    - INACTIVE: No recent activity
    - ARCHIVED: Retired from active tracking
    - MERGED: Consolidated into another entity
    - SUPERSEDED: Replaced by another entity

    FORBIDDEN STATES:
    - PENDING: Not constitutional
    - DELETED: Physical deletion forbidden by ENTITY-001

    Transition Rules:
    - Fresh entities start at UNKNOWN (or OBSERVED if first sight)
    - DELETED must never be used
    - No state may skip constitutional flow
    """

    UNKNOWN = "unknown"      # Initial state
    OBSERVED = "observed"   # First sight
    IDENTIFIED = "identified"  # Identity known
    CONFIRMED = "confirmed"    # Multiple sources agree
    ACTIVE = "active"       # Operational tracking
    INACTIVE = "inactive"   # No recent activity
    ARCHIVED = "archived"   # Retired
    MERGED = "merged"       # Consolidated
    SUPERSEDED = "superseded"  # Replaced


class EntityRelationType(str, Enum):
    """Entity relationship types.

    Defines valid relationships between entities.
    """

    PARENT = "parent"
    CHILD = "child"
    MEMBER = "member"
    LEADER = "leader"
    SUBORDINATE = "subordinate"
    PEER = "peer"
    LOCATED_AT = "located_at"
    ASSIGNED_TO = "assigned_to"
    REPORTING_TO = "reporting_to"
    PART_OF = "part_of"
    COMMUNICATES_WITH = "communicates_with"
    CONFLICT_WITH = "conflict_with"
    ALLIED_WITH = "allied_with"
    TRACKING = "tracking"
    OBSERVING = "observing"
    ENGAGING = "engaging"
    SUPPORTING = "supporting"
    TRANSPORTING = "transporting"
    SUPPLYING = "supplying"
    CUSTOM = "custom"


class Priority(str, Enum):
    """Priority levels for entities and events."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ROUTINE = "routine"


class IdentityMatchLevel(str, Enum):
    """Identity resolution match levels.

    Per ENTITY-001 Section 11.4:
    - MATCH: Observation belongs to existing Entity
    - PARTIAL_MATCH: Ambiguous, requires more evidence
    - NO_MATCH: New Entity required
    """

    MATCH = "match"
    PARTIAL_MATCH = "partial_match"
    NO_MATCH = "no_match"


# Type aliases for common use
EntityTypeSet = set[EntityType]
EntityId = str
