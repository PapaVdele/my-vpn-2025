import telebot
import requests
import schedule
import time
import threading
from datetime import datetime, timedelta
from groq import Groq
import os

BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID'))
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

last_alerts = {}

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
    except Exception as e:
        print(f"Ошибка данных: {e}")
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
        msg = f"🏆 *Топ-{n} по капитализации (без стейблов):*\n\n"
        for i, coin in enumerate(filtered, 1):
            msg += f"{i}. {coin['symbol'].upper()}: {format_price(coin['current_price'])}\n"
        return msg
    except:
        return "⚠️ Проблема с данными — попробуй позже"

def get_top_growth(n=10):
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    msg = f"🚀 *Топ-{n} роста за 24ч:*\n\n"
    sorted_growth = sorted(data['all_coins'], key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[:n]
    for i, coin in enumerate(sorted_growth, 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. *{coin['name']}* ({coin['symbol'].upper()}) — *{change:+.2f}%* ({format_price(coin['current_price'])})\n"
    return msg

def get_top_drop(n=10):
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    msg = f"📉 *Топ-{n} падения за 24ч:*\n\n"
    sorted_drop = sorted(data['all_coins'], key=lambda x: x.get('price_change_percentage_24h', 0) or 0)[:n]
    for i, coin in enumerate(sorted_drop, 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. *{coin['name']}* ({coin['symbol'].upper()}) — *{change:+.2f}%* ({format_price(coin['current_price'])})\n"
    return msg

def create_daily_report():
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — отчёт позже"
    msg = "📊 *Ежедневный крипто-отчёт* 📊\n\n"
    msg += "*Основные:*\n"
    msg += f"🟠 BTC: ${data['btc_price']:,} {'📈' if data['btc_change'] > 0 else '📉'} *{data['btc_change']:+.2f}%*\n"
    msg += f"🔷 ETH: ${data['eth_price']:,} {'📈' if data['eth_change'] > 0 else '📉'} *{data['eth_change']:+.2f}%*\n"
    msg += f"🟣 SOL: ${data['sol_price']:,} {'📈' if data['sol_change'] > 0 else '📉'} *{data['sol_change']:+.2f}%*\n\n"
    msg += "🚀 *Топ-3 роста:*\n"
    for i, coin in enumerate(data['top_growth'], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. *{coin['name']}* ({coin['symbol'].upper()}) — *{change:+.2f}%* ({format_price(coin['current_price'])})\n"
    msg += "\n📉 *Топ-3 падения:*\n"
    for i, coin in enumerate(data['top_drop'], 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. *{coin['name']}* ({coin['symbol'].upper()}) — *{change:+.2f}%* ({format_price(coin['current_price'])})\n"
    msg += "\n_Источник: CoinGecko_"
    return msg

def get_anomaly_alerts():
    data = get_crypto_data()
    if not data['all_coins']:
        return None

    alerts = []
    current_time = datetime.now()

    for coin in data['all_coins']:
        volume = coin.get('total_volume', 0)
        price_change = coin.get('price_change_percentage_24h', 0) or 0
        market_cap = coin.get('market_cap', 1)
        ath_change = coin.get('ath_change_percentage', 0) or 0
        price = coin.get('current_price', 0)
        coin_id = coin['id']

        if not (volume > 10_000_000 and market_cap > 50_000_000):
            continue

        last = last_alerts.get(coin_id)

        if last:
            time_diff = current_time - last['time']
            if time_diff < timedelta(hours=3):
                continue

            price_diff = ((price - last['price']) / last['price']) * 100 if last['price'] > 0 else 0
            volume_diff = ((volume - last['volume']) / last['volume']) * 100 if last['volume'] > 0 else 0

            if abs(price_diff) < 8 and abs(volume_diff) < 20:
                continue

            price_str = f"{price_diff:+.2f}% с прошлого сигнала (было ${format_price(last['price'])})"
            volume_str = f"{volume_diff:+.2f}% с прошлого сигнала"
            status = "сигнал усиливается 🔥" if price_diff > 0 and volume_diff > 0 else "сигнал слабеет ⚠️"

        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.08):
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            volume_str = "аномально высокий"
            status = "новый сигнал — возможная аккумуляция!"

        alert = f"🚨 *АНОМАЛЬНЫЙ ОБЪЁМ — {status}* 🚨\n\n"
        alert += f"*{coin['name']}* ({coin['symbol'].upper()})\n"
        alert += f"Цена: ${format_price(price)} ({price_str})\n"
        alert += f"Объём 24h: ${volume:,.0f} ({volume_str})\n"
        if ath_change < -80:
            alert += f"На дне: {ath_change:.1f}% от ATH 🔥\n"
        alert += "\nКиты в деле — следим! 👀"

        alerts.append(alert)

        last_alerts[coin_id] = {
            'time': current_time,
            'price': price,
            'volume': volume
        }

        if len(alerts) >= 4:
            break

    return "\n\n".join(alerts) if alerts else None

def ask_groq(question):
    try:
        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": "Ты — циничный, остроумный криптобомж из чата 'Криптобомжи'. Отвечай кратко, по делу, с чёрным юмором, матом если уместно, сленгом. Будь своим — подкалывай, радуйся пампам, грусти по дампам. Всегда на русском."},
                {"role": "user", "content": question}
            ],
            temperature=0.9,
            max_tokens=300
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq ошибка: {e}")
        return "Groq сегодня в отключке... Попробуй позже 😅"

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    if message.text and message.text.startswith('/'):
        return
    if message.from_user.is_bot:
        return
    if not message.text or len(message.text.strip()) < 3:
        return

    reply = ask_groq(message.text)
    bot.reply_to(message, reply)

@bot.message_handler(commands=['курс'])
def handle_kurs(message):
    bot.send_message(message.chat.id, create_daily_report(), parse_mode='Markdown')

@bot.message_handler(commands=['топ'])
def handle_top(message):
    bot.send_message(message.chat.id
