"""WO-083 — Telegram ``Update`` normalizer (the missing wrapper layer).

WO-082 established that the existing canonical Telegram leaf
(``app.event_sources.adapters.telegram_parser``) normalizes a Telegram
**Message** object, not the ``Update`` ENVELOPE that a webhook actually
delivers.  WO-083 was bounded to implement exactly that missing layer, reusing
the existing message-level media semantics.

Shape (Telegram Bot API, webhook POST body):

    {
      "update_id": 123456789,
      "message": {
        "message_id": 42,
        "from": {"id": 777, "username": "alpha", "first_name": "Alpha"},
        "chat": {"id": -100200300, "type": "group", "title": "..."},
        "date": 1735689600,
        "text": "...",                 # or "caption" for media messages
        "photo": [{"file_id": "...", "file_unique_id": "...",
                   "file_size": 1234}, ...],
        "document": {"file_id": "...", "mime_type": "...", "file_name": "..."}
      }
    }

This module is a PURE TRANSPORT-BOUNDARY helper.  It never constructs a
canonical Event, never touches EventFactory / EventPipeline / the database, and
never makes an external call.  It returns the same kind of raw dict that
``TelegramPayloadNormalizer`` returns, so the canonical
``AdapterRuntime.submit_raw`` path is unchanged.

Identity material (WO-083 §13):

    ``chat_id`` + ``message_id`` are the canonical external identity.  Both are
    emitted as ``str`` (matching ``TelegramPayloadNormalizer`` exactly) so the
    EXISTING ``telegram`` identity policy
    (``app.event_sources.identity.event_identity._telegram_identity``:
    ``_native(raw, "chat_id", "message_id")``) resolves a deterministic UUID5
    with no change to shared identity code and no second namespace.

    When either component is missing the normalizer raises
    ``TelegramUpdateError`` (the ingress maps that to HTTP 400 with zero durable
    events).  There is NO UUID4 fallback, NO identity invented from
    ``update_id`` / timestamps / usernames / message text.

``update_id`` is preserved in the raw payload for observability/replay only; it
is NOT identity material (WO-083 §12).
"""

from __future__ import annotations

from typing import Any

from app.event_sources.adapters.telegram_parser import TelegramPayloadNormalizer

# The single Telegram update type supported by the WO-083 first vertical slice.
SUPPORTED_UPDATE_TYPE = "message"

# Factory-recognized timestamp keys (mirrors TelegramPayloadNormalizer).
_TIMESTAMP_KEYS = ("timestamp", "time", "datetime", "date", "ts", "created_at")


class TelegramUpdateError(Exception):
    """Raised when a Telegram ``Update`` cannot be normalized.

    The ingress treats this as a deterministic client error (HTTP 400): the
    request is authentic (secret token verified) but structurally unusable or
    outside the supported first-slice model, so it must never enter the
    canonical pipeline and must never be acknowledged as durable.
    """


class TelegramUpdateNormalizer:
    """Normalizes a Telegram ``Update`` envelope into an EventFactory raw dict.

    Reuses the EXISTING ``TelegramPayloadNormalizer._normalize_media`` static
    helper for the message-level media/reference semantics (largest photo
    preferred, ``file_id`` / ``file_unique_id`` / ``mime_type`` / ``file_size``
    / ``file_name`` / ``media_type``), so Telegram media semantics live in one
    place and no second media vocabulary is invented.
    """

    def __init__(self) -> None:
        # Shared instance of the existing message-level normalizer (media).
        self._message_normalizer = TelegramPayloadNormalizer()

    def normalize_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one Telegram ``Update`` into a raw event dict.

        Args:
            payload: The decoded Telegram ``Update`` JSON object.

        Returns:
            A raw dict suitable for ``AdapterRuntime.submit_raw`` (and
            ``EventFactory.create_event``): ``chat_id`` + ``message_id``
            (identity), ``text`` (always present, ``""`` when the message
            carries neither text nor caption), optional sender/chat/reply
            fields, optional reference-only ``media`` list, ``timestamp`` from
            ``date``, and ``update_id`` for observability.

        Raises:
            TelegramUpdateError: If the payload is empty/not a dict, carries no
                supported ``message`` update, or the message is missing
                ``message_id`` / ``chat.id``.  Nothing is invented on failure.
        """
        if not isinstance(payload, dict) or not payload:
            raise TelegramUpdateError("Telegram update payload is empty or not a dict")

        if SUPPORTED_UPDATE_TYPE not in payload:
            present = sorted(k for k in payload if k != "update_id")
            raise TelegramUpdateError(
                "unsupported Telegram update type; only "
                f"'{SUPPORTED_UPDATE_TYPE}' is supported in this slice "
                f"(present keys: {present})"
            )

        message = payload.get(SUPPORTED_UPDATE_TYPE)
        if not isinstance(message, dict):
            raise TelegramUpdateError(
                f"Telegram update '{SUPPORTED_UPDATE_TYPE}' must be an object"
            )

        # --- canonical identity material (chat_id + message_id) -------------
        message_id = message.get("message_id")
        if message_id is None or not str(message_id).strip():
            raise TelegramUpdateError("Telegram message is missing 'message_id'")

        chat = message.get("chat")
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        if chat_id is None or not str(chat_id).strip():
            raise TelegramUpdateError("Telegram message is missing 'chat.id'")

        raw: dict[str, Any] = {
            "message_id": str(message_id),
            "chat_id": str(chat_id),
            # Always present (the canonical telegram.message observation mapping
            # requires the field to exist); "" when there is no text/caption.
            "text": "",
        }

        # --- chat metadata (non-identity) -----------------------------------
        if isinstance(chat, dict):
            if chat.get("type") is not None:
                raw["chat_type"] = str(chat["type"])
            if chat.get("title") is not None:
                raw["chat_title"] = str(chat["title"])

        # --- sender metadata (optional; never identity) ---------------------
        sender = message.get("from")
        if isinstance(sender, dict):
            if sender.get("id") is not None:
                raw["sender_id"] = str(sender["id"])
            if sender.get("username") is not None:
                raw["sender_username"] = str(sender["username"])
            if sender.get("is_bot") is not None:
                raw["sender_is_bot"] = bool(sender["is_bot"])
            display_name = self._display_name(
                sender.get("first_name"),
                sender.get("last_name"),
                sender.get("username"),
            )
            if display_name is not None:
                raw["sender_name"] = display_name

        # --- message content ------------------------------------------------
        text = message.get("text")
        if text is None:
            text = message.get("caption")
        if text is not None:
            raw["text"] = str(text)

        reply_to = message.get("reply_to_message")
        if isinstance(reply_to, dict) and reply_to.get("message_id") is not None:
            raw["reply_to_message_id"] = str(reply_to["message_id"])

        # --- media: REFERENCE ONLY (never bytes, never a getFile call) ------
        media = self._message_normalizer._normalize_media(message)
        if media:
            caption = message.get("caption")
            if caption is not None:
                for entry in media:
                    entry.setdefault("caption", str(caption))
            raw["media"] = media
            raw["has_media"] = True

        # --- timestamp (from message 'date', unix seconds) ------------------
        if "date" in message:
            raw["timestamp"] = message["date"]
        else:
            for key in _TIMESTAMP_KEYS:
                if key in message:
                    raw[key] = message[key]
                    break

        # --- observability / replay only (NOT identity) ---------------------
        update_id = payload.get("update_id")
        if update_id is not None:
            raw["update_id"] = update_id

        return raw

    @staticmethod
    def _display_name(
        first_name: Any, last_name: Any, username: Any
    ) -> str | None:
        """Compose a best-effort sender display name.

        Mirrors ``TelegramPayloadNormalizer._display_name`` semantics exactly:
        prefer ``@username``, then first name, then first + last, else None.
        """
        if username is not None and str(username):
            return f"@{str(username)}"
        if first_name is not None and str(first_name):
            name = str(first_name)
            if last_name is not None and str(last_name):
                name = f"{name} {str(last_name)}"
            return name
        return None
