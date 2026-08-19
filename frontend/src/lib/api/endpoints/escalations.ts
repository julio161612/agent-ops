import { api } from "@/lib/api/client"
import type {
  EscalationCaseRead,
  EscalationReason,
  EscalationRespondResponse,
  EscalationStatus,
} from "@/lib/api/types"

export const escalationsApi = {
  list: (params?: { status?: EscalationStatus; reason?: EscalationReason }) =>
    api.get<EscalationCaseRead[]>("/escalations", params),
  get: (id: string) => api.get<EscalationCaseRead>(`/escalations/${id}`),
  claim: (id: string) => api.post<EscalationCaseRead>(`/escalations/${id}/claim`),
  respond: (id: string, content: string) =>
    api.post<EscalationRespondResponse>(`/escalations/${id}/respond`, { content }),
  resolve: (id: string, notes?: string | null) =>
    api.post<EscalationCaseRead>(`/escalations/${id}/resolve`, { notes: notes ?? null }),
  release: (id: string) => api.post<EscalationCaseRead>(`/escalations/${id}/release`),
}
