import { Outlet } from "react-router-dom"
import { Sidebar } from "@/components/layout/Sidebar"
import { Header } from "@/components/layout/Header"
import { MobileNav } from "@/components/layout/MobileNav"

export function AppLayout() {
  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <MobileNav />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl p-5 lg:p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
