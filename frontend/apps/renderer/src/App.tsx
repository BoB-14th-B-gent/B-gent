import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow'
import 'reactflow/dist/style.css'
import './index.css'


const nodes: Node[] = [
  { id: 'n1', position: { x: 200, y: 120 }, data: { label: 'B-GENT' } },
]
const edges: Edge[] = []

export default function App() {
  return (
    <div className="w-screen h-screen bg-neutral-900 text-white">
      <header className="flex items-center gap-2">
        <img src="/logo.svg" alt="B-Gent" className="w-8 h-8" />
        <h1 className="text-xl font-bold">B-Gent</h1>
      </header>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  )
}