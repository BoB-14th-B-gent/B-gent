import { create } from 'zustand'

export type ChatRole = 'user' | 'bgent'
export interface ChatMsg {
  id: string
  role: ChatRole
  text: string
}

interface UIState {
  selectedNodeId: string | null
  setSelectedNode: (id: string | null) => void

  promptOpen: boolean
  activePromptId: string | null
  setActivePrompt: (id: string | null) => void
  openPrompt: () => void
  closePrompt: () => void

  agentOpen: boolean
  activeAgentId: string | null
  setActiveAgent: (id: string | null) => void
  openAgent: () => void
  closeAgent: () => void

  mcpserverOpen: boolean
  activeMCPServerId: string | null
  setActiveMCPServer: (id: string | null) => void
  openMCPServer: () => void
  closeMCPServer: () => void

  totalreportOpen: boolean
  activeTotalReportId: string | null
  setActiveTotalReport: (id: string | null) => void
  openTotalReport: (id?: string | null) => void
  closeTotalReport: () => void

  closeAllPanels: () => void

  promptText: string
  setPromptText: (t: string) => void

  panelMessages: ChatMsg[]
  pushPanelMessage: (m: ChatMsg) => void
  clearPanelMessages: () => void

  setPanelMessages: (msgs: ChatMsg[]) => void

  totalReportRaw: string
  setTotalReportRaw: (raw: string) => void

  conversationId: string | null
  setConversationId: (id: string | null) => void
  currentTriggerId: string | null
  setCurrentTriggerId: (id: string | null) => void
}

export const useUIStore = create<UIState>((set, get) => ({
  selectedNodeId: null,
  setSelectedNode: id => set({ selectedNodeId: id }),

  promptOpen: false,
  activePromptId: null,
  setActivePrompt: id => set({ activePromptId: id }),
  openPrompt: () => set({ promptOpen: true }),
  closePrompt: () => set({ promptOpen: false, activePromptId: null }),

  agentOpen: false,
  activeAgentId: null,
  setActiveAgent: id => set({ activeAgentId: id }),
  openAgent: () => set({ agentOpen: true }),
  closeAgent: () => set({ agentOpen: false, activeAgentId: null }),

  mcpserverOpen: false,
  activeMCPServerId: null,
  setActiveMCPServer: id => set({ activeMCPServerId: id }),
  openMCPServer: () => set({ mcpserverOpen: true }),
  closeMCPServer: () => set({ mcpserverOpen: false, activeMCPServerId: null }),

  totalreportOpen: false,
  activeTotalReportId: null,
  setActiveTotalReport: id => set({ activeTotalReportId: id }),
  openTotalReport: (id = null) => set({ totalreportOpen: true, activeTotalReportId: id }),
  closeTotalReport: () => set({ totalreportOpen: false, activeTotalReportId: null }),

  closeAllPanels: () =>
    set({
      promptOpen: false,
      agentOpen: false,
      mcpserverOpen: false,
      activePromptId: null,
      activeAgentId: null,
      activeMCPServerId: null,
    }),

  promptText: '',
  setPromptText: t => set({ promptText: t }),

  panelMessages: [],
  pushPanelMessage: m => set({ panelMessages: [...get().panelMessages, m] }),
  clearPanelMessages: () => set({ panelMessages: [] }),
  setPanelMessages: (msgs: ChatMsg[]) => set({ panelMessages: msgs }),

  totalReportRaw: '',
  setTotalReportRaw: (raw: string) => set({ totalReportRaw: raw }),

  conversationId: null,
  setConversationId: id => set({ conversationId: id }),
  currentTriggerId: null,
  setCurrentTriggerId: id => set({ currentTriggerId: id }),
}))
