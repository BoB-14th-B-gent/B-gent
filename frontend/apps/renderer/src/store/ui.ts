import { create } from 'zustand';

export type UIState = {
  panelOpen: boolean;
  selectedNodeId: string | null;
  openPanel: () => void;
  closePanel: () => void;
  setSelectedNode: (id: string | null) => void;
};

export const useUIStore = create<UIState>((set) => ({
  panelOpen: false,
  selectedNodeId: null,
  openPanel: () => set({ panelOpen: true }),
  closePanel: () => set({ panelOpen: false }),
  setSelectedNode: (id) => set({ selectedNodeId: id }),
}));