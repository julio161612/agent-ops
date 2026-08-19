import { api } from "@/lib/api/client"
import type { UserInvite, UserRead, UserRoleUpdate } from "@/lib/api/types"

export const usersApi = {
  list: () => api.get<UserRead[]>("/users"),
  invite: (payload: UserInvite) => api.post<UserRead>("/users", payload),
  updateRole: (id: string, payload: UserRoleUpdate) =>
    api.patch<UserRead>(`/users/${id}`, payload),
  deactivate: (id: string) => api.post<UserRead>(`/users/${id}/deactivate`),
}
