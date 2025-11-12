import { useEffect, useMemo, useState } from 'react'
import { buildReportMarkdown } from '@/utils/MarkdownExport'

type BackendReportDoc = {
  _id?: string
  report: string
  conversation_id?: string | null
  stage_id?: number | null
  trigger_id?: string | null
  created_at?: string
  structured?: {
    header?: string
    sections?: Record<string, any>
  }
}

type ViewExecItem = { bullet: string; source?: string }
type ViewTimelineItem = { timestamp?: string; event: string; evidence?: string }
type ViewMitreItem = { action: string; ttpId: string; explanation: string }
type ViewAttackDetail = { artifact: string; bullet: string; raw?: string }
type ViewIocItem = {
  ioc: string
  type?: string
  source?: string
  timestamp?: string
  context?: string
}
type ViewAdditionalItem = { what: string; purpose?: string; successCriteria?: string }

type ViewReport = {
  date?: string
  execSummary: ViewExecItem[]
  timeline: ViewTimelineItem[]
  mitre: ViewMitreItem[]
  attackDetails: ViewAttackDetail[]
  iocs: ViewIocItem[]
  additionalNeeded: ViewAdditionalItem[]
}

const BASE = import.meta.env.VITE_BACKEND_URL
const isObjectId = (s?: string | null) => !!s && /^[0-9a-fA-F]{24}$/.test(s)

async function fetchLatestReport(): Promise<BackendReportDoc | null> {
  const res = await fetch(`${BASE}/reports/latest`, {
    headers: { 'Content-Type': 'application/json' },
  })
  if (res.status === 404) return null
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`GET /reports/latest failed: ${res.status} ${res.statusText} — ${t}`)
  }
  return (await res.json()) as BackendReportDoc
}

async function fetchReport(reportId: string): Promise<BackendReportDoc> {
  const res = await fetch(`${BASE}/reports/${encodeURIComponent(reportId)}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`GET /reports/${reportId} failed: ${res.status} ${res.statusText} — ${t}`)
  }
  return (await res.json()) as BackendReportDoc
}

function adaptStructuredToView(doc: BackendReportDoc | null): ViewReport | null {
  if (!doc?.structured?.sections) return null
  const S = doc.structured.sections

  const exec: ViewExecItem[] = Array.isArray(S['executive summary'])
    ? (S['executive summary'] as any[]).map(s =>
        typeof s === 'string'
          ? { bullet: s }
          : { bullet: String(s?.bullet ?? s ?? ''), source: s?.source }
      )
    : []

  const tl: ViewTimelineItem[] = Array.isArray(S['timeline / progression'])
    ? (S['timeline / progression'] as any[]).map(t => ({
        timestamp: t?.timestamp_iso ?? t?.timestamp_raw ?? '',
        event: t?.description ?? '',
        evidence: t?.source ?? '',
      }))
    : Array.isArray(S['timeline'])
      ? (S['timeline'] as any[]).map(t => ({
          timestamp: t?.timestamp_iso ?? t?.timestamp_raw ?? '',
          event: t?.description ?? '',
          evidence: t?.source ?? '',
        }))
      : []

  const mitre: ViewMitreItem[] = Array.isArray(S['mitre att&ck mapping'])
    ? (S['mitre att&ck mapping'] as any[]).map(m => ({
        action: m?.action ?? '',
        ttpId: m?.ttp_id ?? m?.ttp ?? '',
        explanation: m?.evidence ?? m?.explanation ?? '',
      }))
    : []

  const detailsRaw = S['attack details']
  const attackDetails: ViewAttackDetail[] = detailsRaw
    ? [
        ...(Array.isArray(detailsRaw.items)
          ? detailsRaw.items.map((b: string) => ({ artifact: 'details', bullet: b }))
          : []),
        ...(Array.isArray(detailsRaw.raw_excerpts)
          ? detailsRaw.raw_excerpts.map((r: string) => ({ artifact: 'excerpt', bullet: r, raw: r }))
          : []),
      ]
    : []

  const iocs: ViewIocItem[] = Array.isArray(S['iocs & evidence'])
    ? (S['iocs & evidence'] as any[]).map(i => ({
        ioc: i?.indicator ?? i?.IOC ?? '',
        type: i?.type ?? '',
        source: i?.source ?? '',
        timestamp: i?.timestamp_iso ?? i?.timestamp_raw ?? '',
        context: i?.context ?? '',
      }))
    : Array.isArray(S['iocs'])
      ? (S['iocs'] as any[]).map(i => ({
          ioc: i?.indicator ?? '',
          type: i?.type ?? '',
          source: i?.source ?? '',
          timestamp: i?.timestamp_iso ?? i?.timestamp_raw ?? '',
          context: i?.context ?? '',
        }))
      : []

  const additionalNeeded: ViewAdditionalItem[] = Array.isArray(S['additional evidence required'])
    ? (S['additional evidence required'] as any[]).map(s =>
        typeof s === 'string'
          ? { what: s }
          : {
              what: String(s?.what ?? s ?? ''),
              purpose: s?.purpose,
              successCriteria: s?.successCriteria,
            }
      )
    : []

  return {
    date: doc.created_at,
    execSummary: exec,
    timeline: tl,
    mitre,
    attackDetails,
    iocs,
    additionalNeeded,
  }
}

function fallbackFromRaw(doc: BackendReportDoc): ViewReport {
  const firstLine = (doc.report || '').split('\n').find(Boolean) || 'Incident Analysis Report'
  const summaryBlock = (doc.report || '')
    .split('\n')
    .slice(0, 12)
    .filter(Boolean)
    .slice(1)
    .map(line => ({ bullet: line }) as ViewExecItem)

  return {
    date: doc.created_at,
    execSummary: summaryBlock.length ? summaryBlock : [{ bullet: doc.report || '(empty report)' }],
    timeline: [],
    mitre: [],
    attackDetails: [],
    iocs: [],
    additionalNeeded: [],
  }
}

export default function ReportWindow() {
  const search = new URLSearchParams(location.hash.split('?')[1] || '')
  const reportIdParam = search.get('reportId') || undefined

  const [loading, setLoading] = useState<boolean>(!!reportIdParam)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<ViewReport | null>(null)
  const [resolvedId, setResolvedId] = useState<string | null>(null)
  const [headerText, setHeaderText] = useState<string | null>(null)
  const current = useMemo(
    () =>
      view ?? {
        execSummary: [],
        timeline: [],
        mitre: [],
        attackDetails: [],
        iocs: [],
        additionalNeeded: [],
      },
    [view]
  )
  const safeName = (raw: string) => raw.replace(/[\\/:*?"<>|]+/g, '_').replace(/\s+/g, '_')

  const onExportMD = async () => {
    const md = buildReportMarkdown(current)
    const base = safeName(current.date ?? resolvedId ?? 'report')
    const filename = `Bgent_Report_${base}.md`

    if (window.api?.saveFile) {
      try {
        await window.api.saveFile({
          data: md,
          defaultPath: filename,
          filters: [{ name: 'Markdown', extensions: ['md'] }],
        })
        return
      } catch (e) {
        console.error('[report] saveFile failed, falling back to browser download:', e)
      }
    }

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function extractHeaderTitle(doc: BackendReportDoc): string {
    const h = doc.structured?.header?.trim()
    if (h) return h

    const first = (doc.report || '').split('\n').find(Boolean)?.trim()
    if (first) return first

    return 'Incident Analysis Report'
  }

  useEffect(() => {
    let alive = true

    async function run() {
      try {
        setLoading(true)
        setError(null)

        let doc: BackendReportDoc | null = null

        if (isObjectId(reportIdParam || '')) {
          doc = await fetchReport(reportIdParam!)
        } else {
          doc = await fetchLatestReport()
        }

        if (!doc) {
          throw new Error('표시할 보고서가 없습니다.')
        }

        setResolvedId(doc._id ?? null)
        setHeaderText(extractHeaderTitle(doc))

        const adapted = adaptStructuredToView(doc)
        if (!alive) return
        if (adapted) {
          setView(adapted)
        } else {
          setView(fallbackFromRaw(doc))
        }
      } catch (e: any) {
        if (!alive) return
        setError(e?.message ?? String(e))
        setView(null)
        setResolvedId(null)
      } finally {
        if (!alive) return
        setLoading(false)
      }
    }

    run()
    return () => {
      alive = false
    }
  }, [reportIdParam])

  return (
    <div
      style={{
        height: '100vh',
        width: '100vw',
        display: 'grid',
        gridTemplateRows: 'auto 1fr',
        background: 'rgba(255,255,255,0.92)',
        fontFamily:
          "Pretendard, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif",
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '12px 14px',
          borderBottom: '1px solid rgba(15,23,42,0.08)',
          background: 'linear-gradient(180deg, rgba(255,255,255,.9), rgba(255,255,255,.6))',
        }}
      >
        <strong style={{ fontSize: 16, color: '#0f172a' }}>Total Report</strong>
        {headerText && (
          <span style={{ marginLeft: 10, fontSize: 13, color: '#475569' }}>{headerText}</span>
        )}
        {resolvedId && (
          <span style={{ marginLeft: 8, fontSize: 11, color: '#94a3b8' }}>#{resolvedId}</span>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button
            title="Export: MD"
            style={iconBtn}
            onClick={onExportMD}
            disabled={loading || !current}
          >
            Download
          </button>
        </div>
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '240px 1fr',
          height: '100%',
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        <aside
          style={{
            borderRight: '1px solid rgba(15,23,42,0.06)',
            padding: 12,
            minHeight: 0,
            overflow: 'auto',
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 700, color: '#334155', marginBottom: 8 }}>
            목차
          </div>
          <nav style={{ display: 'grid', gap: 6, fontSize: 13 }}>
            <a href="#exec" style={tocLink}>
              01 Executive Summary
            </a>
            <a href="#timeline" style={tocLink}>
              02 Timeline / Progression
            </a>
            <a href="#mitre" style={tocLink}>
              03 MITRE ATT&CK Mapping
            </a>
            <a href="#details" style={tocLink}>
              04 Attack Details
            </a>
            <a href="#iocs" style={tocLink}>
              05 IoCs & Evidence
            </a>
            <a href="#add" style={tocLink}>
              06 Additional Evidence Required
            </a>
          </nav>
        </aside>

        <main style={{ padding: '16px 18px', minHeight: 0, overflow: 'auto' }}>
          {loading && (
            <div style={{ padding: 16, fontSize: 13, color: '#475569' }}>불러오는 중…</div>
          )}
          {error && (
            <div style={{ padding: 16, fontSize: 13, color: '#ef4444' }}>오류: {error}</div>
          )}

          {!loading && !current && !error && (
            <div style={{ padding: 16, fontSize: 13, color: '#64748b' }}>
              표시할 보고서가 없습니다.
            </div>
          )}

          {current && (
            <>
              <section id="exec" style={sectionBox}>
                <h3 style={h3}>01 Executive Summary</h3>
                <ul style={ul}>
                  {current.execSummary.length ? (
                    current.execSummary.map((i, idx) => (
                      <li key={idx}>
                        - {i.bullet}
                        {i.source ? ` (${i.source})` : ''}
                      </li>
                    ))
                  ) : (
                    <li style={{ color: '#64748b' }}>—</li>
                  )}
                </ul>
              </section>

              <section id="timeline" style={sectionBox}>
                <h3 style={h3}>02 Timeline / Progression</h3>
                <ul style={ul}>
                  {current.timeline.length ? (
                    current.timeline.map((t, idx) => (
                      <li key={idx}>
                        {t.timestamp ?? '—'}
                        <p style={{ marginLeft: 20 }}>
                          - {t.event || '—'}
                          {t.evidence ? ` ${t.evidence}` : ''}
                        </p>
                      </li>
                    ))
                  ) : (
                    <li style={{ color: '#64748b' }}>—</li>
                  )}
                </ul>
              </section>

              <section id="mitre" style={sectionBox}>
                <h3 style={h3}>03 MITRE ATT&CK Mapping</h3>
                <ul style={ul}>
                  {current.mitre.length ? (
                    current.mitre.map((m, idx) => (
                      <li key={idx}>
                        - {m.action || '—'}
                        <p style={{ marginLeft: 20 }}>{m.ttpId || '—'}</p>
                        <p style={{ marginLeft: 20 }}>
                          {m.explanation ? ` (${m.explanation})` : ''}
                        </p>
                      </li>
                    ))
                  ) : (
                    <li style={{ color: '#64748b' }}>—</li>
                  )}
                </ul>
              </section>

              <section id="details" style={sectionBox}>
                <h3 style={h3}>04 Attack Details</h3>
                {current.attackDetails.length ? (
                  current.attackDetails.map((d, idx) => {
                    const isExcerpt = d.artifact?.toLowerCase().includes('excerpt')
                    const isDetail = d.artifact?.toLowerCase().includes('detail')

                    return (
                      <div key={idx} style={{ marginBottom: 10 }}>
                        {isDetail ? (
                          <div style={{ fontWeight: 500, color: '#0f172a', fontSize: 14 }}>
                            • {d.bullet}
                          </div>
                        ) : (
                          <div style={{ marginLeft: 14 }}>
                            <div style={{ color: '#334155', fontSize: 14, marginTop: 6 }}>
                              ↳{' '}
                              <b style={{ color: '#0f172a', fontSize: 14, fontWeight: 500 }}>
                                {d.artifact}
                              </b>
                            </div>
                            {d.raw ? (
                              <pre
                                style={{
                                  background: '#111827',
                                  color: 'white',
                                  padding: '8px 10px',
                                  borderRadius: 8,
                                  whiteSpace: 'pre-wrap',
                                  fontSize: 12,
                                  lineHeight: 1.55,
                                  margin: '6px 0 0 24px',
                                }}
                              >
                                {d.raw}
                              </pre>
                            ) : null}
                          </div>
                        )}
                      </div>
                    )
                  })
                ) : (
                  <div style={{ color: '#64748b' }}>—</div>
                )}
              </section>

              <section id="iocs" style={sectionBox}>
                <h3 style={h3}>05 IoCs & Evidence</h3>
                <ul style={ul}>
                  {current.iocs.length ? (
                    current.iocs.map((i, idx) => (
                      <li key={idx}>
                        - {i.ioc || '-'}
                        {i.type ? ` | ${i.type}` : ''}
                        {i.source ? ` | ${i.source}` : ''}
                        {i.timestamp ? ` @ ${i.timestamp}` : ''}
                        {i.context ? ` | ${i.context}` : ''}
                      </li>
                    ))
                  ) : (
                    <li style={{ color: '#64748b' }}>—</li>
                  )}
                </ul>
              </section>

              <section id="add" style={sectionBox}>
                <h3 style={h3}>06 Additional Evidence Required</h3>
                <ul style={ul}>
                  {current.additionalNeeded.length ? (
                    current.additionalNeeded.map((a, idx) => (
                      <li key={idx}>
                        <b>- {a.what}</b>
                        {a.purpose ? ` — 목적: ${a.purpose}` : ''}
                        {a.successCriteria ? ` · 성공 기준: ${a.successCriteria}` : ''}
                      </li>
                    ))
                  ) : (
                    <li style={{ color: '#64748b' }}>—</li>
                  )}
                </ul>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

const iconBtn: React.CSSProperties = {
  padding: '6px 10px',
  borderRadius: 10,
  border: '1px solid rgba(15,23,42,0.08)',
  background: '#fff',
  fontSize: 12,
  fontWeight: 700,
  color: '#0f172a',
  cursor: 'pointer',
}
const tocLink: React.CSSProperties = {
  color: '#0f172a',
  textDecoration: 'none',
  padding: '6px 8px',
  borderRadius: 8,
  border: '1px solid rgba(15,23,42,0.06)',
  background: 'rgba(255,255,255,0.85)',
}
const sectionBox: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid rgba(15,23,42,0.08)',
  borderRadius: 12,
  padding: 14,
  marginBottom: 14,
}
const h3: React.CSSProperties = { margin: 0, marginBottom: 8, fontSize: 15, color: '#0f172a' }
const ul: React.CSSProperties = {
  margin: '6px 0 0',
  paddingLeft: 18,
  fontSize: 13,
  lineHeight: 1.6,
}
