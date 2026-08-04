# WO-010-002

# Architecture Notes

---

## Purpose

Production Event Persistence Layer

---

## Architecture

Pipeline

↓

PersistenceStage

↓

RepositoryFactory

↓

SQLAlchemy EventRepository

↓

SQLite

---

## Repository Layer

RepositoryFactory

creates

↓

EventRepository

↓

Session

↓

SQLite

---

## Transactions

Every write operation

Session

↓

commit

or

rollback

---

## Session Lifetime

Short living

Per operation

---

## Locking

Optimistic

Version field

---

## Thread Safety

RepositoryFactory

must create independent Session objects.

---

## Soft Delete

delete()

↓

soft_delete()

↓

is_deleted = True

---

## Query Policy

Every query

must filter

is_deleted == False

unless explicitly requested.

---

## Error Handling

Rollback

↓

Log

↓

Raise

---

## Performance

Indexed fields

- source

- event_type

- priority

- status

- created_at

---

## Future Extensions

PostgreSQL

MariaDB

MySQL

without API changes.