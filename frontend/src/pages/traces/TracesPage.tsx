import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Activity } from "lucide-react"
import { tracesApi } from "@/lib/api/endpoints/traces"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { queryKeys } from "@/lib/queryKeys"
import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/Badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table"
import { Pagination } from "@/components/ui/Pagination"
import { EmptyState, ErrorState, PageLoading } from "@/components/ui/States"
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

const LIMIT = 25

export function TracesPage() {
  const navigate = useNavigate()
  const [outcomeFilter, setOutcomeFilter] = React.useState<TraceOutcome | "all">("all")
  const [agentFilter, setAgentFilter] = React.useState<string>("all")
  const [offset, setOffset] = React.useState(0)

  const agentsQuery = useQuery({ queryKey: queryKeys.agents, queryFn: () => agentsApi.list() })

  const tracesQuery = useQuery({
    queryKey: queryKeys.traces({ outcome: outcomeFilter, offset }),
    queryFn: () =>
      tracesApi.list({
        outcome: outcomeFilter === "all" ? undefined : outcomeFilter,
        limit: LIMIT,
        offset,
      }),
  })

  const agentName = (id: string | null) =>
    id ? agentsQuery.data?.find((a) => a.id === id)?.name ?? id.slice(0, 8) : "—"

  const filteredItems = React.useMemo(() => {
    const items = tracesQuery.data?.items ?? []
    return agentFilter === "all" ? items : items.filter((t) => t.agent_id === agentFilter)
  }, [tracesQuery.data, agentFilter])

  return (
    <div>
      <PageHeader
        title="Trazas"
        description="Un registro por cada interacción: routing, guardrails, coste y latencia."
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Select
          value={outcomeFilter}
          onValueChange={(v) => {
            setOutcomeFilter(v as typeof outcomeFilter)
            setOffset(0)
          }}
        >
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los resultados</SelectItem>
            <SelectItem value="completed">Completada</SelectItem>
            <SelectItem value="blocked">Bloqueada</SelectItem>
            <SelectItem value="escalated">Escalada</SelectItem>
            <SelectItem value="unassigned">Sin asignar</SelectItem>
          </SelectContent>
        </Select>

        <Select value={agentFilter} onValueChange={setAgentFilter}>
          <SelectTrigger className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los agentes</SelectItem>
            {agentsQuery.data?.map((agent) => (
              <SelectItem key={agent.id} value={agent.id}>
                {agent.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {tracesQuery.isLoading ? (
        <PageLoading />
      ) : tracesQuery.isError ? (
        <ErrorState message="No se pudieron cargar las trazas" onRetry={() => tracesQuery.refetch()} />
      ) : filteredItems.length > 0 ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Resultado</TableHead>
                <TableHead>Agente</TableHead>
                <TableHead>Coste</TableHead>
                <TableHead>Tokens</TableHead>
                <TableHead>Latencia</TableHead>
                <TableHead>Fecha</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredItems.map((trace) => (
                <TableRow key={trace.id} clickable onClick={() => navigate(`/traces/${trace.id}`)}>
                  <TableCell>
                    <Badge variant={OUTCOME_VARIANTS[trace.outcome]} dot>
                      {OUTCOME_LABELS[trace.outcome]}
                    </Badge>
                  </TableCell>
                  <TableCell>{agentName(trace.agent_id)}</TableCell>
                  <TableCell className="font-mono text-xs">{formatCost(trace.cost_usd)}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {trace.input_tokens + trace.output_tokens}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{trace.total_latency_ms} ms</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDateTime(trace.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination
            offset={offset}
            limit={LIMIT}
            total={tracesQuery.data?.total ?? 0}
            onOffsetChange={setOffset}
          />
        </>
      ) : (
        <EmptyState
          icon={Activity}
          title="Sin trazas todavía"
          description="Cada mensaje procesado por el sistema queda registrado aquí."
        />
      )}
    </div>
  )
}
