import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { routingRulesApi } from "@/lib/api/endpoints/routingRules"
import { queryKeys } from "@/lib/queryKeys"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import { Switch } from "@/components/ui/Switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import type { RoutingRuleRead, RoutingRuleType } from "@/lib/api/types"

interface FormState {
  agent_id: string
  rule_type: RoutingRuleType
  keywords: string
  agent_type: string
  priority: number
  is_active: boolean
}

function ruleToFormState(rule?: RoutingRuleRead | null): FormState {
  return {
    agent_id: rule?.agent_id ?? "",
    rule_type: rule?.rule_type ?? "keyword",
    keywords:
      rule?.rule_type === "keyword" && Array.isArray(rule.condition.keywords)
        ? (rule.condition.keywords as string[]).join(", ")
        : "",
    agent_type:
      rule?.rule_type === "category" && typeof rule.condition.agent_type === "string"
        ? rule.condition.agent_type
        : "",
    priority: rule?.priority ?? 0,
    is_active: rule?.is_active ?? true,
  }
}

export function RoutingRuleFormDialog({
  open,
  onOpenChange,
  rule,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  rule?: RoutingRuleRead | null
}) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const isEditing = Boolean(rule)

  const agentsQuery = useQuery({
    queryKey: queryKeys.agents,
    queryFn: () => agentsApi.list(),
    enabled: open,
  })

  const { control, register, handleSubmit, watch, reset } = useForm<FormState>({
    defaultValues: ruleToFormState(rule),
  })

  React.useEffect(() => {
    if (open) reset(ruleToFormState(rule))
  }, [open, rule, reset])

  const ruleType = watch("rule_type")

  const mutation = useMutation({
    mutationFn: (values: FormState) => {
      const condition =
        values.rule_type === "keyword"
          ? {
              keywords: values.keywords
                .split(",")
                .map((k) => k.trim())
                .filter(Boolean),
            }
          : { agent_type: values.agent_type.trim() }

      const payload = {
        agent_id: values.agent_id,
        rule_type: values.rule_type,
        condition,
        priority: Number(values.priority),
        is_active: values.is_active,
      }
      return isEditing ? routingRulesApi.update(rule!.id, payload) : routingRulesApi.create(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.routingRules })
      toast({ title: isEditing ? "Regla actualizada" : "Regla creada", variant: "success" })
      onOpenChange(false)
    },
    onError: (err) => {
      toast({
        title: "No se pudo guardar la regla",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Editar regla de routing" : "Nueva regla de routing"}</DialogTitle>
          <DialogDescription>
            Decide qué agente atiende un mensaje según palabras clave o el tipo de agente.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit((values) => mutation.mutate(values))} className="space-y-4">
          <div className="space-y-1.5">
            <Label>Agente al que enruta</Label>
            <Controller
              control={control}
              name="agent_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecciona un agente" />
                  </SelectTrigger>
                  <SelectContent>
                    {agentsQuery.data?.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Tipo de regla</Label>
            <Controller
              control={control}
              name="rule_type"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="keyword">Palabras clave</SelectItem>
                    <SelectItem value="category">Categoría de agente (fallback)</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          {ruleType === "keyword" ? (
            <div className="space-y-1.5">
              <Label htmlFor="keywords">Palabras clave (separadas por comas)</Label>
              <Input
                id="keywords"
                placeholder="factura, reembolso, devolución"
                {...register("keywords")}
              />
              <p className="text-xs text-muted-foreground">
                Coincide si el mensaje contiene alguna de estas palabras (sin distinguir mayúsculas).
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="agent_type">Tipo de agente</Label>
              <Input id="agent_type" placeholder="support" {...register("agent_type")} />
              <p className="text-xs text-muted-foreground">
                Actúa como fallback incondicional para agentes de este tipo.
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="priority">Prioridad</Label>
              <Input
                id="priority"
                type="number"
                {...register("priority", { valueAsNumber: true })}
              />
              <p className="text-xs text-muted-foreground">Mayor número gana en caso de empate.</p>
            </div>
            <div className="flex items-end pb-2">
              <div className="flex items-center gap-2.5">
                <Controller
                  control={control}
                  name="is_active"
                  render={({ field }) => (
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
                <Label>Regla activa</Label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {isEditing ? "Guardar cambios" : "Crear regla"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
