// apps/renderer/src/utils/agentWs.ts
export type AgentLogHandler = (message: string) => void
export type AgentCloseHandler = () => void
export type AgentErrorHandler = (event: Event) => void

interface AgentWsOptions {
  triggerId: string
  onLog: AgentLogHandler
  onClose?: AgentCloseHandler
  onError?: AgentErrorHandler
}

export function connectAgentWebSocket({
  triggerId,
  onLog,
  onClose,
  onError,
}: AgentWsOptions): WebSocket | null {
  const baseUrl = import.meta.env.VITE_AGENT_WS_URL as string | undefined

  if (!baseUrl) {
    console.error("[AgentWS] VITE_AGENT_WS_URL is not set")
    return null
  }

  const url = `${baseUrl}/agent/ws/${triggerId}`
  console.log("[AgentWS] connecting to", url)

  const ws = new WebSocket(url)

  ws.onopen = () => {
    console.log("[AgentWS] connected")
  }

  ws.onmessage = (event) => {
    const text = typeof event.data === "string" ? event.data : ""
    if (text) {
      onLog(text)
    }
  }

  ws.onerror = (event) => {
    console.error("[AgentWS] error", event)
    onError?.(event)
  }

  ws.onclose = () => {
    console.log("[AgentWS] closed")
    onClose?.()
  }

  return ws
}