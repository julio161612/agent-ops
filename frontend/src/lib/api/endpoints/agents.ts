import { api } from "@/lib/api/client"
import type {
  AgentCreate,
  AgentRead,
  AgentTestResponse,
  AgentUpdate,
  CreateAgentFromTemplateRequest,
  CreateAgentFromTemplateResponse,
} from "@/lib/api/types"

export const agentsApi = {
  list: () => api.get<AgentRead[]>("/agents"),
  get: (id: string) => api.get<AgentRead>(`/agents/${id}`),
  create: (payload: AgentCreate) => api.post<AgentRead>("/agents", payload),
  update: (id: string, payload: AgentUpdate) => api.patch<AgentRead>(`/agents/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/agents/${id}`),
  test: (id: string, content: string) =>
    api.post<AgentTestResponse>(`/agents/${id}/test`, { content }),
  createFromTemplate: (templateId: string, payload: CreateAgentFromTemplateRequest) =>
    api.post<CreateAgentFromTemplateResponse>(`/agents/from-template/${templateId}`, payload),
}
