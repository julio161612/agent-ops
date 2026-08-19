import { api } from "@/lib/api/client"
import type { ChangePlanRequest, SubscriptionWithPlanRead } from "@/lib/api/types"

export const subscriptionApi = {
  get: () => api.get<SubscriptionWithPlanRead>("/subscription"),
  changePlan: (payload: ChangePlanRequest) =>
    api.post<SubscriptionWithPlanRead>("/subscription/change-plan", payload),
}
