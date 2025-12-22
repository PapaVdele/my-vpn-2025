import telebot
import requests
import schedule
import time
import threading
from datetime import datetime, timedelta
import os
import feedparser
import random
from difflib import SequenceMatcher

BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID') or '-1001922647461')

bot = telebot.TeleBot(BOT_TOKEN)

last_alerts = {}

sent_news_urls = set()
sent_news_titles = set()

current_source_index = 0

sources = [
    ("ForkLog", "https://forklog.com/feed"),
    ("Bits.media", "https://bits.media/rss/"),
    ("RBC Crypto", "https://www.rbc.ru/crypto/rss")
]

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

        top_growth = sorted_growth[:5]
        top_drop = sorted_drop[:5]

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

def create_daily_report():
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — отчёт позже"
    btc_change = data['btc_change']
    if btc_change > 5:
        title = "Криптопушка! 🚀 Бомжи, рынок летит — время грузить мешки!"
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
    for i, coin in enumerate(data['top_growth'][:3], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    msg += "\n📉 Топ-3 падения:\n"
    for i, coin in enumerate(data['top_drop'][:3], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    msg += "\nИсточник: CoinGecko"
    return msg

def final_day_report():
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — финальный отчёт позже"
    msg = "📊 Финальный отчёт за день — лидеры роста и дна:\n\n"
    msg += "🚀 Топ-5 роста за 24ч:\n"
    for i, coin in enumerate(data['top_growth'], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    msg += "\n📉 Топ-5 падения за 24ч:\n"
    for i, coin in enumerate(data['top_drop'], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    msg += "\nБомжи, вот кто сегодня рулил рынком. Завтра новый день — новые шансы 😏"
    return msg

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
        "Это не скам — это реальный аккумулятор. Кто урвёт — тот в пентхаус.",
        "Помните 2021? Кто не боялся — в ламбо. Кто ждал 'ещё подешевле' — до сих пор в криптобомжах.",
        "Бомжи, рынок даёт второй шанс. Первый был в 2022 на дне. Не повторяйте ошибок.",
        "Киты не спят — они аккумулируют. А вы? Всё ещё 'держите стронг хендс' в фиате?",
        "Это как купить BTC по $3k в 2020. Только сейчас. Не проспите — второй раз рынок не даст такой шанс.",
        "Пока вы 'анализируете', киты уже в позиции. Через неделю будете ныть 'почему не сказал раньше'? Говорю сейчас 😈"
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

        long_fomo = ""
        reply_id = last.get('message_id', None)
        history = last.get('history', [])
        history.append({'time': current_time, 'price': price})
        history = [h for h in history if current_time - h['time'] <= timedelta(days=10)]

        for h in history[:-1]:
            days_ago = (current_time - h['time']).days
            if days_ago == 0:
                days_ago = 1
            profit = ((price - h['price']) / h['price']) * 100 if h['price'] > 0 else 0
            if profit > 20:
                long_fomo += f"С сигнала {days_ago} дней назад уже +{profit:.2f}% (с ${format_price(h['price'])} до ${format_price(price)})! Кто-то урвал, а вы? 😏\n"

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
                fomo = f"С последнего сигнала уже +{price_diff:+.2f}%! Киты улыбаются, а вы всё ждёте?\n"

        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.1):
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            volume_str = "аномально высокий"
            status = "новый сигнал — возможная аккумуляция!"

        value = "Надёжный аккумулятор на дне — киты грузят, ждут мощного отскока."

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
        alert += f"Подробности: coingecko.com/en/coins/{coin_id}"

        try:
            sent = bot.send_message(GROUP_CHAT_ID, alert, reply_to_message_id=reply_id, disable_web_page_preview=True)
            last_alerts[coin_id] = {
                'time': current_time,
                'price': price,
                'volume': volume,
                'message_id': sent.message_id,
                'history': history
            }
        except:
            pass

        alerts.append(alert)

        if len(alerts) >= 5:
            break

    if not alerts:
        return None

    full_msg = "🚨 Свежие аккумуляторы с аномальным объёмом — киты в деле! 🚨\n\n"
    full_msg += "Рынок на дне, проверенные проекты аккумулируют объём. Это шанс на отскок. Кто войдёт — тот в плюсе. Не будьте тем, кто 'ждал подтверждения' в 2022. Рубль на веру — и вы легенда 😏\n\n"
    full_msg += "\n\n".join(alerts)

    return full_msg

def get_news():
    global current_source_index, sent_news_urls, sent_news_titles
    try:
        source_name, url = sources[current_source_index]
        current_source_index = (current_source_index + 1) % len(sources)

        feed = feedparser.parse(url)

        unique_entries = {}
        for entry in feed.entries:
            link = entry.link
            title = entry.title.strip()
            if link not in sent_news_urls and title.lower() not in sent_news_titles and link not in unique_entries:
                unique_entries[link] = title

        if not unique_entries:
            return None

        top3 = list(unique_entries.items())[:3]

        msg = f"📰 Свежак от {source_name} — бомжи, читайте, пока не поздно 😏\n\n"
        for link, title in top3:
            msg += f"{title}\n{link}\n\n"
            sent_news_urls.add(link)
            sent_news_titles.add(title.lower())

        return msg
    except:
        return None

def send_alerts():
    alert = get_anomaly_alerts()
    if alert:
        try:
            bot.send_message(GROUP_CHAT_ID, alert, disable_web_page_preview=True)
        except:
            pass

def send_news():
    news = get_news()
    if news:
        try:
            bot.send_message(GROUP_CHAT_ID, news, disable_web_page_preview=False)
        except:
            pass

def daily_report_task():
    try:
        bot.send_message(GROUP_CHAT_ID, create_daily_report())
    except:
        pass

def final_report_task():
    try:
        bot.send_message(GROUP_CHAT_ID, final_day_report())
    except:
        pass

def run_scheduler():
    schedule.every().day.at("07:00").do(daily_report_task)  # 10:00 МСК

    utc_times = [
        "07:15", "07:30", "07:45", "08:00",
        "08:15", "08:30", "08:45", "09:00",
        "09:15", "09:30", "09:45", "10:00",
        "10:15", "10:30", "10:45", "11:00",
        "11:15", "11:30", "11:45", "12:00",
        "12:15", "12:30", "12:45", "13:00",
        "13:15", "13:30", "13:45", "14:00",
        "14:15", "14:30", "14:45", "15:00",
        "15:15", "15:30", "15:45", "16:00",
        "16:15", "16:30", "16:45", "17:00",
        "17:15", "17:30", "17:45", "18:00",
        "18:15", "18:30", "18:45"
    ]

    for i, t in enumerate(utc_times):
        if i % 2 == 0:
            schedule.every().day.at(t).do(send_alerts)
        else:
            schedule.every().day.at(t).do(send_news)

    schedule.every().day.at("19:00").do(final_report_task)  # 22:00 МСК

    schedule.every().hour.do(send_alerts)  # ночь — мощные

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    print("КриптоАСИСТ ожил! 😈")
    threading.Thread(target=run_scheduler, daemon=True).start()
    bot.infinity_polling(none_stop=True)
