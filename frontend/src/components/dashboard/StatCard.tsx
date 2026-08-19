import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
import { Card } from "@/components/ui/Card"
import { cn } from "@/lib/utils"

export function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon: LucideIcon
  label: string
  value: ReactNode
  hint?: string
  tone?: "default" | "success" | "warning" | "destructive"
}) {
  const toneClasses = {
    default: "bg-muted text-muted-foreground",
    success: "bg-success-muted text-success",
    warning: "bg-warning-muted text-warning",
    destructive: "bg-destructive-muted text-destructive",
  }

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-1.5 font-mono text-2xl font-semibold tracking-tight">{value}</p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", toneClasses[tone])}>
          <Icon className="size-4.5" />
        </div>
      </div>
    </Card>
  )
}
