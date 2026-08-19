import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number | string, opts?: { minimumFractionDigits?: number }): string {
  const n = typeof value === "string" ? Number(value) : value
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: opts?.minimumFractionDigits ?? 2,
    maximumFractionDigits: opts?.minimumFractionDigits ?? 2,
  }).format(n)
}

export function formatCost(value: number | string): string {
  const n = typeof value === "string" ? Number(value) : value
  if (n < 1) {
    return `$${n.toFixed(6)}`
  }
  return formatCurrency(n)
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("es-ES").format(value)
}

export function formatPercent(value: number, fractionDigits = 0): string {
  return `${(value * 100).toFixed(fractionDigits)}%`
}

export function formatDate(value: string | Date): string {
  const d = typeof value === "string" ? new Date(value) : value
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(d)
}

export function formatDateTime(value: string | Date): string {
  const d = typeof value === "string" ? new Date(value) : value
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d)
}

export function formatRelativeTime(value: string | Date): string {
  const d = typeof value === "string" ? new Date(value) : value
  const diffMs = d.getTime() - Date.now()
  const diffMin = Math.round(diffMs / 60000)
  const rtf = new Intl.RelativeTimeFormat("es-ES", { numeric: "auto" })

  if (Math.abs(diffMin) < 60) return rtf.format(diffMin, "minute")
  const diffHours = Math.round(diffMin / 60)
  if (Math.abs(diffHours) < 24) return rtf.format(diffHours, "hour")
  const diffDays = Math.round(diffHours / 24)
  return rtf.format(diffDays, "day")
}

export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength)}…`
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("")
}
