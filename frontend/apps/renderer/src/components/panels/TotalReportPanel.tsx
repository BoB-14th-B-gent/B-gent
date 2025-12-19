import { useEffect } from 'react'
import { useUIStore } from '@/store/ui'

export default function TotalReportPanel() {
  const { totalreportOpen, activeTotalReportId, activeTotalReportStageId, closeTotalReport } =
    useUIStore()

  useEffect(() => {
    if (!totalreportOpen) return

    window.api?.openReportWindow?.({
      reportId: String(activeTotalReportId ?? ''),
      stageId: activeTotalReportStageId ?? undefined,
    })

    closeTotalReport()
  }, [totalreportOpen, activeTotalReportId, activeTotalReportStageId, closeTotalReport])

  return null
}
