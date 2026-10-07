"""WO-083 — Telegram ``X-Telegram-Bot-Api-Secret-Token`` verification.

Telegram's webhook security model (Bot API ``setWebhook`` ``secret_token``,
WO-082 GATE G / GATE C) is deliberately DIFFERENT from Meta/WhatsApp:

    WhatsApp/Meta : ``X-Hub-Signature-256`` = HMAC-SHA256 over the RAW body,
                    keyed by the App Secret (see
                    ``app.whatsapp_ingress.signature``).

    Telegram      : ``X-Telegram-Bot-Api-Secret-Token`` = a STATIC SHARED
                    SECRET that Telegram echoes back verbatim in the header of
                    every webhook POST.  Telegram does NOT sign the request
                    body, so there is nothing to compute an HMAC over.

Introducing HMAC signing here would be inventing a protocol that Telegram does
not implement (WO-083 §9).  This module therefore implements exactly the
documented mechanism: a constant-time comparison of the presented header value
against the configured secret, failing closed on any missing/empty/mismatch.

The secret is never logged, never echoed in a response, and never placed on a
canonical event.
"""

from __future__ import annotations

import hmac
from typing import Optional

# Telegram's documented webhook secret header (Bot API, setWebhook secret_token).
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def verify_secret_token(
    expected_secret: str,
    presented_header: Optional[str],
) -> bool:
    """Verify the Telegram webhook secret header in constant time.

    Args:
        expected_secret: The configured webhook ``secret_token`` (never logged).
        presented_header: The value of ``X-Telegram-Bot-Api-Secret-Token`` as
            received (``None`` when the header is absent).

    Returns:
        True only when the header is present, non-empty, and equal to the
        configured secret.  Comparison is constant-time
        (:func:`hmac.compare_digest`) so a mismatch cannot be probed
        byte-by-byte.  Any missing, empty, or mismatching value is False
        (fail closed).
    """
    if not expected_secret or not presented_header:
        return False

    presented = presented_header.strip()
    if not presented:
        return False

    return hmac.compare_digest(expected_secret, presented)
