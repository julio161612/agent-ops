import { api } from "@/lib/api/client"
import type { TenantLimitsRead, TenantLimitsUpdate } from "@/lib/api/types"

export const tenantLimitsApi = {
  get: () => api.get<TenantLimitsRead>("/tenant-limits"),
  update: (payload: TenantLimitsUpdate) => api.patch<TenantLimitsRead>("/tenant-limits", payload),
}
