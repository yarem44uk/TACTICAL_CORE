"""WO-080 — Meta ``X-Hub-Signature-256`` verification.

The signature is an HMAC-SHA256 over the EXACT raw request body, keyed by the
Meta App Secret, sent in the ``X-Hub-Signature-256`` header as::

    sha256=<hex digest>

Verification MUST happen over the raw bytes (never a re-serialized JSON object:
re-serialization changes whitespace/key order and invalidates the signature)
and MUST use constant-time comparison.

The App Secret is never logged, never echoed in a response, and never placed on
a canonical event.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

SIGNATURE_HEADER = "X-Hub-Signature-256"
_SIGNATURE_PREFIX = "sha256="


def compute_signature(app_secret: str, raw_body: bytes) -> str:
    """Return the ``sha256=<hex>`` signature for ``raw_body``.

    Args:
        app_secret: The Meta App Secret (never logged by this module).
        raw_body: The exact raw request body bytes.
    """
    digest = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return f"{_SIGNATURE_PREFIX}{digest}"


def verify_signature(
    app_secret: str,
    raw_body: bytes,
    header_value: Optional[str],
) -> bool:
    """Verify an ``X-Hub-Signature-256`` header value against ``raw_body``.

    Returns:
        True only when the header is present, correctly prefixed, and matches
        the HMAC-SHA256 of the raw body under ``app_secret`` (constant-time
        comparison).  Any malformed, missing, or mismatching value is False.
    """
    if not app_secret or not header_value:
        return False

    presented = header_value.strip()
    if not presented.startswith(_SIGNATURE_PREFIX):
        return False

    expected = compute_signature(app_secret, raw_body)
    # Constant-time comparison; compare the full prefixed strings so a length
    # difference cannot leak byte-by-byte.
    return hmac.compare_digest(expected, presented)
