import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import ReportWindow from '@/pages/ReportWindow'

const route = window.location.hash
const Page = route.startsWith('#/report-window') ? ReportWindow : App

ReactDOM.createRoot(document.getElementById('root')!).render(<Page />)
