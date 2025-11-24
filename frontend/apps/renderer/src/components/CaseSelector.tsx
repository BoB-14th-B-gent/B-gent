import { useEffect, useState } from 'react'
import { useUIStore } from '@/store/ui'
import { listCases, createCase, type CaseDetail, type CaseCreateReq } from '@/utils/api'

type TabKind = 'new' | 'open'

export default function CaseSelectModal() {
  const { caseModalOpen, closeCaseModal, setSelectedCase } = useUIStore()

  const [activeTab, setActiveTab] = useState<TabKind>('new')
  const [cases, setCases] = useState<CaseDetail[]>([])
  const [casesLoading, setCasesLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [form, setForm] = useState<CaseCreateReq>({
    name: '',
    description: '',
    analyst: '',
  })

  useEffect(() => {
    if (!caseModalOpen || activeTab !== 'open') return
    ;(async () => {
      try {
        setCasesLoading(true)
        const items = await listCases()
        setCases(items)
      } catch (e) {
        console.error(e)
        setError('Case 목록을 불러오지 못했습니다.')
      } finally {
        setCasesLoading(false)
      }
    })()
  }, [caseModalOpen, activeTab])

  if (!caseModalOpen) return null

  const overlayStyle: React.CSSProperties = {
    position: 'fixed',
    inset: 0,
    background: 'rgba(15,23,42,0.30)',
    backdropFilter: 'blur(6px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 100,
  }

  const modalStyle: React.CSSProperties = {
    width: 760,
    maxWidth: '90vw',
    height: 420,
    maxHeight: '90vh',
    borderRadius: 20,
    overflow: 'hidden',
    display: 'grid',
    gridTemplateColumns: '1fr 1.2fr',
    background: '#f8fafc',
    boxShadow: '0 20px 60px rgba(15,23,42,0.35)',
    fontFamily:
      "Pretendard, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif",
  }

  const leftStyle: React.CSSProperties = {
    background: `
          radial-gradient(circle at 30% 40%, rgba(255, 255, 255, 0.5), rgba(255,255,255,0) 45%),
          linear-gradient(115deg, #d5e4f7 0%, #bfd3f0 40%, #a8c2e6 75%, #96b3dd 100%)
        `,
    color: 'black',
    padding: 28,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
  }

  const rightStyle: React.CSSProperties = {
    background: '#ffffff',
    padding: 24,
    display: 'flex',
    flexDirection: 'column',
  }

  const handleCreate = async () => {
    if (!form.name.trim() || submitting) return
    try {
      setSubmitting(true)
      setError(null)
      const res = await createCase({
        name: form.name.trim(),
        description: form.description?.trim() || null,
        analyst: form.analyst?.trim() || null,
      })
      setSelectedCase(res._id, form.name.trim())
      closeCaseModal()
    } catch (e) {
      console.error(e)
      setError('Case 생성에 실패했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSelectCase = (c: CaseDetail) => {
    setSelectedCase(c._id, c.name)
    closeCaseModal()
  }

  const handleQuitApp = () => {
    if (window.api?.quitApp) {
      window.api.quitApp()
    } else {
      closeCaseModal()
    }
  }

  return (
    <div style={overlayStyle}>
      <section style={modalStyle}>
        <div style={leftStyle}>
          <div>
            <div style={{ fontSize: 14, opacity: 0.85 }}>Digital Forensic AI Assistant</div>
            <div
              style={{
                fontSize: 32,
                fontWeight: 800,
                marginTop: 8,
                letterSpacing: 1,
              }}
            >
              B-GENT
            </div>
            <div style={{ marginTop: 18, fontSize: 13, opacity: 0.9, lineHeight: 1.5 }}>
              새로운 사건을 시작하거나
              <br />
              기존 사건을 이어서 분석하세요.
            </div>
          </div>
        </div>

        <div style={rightStyle}>
          <header style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
            <div
              style={{
                display: 'inline-flex',
                background: '#e5e7eb',
                borderRadius: 999,
                padding: 4,
                gap: 4,
              }}
            >
              <button
                type="button"
                onClick={() => setActiveTab('new')}
                style={{
                  border: 'none',
                  borderRadius: 999,
                  padding: '6px 14px',
                  fontSize: 13,
                  background: activeTab === 'new' ? '#0f172a' : 'transparent',
                  color: activeTab === 'new' ? '#fff' : '#4b5563',
                  cursor: 'pointer',
                }}
              >
                New Case
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('open')}
                style={{
                  border: 'none',
                  borderRadius: 999,
                  padding: '6px 14px',
                  fontSize: 13,
                  background: activeTab === 'open' ? '#0f172a' : 'transparent',
                  color: activeTab === 'open' ? '#fff' : '#4b5563',
                  cursor: 'pointer',
                }}
              >
                Open Case
              </button>
            </div>

            <button
              type="button"
              onClick={closeCaseModal}
              style={{
                marginLeft: 'auto',
                border: 'none',
                borderRadius: 999,
                width: 28,
                height: 28,
                fontSize: 16,
                lineHeight: '16px',
                cursor: 'pointer',
                background: '#e5e7eb',
              }}
            >
              ×
            </button>
          </header>

          {error && (
            <div
              style={{
                marginBottom: 10,
                padding: '6px 8px',
                borderRadius: 6,
                background: '#fef2f2',
                color: '#b91c1c',
                fontSize: 12,
              }}
            >
              {error}
            </div>
          )}

          {activeTab === 'new' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <label style={{ fontSize: 14, color: '#4b5563' }}>
                Case Name
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  style={inputStyle}
                  placeholder="예: Incident Analysis 2025-12-20-001"
                />
              </label>

              <label style={{ fontSize: 14, color: '#4b5563' }}>
                Description
                <textarea
                  value={form.description ?? ''}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  style={{ ...inputStyle, minHeight: 70, resize: 'vertical' }}
                  placeholder="사건 개요나 주요 이슈를 간단히 적어주세요."
                />
              </label>

              <label style={{ fontSize: 14, color: '#4b5563' }}>
                Analyst
                <input
                  type="text"
                  value={form.analyst ?? ''}
                  onChange={e => setForm(f => ({ ...f, analyst: e.target.value }))}
                  style={inputStyle}
                  placeholder="담당 분석자 이름 (선택)"
                />
              </label>

              <div
                style={{ marginTop: 35, display: 'flex', justifyContent: 'flex-end', gap: 8 }}
              >
                <button type="button" onClick={closeCaseModal} style={secondaryBtn}>
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={!form.name.trim() || submitting}
                  style={{
                    ...primaryBtn,
                    opacity: !form.name.trim() || submitting ? 0.6 : 1,
                    cursor: !form.name.trim() || submitting ? 'default' : 'pointer',
                  }}
                >
                  {submitting ? '생성 중…' : 'OK'}
                </button>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              <div style={{ fontSize: 14, color: '#4b5563', marginBottom: 8 }}>
                Case List
              </div>

              <div
                style={{
                  border: '1px solid #e5e7eb',
                  borderRadius: 10,
                  padding: 4,
                  height: 245,
                  overflowY: 'auto',
                  background: '#f9fafb',
                }}
              >
                {casesLoading && <div style={{ fontSize: 13 }}>불러오는 중…</div>}
                {!casesLoading && cases.length === 0 && (
                  <div style={{ fontSize: 13, color: '#9ca3af', padding: 10 }}>
                    등록된 Case가 없습니다. New Case를 먼저 생성해주세요.
                  </div>
                )}

                {!casesLoading &&
                  cases.map(c => (
                    <button
                      key={c._id}
                      type="button"
                      onClick={() => handleSelectCase(c)}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        padding: '8px 10px',
                        borderRadius: 8,
                        border: 'none',
                        background: '#ffffff',
                        marginBottom: 6,
                        cursor: 'pointer',
                        fontSize: 13,
                      }}
                    >
                      <div style={{ fontWeight: 600, color: '#0f172a' }}>{c.name}</div>
                      {c.description && (
                        <div
                          style={{
                            fontSize: 11,
                            color: '#6b7280',
                            marginTop: 2,
                          }}
                        >
                          {c.description}
                        </div>
                      )}
                    </button>
                  ))}
              </div>

              <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
                <button type="button" onClick={handleQuitApp} style={secondaryBtn}>
                  닫기
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  marginTop: 4,
  padding: '7px 9px',
  fontSize: 13,
  borderRadius: 8,
  border: '1px solid #d1d5db',
  outline: 'none',
}

const primaryBtn: React.CSSProperties = {
  borderRadius: 999,
  border: 'none',
  padding: '6px 14px',
  fontSize: 13,
  background: '#034078',
  color: '#fff',
}

const secondaryBtn: React.CSSProperties = {
  borderRadius: 999,
  border: '1px solid #d1d5db',
  padding: '6px 12px',
  fontSize: 13,
  background: '#fff',
  color: '#4b5563',
}
