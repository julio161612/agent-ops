import { api } from "@/lib/api/client"
import type { SlackIntegrationRead, SlackTestResult } from "@/lib/api/types"

export const integrationsApi = {
  getSlack: () => api.get<SlackIntegrationRead>("/integrations/slack"),
  configureSlack: (webhookUrl: string) =>
    api.post<SlackIntegrationRead>("/integrations/slack", { webhook_url: webhookUrl }),
  testSlack: () => api.post<SlackTestResult>("/integrations/slack/test"),
}
