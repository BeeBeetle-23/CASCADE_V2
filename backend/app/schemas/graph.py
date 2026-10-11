from typing import Any, Optional
from pydantic import BaseModel
from .common import NodeState


class RFPosition(BaseModel):
    x: float
    y: float


class RFNodeData(BaseModel):
    label: str
    node_type: str
    status: str
    value: Optional[str] = None
    reason: str = ""
    verification: Optional[str] = None
    upstream: list[str] = []
    downstream: list[str] = []
    supporting_claim_ids: list[str] = []
    affected: bool = False      # highlighted after a cascade / simulation
    initiator: bool = False     # the source that was changed
    last_recalculated_at: Optional[str] = None


class RFNode(BaseModel):
    id: str
    type: str                   # custom React Flow node type
    position: RFPosition
    data: RFNodeData


class RFEdge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None
    animated: bool = False
    data: dict[str, Any] = {}   # {reason, relationship, affected}


class GraphPayload(BaseModel):
    application_id: str
    scenario_key: Optional[str] = None
    nodes: list[RFNode]
    edges: list[RFEdge]
    recommendation: NodeState
    generated_at: str
