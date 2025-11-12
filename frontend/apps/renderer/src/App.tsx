import Diagram from './components/Diagram'

export default function App() {
  return (
    <div className="h-screen w-screen overflow-hidden bg-gradient-to-br from-sky-50 via-blue-50 to-indigo-50">
      <div className="flex h-full">
        <main>
          <Diagram />
        </main>
      </div>
    </div>
  )
}
