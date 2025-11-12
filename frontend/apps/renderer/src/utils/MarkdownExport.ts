type ExecSummaryItem = { bullet: string; source?: string }
type TimelineItem = { timestamp?: string; event?: string; evidence?: string }
type MitreItem = { action?: string; ttpId?: string; explanation?: string }
type AttackDetailItem = { artifact?: string; bullet?: string; raw?: string }
type IoCItem = {
  ioc?: string
  type?: string
  timestamp?: string
  source?: string
  context?: string
}
type AdditionalNeededItem = { what?: string; purpose?: string; successCriteria?: string }

type AnyReport = {
  title?: string
  date?: string
  version?: string
  execSummary?: ExecSummaryItem[]
  timeline?: TimelineItem[]
  mitre?: MitreItem[]
  attackDetails?: AttackDetailItem[]
  iocs?: IoCItem[]
  additionalNeeded?: AdditionalNeededItem[]
  rawAppendix?: string
}

const esc = (s: string | undefined | null) => String(s ?? '').replace(/\|/g, '\\|')

const nonEmpty = (s?: string | null) => (s && s.trim().length ? s : '')

export function buildReportMarkdown(
  rInput: AnyReport,
  meta?: { title?: string; version?: string }
) {
  const r: AnyReport = {
    ...rInput,
    execSummary: rInput.execSummary ?? [],
    timeline: rInput.timeline ?? [],
    mitre: rInput.mitre ?? [],
    attackDetails: rInput.attackDetails ?? [],
    iocs: rInput.iocs ?? [],
    additionalNeeded: rInput.additionalNeeded ?? [],
  }

  const title = meta?.title ?? r.title ?? 'Incident Analysis Report'
  const version = meta?.version ?? r.version ?? ''

  const header = `# ${title}
- Date: ${nonEmpty(r.date) ?? ''}
- Version: ${version}`.trim()

  const execLines = (r.execSummary ?? [])
    .slice(0, 5)
    .map(i => `- ${nonEmpty(i.bullet) || '-'}${i.source ? ` (${i.source})` : ''}`)
  const exec = `## 1. Executive Summary
${execLines.length ? execLines.join('\n') : '- (no summary)'}
`

  const timelineLines = (r.timeline ?? []).map(
    t =>
      `- ${nonEmpty(t.timestamp) || '-'} | ${nonEmpty(t.event) || '-'}${t.evidence ? ` | ${t.evidence}` : ''}`
  )
  const timeline = `## 2. Timeline / Progression
${timelineLines.length ? timelineLines.join('\n') : '- (no timeline)'}
`

  const mitreRows = (r.mitre ?? [])
    .map(m => `| ${esc(m.action)} | ${esc(m.ttpId)} | ${esc(m.explanation)} |`)
    .join('\n')
  const mitre = `## 3. MITRE ATT&CK Mapping
| Action | TTP ID | Explanation/Evidence |
| --- | --- | --- |
${mitreRows || '| (no mapped actions) | - | - |'}
`

  const attackBlocks = (r.attackDetails ?? []).map(d => {
    const head = `- ${nonEmpty(d.artifact) || 'detail'}: ${nonEmpty(d.bullet) || ''}`.trimEnd()
    if (nonEmpty(d.raw)) {
      return `${head}\n\n  \`\`\`\n  ${String(d.raw).replace(/\n/g, '\n  ')}\n  \`\`\``
    }
    return head
  })
  const attack = `## 4. Attack Details
${attackBlocks.length ? attackBlocks.join('\n\n') : '- (no details)'}
`

  const iocRows = (r.iocs ?? [])
    .map(
      i =>
        `| ${esc(i.ioc)} | ${esc(i.type)} | ${esc(i.timestamp)} | ${esc(i.source)} | ${esc(i.context)} |`
    )
    .join('\n')
  const iocs = `## 5. IoCs & Evidence
| IOC | Type | Timestamp | Source | Context |
| --- | --- | --- | --- | --- |
${iocRows || '| - | - | - | - | - |'}
`

  const addLines = (r.additionalNeeded ?? []).map(
    a =>
      `- **${nonEmpty(a.what) || '-'}**${a.purpose ? ` — 목적: ${a.purpose}` : ''}${a.successCriteria ? ` · 성공 기준: ${a.successCriteria}` : ''}`
  )
  const add = `## 6. Additional Evidence Required
${addLines.length ? addLines.join('\n') : '- (none)'}
`

  const appendix = nonEmpty(r.rawAppendix)
    ? `\n\n---\n\n## Appendix (Raw)\n\`\`\`markdown\n${r.rawAppendix}\n\`\`\`\n`
    : ''

  return [header, exec, timeline, mitre, attack, iocs, add].join('\n\n') + appendix
}
