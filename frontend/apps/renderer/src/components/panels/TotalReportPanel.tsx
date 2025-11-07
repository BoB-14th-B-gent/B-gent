import { useEffect } from 'react'
import { useUIStore } from '@/store/ui'

export default function ReportPanel() {
  const { totalreportOpen, activeTotalReportId, closeTotalReport } = useUIStore()

  useEffect(() => {
    if (!totalreportOpen) return
    window.api?.openReportWindow?.({
      reportId: String(activeTotalReportId ?? ''),
    })
    closeTotalReport()
  }, [totalreportOpen, activeTotalReportId, closeTotalReport])

  return null
}