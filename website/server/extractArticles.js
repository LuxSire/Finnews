import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");

function readJson(filename) {
  const filePath = path.join(PROJECT_ROOT, filename);
  try {
    return JSON.parse(readFileSync(filePath, "utf-8"));
  } catch {
    return {};
  }
}

function flattenSource(data, source) {
  const articles = [];
  for (const [ticker, tickerData] of Object.entries(data)) {
    for (const article of tickerData.articles ?? []) {
      articles.push({
        ticker,
        source,
        title: article.title ?? "",
        url: article.url ?? "",
        published: article.published ?? "",
        sentiment: article.sentiment ?? null,
      });
    }
  }
  return articles;
}

let articles = [];

export function extractAllArticles() {
  const sentiment = readJson("sentiment.json");
  const seekingalpha = readJson("seekingalpha.json");
  const ibnews = readJson("ibnews.json");

  articles = [
    ...flattenSource(sentiment, "google_news"),
    ...flattenSource(seekingalpha, "seekingalpha"),
    ...flattenSource(ibnews, "ibnews"),
  ];

  return articles;
}

export function getArticlesByTicker(ticker) {
  return articles.filter((a) => a.ticker === ticker);
}

export function getTrackedTickers() {
  return Object.keys(readJson("assets.json"));
}
