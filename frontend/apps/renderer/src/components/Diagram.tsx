import { useMemo } from 'react'
import ReactFlow from 'reactflow'
import 'reactflow/dist/style.css'

import { mapNodes, mapEdges } from '@/graph/ConvertToReactFlow'
import { nodeTypes } from '@/components/nodes'
import { edgeTypes } from '@/components/edges'
import { useUIStore } from '@/store/ui'

export default function Diagram() {
  const openPanel = useUIStore(s => s.openPanel)
  const setSelectedNode = useUIStore(s => s.setSelectedNode)

  const nodes = useMemo(() => mapNodes(), [])
  const edges = useMemo(() => mapEdges(), [])

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        background: `
          radial-gradient(circle at 30% 40%, rgba(255, 255, 255, 0.5), rgba(255,255,255,0) 45%),
          linear-gradient(115deg, #d5e4f7 0%, #bfd3f0 40%, #a8c2e6 75%, #96b3dd 100%)
        `,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        overflow: 'hidden',
        padding: 32,
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll
        onNodeClick={(_, node) => {
          setSelectedNode(node.id)
          openPanel()
        }}
      />
    </div>
  )
}
