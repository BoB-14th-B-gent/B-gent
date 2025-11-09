import { useMemo, useCallback, useEffect, useRef } from 'react'
import ReactFlow, { type ReactFlowInstance } from 'reactflow'
import 'reactflow/dist/style.css'

import { mapNodes, mapEdges } from '@/graph/ConvertToReactFlow'
import { nodeTypes } from '@/components/nodes'
import { edgeTypes } from '@/components/edges'
import { useUIStore } from '@/store/ui'

import PromptPanel from '@/components/panels/PromptPanel'
import AgentPanel from '@/components/panels/AgentPanel'
import MCPServerPanel from '@/components/panels/MCPServerPanel'
import TotalReportPanel from '@/components/panels/TotalReportPanel'

export default function Diagram() {
  const selectedNodeId = useUIStore(s => s.selectedNodeId)
  const setSelectedNode = useUIStore(s => s.setSelectedNode)

  const promptOpen = useUIStore(s => s.promptOpen)
  const openPrompt = useUIStore(s => s.openPrompt)
  const closePrompt = useUIStore(s => s.closePrompt)

  const agentOpen = useUIStore(s => s.agentOpen)
  const openAgent = useUIStore(s => s.openAgent)
  const closeAgent = useUIStore(s => s.closeAgent)

  const mcpserverOpen = useUIStore(s => s.mcpserverOpen)
  const openMCPServer = useUIStore(s => s.openMCPServer)
  const closeMCPServer = useUIStore(s => s.closeMCPServer)

  const activePromptId = useUIStore(s => s.activePromptId)
  const setActivePrompt = useUIStore(s => s.setActivePrompt)
  const activeAgentId = useUIStore(s => s.activeAgentId)
  const setActiveAgent = useUIStore(s => s.setActiveAgent)
  const activeMCPServerId = useUIStore(s => s.activeMCPServerId)
  const setActiveMCPServer = useUIStore(s => s.setActiveMCPServer)
  const activeTotalReportId = useUIStore(s => s.activeTotalReportId)
  const setActiveTotalReport = useUIStore(s => s.setActiveTotalReport)

  const totalReportOpen = useUIStore(s => s.totalreportOpen)
  const openTotalReport = useUIStore(s => s.openTotalReport)
  const closeTotalReport = useUIStore(s => s.closeTotalReport)

  const closeAllPanels = useUIStore(s => s.closeAllPanels)

  const rfRef = useRef<ReactFlowInstance | null>(null)
  const shellRef = useRef<HTMLDivElement | null>(null)

  const handleInit = useCallback((inst: ReactFlowInstance) => {
    rfRef.current = inst
    inst.fitView({ padding: 0.1, duration: 0 })
  }, [])

  useEffect(() => {
    const inst = rfRef.current
    if (!inst) return
    const t = setTimeout(() => inst.fitView({ padding: 0.12, duration: 180 }), 0)
    return () => clearTimeout(t)
  }, [promptOpen, agentOpen, mcpserverOpen, totalReportOpen])

  useEffect(() => {
    if (!shellRef.current) return
    const inst = rfRef.current
    if (!inst) return
    const ro = new ResizeObserver(() => {
      inst.fitView({ padding: 0.12, duration: 0 })
    })
    ro.observe(shellRef.current)
    return () => ro.disconnect()
  }, [])

  const nodes = useMemo(() => {
    return mapNodes().map(n => ({
      ...n,
      data: {
        ...n.data,
        isActive:
          (n.type === 'prompt' && activePromptId === n.id) ||
          (n.type === 'agent' && activeAgentId === n.id) ||
          (n.type === 'mcp' && activeMCPServerId === n.id) ||
          (n.type === 'total' && activeTotalReportId === n.id),

        onClick: () => {
          setSelectedNode(n.id)

          if (n.type === 'prompt') {
            if (promptOpen && activePromptId === n.id) {
              closePrompt()
              setActivePrompt(null)
            } else {
              setActivePrompt(n.id)
              openPrompt()
            }
          } else if (n.type === 'agent') {
            if (agentOpen && activeAgentId === n.id) {
              closeAgent()
              setActiveAgent(null)
            } else {
              setActiveAgent(n.id)
              openAgent()
            }
          } else if (n.type === 'mcp') {
            if (mcpserverOpen && activeMCPServerId === n.id) {
              closeMCPServer()
              setActiveMCPServer(null)
            } else {
              setActiveMCPServer(n.id)
              openMCPServer()
            }
          } else if (n.type === 'total') {
            if (totalReportOpen && activeTotalReportId === n.id) {
              closeTotalReport()
              setActiveTotalReport(null)
            } else {
              setActiveTotalReport(n.id)
              openTotalReport()
            }
          } else {
            closeAllPanels()
          }
        },
      },
    }))
  }, [
    activePromptId,
    activeAgentId,
    activeMCPServerId,
    activeTotalReportId,
    promptOpen,
    agentOpen,
    mcpserverOpen,
    totalReportOpen,
    setSelectedNode,
    openPrompt,
    closePrompt,
    openAgent,
    closeAgent,
    openMCPServer,
    closeMCPServer,
    openTotalReport,
    closeTotalReport,
    setActivePrompt,
    setActiveAgent,
    setActiveMCPServer,
    setActiveTotalReport,
    closeAllPanels,
  ])

  const edges = useMemo(() => mapEdges(), [])

  const handlePaneClick = useCallback(() => {
    setSelectedNode(null)
    closeAllPanels()
  }, [setSelectedNode, closeAllPanels])

  let cols = '1fr'
  let rows = '1fr'
  let areas = `"rf"`
  if (promptOpen && agentOpen && mcpserverOpen) {
    cols = '1fr 1fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf rf prompt"
               "agent mcp prompt"`
  } else if (promptOpen && agentOpen) {
    cols = '2fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf prompt"
               "agent prompt"`
  } else if (promptOpen && mcpserverOpen) {
    cols = '2fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf prompt"
               "mcp prompt"`
  } else if (agentOpen && mcpserverOpen) {
    cols = '2fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf rf"
               "agent mcp"`
  } else if (promptOpen) {
    cols = '2fr 1fr'
    rows = '1fr'
    areas = `"rf prompt"`
  } else if (agentOpen) {
    cols = '1fr'
    rows = '2fr 1fr'
    areas = `"rf"
               "agent"`
  } else if (mcpserverOpen) {
    cols = '1fr'
    rows = '2fr 1fr'
    areas = `"rf"
               "mcp"`
  } 

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        background: `
          radial-gradient(circle at 30% 40%, rgba(255, 255, 255, 0.5), rgba(255,255,255,0) 45%),
          linear-gradient(115deg, #d5e4f7 0%, #bfd3f0 40%, #a8c2e6 75%, #96b3dd 100%)
        `,
        boxSizing: 'border-box',
        padding: 10,
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: cols,
          gridTemplateRows: rows,
          gridTemplateAreas: areas,
          gap: 10,
          width: '100%',
          height: '100%',
          transition: 'grid-template-columns 220ms ease, grid-template-rows 220ms ease',
        }}
      >
        <div
          style={{
            gridArea: 'rf',
            width: '100%',
            height: '100%',
            borderRadius: 16,
            overflow: 'hidden',
          }}
        >
          <ReactFlow
            onInit={handleInit}
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
              setSelectedNode(node.id)

              if (node.type === 'prompt') {
                if (promptOpen && activePromptId === node.id) {
                  closePrompt()
                  setActivePrompt(null)
                } else {
                  setActivePrompt(node.id)
                  openPrompt()
                }
                return
              }

              if (node.type === 'agent') {
                if (agentOpen && activeAgentId === node.id) {
                  closeAgent()
                  setActiveAgent(null)
                } else {
                  setActiveAgent(node.id)
                  openAgent()
                }
                return
              }

              if (node.type === 'mcp') {
                if (mcpserverOpen && activeMCPServerId === node.id) {
                  closeMCPServer()
                  setActiveMCPServer(null)
                } else {
                  setActiveMCPServer(node.id)
                  openMCPServer()
                }
                return
              }

              if (node.type === 'report') {
                closeAllPanels()
                openTotalReport(node.id)
                return
              }

              closeAllPanels()
            }}
          />
        </div>

        {promptOpen && (
          <div style={{ gridArea: 'prompt', minWidth: 320, overflow: 'hidden' }}>
            <PromptPanel />
          </div>
        )}

        {agentOpen && (
          <div style={{ gridArea: 'agent', overflow: 'hidden' }}>
            <AgentPanel />
          </div>
        )}

        {mcpserverOpen && (
          <div style={{ gridArea: 'mcp', overflow: 'hidden' }}>
            <MCPServerPanel />
          </div>
        )}

        {totalReportOpen && (
          <TotalReportPanel />
        )}
      </div>
    </div>
  )
}
