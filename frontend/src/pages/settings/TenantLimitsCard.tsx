import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { tenantLimitsApi } from "@/lib/api/endpoints/tenantLimits"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import { ErrorState, PageLoading } from "@/components/ui/States"
import { formatCost } from "@/lib/utils"

export function TenantLimitsCard() {
  const { hasRole } = useAuth()
  const canManage = hasRole("admin")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const limitsQuery = useQuery({
    queryKey: queryKeys.tenantLimits,
    queryFn: () => tenantLimitsApi.get(),
  })

  const [rateLimit, setRateLimit] = React.useState("")
  const [costLimit, setCostLimit] = React.useState("")

  React.useEffect(() => {
    if (limitsQuery.data) {
      setRateLimit(String(limitsQuery.data.messages_per_minute_limit))
      setCostLimit(limitsQuery.data.monthly_cost_limit_usd ?? "")
    }
  }, [limitsQuery.data])

  const mutation = useMutation({
    mutationFn: () =>
      tenantLimitsApi.update({
        messages_per_minute_limit: Number(rateLimit),
        monthly_cost_limit_usd: costLimit.trim() === "" ? null : costLimit.trim(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tenantLimits })
      toast({ title: "Límites actualizados", variant: "success" })
    },
    onError: (err) => {
      toast({
        title: "No se pudo actualizar",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  if (limitsQuery.isLoading) return <PageLoading />
  if (limitsQuery.isError || !limitsQuery.data) {
    return <ErrorState message="No se pudieron cargar los límites" onRetry={() => limitsQuery.refetch()} />
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Límites del tenant</CardTitle>
        <CardDescription>
          Tope propio dentro de lo que permite tu plan — nunca por encima. Gastado este mes:{" "}
          <span className="font-mono">{formatCost(limitsQuery.data.current_month_cost_usd)}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="rate">Mensajes por minuto</Label>
            <Input
              id="rate"
              type="number"
              min={1}
              disabled={!canManage}
              value={rateLimit}
              onChange={(e) => setRateLimit(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cost">Límite de coste mensual (USD, vacío = sin límite propio)</Label>
            <Input
              id="cost"
              type="number"
              step="0.01"
              min={0}
              disabled={!canManage}
              placeholder="Sin límite"
              value={costLimit}
              onChange={(e) => setCostLimit(e.target.value)}
            />
          </div>
        </div>
        {canManage && (
          <Button size="sm" loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Guardar
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
