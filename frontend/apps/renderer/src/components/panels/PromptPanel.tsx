import { useUIStore, type ChatMsg } from '@/store/ui'
import { useCallback, useMemo, useRef, useEffect } from 'react'
import { dummyMessages } from '@/data/dummyMessages'

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

  const onSubmit = useCallback(() => {
    const text = promptText.trim()
    if (!text) return
    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: 'user', text }
    pushPanelMessage(userMsg)
    setPromptText('')
  }, [promptText, pushPanelMessage, setPromptText])

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

  const canSend = useMemo(() => promptText.trim().length > 0, [promptText])

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
        <button
          onClick={closePrompt}
          title="Close"
          style={{
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
          }}
        >
          x
        </button>
      </header>

      <div
        ref={scrollRef}
        className="panel-scroll"
        style={{
          padding: 14,
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {panelMessages.map(m => (
          <MessageBubble key={m.id} role={m.role} text={m.text} />
        ))}
      </div>

      <div
        style={{
          padding: 12,
          borderTop: '1px solid rgba(15,23,42,0.06)',
        }}
      >
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
            placeholder="B-gent! Be your Agent:)"
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
            }}
          />
          <button
            onClick={onSubmit}
            disabled={!canSend}
            style={{
              font: 'inherit',
              width: 25,
              height: 25,
              borderRadius: '50%',
              border: 'none',
              background: canSend ? '#034078' : '#9dbff8',
              color: '#fff',
              fontSize: 17,
              fontWeight: 700,
              cursor: canSend ? 'pointer' : 'default',
              margin: 3,
            }}
          >
            ↑
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
