import * as React from "react"
import * as ToastPrimitive from "@radix-ui/react-toast"
import { CheckCircle2, XCircle, X } from "lucide-react"
import { cn } from "@/lib/utils"

interface ToastItem {
  id: number
  title: string
  description?: string
  variant?: "default" | "success" | "destructive"
}

interface ToastContextValue {
  toast: (item: Omit<ToastItem, "id">) => void
}

const ToastContext = React.createContext<ToastContextValue | null>(null)

let nextId = 1

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([])

  const toast = React.useCallback((item: Omit<ToastItem, "id">) => {
    const id = nextId++
    setItems((prev) => [...prev, { ...item, id }])
  }, [])

  const remove = React.useCallback((id: number) => {
    setItems((prev) => prev.filter((i) => i.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right" duration={4500}>
        {children}
        {items.map((item) => (
          <ToastPrimitive.Root
            key={item.id}
            onOpenChange={(open) => !open && remove(item.id)}
            className={cn(
              "grid grid-cols-[auto_1fr_auto] items-start gap-3 rounded-lg border bg-card p-4 shadow-lg",
              "data-[state=open]:animate-fade-in data-[swipe=end]:animate-fade-in",
              item.variant === "destructive" && "border-destructive/30",
              item.variant === "success" && "border-success/30"
            )}
          >
            {item.variant === "success" && <CheckCircle2 className="size-5 text-success mt-0.5" />}
            {item.variant === "destructive" && <XCircle className="size-5 text-destructive mt-0.5" />}
            <div className="grid gap-0.5">
              <ToastPrimitive.Title className="text-sm font-medium">{item.title}</ToastPrimitive.Title>
              {item.description && (
                <ToastPrimitive.Description className="text-xs text-muted-foreground">
                  {item.description}
                </ToastPrimitive.Description>
              )}
            </div>
            <ToastPrimitive.Close className="cursor-pointer text-muted-foreground hover:text-foreground">
              <X className="size-4" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-[100] flex w-full max-w-sm flex-col gap-2 p-4 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext)
  if (!ctx) throw new Error("useToast must be used within a ToastProvider")
  return ctx
}
