import type { NodeProps } from 'reactflow'
import { Handle, Position } from 'reactflow'

export type PromptData = {
  label: string
  bg?: string
  leftDot?: string
  rightDot?: string
  icon?: string
  onClick?: () => void
}

export default function PromptNode({ data }: NodeProps<PromptData>) {
  const bg = data.bg ?? '#334155'

  return (
    <div className="flex flex-col items-center">
      <button
        onClick={data.onClick}
        className="relative flex h-30 w-30 items-center justify-center rounded-full shadow-lg ring-1 ring-black/5"
        style={{
          background: bg,
          boxShadow: '0 6px 14px rgba(0,0,0,0.18), inset 0 0 0 1px rgba(255,255,255,0.06)',
        }}
      >
        {data.icon ? (
          <img
            src={data.icon}
            alt={data.label}
            className="h-18 w-18 select-none"
            draggable={false}
          />
        ) : (
          <span className="text-2xl">🔘</span>
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

      <div className="font-pretendard mt-2 text-base font-semibold text-slate-700 select-none">
        {data.label}
      </div>
    </div>
  )
}
