from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[Any] = None


class BoundingBox(BaseModel):
    """PDF page coordinates (points). Absent when unavailable; never zero-filled."""
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _ordered(self):
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bounding box must satisfy x1>=x0 and y1>=y0")
        return self


class NodeState(BaseModel):
    """Engine output for one node. value is a string so Decimals survive JSON exactly."""
    status: str
    value: Optional[str] = None
    reason: str = ""
