import { PageHeader } from "@/components/layout/PageHeader"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs"
import { ApiKeysTab } from "@/pages/integrations/ApiKeysTab"
import { SlackTab } from "@/pages/integrations/SlackTab"
import { WidgetTab } from "@/pages/integrations/WidgetTab"

export function IntegrationsPage() {
  return (
    <div>
      <PageHeader
        title="Integraciones"
        description="Conecta Agent Ops con tus canales: API pública, widget embebible y notificaciones de Slack."
      />

      <Tabs defaultValue="api-keys">
        <TabsList>
          <TabsTrigger value="api-keys">API Keys</TabsTrigger>
          <TabsTrigger value="slack">Slack</TabsTrigger>
          <TabsTrigger value="widget">Widget</TabsTrigger>
        </TabsList>
        <TabsContent value="api-keys">
          <ApiKeysTab />
        </TabsContent>
        <TabsContent value="slack">
          <SlackTab />
        </TabsContent>
        <TabsContent value="widget">
          <WidgetTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
