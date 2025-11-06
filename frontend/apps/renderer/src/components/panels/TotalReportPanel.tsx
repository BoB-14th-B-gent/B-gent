// src/components/panels/ReportPanel.tsx
import { useEffect, useRef } from 'react'
import { useUIStore } from '@/store/ui'
import { dummyReport } from '@/data/dummyReports'
import { buildReportMarkdown } from '@/utils/MarkdownExport'

export default function ReportPanel() {
  const { totalreportOpen, activeTotalReportId, closeTotalReport } = useUIStore()
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeTotalReport() }
    if (totalreportOpen) {
      document.addEventListener('keydown', onKey)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [totalreportOpen, closeTotalReport])

  if (!totalreportOpen) return null

  const onExportMD = () => {
    const md = buildReportMarkdown(dummyReport)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Bgent_Report_${dummyReport.date ?? 'report'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div
      aria-modal
      role="dialog"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'grid',
        placeItems: 'center',
        background: 'rgba(2,8,23,0.45)',
        backdropFilter: 'blur(2px)',
      }}
      onClick={closeTotalReport}
    >
      <div
        ref={dialogRef}
        onClick={e => e.stopPropagation()}
        style={{
          width: 'min(96vw, 1280px)',
          height: 'min(92vh, 900px)',
          background: 'rgba(255,255,255,0.92)',
          border: '1px solid rgba(15,23,42,0.08)',
          borderRadius: 16,
          boxShadow: '0 20px 60px rgba(2,8,23,0.35)',
          backdropFilter: 'saturate(120%) blur(8px)',
          display: 'grid',
          gridTemplateRows: 'auto 1fr',
          overflow: 'hidden',
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
          <strong style={{ fontSize: 16, color: '#0f172a' }}>
            Total Report {activeTotalReportId ? `#${activeTotalReportId}` : ''}
          </strong>

          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button title="Export: MD" style={iconBtn} onClick={onExportMD}>
              Download
            </button>
            <button title="닫기" style={closeBtn} onClick={closeTotalReport}>
              ✕
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
              <a href="#exec" style={tocLink}>01 Executive Summary</a>
              <a href="#timeline" style={tocLink}>02 Timeline / Progression</a>
              <a href="#mitre" style={tocLink}>03 MITRE ATT&CK Mapping</a>
              <a href="#details" style={tocLink}>04 Attack Details</a>
              <a href="#iocs" style={tocLink}>05 IoCs & Evidence</a>
              <a href="#add" style={tocLink}>06 Additional Evidence Required</a>
            </nav>
          </aside>

          <main style={{ padding: '16px 18px', minHeight: 0, overflow: 'auto' }}>
            <section id="exec" style={sectionBox}>
              <h3 style={h3}>01 Executive Summary</h3>
              <ul style={ul}>
                {dummyReport.execSummary.map((i, idx) => (
                  <li key={idx}>{i.bullet}{i.source ? ` (${i.source})` : ''}</li>
                ))}
              </ul>
            </section>

            <section id="timeline" style={sectionBox}>
              <h3 style={h3}>02 Timeline / Progression</h3>
              <ul style={ul}>
                {dummyReport.timeline.map((t, idx) => (
                  <li key={idx}>
                    {t.timestamp} | {t.event} | {t.evidence}
                  </li>
                ))}
              </ul>
            </section>

            <section id="mitre" style={sectionBox}>
              <h3 style={h3}>03 MITRE ATT&CK Mapping</h3>
              <ul style={ul}>
                {dummyReport.mitre.map((m, idx) => (
                  <li key={idx}>
                    {m.action} — <b>{m.ttpId}</b> ({m.explanation})
                  </li>
                ))}
              </ul>
            </section>

            <section id="details" style={sectionBox}>
              <h3 style={h3}>04 Attack Details</h3>
              {dummyReport.attackDetails.map((d, idx) => (
                <div key={idx} style={{ marginBottom: 12 }}>
                  <div>- <b>{d.artifact}</b>: {d.bullet}</div>
                  <pre style={pre}>{d.raw}</pre>
                </div>
              ))}
            </section>

            <section id="iocs" style={sectionBox}>
              <h3 style={h3}>05 IoCs & Evidence</h3>
              <ul style={ul}>
                {dummyReport.iocs.map((i, idx) => (
                  <li key={idx}>
                    {i.ioc} — {i.type} | {i.source} {i.timestamp ? `@ ${i.timestamp}` : ''}{i.context ? ` (${i.context})` : ''}
                  </li>
                ))}
              </ul>
            </section>

            <section id="add" style={sectionBox}>
              <h3 style={h3}>06 Additional Evidence Required</h3>
              <ul style={ul}>
                {dummyReport.additionalNeeded.map((a, idx) => (
                  <li key={idx}>
                    <b>{a.what}</b> — 목적: {a.purpose} · 성공 기준: {a.successCriteria}
                  </li>
                ))}
              </ul>
            </section>
          </main>
        </div>
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

const closeBtn: React.CSSProperties = {
  ...iconBtn,
  width: 32,
  textAlign: 'center',
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
const ul: React.CSSProperties = { margin: '6px 0 0', paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }
const pre: React.CSSProperties = {
  background: '#0f172a',
  color: 'white',
  padding: 10,
  borderRadius: 8,
  whiteSpace: 'pre-wrap',
  fontSize: 12,
  lineHeight: 1.55,
}