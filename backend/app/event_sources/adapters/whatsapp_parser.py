"""TACTICAL CORE — WhatsApp Cloud API Payload Normalizer
WO-080

Adapter-local helper that normalizes a raw Meta WhatsApp Cloud API webhook
payload into the flat raw dicts consumed by ``EventFactory.create_event``
through the canonical ``AdapterRuntime``.

This is an INDEPENDENT implementation.  It reuses the field SEMANTICS of the
Meta Cloud API webhook contract (WO-077/WO-078/ADR-015) but DOES NOT import or
depend on any Meta SDK, HTTP client, or connector.  It never touches the
EventBus, the API layer, the database, the event pipeline, or the network.

Webhook shape (Meta Cloud API, as documented in WO-078):

    {
      "object": "whatsapp_business_account",
      "entry": [
        {
          "id": "<WABA_ID>",
          "changes": [
            {
              "field": "messages",
              "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "...",
                             "phone_number_id": "<PHONE_NUMBER_ID>"},
                "contacts": [{"profile": {"name": "..."}, "wa_id": "..."}],
                "messages": [
                  {"from": "<WA_ID>", "id": "<wamid...>", "timestamp": "...",
                   "type": "text", "text": {"body": "..."}},
                  {"from": "<WA_ID>", "id": "<wamid...>", "timestamp": "...",
                   "type": "image", "image": {"id": "...", "mime_type": "...",
                                              "sha256": "...", "caption": "..."}}
                ]
              }
            }
          ]
        }
      ]
    }

Media arrives as REFERENCES only (media id, mime_type, sha256, filename) —
never bytes.  This normalizer NEVER downloads media and never makes an external
call.

The normalized raw dict is shaped for ``EventFactory.create_event``:

    timestamp      -> Event.timestamp        (normalized to UTC by the factory)
    all other keys -> Event.payload

and carries exactly the identity material required by the WO-080 WhatsApp
identity policy (``phone_number_id`` + ``message_id``) plus the message
category and, where present, the media descriptor.

Non-message changes (e.g. ``statuses[]`` delivery receipts) are intentionally
ignored: they describe the fate of an OUTBOUND message and are not inbound
intelligence.  A webhook that carries no messages yields an empty list.
"""

from __future__ import annotations

from typing import Any, Iterator

# Message categories whose payload block is a media REFERENCE (never bytes).
# WO-078 established text/image/audio/video/document; ``sticker`` is included
# because the Cloud API delivers it with the same reference shape.
MEDIA_MESSAGE_TYPES = ("image", "audio", "video", "document", "sticker")


class WhatsAppParseError(Exception):
    """Raised when a WhatsApp webhook payload cannot be normalized.

    The ingress treats this as a deterministic client error (HTTP 400): the
    payload is authentic (signature verified) but structurally unusable, so it
    must never enter the canonical pipeline.
    """


class WhatsAppPayloadNormalizer:
    """Normalizes Meta WhatsApp Cloud API webhook payloads into raw dicts."""

    media_message_types = MEDIA_MESSAGE_TYPES

    def normalize_webhook(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize a full webhook payload into one raw dict per message.

        Args:
            payload: The decoded Meta webhook JSON object.

        Returns:
            A list of raw dicts (possibly empty when the webhook carries no
            inbound messages, e.g. a statuses-only delivery receipt).

        Raises:
            WhatsAppParseError: If the payload is empty, not a dict, or lacks
                the ``entry`` list.  A single malformed message raises the same
                error (it is NOT silently dropped, because the ingress must not
                acknowledge a message it could not normalize).
        """
        if not isinstance(payload, dict) or not payload:
            raise WhatsAppParseError("WhatsApp webhook payload is empty or not a dict")
        if "entry" not in payload:
            raise WhatsAppParseError("WhatsApp webhook payload has no 'entry'")
        entries = payload.get("entry")
        if not isinstance(entries, list):
            raise WhatsAppParseError("WhatsApp webhook 'entry' must be a list")

        raw_events: list[dict[str, Any]] = []
        for entry in entries:
            for value in self._iter_change_values(entry):
                raw_events.extend(self._normalize_value(value))
        return raw_events

    # --- internals -------------------------------------------------------

    @staticmethod
    def _iter_change_values(entry: Any) -> Iterator[dict[str, Any]]:
        """Yield each ``changes[].value`` dict from one entry (defensively)."""
        if not isinstance(entry, dict):
            return
        changes = entry.get("changes")
        if not isinstance(changes, list):
            return
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if isinstance(value, dict):
                yield value

    def _normalize_value(self, value: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize one ``changes[].value`` block into raw message dicts."""
        metadata = value.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        phone_number_id = metadata.get("phone_number_id")
        display_phone_number = metadata.get("display_phone_number")

        messages = value.get("messages")
        if not isinstance(messages, list):
            # statuses-only change (outbound delivery receipt): nothing inbound.
            return []

        return [
            self._normalize_message(m, phone_number_id, display_phone_number)
            for m in messages
        ]

    def _normalize_message(
        self,
        message: Any,
        phone_number_id: Any,
        display_phone_number: Any,
    ) -> dict[str, Any]:
        """Normalize a single ``messages[]`` entry into a raw dict."""
        if not isinstance(message, dict):
            raise WhatsAppParseError("WhatsApp message entry is not a dict")

        message_id = message.get("id")
        if message_id is None or not str(message_id).strip():
            raise WhatsAppParseError("WhatsApp message is missing 'id'")
        if phone_number_id is None or not str(phone_number_id).strip():
            raise WhatsAppParseError(
                "WhatsApp message is missing metadata.phone_number_id"
            )

        sender = message.get("from")
        message_type = message.get("type")

        raw: dict[str, Any] = {
            "message_id": str(message_id),
            "phone_number_id": str(phone_number_id),
            "sender": None if sender is None else str(sender),
            "message_type": None if message_type is None else str(message_type),
            "text": "",
        }
        if display_phone_number is not None:
            raw["display_phone_number"] = str(display_phone_number)
        if message.get("timestamp") is not None:
            raw["timestamp"] = message.get("timestamp")

        type_str = raw["message_type"]

        if type_str == "text":
            block = message.get("text")
            body = block.get("body") if isinstance(block, dict) else None
            raw["text"] = "" if body is None else str(body)
        elif type_str in self.media_message_types:
            raw["media"] = self._normalize_media(type_str, message.get(type_str))
            caption = raw["media"].get("caption")
            if caption:
                raw["text"] = str(caption)
        # Any other category is ingested METADATA-ONLY (message_type preserved,
        # no fabricated fields).  Documented in ADR-015/WO-080: rejecting an
        # authentic message would make Meta retry it indefinitely.

        return raw

    @staticmethod
    def _normalize_media(message_type: str, block: Any) -> dict[str, Any]:
        """Normalize a media message block into a reference-only descriptor.

        Only fields actually present in the webhook are kept; nothing is
        invented (in particular, ``sha256`` is only carried when Meta supplied
        it — the normalizer never computes or fabricates a hash).  No bytes are
        fetched.
        """
        descriptor: dict[str, Any] = {"media_type": message_type}
        if isinstance(block, dict):
            for source_key, target_key in (
                ("id", "media_id"),
                ("mime_type", "mime_type"),
                ("sha256", "sha256"),
                ("filename", "filename"),
                ("caption", "caption"),
                ("voice", "voice"),
                ("animated", "animated"),
            ):
                value = block.get(source_key)
                if value is not None:
                    descriptor[target_key] = value
        return descriptor
