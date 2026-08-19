import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { usersApi } from "@/lib/api/endpoints/users"
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
import { Input } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"

const schema = z.object({
  email: z.string().min(1, "Obligatorio").email("Email no válido"),
  password: z.string().min(8, "Mínimo 8 caracteres").max(128),
  role: z.enum(["viewer", "operator", "admin"]),
})

type FormValues = z.infer<typeof schema>

export function InviteUserDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", role: "operator" },
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => usersApi.invite(values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users })
      toast({ title: "Usuario invitado", variant: "success" })
      reset()
      onOpenChange(false)
    },
    onError: (err) => {
      toast({
        title: "No se pudo invitar al usuario",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Invitar usuario</DialogTitle>
          <DialogDescription>Crea una cuenta para un nuevo miembro de tu equipo.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit((values) => mutation.mutate(values))} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" error={Boolean(errors.email)} {...register("email")} />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Contraseña temporal</Label>
            <Input
              id="password"
              type="password"
              error={Boolean(errors.password)}
              {...register("password")}
            />
            {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label>Rol</Label>
            <Controller
              control={control}
              name="role"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Viewer — solo lectura</SelectItem>
                    <SelectItem value="operator">Operator — puede gestionar agentes/routing/guardrails</SelectItem>
                    <SelectItem value="admin">Admin — control total, incluidos usuarios y facturación</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={isSubmitting || mutation.isPending}>
              Invitar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
