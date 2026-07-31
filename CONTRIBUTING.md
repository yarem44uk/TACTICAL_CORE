# Contributing to TACTICAL CORE

Thank you for your interest in contributing!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/TACTICAL_CORE.git
cd TACTICAL_CORE

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install development dependencies
pip install -e "backend/[dev]"

# Run tests
pytest backend/tests/ -v
```

## Coding Standards

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write docstrings for public functions
- Add unit tests for new features
- Ensure all tests pass before submitting PR

## Branch Strategy

- `main` - Stable, production-ready code
- `develop` - Integration branch for features
- `feature/*` - Feature branches
- `fix/*` - Bug fix branches
- `docs/*` - Documentation improvements

## Pull Request Process

1. Update documentation if needed
2. Add tests for new functionality
3. Ensure all tests pass
4. Request review from maintainers
5. Squash commits before merge

## Work Order Process

Work Orders (WOs) follow this lifecycle:

1. **Authorized** - Approved for implementation
2. **In Progress** - Being implemented
3. **Review** - Under independent review
4. **Closed** - Completed and merged

## Questions?

Open an issue for discussion.
