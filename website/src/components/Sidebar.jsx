import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

const SOURCE_LABELS = {
  google_news: 'Google News',
  seekingalpha: 'Seeking Alpha',
  ibnews: 'IB Gateway',
}

const ARTICLES_PER_SOURCE = 5

function Sidebar() {
  const [articles, setArticles] = useState(null)

  useEffect(() => {
    fetch('/api/articles')
      .then((res) => res.json())
      .then(setArticles)
      .catch(() => setArticles([]))
  }, [])

  if (!articles) return null

  const bySource = {}
  for (const a of articles) {
    ;(bySource[a.source] ??= []).push(a)
  }

  return (
    <aside className="sidebar">
      <h2>Latest by Source</h2>
      {Object.entries(bySource).map(([source, items]) => (
        <div key={source} className="sidebar-group">
          <h3>
            {SOURCE_LABELS[source] ?? source}{' '}
            <span className="sidebar-count">({items.length})</span>
          </h3>
          <ul>
            {items
              .slice()
              .sort((a, b) => new Date(b.published) - new Date(a.published))
              .slice(0, ARTICLES_PER_SOURCE)
              .map((a, i) => (
                <li key={i}>
                  <Link to={`/ticker/${a.ticker}`}>{a.title}</Link>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </aside>
  )
}

export default Sidebar
