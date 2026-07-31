# ADR-005: Modular Configuration

**Date:** TASK-Sprint-004  
**Status:** Accepted  
**Deciders:** Architecture Team

---

## Context

The original `config.py` file contained 50+ settings with no logical grouping. This made the file difficult to maintain and understand.

---

## Decision

Split configuration into domain-specific modules within `app/config/` package:

| Module | Contents |
|--------|----------|
| settings.py | Main app settings |
| database.py | Database connection |
| storage.py | File storage paths |
| security.py | CORS, authentication |
| logging.py | Log levels, formats |
| pipeline.py | Pipeline stages |
| plugins.py | Plugin system |
| radio.py | Radio module |
| signal.py | Signal module |
| ai.py | AI module |
| media.py | Media/Camera module |
| mqtt.py | MQTT broker |
| websocket.py | WebSocket server |
| scheduler.py | Background jobs |

---

## Motivation

- **Organization:** Related settings together
- **Maintainability:** Changes affect smaller files
- **Type Safety:** Each module can have its own types
- **Testing:** Easier to test specific configs
- **Documentation:** Clear what belongs where

---

## Alternatives Considered

1. **Single Config File:** Rejected - Became too large
2. **YAML/JSON Config:** Rejected - Loses type safety
3. **Environment Variables Only:** Rejected - No structure

---

## Trade-offs

| Positive | Negative |
|----------|----------|
| Organized by domain | More files to navigate |
| Easier to find settings | Import complexity |
| Type safety per module | Potential code duplication |
| Clear dependencies | Configuration inheritance complexity |

---

## Future Consequences

- **Positive:** Easy to add module-specific config
- **Positive:** Configuration validation per module
- **Neutral:** Need to coordinate shared settings
- **Need:** Config inheritance strategy

---

## Implementation Notes

- Settings class uses Pydantic for validation
- Other modules use dataclasses for simplicity
- Shared settings remain in settings.py
- Each module validates its own settings
