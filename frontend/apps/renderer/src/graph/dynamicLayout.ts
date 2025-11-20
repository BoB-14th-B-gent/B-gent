import type { Node, Edge } from 'reactflow'
import type { MCPServer } from './events'

export const PALETTE = {
  prompt: '#90949B',
  bgent: '#AFC0CF',
  velociraptor: '#003D00',
  elastic: '#054861',
  tsk: '#F5D356',
  ghidra: '#FF8B8D',
  report: '#7FA9CE',
  total: '#90949B',
} as const

export const POS = {
  prompt: { x: 100, y: 340 },
  bgent: { x: 325, y: 340 },
  velociraptor: { x: 550, y: 250 },
  elastic: { x: 550, y: 450 },
  sleuthkit: { x: 550, y: 250 },
  ghidra: { x: 550, y: 450 },
  'velo-report': { x: 775, y: 250 },
  'elastic-report': { x: 775, y: 450 },
  'tsk-report': { x: 775, y: 250 },
  'ghidra-report': { x: 775, y: 450 },
  'total-report': { x: 980, y: 330 },
} as const

export const NODE_META: Record<
  string,
  { label: string; bg?: string; icon?: string; kind: 'prompt' | 'agent' | 'mcp' | 'doc' | 'total' }
> = {
  prompt: { label: 'User Prompt', kind: 'prompt', bg: '#555C62', icon: 'icons/prompt.svg' },
  bgent: { label: 'B-gent', kind: 'agent', bg: '#506D99', icon: 'icons/bgent.svg' },

  velociraptor: {
    label: 'Velociraptor',
    kind: 'mcp',
    bg: '#003D00',
    icon: 'icons/velociraptor.svg',
  },
  elastic: { label: 'Elasticsearch', kind: 'mcp', bg: '#002A3A', icon: 'icons/elastic.svg' },
  sleuthkit: { label: 'The Sleuth Kit', kind: 'mcp', bg: '#F5D356', icon: 'icons/tsk.svg' },
  ghidra: { label: 'Ghidra', kind: 'mcp', bg: '#FF6B6D', icon: 'icons/ghidra.svg' },

  'velo-report': { label: 'Report', kind: 'doc', icon: 'icons/report.svg' },
  'elastic-report': { label: 'Report', kind: 'doc', icon: 'icons/report.svg' },
  'tsk-report': { label: 'Report', kind: 'doc', icon: 'icons/report.svg' },
  'ghidra-report': { label: 'Report', kind: 'doc', icon: 'icons/report.svg' },

  'total-report': { label: 'Total Report', kind: 'total', bg: '#F0F5F9', icon: 'icons/total.svg' },
}

export function makeNode(id: string): Node {
  const meta = NODE_META[id] ?? { label: id, kind: 'doc' }
  const pos = (POS as any)[id] ?? { x: 100, y: 100 }
  return {
    id,
    type: meta.kind,
    position: pos,
    data: {
      label: meta.label,
      icon: meta.icon,
      bg: meta.bg,
      isActive: id === 'prompt' ? true : false,
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
  } as Edge
}

export function reportIdOf(server: MCPServer) {
  if (server === 'velociraptor') return 'velo-report'
  if (server === 'elastic') return 'elastic-report'
  if (server === 'sleuthkit') return 'tsk-report'
  return 'ghidra-report'
}
