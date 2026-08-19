// Minimal token persistence + a tiny pub/sub so the AuthContext can react
// when the API client decides a session is no longer valid (refresh failed).
//
// Tokens live in localStorage, same trade-off every plain bearer-JWT SPA
// without a BFF makes: simple, but readable by any script on the page (XSS
// risk). A production version of this would put the refresh token behind an
// httpOnly cookie issued by a backend-for-frontend — out of scope for this
// phase, called out here and in the README rather than silently glossed over.

const ACCESS_TOKEN_KEY = "agentops_access_token"
const REFRESH_TOKEN_KEY = "agentops_refresh_token"

type Listener = () => void
const unauthorizedListeners = new Set<Listener>()

export const tokenStore = {
  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY)
  },
  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  },
  setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  },
  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },
  hasSession(): boolean {
    return Boolean(localStorage.getItem(ACCESS_TOKEN_KEY))
  },
  onUnauthorized(listener: Listener): () => void {
    unauthorizedListeners.add(listener)
    return () => unauthorizedListeners.delete(listener)
  },
  notifyUnauthorized(): void {
    for (const listener of unauthorizedListeners) listener()
  },
}
