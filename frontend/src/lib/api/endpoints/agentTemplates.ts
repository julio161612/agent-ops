import { api } from "@/lib/api/client"
import type { AgentTemplateRead } from "@/lib/api/types"

export const agentTemplatesApi = {
  list: () => api.get<AgentTemplateRead[]>("/agent-templates"),
}
