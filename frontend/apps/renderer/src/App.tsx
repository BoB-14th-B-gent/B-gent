import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow'
import 'reactflow/dist/style.css'
import './index.css'

const nodes: Node[] = [
  { id: 'n1', position: { x: 200, y: 120 }, data: { label: 'Hello Node' } },
]
const edges: Edge[] = []

export default function App() {
  return (
    <div className="w-screen h-screen bg-neutral-900 text-white">
      <div className="p-3">Renderer OK</div>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  )
}