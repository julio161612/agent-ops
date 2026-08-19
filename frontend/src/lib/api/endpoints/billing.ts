import { api } from "@/lib/api/client"
import type { CurrentUsageRead, InvoiceRead } from "@/lib/api/types"

export const billingApi = {
  currentUsage: () => api.get<CurrentUsageRead>("/billing/current-usage"),
  listInvoices: () => api.get<InvoiceRead[]>("/billing/invoices"),
  getInvoice: (id: string) => api.get<InvoiceRead>(`/billing/invoices/${id}`),
}
