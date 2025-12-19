import { useEffect, useMemo, useRef, useState } from 'react'
import { getMcpSummary, getMcpEvidences, getMcpEvidenceDetail } from '@/utils/api'
import { useUIStore } from '@/store/ui'

type ToolAgg = {
  tool_name: string
  total: number
  success: number
  failed: number
  last_at?: string | null
}

function asJsonPretty(v: unknown) {
  try {
    return JSON.stringify(v ?? {}, null, 2)
  } catch {
    return String(v)
  }
}

function fmtTime(s?: string | null) {
  if (!s) return ''
  return s.replace('T', ' ').replace('Z', '')
}

export default function MCPReportPanel() {
  const mcpreportOpen = useUIStore(s => s.mcpreportOpen)
  const active = useUIStore(s => s.activeMCPReport) // { triggerId, stageId, mcpName } | null
  const closeMCPReport = useUIStore(s => s.closeMCPReport)

  const triggerId = active?.triggerId ?? null
  const stageId = active?.stageId ?? null
  const mcpName = active?.mcpName ?? null

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [summary, setSummary] = useState<{
    total: number
    success: number
    failed: number
    last_at?: string | null
  } | null>(null)

  const [toolAggs, setToolAggs] = useState<ToolAgg[]>([])
  const [items, setItems] = useState<
    Array<{
      _id: string
      tool_name?: string | null
      success?: boolean
      created_at?: string | null
      request?: Record<string, unknown>
      response?: Record<string, unknown>
    }>
  >([])

  const [selectedTool, setSelectedTool] = useState<string | null>(null)
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null)
  const detailReqSeqRef = useRef(0)

  const selectedEvidence = useMemo(() => {
    if (!selectedEvidenceId) return null
    return items.find(x => x._id === selectedEvidenceId) ?? null
  }, [items, selectedEvidenceId])

  const filteredItems = useMemo(() => {
    if (!selectedTool) return items
    return items.filter(x => (x.tool_name ?? '(unknown)') === selectedTool)
  }, [items, selectedTool])

  useEffect(() => {
    if (!mcpreportOpen) return
    if (!triggerId || !stageId || !mcpName) return

    let alive = true
    ;(async () => {
      try {
        setLoading(true)
        setError(null)
        setSummary(null)
        setToolAggs([])
        setItems([])
        setSelectedTool(null)
        setSelectedEvidenceId(null)
        detailReqSeqRef.current += 1

        // 1) summary (전체 MCP 요약 중에서 해당 mcp만 골라쓰기)
        const s = await getMcpSummary(triggerId, stageId)
        const row = s.items?.find(x => x.mcp_name === mcpName)

        const total = row?.total ?? 0
        const success = row?.success ?? 0
        const failed = row?.failed ?? 0
        const last_at = row?.last_at ?? null

        // 2) evidences list (payload는 기본 false로 두고, evidence 클릭 시 단건 조회로 가져오기)
        const list = await getMcpEvidences(triggerId, {
          mcp_name: mcpName,
          stage_id: stageId,
          limit: 500,
          include_payload: false,
        })

        if (!alive) return

        const baseItems = (list.items ?? []).map(x => ({
          _id: x._id,
          tool_name: x.tool_name ?? '(unknown)',
          success: x.success,
          created_at: x.created_at ?? null,
          request: undefined,
          response: undefined,
        }))

        // tool별 집계
        const aggMap = new Map<string, ToolAgg>()
        for (const it of baseItems) {
          const tn = it.tool_name ?? '(unknown)'
          const prev = aggMap.get(tn) ?? { tool_name: tn, total: 0, success: 0, failed: 0 }
          prev.total += 1
          if (it.success === true) prev.success += 1
          if (it.success === false) prev.failed += 1
          const cur = it.created_at
          if (cur && (!prev.last_at || cur > prev.last_at)) prev.last_at = cur
          aggMap.set(tn, prev)
        }

        const aggs = Array.from(aggMap.values()).sort((a, b) => {
          const aa = a.last_at ?? ''
          const bb = b.last_at ?? ''
          if (!aa && !bb) return 0
          if (!aa) return 1
          if (!bb) return -1
          return bb.localeCompare(aa)
        })

        setSummary({ total, success, failed, last_at })
        setItems(baseItems)
        setToolAggs(aggs)

        // 초기 선택: tool 1개 자동 선택
        if (aggs.length > 0) setSelectedTool(aggs[0].tool_name)
      } catch (e: unknown) {
        if (!alive) return
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
      } finally {
        if (alive) setLoading(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [mcpreportOpen, triggerId, stageId, mcpName])

  // evidence 클릭 시: 단건 payload 가져와서 items 업데이트
  const onSelectEvidence = async (evidenceId: string) => {
    if (!triggerId || !stageId || !mcpName) return

    setSelectedEvidenceId(evidenceId)

    // 요청 순번 증가 (race 방지)
    const mySeq = ++detailReqSeqRef.current

    try {
      const full = await getMcpEvidenceDetail(evidenceId)

      // 가장 최신 요청만 반영
      if (mySeq !== detailReqSeqRef.current) return

      setItems(prev =>
        prev.map(x =>
          x._id === evidenceId
            ? {
                ...x,
                request: full.request ?? x.request,
                response: full.response ?? x.response,
                tool_name: full.tool_name ?? x.tool_name,
                success: full.success ?? x.success,
                created_at: full.created_at ?? x.created_at,
              }
            : x
        )
      )
    } catch (err) {
      console.warn('[MCPReportPanel] getMcpEvidenceDetail failed', err)
    }
  }

  if (!mcpreportOpen || !active) return null

  return (
    <div
      style={{
        overflow: 'hidden',
        borderRadius: 16,
        background: 'rgba(255,255,255,0.92)',
        border: '1px solid rgba(15,23,42,0.08)',
        display: 'grid',
        gridTemplateRows: 'auto 1fr',
        minHeight: 0,
        height: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 12px',
          borderBottom: '1px solid rgba(15,23,42,0.08)',
        }}
      >
        <strong style={{ fontSize: 14, color: '#0f172a' }}>MCP Report</strong>
        <span style={{ fontSize: 13, fontWeight: 700, color: '#1f2937' }}>{mcpName}</span>
        <span style={{ fontSize: 12, color: '#64748b' }}>stage {stageId}</span>
        <span style={{ fontSize: 11, color: '#94a3b8' }}>trigger {triggerId}</span>

        <button
          aria-label="Close MCP report"
          onClick={closeMCPReport}
          style={{
            marginLeft: 'auto',
            padding: '6px 10px',
            borderRadius: 10,
            border: '1px solid rgba(15,23,42,0.08)',
            background: '#fff',
            fontSize: 12,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          Close
        </button>
      </div>

      {/* Body */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '280px 1fr',
          minHeight: 0,
        }}
      >
        {/* Left */}
        <aside
          style={{
            borderRight: '1px solid rgba(15,23,42,0.06)',
            padding: 12,
            overflow: 'auto',
            minHeight: 0,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 800, color: '#334155', marginBottom: 8 }}>
            Plugins / Tools
          </div>

          {loading && <div style={{ fontSize: 12, color: '#64748b' }}>불러오는 중…</div>}
          {error && <div style={{ fontSize: 12, color: '#ef4444' }}>오류: {error}</div>}

          {summary && (
            <div
              style={{
                border: '1px solid rgba(15,23,42,0.08)',
                borderRadius: 12,
                padding: 10,
                background: '#fff',
                marginBottom: 10,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: '#475569' }}>Total</span>
                <b>{summary.total}</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: '#475569' }}>Success</span>
                <b style={{ color: '#16a34a' }}>{summary.success}</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: '#475569' }}>Failed</span>
                <b style={{ color: '#ef4444' }}>{summary.failed}</b>
              </div>
              {summary.last_at && (
                <div style={{ marginTop: 6, fontSize: 11, color: '#94a3b8' }}>
                  last: {fmtTime(summary.last_at)}
                </div>
              )}
            </div>
          )}

          <div style={{ display: 'grid', gap: 6 }}>
            {toolAggs.map(t => {
              const active = selectedTool === t.tool_name
              return (
                <button
                  key={t.tool_name}
                  onClick={() => {
                    setSelectedTool(t.tool_name)
                    setSelectedEvidenceId(null)
                  }}
                  style={{
                    textAlign: 'left',
                    padding: '8px 10px',
                    borderRadius: 12,
                    border: active
                      ? '1px solid rgba(37,99,235,0.35)'
                      : '1px solid rgba(15,23,42,0.06)',
                    background: active ? 'rgba(37,99,235,0.08)' : 'rgba(255,255,255,0.85)',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>
                    {t.tool_name}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                    {t.total} runs · <span style={{ color: '#16a34a' }}>{t.success}</span> ok ·{' '}
                    <span style={{ color: '#ef4444' }}>{t.failed}</span> fail
                  </div>
                  {t.last_at && (
                    <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
                      last: {fmtTime(t.last_at)}
                    </div>
                  )}
                </button>
              )
            })}
            {!loading && toolAggs.length === 0 && (
              <div style={{ fontSize: 12, color: '#64748b' }}>표시할 tool이 없습니다.</div>
            )}
          </div>
        </aside>

        {/* Right */}
        <main
          style={{
            minHeight: 0,
            overflow: 'hidden',
            display: 'grid',
            gridTemplateRows: '160px 1fr',
          }}
        >
          {/* run list */}
          <div
            style={{ padding: 12, borderBottom: '1px solid rgba(15,23,42,0.06)', overflow: 'auto' }}
          >
            <div style={{ fontSize: 12, fontWeight: 800, color: '#334155', marginBottom: 8 }}>
              Runs {selectedTool ? `— ${selectedTool}` : ''}
            </div>

            <div style={{ display: 'grid', gap: 6 }}>
              {filteredItems.map(it => {
                const active = selectedEvidenceId === it._id
                return (
                  <button
                    key={it._id}
                    onClick={() => onSelectEvidence(it._id)}
                    style={{
                      textAlign: 'left',
                      padding: '8px 10px',
                      borderRadius: 12,
                      border: active
                        ? '1px solid rgba(37,99,235,0.35)'
                        : '1px solid rgba(15,23,42,0.06)',
                      background: active ? 'rgba(37,99,235,0.08)' : '#fff',
                      cursor: 'pointer',
                      display: 'flex',
                      gap: 10,
                      alignItems: 'center',
                    }}
                  >
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 999,
                        background:
                          it.success === false
                            ? '#ef4444'
                            : it.success === true
                              ? '#16a34a'
                              : '#94a3b8',
                        flex: '0 0 auto',
                      }}
                    />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>
                        {fmtTime(it.created_at) || '(time unknown)'}
                      </div>
                      <div style={{ fontSize: 11, color: '#64748b' }}>#{it._id}</div>
                    </div>
                  </button>
                )
              })}
              {!loading && filteredItems.length === 0 && (
                <div style={{ fontSize: 12, color: '#64748b' }}>선택된 tool의 run이 없습니다.</div>
              )}
            </div>
          </div>

          {/* request/response */}
          <div style={{ minHeight: 0, overflow: 'auto', padding: 12 }}>
            {!selectedEvidence && (
              <div style={{ fontSize: 13, color: '#64748b' }}>좌측 Runs에서 항목을 선택하세요.</div>
            )}

            {selectedEvidence && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={box}>
                  <div style={boxTitle}>Request</div>
                  <pre style={pre}>{asJsonPretty(selectedEvidence.request ?? {})}</pre>
                </div>

                <div style={box}>
                  <div style={boxTitle}>Response</div>
                  <pre style={pre}>{asJsonPretty(selectedEvidence.response ?? {})}</pre>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

const box: React.CSSProperties = {
  background: '#fff',
  border: '1px solid rgba(15,23,42,0.08)',
  borderRadius: 12,
  overflow: 'hidden',
}
const boxTitle: React.CSSProperties = {
  padding: '10px 12px',
  borderBottom: '1px solid rgba(15,23,42,0.06)',
  fontSize: 12,
  fontWeight: 900,
  color: '#0f172a',
}
const pre: React.CSSProperties = {
  margin: 0,
  padding: 12,
  background: '#0b1220',
  color: '#e5e7eb',
  fontSize: 12,
  lineHeight: 1.55,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}
