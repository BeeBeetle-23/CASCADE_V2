from datetime import datetime
from typing import Any, Optional
from .common import ORM


class AuditEventOut(ORM):
    id: int
    application_id: str
    event_type: str
    ts: datetime
    actor: str
    target_entity: str
    previous_state: Optional[Any] = None
    new_state: Optional[Any] = None
    reason: str
    affected_node_ids: list[str] = []
    document_version_ids: list[str] = []
    recommendation_before: Optional[str] = None
    recommendation_after: Optional[str] = None
