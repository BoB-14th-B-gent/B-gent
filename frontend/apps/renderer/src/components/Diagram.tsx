import { useMemo } from 'react';
import ReactFlow, {
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
} from 'reactflow';
import 'reactflow/dist/style.css';

import PromptNode,     { type PromptData }     from './nodes/PromptNode';
import AgentNode,      { type AgentData }      from './nodes/AgentNode';
import MCPServerNode,  { type MCPServerData }  from './nodes/MCPServerNode';
import MCPReportNode,  { type MCPReportData }  from './nodes/MCPReportNode';
import TotalReportNode,{ type TotalData }      from './nodes/TotalReportNode';
import DottedEdge from './edges/DottedEdge';
import { useUIStore } from '@/store/ui';

const COLORS = {
  prompt:       '#90949B',
  bgent:        '#AFC0CF',
  velociraptor: '#003D00',
  elastic:      '#054861',
  tsk:          '#F5D356',
  report:       '#7FA9CE',
  total:        '#90949B',
} as const;

const nodeTypes: NodeTypes = {
  prompt: PromptNode,
  agent:  AgentNode,
  mcp:    MCPServerNode,
  doc:    MCPReportNode,
  total:  TotalReportNode,
};

const edgeTypes: EdgeTypes = {
  dotted: DottedEdge,
};

type ND = PromptData | AgentData | MCPServerData | MCPReportData | TotalData;

const NODES: Node<ND>[] = [
  {
    id: 'prompt',
    type: 'prompt',
    position: { x: 100, y: 340 },
    data: {
      label: 'User Prompt',
      bg: '#555C62',
      leftDot: COLORS.prompt,
      rightDot: '#2d5bff',
      iconUrl: '/icons/prompt.svg',
    },
  },
  {
    id: 'bgent',
    type: 'agent',
    position: { x: 320, y: 340 },
    data: {
      label: 'B-gent',
      bg: '#506D99',
      leftDot: '#2d5bff',
      rightDot: '#2d5bff',
      iconUrl: '/icons/bgent.svg',
    },
  },
  {
    id: 'velociraptor',
    type: 'mcp',
    position: { x: 550, y: 200 },
    data: {
      label: 'Velociraptor',
      bg: '#003D00',
      leftDot: '#1f8a5b',
      rightDot: COLORS.report,
      iconUrl: '/icons/velociraptor.svg',
    },
  },
  {
    id: 'elastic',
    type: 'mcp',
    position: { x: 550, y: 350 },
    data: {
      label: 'Elasticsearch',
      bg: '#002A3A',
      leftDot: '#0d7d6f',
      rightDot: COLORS.report,
      iconUrl: '/icons/elastic.svg',
    },
  },
  {
    id: 'tsk',
    type: 'mcp',
    position: { x: 550, y: 500 },
    data: {
      label: 'The Sleuth Kit',
      bg: '#F5D356',
      leftDot: '#e7a90e',
      rightDot: COLORS.report,
      iconUrl: '/icons/tsk.svg',
    },
  },
  {
    id: 'velo-report',
    type: 'doc',
    position: { x: 750, y: 209 },
    data: {
      label: 'Report',
      bg: '#C8E5FF',
      iconUrl: '/icons/report.svg',
    },
  },
  {
    id: 'elastic-report',
    type: 'doc',
    position: { x: 750, y: 359 },
    data: {
      label: 'Report',
      bg: '#C8E5FF',
      iconUrl: '/icons/report.svg',
    },
  },
  {
    id: 'tsk-report',
    type: 'doc',
    position: { x: 750, y: 509 },
    data: {
      label: 'Report',
      bg: '#C8E5FF',
      iconUrl: '/icons/report.svg',
    },
  },
  {
    id: 'total-report',
    type: 'total',
    position: { x: 980, y: 330 },
    data: {
      label: 'Total Report',
      bg: '#F3F6FB',
      iconUrl: '/icons/total.svg',
    },
  },
];

const EDGES: Edge[] = [
  {
    id: 'e-prompt-bgent',
    source: 'prompt',
    target: 'bgent',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.prompt, to: COLORS.bgent },
  },

  {
    id: 'e-bgent-velociraptor',
    source: 'bgent',
    target: 'velociraptor',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.bgent, to: COLORS.velociraptor },
  },
  {
    id: 'e-bgent-elastic',
    source: 'bgent',
    target: 'elastic',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.bgent, to: COLORS.elastic },
  },
  {
    id: 'e-bgent-tsk',
    source: 'bgent',
    target: 'tsk',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.bgent, to: COLORS.tsk },
  },

  {
    id: 'e-velociraptor-report',
    source: 'velociraptor',
    target: 'velo-report',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.velociraptor, to: COLORS.report },
  },
  {
    id: 'e-elastic-report',
    source: 'elastic',
    target: 'elastic-report',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.elastic, to: COLORS.report },
  },
  {
    id: 'e-tsk-report',
    source: 'tsk',
    target: 'tsk-report',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.tsk, to: COLORS.report },
  },

  {
    id: 'e-r-total-1',
    source: 'velo-report',
    target: 'total-report',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.report, to: COLORS.total },
  },
  {
    id: 'e-r-total-2',
    source: 'elastic-report',
    target: 'total-report',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.report, to: COLORS.total },
  },
  {
    id: 'e-r-total-3',
    source: 'tsk-report',
    target: 'total-report',
    sourceHandle: 'r',
    targetHandle: 'l',
    type: 'dotted',
    data: { from: COLORS.report, to: COLORS.total },
  },
];

export default function Diagram() {
  const openPanel = useUIStore((s) => s.openPanel);
  const setSelectedNode = useUIStore((s) => s.setSelectedNode);

  const nodes = useMemo(
    () =>
      NODES.map((n) => ({
        ...n,
        data: {
          ...(n.data as ND),
          onClick: () => {
            setSelectedNode(n.id);
            openPanel();
          },
        },
      })),
    [openPanel, setSelectedNode]
  );

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        background: `
          radial-gradient(circle at 30% 40%, rgba(255, 255, 255, 0.5), rgba(255,255,255,0) 45%),
          linear-gradient(115deg, #d5e4f7 0%, #bfd3f0 40%, #a8c2e6 75%, #96b3dd 100%)
        `,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        overflow: 'hidden',
        padding: 32,
      }}
    >
      <div style={{ width: '100%', height: '100%' }}>
        <ReactFlow
          nodes={nodes}
          edges={EDGES}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          nodesConnectable={false}
          connectOnClick={false}
          elementsSelectable={false}
          nodesDraggable={false}
          panOnDrag
          zoomOnScroll
          onNodeClick={(_, node) => {
            setSelectedNode(node.id);
            openPanel();
          }}
        >
        </ReactFlow>
      </div>
    </div>
  );
}