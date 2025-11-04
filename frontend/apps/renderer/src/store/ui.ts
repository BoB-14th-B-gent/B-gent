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
  togglePrompt: () => void

  promptText: string
  setPromptText: (t: string) => void

  panelMessages: ChatMsg[]
  pushPanelMessage: (m: ChatMsg) => void
  clearPanelMessages: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  selectedNodeId: null,
  setSelectedNode: (id) => set({ selectedNodeId: id }),

  promptOpen: false,
  openPrompt: () => set({ promptOpen: true }),
  closePrompt: () => set({ promptOpen: false }),
  togglePrompt: () => set({ promptOpen: !get().promptOpen }),

  promptText: '',
  setPromptText: (t) => set({ promptText: t }),

  panelMessages: [],
  pushPanelMessage: (m) => set({ panelMessages: [...get().panelMessages, m] }),
  clearPanelMessages: () => set({ panelMessages: [] }),
}))