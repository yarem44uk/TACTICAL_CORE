# ARCHITECTURE_BLOCKER.md

## Status: OPEN — WO-005G

## Current Blocker

**Issue:** Runtime verification not executed + governance decision required

**Components:**
1. pytest execution required in local Python environment
2. WO-006 files decision required from Chief Systems Architect

---

## Evidence

**Static Analysis:** 20/20 checks passed
**Runtime Verification:** NOT EXECUTED (Pyodide limitation)

**Required Local Execution:**
```bash
cd tactical_core/backend
pip install -r requirements.txt
pytest tests/test_signal_reference_plugin_e2e.py -v
```

**Success Criteria:** 8 PASSED

---

## Previous Work Orders — CLOSED

| WO | Description |
|----|-------------|
| WO-005C | PluginManager RLock, SignalReferencePlugin restore |
| WO-005D | PassThroughStage.order fix |
| WO-005E | ORM Event model created |
| WO-005E-R2 | Duplicate SQLAlchemy indexes fixed |
| WO-005E-R3 | Lock import fixed |
| WO-005E-R7 | PluginManager lifecycle fixes |
| WO-005E-R8 | shutdown()/stop_plugin() fixes |

---

## Next Steps

1. **WO-005G:** Execute pytest locally, confirm 8 PASSED
2. **Chief Systems Architect:** Decision on WO-006 files
3. **If 8 PASSED + WO-006 resolved:** Foundation VERIFIED
4. **WO-006:** Platform Bootstrap opens
