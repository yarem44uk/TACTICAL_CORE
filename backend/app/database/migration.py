"""
Database Migration Module.

This module provides Alembic integration and migration utilities.
Supports both development auto-migration and production Alembic migrations.

Architecture Rule: All module communication via Event Service.
No direct module-to-module coupling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Tuple

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MigrationManager:
    """
    Database migration manager using Alembic.

    Provides both automatic migration for development and
    manual control for production deployments.

    Attributes:
        alembic_cfg: Alembic configuration object.
        migrations_path: Path to migrations directory.

    Usage:
        >>> manager = MigrationManager(database_url="sqlite:///./db.sqlite")
        >>> manager.upgrade()
    """

    def __init__(
        self,
        database_url: str,
        migrations_path: Optional[str] = None,
        alembic_ini_path: Optional[str] = None,
    ) -> None:
        """
        Initialize the migration manager.

        Args:
            database_url: SQLAlchemy database URL.
            migrations_path: Path to Alembic migrations directory.
            alembic_ini_path: Path to alembic.ini configuration file.
        """
        self.database_url = database_url
        self.migrations_path = migrations_path or self._default_migrations_path()
        self.alembic_ini_path = alembic_ini_path or self._default_alembic_ini_path()

        self._alembic_config: Optional[AlembicConfig] = None

    @staticmethod
    def _default_migrations_path() -> str:
        """
        Get the default migrations path.

        Returns:
            Path to migrations directory.
        """
        return str(Path(__file__).parent.parent.parent / "migrations")

    @staticmethod
    def _default_alembic_ini_path() -> str:
        """
        Get the default alembic.ini path.

        Returns:
            Path to alembic.ini file.
        """
        return str(Path(__file__).parent.parent.parent / "alembic.ini")

    def _get_alembic_config(self) -> AlembicConfig:
        """
        Get or create Alembic configuration.

        Returns:
            Configured AlembicConfig instance.
        """
        if self._alembic_config is None:
            if not os.path.exists(self.alembic_ini_path):
                logger.warning(
                    f"alembic.ini not found at {self.alembic_ini_path}. "
                    "Using defaults."
                )

            self._alembic_config = AlembicConfig(
                config_file=self.alembic_ini_path if os.path.exists(self.alembic_ini_path) else None,
            )
            self._alembic_config.set_main_option(
                "sqlalchemy.url",
                self.database_url
            )
            self._alembic_config.set_main_option(
                "script_location",
                self.migrations_path
            )

        return self._alembic_config

    def create_migration(
        self,
        message: str,
        autogenerate: bool = True,
    ) -> Optional[str]:
        """
        Create a new migration.

        Args:
            message: Migration description.
            autogenerate: Whether to auto-detect model changes.

        Returns:
            Path to created migration file, or None if failed.
        """
        logger.info(f"Creating migration: {message}")

        try:
            cfg = self._get_alembic_config()
            revision = command.revision(
                cfg,
                message=message,
                autogenerate=autogenerate,
                branch_label=None,
                version_path=None,
                rev_id=None,
            )
            logger.info(f"Migration created: {revision}")
            return revision
        except Exception as e:
            logger.error(f"Failed to create migration: {e}")
            return None

    def upgrade(self, revision: str = "head") -> None:
        """
        Apply migrations up to specified revision.

        Args:
            revision: Target revision (default: "head").
        """
        logger.info(f"Upgrading database to: {revision}")

        try:
            cfg = self._get_alembic_config()
            command.upgrade(cfg, revision)
            logger.info("Database upgrade completed")
        except Exception as e:
            logger.error(f"Database upgrade failed: {e}")
            raise

    def downgrade(self, revision: str = "-1") -> None:
        """
        Revert migrations down to specified revision.

        Args:
            revision: Target revision (default: "-1" for one step back).
        """
        logger.info(f"Downgrading database to: {revision}")

        try:
            cfg = self._get_alembic_config()
            command.downgrade(cfg, revision)
            logger.info("Database downgrade completed")
        except Exception as e:
            logger.error(f"Database downgrade failed: {e}")
            raise

    def current_revision(self) -> Optional[str]:
        """
        Get the current database revision.

        Returns:
            Current revision string, or None if not migrated.
        """
        try:
            cfg = self._get_alembic_config()
            command.current(cfg)
            return self._get_current_revision_from_db()
        except Exception as e:
            logger.error(f"Failed to get current revision: {e}")
            return None

    def _get_current_revision_from_db(self) -> Optional[str]:
        """
        Get current revision directly from database.

        Returns:
            Current revision string, or None.
        """
        from app.database.session import get_session_manager

        try:
            manager = get_session_manager()
            with manager.session(commit=False) as session:
                result = session.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                row = result.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def history(self) -> List[Tuple[str, str, str]]:
        """
        Get migration history.

        Returns:
            List of tuples: (revision, parent, description)
        """
        try:
            cfg = self._get_alembic_config()
            script = ScriptDirectory.from_config(cfg)

            history = []
            for revision in script.walk_revisions():
                history.append((
                    revision.revision,
                    revision.down_revision,
                    revision.description,
                ))

            return history
        except Exception as e:
            logger.error(f"Failed to get migration history: {e}")
            return []

    def branches(self) -> List[str]:
        """
        Get all migration branches.

        Returns:
            List of branch revision IDs.
        """
        try:
            cfg = self._get_alembic_config()
            script = ScriptDirectory.from_config(cfg)
            return list(script.get_heads())
        except Exception as e:
            logger.error(f"Failed to get branches: {e}")
            return []

    def heads(self) -> List[str]:
        """
        Get all migration heads.

        Returns:
            List of head revision IDs.
        """
        try:
            cfg = self._get_alembic_config()
            script = ScriptDirectory.from_config(cfg)
            return list(script.get_heads())
        except Exception as e:
            logger.error(f"Failed to get heads: {e}")
            return []

    def stamp(self, revision: str) -> None:
        """
        Stamp the database with a specific revision.

        Does not run migrations, just marks the version.

        Args:
            revision: Revision to stamp (e.g., "head", "base").
        """
        logger.info(f"Stamping database at: {revision}")

        try:
            cfg = self._get_alembic_config()
            command.stamp(cfg, revision)
            logger.info("Database stamped successfully")
        except Exception as e:
            logger.error(f"Failed to stamp database: {e}")
            raise

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate that migration history is consistent.

        Returns:
            Tuple of (is_valid, list of errors).
        """
        errors = []

        try:
            cfg = self._get_alembic_config()
            script = ScriptDirectory.from_config(cfg)

            heads = list(script.get_heads())
            if len(heads) > 1:
                errors.append(f"Multiple heads detected: {heads}")

            for rev in script.walk_revisions():
                if rev.down_revision is None:
                    continue
                if rev.down_revision not in [r.revision for r in script.walk_revisions()]:
                    errors.append(
                        f"Disconnected revision: {rev.revision} "
                        f"(parent {rev.down_revision} not found)"
                    )

            return len(errors) == 0, errors
        except Exception as e:
            logger.error(f"Failed to validate migrations: {e}")
            errors.append(str(e))
            return False, errors


def init_alembic(
    database_url: str,
    migrations_path: Optional[str] = None,
) -> None:
    """
    Initialize Alembic configuration.

    Creates alembic.ini and env.py if they do not exist.

    Args:
        database_url: SQLAlchemy database URL.
        migrations_path: Path to migrations directory.
    """
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    migrations_dir = Path(migrations_path) if migrations_path else project_root / "migrations"

    migrations_dir.mkdir(parents=True, exist_ok=True)

    alembic_ini = project_root / "alembic.ini"
    if not alembic_ini.exists():
        alembic_ini_content = f"""# Alembic Configuration

[alembic]
script_location = migrations
sqlalchemy.url = {database_url}

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
        alembic_ini.write_text(alembic_ini_content)
        logger.info(f"Created {alembic_ini}")

    env_py = migrations_dir / "env.py"
    if not env_py.exists():
        env_py_content = '''"""Alembic Environment Configuration."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.database.base import Base
from app.models.event import Event

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''
        env_py.write_text(env_py_content)
        logger.info(f"Created {env_py}")

    script_mako = migrations_dir / "script.py.mako"
    if not script_mako.exists():
        script_mako_content = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''
        script_mako.write_text(script_mako_content)
        logger.info(f"Created {script_mako}")

    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    (versions_dir / ".gitkeep").touch()

    logger.info("Alembic initialized successfully")


def run_migrations(
    database_url: str,
    revision: str = "head",
    migrations_path: Optional[str] = None,
) -> None:
    """
    Run database migrations.

    Args:
        database_url: SQLAlchemy database URL.
        revision: Target revision (default: "head").
        migrations_path: Path to migrations directory.
    """
    manager = MigrationManager(
        database_url=database_url,
        migrations_path=migrations_path,
    )
    manager.upgrade(revision)


def ensure_database_schema(
    database_url: str,
    create_tables: bool = True,
) -> None:
    """
    Ensure database schema exists.

    For development: creates tables directly.
    For production: runs migrations.

    Args:
        database_url: SQLAlchemy database URL.
        create_tables: Whether to create tables in development.
    """
    from app.database.database import initialize_database

    is_production = os.getenv("ENVIRONMENT") == "production"

    if is_production:
        logger.info("Production mode: using migrations")
        run_migrations(database_url)
    else:
        logger.info("Development mode: auto-creating tables")
        initialize_database(
            database_url=database_url,
            create_tables=create_tables,
        )
