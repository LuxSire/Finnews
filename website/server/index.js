import express from "express";
import cors from "cors";
import { extractAllArticles, getArticlesByTicker, getTrackedTickers } from "./extractArticles.js";
import { getSentimentAverages } from "./getSentiments.js";

const app = express();
app.use(cors());

app.get("/api/articles", (req, res) => {
  res.json(extractAllArticles());
});

app.get("/api/articles/:ticker", (req, res) => {
  extractAllArticles();
  res.json(getArticlesByTicker(req.params.ticker));
});

app.get("/api/sentiments", (req, res) => {
  res.json(getSentimentAverages());
});

app.get("/api/tickers", (req, res) => {
  res.json(getTrackedTickers());
});

const PORT = 5175;
app.listen(PORT, () => {
  console.log(`API server listening on http://localhost:${PORT}`);
});
