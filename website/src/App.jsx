import { Routes, Route } from 'react-router-dom'
import TickerList from './pages/TickerList.jsx'
import TickerArticles from './pages/TickerArticles.jsx'
import Sidebar from './components/Sidebar.jsx'
import './App.css'

function App() {
  return (
    <div className="app-layout">
      <div className="app-content">
        <Routes>
          <Route path="/" element={<TickerList />} />
          <Route path="/ticker/:ticker" element={<TickerArticles />} />
        </Routes>
      </div>
      <Sidebar />
    </div>
  )
}

export default App
