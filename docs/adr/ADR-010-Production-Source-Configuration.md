# ADR-010: Production Source Configuration Catalog

**Date:** 2026-08-25
**Status:** Accepted
**Deciders:** Chief Systems Architect (pending review)

---

## Context

TACTICAL CORE defines a complete source-configuration contract but ships no
production implementation of it:

- `ISourceConfigProvider` (ABC) — `backend/app/event_sources/config/provider.py`
- `SourceDefinition` — `backend/app/event_sources/config/source_definition.py`
- `AdapterFactory` — `backend/app/event_sources/config/adapter_factory.py`
- `ProductionSourceRegistrar` — `backend/app/event_sources/source_registration.py`
- Five production adapters: `atak`, `mqtt`, `signal`, `radio`, `telegram`

Each adapter ships a static registration helper (`register_<name>_adapter` /
`build_registered_factory`) under
`backend/app/event_sources/adapters/<name>_adapter_registration.py`.

The production entrypoint (`backend/main.py`) documents a real gap:

```text
SOURCE_CONFIGURATION_GAP = True
_production_source_provider() -> None
_production_adapter_factory() -> AdapterFactory()   # empty
```

Consequently the production process starts with **zero registered sources** and
has **no mechanism to supply real `SourceDefinition` objects** without editing
production code.

This ADR resolves the WO-035 architecture gate:

> What is the canonical production source of `SourceDefinition` objects, and how
> are they loaded into `ISourceConfigProvider`, so that real source adapters can
> be configured without weakening existing production invariants?

This is an architecture-decision record only. It authorizes no implementation.

---

## Problem

The production runtime needs real source adapters. Supplying them requires a
concrete `ISourceConfigProvider` and a production `AdapterFactory` with the
desired adapter types registered. The repository currently provides neither.

The design must:

1. supply multiple `SourceDefinition` objects;
2. carry arbitrary per-adapter `config` dictionaries;
3. preserve `credentials_ref` as secrets-by-reference (never inline);
4. preserve the fail-closed durable-delivery invariant
   (`require_durable_delivery=True`);
5. respect ADR-005 (modular, type-safe configuration).

---

## Decision Drivers

- **Evidence strength** — the chosen mechanism must already be established by
  repository structure, not invented.
- **Type safety** — ADR-005 explicitly rejects mechanisms that lose type safety.
- **Multi-source representation** — must cleanly express a list of sources, each
  with its own `config` dict.
- **Secrets-by-reference** — `credentials_ref` is a reference, not inline value.
- **No coupling** to the durable event database or to new deployment infra.
- **Fail-closed** behavior preserved.

---

## Options Considered

### Option A — Environment / pydantic-settings

Settings loaded from environment / `.env` via `BaseSettings`
(`backend/app/config/settings.py`).

- **ADR-005 compatibility:** LOW. ADR-005 explicitly *rejected*
  "Environment Variables Only" as a configuration mechanism, citing *No structure*.
- **Multiple sources:** UNKNOWN — no repo precedent for a list-of-objects setting.
- **Arbitrary adapter config:** POOR — nested `config` dicts per source do not map
  to flat env vars without a lossy encoding scheme.
- **Secrets:** supported via env; but `credentials_ref` (a *reference*) is the
  required model, and env var *values* are not references.
- **Validation:** pydantic validates flat scalars only.
- **Verdict:** unsuitable as the *catalog* mechanism; contradicts ADR-005's
  structural rejection. Remains valid for simple scalar runtime settings.

### Option B — Static Python catalog module (SELECTED)

A Python module under the ADR-005 modular-configuration layout that constructs
`SourceDefinition` objects directly.

- **ADR-005 compatibility:** HIGH — this *is* the ADR-005 modular pattern
  (domain-specific config module, type-safe Python).
- **Multiple sources:** YES — a Python list of `SourceDefinition`.
- **Arbitrary adapter config:** YES — each `SourceDefinition.config` is a native
  Python `dict`, matching exactly how every adapter reads it
  (`definition.config.get("topics")`, `"channel"`, `"team"`, `"chat"`, etc.).
- **Secrets:** preserved — `credentials_ref` remains a string reference resolved
  at runtime against env/`.env`; no inline secrets.
- **Validation:** `SourceDefinition.__post_init__` and adapter construction
  validate at import/registration time.
- **Matches existing evidence:** the five `build_registered_factory()` helpers are
  already static Python registration modules — this is the established pattern.

### Option C — File-based catalog (YAML/JSON/TOML)

- **ADR-005 compatibility:** LOW — ADR-005 explicitly *rejected* "YAML/JSON Config"
  citing *Loses type safety*.
- **Evidence:** none — no loader, no format, no deployment model exists.
- **Verdict:** rejected by ADR-005; no repository evidence overrides that.

### Option D — Database-backed catalog

- **Evidence:** none — no source-config schema in the database; would require
  schema redesign (forbidden) and couples source config to the durable event DB.
- **Verdict:** rejected — highest coupling/migration burden, no evidence.

---

## Decision

**SELECTED OPTION: B — Static Python catalog module, implemented as an ADR-005
modular configuration module.**

The canonical production source of `SourceDefinition` objects is a versioned,
type-safe Python module that constructs `SourceDefinition` instances directly and
supplies them through a concrete `ISourceConfigProvider` implementation.

The decision is grounded in repository evidence:

1. **ADR-005 established modular, type-safe configuration** — its decision table
   lists per-domain config modules (`signal.py`, `radio.py`, `mqtt.py`, ...).
   A source catalog is the natural continuation of that pattern, not a departure.
2. **Every adapter already reads its config as a native Python dict** from
   `definition.config` (`topics`, `channel`, `team`, `chat`, `client_id`, ...).
   A Python module expresses these natively and type-safely.
3. **The five `build_registered_factory()` helpers are already static Python
   registration modules** — the repository's proven registration idiom.
4. **No deployment model exists** (verified: no Docker/systemd/service/deploy
   files), so "change source config without redeploy" is *not* an established
   requirement. A config change via the catalog module is a normal code release.

**Trade-off accepted:** changing source configuration requires a code change and
redeploy. This is acceptable because (a) there is no runtime-config-reload
requirement in the repository, and (b) it preserves ADR-005 type safety. If a
deployment model later introduces a hot-reload requirement, a follow-up ADR may
revisit.

---

## Source Catalog Model

A single, authoritative, versioned module, e.g.:

```text
backend/app/config/sources.py
```

following the ADR-005 modular-configuration layout (`app/config/`). It exports a
function returning the ordered catalog of enabled `SourceDefinition` objects:

```python
def production_source_catalog() -> list[SourceDefinition]:
    return [
        SourceDefinition(
            name="mqtt-primary",
            adapter_type="mqtt",
            enabled=True,
            config={"topics": [...], "client_id": "..."},
            credentials_ref="mqtt.primary.credentials",
        ),
        # ...
    ]
```

The catalog is the single source of truth for which sources a production
deployment runs. It contains **no** business/event-pipeline logic.

---

## SourceDefinition Representation

Multiple sources are a `list[SourceDefinition]`. Each element:

| Field | Meaning | Source |
| --- | --- | --- |
| `name` | unique, non-empty identifier | catalog |
| `adapter_type` | one of the five known adapter type strings | catalog |
| `enabled` | whether the runtime should start it | catalog |
| `config` | free-form adapter-specific dict, opaque to config layer | catalog |
| `credentials_ref` | string reference to a credential store entry | catalog (reference only) |

Representation is identical to the existing `SourceDefinition` contract; no new
schema is introduced.

---

## Credential Reference Model

`credentials_ref` remains a **reference**, never an inline secret
(`SourceDefinition.__post_init__` enforces it is a string). Resolution follows the
repository's existing secrets pattern — environment variables / `.env` (no vault,
no external secret manager exists; none is invented by this ADR). The concrete
provider resolves `credentials_ref` against env/`.env` at load time and does not
embed resolved values back into the catalog.

---

## Adapter Registration Model

The production `AdapterFactory` obtains the five known adapter types through the
**existing static registration helpers**:

```python
from app.event_sources.adapters.mqtt_adapter_registration import register_mqtt_adapter
# ... register_atak_adapter, register_signal_adapter, register_radio_adapter,
#     register_telegram_adapter
```

This is **explicit/static** registration, matching the repository's established
`build_registered_factory()` idiom. No plugin-discovery, no dynamic module
loading, no service registry. `AdapterFactory.register_type` already rejects
duplicate registration deterministically.

---

## Validation Rules

Validation reuses the existing contract, which is already present and correct:

- `SourceDefinition.__post_init__` validates `name`, `adapter_type`,
  `credentials_ref` type.
- `AdapterFactory.create` re-validates the definition and raises
  `AdapterTypeError` for unknown/duplicate adapter types.
- `SourceConfigError` hierarchy already distinguishes `SourceDefinitionError`,
  `AdapterTypeError`, `SourceNotFoundError`, `DuplicateSourceError`.

No new validation framework is introduced.

---

## Startup / Fail-Closed Semantics

The ADR fixes the following startup semantics. The durable-delivery invariant
(`require_durable_delivery=True`) is **never** weakened.

| Condition | Behavior |
| --- | --- |
| Missing catalog module | FAIL CLOSED — provider cannot load; process refuses to start |
| Empty catalog | START with zero sources (matches current `ZERO_SOURCE_START=PASS`) |
| Malformed catalog (invalid `SourceDefinition`) | FAIL CLOSED — `SourceDefinitionError` at load |
| Unknown adapter type | FAIL CLOSED — `AdapterTypeError` at registration |
| Disabled source (`enabled=False`) | SKIPPED — registrar filters it out before registration |
| Missing adapter configuration | FAIL CLOSED — adapter construction raises |
| Missing `credentials_ref` | FAIL CLOSED — provider raises on unresolved reference |
| Invalid credentials reference | FAIL CLOSED — provider raises on unresolved reference |
| Duplicate source name | FAIL CLOSED — `DuplicateSourceError` at load |
| Duplicate registration | FAIL CLOSED — `AdapterTypeError` at factory registration |
| One source fails registration | FAIL CLOSED — exception propagates; process refuses to start with partial state |
| Multiple sources, one invalid | FAIL CLOSED — whole load/registration fails atomically |
| Adapter factory failure | FAIL CLOSED — exception propagates |

The established error hierarchy already defines most of these; the ADR makes them
explicit architecture-level startup semantics rather than "implementation
details."

---

## Zero-Source Semantics

- `no catalog` → **FAIL CLOSED** (provider cannot be constructed).
- `empty catalog` → **start with zero sources** (explicit, deliberate; matches the
  current verified `ZERO_SOURCE_START = PASS`).
- `invalid catalog` → **FAIL CLOSED**.
- `disabled sources only` → **start with zero active sources** (empty after
  filter).
- `partial registration failure` → **FAIL CLOSED** (no silent partial startup).

The current zero-source capability remains valid as a deliberate "no sources
configured" state, but a missing/unreadable catalog is never silently treated as
empty.

---

## Security Considerations

- `credentials_ref` is reference-only; **no plaintext credentials** are embedded
  in the catalog.
- Resolution uses the existing env/`.env` secrets pattern. No new secret
  manager, vault, or external platform is introduced.
- The selected mechanism adds **no** network, exec, shell, or dynamic-code
  surface beyond normal module import.
- Adapter registration remains explicit (whitelist of five known types); no
  arbitrary dynamic adapter loading is enabled.

---

## Compatibility with ADR-005

ADR-005 established **modular, type-safe configuration** as the canonical pattern
and rejected both "Environment Variables Only" (no structure) and "YAML/JSON"
(loss of type safety).

Option B is **the direct continuation** of ADR-005: it adds one more
domain-specific, type-safe Python configuration module (`app/config/sources.py`).
It does **not** overturn ADR-005 and does **not** require a carve-out. It is the
option most consistent with ADR-005's stated motivation (type safety,
modularity, per-domain validation).

---

## Consequences

Positive:

- Real production source adapters become configurable without weakening any
  invariant.
- Matches the existing `build_registered_factory` / modular-config idiom.
- Type-safe, validated at import/registration time.
- No new dependencies, schemas, deployment infra, or secret platform.
- Durable delivery stays fail-closed.

Negative:

- Source configuration is code: changing sources requires a code release (accepted
  — no hot-reload requirement exists).

Neutral:

- The concrete `ISourceConfigProvider` and catalog wiring remain for the
  implementation WO (WO-036) to deliver.

---

## Non-Goals

- No YAML/JSON/TOML catalog (rejected by ADR-005).
- No database-backed source configuration (schema redesign, coupling).
- No env-var-encoded multi-source catalog (contradicts ADR-005).
- No secret manager / vault / external credentials platform.
- No dynamic plugin discovery / service registry / message bus.
- No deployment infrastructure (Docker/systemd/Kubernetes).
- No redesign of `ISourceConfigProvider`, `AdapterFactory`,
  `ProductionSourceRegistrar`, adapters, event pipeline, durable delivery,
  projection/checkpoint, or repositories.

---

## Implementation Boundary

The implementation WO (WO-036) is limited to:

- a concrete `ISourceConfigProvider` (e.g. a static-catalog provider resolving
  `credentials_ref` against env/`.env`);
- a production `AdapterFactory` built via the existing static
  `register_<name>_adapter` helpers;
- wiring the provider + factory into `_production_source_provider()` /
  `_production_adapter_factory()` in `backend/main.py` (or equivalent
  entrypoint-local injection);
- focused tests.

It MUST NOT modify: `EventPipeline`, `DurableCanonicalEvent`,
`DurableDeliveryDispatcher`, outbox/retry/dead-letter, projection/checkpoint,
`EntityRepository`, `RelationRepository`, WO-031 reconstruction, WO-033/034
entrypoint behavior/tests, adapter internals, database schema, or deployment
infrastructure.

---

## Future Work

- Revisit if a deployment model introduces a hot-reload / config-without-redeploy
  requirement.
- Consider a per-adapter strict config schema (Pydantic model per adapter) if
  validation beyond free-form dicts is required.

---

## Status

**Status:** Accepted — awaiting review/approval per repository governance. This
record does not authorize implementation.
