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


# ==================== TEST G — No duplicate identity ====================

@pytest.mark.asyncio
async def test_no_duplicate_identity_after_delete():
    repo = make_sql_repo()
    mgr = EntityManager(repo)

    e1, _ = await mgr.resolve_or_create(source="tak", external_id="T8", entity_type=EntityType.CONTACT)
    await mgr.delete(e1.id)
    e2, _ = await mgr.resolve_or_create(source="tak", external_id="T8", entity_type=EntityType.CONTACT)
    e3, _ = await mgr.resolve_or_create(source="tak", external_id="T8", entity_type=EntityType.CONTACT)

    assert e2.id == e1.id
    assert e3.id == e1.id
    unique_ids = {e1.id, e2.id, e3.id}
    assert len(unique_ids) == 1
