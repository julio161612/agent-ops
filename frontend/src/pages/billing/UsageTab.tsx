import { useQuery } from "@tanstack/react-query"
import { billingApi } from "@/lib/api/endpoints/billing"
import { queryKeys } from "@/lib/queryKeys"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { ProgressBar } from "@/components/ui/ProgressBar"
import { Badge } from "@/components/ui/Badge"
import { ErrorState, PageLoading } from "@/components/ui/States"
import { formatCost, formatNumber } from "@/lib/utils"

export function UsageTab() {
  const usageQuery = useQuery({
    queryKey: queryKeys.billingUsage,
    queryFn: () => billingApi.currentUsage(),
  })

  if (usageQuery.isLoading) return <PageLoading />
  if (usageQuery.isError || !usageQuery.data) {
    return <ErrorState message="No se pudo cargar el uso actual" onRetry={() => usageQuery.refetch()} />
  }

  const usage = usageQuery.data
  const messagesLimit = usage.included_messages
  const costLimit = usage.included_ai_cost_usd ? Number(usage.included_ai_cost_usd) : null

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Mensajes este mes</CardTitle>
          <CardDescription>
            Periodo {usage.period_month}/{usage.period_year} · plan {usage.plan.name}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-2xl font-semibold">{formatNumber(usage.messages_used)}</span>
            <span className="text-sm text-muted-foreground">
              {messagesLimit !== null ? `de ${formatNumber(messagesLimit)} incluidos` : "sin límite"}
            </span>
          </div>
          {messagesLimit !== null && <ProgressBar value={usage.messages_used} max={messagesLimit} />}
          {usage.overage_messages > 0 && (
            <div className="flex items-center justify-between rounded-md bg-warning-muted px-3 py-2 text-xs text-warning">
              <span>{formatNumber(usage.overage_messages)} mensajes de excedente</span>
              <span className="font-mono">{formatCost(usage.overage_cost_usd)}</span>
            </div>
          )}
          <Badge variant={usage.overage_enabled ? "info" : "outline"}>
            Overage {usage.overage_enabled ? "activado" : "desactivado"}
          </Badge>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Coste de IA este mes</CardTitle>
          <CardDescription>Gasto real en llamadas a Anthropic</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-2xl font-semibold">{formatCost(usage.ai_cost_usd)}</span>
            <span className="text-sm text-muted-foreground">
              {costLimit !== null ? `de ${formatCost(costLimit)} incluidos` : "sin límite"}
            </span>
          </div>
          {costLimit !== null && <ProgressBar value={Number(usage.ai_cost_usd)} max={costLimit} />}
        </CardContent>
      </Card>
    </div>
  )
}
