import type { Node, Edge } from 'reactflow'
import { nodesData, edgesData, type UINode, type UIEdge } from './graph'

export function mapNodes(): Node[] {
  return nodesData.map((n: UINode) => ({
    id: n.id,
    type: n.kind,
    position: { x: n.x, y: n.y },
    data: {
      label: n.label,
      icon: n.icon,
      bg: n.bg,
      leftDot: n.leftDot,
      rightDot: n.rightDot,
    },
    draggable: false,
    selectable: false,
  }))
}

export function mapEdges(): Edge[] {
  return edgesData.map((e: UIEdge) => ({
    id: e.id,
    source: e.from,
    target: e.to,
    type: e.type,
    data: { from: e.colorFrom, to: e.colorTo },
  }))
}
