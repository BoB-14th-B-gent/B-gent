export const graphEvents = new EventTarget()

export const GraphEvt = {
  AddInitial: 'graph:add-initial',
  MCPStart: 'graph:mcp-start',
  MCPDone: 'graph:mcp-done',
  AgentDone: 'graph:agent-done',
} as const

export type MCPServer = 'velociraptor' | 'elastic' | 'sleuthkit' | 'ghidra'
