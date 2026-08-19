import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Copy, Key, Plus, Trash2 } from "lucide-react"
import { apiKeysApi } from "@/lib/api/endpoints/apiKeys"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { Card } from "@/components/ui/Card"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog"
import { EmptyState, ErrorState, PageLoading } from "@/components/ui/States"
import { formatDateTime } from "@/lib/utils"
import type { ApiKeyCreate, ApiKeyRead } from "@/lib/api/types"

export function ApiKeysTab() {
  const { hasRole } = useAuth()
  const canManage = hasRole("admin")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [createOpen, setCreateOpen] = React.useState(false)
  const [revoking, setRevoking] = React.useState<ApiKeyRead | null>(null)
  const [newKey, setNewKey] = React.useState<string | null>(null)

  const keysQuery = useQuery({ queryKey: queryKeys.apiKeys, queryFn: () => apiKeysApi.list() })

  const { register, handleSubmit, control, reset } = useForm<ApiKeyCreate>({
    defaultValues: { name: "", key_type: "server", can_send_messages: true },
  })

  const createMutation = useMutation({
    mutationFn: (values: ApiKeyCreate) => apiKeysApi.create(values),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys })
      setNewKey(result.api_key)
      setCreateOpen(false)
      reset()
    },
    onError: (err) => {
      toast({
        title: "No se pudo crear la key",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: string) => apiKeysApi.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys })
      toast({ title: "API key revocada", variant: "success" })
      setRevoking(null)
    },
  })

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Claves para integrar la API pública o el widget desde fuera del panel.
        </p>
        {canManage && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            Nueva key
          </Button>
        )}
      </div>

      {keysQuery.isLoading ? (
        <PageLoading />
      ) : keysQuery.isError ? (
        <ErrorState message="No se pudieron cargar las API keys" onRetry={() => keysQuery.refetch()} />
      ) : keysQuery.data && keysQuery.data.length > 0 ? (
        <div className="space-y-2">
          {keysQuery.data.map((key) => (
            <Card key={key.id} className="flex items-center gap-3 p-3">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/5 text-primary">
                <Key className="size-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium">{key.name}</p>
                  <Badge variant="outline">{key.key_type}</Badge>
                  <Badge variant={key.is_active ? "success" : "outline"}>
                    {key.is_active ? "activa" : "revocada"}
                  </Badge>
                </div>
                <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                  {key.key_prefix}••••••••••••••••••••••••
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {key.last_used_at ? `Último uso ${formatDateTime(key.last_used_at)}` : "Nunca usada"}
                </p>
              </div>
              {canManage && key.is_active && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive hover:bg-destructive-muted"
                  onClick={() => setRevoking(key)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              )}
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState icon={Key} title="Sin API keys" description="Crea una para integrar la API pública o el widget." />
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Nueva API key</DialogTitle>
            <DialogDescription>
              Las keys de tipo widget solo pueden enviar mensajes; las de servidor también pueden leer
              historial.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit((values) => createMutation.mutate(values))} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="name">Nombre</Label>
              <Input id="name" placeholder="Producción — sitio web" {...register("name", { required: true })} />
            </div>
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Controller
                control={control}
                name="key_type"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="server">Servidor (ao_sk_…)</SelectItem>
                      <SelectItem value="widget">Widget (ao_pk_…)</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" loading={createMutation.isPending}>
                Crear
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(newKey)} onOpenChange={(o) => !o && setNewKey(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Guarda esta key ahora</DialogTitle>
            <DialogDescription>
              Por seguridad, no volverás a ver el valor completo. Cópialo y guárdalo en un lugar seguro.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2 rounded-md border border-warning/30 bg-warning-muted p-3 text-xs text-warning">
            <AlertTriangle className="size-4 shrink-0" />
            Esta es la única vez que se muestra en texto claro.
          </div>
          <div className="flex items-center gap-2">
            <Input readOnly value={newKey ?? ""} className="font-mono text-xs" />
            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                if (newKey) navigator.clipboard.writeText(newKey)
                toast({ title: "Copiada al portapapeles", variant: "success" })
              }}
            >
              <Copy className="size-4" />
            </Button>
          </div>
          <DialogFooter>
            <Button onClick={() => setNewKey(null)}>Entendido</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(revoking)}
        onOpenChange={(o) => !o && setRevoking(null)}
        title={`Revocar «${revoking?.name}»`}
        description="Cualquier integración que use esta key dejará de funcionar inmediatamente."
        confirmLabel="Revocar"
        loading={revokeMutation.isPending}
        onConfirm={() => revoking && revokeMutation.mutate(revoking.id)}
      />
    </div>
  )
}
