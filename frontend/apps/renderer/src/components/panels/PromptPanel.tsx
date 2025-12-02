import { useUIStore, type ChatMsg } from '@/store/ui'
import { useCallback, useMemo, useRef, useEffect, useState } from 'react'
import { graphEvents } from '@/graph/events'
import { makeNode, makeEdge, PALETTE } from '@/graph/dynamicLayout'
import { pipelineRun, getReport, type PipelineRunReq } from '@/utils/api'

function emitGraph(detail: unknown) {
  graphEvents.dispatchEvent(new CustomEvent('graph', { detail }))
}

export default function PromptPanel() {
  const {
    promptOpen,
    promptText,
    setPromptText,
    closePrompt,
    panelMessages,
    pushPanelMessage,
    setConversationId: setConvIdInStore,
    setCurrentTriggerId,
    conversationId,
    currentStageId,
    setCurrentStageId,
    selectedCaseId,
  } = useUIStore()

  const [sending, setSending] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!promptOpen) return
    const t = setTimeout(() => inputRef.current?.focus(), 50)
    return () => clearTimeout(t)
  }, [promptOpen])

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

  const H_GAP = 1105

  const onSubmit = useCallback(async () => {
    const text = promptText.trim()
    if (!text || sending) return

    const stageToUse = currentStageId ?? 1

    const basePrompt = makeNode('prompt')
    const promptNodeId = `prompt-${stageToUse}`
    const promptNode = {
      ...basePrompt,
      id: promptNodeId,
      position: {
        ...basePrompt.position,
        x: basePrompt.position.x + (stageToUse - 1) * H_GAP,
      },
    }

    const baseAgent = makeNode('bgent')
    const agentNodeId = `bgent-${stageToUse}`
    const agentNode = {
      ...baseAgent,
      id: agentNodeId,
      position: {
        ...baseAgent.position,
        x: baseAgent.position.x + (stageToUse - 1) * H_GAP,
      },
    }

    emitGraph({ type: 'add-node', node: promptNode })
    emitGraph({ type: 'add-node', node: agentNode })
    emitGraph({
      type: 'add-edge',
      edge: makeEdge(
        `e-${promptNodeId}-${agentNodeId}`,
        promptNodeId,
        agentNodeId,
        PALETTE.prompt,
        PALETTE.bgent
      ),
    })

    if (stageToUse > 1) {
      const prevTotalId = `total-report-${stageToUse - 1}`
      const edgeId = `e-${prevTotalId}-${promptNodeId}`
      emitGraph({
        type: 'add-edge',
        edge: makeEdge(edgeId, prevTotalId, promptNodeId, PALETTE.total, PALETTE.prompt),
      })
    }

    emitGraph({ type: 'fit' })

    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: 'user', text }
    pushPanelMessage(userMsg)
    setPromptText('')
    setSending(true)

    try {
      const payload: PipelineRunReq = {
        input: text,
        stage_id: stageToUse,
      }
      if (conversationId) {
        payload.conversation_id = conversationId
      }
      if (selectedCaseId) {
        payload.case_id = selectedCaseId
      }

      const res = await pipelineRun(payload)

      if (!conversationId) {
        setConvIdInStore?.(res.conversation_id)
      }
      setCurrentTriggerId?.(res.trigger_id)

      setCurrentStageId?.(stageToUse + 1)

      const reportDoc = await getReport(res.report_id)

      let summary = ''
      const s = (reportDoc as any)?.structured?.sections
      if (s) {
        const execArr = s['executive summary'] ?? []
        const addArr = s['additional evidence required'] ?? []

        const execPart = Array.isArray(execArr)
          ? execArr.map((x: any) => `- ${x.bullet || x}`).join('\n')
          : '- (none)'
        const addPart = Array.isArray(addArr)
          ? addArr.map((x: any) => `- ${x.what || x}`).join('\n')
          : '- (none)'

        summary = `[Executive Summary]\n${execPart}\n\n[Additional Evidence Required]\n${addPart}`
      }

      if (summary.trim()) {
        const summaryMsg: ChatMsg = {
          id: crypto.randomUUID(),
          role: 'bgent',
          text: summary,
        }
        pushPanelMessage(summaryMsg)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      const botMsg: ChatMsg = {
        id: crypto.randomUUID(),
        role: 'bgent',
        text: `보고서 생성 중 오류가 발생했습니다.\n${msg}`,
      }
      pushPanelMessage(botMsg)
      console.error('[pipeline-run]', err)
    } finally {
      setSending(false)
    }
  }, [
    promptText,
    sending,
    pushPanelMessage,
    setPromptText,
    setConvIdInStore,
    setCurrentTriggerId,
    currentStageId,
    setCurrentStageId,
    conversationId,
    selectedCaseId,
  ])

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

  const isIntro = panelMessages.length === 0
  const shellStyle: React.CSSProperties = {
    position: 'fixed',
    top: 10,
    right: 10,
    bottom: 10,
    width: isIntro ? 'min(50vw, 820px)' : 'min(33.333vw, 620px)',
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
    transition: 'transform 240ms ease, width 300ms ease',
    zIndex: 50,
    display: 'grid',
    gridTemplateRows: 'auto 1fr auto',
  }

  return (
    <aside aria-hidden={!promptOpen} style={shellStyle}>
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
          ×
        </button>
      </header>

      <div
        ref={scrollRef}
        className="panel-scroll"
        style={{
          position: 'relative',
          padding: 14,
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {isIntro && (
          <div
            style={{
              flexGrow: 1,
              display: 'grid',
              placeItems: 'center',
              textAlign: 'center',
              paddingBottom: 80,
            }}
          >
            <div style={{ opacity: 0.25, userSelect: 'none', pointerEvents: 'none' }}>
              <span
                style={{
                  fontSize: 80,
                  fontWeight: 900,
                  color: '#034078',
                  letterSpacing: '2px',
                  lineHeight: 1.1,
                }}
              >
                B-GENT
              </span>
              <p style={{ marginTop: 10, fontSize: 16, color: '#475569', fontWeight: 600 }}>
                분석을 시작하려면 아래에 사건 정보를 입력하세요.
              </p>
            </div>
          </div>
        )}

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
            placeholder={
              sending
                ? '보고서 생성 중…'
                : isIntro
                  ? '분석할 사건에 대한 설명과 증거파일명을 작성해주세요.'
                  : 'B-gent! Be your Agent:)'
            }
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
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
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
