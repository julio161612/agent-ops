import * as React from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Bot, CheckCircle2, Send, Unlock, User as UserIcon, UserCheck } from "lucide-react"
import { escalationsApi } from "@/lib/api/endpoints/escalations"
import { conversationsApi } from "@/lib/api/endpoints/conversations"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { PageHeader } from "@/components/layout/PageHeader"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { Textarea } from "@/components/ui/Input"
import { ErrorState, PageLoading } from "@/components/ui/States"
import { cn, formatDateTime } from "@/lib/utils"
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

export function EscalationDetailPage() {
  const { id = "" } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user, hasRole } = useAuth()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const canManage = hasRole("operator")

  const [replyText, setReplyText] = React.useState("")
  const [resolutionNotes, setResolutionNotes] = React.useState("")

  const caseQuery = useQuery({
    queryKey: queryKeys.escalation(id),
    queryFn: () => escalationsApi.get(id),
  })

  const messagesQuery = useQuery({
    queryKey: ["conversation-messages", caseQuery.data?.conversation_id],
    queryFn: () => conversationsApi.listMessages(caseQuery.data!.conversation_id),
    enabled: Boolean(caseQuery.data),
  })

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: queryKeys.escalation(id) })
    queryClient.invalidateQueries({ queryKey: queryKeys.escalations(undefined) })
    queryClient.invalidateQueries({ queryKey: ["conversation-messages"] })
  }

  const claimMutation = useMutation({
    mutationFn: () => escalationsApi.claim(id),
    onSuccess: () => {
      invalidateAll()
      toast({ title: "Caso asignado a ti", variant: "success" })
    },
    onError: (err) =>
      toast({
        title: "No se pudo tomar el caso",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      }),
  })

  const respondMutation = useMutation({
    mutationFn: () => escalationsApi.respond(id, replyText.trim()),
    onSuccess: () => {
      invalidateAll()
      setReplyText("")
      toast({ title: "Respuesta enviada", variant: "success" })
    },
    onError: (err) =>
      toast({
        title: "No se pudo enviar la respuesta",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      }),
  })

  const resolveMutation = useMutation({
    mutationFn: () => escalationsApi.resolve(id, resolutionNotes.trim() || null),
    onSuccess: () => {
      invalidateAll()
      toast({ title: "Caso resuelto", variant: "success" })
    },
    onError: (err) =>
      toast({
        title: "No se pudo resolver el caso",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      }),
  })

  const releaseMutation = useMutation({
    mutationFn: () => escalationsApi.release(id),
    onSuccess: () => {
      invalidateAll()
      toast({ title: "Caso liberado", variant: "success" })
    },
  })

  if (caseQuery.isLoading) return <PageLoading />
  if (caseQuery.isError || !caseQuery.data) {
    return <ErrorState message="No se pudo cargar el caso" onRetry={() => caseQuery.refetch()} />
  }

  const escalationCase = caseQuery.data
  const isMine = escalationCase.assigned_to === user?.id

  return (
    <div>
      <button
        onClick={() => navigate("/escalations")}
        className="mb-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground cursor-pointer"
      >
        <ArrowLeft className="size-4" />
        Volver a escalados
      </button>

      <PageHeader
        title={`Caso ${escalationCase.id.slice(0, 8)}…`}
        description={`Conversación ${escalationCase.conversation_id.slice(0, 8)}… · creado ${formatDateTime(escalationCase.created_at)}`}
        actions={
          <>
            <Badge variant={STATUS_VARIANTS[escalationCase.status]} dot>
              {STATUS_LABELS[escalationCase.status]}
            </Badge>
            <Badge variant="outline">{REASON_LABELS[escalationCase.reason]}</Badge>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Historial de la conversación</CardTitle>
          </CardHeader>
          <CardContent>
            {messagesQuery.isLoading ? (
              <PageLoading />
            ) : (
              <div className="space-y-3">
                {messagesQuery.data?.map((m) => (
                  <div key={m.id} className={cn("flex gap-2", m.role === "user" && "flex-row-reverse")}>
                    <div
                      className={cn(
                        "flex size-6 shrink-0 items-center justify-center rounded-full",
                        m.role === "user" ? "bg-muted" : "bg-primary text-primary-foreground"
                      )}
                    >
                      {m.role === "user" ? (
                        <UserIcon className="size-3.5 text-muted-foreground" />
                      ) : (
                        <Bot className="size-3.5" />
                      )}
                    </div>
                    <div
                      className={cn(
                        "max-w-[80%] space-y-1 rounded-lg px-3 py-2 text-sm",
                        m.role === "user" ? "bg-muted" : "bg-accent/10"
                      )}
                    >
                      <p>{m.content}</p>
                      <p className="text-[10px] text-muted-foreground">{formatDateTime(m.created_at)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Acciones</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {!canManage ? (
                <p className="text-xs text-muted-foreground">
                  Necesitas rol operador o superior para gestionar escalados.
                </p>
              ) : escalationCase.status === "resolved" ? (
                <div className="flex items-center gap-2 text-sm text-success">
                  <CheckCircle2 className="size-4" />
                  Resuelto
                  {escalationCase.resolution_notes && (
                    <span className="text-muted-foreground">— {escalationCase.resolution_notes}</span>
                  )}
                </div>
              ) : escalationCase.status === "pending" ? (
                <Button className="w-full" loading={claimMutation.isPending} onClick={() => claimMutation.mutate()}>
                  <UserCheck className="size-4" />
                  Tomar caso
                </Button>
              ) : isMine ? (
                <>
                  <div className="space-y-1.5">
                    <Textarea
                      rows={3}
                      placeholder="Escribe la respuesta que verá el cliente…"
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                    />
                    <Button
                      size="sm"
                      className="w-full"
                      disabled={!replyText.trim()}
                      loading={respondMutation.isPending}
                      onClick={() => respondMutation.mutate()}
                    >
                      <Send className="size-3.5" />
                      Enviar respuesta
                    </Button>
                  </div>

                  <div className="space-y-1.5 border-t border-border pt-3">
                    <Textarea
                      rows={2}
                      placeholder="Notas de resolución (opcional)"
                      value={resolutionNotes}
                      onChange={(e) => setResolutionNotes(e.target.value)}
                    />
                    <Button
                      size="sm"
                      variant="secondary"
                      className="w-full"
                      loading={resolveMutation.isPending}
                      onClick={() => resolveMutation.mutate()}
                    >
                      <CheckCircle2 className="size-3.5" />
                      Resolver caso
                    </Button>
                  </div>

                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full"
                    loading={releaseMutation.isPending}
                    onClick={() => releaseMutation.mutate()}
                  >
                    <Unlock className="size-3.5" />
                    Liberar caso
                  </Button>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Este caso está asignado a otro miembro del equipo.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
