import { useEffect, useMemo, useRef } from 'react'
import { useUIStore } from '@/store/ui'
import { MCP_TOOLS, MCP_SERVER_NAMES, type MCPTool } from '@/data/dummyMCPServerTools'

export default function McpPanel() {
  const { mcpserverOpen, closeMCPServer, activeMCPServerId } = useUIStore()
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTop = 0
  }, [mcpserverOpen, activeMCPServerId])

  const serverName = MCP_SERVER_NAMES[activeMCPServerId ?? ''] ?? 'MCP Tools'
  const tools: MCPTool[] = useMemo(
    () => MCP_TOOLS[activeMCPServerId ?? ''] ?? [],
    [activeMCPServerId]
  )

  return (
    <aside
      aria-hidden={!mcpserverOpen}
      style={{
        width: '93%',
        height: '100%',
        margin: 'auto',
        fontFamily:
          "Pretendard, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif",
        background: 'rgba(255,255,255,0.78)',
        backdropFilter: 'saturate(120%) blur(10px)',
        border: '1px solid rgba(15,23,42,0.08)',
        borderRadius: 14,
        boxShadow: '0 10px 30px rgba(2,8,23,0.18)',
        boxSizing: 'border-box',
        overflow: 'hidden',
        transform: `translateY(${mcpserverOpen ? '0' : '8px'})`,
        opacity: mcpserverOpen ? 1 : 0,
        transition: 'opacity 200ms ease, transform 200ms ease',
        display: 'grid',
        gridTemplateRows: 'auto auto 1fr',
      }}
    >
      <header
        style={{
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderBottom: '1px solid rgba(15,23,42,0.06)',
        }}
      >
        <span style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>{serverName}</span>
        <button
          onClick={closeMCPServer}
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
          ×
        </button>
      </header>

      <div
        ref={scrollRef}
        className="panel-scroll"
        style={{
          padding: 14,
          overflow: 'auto',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
          gap: 14,
          alignContent: 'start',
        }}
      >
        {tools.map(t => (
          <article
            key={t.id}
            style={{
              background: '#fff',
              border: '1px solid rgba(15,23,42,0.08)',
              borderRadius: 12,
              padding: 12,
              boxShadow: '0 4px 10px rgba(2,8,23,0.06)',
              display: 'grid',
              gap: 6,
              minHeight: 80,
              overflow: 'hidden',
              wordBreak: 'break-word',
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a', wordBreak: 'break-word' }}>{t.name}</div>
            {t.desc && <div style={{ color: '#475569', fontSize: 12 }}>{t.desc}</div>}
          </article>
        ))}
        {tools.length === 0 && (
          <div style={{ color: '#64748b', fontSize: 13 }}>선택된 MCP 서버가 없습니다.</div>
        )}
      </div>
    </aside>
  )
}
