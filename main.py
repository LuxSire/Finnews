import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import requests
import feedparser
import trafilatura
from googlenewsdecoder import gnewsdecoder
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from ib_async import IB, Stock

logger = logging.getLogger("finnews")
logger.setLevel(logging.INFO)
logger.propagate = False
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
for _handler in (logging.FileHandler("main.log"), logging.StreamHandler()):
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)

MODEL_NAME = "ProsusAI/finbert"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()

LABELS = [model.config.id2label[i] for i in range(len(model.config.id2label))]

MAX_WORKERS = 16
DECODE_MAX_CONCURRENCY = 4
_decode_semaphore = threading.Semaphore(DECODE_MAX_CONCURRENCY)

with open("assets.json") as f:
    ticker_map = json.load(f)

def google_news_rss_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"

def build_query(company: str, aliases: list[str]) -> str:
    terms = [company] + aliases
    return " OR ".join(f'"{t}"' for t in terms)

def parse_feed(url: str):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    return feed.entries

def is_last_Xh(entry, hours: int = 72) -> bool:
    published = entry.get("published")
    if not published:
        return False
    dt = parsedate_to_datetime(published)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(hours=hours)

def resolve_article_url(url: str) -> str:
    if "news.google.com" not in url:
        return url
    with _decode_semaphore:
        result = gnewsdecoder(url)
    return result["decoded_url"] if result.get("status") else url

def extract_article_text(url: str) -> str:
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    text = trafilatura.extract(r.text, include_comments=False, include_tables=False)
    return text or ""

PRICE_ACTION_PATTERN = re.compile(
    r"\b(shares?|stocks?)\b[^.!?]{0,40}\b("
    r"ros[ei]|rising|"
    r"fe?ll|falls|falling|"
    r"gained?|gains|gaining|"
    r"dropp?ed|drops|dropping|"
    r"climb(?:ed|s|ing)?|"
    r"sl(?:id|ides|iding)|"
    r"surg(?:ed|es|ing)?|"
    r"plunge[ds]?|plunging|"
    r"jump(?:ed|s|ing)?|"
    r"tumbl(?:ed|es|ing)|"
    r"ralli(?:ed|es)|rallying|"
    r"soar(?:ed|s|ing)?|"
    r"slump(?:ed|s|ing)?|"
    r"trad(?:ed|es|ing)|"
    r"clos(?:ed|es|ing)|"
    r"open(?:ed|s|ing)?"
    r")\b"
    r"|\bstock price\b|\bshare price\b|\b52-week (?:high|low)\b|\ball-time high\b"
    r"|\bmarket cap(?:italization)?\b|\bintraday\b|\bpremarket\b|\bafter-hours trading\b",
    re.IGNORECASE,
)

def strip_price_action(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    filtered = [s for s in sentences if not PRICE_ACTION_PATTERN.search(s)]
    return " ".join(filtered).strip() if filtered else text

def score_finbert(text: str):
    if not text.strip():
        return None

    filtered_text = strip_price_action(text)
    inputs = tokenizer(filtered_text[:4000], return_tensors="pt", truncation=True, max_length=512, padding=True)
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=1).squeeze().tolist()

    return {
        "label": LABELS[int(torch.argmax(logits, dim=1))],
        "positive": probs[0],
        "negative": probs[1],
        "neutral": probs[2],
        "net_score": probs[0] - probs[1],
    }

def fetch_ticker_entries(meta: dict):
    query = build_query(meta["company"], meta["aliases"])
    rss_url = google_news_rss_url(query)
    logger.info("fetching RSS feed: %s", rss_url)
    entries = [e for e in parse_feed(rss_url) if is_last_Xh(e, hours=72)]
    logger.info("RSS feed returned %d entries in window: %s", len(entries), rss_url)
    return query, entries

def build_article(ticker: str, e: dict) -> dict:
    url = e.get("link", "")
    real_url = url
    start = time.monotonic()
    try:
        real_url = resolve_article_url(url)
        article_text = extract_article_text(real_url)
        logger.info(
            "[%s] fetched article in %.2fs (%d chars): %s",
            ticker, time.monotonic() - start, len(article_text), real_url,
        )
    except Exception as exc:
        logger.warning("[%s] failed to fetch article: %s (%s)", ticker, real_url, exc)
        article_text = ""

    full_text = " ".join([
        e.get("title", ""),
        e.get("summary", ""),
        article_text
    ]).strip()

    sentiment = score_finbert(full_text) if full_text else None

    return {
        "ticker": ticker,
        "title": e.get("title", ""),
        "url": url,
        "published": e.get("published", ""),
        "summary": e.get("summary", ""),
        "article_text": article_text,
        "sentiment": sentiment,
    }

def analyze_ticker(ticker: str, meta: dict) -> dict:
    query, entries = fetch_ticker_entries(meta)
    articles = [build_article(ticker, e) for e in entries]
    return finalize_ticker_result(ticker, query, articles)

def finalize_ticker_result(ticker: str, query: str, articles: list[dict]) -> dict:
    blob = "\n\n".join(
        " ".join([a["title"], a["summary"], a["article_text"]]).strip()
        for a in articles
        if a["title"] or a["summary"] or a["article_text"]
    )

    blob_sentiment = score_finbert(blob) if blob else None

    return {
        "ticker": ticker,
        "query": query,
        "article_count": len(articles),
        "blob": blob,
        "blob_sentiment": blob_sentiment,
        "articles": articles,
    }

def analyze_all_tickers(ticker_map: dict, max_workers: int = MAX_WORKERS) -> dict:
    queries = {}
    work_items = []
    for ticker, meta in ticker_map.items():
        logger.info("[%s] fetching RSS entries", ticker)
        try:
            query, entries = fetch_ticker_entries(meta)
        except Exception as exc:
            logger.warning("[%s] failed to fetch RSS feed: %s", ticker, exc)
            query, entries = build_query(meta["company"], meta["aliases"]), []
        queries[ticker] = query
        work_items.extend((ticker, e) for e in entries)

    logger.info("dispatching %d article fetches across %d tickers (%d workers)", len(work_items), len(ticker_map), max_workers)

    articles_by_ticker = {ticker: [] for ticker in ticker_map}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(build_article, ticker, e) for ticker, e in work_items]
        for future in as_completed(futures):
            article = future.result()
            articles_by_ticker[article["ticker"]].append(article)

    return {
        ticker: finalize_ticker_result(ticker, queries[ticker], articles_by_ticker[ticker])
        for ticker in ticker_map
    }

SEEKING_ALPHA_MARKET_NEWS_URL = "https://seekingalpha.com/market-news"
SEEKING_ALPHA_CACHE_PATH = "seekingalpha_articles.json"

def fetch_seekingalpha_market_news() -> list[dict]:
    logger.info("fetching Seeking Alpha market news: %s", SEEKING_ALPHA_MARKET_NEWS_URL)
    r = requests.get(SEEKING_ALPHA_MARKET_NEWS_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    match = re.search(r"window\.SSR_DATA\s*=\s*(\{.*?\});", r.text, re.DOTALL)
    if not match:
        return []

    response = json.loads(match.group(1)).get("marketNews", {}).get("response", {})
    tags = {t["id"]: t["attributes"] for t in response.get("included", []) if t.get("type") == "tag"}

    entries = []
    for item in response.get("data", []):
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        tag_ids = [
            t["id"]
            for key in ("primaryTickers", "secondaryTickers")
            for t in rels.get(key, {}).get("data", [])
        ]
        link = item.get("links", {}).get("self", "")

        entries.append({
            "id": item.get("id", ""),
            "title": attrs.get("title", ""),
            "published": attrs.get("publishOn", ""),
            "url": f"https://seekingalpha.com{link}" if link else "",
            "tickers": {tags[tid]["name"] for tid in tag_ids if tid in tags},
        })

    logger.info("Seeking Alpha market news: %d entries", len(entries))
    return entries

def load_json_cache(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def update_seekingalpha_cache(cache: dict, news_items: list[dict]) -> dict:
    for n in news_items:
        article_id = n["id"]
        if not article_id or article_id in cache:
            continue

        start = time.monotonic()
        try:
            article_text = extract_article_text(n["url"]) if n["url"] else ""
            logger.info(
                "[seekingalpha] fetched article in %.2fs (%d chars): %s",
                time.monotonic() - start, len(article_text), n["url"],
            )
        except Exception as exc:
            logger.warning("[seekingalpha] failed to fetch article: %s (%s)", n["url"], exc)
            article_text = ""

        full_text = " ".join([n["title"], article_text]).strip()
        sentiment = score_finbert(full_text) if full_text else None

        cache[article_id] = {
            "title": n["title"],
            "url": n["url"],
            "published": n["published"],
            "article_text": article_text,
            "sentiment": sentiment,
            "tickers": sorted(n["tickers"]),
        }

    return cache

def build_ticker_news_results(cache: dict, tickers: list[str]) -> dict:
    results = {}
    for ticker in tickers:
        matches = sorted(
            (a for a in cache.values() if ticker in a["tickers"]),
            key=lambda a: a["published"],
            reverse=True,
        )

        articles = [
            {
                "ticker": ticker,
                "title": a["title"],
                "url": a["url"],
                "published": a["published"],
                "summary": "",
                "article_text": a["article_text"],
                "sentiment": a["sentiment"],
            }
            for a in matches
        ]

        blob = "\n\n".join(
            " ".join([a["title"], a["article_text"]]).strip()
            for a in articles
            if a["title"] or a["article_text"]
        )

        blob_sentiment = score_finbert(blob) if blob else None

        results[ticker] = {
            "ticker": ticker,
            "article_count": len(articles),
            "blob": blob,
            "blob_sentiment": blob_sentiment,
            "articles": articles,
        }

    return results

IB_HOST = "127.0.0.1"
IB_PORT = 4001
IB_CLIENT_ID = 47
IB_NEWS_LOOKBACK_HOURS = 72
IB_NEWS_CACHE_PATH = "ibnews_articles.json"

def connect_ib(client_id: int = IB_CLIENT_ID) -> IB:
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=client_id, timeout=10)
    return ib

def clean_ib_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()

def fetch_ib_headlines(ib: IB, contract: Stock, provider_codes: str, hours: int = IB_NEWS_LOOKBACK_HOURS, total: int = 30):
    headlines = ib.reqHistoricalNews(contract.conId, provider_codes, "", "", total)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [
        h for h in headlines
        if (h.time if h.time.tzinfo else h.time.replace(tzinfo=timezone.utc)) >= cutoff
    ]

def fetch_ib_article_text(ib: IB, provider_code: str, article_id: str) -> str:
    article = ib.reqNewsArticle(provider_code, article_id)
    text = article.articleText or ""
    return clean_ib_html(text) if article.articleType == 1 else text

def update_ib_news_cache(ib: IB, cache: dict, ticker: str, provider_codes: str) -> dict:
    contract = Stock(ticker.replace(".", " "), "SMART", "USD")
    ib.qualifyContracts(contract)
    if not contract.conId:
        logger.warning("[%s] IB could not qualify contract", ticker)
        return cache

    try:
        headlines = fetch_ib_headlines(ib, contract, provider_codes)
    except Exception as exc:
        logger.warning("[%s] IB historical news request failed: %s", ticker, exc)
        return cache

    logger.info("[%s] IB historical news returned %d headlines in window", ticker, len(headlines))

    for h in headlines:
        article_id = f"{h.providerCode}:{h.articleId}"
        if article_id in cache:
            if ticker not in cache[article_id]["tickers"]:
                cache[article_id]["tickers"].append(ticker)
            continue

        start = time.monotonic()
        try:
            article_text = fetch_ib_article_text(ib, h.providerCode, h.articleId)
            logger.info(
                "[ibnews] fetched article in %.2fs (%d chars): %s",
                time.monotonic() - start, len(article_text), article_id,
            )
        except Exception as exc:
            logger.warning("[ibnews] failed to fetch article %s: %s", article_id, exc)
            article_text = ""

        title = re.sub(r"\{.*?\}", "", h.headline).strip()
        full_text = " ".join([title, article_text]).strip()
        sentiment = score_finbert(full_text) if full_text else None

        cache[article_id] = {
            "title": title,
            "url": "",
            "published": h.time.isoformat(),
            "article_text": article_text,
            "sentiment": sentiment,
            "tickers": [ticker],
        }

    return cache

def run_trading_agent(ticker: str, trade_date: str | None = None) -> dict:
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    trade_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    graph = TradingAgentsGraph(debug=False, config=DEFAULT_CONFIG.copy())
    _, decision = graph.propagate(ticker, trade_date)
    return decision

if __name__ == "__main__":
    logger.info("=== starting Google News pass: %d tickers ===", len(ticker_map))
    results = analyze_all_tickers(ticker_map)
    logger.info("Google News pass done: %d articles total", sum(v["article_count"] for v in results.values()))
    with open("sentiment.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("=== starting Seeking Alpha pass ===")
    try:
        sa_news_items = fetch_seekingalpha_market_news()
    except requests.exceptions.HTTPError as exc:
        logger.warning("Seeking Alpha market news fetch failed: %s", exc)
        sa_news_items = []

    sa_cache = update_seekingalpha_cache(load_json_cache(SEEKING_ALPHA_CACHE_PATH), sa_news_items)
    with open(SEEKING_ALPHA_CACHE_PATH, "w") as f:
        json.dump(sa_cache, f, indent=2)

    sa_tickers = sorted({t for a in sa_cache.values() for t in a["tickers"]})
    sa_results = build_ticker_news_results(sa_cache, sa_tickers)
    logger.info("Seeking Alpha pass done: %d tickers, %d cached articles", len(sa_tickers), len(sa_cache))
    with open("seekingalpha.json", "w") as f:
        json.dump(sa_results, f, indent=2)

    logger.info("=== starting IB Gateway news pass ===")
    try:
        ib = connect_ib()
    except Exception as exc:
        logger.warning("IB Gateway connection failed: %s", exc)
        ib = None

    if ib is not None:
        try:
            provider_codes = "+".join(p.code for p in ib.reqNewsProviders())
            ib_cache = load_json_cache(IB_NEWS_CACHE_PATH)
            for ticker in ticker_map:
                ib_cache = update_ib_news_cache(ib, ib_cache, ticker, provider_codes)
            with open(IB_NEWS_CACHE_PATH, "w") as f:
                json.dump(ib_cache, f, indent=2)

            ib_results = build_ticker_news_results(ib_cache, list(ticker_map))
            logger.info("IB Gateway news pass done: %d tickers, %d cached articles", len(ticker_map), len(ib_cache))
            with open("ibnews.json", "w") as f:
                json.dump(ib_results, f, indent=2)
        finally:
            ib.disconnect()