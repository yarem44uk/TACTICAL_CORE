from typing import List, Callable, Any, Optional
from threading import Lock
import logging
from app.event.event import Event
from .interfaces.i_event_pipeline import IEventPipeline

class EventPipeline(IEventPipeline):
    def __init__(self):
        self._before_middleware: List[Callable[[Any], Any]] = []
        self._filters: List[Callable[[Any], bool]] = []
        self._after_middleware: List[Callable[[Any], Any]] = []
        self._dispatcher: Optional[Any] = None
        self._repository: Optional[Any] = None
        self._event_bus: Optional[Any] = None
        self._projection: Optional[Any] = None
        self._delivery_dispatcher: Optional[Any] = None
        # WO-027: consumers that contractually receive every canonical event
        # through the durable outbox (post-commit delivery).
        self._outbox_consumer_ids: List[str] = []
        self._lock = Lock()

    def set_dispatcher(self, dispatcher: Any) -> None:
        self._dispatcher = dispatcher

    def set_repository(self, repository: Any) -> None:
        self._repository = repository

    def set_event_bus(self, event_bus: Any) -> None:
        self._event_bus = event_bus

    def set_projection(self, projection: Any) -> None:
        """Attach an optional entity-projection step (WO-014-022).

        The projection is invoked AFTER the durable repository has persisted
        the canonical Event, and is strictly best-effort: a projection
        failure is logged but never propagated, so it can neither roll back
        nor prevent durable Event persistence.

        Args:
            projection: A callable ``projection(event)`` that derives Entity
                state from a canonical Event (e.g. an EntityBridge adapter).
        """
        self._projection = projection

    def set_delivery_dispatcher(self, delivery_dispatcher: Any) -> None:
        """WO-027 — Enable durable post-commit delivery for this pipeline.

        When a ``DurableDeliveryDispatcher`` is attached (with the durable
        repository's atomic ``save_with_deliveries`` contract), the pipeline
        writes the canonical event AND its PENDING outbox delivery records in
        one transaction, then runs the post-commit delivery dispatcher.  No
        consumer side effect runs before the durable commit.

        Args:
            delivery_dispatcher: a component exposing ``register_consumer``,
                ``enqueue``, ``deliver_pending`` and ``outbox``.  Typically a
                ``DurableDeliveryDispatcher``.
        """
        self._delivery_dispatcher = delivery_dispatcher

    def set_outbox_consumer_ids(self, consumer_ids: List[str]) -> None:
        """WO-027 — Set the consumers that contractually receive every event.

        These consumer ids are enqueued into the durable outbox transactionally
        with each canonical event commit.
        """
        self._outbox_consumer_ids = list(consumer_ids)

    def process(self, event: Any) -> bool:
        with self._lock:
            # 1. Before Middleware
            for mw in self._before_middleware:
                event = mw(event)
            if event is None:
                return False
            
            # 2. Filters
            for f in self._filters:
                if not f(event):
                    return False

            # WO-027 — durable post-commit delivery path (transactional outbox).
            # When a delivery dispatcher is configured AND the repository
            # supports atomic event+outbox persistence, the pipeline commits
            # the canonical event and its delivery records together, then
            # delivers to consumers strictly AFTER the commit.  No consumer
            # side effect (plugin, event bus, observation) runs before the
            # durable commit.  This is the PRODUCTION path.
            if self._delivery_dispatcher is not None:
                return self._process_durable(event)

            # --- legacy / mock / runtime-only path (no durable outbox) -------
            # 3. Dispatcher
            if self._dispatcher and hasattr(self._dispatcher, 'dispatch'):
                self._dispatcher.dispatch(event)
                
            # 4. After Middleware
            for mw in self._after_middleware:
                event = mw(event)
            if event is None:
                return False

            # 5. Repository
            if self._repository and hasattr(self._repository, 'save'):
                self._repository.save(event)

            # 5b. Entity projection (WO-014-022) — AFTER durable persistence,
            #     best-effort: a projection failure must never roll back or
            #     prevent the canonical Event durability achieved in (5).
            if self._projection is not None:
                try:
                    self._projection(event)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "EventPipeline projection failed (best-effort, not "
                        "propagating) for event_id=%s",
                        getattr(event, "event_id", None),
                    )

            # 6. EventBus
            if self._event_bus and hasattr(self._event_bus, 'publish'):
                self._event_bus.publish(event)
                
        return True

    def _process_durable(self, event: Any) -> bool:
        """WO-027 — Durable post-commit delivery pipeline.

        Runs middleware/filters, then atomically persists the canonical event
        and its outbox delivery records, then projects (post-commit), then
        delivers to consumers strictly AFTER the durable commit.

        WO-030 (Option C — hybrid): the hot path delivers the ORIGINAL
        in-memory canonical ``Event`` to the registered consumers (plugins /
        observation) and durably marks their delivery records DELIVERED (or
        FAILED for retry) via the existing WO-029 outbox mechanisms.  Crash /
        retry / requeue / stale-IN_FLIGHT recovery continues to reconstruct a
        canonical ``Event`` from ``record.event_id`` through the WO-031
        durable event repository.  Returns True on successful commit +
        delivery; delivery is AT-LEAST-ONCE and independently retryable via
        the durable outbox.
        """
        import logging as _logging

        _log = _logging.getLogger(__name__)

        # WO-030 — reject non-canonical input at the durable boundary, BEFORE
        # any persistence / outbox processing.  A raw dict is never a valid
        # canonical Event and must not reach the durable store.  This mirrors
        # PluginManager.deliver_event (TypeError) and keeps test_raw_dict
        # rejection deterministic on the durable path.
        if not isinstance(event, Event):
            raise TypeError(
                "EventPipeline durable path requires a canonical "
                f"app.event.Event, got {type(event).__name__}"
            )

        # 4. After Middleware
        for mw in self._after_middleware:
            event = mw(event)
        if event is None:
            return False

        event_id = getattr(event, "event_id", None)
        consumer_ids = list(self._outbox_consumer_ids)

        # 5. Atomic durable commit: canonical event + outbox delivery records.
        #    No consumer side effect has run yet.
        repo = self._repository
        if repo is not None and hasattr(repo, "save_with_deliveries"):
            repo.save_with_deliveries(event, consumer_ids)
        elif repo is not None and hasattr(repo, "save"):
            repo.save(event)
            dd = self._delivery_dispatcher
            if dd is not None and event_id is not None:
                dd.enqueue(event_id, consumer_ids)

        # 5b. Projection — AFTER durable commit, best-effort (unchanged).
        if self._projection is not None:
            try:
                self._projection(event)
            except Exception:
                _log.exception(
                    "EventPipeline projection failed (best-effort) for "
                    "event_id=%s",
                    event_id,
                )

        # 6. WO-030 hot-path — deliver the ORIGINAL committed canonical Event
        #    to the registered consumers, then mark the corresponding durable
        #    delivery records DELIVERED (or FAILED for retry).  This avoids
        #    the WO-031 reconstruction round-trip for the just-committed event
        #    and preserves the original Event instance on the hot path.  The
        #    WO-029 mark_delivered/mark_failed mechanisms are reused (no
        #    second state machine, no WO-029 semantics change).
        #
        #    We reach the dispatcher's registered consumer callbacks and its
        #    outbox repository directly (delivery_dispatcher.py is immutable
        #    for WO-030); consumers not yet registered are left PENDING so the
        #    durable recovery pass can deliver them once they register.
        dd = self._delivery_dispatcher
        if dd is not None:
            consumers = getattr(dd, "_consumers", {}) or {}
            outbox = getattr(dd, "_outbox", None)
            for cid in consumer_ids:
                cb = consumers.get(cid)
                if cb is None:
                    # Consumer not registered yet: leave the record PENDING so
                    # it is delivered by the durable recovery pass later.
                    continue
                try:
                    cb(event)  # deliver the ORIGINAL canonical Event
                except Exception:  # noqa: BLE001 - consumer failure is recorded, not fatal
                    _log.exception(
                        "hot-path delivery failed for event_id=%s consumer=%s",
                        event_id,
                        cid,
                    )
                    if outbox is not None:
                        outbox.mark_failed(event_id, cid, "consumer raised")
                else:
                    if outbox is not None:
                        outbox.mark_delivered(event_id, cid)

            # 6b. Recovery — deliver any OTHER pending/stale/failed/requeued
            #     records (WO-031 reconstruction from record.event_id).  The
            #     just-committed hot-path records above are now DELIVERED (or
            #     FAILED), so they are not redelivered here.
            try:
                dd.deliver_pending()
            except Exception:  # noqa: BLE001 - delivery is retryable via outbox
                _log.exception(
                    "recovery delivery pass failed (events remain in "
                    "durable outbox) for event_id=%s",
                    event_id,
                )
        return True

    def add_filter(self, filter_func: Callable[[Any], bool]) -> None:
        with self._lock:
            self._filters.append(filter_func)

    def remove_filter(self, filter_func: Callable[[Any], bool]) -> None:
        with self._lock:
            if filter_func in self._filters:
                self._filters.remove(filter_func)

    def add_before(self, middleware: Callable[[Any], Any]) -> None:
        with self._lock:
            self._before_middleware.append(middleware)

    def add_after(self, middleware: Callable[[Any], Any]) -> None:
        with self._lock:
            self._after_middleware.append(middleware)

    def clear(self) -> None:
        with self._lock:
            self._before_middleware.clear()
            self._filters.clear()
            self._after_middleware.clear()
            self._dispatcher = None
            self._repository = None
            self._event_bus = None
            self._projection = None
