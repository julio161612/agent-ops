import { tokenStore } from "@/lib/api/tokenStore"
import type { ApiErrorBody, TokenResponse } from "@/lib/api/types"

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1"

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, message: string, detail: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

function extractErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as ApiErrorBody).detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join("; ")
    }
  }
  return fallback
}

// Ensures concurrent 401s trigger exactly one refresh call, not one per
// in-flight request — every caller awaits the same promise.
let refreshPromise: Promise<boolean> | null = null

async function performRefresh(): Promise<boolean> {
  const refreshToken = tokenStore.getRefreshToken()
  if (!refreshToken) return false

  try {
    const response = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!response.ok) return false
    const data: TokenResponse = await response.json()
    tokenStore.setTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  skipAuth?: boolean
  /** Internal: prevents infinite refresh-retry loops. */
  _isRetry?: boolean
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value))
      }
    }
  }
  return url.pathname + url.search
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, skipAuth, _isRetry } = options

  const headers: Record<string, string> = {}
  if (body !== undefined) headers["Content-Type"] = "application/json"
  if (!skipAuth) {
    const token = tokenStore.getAccessToken()
    if (token) headers["Authorization"] = `Bearer ${token}`
  }

  const response = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 401 && !skipAuth && !_isRetry) {
    const refreshed = await refreshSession()
    if (refreshed) {
      return apiRequest<T>(path, { ...options, _isRetry: true })
    }
    tokenStore.clear()
    tokenStore.notifyUnauthorized()
    throw new ApiError(401, "Sesión expirada", null)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const isJson = response.headers.get("content-type")?.includes("application/json")
  const data = isJson ? await response.json().catch(() => null) : null

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractErrorMessage(data, `Error ${response.status}`),
      data
    )
  }

  return data as T
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"]) =>
    apiRequest<T>(path, { method: "GET", query }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
}
