from __future__ import annotations

import sqlite3
from .schema import SCHEMA_SQL


def apply_migrations(db_path: str) -> None:
    """Apply database schema migrations."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
