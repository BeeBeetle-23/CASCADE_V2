from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .common import NodeState
from .graph import GraphPayload


class NodeDiff(BaseModel):
    before: NodeState
    after: NodeState


class SimulationRequest(BaseModel):
    excluded_node_id: str = Field(min_length=1, description="Document or claim node to exclude")
    actor: str = Field(default="analyst", max_length=100)


class SimulationResult(BaseModel):
    id: Optional[int] = None
    excluded_node_id: str
    original_recommendation: NodeState
    simulated_recommendation: NodeState
    recommendation_changed: bool
    changes: dict[str, NodeDiff]
    created_at: Optional[datetime] = None
    simulated_graph: Optional[GraphPayload] = None  # same layout, simulated states; live state untouched


class CascadeResult(BaseModel):
    initiator: str
    downstream_order: list[str]            # topological order of true descendants
    changed: dict[str, NodeDiff]
    unchanged_downstream: list[str]        # descendants whose result stayed the same
    independent_unchanged: list[str]       # nodes outside the descendant set
    recommendation: NodeState
    graph: GraphPayload
