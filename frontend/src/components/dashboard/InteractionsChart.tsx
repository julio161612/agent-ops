import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { TimeseriesBucketRead } from "@/lib/api/types"
import { formatDate, formatNumber } from "@/lib/utils"

export function InteractionsChart({ buckets }: { buckets: TimeseriesBucketRead[] }) {
  const data = buckets.map((b) => ({
    date: formatDate(b.bucket_start),
    completadas: b.completed,
    escaladas: b.escalated,
    bloqueadas: b.blocked,
    sinAsignar: b.unassigned,
  }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="fillCompletadas" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#0369a1" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#0369a1" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="fillEscaladas" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#d97706" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#d97706" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="fillBloqueadas" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#dc2626" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#dc2626" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="#e2e8f0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#64748b" }}
          axisLine={{ stroke: "#e2e8f0" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#64748b" }}
          axisLine={false}
          tickLine={false}
          width={32}
          tickFormatter={(v) => formatNumber(v)}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{
            fontSize: 12,
            borderRadius: 8,
            border: "1px solid #e2e8f0",
            boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
          }}
        />
        <Area
          type="monotone"
          dataKey="completadas"
          stackId="1"
          stroke="#0369a1"
          fill="url(#fillCompletadas)"
          strokeWidth={2}
        />
        <Area
          type="monotone"
          dataKey="escaladas"
          stackId="1"
          stroke="#d97706"
          fill="url(#fillEscaladas)"
          strokeWidth={2}
        />
        <Area
          type="monotone"
          dataKey="bloqueadas"
          stackId="1"
          stroke="#dc2626"
          fill="url(#fillBloqueadas)"
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
