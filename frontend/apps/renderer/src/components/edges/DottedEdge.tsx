import { useState, useEffect } from 'react'
import { type EdgeProps, getStraightPath } from 'reactflow'

type EdgeData = {
  from?: string
  to?: string
  active?: boolean
}

export default function DottedEdge(props: EdgeProps<EdgeData>) {
  const { id, sourceX, sourceY, targetX, targetY, data } = props

  const [path] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  })
  const isActive = !!data?.active
  const [live, setLive] = useState(isActive);
  useEffect(() => {
    if (isActive) {
      setLive(true);
      return;
    }
    const t = setTimeout(() => setLive(false), 300);
    return () => clearTimeout(t);
  }, [isActive]);

  const gradId = `grad-${id}`
  const startId = `mstart-${id}`
  const endId = `mend-${id}`

  const from = data?.from ?? '#64748b'
  const to = data?.to ?? '#64748b'

  const strokeWidth = 12
  const dot = 1
  const gap = 23

  return (
    <g className={`edge-flow ${live ? 'is-active' : ''}`} style={{ pointerEvents: 'none' }}>
      <defs>
        <linearGradient
          id={gradId}
          x1={sourceX}
          y1={sourceY}
          x2={targetX}
          y2={targetY}
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor={from} stopOpacity={0.9} />
          <stop offset="20%" stopColor={from} stopOpacity={0.8} />
          <stop offset="80%" stopColor={to} stopOpacity={0.7} />
          <stop offset="100%" stopColor={to} stopOpacity={0.9} />
        </linearGradient>

        <marker id={startId} markerWidth="6" markerHeight="6" refX="3" refY="3">
          <circle cx="3" cy="3" r="1.0" fill={from} />
        </marker>
        <marker id={endId} markerWidth="6" markerHeight="6" refX="3" refY="3">
          <circle cx="3" cy="3" r="1.0" fill={to} />
        </marker>
      </defs>

      <path
        d={path}
        className={live ? 'edge--active' : 'edge'}
        stroke={`url(#${gradId})`}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={`${dot} ${gap}`}
        fill="none"
        markerStart={`url(#${startId})`}
        markerEnd={`url(#${endId})`}
        style={{
          pointerEvents: 'none',
          filter: 'drop-shadow(0 1px 0 rgba(0,0,0,.06))',
        }}
      />
    </g>
  )
}
