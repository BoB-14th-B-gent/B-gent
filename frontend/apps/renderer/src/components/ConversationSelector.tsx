import { useEffect, useState } from 'react'
import { listCaseConversations, getMessages, type ConversationSummary } from '@/utils/api'
import { useUIStore, type ChatMsg } from '@/store/ui'
import { formatKST } from '@/utils/date'
import { graphEvents } from '@/graph/events'

function normalizeLoadedReport(text: string): string {
  if (!text) return ''

  let out = text

  out = out.replace(/##\s*1\.\s*Executive Summary\s*/gi, '[Executive Summary]\n')

  out = out.replace(
    /##\s*6\.\s*Additional Evidence Required\s*/gi,
    '\n[Additional Evidence Required]\n'
  )

  return out.trim()
}

type Props = { refreshKey: number; sidebarOpen: boolean }

export default function ConversationSelector({ refreshKey, sidebarOpen }: Props) {
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<ConversationSummary[]>([])

  const conversationId = useUIStore(s => s.conversationId)
  const setConversationId = useUIStore(s => s.setConversationId)
  const setPanelMessages = useUIStore(s => s.setPanelMessages)
  const setPromptText = useUIStore(s => s.setPromptText)
  const setCurrentStageId = useUIStore(s => s.setCurrentStageId)
  const selectedCaseId = useUIStore(s => s.selectedCaseId)

  const fetchList = async (silent = false) => {
    if (!selectedCaseId) {
      setItems([])
      setLoading(false)
      return
    }
    if (!silent) setLoading(true)
    try {
      const list = await listCaseConversations(selectedCaseId)
      setItems(list ?? [])
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    fetchList(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey, selectedCaseId])

  useEffect(() => {
    if (!sidebarOpen) return
    if (!selectedCaseId) return

    const t = window.setInterval(() => {
      fetchList(true) // ✅ 폴링은 silent
    }, 1500)

    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sidebarOpen, selectedCaseId])

  const handleSelect = async (conv: ConversationSummary) => {
    if (!conv._id) return
    if (!selectedCaseId) return

    graphEvents.dispatchEvent(new CustomEvent('graph', { detail: { type: 'reset' } }))

    setConversationId(conv._id)
    setPromptText('')

    setCurrentStageId(conv.last_stage_id ?? 1)

    try {
      const msgs = await getMessages(conv._id, conv.last_stage_id ?? 1)

      const uiMsgs: ChatMsg[] = msgs.map(m => ({
        id: crypto.randomUUID(),
        role: m.role === 'USER' ? 'user' : 'bgent',
        text: normalizeLoadedReport(m.content ?? ''),
      }))

      setPanelMessages(uiMsgs)
    } catch (e) {
      console.error('[ConversationSelector] failed to load messages:', e)
      setPanelMessages([])
    }
  }

  return (
    <div
      style={{
        padding: '10px',
        background: 'rgba(255,255,255,0.6)',
        height: '100%',
        overflowY: 'auto',
      }}
    >
      {loading && <div style={{ marginTop: 8 }}>Loading...</div>}

      {!loading && items.length === 0 && (
        <div style={{ marginTop: 8, fontSize: 13, opacity: 0.7 }}>
          {selectedCaseId
            ? '이 케이스에는 아직 저장된 대화가 없습니다.'
            : '아직 저장된 대화가 없습니다.'}
        </div>
      )}

      {!loading &&
        items.map(conv => (
          <div
            key={conv._id}
            onClick={() => handleSelect(conv)}
            style={{
              padding: '6px 6px',
              cursor: 'pointer',
              borderRadius: 6,
              marginTop: 6,
              background: conversationId === conv._id ? 'rgba(49,108,214,0.15)' : 'transparent',
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 600 }}>{conv.title}</div>
            <div style={{ fontSize: 12, opacity: 0.6 }}>{formatKST(conv.created_at)}</div>
          </div>
        ))}
    </div>
  )
}
