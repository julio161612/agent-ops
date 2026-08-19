import { api } from "@/lib/api/client"
import type {
  GuardrailPolicyCreate,
  GuardrailPolicyRead,
  GuardrailPolicyUpdate,
  GuardrailViolationRead,
} from "@/lib/api/types"

export const guardrailPoliciesApi = {
  list: () => api.get<GuardrailPolicyRead[]>("/guardrail-policies"),
  get: (id: string) => api.get<GuardrailPolicyRead>(`/guardrail-policies/${id}`),
  create: (payload: GuardrailPolicyCreate) =>
    api.post<GuardrailPolicyRead>("/guardrail-policies", payload),
  update: (id: string, payload: GuardrailPolicyUpdate) =>
    api.patch<GuardrailPolicyRead>(`/guardrail-policies/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/guardrail-policies/${id}`),
}

export const guardrailViolationsApi = {
  list: (params?: { conversation_id?: string }) =>
    api.get<GuardrailViolationRead[]>("/guardrail-violations", params),
}
