import { useNavigate, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, Route, ShieldAlert, Timer, DollarSign } from "lucide-react"
import { tracesApi } from "@/lib/api/endpoints/traces"
import { queryKeys } from "@/lib/queryKeys"
import { PageHeader } from "@/components/layout/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { ErrorState, PageLoading } from "@/components/ui/States"
import { formatCost, formatDateTime } from "@/lib/utils"
import type { TraceOutcome } from "@/lib/api/types"

const OUTCOME_LABELS: Record<TraceOutcome, string> = {
  completed: "Completada",
  blocked: "Bloqueada",
  escalated: "Escalada",
  unassigned: "Sin asignar",
}
const OUTCOME_VARIANTS: Record<TraceOutcome, "success" | "destructive" | "warning" | "outline"> = {
  completed: "success",
  blocked: "destructive",
  escalated: "warning",
  unassigned: "outline",
}

export function TraceDetailPage() {
  const { id = "" } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const traceQuery = useQuery({ queryKey: queryKeys.trace(id), queryFn: () => tracesApi.get(id) })

  if (traceQuery.isLoading) return <PageLoading />
  if (traceQuery.isError || !traceQuery.data) {
    return <ErrorState message="No se pudo cargar la traza" onRetry={() => traceQuery.refetch()} />
  }

  const trace = traceQuery.data
  const stages = Object.entries(trace.stage_latencies_ms)
  const maxStage = Math.max(1, ...stages.map(([, v]) => v))

  return (
    <div>
      <button
        onClick={() => navigate("/traces")}
        className="mb-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground cursor-pointer"
      >
        <ArrowLeft className="size-4" />
        Volver a trazas
      </button>

      <PageHeader
        title={`Traza ${trace.id.slice(0, 8)}…`}
        description={formatDateTime(trace.created_at)}
        actions={
          <Badge variant={OUTCOME_VARIANTS[trace.outcome]} dot>
            {OUTCOME_LABELS[trace.outcome]}
          </Badge>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <DollarSign className="size-3.5" />
            Coste total
          </div>
          <p className="mt-1 font-mono text-xl font-semibold">{formatCost(trace.cost_usd)}</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <Timer className="size-3.5" />
            Latencia total
          </div>
          <p className="mt-1 font-mono text-xl font-semibold">{trace.total_latency_ms} ms</p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            Tokens
          </div>
          <p className="mt-1 font-mono text-xl font-semibold">
            {trace.input_tokens} / {trace.output_tokens}
          </p>
          <p className="text-[11px] text-muted-foreground">entrada / salida</p>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Latencia por etapa</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {stages.length > 0 ? (
              stages.map(([stage, ms]) => (
                <div key={stage}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="capitalize text-muted-foreground">{stage.replace(/_/g, " ")}</span>
                    <span className="font-mono">{ms} ms</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${(ms / maxStage) * 100}%` }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Sin desglose por etapas.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Route className="size-4" />
              Decisión de routing
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trace.routing_decision ? (
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Método</dt>
                  <dd className="font-medium">
                    {trace.routing_decision.method === "rule" ? "Regla" : "LLM"}
                  </dd>
                </div>
                {trace.routing_decision.confidence !== null && (
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">Confianza</dt>
                    <dd className="font-mono">{(trace.routing_decision.confidence * 100).toFixed(0)}%</dd>
                  </div>
                )}
                {trace.routing_decision.reasoning && (
                  <div>
                    <dt className="text-muted-foreground">Razonamiento</dt>
                    <dd className="mt-1 rounded-md bg-muted p-2 text-xs">
                      {trace.routing_decision.reasoning}
                    </dd>
                  </div>
                )}
              </dl>
            ) : (
              <p className="text-sm text-muted-foreground">
                Este turno no pasó por el orquestador (agente fijado explícitamente).
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <ShieldAlert className="size-4" />
              Guardrails disparados
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trace.guardrail_violations.length > 0 ? (
              <div className="space-y-2">
                {trace.guardrail_violations.map((v) => (
                  <div
                    key={v.id}
                    className="flex items-start justify-between gap-3 rounded-md border border-border p-2.5 text-sm"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{v.guardrail_type}</Badge>
                        <Badge variant="outline">{v.violation_type}</Badge>
                        <Badge variant={v.action_taken === "block" ? "destructive" : "warning"}>
                          {v.action_taken === "block" ? "bloqueado" : "marcado"}
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{v.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Ningún guardrail se disparó en este turno.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
