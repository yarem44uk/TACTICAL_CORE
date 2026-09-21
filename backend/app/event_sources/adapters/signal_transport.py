"""
TACTICAL CORE — Signal Transport Seam
WO-075

The smallest possible transport abstraction required to feed Signal messages
into ``SignalSourceAdapter.ingest(payload)``.

The transport is a LEAF producer with exactly one production responsibility:

    transport.start(sink)          # sink == SignalSourceAdapter.ingest
        -> sink(payload)           # one dict payload per received Signal message
    transport.stop()

Responsibilities (and nothing more):

    * obtain a Signal payload however the embedding deployment does so
    * hand the payload to the adapter through the injected ``sink`` callable
    * release its own resources on ``stop()``

It does NOT, and must NOT:

    * provision / install / launch signal-cli
    * authenticate or log in to a Signal account
    * open a live Signal network connection or deliver live messages
    * store credentials or secret material
    * construct canonical Events, touch EventBus / EventPipeline / the database
      / the API layer
    * implement cursor, replay, restart or retry semantics

Injection seam (WO-075): the production composition injects the transport when
it builds the Signal adapter, through the EXISTING adapter-type registration
mechanism::

    build_production_adapter_factory(signal_transport=my_transport)
        -> register_signal_adapter(factory, transport=my_transport)
        -> AdapterFactory.create(definition)
        -> SignalSourceAdapter(definition, transport=my_transport)

When no transport is injected the adapter remains a purely passive queue
(backward compatible: identical to its pre-WO-075 behaviour).

Live Signal connectivity is explicitly OUT OF SCOPE (WO-075).  A synthetic /
in-memory transport implementation is used exclusively for acceptance testing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

# A sink accepts exactly one raw Signal payload and returns True when the
# adapter accepted it (False when it was malformed and dropped).
SignalIngestSink = Callable[[dict[str, Any]], bool]


class SignalTransportError(Exception):
    """Raised by a transport when it cannot start, stop, or obtain payloads.

    A failure raised from ``start()`` propagates through
    ``SignalSourceAdapter.start()`` into the canonical ``AdapterRuntime``
    failure path (runtime-level failure -> bounded restart / FAILED); it is
    never swallowed into a silent "healthy" state.
    """


class SignalTransport(ABC):
    """Abstract Signal payload transport feeding the adapter ingest seam.

    Implementations are LEAF producers: they call the injected sink and never
    reach the canonical event path directly.
    """

    @abstractmethod
    def start(self, sink: SignalIngestSink) -> None:
        """Begin obtaining Signal payloads and feed them to ``sink``.

        Args:
            sink: The adapter's ingest callable
                (``SignalSourceAdapter.ingest``).  Returns True when the
                payload was accepted, False when it was malformed and dropped.

        Raises:
            SignalTransportError: If the transport cannot start.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop obtaining payloads and release resources (idempotent)."""
        ...
