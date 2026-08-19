import { Link } from "react-router-dom"
import { CheckCircle2, Circle, PartyPopper } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card"
import type { OnboardingStatusRead } from "@/lib/api/types"

const ITEM_LINKS: Record<string, string> = {
  agent_created: "/agents",
  routing_rule_created: "/routing-rules",
  guardrail_configured: "/guardrails",
  first_conversation: "/traces",
  tenant_limits_reviewed: "/settings",
}

export function OnboardingChecklist({ status }: { status: OnboardingStatusRead }) {
  if (status.is_complete) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Primeros pasos</CardTitle>
        <CardDescription>
          {status.completed_count} de {status.total_count} completados — termina de configurar tu
          tenant
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        {status.items.map((item) => {
          const to = ITEM_LINKS[item.key] ?? "/settings"
          return (
            <Link
              key={item.key}
              to={to}
              className="flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted"
            >
              {item.done ? (
                <CheckCircle2 className="size-4 shrink-0 text-success" />
              ) : (
                <Circle className="size-4 shrink-0 text-muted-foreground" />
              )}
              <span className="flex-1">
                <span className={item.done ? "text-muted-foreground line-through" : ""}>
                  {item.label}
                </span>
                {!item.done && <span className="block text-xs text-muted-foreground">{item.detail}</span>}
              </span>
            </Link>
          )
        })}
      </CardContent>
    </Card>
  )
}

export function OnboardingComplete() {
  return (
    <Card className="flex items-center gap-3 p-4">
      <div className="flex size-9 items-center justify-center rounded-lg bg-success-muted text-success">
        <PartyPopper className="size-4.5" />
      </div>
      <div>
        <p className="text-sm font-medium">Tu tenant está listo</p>
        <p className="text-xs text-muted-foreground">
          Completaste la configuración inicial de Agent Ops.
        </p>
      </div>
    </Card>
  )
}
