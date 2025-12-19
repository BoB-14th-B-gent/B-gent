const BASE = import.meta.env.VITE_BACKEND_URL

export type CreateConversationReq = { input: string }
export type CreateConversationRes = {
  _id?: string
  id?: string
  conversation_id?: string
  title?: string
  created_at?: string
}

export type CreateTriggerReq = { conversation_id: string; stage_id: number }
export type CreateTriggerRes = { trigger_id: string; status: string; created_at: string }

export type CreateInputEvidencesReq = {
  conversation_id: string
  stage_id: number
  mode: 'auto' | 'manual'
  inline_threshold: number
}
export type CreateInputEvidencesRes = {
  prompt_id: string
  items: Array<{
    evidence_id: string
    type: string
    strategy: 'inline' | 'gridfs'
    data_gridfs_id?: string
    filename?: string
    size?: number
  }>
}

export type PatchTriggerPromptReq = { prompt_id: string }
export type PatchTriggerEvidencesReq = {
  evidences: Array<{ collection: 'INPUT_EVIDENCES' | 'MCP_EVIDENCES'; id: string }>
}

export type ConversationSummary = {
  _id: string
  title: string
  last_stage_id: number
  created_at: string
  updated_at: string
  case_id?: string | null
}

export type ConversationListRes = {
  items: ConversationSummary[]
}

export type MessageRole = 'USER' | 'B-GENT'

export type MessageItem = {
  role: MessageRole
  stage_id: number
  content: string
  created_at: string
}

export type MessageListRes = {
  conversation_id: string
  items: MessageItem[]
}

export type RFPosition = {
  x: number
  y: number
}

export type RFNodeDTO = {
  id: string
  type: string
  position: RFPosition
  data?: Record<string, unknown>
}

export type RFEdgeDTO = {
  id: string
  source: string
  target: string
  type?: string
  data?: Record<string, unknown>
}

export type UILayoutRes = {
  nodes?: RFNodeDTO[]
  edges?: RFEdgeDTO[]
  conversation_id: string
  stage_id: number
  created_at: string
  updated_at: string
}

export type UILayoutUpsertReq = {
  nodes: RFNodeDTO[]
  edges: RFEdgeDTO[]
}

export type CaseDetail = {
  _id: string
  name: string
  description?: string | null
  analyst?: string | null
  created_at: string
  updated_at: string
}

export type CaseListRes = {
  items: CaseDetail[]
}

export type CaseCreateReq = {
  name: string
  description?: string | null
  analyst?: string | null
}

export type CaseCreateRes = {
  _id: string
  created_at: string
}

export type CaseConversationListRes = {
  case_id: string
  items: ConversationSummary[]
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText} ${text}`.trim())
  }
  return (await res.json()) as T
}

export const api = {
  createTrigger: (body: CreateTriggerReq) =>
    http<CreateTriggerRes>('/triggers', { method: 'POST', body: JSON.stringify(body) }),

  createInputEvidences: (body: CreateInputEvidencesReq) =>
    http<CreateInputEvidencesRes>('/evidences/input', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  patchTriggerPrompt: (triggerId: string, body: PatchTriggerPromptReq) =>
    http(`/triggers/${encodeURIComponent(triggerId)}/prompt`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  patchTriggerEvidences: (triggerId: string, body: PatchTriggerEvidencesReq) =>
    http(`/triggers/${encodeURIComponent(triggerId)}/evidences`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${text}`)
  }
  const ct = res.headers.get('content-type') || ''
  return ct.includes('application/json') ? ((await res.json()) as T) : ({} as T)
}

export async function createSllmReport(
  triggerId: string
): Promise<{ ok: boolean; report_id: string }> {
  return req('/sllm/reports', {
    method: 'POST',
    body: JSON.stringify({ trigger_id: triggerId }),
  })
}

export async function getReport(reportId: string): Promise<{
  report: string
  conversation_id: string
  stage_id: number
  trigger_id: string
  created_at: string
  structured?: {
    header?: string
    sections?: Record<string, unknown>
  }
}> {
  return req(`/reports/${encodeURIComponent(reportId)}`, { method: 'GET' })
}

export async function patchTriggerReport(triggerId: string, reportId: string): Promise<unknown> {
  return req(`/triggers/${encodeURIComponent(triggerId)}/report`, {
    method: 'PATCH',
    body: JSON.stringify({ report_id: reportId }),
  })
}

export async function postMessage(
  conversationId: string,
  content: string,
  role: 'USER' | 'B-GENT' = 'B-GENT',
  stageId = 0
): Promise<unknown> {
  return req(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ role, stage_id: stageId, content }),
  })
}

export type PipelineRunReq = {
  input: string
  stage_id?: number
  inline_threshold?: number
  mode?: 'auto' | 'manual'
  conversation_id?: string
  case_id?: string
}

export type PipelineRunPrepareRes = {
  conversation_id: string
  trigger_id: string
  prompt_id?: string | null
}

export type PipelineRunFullRes = {
  conversation_id: string
  trigger_id: string
  prompt_id?: string | null
  report_id: string
  report: string
}

export async function pipelineRun(body: PipelineRunReq): Promise<PipelineRunPrepareRes> {
  if (body.stage_id == null) {
    throw new Error('stage_id is required')
  }

  const payload: PipelineRunReq = {
    inline_threshold: 10 * 1024 * 1024,
    mode: 'auto',
    ...body,
  }
  const res = await fetch(`${BASE}/pipeline/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${t}`)
  }
  return (await res.json()) as PipelineRunPrepareRes
}

export async function pipelineRunAfterAgent(triggerId: string): Promise<PipelineRunFullRes> {
  const payload = { trigger_id: triggerId }

  const res = await fetch(`${BASE}/pipeline/run/after-agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${t}`)
  }

  return (await res.json()) as PipelineRunFullRes
}

export async function pipelineRunFull(body: PipelineRunReq): Promise<PipelineRunFullRes> {
  const payload: PipelineRunReq = {
    stage_id: 0,
    inline_threshold: 10 * 1024 * 1024,
    mode: 'auto',
    ...body,
  }
  const res = await fetch(`${BASE}/pipeline/run/full`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${t}`)
  }
  return (await res.json()) as PipelineRunFullRes
}

export type OID = string | { $oid: string }

export type EvidenceRef = { collection: 'INPUT_EVIDENCES' | 'MCP_EVIDENCES'; id: string }

export type TriggerDoc = {
  _id: string
  conversation_id: string
  stage_id: number
  evidences: Array<{ collection: 'INPUT_EVIDENCES' | 'MCP_EVIDENCES'; id: string }>
  prompt_id?: string | null
  status?: 'initial' | 'collecting' | 'ready' | 'processing' | 'done'
  report_id?: string | null
  created_at?: string
  updated_at?: string
}

export type TriggerListRes = {
  conversation_id: string
  items: Array<{
    id: string
    conversation_id: string
    stage_id: number
    status: 'initial' | 'collecting' | 'ready' | 'processing' | 'done'
    prompt_id?: string | null
    report_id?: string | null
    evidences: Array<{ collection: string; id: string }>
    created_at?: string
    updated_at?: string
  }>
}

export async function getConversationTriggers(
  conversationId: string,
  opts?: {
    stage_id?: number
    status?: 'initial' | 'collecting' | 'ready' | 'processing' | 'done'
    include_evidences?: boolean
    limit?: number
  }
): Promise<TriggerListRes> {
  const qs = new URLSearchParams()
  if (opts?.stage_id != null) qs.set('stage_id', String(opts.stage_id))
  if (opts?.status) qs.set('status', opts.status)
  if (opts?.include_evidences != null) qs.set('include_evidences', String(opts.include_evidences))
  if (opts?.limit != null) qs.set('limit', String(opts.limit))

  const path = `/conversations/${encodeURIComponent(conversationId)}/triggers${
    qs.toString() ? `?${qs.toString()}` : ''
  }`

  return http<TriggerListRes>(path, { method: 'GET' })
}

export type MCPSummaryItem = {
  mcp_name: string
  total: number
  success: number
  failed: number
  last_at?: string | null
}
export type MCPSummaryRes = {
  trigger_id: string
  stage_id: number
  items: MCPSummaryItem[]
}

export async function getMcpSummary(triggerId: string, stageId: number): Promise<MCPSummaryRes> {
  const qs = new URLSearchParams({ stage_id: String(stageId) })
  return http(`/triggers/${encodeURIComponent(triggerId)}/mcp-summary?${qs.toString()}`, {
    method: 'GET',
  })
}

export type MCPEvidenceListItem = {
  _id: string
  trigger_id: string
  conversation_id: string
  agent_id?: string | null
  stage_id: number
  mcp_name: string
  tool_name?: string | null
  success?: boolean
  created_at?: string | null
  request?: Record<string, unknown>
  response?: Record<string, unknown>
}
export type MCPEvidenceListRes = {
  trigger_id: string
  stage_id: number
  mcp_name: string
  items: MCPEvidenceListItem[]
}

export async function getMcpEvidences(
  triggerId: string,
  params: { mcp_name: string; stage_id: number; limit?: number; include_payload?: boolean }
): Promise<MCPEvidenceListRes> {
  const qs = new URLSearchParams({
    mcp_name: params.mcp_name,
    stage_id: String(params.stage_id),
    limit: String(params.limit ?? 200),
    include_payload: String(params.include_payload ?? true),
  })
  return http(`/triggers/${encodeURIComponent(triggerId)}/mcp-evidences?${qs.toString()}`, {
    method: 'GET',
  })
}

export type McpEvidenceDetailRes = {
  _id: string
  trigger_id?: string | null
  conversation_id?: string | null
  stage_id?: number | null
  mcp_name?: string | null
  tool_name?: string | null
  agent_id?: string | null
  success?: boolean | null
  created_at?: string | null
  request?: Record<string, unknown> | null
  response?: Record<string, unknown> | null
}

export async function getMcpEvidenceDetail(evidenceId: string): Promise<McpEvidenceDetailRes> {
  return http<McpEvidenceDetailRes>(`/evidences/mcp/${encodeURIComponent(evidenceId)}`, {
    method: 'GET',
  })
}

export async function getTrigger(triggerId: string): Promise<TriggerDoc> {
  return http<TriggerDoc>(`/triggers/${encodeURIComponent(triggerId)}`, { method: 'GET' })
}

export async function getLatestReportIdByConversation(
  conversationId: string,
  stageId?: number
): Promise<string | null> {
  const items = await getConversationReports(conversationId)
  const filtered = stageId != null ? items.filter(r => r.stage_id === stageId) : items
  if (filtered.length === 0) return null
  return filtered[filtered.length - 1]._id
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await http<ConversationListRes>('/conversations', { method: 'GET' })
  return res.items ?? []
}

export async function getConversation(conversationId: string): Promise<ConversationSummary> {
  return http<ConversationSummary>(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'GET',
  })
}

export async function updateConversationStage(
  conversationId: string,
  stageId: number
): Promise<void> {
  const qs = new URLSearchParams({ stage_id: String(stageId) })
  await http(`/conversations/${encodeURIComponent(conversationId)}/stage?${qs.toString()}`, {
    method: 'PATCH',
  })
}

export async function getMessages(
  conversationId: string,
  stageId: number,
  limit = 100
): Promise<MessageItem[]> {
  const qs = new URLSearchParams({
    stage_id: String(stageId),
    limit: String(limit),
  })
  const path = `/conversations/${encodeURIComponent(conversationId)}/messages?${qs.toString()}`
  const res = await http<MessageListRes>(path, { method: 'GET' })
  return res.items ?? []
}

export async function getUILayout(conversationId: string, stageId: number): Promise<UILayoutRes> {
  return http<UILayoutRes>(
    `/conversations/${encodeURIComponent(conversationId)}/${encodeURIComponent(String(stageId))}`,
    { method: 'GET' }
  )
}

export async function putUILayout(
  conversationId: string,
  stageId: number,
  body: UILayoutUpsertReq
): Promise<UILayoutRes> {
  return http<UILayoutRes>(
    `/conversations/${encodeURIComponent(conversationId)}/${encodeURIComponent(String(stageId))}`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    }
  )
}

export type ReportItem = {
  _id: string
  stage_id: number
  report: string
  created_at: string
}

export type ConversationReportsRes = {
  conversation_id: string
  items: ReportItem[]
}

export async function getConversationReports(conversationId: string): Promise<ReportItem[]> {
  const res = await http<ConversationReportsRes>(
    `/conversations/${encodeURIComponent(conversationId)}/reports`,
    { method: 'GET' }
  )
  return res.items ?? []
}

export async function listCases(): Promise<CaseDetail[]> {
  const res = await http<CaseListRes>('/cases', { method: 'GET' })
  return res.items ?? []
}

export async function createCase(body: CaseCreateReq): Promise<CaseCreateRes> {
  return http<CaseCreateRes>('/cases', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function listCaseConversations(caseId: string): Promise<ConversationSummary[]> {
  const res = await http<CaseConversationListRes>(
    `/cases/${encodeURIComponent(caseId)}/conversations`,
    { method: 'GET' }
  )
  return res.items ?? []
}

export async function createCaseConversation(
  caseId: string,
  body: CreateConversationReq
): Promise<CreateConversationRes> {
  return http<CreateConversationRes>(`/cases/${encodeURIComponent(caseId)}/conversations`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function getCase(caseId: string): Promise<CaseDetail> {
  return http<CaseDetail>(`/cases/${encodeURIComponent(caseId)}`, { method: 'GET' })
}
