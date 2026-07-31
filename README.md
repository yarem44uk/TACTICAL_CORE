# TACTICAL CORE

**Intelligence Operations Command & Control Platform**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Overview

TACTICAL CORE is a C4ISR software platform for intelligence operations, providing:

- **Multi-source Integration**: Signal, Telegram, MQTT, Radio, ATAK connectors
- **Real-time Event Processing**: EventBus architecture with pub/sub messaging
- **Intelligence Observation**: Immutable observation capture and storage
- **Entity Management**: Identity-first entity resolution with persistent storage
- **Constitutional Architecture**: ENTITY-001 compliant design

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TACTICAL CORE                           │
├─────────────────────────────────────────────────────────────┤
│  Connectors        │  Core          │  Intelligence         │
│  ───────────      │  ─────         │  ────────────         │
│  • Signal        │  • EventBus    │  • Entity             │
│  • Telegram      │  • Events      │  • Identity           │
│  • MQTT          │  • Dispatcher   │  • Relations          │
│  • Radio         │                │  • Observation        │
│  • ATAK          │                │                       │
├─────────────────────────────────────────────────────────────┤
│                    Persistence Layer                      │
│  • SQLite (Intelligence Observations)                      │
│  • InMemory/SQLAlchemy (Entities)                       │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/TACTICAL_CORE.git
cd TACTICAL_CORE

# Install dependencies
pip install -r backend/requirements.txt

# Run tests
pytest backend/tests/ -q

# Start the application (if API server implemented)
python backend/main.py
```

## Project Structure

```
TACTICAL_CORE/
├── backend/                  # Python application
│   ├── app/
│   │   ├── core/           # EventBus, events, dispatcher
│   │   ├── connectors/     # Signal, Telegram, MQTT, Radio, ATAK
│   │   ├── intelligence/   # Entity, Identity, Observation
│   │   ├── observation/    # Observation service
│   │   └── database/      # Database models
│   └── tests/             # Test suites
├── docs/                  # Documentation
│   ├── architecture/     # Entity-001, ADRs
│   ├── governance/        # Project governance
│   └── reviews/          # Review documents
├── plugins/              # Plugin system
└── scripts/             # Utility scripts
```

## Constitutional Compliance

TACTICAL CORE implements **ENTITY-001 Constitutional Architecture**:

| Principle | Description | Status |
|-----------|-------------|--------|
| **CV1** | Identity-First | ✅ Verified |
| **CV2** | Non-Destructive Delete | ✅ Verified |
| **CV3** | Initial Status UNKNOWN | ✅ Verified |
| **CV4** | Confidence First-Class | ✅ Verified |

## Testing

```bash
# Run all tests
pytest backend/tests/ -v

# Run integration tests only
pytest backend/tests/integration/ -v

# Run intelligence tests only
pytest backend/tests/intelligence/ -v
```

## Documentation

- [ENTITY-001 Constitutional Architecture](./docs/architecture/ENTITY-001.md)
- [ADR Documents](./docs/architecture/adr/)
- [API Documentation](./docs/api/)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Authors

**TACTICAL CORE Engineering Team**

---

*Building the future of intelligence operations.*
