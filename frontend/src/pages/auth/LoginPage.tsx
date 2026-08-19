import * as React from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Bot, AlertCircle } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { ApiError } from "@/lib/api/client"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"

const schema = z.object({
  email: z.string().min(1, "Introduce tu email").email("Email no válido"),
  password: z.string().min(1, "Introduce tu contraseña"),
})

type FormValues = z.infer<typeof schema>

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [serverError, setServerError] = React.useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async (values: FormValues) => {
    setServerError(null)
    try {
      await login(values)
      const from = (location.state as { from?: Location })?.from?.pathname ?? "/"
      navigate(from, { replace: true })
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "No se pudo iniciar sesión")
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Bot className="size-4.5" />
          </div>
          <span className="text-base font-semibold tracking-tight">Agent Ops</span>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Inicia sesión</CardTitle>
            <CardDescription>Accede al panel de administración de tu tenant</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {serverError && (
                <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive-muted px-3 py-2 text-xs text-destructive">
                  <AlertCircle className="size-4 shrink-0" />
                  {serverError}
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="tu@empresa.com"
                  error={Boolean(errors.email)}
                  {...register("email")}
                />
                {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Contraseña</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  error={Boolean(errors.password)}
                  {...register("password")}
                />
                {errors.password && (
                  <p className="text-xs text-destructive">{errors.password.message}</p>
                )}
              </div>
              <Button type="submit" className="w-full" loading={isSubmitting}>
                Entrar
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          ¿No tienes cuenta?{" "}
          <Link to="/register" className="font-medium text-accent hover:underline">
            Crea un tenant nuevo
          </Link>
        </p>
      </div>
    </div>
  )
}
