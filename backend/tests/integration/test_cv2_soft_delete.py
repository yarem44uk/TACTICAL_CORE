"""WO-008-018: SQLAlchemy Soft-Delete / Persistent Identity Integrity Tests

Tests that verify:
- InMemory CV2: create -> delete -> get returns INACTIVE entity
- SQLAlchemy CV2: create -> delete -> get returns INACTIVE entity
- SQLAlchemy identity after delete: resolve_by_identity returns same UUID
- SQLAlchemy resolve_or_create after delete: created=False, same entity
- Cross-manager SQLAlchemy: survives manager recreation after delete
- No duplicate identity creation after delete
"""

import pytest
import asyncio
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.intelligence.entity.entity_manager import (
    EntityManager,
    InMemoryEntityRepository,
    SQLAlchemyEntityRepository,
)
from app.intelligence.entity.types import EntityType, EntityStatus


def make_sql_repo():
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()
    return SQLAlchemyEntityRepository(session)


# ==================== TEST A — InMemory CV2 ====================

@pytest.mark.asyncio
async def test_inmemory_cv2_create_delete_get():
    repo = InMemoryEntityRepository()
    mgr = EntityManager(repo)
    entity, created = await mgr.resolve_or_create(
        source="tak", external_id="T1", entity_type=EntityType.CONTACT
    )
    assert created is True

    await mgr.delete(entity.id)
    retrieved = await mgr.get(entity.id)

    assert retrieved is not None
    assert retrieved.status == EntityStatus.INACTIVE
    assert retrieved.id == entity.id


# ==================== TEST B — SQLAlchemy CV2 ====================

@pytest.mark.asyncio
async def test_sqlalchemy_cv2_create_delete_get():
    repo = make_sql_repo()
    mgr = EntityManager(repo)
    entity, created = await mgr.resolve_or_create(
        source="tak", external_id="T2", entity_type=EntityType.CONTACT
    )
    assert created is True

    await mgr.delete(entity.id)
    retrieved = await mgr.get(entity.id)

    assert retrieved is not None
    assert retrieved.status == EntityStatus.INACTIVE
    assert retrieved.id == entity.id


# ==================== TEST C — InMemory identity after delete ====================

@pytest.mark.asyncio
async def test_inmemory_identity_after_delete():
    repo = InMemoryEntityRepository()
    mgr = EntityManager(repo)
    entity, created = await mgr.resolve_or_create(
        source="tak", external_id="T3", entity_type=EntityType.CONTACT
    )
    await mgr.delete(entity.id)

    resolved_uuid = await repo.resolve_by_identity("tak", "T3")
    assert resolved_uuid is not None
    assert resolved_uuid == entity.id


# ==================== TEST D — SQLAlchemy identity after delete ====================

@pytest.mark.asyncio
async def test_sqlalchemy_identity_after_delete():
    repo = make_sql_repo()
    mgr = EntityManager(repo)
    entity, created = await mgr.resolve_or_create(
        source="tak", external_id="T4", entity_type=EntityType.CONTACT
    )
    await mgr.delete(entity.id)

    resolved_uuid = await repo.resolve_by_identity("tak", "T4")
    assert resolved_uuid is not None
    assert resolved_uuid == entity.id


# ==================== TEST E — resolve_or_create after delete ====================

@pytest.mark.asyncio
async def test_resolve_or_create_after_delete_inmemory():
    repo = InMemoryEntityRepository()
    mgr = EntityManager(repo)
    e1, c1 = await mgr.resolve_or_create(
        source="tak", external_id="T5", entity_type=EntityType.CONTACT
    )
    assert c1 is True
    await mgr.delete(e1.id)

    e2, c2 = await mgr.resolve_or_create(
        source="tak", external_id="T5", entity_type=EntityType.CONTACT
    )
    assert c2 is False
    assert e2.id == e1.id
    assert e2.status == EntityStatus.INACTIVE


@pytest.mark.asyncio
async def test_resolve_or_create_after_delete_sqlalchemy():
    repo = make_sql_repo()
    mgr = EntityManager(repo)
    e1, c1 = await mgr.resolve_or_create(
        source="tak", external_id="T6", entity_type=EntityType.CONTACT
    )
    assert c1 is True
    await mgr.delete(e1.id)

    e2, c2 = await mgr.resolve_or_create(
        source="tak", external_id="T6", entity_type=EntityType.CONTACT
    )
    assert c2 is False
    assert e2.id == e1.id
    assert e2.status == EntityStatus.INACTIVE


# ==================== TEST F — Cross-manager SQLAlchemy ====================

@pytest.mark.asyncio
async def test_cross_manager_sql_after_delete():
    repo = make_sql_repo()

    mgr1 = EntityManager(repo)
    e1, c1 = await mgr1.resolve_or_create(
        source="tak", external_id="T7", entity_type=EntityType.CONTACT
    )
    assert c1 is True

    mgr2 = EntityManager(repo)
    e2, c2 = await mgr2.resolve_or_create(
        source="tak", external_id="T7", entity_type=EntityType.CONTACT
    )
    assert c2 is False
    assert e2.id == e1.id

    mgr3 = EntityManager(repo)
    await mgr3.delete(e1.id)
    e3, c3 = await mgr3.resolve_or_create(
        source="tak", external_id="T7", entity_type=EntityType.CONTACT
    )
    assert c3 is False
    assert e3.id == e1.id
    assert e3.status == EntityStatus.INACTIVE


# ==================== TEST H — DB-level is_deleted assertion ====================
# W18-R1: Verify database-level state directly, not just reconstructed Entity

@pytest.mark.asyncio
async def test_sqlalchemy_db_is_deleted_false_after_delete():
    """Assert that the database row has is_deleted=FALSE after soft delete.
    The previous bug was: JSON status=inactive but is_deleted=TRUE.
    This test prevents regression of that exact failure.
    """
    from sqlalchemy import text

    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SQLAlchemyEntityRepository(session)
    mgr = EntityManager(repo)

    entity, created = await mgr.resolve_or_create(
        source="tak", external_id="DB_T1", entity_type=EntityType.CONTACT
    )
    assert created is True
    await mgr.delete(entity.id)

    # Direct database query — no Entity reconstruction
    row = session.execute(
        text("SELECT is_deleted, entity_data FROM entity_store WHERE entity_id = :id"),
        {"id": str(entity.id)},
    ).fetchone()

    assert row is not None, "Row must still exist after soft delete"
    assert row[0] in (False, 0), f"is_deleted must be FALSE, got {row[0]}"

    # Also verify the JSON payload carries INACTIVE status
    import json
    data = json.loads(row[1])
    assert data.get("status") == "inactive"


# ==================== TEST I — Fresh session persistence ====================
# W18-R2: Verify identity survives a completely new SQLAlchemy Session/Repository

@pytest.mark.asyncio
async def test_sqlalchemy_fresh_session_persistence():
    """Create entity in Session A, delete it, then verify a new Session B
    can still get() and resolve_by_identity() the same entity.
    This proves true persistence, not just same-session caching.
    """
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)

    # Session A: create and delete
    session_a = Session()
    repo_a = SQLAlchemyEntityRepository(session_a)
    mgr_a = EntityManager(repo_a)

    entity_a, created_a = await mgr_a.resolve_or_create(
        source="tak", external_id="FS_T1", entity_type=EntityType.CONTACT
    )
    assert created_a is True
    entity_id = entity_a.id
    await mgr_a.delete(entity_id)
    session_a.commit()

    # Session B: completely new session, new repository, new manager
    session_b = Session()
    repo_b = SQLAlchemyEntityRepository(session_b)
    mgr_b = EntityManager(repo_b)

    # get() from fresh session must return the entity
    entity_b = await mgr_b.get(entity_id)
    assert entity_b is not None, "Fresh session must retrieve soft-deleted entity"
    assert entity_b.id == entity_id
    assert entity_b.status == EntityStatus.INACTIVE

    # resolve_by_identity from fresh session must return same UUID
    resolved_id = await repo_b.resolve_by_identity("tak", "FS_T1")
    assert resolved_id is not None, "Fresh session must resolve identity"
    assert resolved_id == entity_id

    # resolve_or_create from fresh session must NOT create a new entity
    entity_c, created_c = await mgr_b.resolve_or_create(
        source="tak", external_id="FS_T1", entity_type=EntityType.CONTACT
    )
    assert created_c is False, "Fresh session must not create duplicate entity"
    assert entity_c.id == entity_id
    assert entity_c.status == EntityStatus.INACTIVE

    session_b.close()
    session_a.close()


# ==================== TEST J — Fresh session duplicate prevention ====================

@pytest.mark.asyncio
async def test_sqlalchemy_fresh_session_no_duplicates():
    """Multiple resolve_or_create across sessions must produce exactly one UUID."""
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)

    ids = []

    # Session 1: create
    s1 = Session()
    r1 = SQLAlchemyEntityRepository(s1)
    m1 = EntityManager(r1)
    e1, _ = await m1.resolve_or_create(source="tak", external_id="FD_T1", entity_type=EntityType.CONTACT)
    ids.append(e1.id)
    await m1.delete(e1.id)
    s1.commit()
    s1.close()

    # Session 2: resolve after delete
    s2 = Session()
    r2 = SQLAlchemyEntityRepository(s2)
    m2 = EntityManager(r2)
    e2, _ = await m2.resolve_or_create(source="tak", external_id="FD_T1", entity_type=EntityType.CONTACT)
    ids.append(e2.id)
    s2.commit()
    s2.close()

    # Session 3: another resolve
    s3 = Session()
    r3 = SQLAlchemyEntityRepository(s3)
    m3 = EntityManager(r3)
    e3, _ = await m3.resolve_or_create(source="tak", external_id="FD_T1", entity_type=EntityType.CONTACT)
    ids.append(e3.id)
    s3.commit()
    s3.close()

    unique_ids = set(ids)
    assert len(unique_ids) == 1, f"Expected 1 unique UUID across sessions, got {len(unique_ids)}"

