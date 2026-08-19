import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
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
  company_name: z.string().min(2, "Mínimo 2 caracteres").max(255),
  email: z.string().min(1, "Introduce tu email").email("Email no válido"),
  password: z.string().min(8, "Mínimo 8 caracteres").max(128),
})

type FormValues = z.infer<typeof schema>

export function RegisterPage() {
  const { register: doRegister } = useAuth()
  const navigate = useNavigate()
  const [serverError, setServerError] = React.useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async (values: FormValues) => {
    setServerError(null)
    try {
      await doRegister(values)
      navigate("/", { replace: true })
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "No se pudo crear la cuenta")
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Bot className="size-4.5" />
          </div>
          <span className="text-base font-semibold tracking-tight">Agent Ops</span>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Crea tu tenant</CardTitle>
            <CardDescription>
              Empiezas en el plan Free — podrás cambiar de plan cuando quieras
            </CardDescription>
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
                <Label htmlFor="company_name">Nombre de la empresa</Label>
                <Input
                  id="company_name"
                  placeholder="Acme Corp"
                  error={Boolean(errors.company_name)}
                  {...register("company_name")}
                />
                {errors.company_name && (
                  <p className="text-xs text-destructive">{errors.company_name.message}</p>
                )}
              </div>
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
                  autoComplete="new-password"
                  placeholder="Mínimo 8 caracteres"
                  error={Boolean(errors.password)}
                  {...register("password")}
                />
                {errors.password && (
                  <p className="text-xs text-destructive">{errors.password.message}</p>
                )}
              </div>
              <Button type="submit" className="w-full" loading={isSubmitting}>
                Crear cuenta
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          ¿Ya tienes cuenta?{" "}
          <Link to="/login" className="font-medium text-accent hover:underline">
            Inicia sesión
          </Link>
        </p>
      </div>
    </div>
  )
}
