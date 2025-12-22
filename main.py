import telebot
import requests
import schedule
import time
import threading
from datetime import datetime, timedelta
import os
import feedparser
import random

BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID') or '-1001922647461')

bot = telebot.TeleBot(BOT_TOKEN)

last_alerts = {}  # coin_id: {'time': dt, 'price': float, 'volume': int, 'message_id': int, 'history': [{'time': dt, 'price': float}]}

STABLE_KEYWORDS = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'GUSD', 'FDUSD', 'PYUSD', 'FRAX', 'USDE', 'USD', 'BSC-USD', 'BRIDGED', 'WRAPPED', 'STETH', 'WBTC', 'CBBTC', 'WETH', 'WSTETH', 'CBETH']

def is_stable(coin):
    symbol = coin['symbol'].upper()
    name = coin['name'].lower()
    return any(kw in symbol or kw in name for kw in STABLE_KEYWORDS)

def get_crypto_data():
    try:
        price_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
        price_data = requests.get(price_url, timeout=15).json()

        btc_price = price_data.get('bitcoin', {}).get('usd', 0)
        btc_change = round(price_data.get('bitcoin', {}).get('usd_24h_change', 0), 2)
        eth_price = price_data.get('ethereum', {}).get('usd', 0)
        eth_change = round(price_data.get('ethereum', {}).get('usd_24h_change', 0), 2)
        sol_price = price_data.get('solana', {}).get('usd', 0)
        sol_change = round(price_data.get('solana', {}).get('usd_24h_change', 0), 2)

        markets_url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&price_change_percentage=24h"
        all_coins = requests.get(markets_url, timeout=15).json()

        filtered_coins = [coin for coin in all_coins if not is_stable(coin)]

        sorted_growth = sorted(filtered_coins, key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)
        sorted_drop = sorted(filtered_coins, key=lambda x: x.get('price_change_percentage_24h', 0) or 0)

        top_growth = sorted_growth[:3]
        top_drop = sorted_drop[:3]

        return {
            'btc_price': btc_price, 'btc_change': btc_change,
            'eth_price': eth_price, 'eth_change': eth_change,
            'sol_price': sol_price, 'sol_change': sol_change,
            'all_coins': filtered_coins,
            'top_growth': top_growth,
            'top_drop': top_drop
        }
    except:
        return {'all_coins': [], 'top_growth': [], 'top_drop': []}

def format_price(price):
    if price == 0:
        return "$?"
    if price < 1:
        return f"${price:.8f}".rstrip('0').rstrip('.')
    return f"${price:,.2f}"

def get_top_cap(n=10):
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
        data = requests.get(url, timeout=15).json()
        filtered = [coin for coin in data if not is_stable(coin)][:n]
        msg = f"🏆 Топ-{n} по капитализации (без стейблов):\n\n"
        for i, coin in enumerate(filtered, 1):
            msg += f"{i}. {coin['symbol'].upper()}: {format_price(coin['current_price'])}\n"
        return msg
    except:
        return "⚠️ Проблема с данными — попробуй позже"

def get_top_growth(n=10):
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    msg = f"🚀 Топ-{n} роста за 24ч:\n\n"
    sorted_growth = sorted(data['all_coins'], key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[:n]
    for i, coin in enumerate(sorted_growth, 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    return msg

def get_top_drop(n=10):
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    msg = f"📉 Топ-{n} падения за 24ч:\n\n"
    sorted_drop = sorted(data['all_coins'], key=lambda x: x.get('price_change_percentage_24h', 0) or 0)[:n]
    for i, coin in enumerate(sorted_drop, 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    return msg

def create_daily_report():
    data = get_crypto_data()
    if not data['all_coins']:
        time.sleep(600)  # retry after 10 min
        data = get_crypto_data()
        if not data['all_coins']:
            return None  # skip if still no data
    btc_change = data['btc_change']
    if btc_change > 5:
        title = "Криптопушка! 🚀 Бомжи, просыпаемся — рынок летит вверх!"
    elif btc_change > 0:
        title = "Криптопотрясение 📈 Тихо растём — киты шевелятся."
    elif btc_change > -5:
        title = "Криптостабильность 😐 Рынок дышит — ждём импульса."
    else:
        title = "Криптообвал 📉 Держимся, бомжи — дно близко, отскок будет мощный!"
    msg = f"{title}\n\n"
    msg += "Основные:\n"
    msg += f"🟠 BTC: ${data['btc_price']:,} {btc_change:+.2f}%\n"
    msg += f"🔷 ETH: ${data['eth_price']:,} {data['eth_change']:+.2f}%\n"
    msg += f"🟣 SOL: ${data['sol_price']:,} {data['sol_change']:+.2f}%\n\n"
    msg += "🚀 Топ-3 роста:\n"
    for i, coin in enumerate(data['top_growth'], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    msg += "\n📉 Топ-3 падения:\n"
    for i, coin in enumerate(data['top_drop'], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    msg += "\nИсточник: CoinGecko"
    return msg

sources = [
    "https://forklog.com/feed",
    "https://bits.media/rss/",
    "https://www.rbc.ru/crypto/rss"
]

last_news_time = datetime.min

def get_news():
    global last_news_time
    try:
        for url in sources:
            feed = feedparser.parse(url)
            entries = [entry for entry in feed.entries if datetime.fromtimestamp(time.mktime(entry.published_parsed)) > last_news_time][:3]
            if entries:
                last_news_time = datetime.fromtimestamp(time.mktime(entries[0].published_parsed))
                msg = "📰 Топ свежих новостей крипты:\n\n"
                for i, entry in enumerate(entries, 1):
                    title = entry.title
                    link = entry.link
                    msg += f"{i}. {title}\n{link}\n\n"
                return msg
        return None  # no new news
    except:
        return None

def get_anomaly_alerts():
    data = get_crypto_data()
    if not data['all_coins']:
        return None

    alerts = []
    current_time = datetime.now()

    fomo_phrases = [
        "Бомжи, это ваш шанс выбраться из подвала! Киты уже грузят.",
        "Не проспите — вчерашние сигналы уже дали памп. FOMO включён?",
        "Киты в деле, а вы всё в фиате? Присмотритесь, пока не поздно 😏",
        "Это не скам — это реальный аккумулятор. Кто урвёт — тот в пентхаус."
    ]

    for coin in data['all_coins']:
        volume = coin.get('total_volume', 0)
        price_change = coin.get('price_change_percentage_24h', 0) or 0
        market_cap = coin.get('market_cap', 1)
        ath_change = coin.get('ath_change_percentage', 0) or 0
        price = coin.get('current_price', 0)
        coin_id = coin['id']

        if not (volume > 20000000 and market_cap > 100000000 and price > 0.001 and ath_change < -80):
            continue

        last = last_alerts.get(coin_id, {'history': []})

        fomo = ""
        long_fomo = ""
        reply_id = last.get('message_id', None)
        history = last['history']
        history.append({'time': current_time, 'price': price})  # add current to history
        history = [h for h in history if current_time - h['time'] <= timedelta(days=10)]  # keep 10 days

        for h in history[:-1]:  # check past for long FOMO
            days = (current_time - h['time']).days
            long_diff = ((price - h['price']) / h['price']) * 100 if h['price'] > 0 else 0
            if long_diff > 50:
                long_fomo = f"С сигнала {days} дней назад +{long_diff:.2f}%! Бомжи, действуйте — рубль на веру 😏\n"

        if 'time' in last:
            time_diff = current_time - last['time']
            if time_diff < timedelta(hours=3):
                continue

            price_diff = ((price - last['price']) / last['price']) * 100 if last['price'] > 0 else 0
            volume_diff = ((volume - last['volume']) / last['volume']) * 100 if last['volume'] > 0 else 0

            if abs(price_diff) < 8 and abs(volume_diff) < 20:
                continue

            price_str = f"{price_diff:+.2f}% с прошлого сигнала (было ${format_price(last['price'])})"
            volume_str = f"{volume_diff:+.2f}% с прошлого сигнала"
            status = "сигнал усиливается 🔥" if price_diff > 0 and volume_diff > 20 else "сигнал слабеет ⚠️"

            if price_diff > 10:
                fomo = f"С прошлого сигнала уже {price_diff:+.2f}%! Кто-то из бомжей урвал, а вы? 😏\n"

        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.1):
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            volume_str = "аномально высокий"
            status = "новый сигнал — возможная аккумуляция!"

        value = "Как TRX — надёжный, как золото, всегда идёт наверх. Аккумулировал объём, ждём роста."

        humor = random.choice(fomo_phrases)

        alert = f"🚨 АНОМАЛЬНЫЙ ОБЪЁМ — {status} 🚨\n\n"
        alert += f"{coin['name']} ({coin['symbol'].upper()})\n"
        alert += f"Цена: ${format_price(price)} ({price_str})\n"
        alert += f"Объём 24h: ${volume:,.0f} ({volume_str})\n"
        alert += f"{value}\n"
        if ath_change < -80:
            alert += f"На дне: {ath_change:.1f}% от ATH 🔥\n"
        alert += long_fomo
        alert += fomo
        alert += f"\n{humor}\n"
        alert += f"Ссылка: https://www.coingecko.com/en/coins/{coin_id}"

        try:
            sent_msg = bot.send_message(GROUP_CHAT_ID, alert, reply_to_message_id=reply_id)
            last_alerts[coin_id] = {
                'time': current_time,
                'price': price,
                'volume': volume,
                'message_id': sent_msg.message_id,
                'history': history
            }
        except:
            pass

        alerts.append(alert)

        if len(alerts) >= 3:
            break

    return "\n\n".join(alerts) if alerts else None

@bot.message_handler(commands=['курс'])
def handle_kurs(message):
    bot.send_message(message.chat.id, create_daily_report())

@bot.message_handler(commands=['топ'])
def handle_top(message):
    bot.send_message(message.chat.id, get_top_cap(10))

@bot.message_handler(commands=['рост'])
def handle_growth(message):
    bot.send_message(message.chat.id, get_top_growth(10))

@bot.message_handler(commands=['падение'])
def handle_drop(message):
    bot.send_message(message.chat.id, get_top_drop(10))

@bot.message_handler(commands=['алерт'])
def handle_alert(message):
    alert = get_anomaly_alerts()
    if alert:
        bot.send_message(message.chat.id, alert)
    else:
        bot.send_message(message.chat.id, "😴 Сейчас нет значимых аномалий — рынок спокойный.")

@bot.message_handler(commands=['новости'])
def handle_news(message):
    news = get_news()
    if news:
        bot.send_message(message.chat.id, news)
    else:
        bot.send_message(message.chat.id, "⚠️ Проблема с новостями — попробуй позже")

@bot.message_handler(commands=['помощь', 'help'])
def handle_help(message):
    help_text = """
🤖 *КриптоАСИСТ — твоя криптошкола в 'Криптобомжах'*

Команды:
• /курс — отчёт по рынку
• /топ — топ капитализации
• /рост — топ роста
• /падение — топ падения
• /алерт — аномалии с анализом
• /новости — свежие новости крипты
• /помощь — это
"""
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['фомо'])
def handle_fomo(message):
    fomo_msg = "Топ FOMO от прошлых сигналов:\n\n"
    for coin_id, data in last_alerts.items():
        history = data['history']
        if len(history) > 1:
            long_diff = ((history[-1]['price'] - history[0]['price']) / history[0]['price']) * 100 if history[0]['price'] > 0 else 0
            if long_diff > 50:
                days = (history[-1]['time'] - history[0]['time']).days
                fomo_msg += f"{coin_id.upper()} +{long_diff:.2f}% за {days} дней! Бомжи, действуйте — рубль на веру 😏\n"
    if fomo_msg == "Топ FOMO от прошлых сигналов:\n\n":
        fomo_msg = "Пока нет сильных пампов от прошлых сигналов. Ждём! 👀"
    bot.send_message(message.chat.id, fomo_msg)

def daily_report():
    try:
        bot.send_message(GROUP_CHAT_ID, create_daily_report())
    except:
        pass

def hourly_update():
    alert = get_anomaly_alerts()
    if alert:
        try:
            bot.send_message(GROUP_CHAT_ID, alert)
            time.sleep(300)  # 5 min pause before news
            news = get_news()
            if news:
                bot.send_message(GROUP_CHAT_ID, news)
        except:
            pass
    else:
        news = get_news()
        if news:
            try:
                bot.send_message(GROUP_CHAT_ID, news)
            except:
                pass

def run_scheduler():
    schedule.every().day.at("06:55").do(daily_report)  # 10:00 МСК
    schedule.every().hour.do(hourly_update)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    print("КриптоАСИСТ ожил! 😈")
    threading.Thread(target=run_scheduler, daemon=True).start()
    bot.infinity_polling(none_stop=True)
