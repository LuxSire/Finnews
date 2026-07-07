import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

function TickerArticles() {
  const { ticker } = useParams()
  const [articles, setArticles] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setArticles(null)
    fetch(`/api/articles/${ticker}`)
      .then((res) => res.json())
      .then(setArticles)
      .catch((err) => setError(err.message))
  }, [ticker])

  if (error) return <p className="status">Failed to load: {error}</p>
  if (!articles) return <p className="status">Loading articles...</p>

  const scored = articles.filter((a) => a.sentiment)
  const average = (key) =>
    scored.length ? scored.reduce((sum, a) => sum + a.sentiment[key], 0) / scored.length : null
  const formatAverage = (key) => {
    const value = average(key)
    return value === null ? '—' : `${(value * 100).toFixed(1)}%`
  }

  return (
    <main className="ticker-articles">
      <Link to="/" className="back-link">&larr; All tickers</Link>
      <h1>{ticker} Articles</h1>
      {articles.length === 0 && <p className="status">No articles found.</p>}
      {articles.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Article</th>
              <th>Source</th>
              <th>Published</th>
              <th>Positive</th>
              <th>Negative</th>
              <th>Neutral</th>
            </tr>
          </thead>
          <tbody>
            <tr className="average-row">
              <td colSpan={3}>Average</td>
              <td className="sentiment positive">{formatAverage('positive')}</td>
              <td className="sentiment negative">{formatAverage('negative')}</td>
              <td className="sentiment neutral">{formatAverage('neutral')}</td>
            </tr>
            {articles.map((a, i) => (
              <tr key={i}>
                <td>
                  {a.url ? (
                    <a href={a.url} target="_blank" rel="noreferrer">
                      {a.title}
                    </a>
                  ) : (
                    a.title
                  )}
                </td>
                <td>{a.source}</td>
                <td>{a.published}</td>
                <td className="sentiment positive">
                  {a.sentiment ? `${(a.sentiment.positive * 100).toFixed(1)}%` : '—'}
                </td>
                <td className="sentiment negative">
                  {a.sentiment ? `${(a.sentiment.negative * 100).toFixed(1)}%` : '—'}
                </td>
                <td className="sentiment neutral">
                  {a.sentiment ? `${(a.sentiment.neutral * 100).toFixed(1)}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}

export default TickerArticles
