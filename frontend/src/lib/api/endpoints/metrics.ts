import { api } from "@/lib/api/client"
import type { Granularity, MetricsSummaryRead, MetricsTimeseriesRead } from "@/lib/api/types"

export interface MetricsDateRange {
  date_from?: string
  date_to?: string
  [key: string]: string | undefined
}

export const metricsApi = {
  summary: (params?: MetricsDateRange) => api.get<MetricsSummaryRead>("/metrics/summary", params),
  timeseries: (params?: MetricsDateRange & { granularity?: Granularity }) =>
    api.get<MetricsTimeseriesRead>("/metrics/timeseries", params),
}
