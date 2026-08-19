import {
  LayoutDashboard,
  Bot,
  Route,
  ShieldAlert,
  Inbox,
  Activity,
  BarChart3,
  CreditCard,
  Users,
  Plug,
  Settings,
  type LucideIcon,
} from "lucide-react"
import type { UserRole } from "@/lib/api/types"

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  minimumRole: UserRole
}

export const navItems: NavItem[] = [
  { label: "Dashboard", to: "/", icon: LayoutDashboard, minimumRole: "viewer" },
  { label: "Agentes", to: "/agents", icon: Bot, minimumRole: "viewer" },
  { label: "Reglas de routing", to: "/routing-rules", icon: Route, minimumRole: "viewer" },
  { label: "Guardrails", to: "/guardrails", icon: ShieldAlert, minimumRole: "viewer" },
  { label: "Escalados", to: "/escalations", icon: Inbox, minimumRole: "viewer" },
  { label: "Trazas", to: "/traces", icon: Activity, minimumRole: "viewer" },
  { label: "Métricas", to: "/metrics", icon: BarChart3, minimumRole: "viewer" },
  { label: "Facturación", to: "/billing", icon: CreditCard, minimumRole: "viewer" },
  { label: "Usuarios", to: "/users", icon: Users, minimumRole: "admin" },
  { label: "Integraciones", to: "/integrations", icon: Plug, minimumRole: "viewer" },
  { label: "Configuración", to: "/settings", icon: Settings, minimumRole: "viewer" },
]
