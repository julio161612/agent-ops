import { apiRequest } from "@/lib/api/client"
import type { MeResponse, TokenResponse } from "@/lib/api/types"

export interface RegisterPayload {
  company_name: string
  email: string
  password: string
}

export interface LoginPayload {
  email: string
  password: string
}

export const authApi = {
  register: (payload: RegisterPayload) =>
    apiRequest<TokenResponse>("/auth/register", { method: "POST", body: payload, skipAuth: true }),
  login: (payload: LoginPayload) =>
    apiRequest<TokenResponse>("/auth/login", { method: "POST", body: payload, skipAuth: true }),
  me: () => apiRequest<MeResponse>("/auth/me"),
}
