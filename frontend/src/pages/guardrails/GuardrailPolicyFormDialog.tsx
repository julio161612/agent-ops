import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { guardrailPoliciesApi } from "@/lib/api/endpoints/guardrails"
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
import { Input, Textarea } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import { Switch } from "@/components/ui/Switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import type { GuardrailAction, GuardrailPolicyRead, GuardrailRuleType, GuardrailType, PiiPattern } from "@/lib/api/types"

const PII_PATTERNS: { value: PiiPattern; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "credit_card", label: "Tarjeta de crédito" },
  { value: "phone", label: "Teléfono" },
  { value: "spanish_dni", label: "DNI español" },
]

interface FormState {
  agent_id: string
  guardrail_type: GuardrailType
  rule_type: GuardrailRuleType
  action_on_violation: GuardrailAction
  is_active: boolean
  keywords: string
  pii_patterns: PiiPattern[]
  max_characters: number
  instruction: string
  model: string
}

function policyToFormState(policy?: GuardrailPolicyRead | null): FormState {
  const config = policy?.config ?? {}
  return {
    agent_id: policy?.agent_id ?? "__all__",
    guardrail_type: policy?.guardrail_type ?? "input",
    rule_type: policy?.rule_type ?? "blocklist_keywords",
    action_on_violation: policy?.action_on_violation ?? "block",
    is_active: policy?.is_active ?? true,
    keywords: Array.isArray(config.keywords) ? (config.keywords as string[]).join(", ") : "",
    pii_patterns: Array.isArray(config.patterns) ? (config.patterns as PiiPattern[]) : [],
    max_characters: typeof config.max_characters === "number" ? config.max_characters : 500,
    instruction: typeof config.instruction === "string" ? config.instruction : "",
    model: typeof config.model === "string" ? config.model : "",
  }
}

export function GuardrailPolicyFormDialog({
  open,
  onOpenChange,
  policy,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  policy?: GuardrailPolicyRead | null
}) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const isEditing = Boolean(policy)

  const agentsQuery = useQuery({
    queryKey: queryKeys.agents,
    queryFn: () => agentsApi.list(),
    enabled: open,
  })

  const { control, register, handleSubmit, watch, reset } = useForm<FormState>({
    defaultValues: policyToFormState(policy),
  })

  React.useEffect(() => {
    if (open) reset(policyToFormState(policy))
  }, [open, policy, reset])

  const ruleType = watch("rule_type")

  const mutation = useMutation({
    mutationFn: (values: FormState) => {
      let config: Record<string, unknown>
      switch (values.rule_type) {
        case "blocklist_keywords":
          config = {
            keywords: values.keywords
              .split(",")
              .map((k) => k.trim())
              .filter(Boolean),
          }
          break
        case "pii_detection":
          config = values.pii_patterns.length > 0 ? { patterns: values.pii_patterns } : {}
          break
        case "max_length":
          config = { max_characters: Number(values.max_characters) }
          break
        case "custom_llm_check":
          config = {
            instruction: values.instruction,
            ...(values.model ? { model: values.model } : {}),
          }
          break
      }
      const payload = {
        agent_id: values.agent_id === "__all__" ? null : values.agent_id,
        guardrail_type: values.guardrail_type,
        rule_type: values.rule_type,
        config,
        action_on_violation: values.action_on_violation,
        is_active: values.is_active,
      }
      return isEditing
        ? guardrailPoliciesApi.update(policy!.id, payload)
        : guardrailPoliciesApi.create(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrailPolicies })
      toast({ title: isEditing ? "Política actualizada" : "Política creada", variant: "success" })
      onOpenChange(false)
    },
    onError: (err) => {
      toast({
        title: "No se pudo guardar la política",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Editar guardrail" : "Nuevo guardrail"}</DialogTitle>
          <DialogDescription>
            Valida mensajes antes (input) o después (output) de ejecutar el agente.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit((values) => mutation.mutate(values))} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Se aplica a</Label>
              <Controller
                control={control}
                name="agent_id"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all__">Todos los agentes</SelectItem>
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
              <Label>Momento</Label>
              <Controller
                control={control}
                name="guardrail_type"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="input">Entrada (antes del agente)</SelectItem>
                      <SelectItem value="output">Salida (después del agente)</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
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
                    <SelectItem value="blocklist_keywords">Lista de palabras bloqueadas</SelectItem>
                    <SelectItem value="pii_detection">Detección de datos personales (PII)</SelectItem>
                    <SelectItem value="max_length">Longitud máxima</SelectItem>
                    <SelectItem value="custom_llm_check">Chequeo personalizado (LLM)</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          {ruleType === "blocklist_keywords" && (
            <div className="space-y-1.5">
              <Label htmlFor="keywords">Palabras bloqueadas (separadas por comas)</Label>
              <Input id="keywords" placeholder="palabrota1, palabrota2" {...register("keywords")} />
            </div>
          )}

          {ruleType === "pii_detection" && (
            <div className="space-y-1.5">
              <Label>Patrones a detectar (ninguno seleccionado = todos)</Label>
              <Controller
                control={control}
                name="pii_patterns"
                render={({ field }) => (
                  <div className="grid grid-cols-2 gap-2">
                    {PII_PATTERNS.map((p) => {
                      const checked = field.value.includes(p.value)
                      return (
                        <label
                          key={p.value}
                          className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) =>
                              field.onChange(
                                e.target.checked
                                  ? [...field.value, p.value]
                                  : field.value.filter((v) => v !== p.value)
                              )
                            }
                          />
                          {p.label}
                        </label>
                      )
                    })}
                  </div>
                )}
              />
            </div>
          )}

          {ruleType === "max_length" && (
            <div className="space-y-1.5">
              <Label htmlFor="max_characters">Longitud máxima (caracteres)</Label>
              <Input
                id="max_characters"
                type="number"
                min={1}
                {...register("max_characters", { valueAsNumber: true })}
              />
            </div>
          )}

          {ruleType === "custom_llm_check" && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="instruction">Instrucción para el juez</Label>
                <Textarea
                  id="instruction"
                  rows={3}
                  placeholder="Bloquea cualquier promesa de reembolso o descuento no autorizado."
                  {...register("instruction")}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="model">Modelo (opcional)</Label>
                <Input id="model" placeholder="claude-sonnet-4-6" {...register("model")} />
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Acción al violarse</Label>
              <Controller
                control={control}
                name="action_on_violation"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="block">Bloquear</SelectItem>
                      <SelectItem value="flag">Solo marcar (dejar pasar)</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
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
                <Label>Política activa</Label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {isEditing ? "Guardar cambios" : "Crear guardrail"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
