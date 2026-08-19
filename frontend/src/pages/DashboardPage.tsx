import { useQuery } from "@tanstack/react-query"
import { MessageSquare, CheckCircle2, ArrowUpRight, DollarSign, Timer } from "lucide-react"
import { metricsApi } from "@/lib/api/endpoints/metrics"
import { onboardingApi } from "@/lib/api/endpoints/onboarding"
import { queryKeys } from "@/lib/queryKeys"
import { PageHeader } from "@/components/layout/PageHeader"
import { StatCard } from "@/components/dashboard/StatCard"
import { InteractionsChart } from "@/components/dashboard/InteractionsChart"
import { OnboardingChecklist, OnboardingComplete } from "@/components/dashboard/OnboardingChecklist"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { ErrorState, InlineLoading, Skeleton } from "@/components/ui/States"
import { formatCost, formatNumber, formatPercent } from "@/lib/utils"

export function DashboardPage() {
  const summaryQuery = useQuery({
    queryKey: queryKeys.metricsSummary(undefined),
    queryFn: () => metricsApi.summary(),
  })
  const timeseriesQuery = useQuery({
    queryKey: queryKeys.metricsTimeseries({ granularity: "day" }),
    queryFn: () => metricsApi.timeseries({ granularity: "day" }),
  })
  const onboardingQuery = useQuery({
    queryKey: queryKeys.onboardingStatus,
    queryFn: () => onboardingApi.status(),
  })

  const summary = summaryQuery.data

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Resumen de actividad de los últimos 7 días"
      />

      {onboardingQuery.data &&
        (onboardingQuery.data.is_complete ? (
          <div className="mb-6">
            <OnboardingComplete />
          </div>
        ) : (
          <div className="mb-6">
            <OnboardingChecklist status={onboardingQuery.data} />
          </div>
        ))}

      {summaryQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[104px]" />
          ))}
        </div>
      ) : summaryQuery.isError || !summary ? (
        <ErrorState message="No se pudieron cargar las métricas" onRetry={() => summaryQuery.refetch()} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            icon={MessageSquare}
            label="Interacciones totales"
            value={formatNumber(summary.total_interactions)}
            hint={`${formatNumber(summary.completed)} completadas`}
          />
          <StatCard
            icon={CheckCircle2}
            label="Resolución automática"
            value={formatPercent(summary.auto_resolution_rate)}
            hint={`${formatPercent(summary.escalation_rate)} escaladas`}
            tone={summary.auto_resolution_rate >= 0.7 ? "success" : "warning"}
          />
          <StatCard
            icon={DollarSign}
            label="Coste del periodo"
            value={formatCost(summary.total_cost_usd)}
            hint="Llamadas reales a Anthropic"
          />
          <StatCard
            icon={Timer}
            label="Latencia media"
            value={summary.latency_ms_avg ? `${Math.round(summary.latency_ms_avg)} ms` : "—"}
            hint={summary.latency_ms_p95 ? `p95: ${Math.round(summary.latency_ms_p95)} ms` : undefined}
          />
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Interacciones a lo largo del tiempo</CardTitle>
            <CardDescription>Completadas, escaladas y bloqueadas por día</CardDescription>
          </CardHeader>
          <CardContent>
            {timeseriesQuery.isLoading ? (
              <InlineLoading />
            ) : timeseriesQuery.isError || !timeseriesQuery.data ? (
              <ErrorState message="No se pudo cargar el gráfico" onRetry={() => timeseriesQuery.refetch()} />
            ) : timeseriesQuery.data.buckets.length === 0 ? (
              <p className="py-16 text-center text-sm text-muted-foreground">
                Todavía no hay interacciones registradas en este periodo.
              </p>
            ) : (
              <InteractionsChart buckets={timeseriesQuery.data.buckets} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Uso por agente</CardTitle>
            <CardDescription>Interacciones y coste, últimos 7 días</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {summary && summary.agent_usage.length > 0 ? (
              summary.agent_usage
                .slice()
                .sort((a, b) => b.interaction_count - a.interaction_count)
                .map((stat) => (
                  <div
                    key={stat.agent_id ?? "unassigned"}
                    className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{stat.agent_name ?? "Sin asignar"}</p>
                      <p className="font-mono text-xs text-muted-foreground">{formatCost(stat.cost_usd)}</p>
                    </div>
                    <div className="flex items-center gap-1 text-sm font-medium">
                      {formatNumber(stat.interaction_count)}
                      <ArrowUpRight className="size-3.5 text-muted-foreground" />
                    </div>
                  </div>
                ))
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">Sin datos todavía.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
