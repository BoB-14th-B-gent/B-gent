import DottedEdge from './DottedEdge'

export const edgeTypes = {
  dotted: DottedEdge,
} as const

export type EdgeTypeKey = keyof typeof edgeTypes
