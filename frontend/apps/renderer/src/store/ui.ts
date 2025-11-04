import { create } from 'zustand'

interface UIState {
  selectedNodeId: string | null
  setSelectedNode: (id: string | null) => void

  promptOpen: boolean
  togglePrompt: () => void
  openPrompt: () => void
  closePrompt: () => void

  promptText: string
  setPromptText: (t: string) => void
}

export const useUIStore = create<UIState>((set, get) => ({
  selectedNodeId: null,
  setSelectedNode: id => set({ selectedNodeId: id }),

  promptOpen: false,
  togglePrompt: () => set({ promptOpen: !get().promptOpen }),
  openPrompt: () => set({ promptOpen: true }),
  closePrompt: () => set({ promptOpen: false }),

  promptText: '',
  setPromptText: t => set({ promptText: t }),
}))
