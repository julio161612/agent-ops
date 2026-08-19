import { Copy, Puzzle } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { useToast } from "@/components/ui/Toast"

export function WidgetTab() {
  const { toast } = useToast()
  const backendOrigin =
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/api\/v1\/?$/, "") ||
    window.location.origin

  const snippet = `<script
  src="${backendOrigin}/widget.js"
  data-api-key="ao_pk_TU_WIDGET_KEY"
  data-api-url="${backendOrigin}"
  data-title="Chat de soporte"
  async
></script>`

  function copy() {
    navigator.clipboard.writeText(snippet)
    toast({ title: "Snippet copiado", variant: "success" })
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Puzzle className="size-4" />
          Widget de chat embebible
        </CardTitle>
        <CardDescription>
          Pega este snippet antes de <code className="font-mono">&lt;/body&gt;</code> en cualquier página
          de tu web. No requiere build ni dependencias.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="relative">
          <pre className="overflow-x-auto rounded-lg bg-primary p-4 font-mono text-xs text-primary-foreground">
            {snippet}
          </pre>
          <Button
            variant="secondary"
            size="icon"
            className="absolute right-2 top-2 bg-white/10 text-white hover:bg-white/20"
            onClick={copy}
          >
            <Copy className="size-3.5" />
          </Button>
        </div>

        <ol className="list-inside list-decimal space-y-1.5 text-sm text-muted-foreground">
          <li>
            Crea una API key de tipo <span className="font-medium text-foreground">widget</span> en la
            pestaña "API Keys".
          </li>
          <li>Sustituye <code className="font-mono text-xs">ao_pk_TU_WIDGET_KEY</code> por el valor real.</li>
          <li>Publica la página — el widget aparecerá como una burbuja de chat abajo a la derecha.</li>
        </ol>
      </CardContent>
    </Card>
  )
}
