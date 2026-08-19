import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Sparkles, ShieldCheck } from "lucide-react"
import { agentTemplatesApi } from "@/lib/api/endpoints/agentTemplates"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { queryKeys } from "@/lib/queryKeys"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { ErrorState, InlineLoading } from "@/components/ui/States"
import { cn, truncate } from "@/lib/utils"
import type { AgentTemplateRead } from "@/lib/api/types"

export function AgentTemplatesDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [selected, setSelected] = React.useState<AgentTemplateRead | null>(null)

  const templatesQuery = useQuery({
    queryKey: queryKeys.agentTemplates,
    queryFn: () => agentTemplatesApi.list(),
    enabled: open,
  })

  const createMutation = useMutation({
    mutationFn: (templateId: string) =>
      agentsApi.createFromTemplate(templateId, { apply_recommended_guardrail: true }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents })
      queryClient.invalidateQueries({ queryKey: queryKeys.guardrailPolicies })
      toast({
        title: `Agente "${result.agent.name}" creado desde plantilla`,
        description: result.guardrail_policy
          ? "Se aplicó también el guardrail recomendado."
          : undefined,
        variant: "success",
      })
      onOpenChange(false)
      setSelected(null)
    },
    onError: (err) => {
      toast({
        title: "No se pudo crear el agente",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="xl">
        <DialogHeader>
          <DialogTitle>Crear agente desde plantilla</DialogTitle>
          <DialogDescription>
            Catálogo de casos de uso habituales, con parámetros y guardrail recomendado ya
            configurados.
          </DialogDescription>
        </DialogHeader>

        {templatesQuery.isLoading ? (
          <InlineLoading />
        ) : templatesQuery.isError || !templatesQuery.data ? (
          <ErrorState message="No se pudieron cargar las plantillas" onRetry={() => templatesQuery.refetch()} />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {templatesQuery.data.map((template) => {
              const isSelected = selected?.id === template.id
              return (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => setSelected(template)}
                  className={cn(
                    "flex flex-col gap-2 rounded-lg border p-4 text-left transition-colors cursor-pointer",
                    isSelected ? "border-accent ring-1 ring-accent" : "border-border hover:border-accent/50"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold">{template.name}</span>
                    <Badge variant="outline">{template.agent_type}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">{template.description}</p>
                  <p className="rounded-md bg-muted p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                    {truncate(template.system_prompt, isSelected ? 400 : 120)}
                  </p>
                  {template.recommended_guardrail && (
                    <div className="mt-1 flex items-start gap-1.5 text-[11px] text-muted-foreground">
                      <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-accent" />
                      <span>{template.recommended_guardrail.rationale}</span>
                    </div>
                  )}
                  {isSelected && (
                    <Button
                      className="mt-2 w-full"
                      size="sm"
                      loading={createMutation.isPending}
                      onClick={(e) => {
                        e.stopPropagation()
                        createMutation.mutate(template.id)
                      }}
                    >
                      <Sparkles className="size-3.5" />
                      Usar esta plantilla
                    </Button>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
