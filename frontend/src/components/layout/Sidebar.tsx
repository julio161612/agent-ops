import { NavLink } from "react-router-dom"
import { Bot } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { navItems } from "@/components/layout/nav"
import { cn } from "@/lib/utils"

export function Sidebar() {
  const { hasRole } = useAuth()

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card lg:flex">
      <div className="flex h-14 items-center gap-2 border-b border-border px-5">
        <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Bot className="size-4" />
        </div>
        <span className="text-sm font-semibold tracking-tight">Agent Ops</span>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
        {navItems
          .filter((item) => hasRole(item.minimumRole))
          .map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )
              }
            >
              <item.icon className="size-4 shrink-0" />
              {item.label}
            </NavLink>
          ))}
      </nav>

      <div className="border-t border-border p-3">
        <p className="px-2 text-[11px] leading-tight text-muted-foreground">
          Agent Ops · Panel de administración
        </p>
      </div>
    </aside>
  )
}
