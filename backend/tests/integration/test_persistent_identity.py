"""Persistent Identity Resolution Tests — WO-008-017

Verifies that identity resolution belongs to the repository persistence
contract, not merely to an EntityManager instance. Both InMemory and
SQLAlchemy repositories must support cross-manager identity resolution.

Author: WO-008-017 Implementation
Version: 1.0
"""

import os
import pytest
from uuid import UUID

from app.intelligence.entity import (
    Entity,
    EntityData,
    EntityManager,
    EntityStatus,
    EntityType,
    Priority,
)
from app.intelligence.entity.entity_manager import InMemoryEntityRepository


# ---------------------------------------------------------------------------
# InMemory persistent identity
# ---------------------------------------------------------------------------


class TestInMemoryPersistentIdentity:
    """InMemory repository identity persistence across managers."""

    async def test_cross_manager_same_entity(self):
        """Two managers, same repo → same entity UUID."""
        repo = InMemoryEntityRepository()

        m1 = EntityManager(repository=repo)
        e1, c1 = await m1.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="WO-017-001",
        )
        assert c1 is True

        m2 = EntityManager(repository=repo)
        e2, c2 = await m2.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="WO-017-001",
        )
        assert c2 is False
        assert e1.id == e2.id

    async def test_identity_survives_entity_update(self):
        """Identity mapping persists after entity field update + save."""
        repo = InMemoryEntityRepository()
        m = EntityManager(repository=repo)

        e, _ = await m.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="sig",
            external_id="UPDATE-TEST",
        )
        eid = e.id

        # Update unrelated field
        e.data.callsign = "ALPHA"
        await m.update(e)

        # Identity still resolves
        m2 = EntityManager(repository=repo)
        e2, c2 = await m2.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="sig",
            external_id="UPDATE-TEST",
        )
        assert c2 is False
        assert e2.id == eid

    async def test_multiple_external_ids_same_entity(self):
        """Multiple (source, external_id) pairs can map to same entity."""
        repo = InMemoryEntityRepository()
        m = EntityManager(repository=repo)

        e1, _ = await m.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="A",
        )

        # Add alias manually
        e1.external_ids["signal"] = "B"
        await repo.save(e1)

        # Resolve via alias
        resolved = await repo.resolve_by_identity("signal", "B")
        assert resolved == e1.id

    async def test_cv1_same_manager_dedup(self):
        """Same manager, same identity → no duplicate."""
        repo = InMemoryEntityRepository()
        m = EntityManager(repository=repo)

        e1, c1 = await m.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="x",
            external_id="dedup-01",
        )
        assert c1 is True

        e2, c2 = await m.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="x",
            external_id="dedup-01",
        )
        assert c2 is False
        assert e1.id == e2.id

    async def test_cv2_soft_delete_inmemory(self):
        """CV2: soft delete preserves entity as INACTIVE."""
        repo = InMemoryEntityRepository()
        m = EntityManager(repository=repo)

        e, _ = await m.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="del",
            external_id="soft-del",
        )
        eid = e.id

        await m.delete(eid)
        retrieved = await m.get(eid)
        assert retrieved is not None
        assert retrieved.status == EntityStatus.INACTIVE

    async def test_cv3_initial_unknown(self):
        """CV3: fresh entity starts at UNKNOWN."""
        e = Entity.create(entity_type=EntityType.CONTACT)
        assert e.status == EntityStatus.UNKNOWN

    async def test_cv4_confidence_validated(self):
        """CV4: Entity.create() rejects out-of-range confidence."""
        with pytest.raises(ValueError):
            Entity.create(entity_type=EntityType.CONTACT, confidence=-0.1)

        with pytest.raises(ValueError):
            Entity.create(entity_type=EntityType.CONTACT, confidence=1.1)

        # Valid values work
        e = Entity.create(entity_type=EntityType.CONTACT, confidence=0.5)
        assert e.confidence == 0.5
        e2 = Entity.create(entity_type=EntityType.CONTACT, confidence=0.0)
        assert e2.confidence == 0.0
        e3 = Entity.create(entity_type=EntityType.CONTACT, confidence=1.0)
        assert e3.confidence == 1.0


# ---------------------------------------------------------------------------
# SQLAlchemy persistent identity
# ---------------------------------------------------------------------------


SQLALCHEMY = False
try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.intelligence.entity.entity_manager import SQLAlchemyEntityRepository
    SQLALCHEMY = True
except ImportError:
    pass


@pytest.mark.skipif(not SQLALCHEMY, reason="SQLAlchemy not installed")
class TestSQLAlchemyPersistentIdentity:
    """SQLAlchemy repository identity persistence."""

    @pytest.fixture
    def db_file(self, tmp_path):
        return str(tmp_path / "test_identity.db")

    @pytest.fixture
    def repo(self, db_file):
        engine = create_engine(f"sqlite:///{db_file}")
        Session = sessionmaker(bind=engine)
        session = Session()
        r = SQLAlchemyEntityRepository(session)
        yield r
        session.close()

    async def test_cross_manager_same_entity(self, db_file):
        """Two managers, same repo → same entity UUID."""
        engine = create_engine(f"sqlite:///{db_file}")
        Session = sessionmaker(bind=engine)

        session1 = Session()
        repo1 = SQLAlchemyEntityRepository(session1)
        m1 = EntityManager(repository=repo1)
        e1, c1 = await m1.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="SQL-001",
        )
        assert c1 is True
        session1.close()

        # Fresh session
        session2 = Session()
        repo2 = SQLAlchemyEntityRepository(session2)
        m2 = EntityManager(repository=repo2)
        e2, c2 = await m2.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="radio",
            external_id="SQL-001",
        )
        assert c2 is False
        assert e1.id == e2.id
        session2.close()

    async def test_identity_survives_across_sessions(self, db_file):
        """Identity persists across separate database sessions."""
        engine = create_engine(f"sqlite:///{db_file}")
        Session = sessionmaker(bind=engine)

        s1 = Session()
        r1 = SQLAlchemyEntityRepository(s1)
        m1 = EntityManager(repository=r1)
        e1, _ = await m1.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="sig",
            external_id="ACROSS-001",
        )
        s1.close()

        s2 = Session()
        r2 = SQLAlchemyEntityRepository(s2)
        m2 = EntityManager(repository=r2)
        e2, c2 = await m2.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="sig",
            external_id="ACROSS-001",
        )
        assert c2 is False
        assert e1.id == e2.id
        s2.close()

    async def test_cv2_soft_delete_sqlalchemy(self, db_file):
        """CV2: soft delete preserves entity, retrievable via get()."""
        engine = create_engine(f"sqlite:///{db_file}")
        Session = sessionmaker(bind=engine)

        session = Session()
        repo = SQLAlchemyEntityRepository(session)
        m = EntityManager(repository=repo)

        e, _ = await m.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="del",
            external_id="SQL-SOFT-DEL",
        )
        eid = e.id

        await m.delete(eid)
        retrieved = await m.get(eid)
        assert retrieved is not None
        assert retrieved.status == EntityStatus.INACTIVE
        session.close()

    async def test_identity_survives_update_sqlalchemy(self, db_file):
        """Identity persists after entity update in SQLAlchemy."""
        engine = create_engine(f"sqlite:///{db_file}")
        Session = sessionmaker(bind=engine)

        session = Session()
        repo = SQLAlchemyEntityRepository(session)
        m = EntityManager(repository=repo)

        e, _ = await m.resolve_or_create(
            entity_type=EntityType.CONTACT,
            source="upd",
            external_id="SQL-UPD",
        )
        eid = e.id

        e.data.callsign = "UPDATED"
        await repo.save(e)

        resolved = await repo.resolve_by_identity("upd", "SQL-UPD")
        assert resolved == eid
        session.close()
