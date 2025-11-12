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
  evidences: Array<{ collection: 'INPUT_EVIDENCES'; id: string }>
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
  createConversation: (body: CreateConversationReq) =>
    http<CreateConversationRes>('/conversations', { method: 'POST', body: JSON.stringify(body) }),

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
}

export type PipelineRunRes = {
  conversation_id: string
  trigger_id: string
  prompt_id?: string | null
  report_id: string
  report: string
}

export async function pipelineRun(body: PipelineRunReq): Promise<PipelineRunRes> {
  const payload: PipelineRunReq = {
    stage_id: 0,
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
  return (await res.json()) as PipelineRunRes
}

export type OID = string | { $oid: string }

export type EvidenceRef = {
  collection: string
  id: OID
}

export type TriggerDoc = {
  _id: OID
  conversation_id: OID
  stage_id: number

  evidences?: EvidenceRef[]

  prompt_id?: OID

  status?: 'pending' | 'processing' | 'done' | 'error'

  report_id?: OID

  created_at?: string | { $date: string }
  updated_at?: string | { $date: string }
}

export async function getTrigger(triggerId: string): Promise<TriggerDoc> {
  return http<TriggerDoc>(`/triggers/${encodeURIComponent(triggerId)}`, { method: 'GET' })
}

export async function getLatestReportId(): Promise<string | null> {
  const res = await http<{ items?: Array<{ _id: string }> }>(`/reports?limit=1`)
  return res.items?.[0]?._id ?? null
}
