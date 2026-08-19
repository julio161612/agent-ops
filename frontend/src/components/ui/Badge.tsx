import * as React from "react"
import { cn } from "@/lib/utils"

type Variant = "default" | "success" | "warning" | "destructive" | "info" | "outline"

const variantClasses: Record<Variant, string> = {
  default: "bg-muted text-foreground border-transparent",
  success: "bg-success-muted text-success border-success/20",
  warning: "bg-warning-muted text-warning border-warning/20",
  destructive: "bg-destructive-muted text-destructive border-destructive/20",
  info: "bg-info-muted text-accent border-accent/20",
  outline: "bg-transparent text-muted-foreground border-border",
}

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: Variant
  dot?: boolean
}

export function Badge({ className, variant = "default", dot, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn(
            "size-1.5 rounded-full",
            variant === "success" && "bg-success",
            variant === "warning" && "bg-warning",
            variant === "destructive" && "bg-destructive",
            variant === "info" && "bg-accent",
            (variant === "default" || variant === "outline") && "bg-muted-foreground"
          )}
        />
      )}
      {children}
    </span>
  )
}
