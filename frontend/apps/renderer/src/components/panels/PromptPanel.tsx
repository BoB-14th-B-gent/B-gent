import { useUIStore, type ChatMsg } from '@/store/ui'
import { useCallback, useMemo, useRef, useEffect, useState } from 'react'
import { dummyMessages } from '@/data/dummyMessages'

const BASE = import.meta.env.VITE_BACKEND_URL

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    throw new Error(`[${resp.status}] ${resp.statusText} – ${text}`)
  }
  return resp.json() as Promise<T>
}

export default function PromptPanel() {
  const {
    promptOpen,
    promptText,
    setPromptText,
    closePrompt,
    panelMessages,
    pushPanelMessage,
    setPanelMessages,
  } = useUIStore()

  const [conversationId, setConversationId] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!promptOpen) return
    if (panelMessages.length > 0) return
    setPanelMessages(dummyMessages)
  }, [promptOpen, panelMessages.length, setPanelMessages])

  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [panelMessages.length, promptOpen])

  const autoGrow = () => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(160, el.scrollHeight)}px`
  }
  useEffect(() => {
    autoGrow()
  }, [promptText, promptOpen])

  const runReportFlow = useCallback(
    async (userText: string) => {
      let convId = conversationId
      if (!convId) {
        const conv = await api<{ _id: string; title: string; created_at: string }>(
          `/conversations`,
          {
            method: 'POST',
            body: JSON.stringify({ input: userText.slice(0, 60) || 'conversation' }),
          }
        )
        convId = conv._id
        setConversationId(convId)
      }

      await api(`/conversations/${convId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ role: 'USER', stage_id: 0, content: userText }),
      })

      const trig = await api<{ trigger_id: string; status: string; created_at: string }>(
        `/triggers`,
        { method: 'POST', body: JSON.stringify({ conversation_id: convId, stage_id: 0 }) }
      )
      const triggerId = trig.trigger_id

      const evIn = await api<{ prompt_id: string; items: { evidence_id: string }[] }>(
        `/evidences/input`,
        {
          method: 'POST',
          body: JSON.stringify({
            conversation_id: convId,
            mode: 'auto',
            inline_threshold: 10 * 1024 * 1024,
          }),
        }
      )
      const promptId = evIn.prompt_id
      const evRefs = evIn.items.map(x => ({ collection: 'INPUT_EVIDENCES', id: x.evidence_id }))

      await api(`/triggers/${triggerId}/prompt`, {
        method: 'PATCH',
        body: JSON.stringify({ prompt_id: promptId }),
      })

      await api(`/triggers/${triggerId}/evidences`, {
        method: 'PATCH',
        body: JSON.stringify({ evidences: evRefs }),
      })

      const sllm = await api<{ ok: boolean; report_id: string }>(`/sllm/reports`, {
        method: 'POST',
        body: JSON.stringify({ trigger_id: triggerId }),
      })
      const reportId = sllm.report_id

      await api(`/triggers/${triggerId}/report`, {
        method: 'PATCH',
        body: JSON.stringify({ report_id: reportId }),
      })

      const rep = await api<{ report: string; conversation_id: string }>(`/reports/${reportId}`, {
        method: 'GET',
      })

      await api(`/conversations/${convId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ role: 'B-GENT', stage_id: 0, content: rep.report }),
      })

      return rep.report
    },
    [conversationId]
  )

  const onSubmit = useCallback(async () => {
    const text = promptText.trim()
    if (!text || sending) return

    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: 'user', text }
    pushPanelMessage(userMsg)
    setPromptText('')

    setSending(true)
    try {
      const reportText = await runReportFlow(text)
      const botMsg: ChatMsg = { id: crypto.randomUUID(), role: 'bgent', text: reportText }
      pushPanelMessage(botMsg)
    } catch (err: any) {
      const botMsg: ChatMsg = {
        id: crypto.randomUUID(),
        role: 'bgent',
        text: `보고서 생성 중 오류가 발생했습니다.\n${err?.message ?? String(err)}`,
      }
      pushPanelMessage(botMsg)
      console.error('[report-flow]', err)
    } finally {
      setSending(false)
    }
  }, [promptText, sending, pushPanelMessage, setPromptText, runReportFlow])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.nativeEvent?.isComposing) return
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        onSubmit()
      }
    },
    [onSubmit]
  )

  const canSend = useMemo(() => !sending && promptText.trim().length > 0, [sending, promptText])

  return (
    <aside
      aria-hidden={!promptOpen}
      style={{
        position: 'fixed',
        top: 10,
        right: 10,
        bottom: 10,
        width: 'min(33.333vw, 620px)',
        minWidth: 360,
        fontFamily:
          "Pretendard, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif",
        background: 'rgba(255,255,255,0.78)',
        backdropFilter: 'saturate(120%) blur(10px)',
        border: '1px solid rgba(15,23,42,0.08)',
        borderRadius: 14,
        boxShadow: '0 10px 30px rgba(2,8,23,0.18)',
        boxSizing: 'border-box',
        transform: `translateX(${promptOpen ? '0' : 'calc(100% + 12px)'})`,
        transition: 'transform 240ms ease',
        zIndex: 50,
        display: 'grid',
        gridTemplateRows: 'auto 1fr auto',
      }}
    >
      <header
        style={{
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderBottom: '1px solid rgba(15,23,42,0.06)',
        }}
      >
        <span style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>USER PROMPT</span>
        <button onClick={closePrompt} title="Close" style={closeBtn}>
          x
        </button>
      </header>

      <div
        ref={scrollRef}
        className="panel-scroll"
        style={{ padding: 14, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}
      >
        {panelMessages.map(m => (
          <MessageBubble key={m.id} role={m.role} text={m.text} />
        ))}
      </div>

      <div style={{ padding: 12, borderTop: '1px solid rgba(15,23,42,0.06)' }}>
        <div
          style={{
            position: 'relative',
            background: '#fff',
            border: '1px solid rgba(15,23,42,0.08)',
            borderRadius: 10,
            padding: 4,
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'end',
            gap: 6,
          }}
        >
          <textarea
            ref={inputRef}
            value={promptText}
            onChange={e => {
              setPromptText(e.target.value)
              autoGrow()
            }}
            onKeyDown={onKeyDown}
            placeholder={sending ? '보고서 생성 중…' : 'B-gent! Be your Agent:)'}
            disabled={sending}
            style={{
              font: 'inherit',
              width: '100%',
              minHeight: 44,
              maxHeight: 160,
              resize: 'none',
              overflow: 'hidden',
              border: 'none',
              outline: 'none',
              padding: '10px 12px',
              borderRadius: 999,
              background: 'transparent',
              fontSize: 13,
              lineHeight: 1.5,
              opacity: sending ? 0.6 : 1,
            }}
          />
          <button
            onClick={onSubmit}
            disabled={!canSend}
            style={{
              font: 'inherit',
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: 'none',
              background: canSend ? '#034078' : '#9dbff8',
              color: '#fff',
              fontSize: 16,
              fontWeight: 700,
              cursor: canSend ? 'pointer' : 'default',
              margin: 3,
            }}
            title={sending ? '생성 중' : '보내기'}
          >
            {sending ? '…' : '↑'}
          </button>
        </div>
      </div>
    </aside>
  )
}

function MessageBubble({ role, text }: { role: 'user' | 'bgent'; text: string }) {
  const isUser = role === 'user'
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isUser ? 'flex-end' : 'flex-start',
        gap: 6,
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 550, color: '#334155', padding: '0 4px' }}>
        {isUser ? 'USER' : 'B-GENT'}
      </div>
      <div
        style={{
          maxWidth: '92%',
          background: isUser ? '#ffffff' : '#eef4ff',
          border: `1px solid ${isUser ? 'rgba(15,23,42,0.08)' : 'rgba(37,99,235,0.15)'}`,
          color: '#0f172a',
          padding: '8px 12px',
          borderRadius: 10,
          boxShadow: '0 4px 10px rgba(2,8,23,0.06)',
          textAlign: 'left',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          overflowWrap: 'break-word',
          lineHeight: 1.55,
          fontSize: 13,
          fontWeight: 400,
        }}
      >
        {text}
      </div>
    </div>
  )
}

const closeBtn: React.CSSProperties = {
  font: 'inherit',
  marginLeft: 'auto',
  width: 30,
  height: 30,
  borderRadius: 10,
  border: '1px solid rgba(15,23,42,0.08)',
  background: '#fff',
  lineHeight: '15px',
  textAlign: 'center',
  fontWeight: 500,
  color: '#0f172a',
  cursor: 'pointer',
}
