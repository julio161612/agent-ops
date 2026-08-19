import { useNavigate } from "react-router-dom"
import { ChevronsUpDown, LogOut, Building2 } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu"
import { Badge } from "@/components/ui/Badge"
import { initials } from "@/lib/utils"

export function Header() {
  const { user, tenant, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate("/login")
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-5">
      {/* Tenant selector — a single tenant per account today, but shaped for
          multi-tenant membership so adding a switcher later is a data change,
          not a UI rewrite. */}
      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium hover:bg-muted cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Building2 className="size-4 text-muted-foreground" />
          {tenant?.name ?? "…"}
          <ChevronsUpDown className="size-3.5 text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>Organización</DropdownMenuLabel>
          <DropdownMenuItem disabled className="justify-between">
            {tenant?.name}
            <Badge variant="info">actual</Badge>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <span className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {user ? initials(user.email) : "?"}
          </span>
          <span className="hidden text-left sm:block">
            <span className="block text-xs font-medium leading-tight">{user?.email}</span>
            <span className="block text-[11px] capitalize leading-tight text-muted-foreground">
              {user?.role}
            </span>
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Mi cuenta</DropdownMenuLabel>
          <DropdownMenuItem disabled>{user?.email}</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={handleLogout} className="text-destructive">
            <LogOut className="size-4" />
            Cerrar sesión
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
