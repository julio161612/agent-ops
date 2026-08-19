import { cn } from "@/lib/utils"

export function ProgressBar({
  value,
  max = 100,
  className,
  barClassName,
  tone = "accent",
}: {
  value: number
  max?: number
  className?: string
  barClassName?: string
  tone?: "accent" | "success" | "warning" | "destructive"
}) {
  const pct = max <= 0 ? 0 : Math.min(100, Math.max(0, (value / max) * 100))
  const toneClasses = {
    accent: "bg-accent",
    success: "bg-success",
    warning: "bg-warning",
    destructive: "bg-destructive",
  }
  const effectiveTone = pct >= 100 ? "destructive" : pct >= 85 ? "warning" : tone

  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}>
      <div
        className={cn("h-full rounded-full transition-all duration-300", toneClasses[effectiveTone], barClassName)}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
