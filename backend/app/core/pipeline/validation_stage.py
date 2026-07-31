"""
Validation Stage.

Validates event data against expected schema and rules.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, List, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class ValidationStage(BaseStage):
    """
    Validates incoming event data.

    Checks required fields, data types, and business rules.
    """

    REQUIRED_FIELDS = ["title", "source", "source_type", "category"]

    def __init__(self, **kwargs) -> None:
        super().__init__(name="validation", order=10, required=True, **kwargs)

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Validate event data."""
        data = context.event_data
        errors = self.validate(data)

        if errors:
            context.stage_errors["validation"] = errors
            return data

        return data

    def validate(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate event data and return errors."""
        errors = []

        for field in self.REQUIRED_FIELDS:
            if field not in data or not data[field]:
                errors.append({
                    "code": "MISSING_FIELD",
                    "message": "Required field missing: " + field,
                    "field": field,
                })

        if "latitude" in data or "longitude" in data:
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is not None and not (-90 <= lat <= 90):
                errors.append({
                    "code": "INVALID_COORDINATE",
                    "message": "Latitude must be between -90 and 90",
                    "field": "latitude",
                })
            if lon is not None and not (-180 <= lon <= 180):
                errors.append({
                    "code": "INVALID_COORDINATE",
                    "message": "Longitude must be between -180 and 180",
                    "field": "longitude",
                })

        if "ai_confidence" in data:
            conf = data["ai_confidence"]
            if conf is not None and not (0 <= conf <= 1):
                errors.append({
                    "code": "INVALID_CONFIDENCE",
                    "message": "AI confidence must be between 0 and 1",
                    "field": "ai_confidence",
                })

        return errors
