import { extractAllArticles } from "./extractArticles.js";

export function getSentimentAverages() {
  const articles = extractAllArticles();

  const byTicker = new Map();
  for (const article of articles) {
    if (!article.sentiment) continue;
    if (!byTicker.has(article.ticker)) byTicker.set(article.ticker, []);
    byTicker.get(article.ticker).push(article.sentiment);
  }

  const averages = {};
  for (const [ticker, sentiments] of byTicker) {
    const count = sentiments.length;
    averages[ticker] = {
      ticker,
      article_count: count,
      positive: sentiments.reduce((sum, s) => sum + s.positive, 0) / count,
      negative: sentiments.reduce((sum, s) => sum + s.negative, 0) / count,
      neutral: sentiments.reduce((sum, s) => sum + s.neutral, 0) / count,
    };
  }

  return averages;
}
