import { NavLink } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import { navItems } from "@/components/layout/nav"
import { cn } from "@/lib/utils"

export function MobileNav() {
  const { hasRole } = useAuth()

  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-border bg-card px-3 py-2 scrollbar-thin lg:hidden">
      {navItems
        .filter((item) => hasRole(item.minimumRole))
        .map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                isActive
                  ? "bg-accent/10 text-accent"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )
            }
          >
            <item.icon className="size-3.5" />
            {item.label}
          </NavLink>
        ))}
    </nav>
  )
}
