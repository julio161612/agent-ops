import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { agentsApi } from "@/lib/api/endpoints/agents"
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
import type { AgentRead } from "@/lib/api/types"

const schema = z.object({
  name: z.string().min(1, "Obligatorio").max(255),
  description: z.string().max(2000).optional(),
  agent_type: z.string().max(100).optional(),
  system_prompt: z.string().min(1, "Obligatorio"),
  model: z.string().min(1).optional(),
  temperature: z.number().min(0).max(1),
  max_tokens: z.number().int().min(1).max(64000),
  is_active: z.boolean(),
})

type FormValues = z.infer<typeof schema>

const DEFAULT_MODEL = "claude-sonnet-4-6"

export function AgentFormDialog({
  open,
  onOpenChange,
  agent,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  agent?: AgentRead | null
}) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const isEditing = Boolean(agent)

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      description: "",
      agent_type: "",
      system_prompt: "",
      model: DEFAULT_MODEL,
      temperature: 0.7,
      max_tokens: 1024,
      is_active: true,
    },
  })

  React.useEffect(() => {
    if (open) {
      reset({
        name: agent?.name ?? "",
        description: agent?.description ?? "",
        agent_type: agent?.agent_type ?? "",
        system_prompt: agent?.system_prompt ?? "",
        model: agent?.model ?? DEFAULT_MODEL,
        temperature: agent?.parameters.temperature ?? 0.7,
        max_tokens: agent?.parameters.max_tokens ?? 1024,
        is_active: agent?.is_active ?? true,
      })
    }
  }, [open, agent, reset])

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      const payload = {
        name: values.name,
        description: values.description || null,
        agent_type: values.agent_type || null,
        system_prompt: values.system_prompt,
        model: values.model || null,
        parameters: { temperature: values.temperature, max_tokens: values.max_tokens },
        is_active: values.is_active,
      }
      return isEditing ? agentsApi.update(agent!.id, payload) : agentsApi.create(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents })
      toast({
        title: isEditing ? "Agente actualizado" : "Agente creado",
        variant: "success",
      })
      onOpenChange(false)
    },
    onError: (err) => {
      toast({
        title: "No se pudo guardar el agente",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Editar agente" : "Nuevo agente"}</DialogTitle>
          <DialogDescription>
            Define el comportamiento del agente con su prompt de sistema y parámetros del modelo.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={handleSubmit((values) => mutation.mutate(values))}
          className="space-y-4"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="name">Nombre</Label>
              <Input id="name" error={Boolean(errors.name)} {...register("name")} />
              {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="agent_type">Tipo (opcional)</Label>
              <Input id="agent_type" placeholder="support, sales, faq…" {...register("agent_type")} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="description">Descripción (opcional)</Label>
            <Input id="description" {...register("description")} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="system_prompt">Prompt de sistema</Label>
            <Textarea
              id="system_prompt"
              rows={8}
              className="font-mono text-xs"
              error={Boolean(errors.system_prompt)}
              {...register("system_prompt")}
            />
            {errors.system_prompt && (
              <p className="text-xs text-destructive">{errors.system_prompt.message}</p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="model">Modelo</Label>
              <Input id="model" {...register("model")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="temperature">Temperature (0–1)</Label>
              <Input
                id="temperature"
                type="number"
                step="0.1"
                min={0}
                max={1}
                error={Boolean(errors.temperature)}
                {...register("temperature", { valueAsNumber: true })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="max_tokens">Max tokens</Label>
              <Input
                id="max_tokens"
                type="number"
                min={1}
                max={64000}
                error={Boolean(errors.max_tokens)}
                {...register("max_tokens", { valueAsNumber: true })}
              />
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <Controller
              control={control}
              name="is_active"
              render={({ field }) => (
                <Switch id="is_active" checked={field.value} onCheckedChange={field.onChange} />
              )}
            />
            <Label htmlFor="is_active">Agente activo</Label>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={isSubmitting || mutation.isPending}>
              {isEditing ? "Guardar cambios" : "Crear agente"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
