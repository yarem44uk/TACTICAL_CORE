# ENTITY-001: Constitutional Architecture
## Intelligence Core — Foundational Specification

**Project:** TACTICAL CORE v1.0  
**Status:** Draft — Under Constitutional Review  
**Version:** 1.0  
**Revision:** 2.2  
**Author:** Chief Systems Architect  
**Date:** Sprint 6  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Purpose of Intelligence Core](#2-purpose-of-intelligence-core)
3. [Architecture Philosophy](#3-architecture-philosophy)
4. [Intelligence Philosophy](#4-intelligence-philosophy)
5. [Constitutional Principles](#5-constitutional-principles)
6. [Future Architecture Constraints](#6-future-architecture-constraints)
7. [Fundamental Concepts](#7-fundamental-concepts)
8. [Observation](#8-observation)
9. [Entity](#9-entity)
10. [Confidence](#10-confidence)
11. [Identity Resolution](#11-identity-resolution)
12. [Knowledge Evolution](#12-knowledge-evolution)
13. [Historical Reconstruction](#13-historical-reconstruction)
14. [Future Intelligence Correlation](#14-future-intelligence-correlation)
15. [Architectural Decisions](#15-architectural-decisions)
16. [Architectural Risks](#16-architectural-risks)
17. [Future Extensions](#17-future-extensions)
18. [Approval Recommendation](#18-approval-recommendation)

---

## 1. Executive Summary

**Purpose:** This document establishes the constitutional architecture of the Intelligence Core for TACTICAL CORE. It defines the fundamental concepts, principles, and constraints upon which every future architecture document and implementation Work Order will depend.

**Constitutional Significance:** After approval, this document becomes immutable. No future architecture document may redefine concepts established here. All subsequent documents SHALL reference ENTITY-001 instead of duplicating definitions.

**Scope:** This document defines WHAT the Intelligence Core is. Future documents will explain HOW it works.

**Review Status:** Independent Architecture Review completed. Revision 2.2 addresses all findings from multiple constitutional audits. Chief Systems Architect approval required to establish Constitutional Baseline.

---

## 2. Purpose of Intelligence Core

The Intelligence Core exists to solve a fundamental operational problem: **fragmented situational awareness**.

In tactical environments, information arrives from multiple independent sources:

- Radio communications
- Signal messages
- ATAK map objects
- Operator observations
- External REST APIs
- Future plugin sources

Each source operates independently. Each source produces data in its own format. Each source maintains its own view of operational reality.

**The Intelligence Core solves this by:**

1. **Unifying all inputs** through a common Observation model
2. **Accumulating knowledge** through Entity evolution
3. **Preserving truth** through immutable Observations
4. **Enabling correlation** through shared identity resolution
5. **Supporting replay** through complete historical preservation

The Intelligence Core does NOT replace source systems. It creates a coherent operational overlay that allows operators to understand the complete tactical picture from a single interface.

---

## 3. Architecture Philosophy

### 3.1 Design Principles

The Intelligence Core architecture follows these guiding principles:

**Truth Ownership:** The Intelligence Core never owns truth. It maintains the best available operational assessment based on accumulated evidence. Source systems own their truth. The Intelligence Core aggregates, correlates, and presents.

**Operational Focus:** Every architectural decision serves operational needs. Theoretical purity yields to practical utility.

**Evolution Over Correction:** When new information contradicts previous assessment, the system evolves its knowledge rather than claiming error. This reflects the reality of tactical operations where partial information is the norm.

**Completeness Over Speed:** Historical preservation takes precedence over storage optimization. Every piece of information may become operationally significant.

**Correlation Readiness:** Every component is designed to participate in future intelligence correlation. Architecture that cannot correlate is architecture that will fail when AI capabilities arrive.

### 3.2 Architectural Goals

1. **Zero information loss** — Every observation is preserved
2. **Complete traceability** — Any entity state can be traced to its origins
3. **Operational confidence** — Operators understand how certain the system is
4. **Temporal awareness** — The system understands time, not just current state
5. **Correlation capability** — Future AI can analyze relationships

---

## 4. Intelligence Philosophy

This chapter explains the conceptual foundation of the Intelligence Core. It defines terms that will be used precisely throughout all subsequent documents.

### 4.1 What is an Observation

An Observation is the **atomic unit of intelligence**.

An Observation represents a single, immutable piece of raw intelligence captured from a source. It is the direct output of a Driver. It is the first-class architectural object from which all knowledge flows.

**Characteristics of an Observation:**
- It is **immutable** — never changed after creation
- It is **attributed** — source, device, operator, timestamp always known
- It is **complete** — contains all raw data captured at the moment
- It is **traceable** — can be followed back to its origin

**What an Observation is NOT:**
- It is not a judgment
- It is not an interpretation
- It is not an assessment
- It is not a conclusion

An Observation is pure capture. What you do with it comes later.

### 4.2 What is an Entity

An Entity is the **current best operational assessment** of a real-world object.

An Entity represents accumulated knowledge about something in the operational environment: a person, a vehicle, a device, a callsign, a location, a mission.

**Key insight:** An Entity is not a database record. It is a living, evolving operational hypothesis.

The Entity knows:
- What we believe this thing is
- How confident we are in that belief
- What we have observed about it
- How it relates to other entities
- What aliases it responds to

The Entity does NOT know:
- Absolute truth (truth belongs to Observations)
- Future behavior
- Complete identity (identity is always partial)

### 4.3 What is Knowledge

Knowledge is the **accumulated understanding** derived from Observations.

Knowledge is NOT:
- A single Observation
- A single Entity state
- A static snapshot

Knowledge IS:
- The complete history of Observations about an Entity
- The evolution of Entity state over time
- The pattern of confidence changes
- The history of identity resolutions

Knowledge grows. It never decreases. New Observations may lower confidence, but they do not erase the history of what was previously believed.

### 4.4 What is Truth

**Truth is the complete set of all Observations.**

The Intelligence Core does not possess truth. It possesses evidence (Observations) and assessment (Entities). Truth is infinite and distributed across all sources.

**What this means operationally:**

- An Entity with high confidence is NOT "true"
- An Entity with low confidence is NOT "false"
- Both represent operational assessments based on available evidence

This philosophy prevents the dangerous illusion that the system "knows" things it cannot know.

### 4.5 Why Observation Never Changes

Once created, an Observation is eternal and immutable.

**Rationale:**

1. **Evidence integrity** — The record of what was captured must be preserved. If Observations could change, history could be rewritten.

2. **Traceability** — Operators must be able to ask "Why does the system believe X?" and receive a complete answer rooted in specific Observations.

3. **Analysis capability** — Future AI analysis requires complete, unmodified evidence. If Observations could change, correlation analysis would be unreliable.

4. **Trust** — The system earns operator trust by never obscuring what it originally observed.

### 4.6 Why Entity Evolves

An Entity changes because new Observations provide new evidence.

**Example:**

1. Observer sees a person. Creates Observation.
2. System creates Entity with low confidence (UNKNOWN state).
3. Same person speaks on radio with callsign "BURYA".
4. New Observation contains "BURYA".
5. Identity Resolution matches to existing Entity.
6. Entity evolves: confidence increases, callsign added, state changes to IDENTIFIED.

The Entity is the **current snapshot** of accumulated knowledge. It is always being updated as new Observations arrive.

### 4.7 Why Confidence Evolves

Confidence changes because evidence changes.

Confidence can:
- **Increase** — More Observations support a belief
- **Decrease** — Contradicting Observations emerge
- **Stabilize** — Pattern of consistent Observations
- **Drift** — Long periods without Observations

Confidence is never arbitrary. Every confidence change has a documented cause rooted in Observation history.

### 4.8 Why History Must Exist Forever

History enables four critical capabilities:

1. **Replay** — Reconstruct any past operational state
2. **Analysis** — Understand how situations developed
3. **Attribution** — Answer "What did we know and when?"
4. **Correlation** — Identify patterns across time

The Intelligence Core never deletes. Entities may transition to INACTIVE or ARCHIVED, but all history remains accessible.

---

## 5. Constitutional Principles

The following 13 principles are constitutional architectural law. They SHALL NOT be violated by any future Work Order.

### Principle 1: Everything Begins with an Observation

No intelligence enters the system except through an Observation. Drivers capture raw data. That data becomes an Observation. Nothing bypasses this.

### Principle 2: Drivers NEVER Create Entities

Drivers produce Observations only. Drivers have no knowledge of Entity existence. Drivers are stateless regarding Entity identity.

### Principle 3: Drivers NEVER Communicate Directly with EntityManager

All Driver output flows through Observation. Identity Resolution determines Entity impact. Direct communication is prohibited.

### Principle 4: EntityManager is NOT CRUD

EntityManager does not create, read, update, delete in the database sense. EntityManager performs identity resolution, observation processing, entity merge, entity split, confidence update, alias management, relationship management, history update.

### Principle 5: Identity Resolution Always Precedes Entity Creation

Before any Entity can be created, Identity Resolution must determine that no existing Entity matches the Observation. Creation occurs ONLY after successful Identity Resolution.

### Principle 6: Entity Represents Operational Knowledge

Entity is NOT a database record. Entity is the current best operational assessment. It is a continuously evolving hypothesis, not a static object.

### Principle 7: Observations Are Immutable Forever

Once created, an Observation cannot be modified, updated, or deleted. It is permanent evidence.

### Principle 8: Knowledge Evolves. Observations Never Change.

Knowledge (Entities) evolves continuously as new Observations arrive. Observations (Truth) never change. The distinction is fundamental.

### Principle 9: Every Architectural Decision Supports Future AI

Every component is designed to participate in AI correlation. If a component cannot support AI, it does not belong to Intelligence Core.

### Principle 10: Architecture First. Implementation Later.

Architecture must be complete and approved before implementation begins. Implementation conforms to architecture.

### Principle 11: Entity Never Owns Truth

Entity represents only the current best operational assessment. Truth is represented only by accumulated Observations.

### Principle 12: Information Is Never Deleted

Observations are immutable. History is preserved forever. Every architectural component supports complete historical reconstruction.

### Principle 13: Every Component Supports Intelligence Correlation

Every architectural component shall support future intelligence correlation. Components that cannot participate in correlation SHALL NOT belong to Intelligence Core.

---

## 6. Future Architecture Constraints

**Relationship to Constitutional Principles:** Constitutional Principles (Section 5) are immutable architectural law — they define the philosophical boundaries of the Intelligence Core and SHALL NOT be violated under any circumstances. Future Architecture Constraints (this section) are architectural requirements that all future Work Orders must incorporate into their design. Constraints operationalize Principles into requirements that implementation must satisfy.

Some content appears in both sections because a single architectural truth may be expressed as both a philosophical Principle (the WHY) and an implementation Constraint (the WHAT must be satisfied). This is intentional. Principles govern judgment; Constraints govern design.

The following 9 constraints SHALL be incorporated into all future architecture and implementation.

### Constraint 1: Entities Are Never Created by Drivers

Drivers produce Observations only. Drivers have no knowledge of Entity existence. Drivers are stateless regarding Entity identity.

### Constraint 2: Observations May Create Zero, One, or Many Entities

An Observation is not guaranteed to create an Entity. One Observation may update an existing Entity, create a new Entity, update multiple Entities, or create no Entity at all. Architecture shall support all four outcomes.

### Constraint 3: Entities May Exist Without Current Observations

Entities represent accumulated operational knowledge. Temporary loss of Observations SHALL NOT delete an Entity. Confidence may decrease. Status may change. History remains intact.

### Constraint 4: Entities Are Never Deleted

Deletion is prohibited. Entities may only transition to INACTIVE, ARCHIVED, MERGED, or SUPERSEDED. Historical references must remain valid forever.

### Constraint 5: Observation Correlation Precedes Event Generation

The Intelligence Core SHALL determine: Is this observation relevant? Does it affect any Entity? Does it create operational significance? Only afterwards may an operational Event be generated. Event generation SHALL NOT be automatic for every Observation.

### Constraint 6: Entity Graph Capability Shall Exist

Architecture SHALL support future graph representation. Entities shall be capable of relationships including Person to Callsign, Person to Device, Device to Radio, Vehicle to Crew, Operator to Signal Account, Mission to Entity, Entity to Location, Entity to Observation.

### Constraint 7: AI Shall Never Read Raw Drivers

Future AI modules SHALL consume only Intelligence Core outputs. AI SHALL NOT communicate directly with Drivers. AI SHALL operate using Observations, Entities, Timeline, Relationships, Knowledge Graph, Confidence. This guarantees deterministic AI behavior.

### Constraint 8: Every Observation Shall Be Traceable

For every Entity update it shall always be possible to answer: Which Observation caused this? Which Driver produced it? Which Device captured it? Which Operator owned it? When did it occur? How confident was the system before? How confident afterwards? Traceability is mandatory.

### Constraint 9: ENTITY-001 Serves as Foundational Model

All future Work Orders including WO-006, WO-007, WO-008, WO-009, WO-010, Speech Recognition, Signal Integration, Multicast Drivers, Timeline, Knowledge Graph, ATAK Integration, AI Correlation Engine shall inherit ENTITY-001 without redefining Entity concepts. ENTITY-001 becomes the constitutional model for Intelligence Core.

---

## 7. Fundamental Concepts

This section provides formal conceptual definitions for core terms.

### Observation

The atomic unit of intelligence capture. Immutable. Created by Drivers. Processed by Intelligence Core. Never modified after creation.

### Entity

The current best operational assessment of a real-world object. Evolves continuously. Never owns truth. Represents accumulated knowledge derived from Observations.

### Knowledge

Accumulated understanding derived from Observations. Grows over time. Includes Entity state history, Observation history, confidence history, relationship history.

### Truth

Complete set of all Observations. Distributed and infinite. Not owned by Intelligence Core. The system maintains evidence, not truth.

### Confidence

Operational measure of belief strength. Based on observation count, consistency, source reliability. Evolves with new evidence. Never arbitrary. An ordered, comparable value. The specific representation of Confidence is defined by the Work Order that implements the Intelligence Core.

### Identity

The set of characteristics that link Observations to Entities. Includes callsigns, physical descriptions, device signatures, behavioral patterns.

### Identity Resolution

The architectural component that determines whether an Observation belongs to an existing Entity or requires a new Entity. Precedes Entity creation. Operates on identity characteristics.

### Alias

An alternative name or identifier for an Entity. One Entity may have many aliases. Example: BURYA, Burya, буря, БУРЯ all resolve to one Entity.

### Source Attribution

The complete provenance information for an Observation. Includes Driver, Device, Operator, Channel, Frequency, Session, Timestamp, Acquisition Method, Reliability.

### Operational Assessment

The current state of an Entity including confidence, status, aliases, relationships, and recent observations.

### Timeline

The ordered sequence of Events generated from Entity updates. Supports temporal queries, replay, historical reconstruction.

### History

Complete record of Entity evolution over time. Includes all Observation references, state changes, confidence changes, alias changes.

### Confidence Evolution

The pattern of confidence changes over time. Tracked for every Entity. Used for pattern analysis and AI correlation.

### Knowledge Evolution

How knowledge grows as new Observations arrive. Entity state changes. Old assessments are preserved in history. Knowledge never decreases.

### Correlation

The process of identifying relationships between Entities, Observations, and Events across time and sources.

### Mission Context

The operational mission within which Entities and Observations exist. May affect priority, classification, and processing rules.

### Operational State

The current status of an Entity in its lifecycle: UNKNOWN, OBSERVED, IDENTIFIED, CONFIRMED, ACTIVE, INACTIVE, ARCHIVED, MERGED, SUPERSEDED.

### Relationship

A first-class architectural concept representing a named connection between two Entities. Relationships enable the Knowledge Graph and support intelligence correlation.

**Purpose:** Relationships capture operational connections between Entities — who communicates with whom, who controls what, who is located where, who is part of which group.

**Meaning:** A Relationship is an architectural assertion that two Entities are operationally connected in a defined way. Every Relationship has a type (the nature of the connection), direction (the flow of the relationship), confidence (the strength of the evidence), and history (the record of when and how the relationship was established or changed).

**History:** Relationship history is preserved forever. When a Relationship is established, modified, or superseded, the previous state is retained. This enables historical graph reconstruction.

**Confidence:** Every Relationship has its own Confidence, independent of the Confidence of its source Entities. A Relationship between two high-confidence Entities may itself have low confidence if the evidence for the connection is weak.

**Graph Participation:** Relationships form the edges of the Knowledge Graph. Every Entity can participate in multiple Relationships. The graph is directed and typed.

**Merge/Split Behavior:** When an Entity is merged, all Relationships referencing the source Entities are consolidated onto the resulting Entity. When an Entity is split, all Relationships are redistributed to the resulting Entities based on the Observation evidence that supports each Relationship. Relationships are never silently destroyed by merge or split operations.

### Driver

A source-specific component that captures raw data from an external system and produces Observations. Drivers are stateless with respect to Entity identity. Drivers produce Observations only and never create or modify Entities. Every piece of intelligence entering the Intelligence Core originates from a Driver.

### Event

An operator-facing signal generated from Entity state changes. Events are derived from Entities, not Observations. Not every Entity change produces an Event. Events enable operators to receive alerts and updates without consuming raw Observations.

**Operational Significance:** An Entity state change has Operational Significance if it meets at least one of the following constitutional criteria:

- **Identity change:** The Entity's identity characteristics have changed (new alias, confirmed identity, state transition from UNKNOWN to IDENTIFIED)
- **Confidence change:** The Entity's Confidence has crossed an operational boundary (transition between confidence tiers)
- **Relationship change:** A new Relationship has been established or an existing Relationship has been superseded
- **Operational State change:** The Entity's Operational State has changed (transition between lifecycle states)
- **Mission impact:** The Entity's change affects the operator's understanding of the current mission situation

Changes that do not meet any of these criteria may be suppressed at the Event layer without violating constitutional requirements. The specific thresholds for confidence tiers and the mechanisms for determining mission impact are defined by the Work Order that implements the Event system. ENTITY-001 constrains only that Operational Significance must be determined before Event generation and that the five categories above constitute the complete set of constitutionally significant change types.

### EntityManager

The architectural component responsible for maintaining Entity state. EntityManager receives Observations after Identity Resolution and performs Entity evolution: identity resolution, observation processing, entity merge, entity split, confidence update, alias management, relationship management, and history update. EntityManager does not perform CRUD operations — it performs intelligence operations on Entities.

### Work Order

A future architecture or implementation document that inherits from ENTITY-001. Work Orders define HOW specific capabilities are realized. Work Orders SHALL reference ENTITY-001 concepts without redefining them. ENTITY-001 is the constitutional parent of all Work Orders.

### Constitutional Baseline

The governance state achieved when ENTITY-001 receives Chief Systems Architect approval. Upon becoming the Constitutional Baseline, ENTITY-001 becomes immutable. No future Work Order may redefine its concepts. All future architecture documents SHALL inherit from the Constitutional Baseline. Changes to the Constitutional Baseline require a Constitutional Amendment per Section 17.3.

### Entity Merge

The architectural process by which two or more Entities that represent the same real-world object are consolidated into a single Entity.

**Observation Preservation:** All Observations from all source Entities remain immutable and are retained in the resulting Entity. No Observation is lost, modified, or deleted.

**Relationship Preservation:** All Relationships referencing any source Entity are consolidated onto the resulting Entity. Duplicate Relationships (multiple source Entities having the same Relationship with the same target) are merged into a single Relationship with Confidence recalculated from combined evidence.

**Confidence Recalculation:** The resulting Entity's Confidence is recalculated from the combined Observation evidence of all source Entities. The recalculation principle is: merged Entity Confidence reflects the total evidentiary support available after consolidation, not the sum or average of source Confidence values. The specific recalculation method is defined by the Work Order that implements Confidence.

**History Preservation:** Complete evolution history from all source Entities is preserved in the resulting Entity. Operators can trace which Observations originated from which source Entity.

**Traceability Preservation:** Every attribute of the resulting Entity is traceable to specific Observations from specific source Entities. The merge operation itself is recorded in History as a discrete event with full attribution.

### Entity Split

The architectural process by which a single Entity is determined to represent two or more distinct real-world objects and is separated into multiple Entities.

**Observation Preservation:** All Observations remain immutable and are redistributed to the resulting Entities based on identity characteristics. No Observation is lost, modified, or deleted.

**Relationship Redistribution:** All Relationships referencing the source Entity are redistributed to the resulting Entities based on the Observation evidence that supports each Relationship. When evidence does not clearly associate a Relationship with a single resulting Entity, the Relationship is preserved on all resulting Entities with a note indicating ambiguity. Relationships are never silently destroyed.

**Confidence Recalculation:** Each resulting Entity's Confidence is recalculated from the Observation evidence assigned to it. The recalculation principle is: split Entity Confidence reflects the evidentiary support available within that Entity's Observation subset, not a proportion of the source Entity's Confidence. The specific recalculation method is defined by the Work Order that implements Confidence.

**History Preservation:** Complete evolution history from the source Entity is preserved and partitioned across resulting Entities. Operators can trace which Observations belong to which resulting Entity.

**Traceability Preservation:** The split operation itself is recorded in History as a discrete event with full attribution. Every attribute of every resulting Entity is traceable to specific Observations.

---

## 8. Observation

### 8.1 Conceptual Definition

An Observation is the **atomic unit of intelligence capture** in TACTICAL CORE. It represents a single, immutable piece of raw intelligence captured from a source system.

**Every piece of information that enters the Intelligence Core must be an Observation.**

### 8.2 Operational Meaning

Observations are created by Drivers when they capture data from source systems:

- Radio transmission captured
- Signal message received
- ATAK object updated
- REST API response received
- Future plugin data captured

Each capture becomes an Observation with complete provenance information.

### 8.3 Observation Lifecycle

1. **Creation** — Driver captures data, creates Observation with provenance
2. **Submission** — Observation submitted to Intelligence Core
3. **Processing** — Identity Resolution determines Entity impact
4. **Attachment** — Observation linked to relevant Entities
5. **Retention** — Observation preserved forever
6. **Replay** — Observation available for historical reconstruction

### 8.4 Immutability Policy

Observations are **immutable after creation**. This is a hard architectural requirement.

- Observation content never changes
- Observation provenance never changes
- Observation timestamp never changes
- Observation links to Entities never break

If an Observation was created in error, the response is creation of a new Observation indicating correction, not modification of the original.

### 8.5 Role Inside Intelligence Core

Observations serve as:
- **Evidence** — The raw data that supports Entity assessments
- **Truth** — The unchanging record of what was captured
- **Traceability anchors** — The fixed points to which all knowledge refers
- **Correlation targets** — The inputs to future AI analysis

---

## 9. Entity

### 9.1 Conceptual Definition

An Entity is the **current best operational assessment** of a real-world object in the operational environment.

An Entity is not a database record. It is a living, evolving operational hypothesis that changes as new Observations arrive.

### 9.2 Operational Meaning

Entities represent things operators need to track:

- People (operators, contacts, targets)
- Vehicles (cars, aircraft, vessels)
- Devices (radios, phones, computers)
- Callsigns (radio identifiers)
- Locations (waypoints, positions, areas)
- Missions (operational activities)
- Groups (organizations, teams)

### 9.3 Entity as Operational Hypothesis

Every Entity is a hypothesis: "This set of Observations represents this real-world object."

Hypotheses can be:
- **Strong** — High confidence, many consistent Observations
- **Weak** — Low confidence, few Observations, inconsistent data
- **Confirmed** — Multiple independent sources agree
- **Disputed** — Conflicting evidence requires resolution

No Entity is permanently correct. Every Entity is continuously re-evaluated with each new Observation.

**Operational State versus Hypothesis Strength:** Operational State (UNKNOWN, OBSERVED, IDENTIFIED, CONFIRMED, ACTIVE, INACTIVE, ARCHIVED, MERGED, SUPERSEDED) and Hypothesis Strength (Strong, Weak, Confirmed, Disputed) are two independent dimensions of Entity characterization. Operational State describes the Entity's position in its lifecycle — whether it is actively being tracked, has gone silent, has been consolidated, or has been replaced. Hypothesis Strength describes the evidentiary support for the current assessment — how much evidence supports it and whether sources agree. An Entity has both an Operational State and a Hypothesis Strength simultaneously. They are related but not derived from one another: an ACTIVE Entity can be Weak, and an INACTIVE Entity can be Confirmed.

See also: Section 4.6 (Why Entity Evolves) for the philosophical rationale of Entity evolution.

### 9.4 Continuous Evolution

Entity state evolves continuously:

- Confidence increases or decreases
- New aliases are added
- New relationships are established
- Location history grows
- Observation count increases
- Status may change

Evolution is tracked in Entity History. Previous states remain accessible.

### 9.5 Relationship to Observations

An Entity is derived from Observations. It cannot exist without Observations. It evolves as new Observations arrive.

The relationship is:
- Many Observations to One Entity (common)
- One Observation to Many Entities (rare, possible)

A single Observation may affect multiple Entities when the captured data contains information about more than one real-world object. For example, a radio transmission mentioning two callsigns generates one Observation that may update two Entities and establish or confirm a Relationship between them. This is a normal outcome of Identity Resolution, not an error condition.

---

## 10. Confidence

### 10.1 Meaning

Confidence is the **operational measure of belief strength** in an Entity's current assessment.

Confidence is NOT:
- A percentage of correctness
- A probability of truth
- A measure of data quality

Confidence IS:
- A measure of evidence strength
- An operational decision aid
- A representation of system belief state

See also: Section 4.7 (Why Confidence Evolves) for the philosophical rationale of Confidence evolution.

### 10.2 Operational Interpretation

High confidence means: "The system has strong, consistent evidence for this assessment."

Low confidence means: "The system has limited or inconsistent evidence."

Confidence affects:
- Display priority on Tactical Wall
- Alert generation
- AI correlation weight
- Operator decision-making

### 10.3 Evolution Over Time

Confidence changes as new Observations arrive:

- **Consistent Observations** — Confidence increases
- **Contradicting Observations** — Confidence decreases
- **New aliases confirmed** — Confidence increases
- **Long silence** — Confidence may decrease over time
- **Conflicting sources** — Confidence decreases

Every confidence change has a documented cause.

### 10.4 Relationship to Knowledge

Confidence is a key component of knowledge. It represents how certain the accumulated knowledge is.

High confidence + low Observation count = fragile knowledge
Low confidence + high Observation count = uncertain knowledge
High confidence + high Observation count = robust knowledge

### 10.5 Representation

Confidence is an ordered, comparable value that represents belief strength. The specific representation of Confidence (numeric scale, named levels, or other format) is defined by the Work Order that implements the Intelligence Core. ENTITY-001 constrains only that Confidence must support ordering (higher indicates stronger belief), comparison between Entities, and historical tracking of changes.

### 10.6 Confidence Floor

Confidence cannot become negative. The minimum Confidence value represents the state of having some evidence but insufficient strength for operational reliance. Confidence must remain ordered at all times — a higher Confidence value always indicates stronger evidentiary support than a lower value. Every Confidence value must be explainable through Observation history: the system must always be able to answer "Why is the Confidence at this level?" by referencing the specific Observations that contributed to it. Confidence must always be historically reconstructable: at any point in time, the Confidence value and its cause can be determined from the preserved record. The specific representation of Confidence, including the minimum value and the scale, is defined by the Work Order that implements Confidence. ENTITY-001 constrains only that Confidence has a floor, remains ordered, and remains explainable.

---

## 11. Identity Resolution

### 11.1 Concept Only

Identity Resolution is an **architectural component** responsible for determining whether an Observation belongs to an existing Entity or requires a new Entity.

### 11.2 Purpose

Identity Resolution solves the fundamental problem: "Have we seen this before?"

Without Identity Resolution:
- Same person produces many duplicate Entities
- No unified view
- Fragmented knowledge

With Identity Resolution:
- Same person produces one Entity
- Complete history
- Unified operational picture

### 11.3 Architectural Role

Identity Resolution is the architectural boundary between Observation and Entity. It is the mechanism by which the Intelligence Core determines whether incoming evidence extends existing knowledge or requires new knowledge structures.

**Architectural Position:** Identity Resolution sits between Observation intake and Entity evolution. Every Observation must pass through Identity Resolution before any Entity state change occurs. Identity Resolution is the gatekeeper of Entity identity.

**Responsibility:** Identity Resolution examines the identity characteristics present in an Observation and determines the relationship between that Observation and the existing Entity space. It answers a single question: "Does this Observation correspond to something we already know about?"

**Relationship Between Observation and Entity:** Observations carry identity characteristics (callsigns, device identifiers, behavioral markers, physical descriptions). Entities accumulate identity characteristics through their Observation history. Identity Resolution compares Observation characteristics against Entity characteristics and determines the mapping between them. This mapping determines whether the Observation extends an existing Entity's history or initiates a new Entity.

**Why Identity Resolution Exists:** Without Identity Resolution, every Observation would create a new Entity, producing duplicate knowledge about the same real-world objects. Identity Resolution enables the Intelligence Core to maintain a unified operational picture by ensuring that Observations about the same object accumulate on the same Entity.

**Why It Is Constitutionally Required:** Identity Resolution is constitutionally required because it enforces Principle 5 (Identity Resolution Always Precedes Entity Creation) and Constraint 1 (Entities Are Never Created by Drivers). It is the architectural mechanism that separates evidence intake (Observation) from knowledge management (Entity). Without this separation, the distinction between raw evidence and operational assessment collapses, and the Intelligence Core cannot maintain traceability, confidence, or historical integrity.

Identity Resolution is a constitutional component, not an implementation detail. HOW Identity Resolution performs matching is defined by a future Work Order. THAT Identity Resolution exists and precedes Entity creation is constitutional law.

See also: Principle 5 (Identity Resolution Always Precedes Entity Creation), Constraint 1 (Entities Are Never Created by Drivers), Section 4.5 (Why Observation Never Changes).

### 11.4 Relationship to Entity and Observation

Identity Resolution examines Observation identity characteristics (callsigns, aliases, patterns) and compares them against known Entity identity information.

It determines:
- **Match** — Observation belongs to existing Entity
- **Partial Match** — Observation may belong, entity evolution pauses until additional evidence resolves ambiguity
- **No Match** — Observation requires new Entity

When Identity Resolution returns Partial Match, the system preserves the Observation and maintains the existing Entity state without modification. The Observation is retained for future resolution. As additional Observations arrive, they provide the evidence needed to resolve the ambiguity. Entity evolution resumes only when subsequent evidence clarifies the identity relationship. This approach preserves both data integrity and operational continuity: no information is lost, no incorrect Entity changes are made, and the system continues to function while ambiguity exists.

### 11.5 Why It Precedes Entity Creation

Identity Resolution must execute before Entity creation because:

1. **Uniqueness** — System must not create duplicate Entities
2. **Continuity** — Observations must link to existing knowledge
3. **History** — New Observations must extend existing history
4. **Accuracy** — System must maintain coherent view

---

## 12. Knowledge Evolution

### 12.1 How Knowledge Grows

Knowledge grows through accumulation:

1. New Observation arrives
2. Identity Resolution matches to Entity
3. Entity state evolves
4. History records the change
5. Knowledge now includes new evidence

### 12.2 How Observations Accumulate

Every Observation linked to an Entity adds to the accumulated knowledge:

- Observation count increases
- Temporal span extends
- Source diversity grows
- Pattern library expands

### 12.3 Why Entities Evolve

Entities evolve because:
- New Observations provide new evidence
- Identity Resolution updates beliefs
- Confidence changes reflect evidence strength
- Aliases expand the identity picture
- Relationships connect entities
- Entity Split corrects prior consolidation errors when a single Entity is determined to represent multiple distinct objects
- Entity Merge consolidates duplicate Entities when multiple Entities are determined to represent the same object

### 12.4 Why Operational Assessment Changes

Operational assessment changes because:
- Initial assessment was based on limited evidence
- New evidence updates beliefs
- Contradicting evidence weakens confidence
- Confirming evidence strengthens confidence
- Pattern matching reveals new connections

### 12.5 Core Concept Interrelationship

The Intelligence Core architecture consists of interconnected concepts that form a complete intelligence pipeline:

**Observation** is the entry point. All intelligence enters as Observations, produced by Drivers from external sources.

**Identity Resolution** determines whether an Observation extends existing knowledge or requires new knowledge structures. Identity Resolution sits between Observation and Entity.

**Entity** is the current operational assessment. Entities evolve as Observations arrive through Identity Resolution. Entities accumulate knowledge about real-world objects.

**Knowledge** is the accumulated understanding derived from all Observations. Knowledge includes Entity state history, Observation history, Confidence history, and Relationship history. Knowledge grows but never decreases.

**Timeline** provides the temporal dimension. The Timeline is the ordered sequence of Events generated from Entity updates. The Timeline enables temporal queries, replay, and historical reconstruction.

**Knowledge Graph** provides the structural dimension. The Knowledge Graph represents Entities and their Relationships as a graph. The Knowledge Graph enables correlation queries and relationship analysis.

**Future AI** consumes the outputs of the Intelligence Core. Future AI modules operate on Observations, Entities, Confidence, Timeline, Knowledge Graph, and Relationships. Future AI never reads raw Drivers. Future AI relies on the constitutional guarantees of traceability, immutability, and confidence.

This pipeline ensures that every piece of intelligence is captured, attributed, correlated, preserved, and made available for analysis.

---

## 13. Historical Reconstruction

### 13.1 Why History Is Preserved Forever

History enables the system to answer: "What did we know and when?"

This is critical for:
- Post-operation analysis
- Intelligence review
- Pattern discovery
- Attribution
- Trust

### 13.2 Architectural Necessity

The architecture requires that:
- Every Observation is preserved
- Every Entity state change is logged
- Every Confidence update is recorded
- Every Alias addition is tracked
- Every Relationship change is documented

### 13.3 Operational Value

Historical reconstruction enables:
- Replay of past operations
- Reconstruction of decisions
- Discovery of patterns
- Attribution of actions
- Analysis of confidence evolution

### 13.4 Replay Capability Conceptually

At any point in time, the system can reconstruct:
- What Entities existed
- What their state was
- What Observations supported that state
- What Confidence levels were
- What Relationships existed

---

## 14. Future Intelligence Correlation

This chapter explains conceptually how the ENTITY-001 constitutional model enables future capabilities.

### 14.1 Speech Intelligence

Speech Intelligence (AUDIO-001) will:
- Capture audio from multicast and operator sources
- Convert speech to text through Speech Recognition
- Detect callsigns through Callsign Detection
- Create Observations with transcription

The constitutional model ensures:
- Every transcription is an Observation
- Every Observation is traceable to source audio
- Every callsign detection is attributable
- Confidence reflects recognition accuracy

### 14.2 Signal Intelligence

Signal Intelligence (SIGNAL-001) will:
- Capture Signal messages
- Parse content and attachments
- Map sender identity
- Create Observations

The constitutional model ensures:
- Every message is an Observation
- Sender identity resolves to Entity
- Attachments are preserved as Observations
- Timeline reflects message chronology

### 14.3 Radio Intelligence

Radio Intelligence combines Speech Intelligence with radio-specific processing:
- Channel attribution
- Session tracking
- Frequency correlation
- Device identification

The constitutional model ensures:
- Radio-specific provenance in Source Attribution
- Callsign resolution to Entity
- Channel history per Entity
- Device fingerprinting

### 14.4 Timeline

Timeline (TIMELINE-001) will:
- Generate Events from Entity updates
- Maintain chronological order
- Enable replay and reconstruction

The constitutional model ensures:
- Every Event is traceable to Entity and Observation
- Complete temporal history
- Cross-source correlation capability
- Historical reconstruction

### 14.5 Knowledge Graph

Knowledge Graph (GRAPH-001) will:
- Represent Entity relationships
- Enable graph analysis
- Support correlation queries

The constitutional model ensures:
- Relationships are first-class concepts
- Every Entity can participate in relationships
- Graph queries are traceable to Observations
- Historical relationships are preserved

### 14.6 ATAK Integration

ATAK integration will:
- Receive ATAK map objects as Observations
- Resolve ATAK entities to Intelligence Core Entities
- Sync operational picture

The constitutional model ensures:
- ATAK objects become Observations
- Entity resolution applies to ATAK data
- Cross-system correlation is possible
- Complete provenance from ATAK source

### 14.7 Mission Analytics

Future mission analytics will:
- Analyze patterns across Observations
- Identify behavioral patterns
- Predict Entity movements
- Assess mission risk

The constitutional model ensures:
- Complete historical data for analysis
- Confidence patterns for prediction
- Relationship patterns for correlation
- Traceable evidence for conclusions

### 14.8 Future AI

Future AI modules will:
- Consume Intelligence Core outputs only
- Perform correlation analysis
- Generate insights
- Support decision-making

The constitutional model ensures:
- AI operates on verified data
- Correlation is deterministic
- Confidence is calculable
- Traceability is complete

---

## 15. Architectural Decisions

### 15.1 Decision: Observation as First-Class Object

**Decision:** Every piece of intelligence entering the system must be represented as an Observation.

**Rationale:** This ensures complete traceability, immutability, and correlation capability. It prevents information bypass and maintains data integrity.

### 15.2 Decision: Entity Is Not a Database Record

**Decision:** Entity represents current best operational assessment, not a static record.

**Rationale:** Operational reality requires continuous re-evaluation. A static record would misrepresent the dynamic nature of tactical intelligence.

### 15.3 Decision: Identity Resolution Precedes Entity Creation

**Decision:** Identity Resolution must execute before any Entity can be created.

**Rationale:** This prevents duplicate Entities, maintains knowledge continuity, and ensures complete history for every real-world object.

### 15.4 Decision: Entity Never Owns Truth

**Decision:** Truth belongs to Observations. Entity represents assessed knowledge.

**Rationale:** This prevents dangerous overconfidence and maintains honest representation of system uncertainty.

### 15.5 Decision: Information Never Deleted

**Decision:** All Observations and historical data are preserved forever.

**Rationale:** Historical evidence is operationally valuable. Deletion destroys traceability and analysis capability.

### 15.6 Decision: Confidence Is First-Class

**Decision:** Confidence is a dedicated architectural concept with explicit update rules and history.

**Rationale:** Confidence is critical for operational decision-making. It must be explicit, trackable, and understandable.

### 15.7 Decision: Alias Model

**Decision:** One Entity may have many aliases. All aliases resolve to one Entity.

**Rationale:** Real-world identity is multi-faceted. A person may be known by callsign, name, nickname, and identifier. The system must handle this.

### 15.8 Architectural Invariants

The following statements are immutable architectural truths. They are derived from the Constitutional Principles and Future Architecture Constraints. They SHALL NOT be violated by any future Work Order. They SHALL NOT be reinterpreted by any future architect.

1. Observation is immutable forever. Once created, an Observation cannot be modified, updated, or deleted.
2. Entity never owns Truth. Entity represents only the current best operational assessment. Truth is represented only by accumulated Observations.
3. Drivers never create Entities. Drivers produce Observations only. Drivers have no knowledge of Entity existence.
4. Identity Resolution always precedes Entity creation. Before any Entity can be created, Identity Resolution must determine that no existing Entity matches the Observation.
5. Information is never deleted. Observations are immutable. History is preserved forever. Every architectural component supports complete historical reconstruction.
6. Every Entity state is explainable through Observation history. For every attribute of every Entity, it must be possible to trace the specific Observations that caused that attribute to exist.
7. Every Entity state change preserves history. When an Entity evolves, its previous state is preserved in History. No historical state is ever lost.
8. Every Relationship has traceable evidence. For every Relationship between two Entities, it must be possible to identify the Observations that support that Relationship.
9. Every Confidence value has a documented cause. For every Confidence change on every Entity, it must be possible to identify the Observation that caused the change.
10. Every Event is derived from an Entity state change. Events are never generated directly from Observations. Every Event is traceable to a specific Entity and a specific Entity state change.
11. AI never reads raw Drivers. Future AI modules consume only Intelligence Core outputs. AI operates using Observations, Entities, Timeline, Relationships, Knowledge Graph, and Confidence.
12. No future Work Order may redefine constitutional concepts. All Work Orders inherit from ENTITY-001. Concepts defined in this document are immutable.

---

## 16. Architectural Risks

### 16.1 Risk: Identity Explosion

**Description:** Large number of Observations creating large number of Entities without proper resolution.

**Probability:** Medium

**Impact:** High

**Mitigation:** Robust Identity Resolution architecture supporting entity consolidation operations.

### 16.2 Risk: Confidence Drift

**Description:** Entity confidence gradually diverges from reality due to stale Observations.

**Probability:** Medium

**Impact:** Medium

**Mitigation:** Confidence decay capability. Operator visibility into confidence changes.

### 16.3 Risk: Circular Dependencies

**Description:** Entity resolution creating circular references between Entities.

**Probability:** Low

**Impact:** High

**Mitigation:** Explicit cycle detection in relationship management. No self-referential Entities.

### 16.4 Risk: Storage Growth

**Description:** Unbounded Observation storage exhausting available storage.

**Probability:** High

**Impact:** Medium

**Mitigation:** Archival policies for historical Observations. Storage management architecture supporting long-term data preservation.

### 16.5 Risk: Performance Degradation

**Description:** Entity queries slowing as Entity count grows.

**Probability:** High

**Impact:** Medium

**Mitigation:** Query architecture supporting scalable Entity access. Performance requirements defined by future Work Orders.

### 16.6 Risk: Architecture Creep

**Description:** Future Work Orders attempting to redefine concepts established in ENTITY-001.

**Probability:** Medium

**Impact:** Medium

**Mitigation:** Strict governance. All future documents must reference ENTITY-001 instead of redefining.

### 16.7 Risk: Semantic Drift

**Description:** Different Work Orders and subsystems interpret the same constitutional concept differently over time. Even with formal definitions, concepts such as "operational significance," "correlation," and "knowledge" may be interpreted differently by different architects, producing subtle architectural inconsistencies.

**Probability:** High

**Impact:** High

**Mitigation:** ENTITY-001 provides formal definitions for all constitutional concepts in Section 7. Future Work Orders SHALL reference ENTITY-001 definitions without reinterpretation. The Constitutional Amendment Process (Section 17.3) provides a mechanism to clarify ambiguous concepts without silent reinterpretation. Architecture Review Board validation of future Work Orders against ENTITY-001 ensures consistent interpretation.

### 16.8 Risk: Event Storm

**Description:** High-volume Observation processing generates excessive Events, overwhelming operators with alerts. Entity updates from many Observations in rapid succession could produce Events faster than operators can process them.

**Probability:** Medium

**Impact:** High

**Mitigation:** ENTITY-001 constrains that Events are generated only for Operationally Significant Entity state changes (Section 7, Event definition). The five constitutional criteria for Operational Significance limit Event generation to changes that affect operator understanding. The Work Order that implements the Event system SHALL incorporate rate-limiting and deduplication capabilities. Event generation SHALL NOT be automatic for every Observation (Constraint 5).

---

## 17. Future Extensions

### 17.1 How This Document Enables Future Architecture

ENTITY-001 establishes the constitutional foundation upon which all future architecture is built:

- **OBS-001 Observation Architecture** — Inherits Observation concept from ENTITY-001
- **FLOW-001 Intelligence Data Flow** — Uses Observation to Entity to Event flow
- **DRV-001 Driver Framework** — Defines Observation production contract
- **AUDIO-001 Speech Intelligence** — Creates Observation from audio
- **SIGNAL-001 Signal Intelligence** — Creates Observation from messages
- **ENTITY-RESOLUTION-001 Identity Resolution** — Precedes Entity creation
- **TIMELINE-001 Timeline** — Events from Entity updates
- **GRAPH-001 Knowledge Graph** — Entity relationships

### 17.2 Why Future Work Orders Must Inherit

Every future Work Order SHALL reference ENTITY-001 concepts without redefining them.

If a future Work Order needs to extend or clarify an ENTITY-001 concept, it must:
1. Reference the original ENTITY-001 definition
2. Explain the extension necessity
3. Obtain Chief Systems Architect approval for the extension

This prevents architectural drift and maintains conceptual coherence.

### 17.3 Constitutional Amendment Process

After ENTITY-001 becomes the Constitutional Baseline, it is immutable. Changes to the Constitutional Baseline require a Constitutional Amendment.

**Constitutional Amendment versus Work Order Extension:** A Work Order Extension (Section 17.2) adds new capability that inherits from existing ENTITY-001 concepts. A Constitutional Amendment modifies ENTITY-001 itself. The distinction is critical: extensions expand the architecture; amendments change the foundation.

**Amendment Authority:** Constitutional Amendments require Chief Systems Architect approval. The Chief Systems Architect evaluates whether the proposed amendment:
1. Addresses a genuine architectural deficiency (not a preference or implementation choice)
2. Maintains compatibility with all existing Work Orders
3. Does not violate the core constitutional philosophy (Observation immutability, Entity evolution, Truth ownership, Information preservation)

**Versioning Principles:** Constitutional Amendments increment the revision number of ENTITY-001. The document maintains a revision history. Each amendment preserves backward compatibility: Work Orders that inherited from the previous revision remain valid unless explicitly superseded.

**Prohibition of Silent Reinterpretation:** No architect, Work Order, or implementation may silently reinterpret constitutional concepts. If a concept is ambiguous or insufficient, the correct response is a Constitutional Amendment request, not a reinterpretation. Silent reinterpretation is the primary mechanism of architectural drift and is explicitly prohibited.

**Amendment Record:** Every Constitutional Amendment is recorded in the document's revision history with: the amendment number, the date, the author, the Chief Systems Architect approval, the modified sections, and the rationale. The amendment record is part of the Constitutional Baseline.

---

## 18. Approval Recommendation

### 18.1 Readiness Assessment

**Architecture Completeness:** Complete

**Conceptual Coherence:** High

**Future Compatibility:** High

**Governance Framework:** Established

### 18.2 Identified Gaps

The following gaps were identified across multiple Independent Architecture Reviews and corrected in Revisions 2.1 and 2.2:

**Corrected in Revision 2.1:**
- Section 11.3 incomplete — Architectural Role of Identity Resolution was missing. Corrected.
- Missing glossary definitions — Driver, Event, EntityManager, Work Order, Entity Merge, Entity Split. Corrected.
- Implementation leakage in Risk mitigations. Corrected.
- Constitutional Principles versus Future Architecture Constraints distinction not explained. Corrected.
- Operational State versus Hypothesis Strength relationship not explained. Corrected.
- Governance state inconsistency. Corrected.
- Operational State enumeration unified across Section 7 and Constraint 4. Corrected.
- Partial Match resolution path undefined. Corrected.

**Corrected in Revision 2.2:**
- No constitutional amendment process defined. Corrected (Section 17.3).
- Entity Merge/Split effects on Relationships and Confidence undefined. Corrected (Section 7 definitions extended).
- Event "operational significance" criterion undefined. Corrected (Section 7, Event definition).
- Semantic drift risk not addressed. Corrected (Section 16.7).
- Event storm risk not addressed. Corrected (Section 16.8).
- Confidence floor not established. Corrected (Section 10.6).
- Relationship not elevated to first-class concept. Corrected (Section 7 definition).
- Core concept interrelationships not shown. Corrected (Section 12.5).
- Architectural Invariants not consolidated. Corrected (Section 15.8).
- Constitutional Baseline not defined. Corrected (Section 7).

No additional gaps identified.

### 18.3 Conditions

Chief Systems Architect approval required to establish ENTITY-001 as the immutable Constitutional Baseline. Upon approval, this document becomes immutable and all future Work Orders SHALL inherit from it.

### 18.4 Final Recommendation

**RECOMMENDATION: FINAL CONSTITUTIONAL APPROVAL**

ENTITY-001 Constitutional Architecture Revision 2.2 resolves all findings from multiple Independent Architecture Reviews. The constitutional model is architecturally complete, internally consistent, and governance-ready.

All 13 Constitutional Principles are documented.
All 9 Future Architecture Constraints are documented.
All 12 Architectural Invariants are established.
Intelligence Philosophy is complete.
All fundamental concepts are defined.
All architectural decisions are documented.
All risks are identified with constitutional mitigations.
Constitutional Amendment Process is established.
Future extensibility is preserved.

**Next Step:** Chief Systems Architect approval to establish ENTITY-001 Revision 2.2 as the immutable Constitutional Baseline. Upon approval, implementation of all future Work Orders may begin.

## 19. Programmer Handoff / Execution Contract

### 19.1 Purpose

This section exists solely to establish the execution contract for software engineers working on TACTICAL CORE after reading ENTITY-001.

This section does **not** redefine, extend, or modify any constitutional concept.

ENTITY-001 defines **WHAT the Intelligence Core is**.

Work Orders define **WHAT specific capability is being implemented and HOW it is realized**.

The programmer SHALL treat ENTITY-001 as the architectural authority for all Intelligence Core work.

---

### 19.2 Mandatory Reading Order

Before implementing any Work Order, the programmer SHALL read and understand:

1. ENTITY-001 — Constitutional Architecture
2. The specific Work Order
3. The current repository state
4. Any predecessor Work Orders referenced by the current Work Order
5. Any Independent Architecture Review findings applicable to the current Work Order

The programmer SHALL NOT begin implementation based only on the Work Order title, task description, or previous chat context.

The current repository is the implementation reality.

The Work Order is the authorized change boundary.

ENTITY-001 is the constitutional authority.

---

### 19.3 Authority Hierarchy

When documents or instructions appear to conflict, the following order SHALL apply:

1. **Constitutional Baseline — ENTITY-001**
2. **Approved Architecture Documents**
3. **Approved Work Order**
4. **Independent Architecture Review**
5. **Implementation Notes**
6. **Programmer assumptions**

A lower-level artifact SHALL NEVER override a higher-level architectural rule.

If the programmer identifies a conflict with ENTITY-001, implementation SHALL STOP and the conflict SHALL be reported before code is changed.

---

### 19.4 Work Order Is a Strict Change Contract

A Work Order is not a general improvement request.

The programmer SHALL:

* modify only files explicitly authorized by the Work Order;
* implement only capabilities explicitly authorized by the Work Order;
* avoid unrelated refactoring;
* avoid opportunistic cleanup;
* avoid architectural redesign;
* avoid introducing new dependencies unless explicitly authorized;
* avoid modifying Protected Files unless explicitly authorized;
* preserve all previously approved constitutional behavior.

Anything outside the Work Order perimeter is considered unauthorized scope expansion.

---

### 19.5 Architecture Before Code

The programmer SHALL NOT invent architectural behavior during implementation.

If a required behavior is not defined by:

* ENTITY-001;
* an approved architecture document; or
* the current Work Order,

the programmer SHALL NOT silently choose an architecture.

Instead, the programmer SHALL report:

**ARCHITECTURE GAP — IMPLEMENTATION BLOCKED**

and identify:

1. the missing architectural decision;
2. the affected component;
3. the proposed options;
4. the consequences of each option.

Implementation resumes only after architectural direction is provided.

---

### 19.6 Evidence Is Mandatory

A claim that code works is not evidence.

The following are NOT accepted as verification evidence:

* “implemented”;
* “fixed”;
* “all tests pass”;
* “45/45 passed”;
* screenshots without reproducible commands;
* programmer-written claims without executable artifacts;
* claims-only ZIP packages.

A Work Order delivery SHALL contain executable evidence appropriate to its scope.

Evidence SHOULD include:

* modified source files;
* modified test files;
* exact commands executed;
* actual test output;
* relevant logs;
* runtime verification where required;
* implementation notes explaining architectural compliance.

---

### 19.7 Test Failure Classification

Every test failure SHALL be classified before any repair is made.

Permitted classifications:

* **PRODUCTION DEFECT** — production behavior violates the architecture or Work Order.
* **TEST DEFECT** — test logic, fixture, assertion, async handling, or test infrastructure is incorrect.
* **ENVIRONMENT DEFECT** — required dependency, runtime, service, or platform is unavailable.
* **ARCHITECTURE GAP** — required behavior is not sufficiently defined.
* **PROCESS DEFECT** — delivery or evidence is incomplete.

The programmer SHALL NOT modify production code merely to make a defective test pass.

The programmer SHALL NOT modify tests merely to hide a production defect.

---

### 19.8 Native Verification Is Authoritative

When a Work Order requires pytest or another executable verification command, the actual executed result is authoritative.

Programmer-reported test counts SHALL NOT supersede independent execution.

Example:

```text
Programmer claim: 35/35 passed
Independent execution: 11 passed, 1 failed
```

The authoritative result is:

```text
11 passed, 1 failed
```

The programmer SHALL treat independent verification as the final source of truth.

---

### 19.9 No Claims-Only Completion

A test-only Work Order SHALL deliver the actual test files.

A production Work Order SHALL deliver the actual modified production files.

An integration Work Order SHALL deliver the executable integration artifacts required by its scope.

`MODIFIED_FILES.txt`, `TEST_RESULTS.txt`, and `IMPLEMENTATION_NOTES.md` alone SHALL NOT constitute an implementation package unless the Work Order explicitly defines a documentation-only change.

---

### 19.10 Preserve Closed Findings

A previously closed defect SHALL NOT be reopened or reintroduced without explicit evidence.

Before modifying a component previously closed by an Independent Architecture Review, the programmer SHALL verify:

1. why the defect was originally opened;
2. what change closed it;
3. what tests or runtime evidence closed it;
4. whether the current Work Order actually requires touching that area.

Closed constitutional behavior is regression-sensitive.

---

### 19.11 Protected Files

Protected Files are outside normal programmer authority.

A Protected File SHALL NOT be:

* rewritten;
* reformatted;
* refactored;
* regenerated;
* deleted;
* modified indirectly,

unless the current Work Order explicitly authorizes the change.

If a required implementation appears to require modification of a Protected File, the programmer SHALL stop and report:

**PROTECTED FILE CONFLICT — IMPLEMENTATION BLOCKED**

---

### 19.12 Minimal Change Principle

The preferred implementation is the smallest change that:

1. satisfies the Work Order;
2. conforms to ENTITY-001;
3. preserves existing behavior;
4. passes the required verification;
5. introduces no unnecessary architectural surface.

The programmer SHALL NOT expand a Work Order merely because an adjacent improvement appears desirable.

---

### 19.13 Required Delivery Package

Unless the Work Order explicitly states otherwise, the programmer SHALL deliver:

```text
WO-XXX_IMPLEMENTATION/
├── MODIFIED_FILES.txt
├── TEST_RESULTS.txt
├── IMPLEMENTATION_NOTES.md
├── <actual modified source files>
├── <actual modified test files>
└── <required executable verification artifacts>
```

`MODIFIED_FILES.txt` SHALL list every changed file.

`TEST_RESULTS.txt` SHALL contain the exact commands executed and their actual output.

`IMPLEMENTATION_NOTES.md` SHALL explain:

* what was changed;
* why it was changed;
* which Work Order requirement it satisfies;
* which ENTITY-001 principles/constraints/invariants it relies upon;
* what was intentionally not changed;
* any remaining environment or dependency limitations.

---

### 19.14 STOP Conditions

The programmer SHALL STOP implementation and request architectural clarification when any of the following occurs:

* the Work Order conflicts with ENTITY-001;
* a constitutional concept is ambiguous;
* implementation requires redefining a constitutional concept;
* a Protected File must be changed;
* required behavior is not architecturally specified;
* a dependency changes the architectural behavior;
* a test failure cannot be confidently classified;
* the requested behavior requires unauthorized scope expansion.

The programmer SHALL NOT resolve these situations through assumption.

---

### 19.15 New Chat Initialization

When starting a new implementation chat, the programmer SHALL assume:

> This is a continuation of TACTICAL CORE, not a new project.

The programmer SHALL first establish:

* current repository revision;
* current Work Order;
* predecessor Work Orders;
* currently CLOSED findings;
* currently OPEN findings;
* Protected Files;
* applicable architecture documents;
* required verification commands.

The programmer SHALL NOT assume that previous chat memory is authoritative.

The repository, approved architecture documents, and current Work Order are authoritative.

---

### 19.16 Programmer Completion Statement

At the end of implementation, the programmer SHALL provide a concise completion statement containing:

```text
WORK ORDER: WO-XXX
STATUS: IMPLEMENTED / BLOCKED / REQUIRES ARCHITECTURE

AUTHORIZED FILES:
- ...

ACTUAL CHANGED FILES:
- ...

PRODUCTION CHANGES:
- YES / NO

TESTS EXECUTED:
- exact command

RESULT:
- exact result

ARCHITECTURAL COMPLIANCE:
- ENTITY-001 principles/constraints/invariants satisfied

REMAINING FINDINGS:
- NONE / ...

SCOPE EXPANSION:
- NONE / ...

STOP:
- YES
```

The completion statement is a delivery summary only. It SHALL NOT be treated as evidence without the underlying executable artifacts and actual verification output.

---

### 19.17 Final Rule

The programmer SHALL remember:

**Do not invent architecture.
Do not expand scope.
Do not trust claims over evidence.
Do not modify protected files.
Do not repair tests by corrupting production behavior.
Do not silently reinterpret ENTITY-001.
When architecture is missing, STOP.
When evidence is missing, the Work Order is not verified.**

ENTITY-001 defines the constitutional boundary.

The Work Order defines the authorized change.

The repository defines the current implementation state.

Executable verification defines whether the implementation actually works.

---

*End of Programmer Handoff / Execution Contract*

---

*End of ENTITY-001 Constitutional Architecture — Revision 2.2*
