import PromptNode from './PromptNode'
import AgentNode from './AgentNode'
import MCPServerNode from './MCPServerNode'
import MCPReportNode from './MCPReportNode'
import TotalReportNode from './TotalReportNode'

export const nodeTypes = {
  prompt: PromptNode,
  agent: AgentNode,
  mcp: MCPServerNode,
  doc: MCPReportNode,
  total: TotalReportNode,
} as const

export type NodeTypeKey = keyof typeof nodeTypes
