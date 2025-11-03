import type { NodeProps } from 'reactflow';
import { Handle, Position } from 'reactflow';

export type MCPReportData = {
  label: string;
  iconUrl?: string;
  bg?: string;
  onClick?: () => void;
};

export default function MCPReportNode({ data }: NodeProps<MCPReportData>) {
  const bg = data.bg ?? '#C8E5FF';

  return (
    <div className="flex flex-col items-center">
      <button
        onClick={data.onClick}
        className="relative flex items-center justify-center h-20 w-20 rounded-full shadow-lg ring-1 ring-black/5"
        style={{
          background: bg,
          boxShadow: '0 6px 14px rgba(0,0,0,0.18), inset 0 0 0 1px rgba(255,255,255,0.06)',
        }}
      >
        {data.iconUrl ? (
          <img
            src={data.iconUrl}
            alt={data.label}
            className="h-10 w-10 select-none"
            draggable={false}
          />
        ) : (
          <span className="text-2xl">📄</span>
        )}

        <Handle id="l" type="target" position={Position.Left}  style={{ opacity: 0, width: 0, height: 0, border: 0 }} isConnectable={false}/>
        <Handle id="r" type="source" position={Position.Right} style={{ opacity: 0, width: 0, height: 0, border: 0 }} isConnectable={false}/>
      </button>

      <div className="mt-2 text-xs font-medium text-slate-700 select-none">
        {data.label}
      </div>
    </div>
  );
}