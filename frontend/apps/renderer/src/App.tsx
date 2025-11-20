import { useState } from 'react'
import Diagram from './components/Diagram'
import ConversationSelector from './components/ConversationSelector'
import { useUIStore } from '@/store/ui'

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [convRefreshKey, setConvRefreshKey] = useState(0)

  const openSidebar = () => {
    setSidebarOpen(true)
    setConvRefreshKey(k => k + 1)
  }

  const resetForConversation = useUIStore(s => s.resetForConversation)
  const openPrompt = useUIStore(s => s.openPrompt)

  const handleNewConversation = () => {
    resetForConversation(null, 1)
    openPrompt()
    setConvRefreshKey(k => k + 1)
  }

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-gradient-to-br from-sky-50 via-blue-50 to-indigo-50">
      {!sidebarOpen && (
        <button
          onClick={openSidebar}
          className="absolute top-4 left-4 z-20 rounded-xl border border-slate-300/80 bg-white/90 px-3 py-1.5 text-base font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
        >
          ☰ Conversations
        </button>
      )}

      <div className="flex h-full">
        {sidebarOpen && (
          <aside className="relative z-10 flex h-full w-80 flex-col border-r border-slate-200/70 bg-white/80 backdrop-blur-sm">
            <div className="flex items-center justify-between border-b border-slate-200/70 bg-white/90 px-4 py-3">
              <span className="text-sm font-bold tracking-wide text-slate-700">CONVERSATIONS</span>
              <button
                onClick={() => setSidebarOpen(false)}
                className="rounded-md px-2 py-0.5 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-700"
              >
                ✕
              </button>
            </div>

            <div className="border-b border-slate-200/70 bg-slate-50/50 p-2">
              <button
                onClick={handleNewConversation}
                className="flex w-full items-center justify-center rounded-lg border border-blue-400 bg-white/80 px-3 py-2 text-sm font-medium text-blue-600 shadow-md transition hover:border-blue-500 hover:bg-blue-100 hover:text-blue-700 hover:shadow-lg"
              >
                + 새 대화 시작
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <ConversationSelector refreshKey={convRefreshKey} />
            </div>
          </aside>
        )}

        <main className="h-full min-w-0 flex-1">
          <Diagram sidebarOpen={sidebarOpen} />
        </main>
      </div>
    </div>
  )
}
