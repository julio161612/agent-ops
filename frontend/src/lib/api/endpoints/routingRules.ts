import { api } from "@/lib/api/client"
import type {
  RoutingRuleCreate,
  RoutingRuleRead,
  RoutingRuleUpdate,
  RoutingValidateResponse,
} from "@/lib/api/types"

export const routingRulesApi = {
  list: () => api.get<RoutingRuleRead[]>("/routing-rules"),
  get: (id: string) => api.get<RoutingRuleRead>(`/routing-rules/${id}`),
  create: (payload: RoutingRuleCreate) => api.post<RoutingRuleRead>("/routing-rules", payload),
  update: (id: string, payload: RoutingRuleUpdate) =>
    api.patch<RoutingRuleRead>(`/routing-rules/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/routing-rules/${id}`),
  validate: (content: string) =>
    api.post<RoutingValidateResponse>("/routing-rules/validate", { content }),
}
