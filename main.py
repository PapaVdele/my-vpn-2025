import telebot
import requests
import schedule
import time
import threading
import os
import feedparser
import random
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1001922647461"))

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

COINGECKO_MARKETS = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=market_cap_desc&per_page=250&page=1"
    "&price_change_percentage=24h"
)

CACHE = {"time": None, "data": None}
CACHE_TTL = 60  # секунд

last_alerts = {}
sent_news_urls = set()
sent_news_titles = set()

NEWS_SOURCES = [
    ("ForkLog", "https://forklog.com/feed"),
    ("Bits.media", "https://bits.media/rss/"),
    ("RBC Crypto", "https://www.rbc.ru/crypto/rss"),
]

STABLE_KEYWORDS = [
    "USDT", "USDC", "DAI", "BUSD", "USD", "FRAX",
    "WBTC", "WETH", "STETH", "CBETH"
]

# ================== HELPERS ==================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def is_stable(coin):
    name = coin["name"].lower()
    symbol = coin["symbol"].upper()
    return any(k.lower() in name or k in symbol for k in STABLE_KEYWORDS)

def format_price(p):
    if p < 1:
        return f"${p:.8f}".rstrip("0").rstrip(".")
    return f"${p:,.2f}"

# ================== DATA ==================

def get_market_data():
    global CACHE
    now = datetime.now()

    if CACHE["time"] and (now - CACHE["time"]).seconds < CACHE_TTL:
        return CACHE["data"]

    try:
        r = requests.get(COINGECKO_MARKETS, timeout=15)
        coins = [c for c in r.json() if not is_stable(c)]

        CACHE = {"time": now, "data": coins}
        return coins
    except Exception as e:
        log(f"CoinGecko error: {e}")
        return []

# ================== REPORTS ==================

def daily_report():
    coins = get_market_data()
    if not coins:
        return "⚠️ Данные недоступны"

    btc = next(c for c in coins if c["symbol"] == "btc")
    mood = (
        "эйфория" if btc["price_change_percentage_24h"] > 5 else
        "осторожный оптимизм" if btc["price_change_percentage_24h"] > 0 else
        "напряжённое ожидание"
    )

    top_up = sorted(coins, key=lambda x: x["price_change_percentage_24h"] or 0, reverse=True)[:3]
    top_down = sorted(coins, key=lambda x: x["price_change_percentage_24h"] or 0)[:3]

    msg = f"🌅 Утро. Рынок в режиме: *{mood}*\n\n"
    msg += f"BTC: {format_price(btc['current_price'])} ({btc['price_change_percentage_24h']:+.2f}%)\n\n"

    msg += "🚀 Рост:\n"
    for c in top_up:
        msg += f"• {c['symbol'].upper()} {c['price_change_percentage_24h']:+.2f}%\n"

    msg += "\n📉 Падение:\n"
    for c in top_down:
        msg += f"• {c['symbol'].upper()} {c['price_change_percentage_24h']:+.2f}%\n"

    return msg

# ================== ALERTS ==================

def anomaly_alerts():
    coins = get_market_data()
    now = datetime.now()
    alerts = []

    for c in coins:
        if c["total_volume"] < 30_000_000:
            continue
        if c["ath_change_percentage"] > -75:
            continue

        last = last_alerts.get(c["id"])
        if last and now - last < timedelta(hours=4):
            continue

        text = (
            f"🚨 *Аномальный объём*\n"
            f"{c['name']} ({c['symbol'].upper()})\n"
            f"Цена: {format_price(c['current_price'])}\n"
            f"От ATH: {c['ath_change_percentage']:.1f}%\n\n"
            f"Рынок редко даёт такие окна. "
            f"Кто видит — тот раньше других."
        )

        alerts.append(text)
        last_alerts[c["id"]] = now

        if len(alerts) >= 2:
            break

    return alerts

# ================== NEWS ==================

def get_news():
    for name, url in NEWS_SOURCES:
        feed = feedparser.parse(url)
        for e in feed.entries[:5]:
            title = e.title.strip()
            if e.link in sent_news_urls:
                continue
            if any(SequenceMatcher(None, title.lower(), t).ratio() > 0.8 for t in sent_news_titles):
                continue

            sent_news_urls.add(e.link)
            sent_news_titles.add(title.lower())

            return f"📰 {name}\n{title}\n{e.link}"

    return None

# ================== COMMANDS ==================

@bot.message_handler(commands=["курс"])
def cmd_kurs(m):
    bot.send_message(m.chat.id, daily_report(), parse_mode="Markdown")

@bot.message_handler(commands=["алерт"])
def cmd_alert(m):
    alerts = anomaly_alerts()
    if not alerts:
        bot.send_message(m.chat.id, "Рынок спокоен. Подозрительной тишины нет.")
    for a in alerts:
        bot.send_message(m.chat.id, a, parse_mode="Markdown")

@bot.message_handler(commands=["новости"])
def cmd_news(m):
    news = get_news()
    bot.send_message(m.chat.id, news or "Пока без свежего.")

@bot.message_handler(commands=["помощь", "help"])
def cmd_help(m):
    bot.send_message(
        m.chat.id,
        "Команды:\n"
        "/курс — рынок\n"
        "/алерт — аномалии\n"
        "/новости — новости\n\n"
        "Это не сигналы. Это ориентиры."
    )

# ================== SCHEDULER ==================

def scheduler():
    schedule.every().day.at("07:00").do(lambda: bot.send_message(GROUP_CHAT_ID, daily_report()))
    schedule.every(2).hours
