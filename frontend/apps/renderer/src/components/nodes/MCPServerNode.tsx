import type { NodeProps } from 'reactflow'
import { Handle, Position } from 'reactflow'

export type MCPServerData = {
  label: string
  bg?: string
  leftDot?: string
  rightDot?: string
  icon?: string
  onClick?: () => void
  isActive?: boolean
}

export default function MCPServerNode({ data }: NodeProps<MCPServerData>) {
  const isActive = !!data.isActive
  const bg = isActive ? '#FFFFFF' : (data.bg ?? '#334155')

  return (
    <div className="flex flex-col items-center select-none">
      <button
        type="button"
        aria-pressed={isActive}
        onClick={e => {
          e.stopPropagation()
          data.onClick?.()
        }}
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
            className="h-13 w-13 select-none"
            draggable={false}
          />
        ) : (
          <img
            src="icons/logo.svg"
            alt="mcp"
            className="h-13 w-13 select-none"
            draggable={false}
          />
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
