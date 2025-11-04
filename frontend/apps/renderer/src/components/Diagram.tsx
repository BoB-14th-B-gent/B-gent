import { useMemo, useCallback } from 'react'
import ReactFlow from 'reactflow'
import 'reactflow/dist/style.css'

import { mapNodes, mapEdges } from '@/graph/ConvertToReactFlow'
import { nodeTypes } from '@/components/nodes'
import { edgeTypes } from '@/components/edges'
import { useUIStore } from '@/store/ui'

import PromptPanel from '@/components/panels/PromptPanel'

export default function Diagram() {
  const selectedNodeId = useUIStore(s => s.selectedNodeId)
  const setSelectedNode = useUIStore(s => s.setSelectedNode)

  const promptOpen = useUIStore(s => s.promptOpen)
  const openPrompt = useUIStore(s => s.openPrompt)
  const closePrompt = useUIStore(s => s.closePrompt)

  const nodes = useMemo(() => {
    const base = mapNodes()
    return base.map(n => ({
      ...n,
      data: {
        ...n.data,
        isActive: n.id === selectedNodeId,
        onClick: () => {
          if (n.type === 'prompt') {
            if (selectedNodeId === n.id && promptOpen) {
              closePrompt()
              setSelectedNode(null)
            } else {
              setSelectedNode(n.id)
              openPrompt()
            }
          } else {
            setSelectedNode(n.id)
            closePrompt()
          }
        },
      },
    }))
  }, [selectedNodeId, promptOpen, setSelectedNode, openPrompt, closePrompt])

  const edges = useMemo(() => mapEdges(), [])

  const handlePaneClick = useCallback(() => {
    setSelectedNode(null)
    closePrompt()
  }, [setSelectedNode, closePrompt])

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
        position: 'relative',
      }}
    >
      <ReactFlow
        panOnDrag
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        connectOnClick={false}
        nodesDraggable={false}
        elementsSelectable={false}
        zoomOnScroll
        onPaneClick={handlePaneClick}
        onNodeClick={(_, node) => {
          if (node.type === 'prompt') {
            if (selectedNodeId === node.id && promptOpen) {
              closePrompt()
              setSelectedNode(null)
            } else {
              setSelectedNode(node.id)
              openPrompt()
            }
          } else {
            setSelectedNode(node.id)
            closePrompt()
          }
        }}
      />

      <PromptPanel />
    </div>
  )
}
