import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { UserPlus, UserX } from "lucide-react"
import { usersApi } from "@/lib/api/endpoints/users"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/Badge"
import { Button } from "@/components/ui/Button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { ErrorState, PageLoading } from "@/components/ui/States"
import { InviteUserDialog } from "@/pages/users/InviteUserDialog"
import { formatDate } from "@/lib/utils"
import type { UserRead, UserRole } from "@/lib/api/types"

export function UsersPage() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [inviteOpen, setInviteOpen] = React.useState(false)
  const [deactivating, setDeactivating] = React.useState<UserRead | null>(null)

  const usersQuery = useQuery({ queryKey: queryKeys.users, queryFn: () => usersApi.list() })

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: UserRole }) => usersApi.updateRole(id, { role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.users }),
    onError: (err) => {
      toast({
        title: "No se pudo cambiar el rol",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => usersApi.deactivate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users })
      toast({ title: "Usuario desactivado", variant: "success" })
      setDeactivating(null)
    },
    onError: (err) => {
      toast({
        title: "No se pudo desactivar",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  return (
    <div>
      <PageHeader
        title="Usuarios"
        description="Miembros del equipo con acceso al panel de este tenant."
        actions={
          <Button onClick={() => setInviteOpen(true)}>
            <UserPlus className="size-4" />
            Invitar usuario
          </Button>
        }
      />

      {usersQuery.isLoading ? (
        <PageLoading />
      ) : usersQuery.isError ? (
        <ErrorState message="No se pudieron cargar los usuarios" onRetry={() => usersQuery.refetch()} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Rol</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Miembro desde</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {usersQuery.data?.map((u) => {
              const isSelf = u.id === currentUser?.id
              return (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">
                    {u.email}
                    {isSelf && <span className="ml-1.5 text-xs text-muted-foreground">(tú)</span>}
                  </TableCell>
                  <TableCell>
                    <Select
                      value={u.role}
                      onValueChange={(role) => roleMutation.mutate({ id: u.id, role: role as UserRole })}
                      disabled={isSelf}
                    >
                      <SelectTrigger className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="viewer">Viewer</SelectItem>
                        <SelectItem value="operator">Operator</SelectItem>
                        <SelectItem value="admin">Admin</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Badge variant={u.is_active ? "success" : "outline"} dot>
                      {u.is_active ? "activo" : "desactivado"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatDate(u.created_at)}</TableCell>
                  <TableCell className="text-right">
                    {!isSelf && u.is_active && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:bg-destructive-muted"
                        onClick={() => setDeactivating(u)}
                      >
                        <UserX className="size-3.5" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}

      <InviteUserDialog open={inviteOpen} onOpenChange={setInviteOpen} />
      <ConfirmDialog
        open={Boolean(deactivating)}
        onOpenChange={(o) => !o && setDeactivating(null)}
        title={`Desactivar a ${deactivating?.email}`}
        description="Perderá acceso al panel inmediatamente. Puedes reactivarlo más tarde cambiándole el rol o contactando soporte."
        confirmLabel="Desactivar"
        loading={deactivateMutation.isPending}
        onConfirm={() => deactivating && deactivateMutation.mutate(deactivating.id)}
      />
    </div>
  )
}
