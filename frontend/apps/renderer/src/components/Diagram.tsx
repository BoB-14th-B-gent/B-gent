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
import { graphEvents, type MCPServer } from '@/graph/events'
import { makeNode, makeEdge, PALETTE } from '@/graph/dynamicLayout'

const MCP_COLOR: Record<MCPServer, string> = {
  velociraptor: PALETTE.velociraptor,
  elastic: PALETTE.elastic,
  sleuthkit: PALETTE.tsk,
  ghidra: PALETTE.ghidra,
  virustotal: PALETTE.virustotal,
  'ez-tools': PALETTE['ez-tools'],
  'consolehost-history': PALETTE['consolehost-history'],
  'browser-db-parser': PALETTE['browser-db-parser'],
  'lnk-parser': PALETTE['lnk-parser'],
  jumplist: PALETTE.jumplist,
  ntfs: PALETTE.ntfs,
  'windows-notification': PALETTE['windows-notification'],
  dissect: PALETTE.dissect,
}

const MCP_SERVERS: readonly MCPServer[] = [
  'velociraptor',
  'elastic',
  'sleuthkit',
  'ghidra',
  'virustotal',
  'ez-tools',
  'consolehost-history',
  'browser-db-parser',
  'lnk-parser',
  'jumplist',
  'ntfs',
  'windows-notification',
  'dissect',
]

const MCP_SERVER_SET: ReadonlySet<MCPServer> = new Set(MCP_SERVERS)

import PromptPanel from '@/components/panels/PromptPanel'
import AgentPanel from '@/components/panels/AgentPanel'
import MCPServerPanel from '@/components/panels/MCPServerPanel'
import MCPReportModal from '@/components/modals/MCPReportModal'
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

  const currentStageId = useUIStore(s => s.currentStageId ?? 1)
  const STAGE_ID = useUIStore(s => s.currentStageId ?? 1)

  const uiStageId = useUIStore(s => s.currentStageId ?? 1)
  const stageIdRef = useRef(uiStageId)

  useEffect(() => {
    stageIdRef.current = uiStageId
  }, [uiStageId])

  const totalReportOpen = useUIStore(s => s.totalreportOpen)
  const openTotalReport = useUIStore(s => s.openTotalReport)
  const closeAllPanels = useUIStore(s => s.closeAllPanels)

  const selectedCaseId = useUIStore(s => s.selectedCaseId)

  const rfRef = useRef<ReactFlowInstance | null>(null)
  const hydratingRef = useRef(false)

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
  const nodesRef = useRef<Node[]>([])
  const startedServersRef = useRef<Record<number, MCPServer[]>>({})
  const plannedServersRef = useRef<Record<number, MCPServer[]>>({})

  const getNodePos = useCallback((id: string) => {
    const n = nodesRef.current.find(x => x.id === id)
    return n?.position ? { ...n.position } : null
  }, [])

  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])

  useEffect(() => {
    if (conversationId === null) {
      setNodes([])
      setEdges([])
      scheduleFit(100)
    }
  }, [conversationId, setNodes, setEdges, scheduleFit])

  const H_GAP = 1145

  const getNodeHeightById = useCallback((baseId: string): number => {
    const id = baseId.replace(/-\d+$/, '')

    if (id === 'prompt') return 110
    if (id === 'bgent') return 120
    if (id === 'total-report') return 140

    if (id.endsWith('-report')) return 90

    return 96
  }, [])

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
        const isPrompt = n.type === 'prompt'
        const isAgent = n.type === 'agent'
        const isMcp = n.type === 'mcp'
        const isTotal = n.type === 'total'

        const isActive =
          (isPrompt &&
            (activePromptId === n.id ||
              (promptOpen && (n.id === 'prompt' || n.id.startsWith('prompt-'))))) ||
          (isAgent &&
            (activeAgentId === n.id ||
              (agentOpen && (n.id === 'bgent' || n.id.startsWith('bgent-'))))) ||
          (isMcp && activeMCPServerId === n.id) ||
          (isTotal && (activeTotalReportId === n.id || totalReportOpen))

        return { ...n, data: { ...((n.data as Record<string, unknown>) ?? {}), isActive } } as Node
      })
    )
  }, [
    activePromptId,
    activeAgentId,
    activeMCPServerId,
    activeTotalReportId,
    promptOpen,
    agentOpen,
    mcpserverOpen,
    totalReportOpen,
    setNodes,
  ])

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
      hydratingRef.current = true
      try {
        const stageForLayout = stageIdRef.current
        const layout = await getUILayout(conversationId, stageForLayout)
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

        setNodes(prev => {
          const prevMaxStage = Math.max(
            0,
            ...prev.map(n => Number(n.id.match(/-(\d+)$/)?.[1] ?? 0))
          )
          const nextMaxStage = Math.max(
            0,
            ...rfNodes.map(n => Number(n.id.match(/-(\d+)$/)?.[1] ?? 0))
          )
          return nextMaxStage >= prevMaxStage ? rfNodes : prev
        })
        setEdges(prev => {
          const prevCount = prev.length
          const nextCount = rfEdges.length
          return nextCount >= prevCount ? rfEdges : prev
        })
        scheduleFit(0)
      } catch (err) {
        console.warn('[Diagram] getUILayout failed; keep current graph:', err)
        if (cancelled) return
        scheduleFit(0)
      } finally {
        window.setTimeout(() => {
          hydratingRef.current = false
        }, 0)
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
    if (hydratingRef.current) return
    if (nodes.length === 0 && edges.length === 0) return

    if (saveLayoutTmo.current) clearTimeout(saveLayoutTmo.current)

    saveLayoutTmo.current = window.setTimeout(() => {
      if (hydratingRef.current) return

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

      const stageForLayout = stageIdRef.current
      putUILayout(conversationId, stageForLayout, { nodes: dtoNodes, edges: dtoEdges }).catch(err =>
        console.warn('[Diagram] putUILayout failed:', err)
      )
    }, 800) as unknown as number
  }, [nodes, edges, conversationId, STAGE_ID])

  useEffect(() => {
    scheduleFit(50)
  }, [sidebarOpen, scheduleFit])

  const fitRaf1 = useRef<number | null>(null)
  const fitRaf2 = useRef<number | null>(null)

  const serverEdgeActiveRef = useRef<Record<string, boolean>>({})

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

  type GraphDetail =
    | { type: 'reset' }
    | { type: 'add-node'; node: Node }
    | { type: 'add-edge'; edge: Edge }
    | { type: 'fit' }
    | { type: 'edge-active'; id: string; active: boolean }
    | { type: 'mcp-layout'; stageId?: number; servers: MCPServer[] }
    | { type: 'add-initial' }
    | { type: 'mcp-start'; server: MCPServer; stage_id?: number }
    | { type: 'mcp-done'; server: MCPServer; stage_id?: number }
    | { type: 'agent-done'; stage_id?: number }
    | { type: 'total-report-loaded'; stage_id?: number; reportId?: string }

  const handleAddInitial = useCallback(() => {
    ensureNode('prompt')
    ensureNode('bgent')
    ensureEdge('e-prompt-bgent', 'prompt', 'bgent', PALETTE.prompt, PALETTE.bgent)

    requestAnimationFrame(() => {
      scheduleFit(0)
      setEdgeActive('e-prompt-bgent', true)
      window.setTimeout(() => setEdgeActive('e-prompt-bgent', false), 1200)
    })
  }, [ensureNode, ensureEdge, scheduleFit, setEdgeActive])

  const layoutPlannedMCPs = useCallback(
    (stage: number) => {
      const servers = plannedServersRef.current[stage] ?? startedServersRef.current[stage] ?? []
      if (servers.length === 0) return

      const agentId = `bgent-${stage}`
      const agentPos = getNodePos(agentId)
      if (!agentPos) {
        requestAnimationFrame(() => layoutPlannedMCPs(stage))
        return
      }

      const agentH = getNodeHeightById('bgent')
      const agentCenterY = agentPos.y + agentH / 2

      const MCP_COL_X = agentPos.x + 245
      const GAP_Y = 220
      const centerIndex = (servers.length - 1) / 2

      setNodes(prev => {
        const next = [...prev]

        servers.forEach((server, idx) => {
          const serverId = `${server}-${stage}`
          const h = getNodeHeightById(server)

          const offset = (idx - centerIndex) * GAP_Y
          const centerY = agentCenterY + offset
          const y = centerY - h / 2

          const baseNode = makeNode(server)
          const i = next.findIndex(n => n.id === serverId)

          const node: Node = {
            ...(i >= 0 ? next[i] : baseNode),
            id: serverId,
            type: baseNode.type,
            data: { ...baseNode.data, ...(i >= 0 ? (next[i].data ?? {}) : {}) },
            position: { x: MCP_COL_X, y },
          }

          if (i >= 0) next[i] = node
          else next.push(node)

          const reportBaseId = `${server}-report`
          const reportNodeId = `${reportBaseId}-${stage}`
          const rIdx = next.findIndex(n => n.id === reportNodeId)
          if (rIdx >= 0) {
            const serverH = getNodeHeightById(server)
            const reportH = getNodeHeightById(reportBaseId)

            const serverCenterY2 = y + serverH / 2
            const reportPos = {
              x: MCP_COL_X + REPORT_DX,
              y: serverCenterY2 - reportH / 2 + REPORT_DY,
            }

            const baseReportNode = makeNode(reportBaseId)
            next[rIdx] = {
              ...next[rIdx],
              type: baseReportNode.type,
              data: { ...baseReportNode.data, ...(next[rIdx].data ?? {}) },
              position: reportPos,
            }
          }
        })

        return next
      })

      scheduleFit(0)
    },
    [getNodePos, getNodeHeightById, setNodes, scheduleFit]
  )

  const handleMCPStart = useCallback(
    (server: MCPServer, stage_id?: number) => {
      const stage = stage_id ?? currentStageId ?? 1

      const prev = startedServersRef.current[stage] ?? []
      if (!prev.includes(server)) {
        startedServersRef.current[stage] = [...prev, server]
      }

      const agentId = ensureStageNode('bgent', stage)
      const serverId = ensureStageNode(server, stage)

      const edgeId = `e-bgent-${server}-${stage}`
      const colorTo = MCP_COLOR[server] ?? PALETTE.report
      ensureStageEdge(edgeId, agentId, serverId, PALETTE.bgent, colorTo)

      layoutPlannedMCPs(stage)

      const key = `${server}-${stage}`
      serverEdgeActiveRef.current[key] = true
      requestAnimationFrame(() => setEdgeActive(edgeId, true))
    },
    [currentStageId, ensureStageNode, ensureStageEdge, setEdgeActive, layoutPlannedMCPs]
  )

  const REPORT_DX = 225
  const REPORT_DY = 0

  const handleMCPDone = useCallback(
    (server: MCPServer, stage_id?: number) => {
      const stage = stage_id ?? currentStageId ?? 1
      const serverKey = `${server}-${stage}`

      const edgeIdToServer = `e-bgent-${server}-${stage}`
      if (serverEdgeActiveRef.current[serverKey]) {
        serverEdgeActiveRef.current[serverKey] = false
        setEdgeActive(edgeIdToServer, false)
      }

      const serverNodeId = ensureStageNode(server, stage)
      const reportBaseId = `${server}-report`
      const reportNodeId = `${reportBaseId}-${stage}`

      const serverPos = getNodePos(serverNodeId)
      const fallback = { x: 550 + (stage - 1) * H_GAP, y: 240 }
      const basePos = serverPos ?? fallback

      const serverH = getNodeHeightById(server)
      const reportH = getNodeHeightById(reportBaseId)

      const serverCenterY = basePos.y + serverH / 2
      const reportPos = {
        x: basePos.x + REPORT_DX,
        y: serverCenterY - reportH / 2 + REPORT_DY,
      }

      setNodes(prev => {
        const next = [...prev]
        const idx = next.findIndex(n => n.id === reportNodeId)
        const baseReportNode = makeNode(reportBaseId)

        if (idx >= 0) {
          next[idx] = {
            ...next[idx],
            type: baseReportNode.type,
            data: { ...baseReportNode.data, ...(next[idx].data ?? {}) },
            position: reportPos,
          }
        } else {
          next.push({
            ...baseReportNode,
            id: reportNodeId,
            position: reportPos,
          })
        }
        return next
      })

      const edgeId = `e-${server}-${stage}-report-${stage}`
      const colorFrom = MCP_COLOR[server] ?? PALETTE.report
      ensureStageEdge(edgeId, serverNodeId, reportNodeId, colorFrom, PALETTE.report)

      requestAnimationFrame(() => {
        setEdgeActive(edgeId, true)
        window.setTimeout(() => setEdgeActive(edgeId, false), 1400)
      })
      layoutPlannedMCPs(stage)
    },
    [
      currentStageId,
      ensureStageNode,
      ensureStageEdge,
      setEdgeActive,
      getNodePos,
      H_GAP,
      setNodes,
      getNodeHeightById,
      layoutPlannedMCPs,
    ]
  )

  const handleAgentDone = useCallback(
    (stage_id?: number) => {
      const stage = stage_id ?? currentStageId ?? 1

      const reportNodeIds = nodesRef.current
        .filter(n => n.id.endsWith(`-report-${stage}`) && !n.id.startsWith('total-report'))
        .map(n => n.id)

      const totalBaseId = 'total-report'
      const totalId = `${totalBaseId}-${stage}`

      const centersY: number[] = []
      const xs: number[] = []

      for (const rid of reportNodeIds) {
        const p = getNodePos(rid)
        if (!p) continue

        const h = getNodeHeightById(rid)
        centersY.push(p.y + h / 2)
        xs.push(p.x)
      }

      const fallbackX = 960 + (stage - 1) * H_GAP
      const fallbackY = 330

      if (centersY.length > 0 && xs.length > 0) {
        const avgCenterY = centersY.reduce((a, b) => a + b, 0) / centersY.length
        const rightMostX = Math.max(...xs)

        const totalH = getNodeHeightById(totalBaseId)
        const yCandidate = avgCenterY - totalH / 2

        const totalPos = {
          x: rightMostX + 225,
          y: Number.isFinite(yCandidate) ? yCandidate : fallbackY,
        }

        setNodes(prev => {
          const next = [...prev]
          const idx = next.findIndex(n => n.id === totalId)
          const baseTotalNode = makeNode(totalBaseId)

          if (idx >= 0) {
            next[idx] = {
              ...next[idx],
              type: baseTotalNode.type,
              data: { ...baseTotalNode.data, ...(next[idx].data ?? {}) },
              position: totalPos,
            }
          } else {
            next.push({
              ...baseTotalNode,
              id: totalId,
              position: totalPos,
            })
          }
          return next
        })
      } else {
        setNodes(prev => {
          const next = [...prev]
          if (next.some(n => n.id === totalId)) return next
          const baseTotalNode = makeNode(totalBaseId)
          next.push({
            ...baseTotalNode,
            id: totalId,
            position: { x: fallbackX, y: fallbackY },
          })
          return next
        })
      }

      setEdges(eds => {
        const next = [...eds]
        for (const fromId of reportNodeIds) {
          const edgeId = `e-${fromId}-${totalId}`
          if (!next.some(e => e.id === edgeId)) {
            next.push(makeEdge(edgeId, fromId, totalId, PALETTE.report, PALETTE.total))
          }
        }
        return next
      })

      requestAnimationFrame(() => {
        scheduleFit(0)
        for (const fromId of reportNodeIds) {
          const edgeId = `e-${fromId}-${totalId}`
          setEdgeActive(edgeId, true)
        }
      })
    },
    [
      currentStageId,
      scheduleFit,
      setEdgeActive,
      setEdges,
      setNodes,
      getNodePos,
      getNodeHeightById,
      H_GAP,
    ]
  )

  useEffect(() => {
    if (!window.api?.onTotalReportLoaded) return

    const unsubscribe = window.api.onTotalReportLoaded(payload => {
      const stage = payload?.stageId ?? currentStageId ?? 1

      graphEvents.dispatchEvent(
        new CustomEvent('graph', {
          detail: { type: 'total-report-loaded', stage_id: stage, reportId: payload?.reportId },
        })
      )
    })

    return () => {
      unsubscribe?.()
    }
  }, [currentStageId])

  useEffect(() => {
    function onGraph(e: Event) {
      const d = (e as CustomEvent<GraphDetail>).detail
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

                const hasFrom = nodesRef.current.some(n => n.id === fromId)
                if (!hasFrom) return

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
        case 'add-initial':
          handleAddInitial()
          break
        case 'mcp-start':
          if (!MCP_SERVER_SET.has(d.server)) return
          handleMCPStart(d.server, d.stage_id)
          break
        case 'mcp-layout': {
          const stage = d.stageId ?? currentStageId ?? 1

          const uniq: MCPServer[] = Array.from(new Set(d.servers)).filter(
            s => MCP_COLOR[s] !== undefined
          )

          plannedServersRef.current[stage] = uniq

          const agentId = ensureStageNode('bgent', stage)
          uniq.forEach(server => {
            const serverId = ensureStageNode(server, stage)
            const edgeId = `e-bgent-${server}-${stage}`
            const colorTo = MCP_COLOR[server] ?? PALETTE.report
            ensureStageEdge(edgeId, agentId, serverId, PALETTE.bgent, colorTo)
          })

          layoutPlannedMCPs(stage)

          break
        }
        case 'mcp-done':
          handleMCPDone(d.server, d.stage_id)
          break
        case 'agent-done':
          handleAgentDone(d.stage_id)
          break
        case 'total-report-loaded': {
          const stage = d.stage_id ?? currentStageId ?? 1
          const totalId = `total-report-${stage}`

          setEdges(eds =>
            eds.map(e => {
              const isToThisTotal = e.target === totalId
              return isToThisTotal
                ? ({ ...e, data: { ...(e.data ?? {}), active: false } } as Edge)
                : e
            })
          )
          useUIStore.getState().setCurrentStageId(stage + 1)
          break
        }
      }
    }

    graphEvents.addEventListener('graph', onGraph)
    return () => graphEvents.removeEventListener('graph', onGraph)
  }, [
    setNodes,
    setEdges,
    setEdgeActive,
    scheduleFit,
    currentStageId,
    H_GAP,
    handleAddInitial,
    handleMCPStart,
    handleMCPDone,
    handleAgentDone,
    getNodePos,
    getNodeHeightById,
    ensureStageEdge,
    ensureStageNode,
    layoutPlannedMCPs,
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

      if (node.type === 'mcp') {
        if (mcpserverOpen && activeMCPServerId === id) {
          closeMCPServer()
          setActiveMCPServer(null)
        } else {
          setActiveMCPServer(id)
          openMCPServer()
        }
        return
      }

      if (id.includes('-report-') && !id.startsWith('total-report')) {
        const stageForNode = stageFromId > 0 ? stageFromId : 1
        const mcpName = id.replace(/-report-\d+$/, '').replace(/-\d+$/, '')

        useUIStore.getState().openMCPReport({
          triggerId: currentTriggerId ?? null,
          stageId: stageForNode,
          mcpName,
        })

        return
      }

      if (id.startsWith('total-report')) {
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

              if (!repId && reports.length > 0) {
                repId = reports[reports.length - 1]._id
              }
            } catch (err) {
              console.error('[graph] getConversationReports failed (stage)', stageForNode, err)
            }
          }

          if (!repId && currentTriggerId) {
            const trig = await getTrigger(currentTriggerId)
            const raw = trig?.report_id
            if (typeof raw === 'string') {
              repId = raw
            } else if (raw && typeof raw === 'object' && '$oid' in raw) {
              repId = (raw as { $oid: string }).$oid
            }
          }

          if (repId) {
            closeAllPanels()
            useUIStore.getState().setActiveTotalReportStageId(stageForNode)
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
      {!promptOpen && !conversationId && !selectedCaseId && (
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

      <MCPReportModal />
    </div>
  )
}
