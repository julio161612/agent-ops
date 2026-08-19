import * as React from "react"
import { useMutation } from "@tanstack/react-query"
import { FlaskConical, Trophy } from "lucide-react"
import { routingRulesApi } from "@/lib/api/endpoints/routingRules"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { Badge } from "@/components/ui/Badge"
import { cn } from "@/lib/utils"
import type { RoutingValidateResponse } from "@/lib/api/types"

export function RoutingValidatorPanel() {
  const [content, setContent] = React.useState("")
  const [result, setResult] = React.useState<RoutingValidateResponse | null>(null)

  const mutation = useMutation({
    mutationFn: (text: string) => routingRulesApi.validate(text),
    onSuccess: (data) => setResult(data),
  })

  React.useEffect(() => {
    const trimmed = content.trim()
    if (!trimmed) {
      setResult(null)
      return
    }
    const handle = setTimeout(() => mutation.mutate(trimmed), 350)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <FlaskConical className="size-4" />
          Probador de routing
        </CardTitle>
        <CardDescription>
          Escribe un mensaje de ejemplo y comprueba en vivo qué agente lo atendería.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Ej: Quiero devolver un pedido que llegó roto"
        />

        {result && (
          <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
            {result.resulting_agent_name ? (
              <div className="flex items-center gap-2 text-sm">
                <Trophy className="size-4 text-accent" />
                <span>
                  Ganaría <span className="font-semibold">{result.resulting_agent_name}</span>
                </span>
              </div>
            ) : result.would_use_llm_router ? (
              <p className="text-sm text-muted-foreground">
                Ninguna regla coincide — se delegaría en el router por LLM.
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">No hay ningún agente configurado.</p>
            )}

            {result.matched_rules.length > 0 && (
              <ul className="space-y-1">
                {result.matched_rules
                  .slice()
                  .sort((a, b) => b.priority - a.priority)
                  .map((match) => (
                    <li
                      key={match.rule_id}
                      className={cn(
                        "flex items-center justify-between rounded-md px-2 py-1 text-xs",
                        match.would_win ? "bg-accent/10 text-accent" : "text-muted-foreground"
                      )}
                    >
                      <span>
                        {match.agent_name} · {match.rule_type} · prioridad {match.priority}
                      </span>
                      {match.would_win && <Badge variant="info">ganadora</Badge>}
                    </li>
                  ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
