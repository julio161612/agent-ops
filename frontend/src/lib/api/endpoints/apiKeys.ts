import { api } from "@/lib/api/client"
import type { ApiKeyCreate, ApiKeyCreateResponse, ApiKeyRead } from "@/lib/api/types"

export const apiKeysApi = {
  list: () => api.get<ApiKeyRead[]>("/api-keys"),
  create: (payload: ApiKeyCreate) => api.post<ApiKeyCreateResponse>("/api-keys", payload),
  revoke: (id: string) => api.delete<void>(`/api-keys/${id}`),
}
