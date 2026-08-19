import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, Circle } from "lucide-react"
import { onboardingApi } from "@/lib/api/endpoints/onboarding"
import { queryKeys } from "@/lib/queryKeys"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { ProgressBar } from "@/components/ui/ProgressBar"
import { ErrorState, PageLoading } from "@/components/ui/States"

const ITEM_LINKS: Record<string, string> = {
  agent_created: "/agents",
  routing_rule_created: "/routing-rules",
  guardrail_configured: "/guardrails",
  first_conversation: "/traces",
  tenant_limits_reviewed: "/settings",
}

export function OnboardingCard() {
  const statusQuery = useQuery({
    queryKey: queryKeys.onboardingStatus,
    queryFn: () => onboardingApi.status(),
  })

  if (statusQuery.isLoading) return <PageLoading />
  if (statusQuery.isError || !statusQuery.data) {
    return <ErrorState message="No se pudo cargar el onboarding" onRetry={() => statusQuery.refetch()} />
  }

  const status = statusQuery.data

  return (
    <Card>
      <CardHeader>
        <CardTitle>Progreso de configuración</CardTitle>
        <CardDescription>
          {status.completed_count} de {status.total_count} pasos completados
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ProgressBar value={status.completed_count} max={status.total_count} tone="success" />
        <div className="space-y-1">
          {status.items.map((item) => {
            const to = ITEM_LINKS[item.key] ?? "/settings"
            return (
              <Link
                key={item.key}
                to={to}
                className="flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted"
              >
                {item.done ? (
                  <CheckCircle2 className="size-4 shrink-0 text-success" />
                ) : (
                  <Circle className="size-4 shrink-0 text-muted-foreground" />
                )}
                <span className="flex-1">
                  <span className={item.done ? "text-muted-foreground line-through" : ""}>
                    {item.label}
                  </span>
                  <span className="block text-xs text-muted-foreground">{item.detail}</span>
                </span>
              </Link>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
