import { PageHeader } from "@/components/layout/PageHeader"
import { OnboardingCard } from "@/pages/settings/OnboardingCard"
import { TenantLimitsCard } from "@/pages/settings/TenantLimitsCard"

export function SettingsPage() {
  return (
    <div>
      <PageHeader
        title="Configuración"
        description="Estado de la configuración inicial del tenant y sus límites de uso."
      />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <OnboardingCard />
        <TenantLimitsCard />
      </div>
    </div>
  )
}
