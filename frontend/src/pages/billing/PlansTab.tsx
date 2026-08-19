import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check } from "lucide-react"
import { plansApi } from "@/lib/api/endpoints/plans"
import { subscriptionApi } from "@/lib/api/endpoints/subscription"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { Card } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { ErrorState, PageLoading } from "@/components/ui/States"
import { cn, formatCurrency, formatNumber } from "@/lib/utils"
import type { PlanRead } from "@/lib/api/types"

function planFeatures(plan: PlanRead): string[] {
  return [
    plan.included_messages_per_month !== null
      ? `${formatNumber(plan.included_messages_per_month)} mensajes/mes`
      : "Mensajes ilimitados",
    plan.included_active_agents !== null
      ? `${plan.included_active_agents} agentes activos`
      : "Agentes ilimitados",
    plan.included_users !== null ? `${plan.included_users} usuarios` : "Usuarios ilimitados",
    plan.included_ai_cost_usd !== null
      ? `${formatCurrency(plan.included_ai_cost_usd)} de coste IA incluido`
      : "Coste de IA ilimitado",
    `${plan.max_messages_per_minute} mensajes/min`,
    plan.overage_price_per_1000_messages_usd
      ? `${formatCurrency(plan.overage_price_per_1000_messages_usd)} por cada 1000 mensajes extra`
      : "Sin overage disponible",
  ]
}

export function PlansTab() {
  const { hasRole } = useAuth()
  const canManage = hasRole("admin")
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [targetPlan, setTargetPlan] = React.useState<PlanRead | null>(null)

  const plansQuery = useQuery({ queryKey: queryKeys.plans, queryFn: () => plansApi.list() })
  const subscriptionQuery = useQuery({
    queryKey: queryKeys.subscription,
    queryFn: () => subscriptionApi.get(),
  })

  const changeMutation = useMutation({
    mutationFn: (planId: string) => subscriptionApi.changePlan({ plan_id: planId }),
    onSuccess: (sub) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.subscription })
      queryClient.invalidateQueries({ queryKey: queryKeys.billingUsage })
      queryClient.invalidateQueries({ queryKey: queryKeys.agents })
      toast({ title: `Cambiado al plan ${sub.plan.name}`, variant: "success" })
      setTargetPlan(null)
    },
    onError: (err) => {
      toast({
        title: "No se pudo cambiar de plan",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  if (plansQuery.isLoading || subscriptionQuery.isLoading) return <PageLoading />
  if (plansQuery.isError || !plansQuery.data) {
    return <ErrorState message="No se pudieron cargar los planes" onRetry={() => plansQuery.refetch()} />
  }

  const currentPlanId = subscriptionQuery.data?.plan.id

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {plansQuery.data.map((plan) => {
          const isCurrent = plan.id === currentPlanId
          return (
            <Card
              key={plan.id}
              className={cn("flex flex-col p-5", isCurrent && "border-accent ring-1 ring-accent")}
            >
              {isCurrent && (
                <Badge variant="info" className="mb-2 w-fit">
                  Tu plan actual
                </Badge>
              )}
              <h3 className="text-sm font-semibold">{plan.name}</h3>
              <p className="mt-1">
                <span className="font-mono text-2xl font-semibold">
                  {formatCurrency(plan.monthly_price_usd, { minimumFractionDigits: 0 })}
                </span>
                <span className="text-xs text-muted-foreground">/mes</span>
              </p>

              <ul className="mt-4 flex-1 space-y-2">
                {planFeatures(plan).map((f) => (
                  <li key={f} className="flex items-start gap-1.5 text-xs">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-success" />
                    {f}
                  </li>
                ))}
              </ul>

              {canManage && !isCurrent && (
                <Button
                  className="mt-4 w-full"
                  variant="outline"
                  onClick={() => setTargetPlan(plan)}
                >
                  Cambiar a {plan.name}
                </Button>
              )}
            </Card>
          )
        })}
      </div>

      <ConfirmDialog
        open={Boolean(targetPlan)}
        onOpenChange={(o) => !o && setTargetPlan(null)}
        title={`Cambiar al plan ${targetPlan?.name}`}
        description="El cambio es inmediato: los nuevos límites se aplican desde ya. La factura del mes en curso reflejará el plan vigente al generarla, sin prorrateo."
        confirmLabel="Confirmar cambio"
        variant="primary"
        loading={changeMutation.isPending}
        onConfirm={() => targetPlan && changeMutation.mutate(targetPlan.id)}
      />
    </>
  )
}
