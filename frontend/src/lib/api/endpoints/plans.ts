import { api } from "@/lib/api/client"
import type { PlanRead } from "@/lib/api/types"

export const plansApi = {
  list: () => api.get<PlanRead[]>("/plans"),
}
