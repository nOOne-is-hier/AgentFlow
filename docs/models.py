from typing import List, Literal, Optional, TypedDict, Union, Dict, Any
from pydantic import BaseModel, Field, AwareDatetime

NodeType = Literal[
    "parse_pdf", "embed_pdf", "build_vectorstore",
    "merge_xlsx", "validate_with_pdf", "export_xlsx"
]

OutKey = Literal[
    "pdf_chunks", "pdf_embeddings", "vs_ref",
    "merged_table", "validation_report", "artifact_path"
]

class Edge(BaseModel):
    from_: str = Field(alias="from")
    to: str

class BaseNode(BaseModel):
    id: str
    type: NodeType
    label: str
    config: Dict[str, Any]
    in_: List[str] = Field(alias="in")
    out: List[OutKey]

class Workflow(BaseModel):
    id: str
    name: str
    nodes: List[BaseNode]
    edges: List[Edge]
    createdAt: AwareDatetime
    updatedAt: AwareDatetime

class GraphPatch(BaseModel):
    addNodes: Optional[List[BaseNode]] = None
    addEdges: Optional[List[Edge]] = None
    updateLabels: Optional[List[Dict[str, str]]] = None
    removeNodes: Optional[List[str]] = None
    removeEdges: Optional[List[Edge]] = None

# ---- Validation Report ----
class Evidence(BaseModel):
    page: int = Field(ge=1)
    snippet: str = Field(min_length=5, max_length=600)

class ExistsItem(BaseModel):
    policy: Literal["exists"]
    dept: str
    status: Literal["ok", "miss"]
    evidence: Optional[List[Evidence]] = None

class SumCheckItem(BaseModel):
    policy: Literal["sum_check"]
    dept: str
    status: Literal["ok", "diff"]
    expected: int
    found: int
    delta: Optional[int] = None
    evidence: Optional[List[Evidence]] = None

class ValidationSummary(BaseModel):
    ok: int
    warn: int
    fail: int

class ValidationReport(BaseModel):
    summary: ValidationSummary
    items: List[Union[ExistsItem, SumCheckItem]]

# ---- Run Event (SSE) ----
class RunEvent(BaseModel):
    seq: int = Field(ge=1)
    ts: AwareDatetime
    type: Literal["PLAN", "ACTION", "OBS", "SUMMARY"]
    message: str
    nodeId: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
