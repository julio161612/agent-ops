import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bot, LayoutGrid, MessageSquareText, Pencil, Plus, Trash2 } from "lucide-react"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { PageHeader } from "@/components/layout/PageHeader"
import { Card } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { EmptyState, ErrorState, PageLoading } from "@/components/ui/States"
import { AgentFormDialog } from "@/pages/agents/AgentFormDialog"
import { AgentTemplatesDialog } from "@/pages/agents/AgentTemplatesDialog"
import { AgentTestDialog } from "@/pages/agents/AgentTestDialog"
import { formatDate } from "@/lib/utils"
import type { AgentRead } from "@/lib/api/types"

export function AgentsPage() {
  const { hasRole } = useAuth()
  const canManage = hasRole("operator")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [formOpen, setFormOpen] = React.useState(false)
  const [templatesOpen, setTemplatesOpen] = React.useState(false)
  const [testAgent, setTestAgent] = React.useState<AgentRead | null>(null)
  const [editingAgent, setEditingAgent] = React.useState<AgentRead | null>(null)
  const [deletingAgent, setDeletingAgent] = React.useState<AgentRead | null>(null)

  const agentsQuery = useQuery({ queryKey: queryKeys.agents, queryFn: () => agentsApi.list() })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => agentsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents })
      toast({ title: "Agente eliminado", variant: "success" })
      setDeletingAgent(null)
    },
    onError: (err) => {
      toast({
        title: "No se pudo eliminar",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  function openCreate() {
    setEditingAgent(null)
    setFormOpen(true)
  }

  function openEdit(agent: AgentRead) {
    setEditingAgent(agent)
    setFormOpen(true)
  }

  return (
    <div>
      <PageHeader
        title="Agentes"
        description="Unidades de IA configurables por tenant, cada una con su propio prompt y parámetros."
        actions={
          canManage ? (
            <>
              <Button variant="outline" onClick={() => setTemplatesOpen(true)}>
                <LayoutGrid className="size-4" />
                Desde plantilla
              </Button>
              <Button onClick={openCreate}>
                <Plus className="size-4" />
                Nuevo agente
              </Button>
            </>
          ) : undefined
        }
      />

      {agentsQuery.isLoading ? (
        <PageLoading />
      ) : agentsQuery.isError ? (
        <ErrorState message="No se pudieron cargar los agentes" onRetry={() => agentsQuery.refetch()} />
      ) : agentsQuery.data && agentsQuery.data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agentsQuery.data.map((agent) => (
            <Card key={agent.id} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/5 text-primary">
                    <Bot className="size-4.5" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold leading-tight">{agent.name}</p>
                    {agent.agent_type && (
                      <p className="text-xs text-muted-foreground">{agent.agent_type}</p>
                    )}
                  </div>
                </div>
                <Badge variant={agent.is_active ? "success" : "outline"} dot>
                  {agent.is_active ? "activo" : "inactivo"}
                </Badge>
              </div>

              {agent.description && (
                <p className="mt-3 text-xs text-muted-foreground line-clamp-2">{agent.description}</p>
              )}

              <p className="mt-3 line-clamp-3 rounded-md bg-muted p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                {agent.system_prompt}
              </p>

              <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
                <Badge variant="outline" className="font-mono">
                  {agent.model}
                </Badge>
                <span>Creado {formatDate(agent.created_at)}</span>
              </div>

              <div className="mt-4 flex items-center gap-2 border-t border-border pt-3">
                <Button variant="outline" size="sm" onClick={() => setTestAgent(agent)}>
                  <MessageSquareText className="size-3.5" />
                  Probar
                </Button>
                {canManage && (
                  <>
                    <Button variant="ghost" size="sm" onClick={() => openEdit(agent)}>
                      <Pencil className="size-3.5" />
                      Editar
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-auto text-destructive hover:bg-destructive-muted"
                      onClick={() => setDeletingAgent(agent)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </>
                )}
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Bot}
          title="Todavía no hay agentes"
          description="Crea tu primer agente desde cero o parte de una plantilla."
          action={
            canManage && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setTemplatesOpen(true)}>
                  Desde plantilla
                </Button>
                <Button size="sm" onClick={openCreate}>
                  Nuevo agente
                </Button>
              </div>
            )
          }
        />
      )}

      <AgentFormDialog open={formOpen} onOpenChange={setFormOpen} agent={editingAgent} />
      <AgentTemplatesDialog open={templatesOpen} onOpenChange={setTemplatesOpen} />
      <AgentTestDialog open={Boolean(testAgent)} onOpenChange={(o) => !o && setTestAgent(null)} agent={testAgent} />
      <ConfirmDialog
        open={Boolean(deletingAgent)}
        onOpenChange={(o) => !o && setDeletingAgent(null)}
        title={`Eliminar «${deletingAgent?.name}»`}
        description="El agente dejará de estar disponible para routing y conversaciones nuevas. Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        loading={deleteMutation.isPending}
        onConfirm={() => deletingAgent && deleteMutation.mutate(deletingAgent.id)}
      />
    </div>
  )
}
