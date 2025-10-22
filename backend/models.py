from typing import List, Literal, Optional, Union, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


# AwareDatetime 대용: Pydantic v2에서 timezone-aware로 직렬화
class AwareDatetime(datetime):
    @classmethod
    def now_kst(cls):
        # Asia/Seoul 고정(간단화). 운영에서는 zoneinfo 사용 권장.
        return datetime.now(timezone.utc).astimezone()


NodeType = Literal[
    "parse_pdf",
    "embed_pdf",
    "build_vectorstore",
    "merge_xlsx",
    "validate_with_pdf",
    "export_xlsx",
]

OutKey = Literal[
    "pdf_chunks",
    "pdf_embeddings",
    "vs_ref",
    "merged_table",
    "validation_report",
    "artifact_path",
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
    createdAt: datetime
    updatedAt: datetime


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
    ts: datetime
    type: Literal["PLAN", "ACTION", "OBS", "SUMMARY"]
    message: str
    nodeId: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
