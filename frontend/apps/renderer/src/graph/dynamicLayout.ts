import type { Node, Edge } from 'reactflow'
import type { MCPServer } from './events'

type XY = { x: number; y: number }

export const PALETTE = {
  prompt: '#90949B',
  bgent: '#AFC0CF',

  velociraptor: '#003D00',
  elastic: '#054861',
  tsk: '#F5D356',
  ghidra: '#FF8B8D',
  virustotal: '#6583FF',
  'ez-tools': '#EFEFEF',
  'consolehost-history': '#B4D0FF',
  'browser-db-parser': '#113A62',
  'lnk-parser': '#C8E4FF',
  jumplist: '#E8EAF6',
  ntfs: '#B5DAFF',
  'windows-notification': '#E3F2FD',
  dissect: '#323436',

  report: '#C8E5FF',
  total: '#90949B',
} as const

export const POS: Record<string, XY> = {
  prompt: { x: 100, y: 340 },
  bgent: { x: 325, y: 340 },
  'total-report': { x: 980, y: 330 },
}

const DEFAULT_POS: XY = { x: 100, y: 100 }

export const REPORT_META = {
  label: 'Report',
  kind: 'doc' as const,
  icon: 'icons/report.svg',
  bg: PALETTE.report,
}

export const NODE_META: Record<
  string,
  { label: string; bg?: string; icon?: string; kind: 'prompt' | 'agent' | 'mcp' | 'doc' | 'total' }
> = {
  prompt: { label: 'User Prompt', kind: 'prompt', bg: '#555C62', icon: 'icons/prompt.svg' },
  bgent: { label: 'B-gent', kind: 'agent', bg: '#506D99', icon: 'icons/bgent.svg' },

  velociraptor: {
    label: 'Velociraptor',
    kind: 'mcp',
    bg: PALETTE.velociraptor,
    icon: 'icons/velociraptor.svg',
  },
  elastic: {
    label: 'Elasticsearch',
    kind: 'mcp',
    bg: PALETTE.elastic,
    icon: 'icons/elastic.svg',
  },
  sleuthkit: {
    label: 'The Sleuth Kit',
    kind: 'mcp',
    bg: PALETTE.tsk,
    icon: 'icons/tsk.svg',
  },
  ghidra: {
    label: 'Ghidra',
    kind: 'mcp',
    bg: PALETTE.ghidra,
    icon: 'icons/ghidra.svg',
  },
  virustotal: {
    label: 'VirusTotal',
    kind: 'mcp',
    bg: PALETTE.virustotal,
    icon: 'icons/virustotal.svg',
  },
  'ez-tools': {
    label: 'EZ Tools',
    kind: 'mcp',
    bg: PALETTE['ez-tools'],
    icon: 'icons/eztools.svg',
  },
  'consolehost-history': {
    label: 'Console',
    kind: 'mcp',
    bg: PALETTE['consolehost-history'],
    icon: 'icons/ntfs.svg',
  },
  'browser-db-parser': {
    label: 'Web Browser',
    kind: 'mcp',
    bg: PALETTE['browser-db-parser'],
    icon: 'icons/ntfs.svg',
  },
  'lnk-parser': {
    label: 'LNK Parser',
    kind: 'mcp',
    bg: PALETTE['lnk-parser'],
    icon: 'icons/ntfs.svg',
  },
  jumplist: {
    label: 'Jump List',
    kind: 'mcp',
    bg: PALETTE.jumplist,
    icon: 'icons/ntfs.svg',
  },
  ntfs: {
    label: 'NTFS',
    kind: 'mcp',
    bg: PALETTE.ntfs,
    icon: 'icons/ntfs.svg',
  },
  notification: {
    label: 'Notification',
    kind: 'mcp',
    bg: PALETTE['windows-notification'],
    icon: 'icons/ntfs.svg',
  },
  dissect: {
    label: 'Dissect',
    kind: 'mcp',
    bg: PALETTE.dissect,
    icon: 'icons/dissect.svg',
  },

  'total-report': {
    label: 'Total Report',
    kind: 'total',
    bg: '#F0F5F9',
    icon: 'icons/total.svg',
  },
}

export const NODE_HEIGHT: Record<'prompt' | 'agent' | 'mcp' | 'doc' | 'total', number> = {
  prompt: 360,
  agent: 360,
  mcp: 360,
  doc: 360,
  total: 360,
}

export function makeNode(id: string): Node {
  const meta = NODE_META[id] ??
    (id.endsWith('-report') ? REPORT_META : undefined) ?? {
      label: id,
      kind: 'mcp' as const,
      bg: PALETTE['consolehost-history'],
      icon: undefined,
    }

  const pos = POS[id] ?? DEFAULT_POS

  return {
    id,
    type: meta.kind,
    position: pos,
    data: {
      label: meta.label,
      icon: meta.icon,
      bg: meta.bg,
      isActive: id === 'prompt',
    },
  }
}

export function makeEdge(
  id: string,
  from: string,
  to: string,
  colorFrom?: string,
  colorTo?: string
): Edge {
  return {
    id,
    source: from,
    target: to,
    type: 'dotted',
    data: { from: colorFrom, to: colorTo, active: false },
  }
}

export function reportIdOf(server: MCPServer): string {
  return `${server}-report`
}

export function computeMcpPositions(
  servers: MCPServer[]
): Record<MCPServer, { x: number; y: number }> {
  const baseX = POS.bgent.x + 225
  const baseY = POS.bgent.y
  const gapY = 120

  const total = servers.length || 1
  const firstY = baseY - ((total - 1) * gapY) / 2

  return servers.reduce(
    (acc, s, idx) => {
      acc[s] = { x: baseX, y: firstY + idx * gapY }
      return acc
    },
    {} as Record<MCPServer, { x: number; y: number }>
  )
}

export function computeMcpReportPositions(
  servers: MCPServer[]
): Record<string, { x: number; y: number }> {
  const mcpPos = computeMcpPositions(servers)
  const dx = 225

  const map: Record<string, { x: number; y: number }> = {}

  servers.forEach(s => {
    const id = reportIdOf(s)
    const p = mcpPos[s]
    map[id] = {
      x: p.x + dx,
      y: p.y,
    }
  })

  return map
}
