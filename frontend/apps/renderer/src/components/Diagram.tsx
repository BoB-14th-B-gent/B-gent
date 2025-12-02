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
import {
  getTrigger,
  getLatestReportId,
  getUILayout,
  putUILayout,
  type RFNodeDTO,
  type RFEdgeDTO,
  getConversationReports,
  getMessages,
  type MessageItem,
} from '@/utils/api'

import { nodeTypes } from '@/components/nodes'
import { edgeTypes } from '@/components/edges'
import { useUIStore, type ChatMsg } from '@/store/ui'
import { graphEvents, GraphEvt, type MCPServer } from '@/graph/events'
import { makeNode, makeEdge, PALETTE, reportIdOf } from '@/graph/dynamicLayout'

import PromptPanel from '@/components/panels/PromptPanel'
import AgentPanel from '@/components/panels/AgentPanel'
import MCPServerPanel from '@/components/panels/MCPServerPanel'
import TotalReportPanel from '@/components/panels/TotalReportPanel'

export default function Diagram({ sidebarOpen }: { sidebarOpen: boolean }) {
  return (
    <ReactFlowProvider>
      <DiagramInner sidebarOpen={sidebarOpen} />
    </ReactFlowProvider>
  )
}

function DiagramInner({ sidebarOpen }: { sidebarOpen: boolean }) {
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
  const conversationId = useUIStore(s => s.conversationId)
  const setPanelMessages = useUIStore(s => s.setPanelMessages)
  const setPromptText = useUIStore(s => s.setPromptText)
  const STAGE_ID = 1

  const totalReportOpen = useUIStore(s => s.totalreportOpen)
  const openTotalReport = useUIStore(s => s.openTotalReport)
  const closeAllPanels = useUIStore(s => s.closeAllPanels)

  const selectedCaseId = useUIStore(s => s.selectedCaseId)

  const rfRef = useRef<ReactFlowInstance | null>(null)

  const saveLayoutTmo = useRef<number | null>(null)

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

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  const currentStageId = useUIStore(s => s.currentStageId ?? 1)

  useEffect(() => {
    if (conversationId === null) {
      setNodes([])
      setEdges([])
      scheduleFit(100)
    }
  }, [conversationId, setNodes, setEdges, scheduleFit])

  const H_GAP = 1105

  const ensureStageNode = useCallback(
    (baseId: string, stage: number): string => {
      const nodeId = `${baseId}-${stage}`
      setNodes(prev => {
        if (prev.some(n => n.id === nodeId)) return prev
        const base = makeNode(baseId)
        const node: Node = {
          ...base,
          id: nodeId,
          position: {
            ...base.position,
            x: base.position.x + (stage - 1) * H_GAP,
          },
        }
        return [...prev, node]
      })
      return nodeId
    },
    [setNodes]
  )

  const ensureStageEdge = useCallback(
    (id: string, from: string, to: string, colorFrom?: string, colorTo?: string) => {
      setEdges(eds =>
        eds.some(e => e.id === id) ? eds : [...eds, makeEdge(id, from, to, colorFrom, colorTo)]
      )
    },
    [setEdges]
  )

  useEffect(
    () => () => {
      if (fitRaf.current) cancelAnimationFrame(fitRaf.current)
      if (fitTmo.current) clearTimeout(fitTmo.current)
      if (saveLayoutTmo.current) clearTimeout(saveLayoutTmo.current)
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

  useEffect(() => {
    if (!conversationId) {
      return
    }

    let cancelled = false

    ;(async () => {
      try {
        const layout = await getUILayout(conversationId, STAGE_ID)
        if (cancelled) return

        const dtoNodes: RFNodeDTO[] = layout.nodes ?? []
        const dtoEdges: RFEdgeDTO[] = layout.edges ?? []

        if (dtoNodes.length === 0 && dtoEdges.length === 0) {
          const stage = currentStageId ?? 1
          const pid = ensureStageNode('prompt', stage)
          const aid = ensureStageNode('bgent', stage)
          ensureStageEdge(`e-${pid}-${aid}`, pid, aid, PALETTE.prompt, PALETTE.bgent)
          scheduleFit(0)
          return
        }

        const rfNodes: Node[] = dtoNodes.map(n => ({
          id: n.id,
          type: n.type,
          position: n.position,
          data: n.data ?? {},
        }))

        const rfEdges: Edge[] = dtoEdges.map(e => ({
          id: e.id,
          source: e.source,
          target: e.target,
          type: e.type,
          data: e.data ?? {},
        }))

        setNodes(rfNodes)
        setEdges(rfEdges)
        scheduleFit(0)
      } catch (err) {
        console.warn('[Diagram] getUILayout failed; keep current graph:', err)
        if (cancelled) return
        scheduleFit(0)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [
    conversationId,
    STAGE_ID,
    setNodes,
    setEdges,
    scheduleFit,
    currentStageId,
    ensureStageEdge,
    ensureStageNode,
  ])

  useEffect(() => {
    if (!conversationId) return

    if (nodes.length === 0 && edges.length === 0) return

    if (saveLayoutTmo.current) {
      clearTimeout(saveLayoutTmo.current)
    }

    saveLayoutTmo.current = window.setTimeout(() => {
      const dtoNodes: RFNodeDTO[] = nodes.map(n => ({
        id: n.id,
        type: n.type ?? 'default',
        position: n.position,
        data: n.data ?? {},
      }))

      const dtoEdges: RFEdgeDTO[] = edges.map(e => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: e.type,
        data: e.data ?? {},
      }))

      putUILayout(conversationId, STAGE_ID, { nodes: dtoNodes, edges: dtoEdges }).catch(err => {
        console.warn('[Diagram] putUILayout failed:', err)
      })
    }, 800) as unknown as number
  }, [nodes, edges, conversationId])

  useEffect(() => {
    scheduleFit(50)
  }, [sidebarOpen, scheduleFit])

  const fitRaf1 = useRef<number | null>(null)
  const fitRaf2 = useRef<number | null>(null)

  const serverEdgeActiveRef = useRef<Record<string, boolean>>({
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

            const m = /^prompt-(\d+)$/.exec(d.node.id)
            if (m) {
              const stage = Number(m[1])
              if (stage > 1) {
                const fromId = `total-report-${stage - 1}`
                const edgeId = `e-${fromId}-${d.node.id}`
                setEdges(prev => {
                  if (prev.some(e => e.id === edgeId)) return prev
                  return [
                    ...prev,
                    makeEdge(edgeId, fromId, d.node.id, PALETTE.total, PALETTE.prompt),
                  ]
                })
              }
            }
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
      const stage = currentStageId ?? 1

      const agentId = ensureStageNode('bgent', stage)
      const serverId = ensureStageNode(server, stage)

      const edgeId = `e-bgent-${server}-${stage}`
      ensureStageEdge(
        edgeId,
        agentId,
        serverId,
        PALETTE.bgent,
        server === 'velociraptor'
          ? PALETTE.velociraptor
          : server === 'elastic'
            ? PALETTE.elastic
            : server === 'ghidra'
              ? PALETTE.ghidra
              : PALETTE.tsk
      )

      serverEdgeActiveRef.current[`${server}-${stage}`] = true
      requestAnimationFrame(() => {
        setEdgeActive(edgeId, true)
      })
    }

    const onMCPDone = (e: Event) => {
      const server = (e as CustomEvent).detail?.server as MCPServer
      const stage = currentStageId ?? 1
      const serverKey = `${server}-${stage}`

      const edgeIdToServer = `e-bgent-${server}-${stage}`
      if (serverEdgeActiveRef.current[serverKey]) {
        serverEdgeActiveRef.current[serverKey] = false
        setEdgeActive(edgeIdToServer, false)
      }

      const serverNodeId = ensureStageNode(server, stage)

      const reportBaseId =
        server === 'velociraptor'
          ? 'velo-report'
          : server === 'elastic'
            ? 'elastic-report'
            : server === 'ghidra'
              ? 'ghidra-report'
              : 'tsk-report'
      const reportNodeId = ensureStageNode(reportBaseId, stage)

      const edgeId = `e-${server}-${stage}-report-${stage}`
      ensureStageEdge(
        edgeId,
        serverNodeId,
        reportNodeId,
        server === 'velociraptor'
          ? PALETTE.velociraptor
          : server === 'elastic'
            ? PALETTE.elastic
            : server === 'ghidra'
              ? PALETTE.ghidra
              : PALETTE.tsk,
        PALETTE.report
      )

      requestAnimationFrame(() => {
        setEdgeActive(edgeId, true)
        window.setTimeout(() => setEdgeActive(edgeId, false), 1400)
      })
    }

    const onAgentDone = () => {
      const stage = currentStageId ?? 1
      const totalId = ensureStageNode('total-report', stage)

      let reportNodeBaseIds: string[] = []

      if (stage === 2) {
        reportNodeBaseIds = ['tsk-report', 'ghidra-report']
      } else {
        reportNodeBaseIds = ['velo-report', 'elastic-report']
      }

      const pairs: Array<[string, string]> = reportNodeBaseIds.map(baseId => {
        const fromId = ensureStageNode(baseId, stage)
        return [fromId, totalId]
      })

      setEdges(eds => {
        const next = [...eds]
        for (const [from, to] of pairs) {
          const edgeId = `e-${from}-${to}`
          if (!next.some(e => e.id === edgeId)) {
            next.push(makeEdge(edgeId, from, to, PALETTE.report, PALETTE.total))
          }
        }
        return next
      })

      requestAnimationFrame(() => {
        scheduleFit(0)
        for (const [from, to] of pairs) {
          const edgeId = `e-${from}-${to}`
          setEdgeActive(edgeId, true)
          window.setTimeout(() => setEdgeActive(edgeId, false), 4000)
        }
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
  }, [
    ensureNode,
    ensureEdge,
    setEdges,
    setEdgeActive,
    scheduleFit,
    currentStageId,
    ensureStageNode,
    ensureStageEdge,
  ])

  const handlePaneClick = useCallback(() => {
    setSelectedNode(null)
    closeAllPanels()
  }, [setSelectedNode, closeAllPanels])

  const normalizeContent = (raw: string): string => {
    if (!raw) return ''

    const trimmed = raw.trim()

    const hasExec = trimmed.includes('## 1. Executive Summary')
    const hasAdd = trimmed.includes('## 6. Additional Evidence Required')
    if (!hasExec || !hasAdd) return raw

    const execMatch =
      /##\s*1\.\s*Executive Summary([\s\S]*?)(?=##\s*6\.\s*Additional Evidence Required|$)/i.exec(
        trimmed
      )
    const addMatch = /##\s*6\.\s*Additional Evidence Required([\s\S]*)/i.exec(trimmed)

    const execPart = execMatch?.[1]?.trim() || '- (none)'
    const addPart = addMatch?.[1]?.trim() || '- (none)'

    return `[Executive Summary]\n${execPart}\n\n[Additional Evidence Required]\n${addPart}`
  }

  const loadMessagesUpToStage = useCallback(
    async (stageLimit: number) => {
      if (!conversationId || stageLimit <= 0) return

      const all: ChatMsg[] = []

      for (let s = 1; s <= stageLimit; s++) {
        try {
          const msgs = await getMessages(conversationId, s)
          const mapped: ChatMsg[] = msgs.map((m: MessageItem) => {
            const role = m.role === 'USER' ? 'user' : 'bgent'
            const text = normalizeContent(m.content ?? '')
            return {
              id: crypto.randomUUID(),
              role,
              text,
            }
          })
          all.push(...mapped)
        } catch (e) {
          console.error('[Diagram] failed to load messages for stage', s, e)
        }
      }

      setPanelMessages(all)
      setPromptText('')
    },
    [conversationId, setPanelMessages, setPromptText]
  )

  const onNodeClick = useCallback(
    async (_evt: React.MouseEvent, node: Node) => {
      setSelectedNode(node.id)
      const id = node.id

      const m = id.match(/-(\d+)$/)
      const stageFromId = m ? Number(m[1]) : 1

      if (id === 'prompt' || id.startsWith('prompt-')) {
        await loadMessagesUpToStage(stageFromId)

        if (promptOpen && activePromptId === id) {
          closePrompt()
          setActivePrompt(null)
        } else {
          setActivePrompt(id)
          openPrompt()
        }
        return
      }

      if (id === 'bgent' || id.startsWith('bgent-')) {
        await loadMessagesUpToStage(stageFromId)

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

      if (
        id.startsWith('velociraptor-') ||
        id.startsWith('elastic-') ||
        id.startsWith('sleuthkit-') ||
        id.startsWith('ghidra-')
      ) {
        if (mcpserverOpen && activeMCPServerId === id) {
          closeMCPServer()
          setActiveMCPServer(null)
        } else {
          setActiveMCPServer(id)
          openMCPServer()
        }
        return
      }

      if (
        id.includes('velo-report') ||
        id.includes('elastic-report') ||
        id.includes('tsk-report') ||
        id.startsWith('total-report')
      ) {
        try {
          let repId: string | null = null

          const stageForNode = stageFromId > 0 ? stageFromId : 1

          if (conversationId) {
            try {
              const reports = await getConversationReports(conversationId)
              const stageReports = reports.filter(r => r.stage_id === stageForNode)

              if (stageReports.length > 0) {
                const last = stageReports[stageReports.length - 1]
                repId = last._id
              }
            } catch (err) {
              console.error('[graph] getConversationReports failed (stage)', stageForNode, err)
            }
          }

          if (!repId && currentTriggerId) {
            const trig = await getTrigger(currentTriggerId)
            const raw = trig?.report_id
            repId = typeof raw === 'string' ? raw : ((raw as any)?.$oid ?? null)
          }

          if (!repId) {
            repId = await getLatestReportId()
          }

          if (repId) {
            closeAllPanels()
            openTotalReport(repId)
          } else {
            console.warn('[graph] no report_id found for node', id)
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
      conversationId,
      openTotalReport,
      closeAllPanels,
      setEdgeActive,
      loadMessagesUpToStage,
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
        width: '100%',
        height: '100%',
        background: `
          radial-gradient(circle at 30% 40%, rgba(255, 255, 255, 0.5), rgba(255,255,255,0) 45%),
          linear-gradient(115deg, #d5e4f7 0%, #bfd3f0 40%, #a8c2e6 75%, #96b3dd 100%)
        `,
        boxSizing: 'border-box',
        padding: 10,
      }}
    >
      {!promptOpen && !conversationId && !selectedCaseId &&(
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 1,
            display: 'grid',
            placeItems: 'center',
            pointerEvents: 'none',
            userSelect: 'none',
          }}
        >
          <div style={{ opacity: 0.1, color: '#034078' }}>
            <span style={{ fontSize: 160, fontWeight: 900 }}>B-GENT</span>
            <p style={{ textAlign: 'center', marginTop: -20, fontSize: 24, fontWeight: 600 }}>
              DFIR 자동 분석 프로그램
            </p>
          </div>
        </div>
      )}
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
