import { useCallback, useEffect, useRef, useLayoutEffect } from 'react'
import ReactFlow, {
  type ReactFlowInstance,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  ReactFlowProvider,
  useReactFlow,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { getTrigger, getLatestReportId } from '@/utils/api'

import { nodeTypes } from '@/components/nodes'
import { edgeTypes } from '@/components/edges'
import { useUIStore } from '@/store/ui'
import { graphEvents, GraphEvt, type MCPServer } from '@/graph/events'
import { makeNode, makeEdge, PALETTE, reportIdOf } from '@/graph/dynamicLayout'

import PromptPanel from '@/components/panels/PromptPanel'
import AgentPanel from '@/components/panels/AgentPanel'
import MCPServerPanel from '@/components/panels/MCPServerPanel'
import TotalReportPanel from '@/components/panels/TotalReportPanel'

export default function Diagram() {
  return (
    <ReactFlowProvider>
      <DiagramInner />
    </ReactFlowProvider>
  )
}

function DiagramInner() {
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

  const currentTriggerId = useUIStore(s => s.currentTriggerId)

  const totalReportOpen = useUIStore(s => s.totalreportOpen)
  const openTotalReport = useUIStore(s => s.openTotalReport)
  const closeAllPanels = useUIStore(s => s.closeAllPanels)

  const rfRef = useRef<ReactFlowInstance | null>(null)

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  const { fitView } = useReactFlow()
  const fitRaf = useRef<number | null>(null)
  const fitTmo = useRef<number | null>(null)
  const scheduleFit = useCallback(
    (delay = 120) => {
      if (fitRaf.current) {
        cancelAnimationFrame(fitRaf.current)
        fitRaf.current = null
      }
      if (fitTmo.current) {
        clearTimeout(fitTmo.current)
        fitTmo.current = null
      }
      fitRaf.current = requestAnimationFrame(() => {
        fitTmo.current = window.setTimeout(() => {
          fitView({ padding: 0.18, duration: 220 })
        }, delay)
      })
    },
    [fitView]
  )

  useEffect(
    () => () => {
      if (fitRaf.current) cancelAnimationFrame(fitRaf.current)
      if (fitTmo.current) clearTimeout(fitTmo.current)
    },
    []
  )

  useEffect(() => {
    setNodes(nds =>
      nds.map(n => {
        const isActive =
          (n.type === 'prompt' && activePromptId === n.id) ||
          (n.type === 'agent' && activeAgentId === n.id) ||
          (n.type === 'mcp' && activeMCPServerId === n.id) ||
          (n.type === 'total' && activeTotalReportId === n.id)
        return { ...n, data: { ...(n.data ?? {}), isActive } }
      })
    )
  }, [activePromptId, activeAgentId, activeMCPServerId, activeTotalReportId, setNodes])

  useEffect(() => {
    setActivePrompt('prompt')
    openPrompt()
  }, [openPrompt, setActivePrompt])

  const handleInit = useCallback(
    (inst: ReactFlowInstance) => {
      rfRef.current = inst
      fitView({ padding: 0.1, duration: 0 })
    },
    [fitView]
  )

  useEffect(() => {
    scheduleFit(0)
  }, [promptOpen, agentOpen, mcpserverOpen, totalReportOpen, scheduleFit])

  const ensureNode = useCallback(
    (id: string) => {
      setNodes(nds => (nds.some(n => n.id === id) ? nds : [...nds, makeNode(id)]))
    },
    [setNodes]
  )

  const ensureEdge = useCallback(
    (id: string, from: string, to: string, colorFrom?: string, colorTo?: string) => {
      setEdges(eds =>
        eds.some(e => e.id === id) ? eds : [...eds, makeEdge(id, from, to, colorFrom, colorTo)]
      )
    },
    [setEdges]
  )

  const fitRaf1 = useRef<number | null>(null)
  const fitRaf2 = useRef<number | null>(null)

  const serverEdgeActiveRef = useRef<Record<MCPServer, boolean>>({
    velociraptor: false,
    elastic: false,
    sleuthkit: false,
  })
  const serverEdgeId = (s: MCPServer) => `e-bgent-${s}`

  useLayoutEffect(() => {
    fitRaf1.current = requestAnimationFrame(() => {
      fitRaf2.current = requestAnimationFrame(() => {
        fitView({ padding: 0.18, duration: 220 })
      })
    })
    return () => {
      if (fitRaf1.current) cancelAnimationFrame(fitRaf1.current)
      if (fitRaf2.current) cancelAnimationFrame(fitRaf2.current)
      fitRaf1.current = null
      fitRaf2.current = null
    }
  }, [nodes.length, edges.length, fitView])

  const setEdgeActive = useCallback(
    (edgeId: string, active: boolean) => {
      setEdges(eds =>
        eds.map(e =>
          e.id === edgeId ? ({ ...e, data: { ...(e.data ?? {}), active } } as Edge) : e
        )
      )
    },
    [setEdges]
  )

  useEffect(() => {
    function onGraph(e: Event) {
      const d = (e as CustomEvent).detail as
        | { type: 'reset' }
        | { type: 'add-node'; node: Node }
        | { type: 'add-edge'; edge: Edge }
        | { type: 'fit' }
        | { type: 'edge-active'; id: string; active: boolean }
        | undefined
      if (!d) return

      switch (d.type) {
        case 'reset':
          setNodes([])
          setEdges([])
          scheduleFit(0)
          break
        case 'add-node':
          if (d.node) {
            setNodes(prev => (prev.some(n => n.id === d.node.id) ? prev : [...prev, d.node]))
          }
          break
        case 'add-edge':
          if (d.edge) {
            setEdges(prev => (prev.some(e => e.id === d.edge.id) ? prev : [...prev, d.edge]))
            if (d.edge.id === 'e-prompt-bgent') setEdgeActive('e-prompt-bgent', true)
          }
          break
        case 'fit':
          scheduleFit(0)
          break
        case 'edge-active':
          setEdgeActive(d.id, d.active)
          break
      }
    }

    graphEvents.addEventListener('graph', onGraph)
    return () => graphEvents.removeEventListener('graph', onGraph)
  }, [setNodes, setEdges, setEdgeActive, scheduleFit])

  useEffect(() => {
    const START_HILITE_MS = 1200
    const BETWEEN_GAP_MS = 300

    let timeline = performance.now()
    const now = () => performance.now()

    const schedule = (delay: number, fn: () => void) => {
      const baseline = Math.max(timeline, now())
      const when = baseline + delay
      const t = window.setTimeout(fn, Math.max(0, when - now()))
      timeline = when
      return t
    }

    const raf2 = (fn: () => void) => requestAnimationFrame(() => requestAnimationFrame(fn))

    const onAddInitial = () => {
      ensureNode('prompt')
      ensureNode('bgent')
      ensureEdge('e-prompt-bgent', 'prompt', 'bgent', PALETTE.prompt, PALETTE.bgent)

      schedule(0, () => {
        raf2(() => {
          scheduleFit(0)
          setEdgeActive('e-prompt-bgent', true)
        })
      })
      schedule(START_HILITE_MS, () => setEdgeActive('e-prompt-bgent', false))
      schedule(BETWEEN_GAP_MS, () => {})
    }

    const onMCPStart = (e: Event) => {
      const server = (e as CustomEvent).detail?.server as MCPServer
      setEdgeActive('e-prompt-bgent', false)

      ensureNode(server)
      const edgeId = serverEdgeId(server)
      ensureEdge(
        edgeId,
        'bgent',
        server,
        PALETTE.bgent,
        server === 'velociraptor'
          ? PALETTE.velociraptor
          : server === 'elastic'
            ? PALETTE.elastic
            : PALETTE.tsk
      )

      serverEdgeActiveRef.current[server] = true
      requestAnimationFrame(() => {
        setEdgeActive(edgeId, true)
      })
    }

    const onMCPDone = (e: Event) => {
      const server = (e as CustomEvent).detail?.server as MCPServer
      const edgeIdToServer = serverEdgeId(server)
      const rid = reportIdOf(server)

      if (serverEdgeActiveRef.current[server]) {
        serverEdgeActiveRef.current[server] = false
        setEdgeActive(edgeIdToServer, false)
      }

      ensureNode(rid)
      const edgeId = `e-${server}-report`
      ensureEdge(
        edgeId,
        server,
        rid,
        server === 'velociraptor'
          ? PALETTE.velociraptor
          : server === 'elastic'
            ? PALETTE.elastic
            : PALETTE.tsk,
        PALETTE.report
      )

      requestAnimationFrame(() => {
        setEdgeActive(edgeId, true)
        window.setTimeout(() => setEdgeActive(edgeId, false), 1400)
      })
    }

    const onAgentDone = () => {
      ensureNode('total-report')
      ensureNode('velo-report')
      ensureNode('elastic-report')
      ensureNode('tsk-report')

      setEdges(eds => {
        const next = [...eds]
        const want = [
          makeEdge(
            'e-velo-report-total',
            'velo-report',
            'total-report',
            PALETTE.report,
            PALETTE.total
          ),
          makeEdge(
            'e-elastic-report-total',
            'elastic-report',
            'total-report',
            PALETTE.report,
            PALETTE.total
          ),
          makeEdge(
            'e-tsk-report-total',
            'tsk-report',
            'total-report',
            PALETTE.report,
            PALETTE.total
          ),
        ]
        for (const w of want) if (!next.some(e => e.id === w.id)) next.push(w)
        return next
      })

      requestAnimationFrame(() => {
        scheduleFit(0)
        setEdgeActive('e-velo-report-total', true)
        setEdgeActive('e-elastic-report-total', true)
        setEdgeActive('e-tsk-report-total', true)

        window.setTimeout(() => {
          setEdgeActive('e-velo-report-total', false)
          setEdgeActive('e-elastic-report-total', false)
          setEdgeActive('e-tsk-report-total', false)
        }, 40000)
      })
    }

    graphEvents.addEventListener(GraphEvt.AddInitial, onAddInitial)
    graphEvents.addEventListener(GraphEvt.MCPStart, onMCPStart)
    graphEvents.addEventListener(GraphEvt.MCPDone, onMCPDone)
    graphEvents.addEventListener(GraphEvt.AgentDone, onAgentDone)
    return () => {
      graphEvents.removeEventListener(GraphEvt.AddInitial, onAddInitial)
      graphEvents.removeEventListener(GraphEvt.MCPStart, onMCPStart)
      graphEvents.removeEventListener(GraphEvt.MCPDone, onMCPDone)
      graphEvents.removeEventListener(GraphEvt.AgentDone, onAgentDone)
    }
  }, [ensureNode, ensureEdge, setEdges, setEdgeActive, scheduleFit])

  const handlePaneClick = useCallback(() => {
    setSelectedNode(null)
    closeAllPanels()
  }, [setSelectedNode, closeAllPanels])

  const onNodeClick = useCallback(
    async (_evt: React.MouseEvent, node: Node) => {
      setSelectedNode(node.id)
      const id = node.id

      if (id === 'prompt') {
        if (promptOpen && activePromptId === id) {
          closePrompt()
          setActivePrompt(null)
        } else {
          setActivePrompt(id)
          openPrompt()
        }
        return
      }

      if (id === 'bgent') {
        setEdgeActive('e-prompt-bgent', false)
        if (agentOpen && activeAgentId === id) {
          closeAgent()
          setActiveAgent(null)
        } else {
          setActiveAgent(id)
          openAgent()
        }
        return
      }

      if (id === 'velociraptor' || id === 'elastic' || id === 'sleuthkit') {
        if (mcpserverOpen && activeMCPServerId === id) {
          closeMCPServer()
          setActiveMCPServer(null)
        } else {
          setActiveMCPServer(id)
          openMCPServer()
        }
        return
      }

      if (id.endsWith('-report') || id === 'total-report') {
        try {
          let repId: string | null = null

          if (currentTriggerId) {
            const trig = await getTrigger(currentTriggerId)
            const raw = trig?.report_id
            repId = typeof raw === 'string' ? raw : (raw?.$oid ?? null)
          }

          if (!repId) repId = await getLatestReportId()

          if (repId) {
            closeAllPanels()
            openTotalReport(repId)
          } else {
            console.warn('[graph] no report_id found')
          }
        } catch (e) {
          console.error('[graph] open report failed:', e)
        }
        return
      }

      closeAllPanels()
    },
    [
      setSelectedNode,
      promptOpen,
      activePromptId,
      closePrompt,
      setActivePrompt,
      openPrompt,
      agentOpen,
      activeAgentId,
      closeAgent,
      setActiveAgent,
      openAgent,
      mcpserverOpen,
      activeMCPServerId,
      closeMCPServer,
      setActiveMCPServer,
      openMCPServer,
      currentTriggerId,
      openTotalReport,
      closeAllPanels,
      setEdgeActive,
    ]
  )

  let cols = '1fr'
  let rows = '1fr'
  let areas = `"rf"`
  if (promptOpen && agentOpen && mcpserverOpen) {
    cols = '1fr 1fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf rf prompt" "agent mcp prompt"`
  } else if (promptOpen && agentOpen) {
    cols = '2fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf prompt" "agent prompt"`
  } else if (promptOpen && mcpserverOpen) {
    cols = '2fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf prompt" "mcp prompt"`
  } else if (agentOpen && mcpserverOpen) {
    cols = '2fr 1fr'
    rows = '2fr 1fr'
    areas = `"rf rf" "agent mcp"`
  } else if (promptOpen) {
    cols = '2fr 1fr'
    rows = '1fr'
    areas = `"rf prompt"`
  } else if (agentOpen) {
    cols = '1fr'
    rows = '2fr 1fr'
    areas = `"rf" "agent"`
  } else if (mcpserverOpen) {
    cols = '1fr'
    rows = '2fr 1fr'
    areas = `"rf" "mcp"`
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
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
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
            onNodeClick={onNodeClick}
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

        {totalReportOpen && <TotalReportPanel />}
      </div>
    </div>
  )
}
