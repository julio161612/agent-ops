import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, MessageCircle, Send, XCircle } from "lucide-react"
import { integrationsApi } from "@/lib/api/endpoints/integrations"
import { queryKeys } from "@/lib/queryKeys"
import { useAuth } from "@/contexts/AuthContext"
import { useToast } from "@/components/ui/Toast"
import { ApiError } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Label } from "@/components/ui/Label"
import { Badge } from "@/components/ui/Badge"
import { ErrorState, PageLoading } from "@/components/ui/States"

export function SlackTab() {
  const { hasRole } = useAuth()
  const canManage = hasRole("admin")
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [webhookUrl, setWebhookUrl] = React.useState("")

  const slackQuery = useQuery({
    queryKey: queryKeys.slackIntegration,
    queryFn: () => integrationsApi.getSlack(),
  })

  const configureMutation = useMutation({
    mutationFn: (url: string) => integrationsApi.configureSlack(url),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.slackIntegration })
      toast({ title: "Webhook de Slack guardado", variant: "success" })
      setWebhookUrl("")
    },
    onError: (err) => {
      toast({
        title: "No se pudo guardar el webhook",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "destructive",
      })
    },
  })

  const testMutation = useMutation({
    mutationFn: () => integrationsApi.testSlack(),
    onSuccess: (result) => {
      toast({
        title: result.sent ? "Mensaje de prueba enviado" : "No se pudo enviar",
        description: result.detail,
        variant: result.sent ? "success" : "destructive",
      })
    },
  })

  if (slackQuery.isLoading) return <PageLoading />
  if (slackQuery.isError || !slackQuery.data) {
    return <ErrorState message="No se pudo cargar la integración" onRetry={() => slackQuery.refetch()} />
  }

  const slack = slackQuery.data

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageCircle className="size-4" />
          Notificaciones de Slack
        </CardTitle>
        <CardDescription>
          Recibe un mensaje en tu canal cada vez que se abre un caso de escalado.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          {slack.configured ? (
            <Badge variant="success" dot>
              Configurado
            </Badge>
          ) : (
            <Badge variant="outline" dot>
              Sin configurar
            </Badge>
          )}
          {slack.masked_webhook_url && (
            <span className="font-mono text-xs text-muted-foreground">{slack.masked_webhook_url}</span>
          )}
        </div>

        {canManage && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="webhook">URL del Incoming Webhook</Label>
              <Input
                id="webhook"
                placeholder="https://hooks.slack.com/services/…"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button
                disabled={!webhookUrl.trim()}
                loading={configureMutation.isPending}
                onClick={() => configureMutation.mutate(webhookUrl.trim())}
              >
                Guardar webhook
              </Button>
              <Button
                variant="outline"
                disabled={!slack.configured}
                loading={testMutation.isPending}
                onClick={() => testMutation.mutate()}
              >
                <Send className="size-3.5" />
                Enviar prueba
              </Button>
            </div>
            {testMutation.data && (
              <div
                className={`flex items-center gap-2 text-xs ${testMutation.data.sent ? "text-success" : "text-destructive"}`}
              >
                {testMutation.data.sent ? (
                  <CheckCircle2 className="size-3.5" />
                ) : (
                  <XCircle className="size-3.5" />
                )}
                {testMutation.data.detail}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
