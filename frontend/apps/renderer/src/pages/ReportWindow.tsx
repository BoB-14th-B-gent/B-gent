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
    sections?: Record<string, unknown>
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

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}
function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}
function asString(v: unknown): string {
  return typeof v === 'string' ? v : String(v ?? '')
}
function cleanLine(s: unknown): string {
  // ✅ any 제거
  const v = asString(s).trim()
  if (!v) return ''
  if (v === '---' || v === '—' || v === '–––') return ''
  return v
}

function adaptStructuredToView(doc: BackendReportDoc | null): ViewReport | null {
  const sections = doc?.structured?.sections
  if (!sections) return null

  // sections는 Record<string, unknown> 이므로 안전하게 접근
  const execSrc = asArray(sections['executive summary'])
  const exec: ViewExecItem[] = execSrc
    .map(s => {
      if (typeof s === 'string') return { bullet: cleanLine(s) }
      if (isRecord(s)) {
        return {
          bullet: cleanLine(s['bullet'] ?? s),
          source: typeof s['source'] === 'string' ? s['source'] : undefined,
        }
      }
      return { bullet: cleanLine(s) }
    })
    .filter(x => !!x.bullet)

  const tlSrc = asArray(sections['timeline'])
  const tl: ViewTimelineItem[] = tlSrc.map(t => {
    const r = isRecord(t) ? t : {}
    return {
      timestamp: cleanLine(r['timestamp_iso'] ?? r['timestamp_raw'] ?? ''),
      event: cleanLine(r['description'] ?? ''),
      evidence: cleanLine(r['source'] ?? ''),
    }
  })

  const mitreSrc = asArray(sections['mitre att&ck mapping'])
  const mitre: ViewMitreItem[] = mitreSrc
    .map(m0 => {
      const m = isRecord(m0) ? m0 : {}
      if (m['technique_id'] || m['technique_name'] || m['tactic']) {
        const techniqueName = cleanLine(m['technique_name'] ?? '')
        const relevance = cleanLine(m['relevance'] ?? '')
        return {
          action: cleanLine(m['tactic'] ?? ''),
          ttpId: cleanLine(m['technique_id'] ?? ''),
          explanation: cleanLine(`${techniqueName}${relevance ? ` — ${relevance}` : ''}`),
        }
      }
      return {
        action: cleanLine(m['ttp_id'] ?? ''),
        ttpId: cleanLine(m['description'] ?? ''),
        explanation: cleanLine(m['observed'] ?? ''),
      }
    })
    .filter(x => x.action || x.ttpId || x.explanation)

  // attack details
  const detailsRaw = sections['attack details']
  let attackDetails: ViewAttackDetail[] = []
  if (isRecord(detailsRaw)) {
    const items = asArray(detailsRaw['items']).map(b => ({
      artifact: 'details',
      bullet: cleanLine(b),
    }))
    const rawEx = asArray(detailsRaw['raw_excerpts']).map(r => {
      const line = cleanLine(r)
      return { artifact: 'excerpt', bullet: line, raw: line }
    })
    attackDetails = [...items, ...rawEx].filter(x => !!x.bullet)
  }

  // iocs
  const iocsSrc = asArray(sections['iocs & evidence'])
  const iocsAlt = asArray(sections['iocs'])
  const baseIocs = iocsSrc.length ? iocsSrc : iocsAlt

  const iocs: ViewIocItem[] = baseIocs
    .map(i0 => {
      const i = isRecord(i0) ? i0 : {}
      return {
        ioc: cleanLine(i['indicator'] ?? i['IOC'] ?? ''),
        type: cleanLine(i['type'] ?? ''),
        source: cleanLine(i['source'] ?? ''),
        timestamp: cleanLine(i['timestamp_iso'] ?? i['timestamp_raw'] ?? ''),
        context: cleanLine(i['context'] ?? i['notes'] ?? i['raw_snippet'] ?? i['snippet'] ?? ''),
      }
    })
    .filter(x => !!x.ioc)

  // additional
  const addSrc = asArray(sections['additional evidence required'])
  const additionalNeeded: ViewAdditionalItem[] = addSrc
    .map(s => {
      if (typeof s === 'string') return { what: cleanLine(s) }
      if (isRecord(s)) {
        return {
          what: cleanLine(s['what'] ?? s),
          purpose: typeof s['purpose'] === 'string' ? s['purpose'] : undefined,
          successCriteria:
            typeof s['successCriteria'] === 'string' ? s['successCriteria'] : undefined,
        }
      }
      return { what: cleanLine(s) }
    })
    .filter(x => !!x.what)

  return {
    date: doc?.created_at,
    execSummary: exec,
    timeline: tl,
    mitre,
    attackDetails,
    iocs,
    additionalNeeded,
  }
}

function fallbackFromRaw(doc: BackendReportDoc): ViewReport {
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
  const stageIdParamRaw = search.get('stageId')
  const stageIdParam = stageIdParamRaw ? Number(stageIdParamRaw) : null
  const safeStageId = Number.isFinite(stageIdParam) ? stageIdParam : null

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

        if (!alive) return

        setResolvedId(doc._id ?? null)
        setHeaderText(extractHeaderTitle(doc))

        const adapted = adaptStructuredToView(doc)
        if (adapted) setView(adapted)
        else setView(fallbackFromRaw(doc))

        window.api?.notifyTotalReportLoaded?.({
          stageId: safeStageId ?? undefined,
          reportId: String(doc._id ?? reportIdParam ?? ''),
        })
      } catch (e: unknown) {
        if (!alive) return
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
        setView(null)
        setResolvedId(null)
      } finally {
        if (!alive) setLoading(false)
        setLoading(false)
      }
    }

    run()
    return () => {
      alive = false
    }
  }, [reportIdParam, stageIdParam, safeStageId])

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
