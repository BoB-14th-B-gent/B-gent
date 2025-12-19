import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

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

  mcpreportOpen: boolean
  activeMCPReport: null | { triggerId: string; stageId: number; mcpName: string }
  openMCPReport: (p: { triggerId: string; stageId: number; mcpName: string }) => void
  closeMCPReport: () => void

  totalreportOpen: boolean
  activeTotalReportId: string | null
  openTotalReport: (id?: string | null) => void
  closeTotalReport: () => void

  activeTotalReportStageId: number | null
  setActiveTotalReportStageId: (n: number | null) => void

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

  currentStageId: number
  setCurrentStageId: (n: number) => void

  loadedConversationTitle: string | null
  setLoadedConversationTitle: (title: string | null) => void

  resetForConversation: (conversationId: string | null, stageId?: number) => void

  sidebarOpen: boolean
  toggleSidebar: () => void

  selectedCaseId: string | null
  selectedCaseName: string | null
  caseModalOpen: boolean
  openCaseModal: () => void
  closeCaseModal: () => void
  setSelectedCase: (id: string | null, name: string | null) => void

  afterAgentRunByTrigger: Record<string, true>
  hasAfterAgentRun: (triggerId: string) => boolean
  setAfterAgentRun: (triggerId: string, v: boolean) => void

  resetSession: () => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
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

      mcpreportOpen: false,
      activeMCPReport: null,
      openMCPReport: p => set({ mcpreportOpen: true, activeMCPReport: p }),
      closeMCPReport: () => set({ mcpreportOpen: false, activeMCPReport: null }),

      totalreportOpen: false,
      activeTotalReportId: null,
      openTotalReport: (id = null) => set({ totalreportOpen: true, activeTotalReportId: id }),
      closeTotalReport: () =>
        set({
          totalreportOpen: false,
          activeTotalReportId: null,
          activeTotalReportStageId: null,
        }),

      activeTotalReportStageId: null,
      setActiveTotalReportStageId: n => set({ activeTotalReportStageId: n }),

      closeAllPanels: () =>
        set({
          promptOpen: false,
          agentOpen: false,
          mcpserverOpen: false,
          mcpreportOpen: false,
          totalreportOpen: false,
          activePromptId: null,
          activeAgentId: null,
          activeMCPServerId: null,
          activeMCPReport: null,
          activeTotalReportId: null,
          activeTotalReportStageId: null,
        }),

      promptText: '',
      setPromptText: t => set({ promptText: t }),

      panelMessages: [],
      pushPanelMessage: m => set({ panelMessages: [...get().panelMessages, m] }),
      clearPanelMessages: () => set({ panelMessages: [] }),
      setPanelMessages: msgs => set({ panelMessages: msgs }),

      totalReportRaw: '',
      setTotalReportRaw: raw => set({ totalReportRaw: raw }),

      conversationId: null,
      setConversationId: id => set({ conversationId: id }),

      currentTriggerId: null,
      setCurrentTriggerId: id => set({ currentTriggerId: id }),

      currentStageId: 1,
      setCurrentStageId: n => set({ currentStageId: n }),

      loadedConversationTitle: null,
      setLoadedConversationTitle: title => set({ loadedConversationTitle: title }),

      resetForConversation: (conversationId, stageId) => {
        set({
          conversationId,
          currentStageId: stageId ?? 1,
          currentTriggerId: null,
          selectedNodeId: null,
          panelMessages: [],
          totalReportRaw: '',
          loadedConversationTitle: null,
        })
      },

      sidebarOpen: false,
      toggleSidebar: () => set({ sidebarOpen: !get().sidebarOpen }),

      selectedCaseId: null,
      selectedCaseName: null,
      caseModalOpen: true,

      openCaseModal: () => set({ caseModalOpen: true }),
      closeCaseModal: () => set({ caseModalOpen: false }),
      setSelectedCase: (id, name) =>
        set({
          selectedCaseId: id,
          selectedCaseName: name,
          caseModalOpen: false,
        }),

      afterAgentRunByTrigger: {},
      hasAfterAgentRun: triggerId => !!get().afterAgentRunByTrigger[triggerId],
      setAfterAgentRun: (triggerId, v) =>
        set(state => {
          const next = { ...state.afterAgentRunByTrigger }
          if (v) next[triggerId] = true
          else delete next[triggerId]
          return { afterAgentRunByTrigger: next }
        }),

      resetSession: () =>
        set({
          conversationId: null,
          currentStageId: 1,
          currentTriggerId: null,

          selectedNodeId: null,
          panelMessages: [],
          totalReportRaw: '',

          promptOpen: false,
          agentOpen: false,
          mcpserverOpen: false,
          mcpreportOpen: false,
          totalreportOpen: false,

          activePromptId: null,
          activeAgentId: null,
          activeMCPServerId: null,
          activeMCPReport: null,
          activeTotalReportId: null,
          activeTotalReportStageId: null,
        }),
    }),
    {
      name: 'bgent-ui-store',
      storage: createJSONStorage(() => localStorage),

      partialize: s => ({
        selectedCaseId: s.selectedCaseId,
        selectedCaseName: s.selectedCaseName,
        sidebarOpen: s.sidebarOpen,
      }),
    }
  )
)
