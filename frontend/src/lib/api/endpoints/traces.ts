import { api } from "@/lib/api/client"
import type { InteractionTraceDetail, InteractionTracePage, TraceOutcome } from "@/lib/api/types"

export interface ListTracesParams {
  conversation_id?: string
  outcome?: TraceOutcome
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
  [key: string]: string | number | undefined
}

export const tracesApi = {
  list: (params?: ListTracesParams) => api.get<InteractionTracePage>("/traces", params),
  get: (id: string) => api.get<InteractionTraceDetail>(`/traces/${id}`),
}
