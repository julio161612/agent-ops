import { PageHeader } from "@/components/layout/PageHeader"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs"
import { UsageTab } from "@/pages/billing/UsageTab"
import { PlansTab } from "@/pages/billing/PlansTab"
import { InvoicesTab } from "@/pages/billing/InvoicesTab"

export function BillingPage() {
  return (
    <div>
      <PageHeader
        title="Facturación"
        description="Uso del plan actual, comparación de planes y facturas mensuales simuladas."
      />

      <Tabs defaultValue="usage">
        <TabsList>
          <TabsTrigger value="usage">Uso actual</TabsTrigger>
          <TabsTrigger value="plans">Planes</TabsTrigger>
          <TabsTrigger value="invoices">Facturas</TabsTrigger>
        </TabsList>
        <TabsContent value="usage">
          <UsageTab />
        </TabsContent>
        <TabsContent value="plans">
          <PlansTab />
        </TabsContent>
        <TabsContent value="invoices">
          <InvoicesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
