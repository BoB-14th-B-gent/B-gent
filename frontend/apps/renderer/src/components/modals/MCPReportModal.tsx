import { useEffect } from 'react'
import { useUIStore } from '@/store/ui'
import MCPReportPanel from '@/components/panels/MCPReportPanel'

export default function MCPReportModal() {
  const open = useUIStore(s => s.mcpreportOpen)
  const close = useUIStore(s => s.closeMCPReport)

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, close])

  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'grid',
        placeItems: 'center',
        padding: 18,
      }}
    >
      <div
        onClick={close}
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(15, 23, 42, 0.35)',
          backdropFilter: 'blur(2px)',
        }}
      />

      <div
        onClick={e => e.stopPropagation()}
        style={{
          position: 'relative',
          width: 'min(1120px, calc(100vw - 36px))',
          height: 'min(760px, calc(100vh - 36px))',
          borderRadius: 16,
          overflow: 'hidden',
          boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
        }}
      >
        <MCPReportPanel />
      </div>
    </div>
  )
}
