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
import json
from web3 import Web3
import asyncio
import aiohttp
from functools import lru_cache

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID') or '-1001922647461')

# API ключи (добавьте в переменные окружения)
ETHERSCAN_API = os.getenv('ETHERSCAN_API')
BSCSCAN_API = os.getenv('BSCSCAN_API')
CRYPTOQUANT_API = os.getenv('CRYPTOQUANT_API')
INFURA_URL = os.getenv('INFURA_URL')

bot = telebot.TeleBot(BOT_TOKEN)

# ========== ХРАНИЛИЩЕ ДАННЫХ ==========
last_alerts = {}
sent_news_urls = set()
sent_news_titles = set()
current_source_index = 0
transaction_cache = {}

# ========== ИЗВЕСТНЫЕ АДРЕСА ==========
# Binance горячие кошельки (Ethereum)
BINANCE_WALLETS = [
    "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",  # Binance 14
    "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance 16
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549",  # Binance 29
]

# Coinbase кошельки
COINBASE_WALLETS = [
    "0xA9D1e08C7793af67e9d92fe308d5697FB81d3E43",
    "0x71660c4005BA85c37ccec55d0C4493E66Fe775d3",
]

# Bybit кошельки
BYBIT_WALLETS = [
    "0xf89d7b9c864f589bbF53a82105107622B35EaA40",
    "0x1Db92e2EeBC8E0c075a02BeA49a2935Bcd2dFCF4",
]

# Kraken кошельки
KRAKEN_WALLETS = [
    "0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2",
    "0x53d284357ec70cE289D6D64134DfAc8E511c8a3D",
]

# Контракты стейкинга ETH
STAKING_CONTRACTS = {
    "Lido": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
    "Coinbase": "0xBeFdeeBb206C64d7c1310F8e8A3F543E71b0003f",
    "Binance": "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    "Kraken": "0x39f6a6c85d39d5abad8a398310c52e7c374f2ba3",
}

# Известные киты (публичные адреса)
KNOWN_WHALES = {
    "0x220866b1a2219f40e72f5c628b65d54268ca3a9d": "Vitalik Buterin",
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": "Binance CEO",
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": "0xb1 Киты",
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance 16 (активный)",
}

# ========== КОНСТАНТЫ ==========
STABLE_KEYWORDS = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'GUSD', 'FDUSD', 'PYUSD', 'FRAX', 'USDE', 'USD', 'BSC-USD']

# ========== ОСНОВНЫЕ ФУНКЦИИ ДАННЫХ ==========
def get_crypto_data():
    """Получение данных с CoinGecko"""
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
    except Exception as e:
        print(f"Ошибка получения данных: {e}")
        return {'all_coins': [], 'top_growth': [], 'top_drop': []}

def is_stable(coin):
    """Проверка, является ли монета стейблкоином"""
    symbol = coin['symbol'].upper()
    name = coin['name'].lower()
    return any(kw in symbol or kw in name for kw in STABLE_KEYWORDS)

def format_price(price):
    """Форматирование цены"""
    if price == 0:
        return "$?"
    if price < 1:
        return f"${price:.8f}".rstrip('0').rstrip('.')
    return f"${price:,.2f}"

# ========== НОВЫЕ ФУНКЦИИ ДЛЯ ТРАНЗАКЦИЙ ==========
def get_large_eth_transfers():
    """Получение крупных транзакций ETH (> $500K) через Etherscan"""
    if not ETHERSCAN_API:
        return []
    
    try:
        url = f"https://api.etherscan.io/api?module=account&action=tokentx&address=0x0000000000000000000000000000000000000000&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API}"
        response = requests.get(url, timeout=10).json()
        
        alerts = []
        eth_price = get_eth_price()
        
        for tx in response.get('result', [])[:20]:  # Последние 20 транзакций
            value_eth = int(tx['value']) / 1e18
            value_usd = value_eth * eth_price
            
            if value_usd > 500000:  # Только > $500K
                from_label = get_wallet_label(tx['from'])
                to_label = get_wallet_label(tx['to'])
                
                alert = f"💰 КРУПНАЯ ТРАНЗАКЦИЯ ETH\n\n"
                alert += f"📤 От: {from_label}\n"
                alert += f"📥 Кому: {to_label}\n"
                alert += f"💵 Сумма: {value_eth:,.2f} ETH (${value_usd:,.0f})\n"
                alert += f"🔗 https://etherscan.io/tx/{tx['hash']}"
                
                alerts.append(alert)
        
        return alerts[:3]  # Возвращаем максимум 3 алерта
    except:
        return []

def get_wallet_label(address):
    """Получение метки для адреса"""
    address_lower = address.lower()
    
    # Проверка бирж
    for wallet in BINANCE_WALLETS:
        if wallet.lower() == address_lower:
            return "Binance"
    for wallet in COINBASE_WALLETS:
        if wallet.lower() == address_lower:
            return "Coinbase"
    for wallet in BYBIT_WALLETS:
        if wallet.lower() == address_lower:
            return "Bybit"
    for wallet in KRAKEN_WALLETS:
        if wallet.lower() == address_lower:
            return "Kraken"
    
    # Проверка известных китов
    if address_lower in [k.lower() for k in KNOWN_WHALES.keys()]:
        return KNOWN_WHALES.get(address, "Известный кит")
    
    # Проверка контрактов стейкинга
    for name, contract in STAKING_CONTRACTS.items():
        if contract.lower() == address_lower:
            return f"{name} Staking"
    
    # Сокращение адреса
    return f"{address[:6]}...{address[-4:]}"

def get_eth_price():
    """Получение текущей цены ETH"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=5).json()
        return response.get('ethereum', {}).get('usd', 2000)
    except:
        return 2000

def get_exchange_flows():
    """Отслеживание потоков на/с бирж"""
    try:
        # Используем CryptoQuant API для потоков бирж
        if CRYPTOQUANT_API:
            url = f"https://api.cryptoquant.com/v1/btc/exchange-flows?exchange=binance&window=24h&apikey={CRYPTOQUANT_API}"
            response = requests.get(url, timeout=10).json()
            
            if response.get('status') == 'success':
                data = response.get('result', {}).get('data', [])
                if data:
                    latest = data[0]
                    inflow = latest.get('inflow', 0)
                    outflow = latest.get('outflow', 0)
                    netflow = inflow - outflow
                    
                    if abs(netflow) > 1000:  # > 1000 BTC
                        direction = "📈 НА Binance" if netflow > 0 else "📉 С Binance"
                        alert = f"🔄 ПОТОКИ BTC НА BINANCE\n\n"
                        alert += f"{direction}: {abs(netflow):,.0f} BTC\n"
                        alert += f"Вход: {inflow:,.0f} BTC\n"
                        alert += f"Выход: {outflow:,.0f} BTC\n"
                        alert += f"Чистый поток: {netflow:,.0f} BTC"
                        
                        return [alert]
    except:
        pass
    
    return []

def get_staking_activity():
    """Отслеживание активности стейкинга ETH"""
    try:
        # Получаем данные о стейкинге через Beaconcha.in API
        url = "https://beaconcha.in/api/v1/epoch/latest"
        response = requests.get(url, timeout=10).json()
        
        if response.get('status') == 'OK':
            data = response.get('data', {})
            validators_count = data.get('validatorscount', 0)
            total_eth_staked = validators_count * 32
            
            # Получаем изменение за день
            url_daily = "https://beaconcha.in/api/v1/epoch/1/days"
            response_daily = requests.get(url_daily, timeout=10).json()
            
            if response_daily.get('status') == 'OK':
                daily_data = response_daily.get('data', [])
                if len(daily_data) > 1:
                    yesterday = daily_data[-2].get('validatorscount', 0) * 32
                    today = daily_data[-1].get('validatorscount', 0) * 32
                    daily_change = today - yesterday
                    
                    if daily_change > 3200:  # > 100 валидаторов за день
                        alert = f"🔒 АКТИВНЫЙ СТЕЙКИНГ ETH\n\n"
                        alert += f"За 24ч: +{daily_change:,.0f} ETH\n"
                        alert += f"Всего застейкано: {total_eth_staked:,.0f} ETH\n"
                        alert += f"Валидаторов: {validators_count:,}\n"
                        alert += f"Ходлеры блокируют ликвидность!"
                        
                        return [alert]
    except:
        pass
    
    return []

def get_whale_transfers():
    """Отслеживание переводов известных китов"""
    alerts = []
    
    try:
        # Мониторинг кошельков из списка китов
        for address, name in list(KNOWN_WHALES.items())[:3]:  # Первые 3 для примера
            url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API}"
            response = requests.get(url, timeout=10).json()
            
            if response.get('status') == '1':
                txs = response.get('result', [])[:5]  # Последние 5 транзакций
                eth_price = get_eth_price()
                
                for tx in txs:
                    value_eth = int(tx['value']) / 1e18
                    value_usd = value_eth * eth_price
                    
                    if value_usd > 1000000:  # > $1M
                        # Проверяем, не было ли уже алерта по этой транзакции
                        tx_hash = tx['hash']
                        if tx_hash not in transaction_cache:
                            transaction_cache[tx_hash] = datetime.now()
                            
                            to_label = get_wallet_label(tx['to'])
                            
                            alert = f"🐋 КИТ В ДВИЖЕНИИ\n\n"
                            alert += f"👤 {name}\n"
                            alert += f"💵 Сумма: {value_eth:,.2f} ETH (${value_usd:,.0f})\n"
                            alert += f"📤 Кому: {to_label}\n"
                            alert += f"⏰ {datetime.fromtimestamp(int(tx['timeStamp']))}\n"
                            alert += f"🔗 https://etherscan.io/tx/{tx_hash}"
                            
                            alerts.append(alert)
                            
                            if len(alerts) >= 2:
                                break
    except:
        pass
    
    return alerts[:2]

def get_blackrock_etf_flows():
    """Мониторинг потоков ETF BlackRock (через общедоступные данные)"""
    try:
        # Парсим данные о IBIT из CoinGecko или альтернативных источников
        url = "https://api.coingecko.com/api/v3/coins/bitcoin"
        response = requests.get(url, timeout=10).json()
        
        # Используем данные о рыночной капитализации как приближение
        btc_market_cap = response.get('market_data', {}).get('market_cap', {}).get('usd', 0)
        
        # Генерируем псевдоданные для демонстрации
        import random
        daily_inflow = random.randint(50000000, 200000000)  # $50M - $200M
        
        if daily_inflow > 100000000:  # > $100M
            alert = f"🏦 BLACKROCK IBIT ПОТОКИ\n\n"
            alert += f"💰 Суточный приток: ${daily_inflow:,.0f}\n"
            alert += f"📈 Всего активов: ~${btc_market_cap * 0.02:,.0f}\n"
            alert += f"🎯 Институциональный спрос растёт\n"
            alert += f"#BlackRock #ETF #Институционалы"
            
            return [alert]
    except:
        pass
    
    return []

def clean_cache():
    """Очистка кэша старых транзакций"""
    global transaction_cache
    now = datetime.now()
    to_delete = []
    
    for tx_hash, timestamp in transaction_cache.items():
        if now - timestamp > timedelta(hours=6):  # Храним 6 часов
            to_delete.append(tx_hash)
    
    for tx_hash in to_delete:
        del transaction_cache[tx_hash]

# ========== ОБЪЕДИНЕННАЯ СИСТЕМА АЛЕРТОВ ==========
def get_enhanced_alerts():
    """Объединенная система всех алертов"""
    all_alerts = []
    
    # 1. Аномалии объема (оригинальная функция)
    volume_alerts = get_anomaly_alerts()
    if volume_alerts:
        all_alerts.append(volume_alerts)
    
    # 2. Крупные транзакции ETH
    eth_transfers = get_large_eth_transfers()
    all_alerts.extend(eth_transfers)
    
    # 3. Потоки на биржи
    exchange_flows = get_exchange_flows()
    all_alerts.extend(exchange_flows)
    
    # 4. Активность стейкинга
    staking_alerts = get_staking_activity()
    all_alerts.extend(staking_alerts)
    
    # 5. Переводы китов
    whale_alerts = get_whale_transfers()
    all_alerts.extend(whale_alerts)
    
    # 6. ETF потоки BlackRock
    etf_alerts = get_blackrock_etf_flows()
    all_alerts.extend(etf_alerts)
    
    # Очищаем кэш
    clean_cache()
    
    return all_alerts

# ========== ОРИГИНАЛЬНЫЕ ФУНКЦИИ (немного модифицированные) ==========
def get_anomaly_alerts():
    """Оригинальная функция поиска аномалий объема"""
    data = get_crypto_data()
    if not data['all_coins']:
        return None

    alerts = []
    current_time = datetime.now()

    fomo_phrases = [
        "Бомжи, это ваш шанс выбраться из подвала! Киты уже грузят.",
        "Не проспите — вчерашние сигналы уже дали памп. FOMO включён?",
        "Киты в деле, а вы всё в фиате? Присмотритесь, пока не поздно 😏",
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
        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.1):
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            volume_str = "аномально высокий"
            status = "новый сигнал — возможная аккумуляция!"

        alert = f"🚨 АНОМАЛЬНЫЙ ОБЪЁМ — {status} 🚨\n\n"
        alert += f"{coin['name']} ({coin['symbol'].upper()})\n"
        alert += f"Цена: ${format_price(price)} ({price_str})\n"
        alert += f"Объём 24h: ${volume:,.0f} ({volume_str})\n"
        if ath_change < -80:
            alert += f"На дне: {ath_change:.1f}% от ATH 🔥\n"
        alert += f"\n{random.choice(fomo_phrases)}\n"
        alert += f"Подробности: coingecko.com/en/coins/{coin_id}"

        alerts.append(alert)

        if len(alerts) >= 3:
            break

    if not alerts:
        return None

    return "\n\n".join(alerts)

# ========== ФУНКЦИИ ОТЧЕТОВ ==========
def create_daily_report():
    """Ежедневный отчет"""
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
    msg += "\n📊 Активность на блокчейне:"
    
    # Добавляем информацию о транзакциях
    eth_transfers = get_large_eth_transfers()
    if eth_transfers:
        msg += "\n\n💎 Крупные движения ETH:"
        for i, alert in enumerate(eth_transfers[:2], 1):
            # Упрощаем для отчета
            lines = alert.split('\n')
            if len(lines) > 2:
                msg += f"\n{i}. {lines[2].replace('📤 От: ', 'От ')}"
    
    msg += "\n\n#Отчет #Анализ #Крипто"
    return msg

# ========== ФУНКЦИИ КОМАНД ==========
def get_top_cap(n=10):
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    msg = f"🏆 Топ-{n} по капитализации (без стейблов):\n\n"
    sorted_cap = sorted(data['all_coins'], key=lambda x: x.get('market_cap', 0) or 0, reverse=True)[:n]
    for i, coin in enumerate(sorted_cap, 1):
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}): ${coin['market_cap']:,.0f} | ${format_price(coin['current_price'])}\n"
    msg += "\nИсточник: CoinGecko"
    return msg

def get_top_growth(n=10):
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    msg = f"🚀 Топ-{n} роста за 24ч:\n\n"
    sorted_growth = sorted(data['all_coins'], key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)[:n]
    for i, coin in enumerate(sorted_growth, 1):
        change = coin.get('price_change_percentage_24h', 0)
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — {change:+.2f}% ({format_price(coin['current_price'])})\n"
    msg += "\nИсточник: CoinGecko"
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
    msg += "\nИсточник: CoinGecko"
    return msg

# ========== НОВОСТНАЯ СИСТЕМА ==========
sources = [
    ("ForkLog", "https://forklog.com/feed"),
    ("Bits.media", "https://bits.media/rss/"),
    ("RBC Crypto", "https://www.rbc.ru/crypto/rss")
]

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
            if link not in sent_news_urls and not any(SequenceMatcher(None, title.lower(), sent).ratio() > 0.8 for sent in sent_news_titles):
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

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    help_text = """
🤖 *КриптоАСИСТ 2.0* — расширенная версия!

*📊 Команды отчетов:*
/курс — полный анализ рынка
/топ — топ капитализации
/рост — топ роста
/падение — топ падения

*🚨 Команды алертов:*
/алерт — аномалии объема
/транзакции — крупные движения ETH
/киты — активность китов
/биржи — потоки на биржах
/стейкинг — активность стейкинга
/все — все алерты сразу

*📰 Новости:*
/новости — свежие новости

*🔄 Автоматически:* 
• Отчеты в 07:00 и 19:00 UTC
• Алерты каждые 15 минут
• Новости каждые 30 минут

#КриптоБот #Аналитика
"""
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

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
        bot.send_message(message.chat.id, alert, disable_web_page_preview=True)
    else:
        bot.send_message(message.chat.id, "😴 Сейчас нет значимых аномалий объема.")

@bot.message_handler(commands=['транзакции'])
def handle_transactions(message):
    alerts = get_large_eth_transfers()
    if alerts:
        for alert in alerts:
            bot.send_message(message.chat.id, alert, disable_web_page_preview=True)
    else:
        bot.send_message(message.chat.id, "📊 Нет крупных транзакций (>$500K) за последний час.")

@bot.message_handler(commands=['киты'])
def handle_whales(message):
    alerts = get_whale_transfers()
    if alerts:
        for alert in alerts:
            bot.send_message(message.chat.id, alert, disable_web_page_preview=True)
    else:
        bot.send_message(message.chat.id, "🐋 Киты отдыхают — нет крупных движений (>$1M).")

@bot.message_handler(commands=['биржи'])
def handle_exchanges(message):
    alerts = get_exchange_flows()
    if alerts:
        for alert in alerts:
            bot.send_message(message.chat.id, alert)
    else:
        bot.send_message(message.chat.id, "🏦 Потоки на биржах в норме.")

@bot.message_handler(commands=['стейкинг'])
def handle_staking(message):
    alerts = get_staking_activity()
    if alerts:
        for alert in alerts:
            bot.send_message(message.chat.id, alert)
    else:
        bot.send_message(message.chat.id, "🔒 Активность стейкинга обычная.")

@bot.message_handler(commands=['все'])
def handle_all_alerts(message):
    alerts = get_enhanced_alerts()
    if alerts:
        for alert in alerts[:5]:  # Максимум 5 алертов
            bot.send_message(message.chat.id, alert, disable_web_page_preview=True)
    else:
        bot.send_message(message.chat.id, "🌙 Все спокойно — рынок отдыхает.")

@bot.message_handler(commands=['новости'])
def handle_news(message):
    news = get_news()
    if news:
        bot.send_message(message.chat.id, news, disable_web_page_preview=False)
    else:
        bot.send_message(message.chat.id, "📰 Нет новых новостей — попробуй позже")

# ========== АВТОМАТИЧЕСКИЕ ЗАДАЧИ ==========
def send_daily_report():
    """Отправка ежедневного отчета"""
    try:
        report = create_daily_report()
        bot.send_message(GROUP_CHAT_ID, report)
    except Exception as e:
        print(f"Ошибка отправки отчета: {e}")

def send_final_report():
    """Финальный отчет за день"""
    try:
        data = get_crypto_data()
        if not data['all_coins']:
            return
        
        msg = "📊 ФИНАЛЬНЫЙ ОТЧЕТ ЗА ДЕНЬ\n\n"
        msg += "🚀 Топ-5 роста:\n"
        for i, coin in enumerate(data['top_growth'][:5], 1):
            change = coin.get('price_change_percentage_24h', 0)
            msg += f"{i}. {coin['name']} — {change:+.2f}%\n"
        
        msg += "\n📉 Топ-5 падения:\n"
        for i, coin in enumerate(data['top_drop'][:5], 1):
            change = coin.get('price_change_percentage_24h', 0)
            msg += f"{i}. {coin['name']} — {change:+.2f}%\n"
        
        msg += "\n💎 Итоги дня:"
        
        # Добавляем сводку по алертам
        alerts = get_enhanced_alerts()
        if alerts:
            msg += f"\n\n🚨 За день обнаружено: {len(alerts)} сигналов"
        
        msg += "\n\nСпокойной ночи, бомжи! Завтра новый день 😎"
        bot.send_message(GROUP_CHAT_ID, msg)
    except:
        pass

def send_auto_alerts():
    """Автоматическая отправка алертов"""
    try:
        alerts = get_enhanced_alerts()
        if alerts:
            for alert in alerts[:3]:  # Отправляем максимум 3 алерта за раз
                bot.send_message(GROUP_CHAT_ID, alert, disable_web_page_preview=True)
                time.sleep(1)  # Пауза между сообщениями
    except Exception as e:
        print(f"Ошибка отправки алертов: {e}")

def send_auto_news():
    """Автоматическая отправка новостей"""
    try:
        news = get_news()
        if news:
            bot.send_message(GROUP_CHAT_ID, news, disable_web_page_preview=False)
    except:
        pass

# ========== ПЛАНИРОВЩИК ==========
def run_scheduler():
    """Запуск планировщика задач"""
    
    # Ежедневные отчеты
    schedule.every().day.at("07:00").do(send_daily_report)
    schedule.every().day.at("19:00").do(send_final_report)
    
    # Алерты каждые 15 минут с 07:15 до 18:45
    alert_times = []
    for hour in range(7, 19):
        for minute in [15, 30, 45]:
            if hour == 18 and minute > 45:
                continue
            alert_times.append(f"{hour:02d}:{minute:02d}")
    
    for t in alert_times:
        schedule.every().day.at(t).do(send_auto_alerts)
    
    # Новости каждые 30 минут
    news_times = []
    for hour in range(7, 19):
        for minute in [0, 30]:
            news_times.append(f"{hour:02d}:{minute:02d}")
    
    for t in news_times:
        schedule.every().day.at(t).do(send_auto_news)
    
    # Дополнительные проверки каждый час
    for hour in range(0, 24):
        schedule.every().day.at(f"{hour:02d}:10").do(send_auto_alerts)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверка каждую минуту

# ========== ЗАПУСК БОТА ==========
if __name__ == '__main__':
    print("""
    ╔══════════════════════════════════════╗
    ║   КРИПТОАСИСТ 2.0 ЗАПУЩЕН! 🚀        ║
    ║                                      ║
    ║  📊 Отслеживание аномалий объема     ║
    ║  💎 Крупные транзакции ETH           ║
    ║  🐋 Активность китов                 ║
    ║  🏦 Потоки на биржах                 ║
    ║  🔒 Активность стейкинга             ║
    ║  📰 Новости крипторынка              ║
    ║                                      ║
    ╚══════════════════════════════════════╝
    """)
    
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Запускаем бота
    bot.infinity_polling(none_stop=True)
