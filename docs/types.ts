// ===== Core Graph =====
export type NodeType =
  | "parse_pdf"
  | "embed_pdf"
  | "build_vectorstore"
  | "merge_xlsx"
  | "validate_with_pdf"
  | "export_xlsx";

export type OutKey =
  | "pdf_chunks"
  | "pdf_embeddings"
  | "vs_ref"
  | "merged_table"
  | "validation_report"
  | "artifact_path";

type BaseNode<T extends NodeType, C extends object> = {
  id: string;
  type: T;
  label: string;
  config: C;
  in: string[];     // e.g. ["parse_pdf.pdf_chunks"]
  out: OutKey[];    // e.g. ["pdf_chunks"]
};

export type Node =
  | BaseNode<"parse_pdf", { pdf_path: string; chunk_size: number; overlap: number }>
  | BaseNode<"embed_pdf", { chunks_in: string; model: "text-embedding-3-small" }>
  | BaseNode<"build_vectorstore", { embeddings_in: string; collection: string }>
  | BaseNode<"merge_xlsx", { xlsx_path?: string; xlsx_paths?: string[]; flatten: boolean; split: "by_department";}>
  | BaseNode<"validate_with_pdf", { table_in: string; vs_in: string; policies: Array<"exists" | "sum_check">; tolerance: number }>
  | BaseNode<"export_xlsx", { table_in: string; filename: string }>;

export type Edge = { from: string; to: string };

export type Workflow = {
  id: string;
  name: string;
  nodes: Node[];
  edges: Edge[];
  createdAt: string; // ISO8601
  updatedAt: string; // ISO8601
};

// ===== GraphPatch =====
export type GraphPatch = {
  addNodes?: Node[];
  addEdges?: Edge[];
  updateLabels?: Array<{ id: string; label: string }>;
  removeNodes?: string[];
  removeEdges?: Edge[];
};

// ===== Validation Report =====
export type ExistsItem = {
  policy: "exists";
  dept: string;
  status: "ok" | "miss";
  evidence?: Array<{ page: number; snippet: string }>;
};

export type SumCheckItem = {
  policy: "sum_check";
  dept: string;
  status: "ok" | "diff";
  expected: number;
  found: number;
  delta?: number; // optional; if present, usually found - expected
  evidence?: Array<{ page: number; snippet: string }>;
};

export type ValidationReport = {
  summary: { ok: number; warn: number; fail: number };
  items: Array<ExistsItem | SumCheckItem>;
};

// ===== Run Event (SSE) =====
export type RunEventType = "PLAN" | "ACTION" | "OBS" | "SUMMARY";

export type RunEvent = {
  seq: number;
  ts: string;              // ISO8601
  type: RunEventType;
  message: string;
  nodeId?: string;         // optional by design
  detail?: Record<string, unknown>;
};
