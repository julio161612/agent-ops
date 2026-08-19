import { ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/Button"

export function Pagination({
  offset,
  limit,
  total,
  onOffsetChange,
}: {
  offset: number
  limit: number
  total: number
  onOffsetChange: (offset: number) => void
}) {
  if (total === 0) return null
  const from = offset + 1
  const to = Math.min(offset + limit, total)

  return (
    <div className="flex items-center justify-between px-1 py-3 text-xs text-muted-foreground">
      <span>
        {from}–{to} de {total}
      </span>
      <div className="flex gap-1">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          <ChevronLeft className="size-3.5" />
          Anterior
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={to >= total}
          onClick={() => onOffsetChange(offset + limit)}
        >
          Siguiente
          <ChevronRight className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}
