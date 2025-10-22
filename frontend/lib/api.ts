import type {
  LoginRequest,
  LoginResponse,
  FileInfo,
  Workflow,
  ChatTurnRequest,
  ChatTurnResponse,
  HITLRequest,
  ExecutePipelineResponse,
} from "@/types"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

class APIError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = "APIError"
  }
}

async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.text()
    throw new APIError(response.status, error || response.statusText)
  }

  return response.json()
}

interface FilesResponse {
  files: Array<{
    id: string
    name: string
    type: string
    size: number
    path: string
    uploadedAt: string
  }>
}

export const api = {
  // Auth
  login: (data: LoginRequest) =>
    fetchAPI<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  logout: () =>
    fetchAPI<void>("/auth/logout", {
      method: "POST",
    }),

  // Files
  uploadFile: async (file: File): Promise<FileInfo> => {
    const formData = new FormData()
    formData.append("files", file)

    const response = await fetch(`${API_BASE}/files/upload`, {
      method: "POST",
      credentials: "include",
      body: formData,
    })

    if (!response.ok) {
      throw new APIError(response.status, await response.text())
    }

    const result = (await response.json()) as FilesResponse
    const uploadedFile = result.files[0]

    return {
      file_id: uploadedFile.id,
      filename: uploadedFile.name,
      file_type: uploadedFile.type as "pdf" | "xlsx" | "artifact",
      size: uploadedFile.size,
      uploaded_at: uploadedFile.uploadedAt,
      is_artifact: false,
    }
  },

  getFiles: async (): Promise<FileInfo[]> => {
    const response = await fetchAPI<FilesResponse>("/files")
    return response.files.map((file) => ({
      file_id: file.id,
      filename: file.name,
      file_type: file.type as "pdf" | "xlsx" | "artifact",
      size: file.size,
      uploaded_at: file.uploadedAt,
      is_artifact: false, // Backend doesn't provide this yet
    }))
  },

  downloadFile: (fileId: string) => `${API_BASE}/files/${fileId}/download`,

  // Workflows
  getWorkflows: () => fetchAPI<Workflow[]>("/workflows"),

  saveWorkflow: (workflow: Workflow) =>
    fetchAPI<{ id: string }>("/workflows", {
      method: "POST",
      body: JSON.stringify(workflow),
    }),

  // Chat
  chatTurn: (data: ChatTurnRequest) =>
    fetchAPI<ChatTurnResponse>("/chat/turn", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Pipeline
  executePipeline: (workflowId: string) => {
    console.log("[v0] executePipeline called with workflowId:", workflowId)
    const body = { workflowId }
    console.log("[v0] Request body:", body)

    return fetchAPI<ExecutePipelineResponse>("/pipeline/execute", {
      method: "POST",
      body: JSON.stringify(body),
    })
  },

  // SSE Events
  getEventStream: (runId: string) => `${API_BASE}/runs/${runId}/events?engine=lg`,

  // HITL
  continueRun: (runId: string, data: HITLRequest) =>
    fetchAPI<{ status: string }>(`/runs/${runId}/continue`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Artifacts
  downloadArtifact: (artifactId: string) => `${API_BASE}/artifacts/${artifactId}`,
}
