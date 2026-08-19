import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Pencil, Plus, Route, Trash2 } from "lucide-react"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { routingRulesApi } from "@/lib/api/endpoints/routingRules"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { PageHeader } from "@/components/layout/PageHeader"
import { Card } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { Switch } from "@/components/ui/Switch"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { EmptyState, ErrorState, PageLoading } from "@/components/ui/States"
import { RoutingRuleFormDialog } from "@/pages/routing/RoutingRuleFormDialog"
import { RoutingValidatorPanel } from "@/pages/routing/RoutingValidatorPanel"
import type { RoutingRuleRead } from "@/lib/api/types"

export function RoutingRulesPage() {
  const { hasRole } = useAuth()
  const canManage = hasRole("operator")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [formOpen, setFormOpen] = React.useState(false)
  const [editingRule, setEditingRule] = React.useState<RoutingRuleRead | null>(null)
  const [deletingRule, setDeletingRule] = React.useState<RoutingRuleRead | null>(null)

  const rulesQuery = useQuery({
    queryKey: queryKeys.routingRules,
    queryFn: () => routingRulesApi.list(),
  })
  const agentsQuery = useQuery({ queryKey: queryKeys.agents, queryFn: () => agentsApi.list() })

  const agentName = (id: string) => agentsQuery.data?.find((a) => a.id === id)?.name ?? "—"

  const updateMutation = useMutation({
    mutationFn: ({ id, priority }: { id: string; priority: number }) =>
      routingRulesApi.update(id, { priority }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.routingRules }),
    onError: (err) => {
      toast({
        title: "No se pudo cambiar la prioridad",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      routingRulesApi.update(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.routingRules }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => routingRulesApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.routingRules })
      toast({ title: "Regla eliminada", variant: "success" })
      setDeletingRule(null)
    },
  })

  const sortedRules = React.useMemo(
    () => (rulesQuery.data ?? []).slice().sort((a, b) => b.priority - a.priority),
    [rulesQuery.data]
  )

  function move(rule: RoutingRuleRead, direction: "up" | "down") {
    const index = sortedRules.findIndex((r) => r.id === rule.id)
    const neighbor = direction === "up" ? sortedRules[index - 1] : sortedRules[index + 1]
    if (!neighbor) return
    updateMutation.mutate({ id: rule.id, priority: neighbor.priority + (direction === "up" ? 1 : -1) })
  }

  return (
    <div>
      <PageHeader
        title="Reglas de routing"
        description="Deciden qué agente atiende cada mensaje entrante, por prioridad. Sin coincidencias, decide el router por LLM."
        actions={
          canManage ? (
            <Button
              onClick={() => {
                setEditingRule(null)
                setFormOpen(true)
              }}
            >
              <Plus className="size-4" />
              Nueva regla
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {rulesQuery.isLoading ? (
            <PageLoading />
          ) : rulesQuery.isError ? (
            <ErrorState message="No se pudieron cargar las reglas" onRetry={() => rulesQuery.refetch()} />
          ) : sortedRules.length > 0 ? (
            <div className="space-y-2">
              {sortedRules.map((rule, i) => (
                <Card key={rule.id} className="flex items-center gap-3 p-3">
                  <div className="flex flex-col">
                    <button
                      className="text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer disabled:cursor-not-allowed"
                      disabled={!canManage || i === 0}
                      onClick={() => move(rule, "up")}
                    >
                      <ArrowUp className="size-3.5" />
                    </button>
                    <button
                      className="text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer disabled:cursor-not-allowed"
                      disabled={!canManage || i === sortedRules.length - 1}
                      onClick={() => move(rule, "down")}
                    >
                      <ArrowDown className="size-3.5" />
                    </button>
                  </div>

                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/5 text-primary">
                    <Route className="size-4" />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">{agentName(rule.agent_id)}</p>
                      <Badge variant="outline">{rule.rule_type}</Badge>
                      <Badge variant="outline" className="font-mono">
                        prioridad {rule.priority}
                      </Badge>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {rule.rule_type === "keyword"
                        ? `Palabras: ${(rule.condition.keywords as string[] | undefined)?.join(", ") ?? "—"}`
                        : `Tipo de agente: ${rule.condition.agent_type ?? "—"}`}
                    </p>
                  </div>

                  {canManage && (
                    <div className="flex shrink-0 items-center gap-2">
                      <Switch
                        checked={rule.is_active}
                        onCheckedChange={(checked) =>
                          toggleMutation.mutate({ id: rule.id, is_active: checked })
                        }
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          setEditingRule(rule)
                          setFormOpen(true)
                        }}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:bg-destructive-muted"
                        onClick={() => setDeletingRule(rule)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Route}
              title="Sin reglas de routing todavía"
              description="Sin reglas, cada mensaje se enruta con el router por LLM."
              action={
                canManage && (
                  <Button size="sm" onClick={() => setFormOpen(true)}>
                    Nueva regla
                  </Button>
                )
              }
            />
          )}
        </div>

        <div>
          <RoutingValidatorPanel />
        </div>
      </div>

      <RoutingRuleFormDialog open={formOpen} onOpenChange={setFormOpen} rule={editingRule} />
      <ConfirmDialog
        open={Boolean(deletingRule)}
        onOpenChange={(o) => !o && setDeletingRule(null)}
        title="Eliminar regla de routing"
        description="Los mensajes que coincidían con esta regla pasarán a evaluarse por las siguientes reglas o por el router por LLM."
        confirmLabel="Eliminar"
        loading={deleteMutation.isPending}
        onConfirm={() => deletingRule && deleteMutation.mutate(deletingRule.id)}
      />
    </div>
  )
}
