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
  openPrompt: () => void
  closePrompt: () => void

  agentOpen: boolean
  openAgent: () => void
  closeAgent: () => void

  mcpserverOpen: boolean
  openMCPServer: () => void
  closeMCPServer: () => void

  activePromptId: string | null
  setActivePrompt: (id: string | null) => void
  activeAgentId: string | null
  setActiveAgent: (id: string | null) => void
  activeMCPServerId: string | null
  setActiveMCPServer: (id: string | null) => void

  closeAllPanels: () => void

  promptText: string
  setPromptText: (t: string) => void

  panelMessages: ChatMsg[]
  pushPanelMessage: (m: ChatMsg) => void
  clearPanelMessages: () => void

  setPanelMessages: (msgs: ChatMsg[]) => void
}

export const useUIStore = create<UIState>((set, get) => ({
  selectedNodeId: null,
  setSelectedNode: id => set({ selectedNodeId: id }),

  promptOpen: false,
  agentOpen: false,
  mcpserverOpen: false,

  activePromptId: null,
  setActivePrompt: id => set({ activePromptId: id }),
  activeAgentId: null,
  setActiveAgent: id => set({ activeAgentId: id }),
  activeMCPServerId: null,
  setActiveMCPServer: id => set({ activeMCPServerId: id }),

  openPrompt: () => {
    const sel = get().selectedNodeId
    set({ promptOpen: true, activePromptId: sel ?? get().activePromptId })
  },
  closePrompt: () => set({ promptOpen: false, activePromptId: null }),

  openAgent: () => {
    const sel = get().selectedNodeId
    set({ agentOpen: true, activeAgentId: sel ?? get().activeAgentId })
  },
  closeAgent: () => set({ agentOpen: false, activeAgentId: null }),

  openMCPServer: () => {
    const sel = get().selectedNodeId
    set({ mcpserverOpen: true, activeMCPServerId: sel ?? get().activeMCPServerId })
  },
  closeMCPServer: () => set({ mcpserverOpen: false, activeMCPServerId: null }),

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
}))
