"""
Enrichment Stage.

Enriches event data with additional information.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class EnrichmentStage(BaseStage):
    """
    Enriches event data with metadata and defaults.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="enrichment", order=20, required=False, **kwargs)

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Enrich event data."""
        data = dict(context.event_data)

        if "id" not in data or data["id"] is None:
            data["id"] = str(uuid.uuid4())

        if "event_time" not in data:
            data["event_time"] = datetime.now(timezone.utc).isoformat()

        if "correlation_id" not in data or not data["correlation_id"]:
            data["correlation_id"] = context.correlation_id or str(uuid.uuid4())

        if "version" not in data:
            data["version"] = 1

        if context.user and "operator" not in data:
            data["operator"] = context.user

        if context.plugin and "device" not in data:
            data["device"] = context.plugin

        return data
