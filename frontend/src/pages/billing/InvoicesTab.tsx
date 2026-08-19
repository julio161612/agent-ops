import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { FileText } from "lucide-react"
import { billingApi } from "@/lib/api/endpoints/billing"
import { queryKeys } from "@/lib/queryKeys"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table"
import { Badge } from "@/components/ui/Badge"
import { EmptyState, ErrorState, PageLoading } from "@/components/ui/States"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog"
import { formatCost, formatDate } from "@/lib/utils"
import type { InvoiceRead, InvoiceStatus } from "@/lib/api/types"

const STATUS_VARIANTS: Record<InvoiceStatus, "outline" | "info" | "success"> = {
  draft: "outline",
  issued: "info",
  paid: "success",
}
const STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: "Borrador",
  issued: "Emitida",
  paid: "Pagada",
}

const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

export function InvoicesTab() {
  const [selected, setSelected] = React.useState<InvoiceRead | null>(null)
  const invoicesQuery = useQuery({
    queryKey: queryKeys.billingInvoices,
    queryFn: () => billingApi.listInvoices(),
  })

  if (invoicesQuery.isLoading) return <PageLoading />
  if (invoicesQuery.isError || !invoicesQuery.data) {
    return <ErrorState message="No se pudieron cargar las facturas" onRetry={() => invoicesQuery.refetch()} />
  }

  if (invoicesQuery.data.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="Sin facturas todavía"
        description="Las facturas se generan al cierre de cada mes a partir del uso real registrado."
      />
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Periodo</TableHead>
            <TableHead>Plan</TableHead>
            <TableHead>Mensajes</TableHead>
            <TableHead>Total</TableHead>
            <TableHead>Estado</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoicesQuery.data
            .slice()
            .sort((a, b) => b.period_year - a.period_year || b.period_month - a.period_month)
            .map((invoice) => (
              <TableRow key={invoice.id} clickable onClick={() => setSelected(invoice)}>
                <TableCell className="capitalize">
                  {MONTHS[invoice.period_month - 1]} {invoice.period_year}
                </TableCell>
                <TableCell>{invoice.plan_name_snapshot}</TableCell>
                <TableCell className="font-mono text-xs">
                  {invoice.total_messages}
                  {invoice.overage_messages > 0 && (
                    <span className="text-warning"> (+{invoice.overage_messages})</span>
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs font-medium">
                  {formatCost(invoice.total_cost_usd)}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANTS[invoice.status]}>{STATUS_LABELS[invoice.status]}</Badge>
                </TableCell>
              </TableRow>
            ))}
        </TableBody>
      </Table>

      <Dialog open={Boolean(selected)} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent size="sm">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="capitalize">
                  {MONTHS[selected.period_month - 1]} {selected.period_year}
                </DialogTitle>
                <DialogDescription>Plan {selected.plan_name_snapshot}</DialogDescription>
              </DialogHeader>
              <dl className="space-y-2 text-sm">
                <Row label="Cargo base" value={formatCost(selected.base_charge_usd)} />
                <Row label="Mensajes incluidos" value={String(selected.included_messages)} />
                <Row label="Mensajes totales" value={String(selected.total_messages)} />
                <Row label="Mensajes de excedente" value={String(selected.overage_messages)} />
                <Row label="Coste del excedente" value={formatCost(selected.overage_cost_usd)} />
                <Row label="Coste real de IA" value={formatCost(selected.total_ai_cost_usd)} />
                <div className="flex justify-between border-t border-border pt-2 font-semibold">
                  <dt>Total</dt>
                  <dd className="font-mono">{formatCost(selected.total_cost_usd)}</dd>
                </div>
                {selected.issued_at && (
                  <Row label="Emitida" value={formatDate(selected.issued_at)} />
                )}
              </dl>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  )
}
