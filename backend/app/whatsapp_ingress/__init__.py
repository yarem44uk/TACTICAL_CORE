"""TACTICAL CORE — WhatsApp Inbound Webhook Ingress (WO-080).

A SEPARATE, independently startable ingress process that terminates the public
WhatsApp Cloud API webhook trust boundary and drives the EXISTING canonical
ingestion path:

    Meta Cloud API
      -> WhatsApp Webhook Ingress (this package; own process, own entrypoint)
      -> X-Hub-Signature-256 verification over the RAW request body
      -> WhatsAppPayloadNormalizer
      -> WhatsAppSourceAdapter (leaf; registered via AdapterFactory)
      -> AdapterRuntime.submit_raw()   (synchronous durable seam)
      -> EventFactory -> EventPipeline -> DurableCanonicalEventRepository
      -> Observation -> Operator Wall

This package is NOT ``backend/main.py`` and NOT the operator FastAPI
application.  The operator API remains read-only and is never on the ingestion
path (ADR-011 §15, ADR-015 §5).  No second event architecture is introduced.

See ``docs/adr/ADR-015-WhatsApp-Ingress-Architecture.md``.
"""

from .app import create_whatsapp_ingress_app
from .config import WhatsAppIngressConfig, WhatsAppIngressConfigError
from .service import IngressOutcome, WhatsAppIngressService
from .signature import compute_signature, verify_signature

__all__ = [
    "create_whatsapp_ingress_app",
    "WhatsAppIngressConfig",
    "WhatsAppIngressConfigError",
    "IngressOutcome",
    "WhatsAppIngressService",
    "compute_signature",
    "verify_signature",
]
