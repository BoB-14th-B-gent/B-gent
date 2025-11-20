import { useRef, useEffect, useMemo, useState } from 'react'
import { useUIStore } from '@/store/ui'
import {
  startDummyAgentStream1,
  type TaskStatus as PlanTaskStatus,
  type PlanTask,
} from '@/data/dummyAgentStream'
import { startDummyAgentStream2 } from '@/data/dummyAgentStream2'

export type StepStatus = 'pending' | 'running' | 'done' | 'failed'
interface AgentStep {
  id: string
  title: string
  detail?: string
  status: StepStatus
  startedAt?: string
  updatedAt?: string
  finishedAt?: string
}

function mapPlanStatusToStepStatus(s: PlanTaskStatus): StepStatus {
  if (s === 'in_progress') return 'running'
  return s as StepStatus
}

export default function AgentPanel() {
  const agentOpen = useUIStore(s => s.agentOpen);
  const closeAgent = useUIStore(s => s.closeAgent);
  const currentStageId = useUIStore(s => s.currentStageId);

  const [steps, setSteps] = useState<AgentStep[]>([])
  const [logs, setLogs] = useState<string[]>([])
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [agentStatus, setAgentStatus] = useState<'running' | 'done' | 'failed'>('running')

  const [toolSteps, setToolSteps] = useState<AgentStep[]>([])

  const startedAtRef = useRef<Record<string, string>>({})
  const finishedAtRef = useRef<Record<string, string>>({})
  const updatedAtRef = useRef<Record<string, string>>({})
  const prevStatusRef = useRef<Record<string, PlanTaskStatus>>({})

  useEffect(() => {
    if (!agentOpen) return
    startedAtRef.current = {}
    finishedAtRef.current = {}
    updatedAtRef.current = {}
    prevStatusRef.current = {}
  }, [agentOpen])

  function toToolSteps(plan: PlanTask[], updatedAt?: string): AgentStep[] {
    const out: AgentStep[] = []
    for (const p of plan) {
      const tools = p.mcp_tools ?? []
      if (tools.length === 0) {
        if (p.status === 'in_progress') {
          out.push({
            id: `${p.task_id}__waiting`,
            title: `${p.mcp_server ?? 'MCP'}: 준비 중`,
            status: 'running',
            startedAt: updatedAt?.slice(11, 19),
          })
        }
        continue
      }
      tools.forEach((tool, idx) => {
        const isLast = idx === tools.length - 1
        const status: StepStatus = p.status === 'done' ? 'done' : isLast ? 'running' : 'done'
        out.push({
          id: `${p.task_id}__${tool}`,
          title: `${p.mcp_server ?? 'MCP'}: ${tool}`,
          status,
          startedAt: status === 'running' ? updatedAt?.slice(11, 19) : undefined,
          finishedAt: status === 'done' ? updatedAt?.slice(11, 19) : undefined,
        })
      })
    }
    return out
  }

  useEffect(() => {
    if (!agentOpen) return

    setSteps([])
    setLogs([])
    setUpdatedAt(null)
    setAgentStatus('running')

    const streamFunc = currentStageId === 2 
      ? startDummyAgentStream2
      : startDummyAgentStream1

    const stop = streamFunc({
      stepMs: 500,
      onEvent: ev => {
        if (ev.type === 'state_update' && ev.data) {
          const ts = ev.data.updated_at?.slice(11, 19) ?? ''

          for (const p of ev.data.plan) {
            const prev = prevStatusRef.current[p.task_id]

            if (
              prev !== 'in_progress' &&
              p.status === 'in_progress' &&
              !startedAtRef.current[p.task_id]
            ) {
              startedAtRef.current[p.task_id] = ts
            }
            if (p.status === 'in_progress') {
              updatedAtRef.current[p.task_id] = ts
            }
            if (prev !== 'done' && p.status === 'done' && !finishedAtRef.current[p.task_id]) {
              finishedAtRef.current[p.task_id] = ts
            }

            prevStatusRef.current[p.task_id] = p.status
          }

          const nextSteps: AgentStep[] = ev.data.plan.map(p => {
            const tools = p.mcp_tools ?? []
            const lastTool = tools.length ? tools[tools.length - 1] : '준비 중'

            return {
              id: p.task_id,
              title: p.description,
              detail: `${p.mcp_server} · ${lastTool}`,
              status: mapPlanStatusToStepStatus(p.status),
              startedAt: startedAtRef.current[p.task_id],
              finishedAt: finishedAtRef.current[p.task_id],
              updatedAt: updatedAtRef.current[p.task_id],
            }
          })

          setSteps(nextSteps)
          setToolSteps(toToolSteps(ev.data.plan ?? [], ev.data.updated_at))
          setUpdatedAt(ev.data.updated_at)
          setAgentStatus(
            ev.data.status === 'done' || ev.data.status === 'completed' ? 'done' : 'running'
          )
        } else if (ev.type === 'log' && ev.text) {
          setLogs(prev => [...prev, ev.text])
        }
      },
    })

    return () => {
      stop?.()
    }
  }, [agentOpen, currentStageId])

  const doneCount = useMemo(() => steps.filter(s => s.status === 'done').length, [steps])
  const runningCount = useMemo(() => steps.filter(s => s.status === 'running').length, [steps])
  const total = useMemo(() => steps.length || 1, [steps])
  const progress = Math.round(((doneCount + runningCount * 0.5) / total) * 100)

  const allDone = useMemo(
    () => (steps.length > 0 && steps.every(s => s.status === 'done')) || agentStatus === 'done',
    [steps, agentStatus]
  )
  const currentRunning = useMemo(() => steps.find(s => s.status === 'running'), [steps])

  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTop = 0
  }, [agentOpen])

  return (
    <aside
      aria-hidden={!agentOpen}
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
        transform: `translateY(${agentOpen ? '0' : '8px'})`,
        opacity: agentOpen ? 1 : 0,
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
        <span style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>AGENT</span>
        <span style={{ fontSize: 12, color: '#475569', marginLeft: 8 }}>
          {allDone ? 'DONE' : 'RUNNING'}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {updatedAt && (
            <span style={{ fontSize: 11, color: '#64748b' }}>
              갱신: {updatedAt.replace('T', ' ').slice(0, 19)}
            </span>
          )}
          <span
            title="진행률"
            style={{
              fontSize: 12,
              color: '#0f172a',
              background: '#eef2ff',
              border: '1px solid rgba(37,99,235,0.18)',
              padding: '4px 8px',
              borderRadius: 999,
              fontWeight: 600,
            }}
          >
            {allDone ? 100 : progress}% 진행
          </span>

          <button
            onClick={closeAgent}
            title="Close"
            style={{
              font: 'inherit',
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
        </div>
      </header>

      <div
        aria-hidden
        style={{ height: 4, background: 'rgba(15,23,42,0.06)', position: 'relative' }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            width: `${allDone ? 100 : progress}%`,
            background: 'linear-gradient(90deg, #034078, rgba(59,130,246,0.85))',
            transition: 'width 240ms ease',
          }}
        />
      </div>

      <div
        ref={scrollRef}
        className="panel-scroll"
        style={{
          padding: 14,
          overflow: 'auto',
          display: 'grid',
          gridTemplateColumns: '1fr',
          gap: 14,
        }}
      >
        <section
          style={{
            background: '#ffffff',
            border: '1px solid rgba(15,23,42,0.08)',
            borderRadius: 12,
            padding: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                display: 'inline-flex',
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: currentRunning ? '#22c55e' : allDone ? '#034078' : '#cbd5e1',
              }}
            />
            <strong style={{ fontSize: 14, color: '#0f172a' }}>현재 단계</strong>
            <span style={{ marginLeft: 'auto', fontSize: 12, color: '#475569' }}>
              실시간 업데이트
            </span>
          </div>
          <div style={{ marginTop: 8, fontSize: 13, color: '#0f172a' }}>
            {currentRunning ? (
              <>
                <b>{currentRunning.title}</b>
                {currentRunning.detail && (
                  <div style={{ marginTop: 4, color: '#475569' }}>{currentRunning.detail}</div>
                )}
              </>
            ) : allDone ? (
              <div style={{ fontSize: 13, color: '#0f172a' }}>
                <b>모든 단계 완료</b>
                <div style={{ marginTop: 4, color: '#475569' }}>
                  {updatedAt
                    ? `완료 시각: ${updatedAt.replace('T', ' ').slice(0, 19)}`
                    : '완료되었습니다.'}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: '#475569' }}>MCP Server 로딩 중…</div>
            )}
          </div>
        </section>

        <section
          style={{
            background: '#ffffff',
            border: '1px solid rgba(15,23,42,0.08)',
            borderRadius: 12,
            padding: 12,
          }}
        >
          <strong style={{ fontSize: 14, color: '#0f172a' }}>단계 진행</strong>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, marginTop: 8 }}>
            {steps.map(step => (
              <li
                key={step.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'auto 1fr auto',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 6px',
                  borderRadius: 8,
                  background: step.status === 'running' ? 'rgba(59,130,246,0.08)' : 'transparent',
                }}
              >
                <StatusDot status={step.status} />
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 13,
                      color: '#0f172a',
                      fontWeight: step.status === 'running' ? 700 : 600,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {step.title}
                  </div>
                  {step.detail ? (
                    <div
                      style={{
                        fontSize: 12,
                        color: '#475569',
                        marginTop: 2,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={step.detail}
                    >
                      {step.detail}
                    </div>
                  ) : null}
                </div>

                <div style={{ textAlign: 'right', color: '#64748b', fontSize: 12 }}>
                  {step.status === 'done' && step.finishedAt
                    ? step.finishedAt
                    : step.status === 'running'
                      ? step.updatedAt || step.startedAt || '—'
                      : '—'}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section
          style={{
            background: '#ffffff',
            border: '1px solid rgba(15,23,42,0.08)',
            borderRadius: 12,
            padding: 12,
          }}
        >
          <strong style={{ fontSize: 14, color: '#0f172a' }}>최근 로그</strong>
          <div
            style={{
              marginTop: 8,
              fontSize: 12,
              color: '#0f172a',
              background: '#f8fafc',
              border: '1px solid rgba(15,23,42,0.06)',
              borderRadius: 8,
              padding: 10,
              lineHeight: 1.5,
              whiteSpace: 'pre-wrap',
              maxHeight: 220,
              overflow: 'auto',
            }}
          >
            {logs.length ? logs.join('\n') : '—'}
          </div>
        </section>
      </div>
    </aside>
  )
}

function StatusDot({ status }: { status: StepStatus }) {
  const base: React.CSSProperties = {
    width: 12,
    height: 12,
    borderRadius: '50%',
    display: 'inline-block',
  }
  if (status === 'done') {
    return (
      <span
        title="완료"
        style={{
          ...base,
          background: '#034078',
          boxShadow: '0 0 0 3px rgba(34,197,94,0.18) inset',
        }}
      />
    )
  }
  if (status === 'running') {
    return (
      <span title="진행 중" style={{ ...base, position: 'relative', background: '#22c55e' }}>
        <span
          style={{
            position: 'absolute',
            inset: -4,
            borderRadius: '50%',
            border: '2px solid rgba(59,130,246,0.45)',
            animation: 'agent-pulse 1.2s ease-out infinite',
          }}
        />
        <style>{`
          @keyframes agent-pulse {
            0% { transform: scale(0.9); opacity: .9; }
            70% { transform: scale(1.15); opacity: .2; }
            100% { transform: scale(0.9); opacity: .0; }
          }
        `}</style>
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span
        title="실패"
        style={{
          ...base,
          background: '#ef4444',
          boxShadow: '0 0 0 3px rgba(239,68,68,0.18) inset',
        }}
      />
    )
  }
  return (
    <span
      title="대기"
      style={{
        ...base,
        background: '#cbd5e1',
        boxShadow: '0 0 0 2px rgba(148,163,184,0.25) inset',
      }}
    />
  )
}
