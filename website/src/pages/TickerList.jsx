import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

function SentimentTable({ tickers }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Articles</th>
          <th>Positive</th>
          <th>Negative</th>
          <th>Neutral</th>
        </tr>
      </thead>
      <tbody>
        {tickers.map((t) => (
          <tr key={t.ticker}>
            <td className="ticker">
              <Link to={`/ticker/${t.ticker}`}>{t.ticker}</Link>
            </td>
            <td>{t.article_count}</td>
            <td>{(t.positive * 100).toFixed(1)}%</td>
            <td>{(t.negative * 100).toFixed(1)}%</td>
            <td>{(t.neutral * 100).toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TickerList() {
  const [sentiments, setSentiments] = useState(null)
  const [trackedTickers, setTrackedTickers] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/sentiments').then((res) => res.json()),
      fetch('/api/tickers').then((res) => res.json()),
    ])
      .then(([sentimentsData, trackedData]) => {
        setSentiments(sentimentsData)
        setTrackedTickers(trackedData)
      })
      .catch((err) => setError(err.message))
  }, [])

  if (error) return <p className="status">Failed to load: {error}</p>
  if (!sentiments || !trackedTickers) return <p className="status">Loading tickers...</p>

  const tickers = Object.values(sentiments).sort((a, b) => b.positive - a.positive)
  const trackedSet = new Set(trackedTickers)
  const tracked = tickers.filter((t) => trackedSet.has(t.ticker))
  const others = tickers.filter((t) => !trackedSet.has(t.ticker))

  return (
    <main className="ticker-list">
      <h1>Stock Sentiment</h1>
      <h2>Tracked Assets</h2>
      <SentimentTable tickers={tracked} />
      <h2>Other Tickers</h2>
      <SentimentTable tickers={others} />
    </main>
  )
}

export default TickerList
