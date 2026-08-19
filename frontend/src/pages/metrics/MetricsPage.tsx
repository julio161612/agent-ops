import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { subDays } from "date-fns"
import { MessageSquare, CheckCircle2, DollarSign, Timer } from "lucide-react"
import { metricsApi } from "@/lib/api/endpoints/metrics"
import { queryKeys } from "@/lib/queryKeys"
import { PageHeader } from "@/components/layout/PageHeader"
import { StatCard } from "@/components/dashboard/StatCard"
import { InteractionsChart } from "@/components/dashboard/InteractionsChart"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table"
import { ErrorState, InlineLoading, PageLoading } from "@/components/ui/States"
import { formatCost, formatNumber, formatPercent } from "@/lib/utils"
import type { Granularity } from "@/lib/api/types"

const RANGE_OPTIONS = [
  { label: "Últimas 24h", days: 1 },
  { label: "Últimos 7 días", days: 7 },
  { label: "Últimos 30 días", days: 30 },
  { label: "Últimos 90 días", days: 90 },
]

export function MetricsPage() {
  const [rangeDays, setRangeDays] = React.useState(7)
  const [granularity, setGranularity] = React.useState<Granularity>("day")

  const dateRange = React.useMemo(() => {
    const now = new Date()
    return { date_from: subDays(now, rangeDays).toISOString(), date_to: now.toISOString() }
  }, [rangeDays])

  const summaryQuery = useQuery({
    queryKey: queryKeys.metricsSummary(dateRange),
    queryFn: () => metricsApi.summary(dateRange),
  })
  const timeseriesQuery = useQuery({
    queryKey: queryKeys.metricsTimeseries({ ...dateRange, granularity }),
    queryFn: () => metricsApi.timeseries({ ...dateRange, granularity }),
  })

  const summary = summaryQuery.data

  return (
    <div>
      <PageHeader
        title="Métricas"
        description="Explora el rendimiento del sistema por periodo: resolución, coste, latencia y guardrails."
        actions={
          <>
            <Select value={String(rangeDays)} onValueChange={(v) => setRangeDays(Number(v))}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RANGE_OPTIONS.map((r) => (
                  <SelectItem key={r.days} value={String(r.days)}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={granularity} onValueChange={(v) => setGranularity(v as Granularity)}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="hour">Por hora</SelectItem>
                <SelectItem value="day">Por día</SelectItem>
                <SelectItem value="week">Por semana</SelectItem>
                <SelectItem value="month">Por mes</SelectItem>
              </SelectContent>
            </Select>
          </>
        }
      />

      {summaryQuery.isLoading ? (
        <PageLoading />
      ) : summaryQuery.isError || !summary ? (
        <ErrorState message="No se pudieron cargar las métricas" onRetry={() => summaryQuery.refetch()} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={MessageSquare}
              label="Interacciones"
              value={formatNumber(summary.total_interactions)}
            />
            <StatCard
              icon={CheckCircle2}
              label="Resolución automática"
              value={formatPercent(summary.auto_resolution_rate)}
              tone={summary.auto_resolution_rate >= 0.7 ? "success" : "warning"}
            />
            <StatCard icon={DollarSign} label="Coste total" value={formatCost(summary.total_cost_usd)} />
            <StatCard
              icon={Timer}
              label="Latencia p95"
              value={summary.latency_ms_p95 ? `${Math.round(summary.latency_ms_p95)} ms` : "—"}
            />
          </div>

          <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Serie temporal</CardTitle>
                <CardDescription>Interacciones por resultado</CardDescription>
              </CardHeader>
              <CardContent>
                {timeseriesQuery.isLoading ? (
                  <InlineLoading />
                ) : timeseriesQuery.data && timeseriesQuery.data.buckets.length > 0 ? (
                  <InteractionsChart buckets={timeseriesQuery.data.buckets} />
                ) : (
                  <p className="py-16 text-center text-sm text-muted-foreground">Sin datos en este periodo.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Guardrails disparados</CardTitle>
                <CardDescription>Por tipo de violación</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {summary.guardrail_violations_by_type.length > 0 ? (
                  summary.guardrail_violations_by_type.map((g) => (
                    <div key={g.violation_type} className="flex items-center justify-between text-sm">
                      <span className="capitalize text-muted-foreground">
                        {g.violation_type.replace(/_/g, " ")}
                      </span>
                      <span className="font-mono font-medium">{g.violation_count}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">Sin violaciones en este periodo.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="mt-5">
            <CardHeader>
              <CardTitle>Uso por agente</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {summary.agent_usage.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Agente</TableHead>
                      <TableHead>Interacciones</TableHead>
                      <TableHead>Coste</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.agent_usage
                      .slice()
                      .sort((a, b) => b.interaction_count - a.interaction_count)
                      .map((stat) => (
                        <TableRow key={stat.agent_id ?? "unassigned"}>
                          <TableCell>{stat.agent_name ?? "Sin asignar"}</TableCell>
                          <TableCell className="font-mono text-xs">
                            {formatNumber(stat.interaction_count)}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{formatCost(stat.cost_usd)}</TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="p-5 text-center text-sm text-muted-foreground">Sin datos todavía.</p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
