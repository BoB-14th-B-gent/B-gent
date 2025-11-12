import { createSllmReport, getReport, patchTriggerReport, postMessage } from './api'

export interface RunReportArgs {
  triggerId: string
  conversationId: string
  stageId?: number
}

export async function runReportPipeline({
  triggerId,
  conversationId,
  stageId = 0,
}: RunReportArgs): Promise<{ reportId: string; reportText: string }> {
  const { ok, report_id } = await createSllmReport(triggerId)
  if (!ok || !report_id) {
    throw new Error('sLLM 보고서 생성 실패: ok=false 또는 report_id 없음')
  }

  const rep = await getReport(report_id)
  const reportText = rep.report ?? ''
  if (!reportText) {
    console.warn('[runReportPipeline] 빈 보고서 텍스트')
  }

  await patchTriggerReport(triggerId, report_id)

  if (reportText) {
    await postMessage(conversationId, reportText, 'B-GENT', stageId)
  }

  return { reportId: report_id, reportText }
}
