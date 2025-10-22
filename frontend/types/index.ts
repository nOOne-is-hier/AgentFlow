// API Response Types
export interface User {
  email: string
  emp_id: string
  name?: string
}

export interface LoginRequest {
  email: string
  emp_id: string
}

export interface LoginResponse {
  user: User
  session_id: string
}

// File Types
export interface FileInfo {
  file_id: string
  filename: string
  size: number
  uploaded_at: string
  file_type: "pdf" | "xlsx" | "artifact"
  is_artifact?: boolean
}

// Workflow Types
export interface WorkflowNode {
  id: string
  type: "parse_pdf" | "embed_pdf" | "merge_xlsx" | "validate" | "export" | "validate_with_pdf" | "export_xlsx"
  label: string
  config: Record<string, any>
  in: string[]
  out: string[]
  position?: { x: number; y: number }
}

export interface WorkflowEdge {
  id: string
  from: string
  to: string
}

export interface Workflow {
  id: string
  name: string
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  createdAt: string
  updatedAt: string
}

// SSE Event Types
export type EventType = "PLAN" | "ACTION" | "OBS" | "SUMMARY" | "ASSISTANT_REPLY" | "WAITING_HITL" | "ERROR"

export interface SSEEvent {
  id: string
  event: EventType
  data: {
    node_id?: string
    node_type?: string
    message?: string
    detail?: any
    __compact__?: boolean
    validation_report?: ValidationReport
    text?: string
    state?: any // For HITL checkpoint state
  }
  timestamp: string
}

// Validation Types
export interface ValidationItem {
  status: "ok" | "warn" | "fail"
  message: string
  evidence?: {
    page?: number
    snippet?: string
  }
}

export interface ValidationReport {
  summary?: {
    ok: number
    warn: number
    fail: number
  }
  items?: Array<{
    policy?: string
    dept?: string
    status: "ok" | "warn" | "fail"
    message?: string
    evidence?: Array<{
      page?: number
      snippet?: string
    }>
  }>
  exists_check?: ValidationItem[]
  sum_check?: ValidationItem[]
  overall_status?: "ok" | "warn" | "fail"
}

// HITL Types
export interface HITLRequest {
  approve: boolean
  comment?: string
}

// Chat Types
export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string
  timestamp: string
  event?: SSEEvent
}

export interface ChatTurnRequest {
  message: string
  fileIds?: string[]
}

export interface ChatTurnResponse {
  assistant: string
  tot: {
    steps: string[]
  }
  graphPatch: {
    addNodes: WorkflowNode[]
    addEdges: WorkflowEdge[]
  }
}

// Execute Pipeline Types
export interface ExecutePipelineRequest {
  workflowId: string
}

export interface ExecutePipelineResponse {
  runId: string
}
