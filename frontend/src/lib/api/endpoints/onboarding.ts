import { api } from "@/lib/api/client"
import type { OnboardingStatusRead } from "@/lib/api/types"

export const onboardingApi = {
  status: () => api.get<OnboardingStatusRead>("/onboarding/status"),
}
