import type { NodeProps } from 'reactflow'
import { Handle, Position } from 'reactflow'

export type MCPReportData = {
  label: string
  icon?: string
  bg?: string
  onClick?: () => void
  isActive?: boolean
}

export default function MCPReportNode({ data }: NodeProps<MCPReportData>) {
  const isActive = !!data.isActive
  const bg = isActive ? '#FFFFFF' : (data.bg ?? '#C8E5FF')

  return (
    <div className="flex flex-col items-center select-none">
      <button
        type="button"
        aria-pressed={isActive}
        onClick={data.onClick}
        onMouseDown={e => e.stopPropagation()}
        className="relative flex h-24 w-24 items-center justify-center rounded-full transition-all duration-200 hover:cursor-pointer"
        style={{
          background: bg,
          boxShadow: isActive
            ? `0 0 0 5px ${data.bg}, 0 8px 24px rgba(0,0,0,.20)`
            : '0 6px 14px rgba(0,0,0,0.18), inset 0 0 0 1px rgba(255,255,255,0.06)',
        }}
      >
        {data.icon ? (
          <img
            src={data.icon}
            alt={data.label}
            className="h-12 w-12 select-none"
            draggable={false}
          />
        ) : (
          <span className="text-2xl">📄</span>
        )}

        <Handle
          id="l"
          type="target"
          position={Position.Left}
          style={{ opacity: 0, width: 0, height: 0, border: 0 }}
          isConnectable={false}
        />
        <Handle
          id="r"
          type="source"
          position={Position.Right}
          style={{ opacity: 0, width: 0, height: 0, border: 0 }}
          isConnectable={false}
        />
      </button>

      <div className="font-pretendard mt-2 text-sm font-semibold text-slate-700 select-none">
        {data.label}
      </div>
    </div>
  )
}
