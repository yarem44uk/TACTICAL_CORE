# Evidence Generator Usage

## Reproducible Command Sequence

```bash
# Clone the repository
git clone <repository-url>
cd TACTICAL_CORE

# Install dependencies
cd backend
pip install -e .

# Generate evidence
cd ..
python scripts/generate_evidence.py
```

## Output

The script generates:

- `artifacts/logs/import_core.log` - Core import test output
- `artifacts/logs/pytest_collect.log` - Test discovery output
- `artifacts/logs/e2e.log` - Integration test output
- `docs/SPRINT_5_0_EVIDENCE.md` - Complete evidence document

## Evidence Document Structure

Each test section contains:

- Executed command
- Working directory
- Timestamp
- stdout
- stderr
- exit code

## CI Integration

The evidence is automatically uploaded as GitHub Actions artifacts
associated with commit SHA and workflow run ID.