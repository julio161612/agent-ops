import { Navigate, Route, Routes } from "react-router-dom"
import { RequireAuth } from "@/components/layout/RequireAuth"
import { RequireRole } from "@/components/layout/RequireRole"
import { AppLayout } from "@/components/layout/AppLayout"
import { LoginPage } from "@/pages/auth/LoginPage"
import { RegisterPage } from "@/pages/auth/RegisterPage"
import { DashboardPage } from "@/pages/DashboardPage"
import { AgentsPage } from "@/pages/agents/AgentsPage"
import { RoutingRulesPage } from "@/pages/routing/RoutingRulesPage"
import { GuardrailsPage } from "@/pages/guardrails/GuardrailsPage"
import { EscalationsInboxPage } from "@/pages/escalations/EscalationsInboxPage"
import { EscalationDetailPage } from "@/pages/escalations/EscalationDetailPage"
import { TracesPage } from "@/pages/traces/TracesPage"
import { TraceDetailPage } from "@/pages/traces/TraceDetailPage"
import { MetricsPage } from "@/pages/metrics/MetricsPage"
import { BillingPage } from "@/pages/billing/BillingPage"
import { UsersPage } from "@/pages/users/UsersPage"
import { IntegrationsPage } from "@/pages/integrations/IntegrationsPage"
import { SettingsPage } from "@/pages/settings/SettingsPage"

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/routing-rules" element={<RoutingRulesPage />} />
          <Route path="/guardrails" element={<GuardrailsPage />} />
          <Route path="/escalations" element={<EscalationsInboxPage />} />
          <Route path="/escalations/:id" element={<EscalationDetailPage />} />
          <Route path="/traces" element={<TracesPage />} />
          <Route path="/traces/:id" element={<TraceDetailPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="/billing" element={<BillingPage />} />
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />

          <Route element={<RequireRole minimumRole="admin" />}>
            <Route path="/users" element={<UsersPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
