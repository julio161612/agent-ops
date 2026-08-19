import { api } from "@/lib/api/client"
import type { MessageRead, SendMessageResponse } from "@/lib/api/types"

export const conversationsApi = {
  sendMessage: (conversationId: string, content: string, agentId?: string | null) =>
    api.post<SendMessageResponse>(`/conversations/${conversationId}/messages`, {
      content,
      agent_id: agentId ?? null,
    }),
  listMessages: (conversationId: string) =>
    api.get<MessageRead[]>(`/conversations/${conversationId}/messages`),
}
