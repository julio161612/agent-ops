import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, ShieldAlert, Trash2 } from "lucide-react"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { guardrailPoliciesApi } from "@/lib/api/endpoints/guardrails"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { PageHeader } from "@/components/layout/PageHeader"
import { Card } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { Switch } from "@/components/ui/Switch"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { EmptyState, ErrorState, PageLoading } from "@/components/ui/States"
import { GuardrailPolicyFormDialog } from "@/pages/guardrails/GuardrailPolicyFormDialog"
import type { GuardrailPolicyRead } from "@/lib/api/types"

const RULE_TYPE_LABELS: Record<string, string> = {
  blocklist_keywords: "Palabras bloqueadas",
  pii_detection: "Detección de PII",
  max_length: "Longitud máxima",
  custom_llm_check: "Chequeo LLM personalizado",
}

function configSummary(policy: GuardrailPolicyRead): string {
  switch (policy.rule_type) {
    case "blocklist_keywords":
      return `Palabras: ${(policy.config.keywords as string[] | undefined)?.join(", ") ?? "—"}`
    case "pii_detection": {
      const patterns = policy.config.patterns as string[] | undefined
      return patterns && patterns.length > 0 ? `Patrones: ${patterns.join(", ")}` : "Todos los patrones"
    }
    case "max_length":
      return `Máximo ${policy.config.max_characters} caracteres`
    case "custom_llm_check":
      return String(policy.config.instruction ?? "")
    default:
      return ""
  }
}

export function GuardrailsPage() {
  const { hasRole } = useAuth()
  const canManage = hasRole("operator")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [formOpen, setFormOpen] = React.useState(false)
  const [editingPolicy, setEditingPolicy] = React.useState<GuardrailPolicyRead | null>(null)
  const [deletingPolicy, setDeletingPolicy] = React.useState<GuardrailPolicyRead | null>(null)

  const policiesQuery = useQuery({
    queryKey: queryKeys.guardrailPolicies,
    queryFn: () => guardrailPoliciesApi.list(),
  })
  const agentsQuery = useQuery({ queryKey: queryKeys.agents, queryFn: () => agentsApi.list() })

  const agentName = (id: string | null) =>
    id ? agentsQuery.data?.find((a) => a.id === id)?.name ?? "—" : "Todos los agentes"

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      guardrailPoliciesApi.update(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.guardrailPolicies }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => guardrailPoliciesApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrailPolicies })
      toast({ title: "Guardrail eliminado", variant: "success" })
      setDeletingPolicy(null)
    },
  })

  return (
    <div>
      <PageHeader
        title="Guardrails"
        description="Validan cada mensaje antes y después de que el agente responda: contenido, coste y comportamiento."
        actions={
          canManage ? (
            <Button
              onClick={() => {
                setEditingPolicy(null)
                setFormOpen(true)
              }}
            >
              <Plus className="size-4" />
              Nuevo guardrail
            </Button>
          ) : undefined
        }
      />

      {policiesQuery.isLoading ? (
        <PageLoading />
      ) : policiesQuery.isError ? (
        <ErrorState message="No se pudieron cargar los guardrails" onRetry={() => policiesQuery.refetch()} />
      ) : policiesQuery.data && policiesQuery.data.length > 0 ? (
        <div className="space-y-2">
          {policiesQuery.data.map((policy) => (
            <Card key={policy.id} className="flex items-center gap-3 p-3">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-warning-muted text-warning">
                <ShieldAlert className="size-4" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium">{agentName(policy.agent_id)}</p>
                  <Badge variant="outline">{policy.guardrail_type === "input" ? "entrada" : "salida"}</Badge>
                  <Badge variant="outline">{RULE_TYPE_LABELS[policy.rule_type]}</Badge>
                  <Badge variant={policy.action_on_violation === "block" ? "destructive" : "warning"}>
                    {policy.action_on_violation === "block" ? "bloquea" : "solo marca"}
                  </Badge>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{configSummary(policy)}</p>
              </div>

              {canManage && (
                <div className="flex shrink-0 items-center gap-2">
                  <Switch
                    checked={policy.is_active}
                    onCheckedChange={(checked) => toggleMutation.mutate({ id: policy.id, is_active: checked })}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => {
                      setEditingPolicy(policy)
                      setFormOpen(true)
                    }}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive hover:bg-destructive-muted"
                    onClick={() => setDeletingPolicy(policy)}
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
          icon={ShieldAlert}
          title="Sin guardrails configurados"
          description="Sin guardrails, los mensajes se procesan sin ninguna validación previa."
          action={
            canManage && (
              <Button size="sm" onClick={() => setFormOpen(true)}>
                Nuevo guardrail
              </Button>
            )
          }
        />
      )}

      <GuardrailPolicyFormDialog open={formOpen} onOpenChange={setFormOpen} policy={editingPolicy} />
      <ConfirmDialog
        open={Boolean(deletingPolicy)}
        onOpenChange={(o) => !o && setDeletingPolicy(null)}
        title="Eliminar guardrail"
        description="Los mensajes futuros dejarán de pasar por esta validación."
        confirmLabel="Eliminar"
        loading={deleteMutation.isPending}
        onConfirm={() => deletingPolicy && deleteMutation.mutate(deletingPolicy.id)}
      />
    </div>
  )
}
