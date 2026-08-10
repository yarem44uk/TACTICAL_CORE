"""
TACTICAL CORE — Telegram Adapter Payload Normalizer
WO-013-008

Adapter-local helper that normalizes raw Telegram message payloads into
raw dictionaries compatible with the canonical EventFactory.

This is an INDEPENDENT implementation. It reuses the field SEMANTICS of
the legacy Telegram connector (message_id, chat_id, sender_id,
sender_username, message_text, timestamp, reply_to_message_id, media)
but does NOT import or depend on `app.connectors.telegram`. It never
touches EventBus, the API layer, the database, or the event pipeline.

The normalized raw dict is shaped for `EventFactory.create_event`:

    timestamp      -> Event.timestamp        (normalized to UTC by factory)
    correlation_id -> Event.metadata.correlation_id
    all other keys -> Event.payload

Parser output is DOMAIN-ONLY data (a plain dict). It never constructs or
returns canonical `Event` objects; Event construction is performed by
EventFactory through AdapterRuntime.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Field names that the EventFactory recognizes as timestamp keys and moves
# into metadata. Kept local to this helper for clarity.
_TIMESTAMP_KEYS = ("timestamp", "time", "datetime", "date", "ts", "created_at")

# Telegram Bot API media/attachment fields (mirrors legacy connector).
_MEDIA_FIELDS = ("photo", "video", "document", "audio", "voice", "sticker")


class TelegramParseError(Exception):
    """Raised when a Telegram payload cannot be normalized.

    A single malformed message raising this error is isolated and dropped
    by the adapter's ingest path without killing the adapter runtime.
    """


class TelegramPayloadNormalizer:
    """Normalizes raw Telegram payloads into EventFactory-compatible dicts.

    This mirrors the field semantics of the legacy Telegram connector
    while remaining fully independent of it (no cross-import).
    """

    def __init__(self) -> None:
        # Required Telegram message identifiers (from the Bot API shape).
        self._required_fields = ("message_id", "chat_id", "sender_id")

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single raw Telegram message into a raw event dict.

        Args:
            payload: Raw Telegram message payload (dict). Expected to carry
                the Bot API shape: `message_id`, `chat.id`, `from.id`,
                optional `text`/`caption`, `date`, `reply_to_message`,
                and media fields.

        Returns:
            A raw dict suitable for `EventFactory.create_event`. The dict
            carries a recognized timestamp key plus the message fields.

        Raises:
            TelegramParseError: If the payload is empty or lacks required
                fields, or required sub-fields (chat.id / from.id) are
                missing. The caller isolates this error per-message.
        """
        if not isinstance(payload, dict) or not payload:
            raise TelegramParseError("Telegram payload is empty or not a dict")

        message_id = payload.get("message_id")
        chat = payload.get("chat")
        sender = payload.get("from")

        # chat.id is mandatory (derived from the nested `chat` object).
        chat_id = None
        if isinstance(chat, dict):
            chat_id = chat.get("id")

        # from.id is mandatory (derived from the nested `from` object).
        sender_id = None
        sender_username = None
        sender_first_name = None
        sender_last_name = None
        if isinstance(sender, dict):
            sender_id = sender.get("id")
            sender_username = sender.get("username")
            sender_first_name = sender.get("first_name")
            sender_last_name = sender.get("last_name")

        missing = [
            f for f in self._required_fields
            if {
                "message_id": message_id,
                "chat_id": chat_id,
                "sender_id": sender_id,
            }.get(f) is None
        ]
        if missing:
            raise TelegramParseError(
                f"Telegram payload missing required fields: {missing}"
            )

        # Build the raw event dict. The timestamp key is preserved so the
        # EventFactory normalizes it to a UTC datetime and moves it to
        # metadata; all other fields land in Event.payload.
        raw: dict[str, Any] = {
            "message_id": str(message_id),
            "chat_id": str(chat_id),
            "sender_id": str(sender_id),
        }

        # Optional chat title.
        if isinstance(chat, dict) and chat.get("title") is not None:
            raw["chat_title"] = str(chat["title"])

        # Optional sender identity fields.
        if sender_username is not None:
            raw["sender_username"] = str(sender_username)
        sender_name = self._display_name(
            sender_first_name, sender_last_name, sender_username
        )
        if sender_name is not None:
            raw["sender_name"] = sender_name

        # Message text: prefer `text`, fall back to `caption` (media caption).
        text = payload.get("text")
        if text is None:
            text = payload.get("caption")
        if text is not None:
            raw["text"] = str(text)

        # Optional reply-to reference.
        reply_to = payload.get("reply_to_message")
        if isinstance(reply_to, dict) and reply_to.get("message_id") is not None:
            raw["reply_to_message_id"] = str(reply_to["message_id"])

        # Optional media / attachment metadata (list of dicts).
        media = self._normalize_media(payload)
        if media:
            raw["media"] = media
            raw["has_media"] = True

        # Preserve timestamp through the factory-recognized keys.
        if "date" in payload:
            raw["timestamp"] = payload["date"]
        elif "timestamp" in payload:
            raw["timestamp"] = payload["timestamp"]
        else:
            # Fall back to any other factory-recognized timestamp key.
            for key in _TIMESTAMP_KEYS:
                if key in payload:
                    raw[key] = payload[key]
                    break

        # Preserve an optional correlation identifier for EventMetadata.
        if "correlation_id" in payload and payload["correlation_id"] is not None:
            raw["correlation_id"] = payload["correlation_id"]

        return raw

    @staticmethod
    def _display_name(
        first_name: Any, last_name: Any, username: Any
    ) -> str | None:
        """Compose a best-effort sender display name.

        Mirrors the legacy Telegram `sender_display_name` semantics: prefer
        username (`@user`), then first name, then first+last, else None.
        """
        if username is not None and str(username):
            return f"@{str(username)}"
        if first_name is not None and str(first_name):
            name = str(first_name)
            if last_name is not None and str(last_name):
                name = f"{name} {str(last_name)}"
            return name
        return None

    @staticmethod
    def _normalize_media(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract media/attachment metadata into EventFactory-friendly dicts.

        Mirrors the legacy Telegram connector: for each known media field,
        a single representative entry (largest photo size preferred) is
        captured with `file_id`, `file_unique_id`, `mime_type`,
        `file_size`, `file_name`, and `media_type`.
        """
        result: list[dict[str, Any]] = []
        for media_type in _MEDIA_FIELDS:
            media_data = payload.get(media_type)
            if media_data is None:
                continue
            if isinstance(media_data, list):
                # For photos, pick the largest representative entry; for
                # other arrays pick the first valid dict entry.
                candidates = [
                    item for item in media_data if isinstance(item, dict)
                ]
                if not candidates:
                    continue
                if media_type == "photo":
                    item = max(
                        candidates,
                        key=lambda it: it.get("file_size") or 0,
                    )
                else:
                    item = candidates[0]
            elif isinstance(media_data, dict):
                item = media_data
            else:
                continue

            file_id = item.get("file_id")
            if not file_id:
                continue
            media: dict[str, Any] = {
                "file_id": str(file_id),
                "media_type": media_type,
            }
            file_unique_id = item.get("file_unique_id")
            if file_unique_id is not None:
                media["file_unique_id"] = str(file_unique_id)
            mime_type = item.get("mime_type")
            if mime_type is not None:
                media["mime_type"] = str(mime_type)
            file_size = item.get("file_size")
            if file_size is not None:
                media["file_size"] = file_size
            file_name = (
                item.get("file_name")
                or item.get("filename")
                or item.get("title")
            )
            if file_name is not None:
                media["file_name"] = str(file_name)

            result.append(media)
        return result

    def normalize_batch(
        self, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize a batch of payloads, isolating malformed ones.

        Returns only the successfully normalized raw dicts. Malformed
        messages are logged and skipped so a single bad message cannot
        break the batch/read path.
        """
        raw_events: list[dict[str, Any]] = []
        for idx, payload in enumerate(payloads):
            try:
                raw_events.append(self.normalize(payload))
            except TelegramParseError as exc:
                logger.warning("Telegram payload %d dropped: %s", idx, exc)
        return raw_events
