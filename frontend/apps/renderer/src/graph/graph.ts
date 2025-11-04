export type NodeKey =
  | 'prompt'
  | 'bgent'
  | 'velociraptor'
  | 'elastic'
  | 'tsk'
  | 'velo-report'
  | 'elastic-report'
  | 'tsk-report'
  | 'total-report'
export type NodeKind = 'prompt' | 'agent' | 'mcp' | 'doc' | 'total'

export interface UINode {
  id: NodeKey
  kind: NodeKind
  x: number
  y: number
  label: string
  icon?: string
  bg?: string
  leftDot?: string
  rightDot?: string
}

export interface UIEdge {
  id: string
  from: NodeKey
  to: NodeKey
  type: 'dotted'
  colorFrom?: string
  colorTo?: string
}

export const PALETTE = {
  prompt: '#90949B',
  bgent: '#AFC0CF',
  velociraptor: '#003D00',
  elastic: '#054861',
  tsk: '#F5D356',
  report: '#7FA9CE',
  total: '#90949B',
} as const

export const nodesData: UINode[] = [
  {
    id: 'prompt',
    kind: 'prompt',
    x: 100,
    y: 340,
    label: 'User Prompt',
    icon: 'icons/prompt.svg',
    bg: '#555C62',
    leftDot: PALETTE.prompt,
    rightDot: '#2d5bff',
  },
  {
    id: 'bgent',
    kind: 'agent',
    x: 320,
    y: 340,
    label: 'B-gent',
    icon: 'icons/bgent.svg',
    bg: '#506D99',
    leftDot: '#2d5bff',
    rightDot: '#2d5bff',
  },

  {
    id: 'velociraptor',
    kind: 'mcp',
    x: 565,
    y: 200,
    label: 'Velociraptor',
    icon: 'icons/velociraptor.svg',
    bg: '#003D00',
    leftDot: '#1f8a5b',
    rightDot: PALETTE.report,
  },

  {
    id: 'elastic',
    kind: 'mcp',
    x: 565,
    y: 350,
    label: 'Elasticsearch',
    icon: 'icons/elastic.svg',
    bg: '#002A3A',
    leftDot: '#0d7d6f',
    rightDot: PALETTE.report,
  },

  {
    id: 'tsk',
    kind: 'mcp',
    x: 565,
    y: 500,
    label: 'The Sleuth Kit',
    icon: 'icons/tsk.svg',
    bg: '#F5D356',
    leftDot: '#e7a90e',
    rightDot: PALETTE.report,
  },

  { id: 'velo-report', kind: 'doc', x: 750, y: 200, label: 'Report', icon: 'icons/report.svg' },
  { id: 'elastic-report', kind: 'doc', x: 750, y: 350, label: 'Report', icon: 'icons/report.svg' },
  { id: 'tsk-report', kind: 'doc', x: 750, y: 500, label: 'Report', icon: 'icons/report.svg' },

  {
    id: 'total-report',
    kind: 'total',
    x: 960,
    y: 330,
    label: 'Total Report',
    icon: 'icons/total.svg',
    bg: '#F0F5F9',
    leftDot: PALETTE.total,
    rightDot: PALETTE.total,
  },
]

export const edgesData: UIEdge[] = [
  {
    id: 'e-prompt-bgent',
    from: 'prompt',
    to: 'bgent',
    type: 'dotted',
    colorFrom: PALETTE.prompt,
    colorTo: PALETTE.bgent,
  },

  {
    id: 'e-bgent-velociraptor',
    from: 'bgent',
    to: 'velociraptor',
    type: 'dotted',
    colorFrom: PALETTE.bgent,
    colorTo: PALETTE.velociraptor,
  },
  {
    id: 'e-bgent-elastic',
    from: 'bgent',
    to: 'elastic',
    type: 'dotted',
    colorFrom: PALETTE.bgent,
    colorTo: PALETTE.elastic,
  },
  {
    id: 'e-bgent-tsk',
    from: 'bgent',
    to: 'tsk',
    type: 'dotted',
    colorFrom: PALETTE.bgent,
    colorTo: PALETTE.tsk,
  },

  {
    id: 'e-velociraptor-report',
    from: 'velociraptor',
    to: 'velo-report',
    type: 'dotted',
    colorFrom: PALETTE.velociraptor,
    colorTo: PALETTE.report,
  },
  {
    id: 'e-elastic-report',
    from: 'elastic',
    to: 'elastic-report',
    type: 'dotted',
    colorFrom: PALETTE.elastic,
    colorTo: PALETTE.report,
  },
  {
    id: 'e-tsk-report',
    from: 'tsk',
    to: 'tsk-report',
    type: 'dotted',
    colorFrom: PALETTE.tsk,
    colorTo: PALETTE.report,
  },

  {
    id: 'e-r-total-1',
    from: 'velo-report',
    to: 'total-report',
    type: 'dotted',
    colorFrom: PALETTE.report,
    colorTo: PALETTE.total,
  },
  {
    id: 'e-r-total-2',
    from: 'elastic-report',
    to: 'total-report',
    type: 'dotted',
    colorFrom: PALETTE.report,
    colorTo: PALETTE.total,
  },
  {
    id: 'e-r-total-3',
    from: 'tsk-report',
    to: 'total-report',
    type: 'dotted',
    colorFrom: PALETTE.report,
    colorTo: PALETTE.total,
  },
]
