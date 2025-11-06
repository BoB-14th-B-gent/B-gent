import type { ReportData } from './reports'

const esc = (s: string) => s.replace(/\|/g, '\\|')

export function buildReportMarkdown(r: ReportData) {
  const header =
`# ${r.title ?? 'Incident Analysis Report'}
- Date: ${r.date ?? ''}
- Version: ${r.version ?? ''}`.trim()

  const exec =
`## 1. Executive Summary
${r.execSummary.slice(0, 5).map(i => `- ${i.bullet}${i.source ? ` (${i.source})` : ''}`).join('\n')}`

  const timeline =
`## 2. Timeline / Progression
${r.timeline.map(t => `- ${t.timestamp} | ${t.event} | ${t.evidence}`).join('\n')}`

  const mitreRows = r.mitre.map(m =>
    `| ${esc(m.action)} | ${esc(m.ttpId)} | ${esc(m.explanation)} |`
  ).join('\n')
  const mitre =
`## 3. MITRE ATT&CK Mapping
| Action | TTP ID | Explanation/Evidence |
| --- | --- | --- |
${mitreRows || '| (no mapped actions) | - | - |'}`

  const attack =
`## 4. Attack Details
${r.attackDetails.map(d =>
  `- ${d.artifact}: ${d.bullet}\n\n  > ${d.raw.split('\n').map(l => l.trim()).join('\n  > ')}`
).join('\n\n')}`

  const iocRows = r.iocs.map(i =>
    `| ${esc(i.ioc)} | ${esc(i.type)} | ${esc(i.timestamp ?? '')} | ${esc(i.source)} | ${esc(i.context ?? '')} |`
  ).join('\n')
  const iocs =
`## 5. IoCs & Evidence
| IOC | Type | Timestamp | Source | Context |
| --- | --- | --- | --- | --- |
${iocRows || '| - | - | - | - | - |'}`

  const add =
`## 6. Additional Evidence Required
${r.additionalNeeded.map(a =>
  `- **${a.what}** — 목적: ${a.purpose} · 성공 기준: ${a.successCriteria}`
).join('\n')}`

  const appendix = r.rawAppendix
    ? `\n\n---\n\n## Appendix (Raw)\n\`\`\`markdown\n${r.rawAppendix}\n\`\`\`\n`
    : ''

  return [header, exec, timeline, mitre, attack, iocs, add].join('\n\n') + appendix
}