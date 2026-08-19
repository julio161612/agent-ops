import * as React from "react"
import { useMutation } from "@tanstack/react-query"
import { Send, ShieldAlert, User, Bot as BotIcon } from "lucide-react"
import { agentsApi } from "@/lib/api/endpoints/agents"
import { ApiError } from "@/lib/api/client"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Badge } from "@/components/ui/Badge"
import { formatCost } from "@/lib/utils"
import type { AgentRead, AgentTestResponse } from "@/lib/api/types"

interface TurnResult {
  content: string
  response: AgentTestResponse
}

export function AgentTestDialog({
  open,
  onOpenChange,
  agent,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  agent: AgentRead | null
}) {
  const [input, setInput] = React.useState("")
  const [turns, setTurns] = React.useState<TurnResult[]>([])
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (open) {
      setTurns([])
      setInput("")
      setError(null)
    }
  }, [open, agent?.id])

  const mutation = useMutation({
    mutationFn: (content: string) => agentsApi.test(agent!.id, content),
    onSuccess: (response, content) => {
      setTurns((prev) => [...prev, { content, response }])
      setInput("")
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Error al probar el agente")
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || !agent) return
    setError(null)
    mutation.mutate(input.trim())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Probar «{agent?.name}»</DialogTitle>
          <DialogDescription>
            Modo de prueba: llamadas reales al modelo, pero nada se guarda en el historial ni en
            métricas.
          </DialogDescription>
        </DialogHeader>

        <div className="flex max-h-[50vh] flex-col gap-3 overflow-y-auto rounded-lg border border-border bg-muted/30 p-3 scrollbar-thin">
          {turns.length === 0 && !mutation.isPending && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Escribe un mensaje de prueba para ver cómo responde el agente.
            </p>
          )}
          {turns.map((turn, i) => (
            <TestTurn key={i} turn={turn} />
          ))}
          {mutation.isPending && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <BotIcon className="size-3.5 animate-pulse" />
              Pensando…
            </div>
          )}
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Escribe un mensaje de prueba…"
            disabled={mutation.isPending}
          />
          <Button type="submit" disabled={!input.trim()} loading={mutation.isPending}>
            <Send className="size-4" />
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function TestTurn({ turn }: { turn: TurnResult }) {
  const { response } = turn
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2">
        <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted">
          <User className="size-3.5 text-muted-foreground" />
        </div>
        <p className="rounded-lg bg-card px-3 py-2 text-sm shadow-sm">{turn.content}</p>
      </div>

      {response.input_guardrail_violations.length > 0 && (
        <GuardrailNote violations={response.input_guardrail_violations} stage="entrada" />
      )}

      {response.input_blocked ? (
        <div className="ml-8 rounded-lg border border-destructive/30 bg-destructive-muted px-3 py-2 text-xs text-destructive">
          Mensaje bloqueado antes de llegar al agente.
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <BotIcon className="size-3.5" />
          </div>
          <div className="max-w-[85%] space-y-1.5">
            <p className="rounded-lg bg-accent/10 px-3 py-2 text-sm">
              {response.output_blocked
                ? "(La respuesta del agente fue bloqueada por un guardrail de salida)"
                : response.reply}
            </p>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
              <Badge variant="outline" className="font-mono">
                {response.model}
              </Badge>
              <span>{response.input_tokens + response.output_tokens} tokens</span>
              <span>·</span>
              <span className="font-mono">{formatCost(response.cost_usd)}</span>
              <span>·</span>
              <span>{response.latency_ms} ms</span>
            </div>
          </div>
        </div>
      )}

      {response.output_guardrail_violations.length > 0 && (
        <GuardrailNote violations={response.output_guardrail_violations} stage="salida" />
      )}
    </div>
  )
}

function GuardrailNote({
  violations,
  stage,
}: {
  violations: AgentTestResponse["input_guardrail_violations"]
  stage: "entrada" | "salida"
}) {
  return (
    <div className="ml-8 space-y-1 rounded-lg border border-warning/30 bg-warning-muted px-3 py-2 text-xs text-warning">
      {violations.map((v, i) => (
        <div key={i} className="flex items-start gap-1.5">
          <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Guardrail de {stage} ({v.violation_type}, {v.action_taken}): {v.detail}
          </span>
        </div>
      ))}
    </div>
  )
}
