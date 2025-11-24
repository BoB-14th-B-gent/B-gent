import { useState, useEffect } from 'react'
import Diagram from './components/Diagram'
import ConversationSelector from './components/ConversationSelector'
import { useUIStore } from '@/store/ui'
import CaseSelectModal from './components/CaseSelector'
import { getCase } from '@/utils/api'

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [convRefreshKey, setConvRefreshKey] = useState(0)

  const resetForConversation = useUIStore(s => s.resetForConversation)
  const openPrompt = useUIStore(s => s.openPrompt)
  const caseModalOpen = useUIStore(s => s.caseModalOpen)
  const selectedCaseId = useUIStore(s => s.selectedCaseId)
  const selectedCaseName = useUIStore(s => s.selectedCaseName)

  const openCaseModal = useUIStore(s => s.openCaseModal)
  const setSelectedCase = useUIStore(s => s.setSelectedCase)

  useEffect(() => {
    const hash = window.location.hash || ''

    const isCaseWindow = hash.startsWith('#/case-window')
    if (isCaseWindow) {
      const qIndex = hash.indexOf('?')
      if (qIndex === -1) return

      const search = new URLSearchParams(hash.slice(qIndex + 1))
      const caseIdFromUrl = search.get('caseId')
      if (!caseIdFromUrl) return

      setSelectedCase(caseIdFromUrl, 'Loading...')

      getCase(caseIdFromUrl)
        .then(c => {
          setSelectedCase(c._id, c.name)
        })
        .catch(err => {
          console.error('[App] failed to load case from URL:', err)
          setSelectedCase(caseIdFromUrl, '(Unknown case)')
        })
    } else {
      openCaseModal()
    }
  }, [openCaseModal, setSelectedCase])

  const openSidebar = () => {
    setSidebarOpen(true)
    setConvRefreshKey(k => k + 1)
  }

  const handleNewConversation = () => {
    if (!selectedCaseId) {
      openCaseModal()
      return
    }

    resetForConversation(null, 1)
    openPrompt()
    setConvRefreshKey(k => k + 1)
  }

  const handleOpenCaseInNewWindow = () => {
    if (!selectedCaseId) return
    window.api?.openCaseWindow?.({ caseId: selectedCaseId })
  }

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-gradient-to-br from-sky-50 via-blue-50 to-indigo-50">
      {caseModalOpen && <CaseSelectModal />}

      <div className="absolute top-3 right-3 z-30 flex items-center gap-2 rounded-full border border-slate-300/70 bg-white/90 px-3 py-1.5 shadow-sm">
        <span className="text-sm font-medium text-slate-500">CASE</span>
        <span className="text-base font-semibold whitespace-nowrap text-slate-800">
          {selectedCaseName || '선택된 Case 없음'}
        </span>

        <button
          onClick={openCaseModal}
          className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm text-slate-600 hover:bg-slate-100"
        >
          변경
        </button>

        <button
          onClick={handleOpenCaseInNewWindow}
          disabled={!selectedCaseId}
          className="rounded-full border border-blue-500/70 bg-blue-50 px-2 py-0.5 text-sm text-blue-600 hover:bg-blue-100 disabled:cursor-default disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
        >
          새창
        </button>
      </div>

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
              <span className="text-base font-bold tracking-wide text-slate-700">
                CONVERSATIONS
              </span>
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
                className="flex w-full items-center justify-center rounded-lg border border-blue-600 bg-white/80 px-3 py-2 text-sm font-medium text-blue-600 shadow-md transition hover:border-blue-500 hover:bg-blue-100 hover:text-blue-700 hover:shadow-lg"
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
