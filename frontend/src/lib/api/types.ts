// Hand-written types mirroring the Agent Ops backend's Pydantic schemas
// (backend/app/schemas/*.py). Kept in sync manually — see frontend/README.md.

// ---------- Enums ----------

export type UserRole = "viewer" | "operator" | "admin"

export type ConversationStatus = "open" | "closed" | "escalated" | "unassigned"

export type MessageRole = "user" | "assistant" | "system"

export type EscalationStatus = "pending" | "in_progress" | "resolved"

export type EscalationReason = "unassigned_routing" | "guardrail_blocked" | "manual"

export type GuardrailType = "input" | "output"

export type GuardrailRuleType =
  | "blocklist_keywords"
  | "pii_detection"
  | "max_length"
  | "custom_llm_check"

export type GuardrailAction = "block" | "flag"

export type RoutingRuleType = "keyword" | "category"

export type RoutingMethod = "rule" | "llm"

export type TraceOutcome = "completed" | "blocked" | "escalated" | "unassigned"

export type ApiKeyType = "server" | "widget"

export type SubscriptionStatus = "active" | "canceled" | "past_due"

export type InvoiceStatus = "draft" | "issued" | "paid"

export type PiiPattern = "email" | "credit_card" | "phone" | "spanish_dni"

// ---------- Auth ----------

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserRead {
  id: string
  tenant_id: string
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface TenantRead {
  id: string
  name: string
  slug: string
  created_at: string
}

export interface MeResponse {
  user: UserRead
  tenant: TenantRead
}

// ---------- Agents ----------

export interface AgentParameters {
  temperature?: number
  max_tokens?: number
  [key: string]: unknown
}

export interface AgentRead {
  id: string
  tenant_id: string
  name: string
  description: string | null
  agent_type: string | null
  system_prompt: string
  model: string
  parameters: AgentParameters
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AgentCreate {
  name: string
  description?: string | null
  agent_type?: string | null
  system_prompt: string
  model?: string | null
  parameters?: AgentParameters
  is_active?: boolean
}

export type AgentUpdate = Partial<AgentCreate>

export interface GuardrailDryRunViolationRead {
  policy_id: string
  guardrail_type: GuardrailType
  violation_type: GuardrailRuleType
  detail: string
  action_taken: GuardrailAction
}

export interface AgentTestResponse {
  agent_id: string
  input_blocked: boolean
  input_guardrail_violations: GuardrailDryRunViolationRead[]
  reply: string | null
  output_blocked: boolean
  output_guardrail_violations: GuardrailDryRunViolationRead[]
  model: string
  input_tokens: number
  output_tokens: number
  cost_usd: string
  latency_ms: number
}

// ---------- Agent templates ----------

export interface RecommendedGuardrailRead {
  guardrail_type: GuardrailType
  rule_type: GuardrailRuleType
  config: Record<string, unknown>
  action_on_violation: GuardrailAction
  rationale: string
}

export interface AgentTemplateRead {
  id: string
  name: string
  description: string
  agent_type: string
  system_prompt: string
  suggested_model: string
  suggested_parameters: AgentParameters
  recommended_guardrail: RecommendedGuardrailRead | null
}

export interface CreateAgentFromTemplateRequest {
  name?: string | null
  system_prompt?: string | null
  model?: string | null
  apply_recommended_guardrail?: boolean
}

export interface CreateAgentFromTemplateResponse {
  agent: AgentRead
  guardrail_policy: GuardrailPolicyRead | null
}

// ---------- Conversations & messages ----------

export interface MessageRead {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface RoutingDecisionRead {
  id: string
  conversation_id: string
  method: RoutingMethod
  matched_rule_id: string | null
  agent_id: string | null
  confidence: number | null
  reasoning: string | null
  created_at: string
}

export interface GuardrailViolationRead {
  id: string
  tenant_id: string
  conversation_id: string
  message_id: string | null
  policy_id: string | null
  guardrail_type: GuardrailType
  violation_type: GuardrailRuleType
  detail: string
  action_taken: GuardrailAction
  created_at: string
}

export interface SendMessageRequest {
  content: string
  agent_id?: string | null
}

export interface SendMessageResponse {
  conversation_id: string
  conversation_status: ConversationStatus
  user_message: MessageRead
  assistant_message: MessageRead | null
  routing: RoutingDecisionRead | null
  guardrail_violations: GuardrailViolationRead[]
  trace_id: string | null
}

// ---------- Routing rules ----------

export interface RoutingRuleRead {
  id: string
  tenant_id: string
  agent_id: string
  rule_type: RoutingRuleType
  condition: Record<string, unknown>
  priority: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface RoutingRuleCreate {
  agent_id: string
  rule_type: RoutingRuleType
  condition: Record<string, unknown>
  priority?: number
  is_active?: boolean
}

export type RoutingRuleUpdate = Partial<RoutingRuleCreate>

export interface RoutingRuleMatchPreview {
  rule_id: string
  rule_type: RoutingRuleType
  priority: number
  agent_id: string
  agent_name: string
  would_win: boolean
}

export interface RoutingValidateResponse {
  content: string
  matched_rules: RoutingRuleMatchPreview[]
  resulting_agent_id: string | null
  resulting_agent_name: string | null
  would_use_llm_router: boolean
}

// ---------- Guardrail policies ----------

export interface GuardrailPolicyRead {
  id: string
  tenant_id: string
  agent_id: string | null
  guardrail_type: GuardrailType
  rule_type: GuardrailRuleType
  config: Record<string, unknown>
  action_on_violation: GuardrailAction
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface GuardrailPolicyCreate {
  agent_id?: string | null
  guardrail_type: GuardrailType
  rule_type: GuardrailRuleType
  config: Record<string, unknown>
  action_on_violation?: GuardrailAction
  is_active?: boolean
}

export type GuardrailPolicyUpdate = Partial<GuardrailPolicyCreate>

// ---------- Escalations ----------

export interface EscalationCaseRead {
  id: string
  tenant_id: string
  conversation_id: string
  reason: EscalationReason
  status: EscalationStatus
  assigned_to: string | null
  assigned_at: string | null
  resolved_at: string | null
  resolution_notes: string | null
  created_at: string
  updated_at: string
}

export interface EscalationRespondResponse {
  case: EscalationCaseRead
  message: MessageRead
}

// ---------- Tenant limits ----------

export interface TenantLimitsRead {
  id: string
  tenant_id: string
  messages_per_minute_limit: number
  monthly_cost_limit_usd: string | null
  current_month: string
  current_month_cost_usd: string
  created_at: string
  updated_at: string
}

export interface TenantLimitsUpdate {
  messages_per_minute_limit?: number | null
  monthly_cost_limit_usd?: string | null
}

// ---------- Traces ----------

export interface InteractionTraceRead {
  id: string
  tenant_id: string
  conversation_id: string
  user_message_id: string
  assistant_message_id: string | null
  agent_id: string | null
  routing_decision_id: string | null
  escalation_case_id: string | null
  outcome: TraceOutcome
  cost_usd: string
  input_tokens: number
  output_tokens: number
  total_latency_ms: number
  stage_latencies_ms: Record<string, number>
  created_at: string
}

export interface InteractionTracePage {
  items: InteractionTraceRead[]
  total: number
  limit: number
  offset: number
}

export interface InteractionTraceDetail extends InteractionTraceRead {
  guardrail_violations: GuardrailViolationRead[]
  routing_decision: RoutingDecisionRead | null
  escalation_case: EscalationCaseRead | null
}

// ---------- Metrics ----------

export interface AgentUsageStatRead {
  agent_id: string | null
  agent_name: string | null
  interaction_count: number
  cost_usd: string
}

export interface GuardrailTypeStatRead {
  violation_type: string
  violation_count: number
}

export interface MetricsSummaryRead {
  date_from: string
  date_to: string
  total_interactions: number
  completed: number
  blocked: number
  escalated: number
  unassigned: number
  auto_resolution_rate: number
  escalation_rate: number
  total_cost_usd: string
  latency_ms_avg: number | null
  latency_ms_p95: number | null
  agent_usage: AgentUsageStatRead[]
  guardrail_violations_by_type: GuardrailTypeStatRead[]
}

export type Granularity = "hour" | "day" | "week" | "month"

export interface TimeseriesBucketRead {
  bucket_start: string
  total_interactions: number
  completed: number
  blocked: number
  escalated: number
  unassigned: number
  total_cost_usd: string
  latency_ms_avg: number | null
}

export interface MetricsTimeseriesRead {
  date_from: string
  date_to: string
  granularity: string
  buckets: TimeseriesBucketRead[]
}

// ---------- Users ----------

export interface UserInvite {
  email: string
  password: string
  role: UserRole
}

export interface UserRoleUpdate {
  role: UserRole
}

// ---------- API keys ----------

export interface ApiKeyRead {
  id: string
  tenant_id: string
  name: string
  key_type: ApiKeyType
  key_prefix: string
  can_send_messages: boolean
  is_active: boolean
  created_by_user_id: string | null
  last_used_at: string | null
  created_at: string
}

export interface ApiKeyCreateResponse extends ApiKeyRead {
  api_key: string
}

export interface ApiKeyCreate {
  name: string
  key_type?: ApiKeyType
  can_send_messages?: boolean
}

// ---------- Plans & subscription ----------

export interface PlanRead {
  id: string
  name: string
  slug: string
  monthly_price_usd: string
  included_messages_per_month: number | null
  included_active_agents: number | null
  included_users: number | null
  included_ai_cost_usd: string | null
  max_messages_per_minute: number
  overage_price_per_1000_messages_usd: string | null
  is_active: boolean
  created_at: string
}

export interface SubscriptionWithPlanRead {
  id: string
  tenant_id: string
  plan_id: string
  status: SubscriptionStatus
  started_at: string
  overage_enabled: boolean
  plan: PlanRead
}

export interface ChangePlanRequest {
  plan_id: string
  overage_enabled?: boolean | null
}

// ---------- Billing ----------

export interface CurrentUsageRead {
  plan: PlanRead
  period_year: number
  period_month: number
  messages_used: number
  included_messages: number | null
  overage_messages: number
  overage_cost_usd: string
  ai_cost_usd: string
  included_ai_cost_usd: string | null
  overage_enabled: boolean
}

export interface InvoiceRead {
  id: string
  tenant_id: string
  period_year: number
  period_month: number
  plan_id: string | null
  plan_name_snapshot: string
  base_charge_usd: string
  included_messages: number
  total_messages: number
  overage_messages: number
  overage_cost_usd: string
  total_ai_cost_usd: string
  total_cost_usd: string
  status: InvoiceStatus
  issued_at: string | null
  created_at: string
}

// ---------- Onboarding ----------

export interface OnboardingItemRead {
  key: string
  label: string
  done: boolean
  detail: string
}

export interface OnboardingStatusRead {
  items: OnboardingItemRead[]
  completed_count: number
  total_count: number
  is_complete: boolean
}

// ---------- Integrations ----------

export interface SlackIntegrationRead {
  configured: boolean
  masked_webhook_url: string | null
}

export interface SlackTestResult {
  sent: boolean
  detail: string
}

// ---------- API error shape ----------

export interface ApiValidationErrorItem {
  loc: (string | number)[]
  msg: string
  type: string
}

export interface ApiErrorBody {
  detail: string | ApiValidationErrorItem[]
}
