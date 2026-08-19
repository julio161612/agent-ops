import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Inbox, User } from "lucide-react"
import { escalationsApi } from "@/lib/api/endpoints/escalations"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { PageHeader } from "@/components/layout/PageHeader"
import { Card } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import { EmptyState, ErrorState, PageLoading } from "@/components/ui/States"
import { formatRelativeTime } from "@/lib/utils"
import type { EscalationReason, EscalationStatus } from "@/lib/api/types"

const STATUS_LABELS: Record<EscalationStatus, string> = {
  pending: "Pendiente",
  in_progress: "En curso",
  resolved: "Resuelto",
}

const STATUS_VARIANTS: Record<EscalationStatus, "warning" | "info" | "success"> = {
  pending: "warning",
  in_progress: "info",
  resolved: "success",
}

const REASON_LABELS: Record<EscalationReason, string> = {
  unassigned_routing: "Sin agente confiable",
  guardrail_blocked: "Respuesta bloqueada",
  manual: "Manual",
}

export function EscalationsInboxPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [statusFilter, setStatusFilter] = React.useState<EscalationStatus | "all">("pending")
  const [reasonFilter, setReasonFilter] = React.useState<EscalationReason | "all">("all")

  const casesQuery = useQuery({
    queryKey: queryKeys.escalations({ status: statusFilter, reason: reasonFilter }),
    queryFn: () =>
      escalationsApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        reason: reasonFilter === "all" ? undefined : reasonFilter,
      }),
  })

  return (
    <div>
      <PageHeader
        title="Escalados"
        description="Casos que ningún agente pudo resolver con suficiente confianza."
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los estados</SelectItem>
            <SelectItem value="pending">Pendiente</SelectItem>
            <SelectItem value="in_progress">En curso</SelectItem>
            <SelectItem value="resolved">Resuelto</SelectItem>
          </SelectContent>
        </Select>

        <Select value={reasonFilter} onValueChange={(v) => setReasonFilter(v as typeof reasonFilter)}>
          <SelectTrigger className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los motivos</SelectItem>
            <SelectItem value="unassigned_routing">Sin agente confiable</SelectItem>
            <SelectItem value="guardrail_blocked">Respuesta bloqueada</SelectItem>
            <SelectItem value="manual">Manual</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {casesQuery.isLoading ? (
        <PageLoading />
      ) : casesQuery.isError ? (
        <ErrorState message="No se pudieron cargar los escalados" onRetry={() => casesQuery.refetch()} />
      ) : casesQuery.data && casesQuery.data.length > 0 ? (
        <div className="space-y-2">
          {casesQuery.data
            .slice()
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
            .map((c) => (
              <Card
                key={c.id}
                className="flex cursor-pointer items-center gap-3 p-3 transition-colors hover:border-accent/40"
                onClick={() => navigate(`/escalations/${c.id}`)}
              >
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/5 text-primary">
                  <Inbox className="size-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={STATUS_VARIANTS[c.status]} dot>
                      {STATUS_LABELS[c.status]}
                    </Badge>
                    <Badge variant="outline">{REASON_LABELS[c.reason]}</Badge>
                    {c.assigned_to && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <User className="size-3" />
                        {c.assigned_to === user?.id ? "Tú" : "Otro miembro del equipo"}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                    conversación {c.conversation_id.slice(0, 8)}…
                  </p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {formatRelativeTime(c.created_at)}
                </span>
              </Card>
            ))}
        </div>
      ) : (
        <EmptyState
          icon={Inbox}
          title="Sin casos escalados"
          description="Cuando el routing no encuentre un agente con suficiente confianza, o un guardrail bloquee una respuesta, el caso aparecerá aquí."
        />
      )}
    </div>
  )
}
