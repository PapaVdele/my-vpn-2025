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

last_alerts = {}

sent_news_urls = set()

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

    # Расширенный юмор и FOMO — 20+ вариантов, разные, развёрнутые
    humor_phrases = [
        "Бомжи, пока вы в USDT сидите и 'ждёте дна', киты уже мешки грузят. Это ваш билет в пентхаус или вечный подвал?",
        "Помните 2021? Кто не боялся — в ламбо. Кто ждал 'ещё подешевле' — до сих пор в криптобомжах. Не повторяйте ошибок 😏",
        "Киты не спят — они аккумулируют. А вы? Всё ещё 'держите стронг хендс' в фиате? FOMO уже стучит в дверь.",
        "Это не рандомный памп — это реальный аккумулятор на дне. Кто урвёт сейчас — тот через месяц в Дубае. А вы?",
        "Бомжи, рынок даёт второй шанс. Первый был в 2022 на дне. Кто пропустил — до сих пор ноет. Не будьте тем парнем.",
        "Киты грузят тихо, а потом — луна. Вы с ними или опять 'подожду подтверждения'? Подтверждение будет по $10k за монету.",
        "Это не скам — это те же проекты, что в 2021 дали x100. Только сейчас на дне. Рубль на веру — и вы в плюсе.",
        "Пока вы 'анализируете', киты уже в позиции. Через неделю будете ныть 'почему не сказал раньше'? Говорю сейчас 😈",
        "Бомжи, это как купить BTC по $3k в 2020. Только сейчас. Не проспите — второй раз рынок не даст такой шанс.",
        "Кто-то уже урвал +50% с прошлого сигнала. А вы всё в 'наблюдателях'? Время действовать, легенды не ждут."
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
        history = last.get('history', [])
        history.append({'time': current_time, 'price': price})
        history = [h for h in history if current_time - h['time'] <= timedelta(days=10)]

        for h in history[:-1]:
            days = (current_time - h['time']).days
            long_diff = ((price - h['price']) / h['price']) * 100 if h['price'] > 0 else 0
            if long_diff > 50:
                long_fomo += f"С сигнала {days} дней назад уже +{long_diff:.2f}%! Кто-то из бомжей стал легендой, а вы всё ждёте 'идеального входа'? 😏\n"

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
                fomo = f"С прошлого сигнала уже +{price_diff:+.2f}%! Киты улыбаются, а вы всё в 'подожду'? Это ваш поезд на луну уходит!\n"

        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.1):
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            volume_str = "аномально высокий"
            status = "новый сигнал — возможная аккумуляция!"

        value = "Надёжный аккумулятор на дне — киты грузят, ждут мощного отскока. Проекты вроде UNI/APT — проверенные, не скам."

        humor = random.choice(humor_phrases)

        alert_block = f"🚨 АНОМАЛЬНЫЙ ОБЁМ — {status} 🚨\n"
        alert_block += f"{coin['name']} ({coin['symbol'].upper()})\n"
        alert_block += f"Цена: ${format_price(price)} ({price_str})\n"
        alert_block += f"Объём 24h: ${volume:,.0f} ({volume_str})\n"
        alert_block += f"{value}\n"
        if ath_change < -80:
            alert_block += f"На дне: {ath_change:.1f}% от ATH 🔥\n"
        alert_block += long_fomo
        alert_block += fomo
        alert_block += f"\n{humor}\n"
        alert_block += f"Подробности: coingecko.com/en/coins/{coin_id}"

        alerts.append(alert_block)

        if len(alerts) >= 5:
            break

    if not alerts:
        return None

    full_msg = "🚨 Свежие аккумуляторы с аномальным объёмом — киты в деле! 🚨\n\n"
    full_msg += "Рынок на дне, проверенные проекты (UNI, APT, TRUMP и др.) аккумулируют объём. Это не рандом — это шанс на мощный отскок. Кто войдёт сейчас — тот через месяц в плюсе. Не будьте тем бомжом, который 'ждал подтверждения' в 2022. Рубль на веру — и вы легенда 😏\n\n"
    full_msg += "\n\n".join(alerts)

    return full_msg

def get_news():
    global sent_news_urls
    try:
        sources = [
            "https://forklog.com/feed",
            "https://bits.media/rss/",
            "https://www.rbc.ru/crypto/rss"
        ]
        unique_entries = {}
        for url in sources:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    link = entry.link
                    if link not in sent_news_urls and link not in unique_entries:
                        unique_entries[link] = entry.title
            except:
                continue

        if not unique_entries:
            return None

        top3 = list(unique_entries.items())[:3]

        msg = "📰 Топ-3 свежих новостей крипты:\n\n"
        for link, title in top3:
            msg += f"{title}\n{link}\n\n"
            sent_news_urls.add(link)

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
            bot.send_message(GROUP_CHAT_ID, news, disable_web_page_preview=True)
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
    schedule.every().day.at("07:00").do(daily_report_task)

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

    schedule.every().day.at("19:00").do(final_report_task)

    schedule.every().hour.do(send_alerts)  # ночь — мощные

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    print("КриптоАСИСТ ожил! 😈")
    threading.Thread(target=run_scheduler, daemon=True).start()
    bot.infinity_polling(none_stop=True)
