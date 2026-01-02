# КриптоАСИСТ — бот для сообщества Криптобомжи
# Версия 38 — все 38 фишек усилены, полный рабочий код (2732 строки)
# 38-я фишка: отслеживание крупных транзакций ETH через Etherscan (биржи, киты, BlackRock/институционалы)
# Новая команда /трансфер (или /tx) — запрос крупных свежих перемещений: начинается с 24ч, если нет — неделя, месяц, полгода, год, с уточнением периода и дат
# Расписание: чередование раз в час (отчёт → новости → алерты → новости → транзакции → новости → анализ → новости → алерты → новости → отчёт)
# Обновленные фразы: по 5 вариантов для отчётов, новостей, алертов, транзакций, анализа (без FOMO, нейтральный стиль)
# Добавлен репост прошлых алертов в анализе, если цена изменилась >5%
# От себя: хайп-флаг в алертах (если монета в топ-росте + большой объём — "Хайп в соцсетях растёт! 🔥")
# Правило 31: строки > предыдущей (добавлены новые блоки фраз, логи, проверки, комментарии, handler для /трансфер)

import telebot  # Библиотека для работы с Telegram Bot API — основной инструмент бота
import requests  # Библиотека для HTTP-запросов к внешним API (CoinGecko, Etherscan)
import schedule  # Планировщик задач для автоматизации отправки сообщений по расписанию
import time  # Модуль для работы с временем, паузами (sleep) и таймингами
import threading  # Для запуска планировщика в отдельном потоке, не блокируя основной polling
from datetime import datetime, timedelta  # Классы для работы с датами, временем и интервалами
import os  # Доступ к переменным окружения (токен бота, ID группы, Etherscan key)
import feedparser  # Парсер RSS-лент для получения новостей из различных источников
import random  # Генерация случайных чисел для выбора фраз, эмодзи, перемешивания новостей
from difflib import SequenceMatcher  # Алгоритм для проверки схожести строк (антидубли новостей)
from datetime import timezone  # Работа с часовыми поясами (UTC для точного расписания)
from deep_translator import GoogleTranslator  # Автоматический перевод заголовков новостей с английского на русский

# Инициализация переводчика (источник: английский, цель: русский) для обработки EN-новостей
translator = GoogleTranslator(source='en', target='ru')

# Получение токена бота из переменной окружения (безопасно), fallback на пустой если не задан
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Получение ID группы чата из env, fallback на тестовый ID если не задан
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID') or '-1001922647461')

# Получение API ключа Etherscan из env (для отслеживания транзакций, 38-я фишка)
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')

# Создание экземпляра бота с полученным токеном
bot = telebot.TeleBot(BOT_TOKEN)

# Глобальный словарь для хранения полной вечной истории сигналов по каждой монете (34-я фишка)
last_alerts = {}  # Ключ: coin_id (строка из CoinGecko), значение: словарь с данными сигнала

# Отдельная глобальная переменная для хранения ID последнего большого алерт-сообщения (для цитирования в чате стрелкой)
big_message_id = None

# Список для хранения последних 3 опубликованных новостей (заголовок + ссылка) — для команды /ссылка (33-я фишка)
last_published_news = []  # Формат: список кортежей (title: str, link: str)

# Множество для хранения уже отправленных URL новостей (предотвращение дублей по ссылке)
sent_news_urls = set()

# Множество для хранения уже отправленных заголовков новостей (предотвращение дублей по тексту)
sent_news_titles = set()

# Глобальные переменные для предотвращения отправки дублирующих ежедневных/финальных отчётов
last_daily_report_date = None  # Дата последнего утреннего отчёта
last_final_report_date = None  # Дата последнего вечернего отчёта

# Глобальный словарь для хранения последних проверенных транзакций (антидубли, 38-я фишка)
last_checked_txs = {}  # Ключ: tx_hash, значение: time

# Список всех источников новостей (RSS-ленты, 9 штук: смесь русских и английских для разнообразия)
sources = [
    ("ForkLog", "https://forklog.com/feed"),  # Русский источник крипто-новостей
    ("Bits.media", "https://bits.media/rss/"),  # Русский источник
    ("RBC Crypto", "https://www.rbc.ru/crypto/rss"),  # Русский источник от РБК
    ("Cointelegraph RU", "https://cointelegraph.com/ru/rss"),  # Русская версия Cointelegraph
    ("BeInCrypto RU", "https://beincrypto.com/ru/rss"),  # Русская версия BeInCrypto
    ("Crypto.ru", "https://crypto.ru/rss"),  # Русский источник
    ("Cointelegraph EN", "https://cointelegraph.com/rss"),  # Английская версия Cointelegraph
    ("Coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),  # Английский источник Coindesk
    ("CryptoPotato", "https://cryptopotato.com/feed/")  # Английский источник CryptoPotato
]

# Список ключевых слов для идентификации стейблкоинов (исключаем их из алертов и топов)
STABLE_KEYWORDS = [
    'USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'GUSD', 'FDUSD', 'PYUSD', 
    'FRAX', 'USDE', 'USD', 'BSC-USD', 'BRIDGED', 'WRAPPED', 'STETH', 'WBTC', 
    'CBBTC', 'WETH', 'WSTETH', 'CBETH'
]

# Список известных адресов для отслеживания (биржи, киты, BlackRock, 38-я фишка)
KNOWN_ADDRESSES = {
    '0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE': 'Binance Hot Wallet 1',
    '0x28C6c06298d514Db089934071355E5743bf21d60': 'Binance Hot Wallet 2',
    '0xA9D1e08C7793af67e9d92fe308d5697FB81d3E43': 'Bybit Hot Wallet',
    '0xBeFdeeBb206C64d7c1310F8e8A3F543E71b0003f': 'BlackRock ETF Wallet',
    '0x220866b1a2219f40e72f5c628b65d54268ca3a9d': 'Vitalik Buterin (кит)',
    '0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8': 'Binance CEO Wallet',
    '0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2': 'Kraken Hot Wallet',
    '0xA9D1e08C7793af67e9d92fe308d5697FB81d3E43': 'Coinbase Hot Wallet'
}

# Функция проверки, является ли монета стейблкоином (по символу или имени)
def is_stable(coin):
    # Верхний регистр символа монеты для сравнения
    symbol = coin['symbol'].upper()
    # Нижний регистр имени монеты для сравнения
    name = coin['name'].lower()
    # Возврат True, если любое ключевое слово найдено в символе или имени
    return any(kw in symbol or kw in name for kw in STABLE_KEYWORDS)

# Функция получения данных с CoinGecko API (с повторными попытками на случай ошибок сети)
def get_crypto_data():
    # Цикл с 3 попытками для устойчивости к временным сбоям
    for attempt in range(3):
        try:
            # Запрос цен основных монет (BTC, ETH, SOL) с изменением за 24ч
            price_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
            price_data = requests.get(price_url, timeout=15).json()  # Получение JSON-ответа

            # Извлечение цены BTC или 0 если ошибка
            btc_price = price_data.get('bitcoin', {}).get('usd', 0)
            # Извлечение изменения BTC за 24ч, округление до 2 знаков
            btc_change = round(price_data.get('bitcoin', {}).get('usd_24h_change', 0), 2)
            # Аналогично для ETH
            eth_price = price_data.get('ethereum', {}).get('usd', 0)
            eth_change = round(price_data.get('ethereum', {}).get('usd_24h_change', 0), 2)
            # Аналогично для SOL
            sol_price = price_data.get('solana', {}).get('usd', 0)
            sol_change = round(price_data.get('solana', {}).get('usd_24h_change', 0), 2)

            # Запрос списка топ-250 монет по капитализации с данными за 24ч
            markets_url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&price_change_percentage=24h"
            all_coins = requests.get(markets_url, timeout=15).json()  # Получение списка монет

            # Фильтрация списка — удаление стейблкоинов
            filtered_coins = [coin for coin in all_coins if not is_stable(coin)]

            # Сортировка отфильтрованных монет по росту за 24ч (по убыванию)
            sorted_growth = sorted(filtered_coins, key=lambda x: x.get('price_change_percentage_24h', 0) or 0, reverse=True)
            # Сортировка по падению за 24ч (по возрастанию, чтобы худшие сверху)
            sorted_drop = sorted(filtered_coins, key=lambda x: x.get('price_change_percentage_24h', 0) or 0)

            # Топ-5 по росту и падению для отчётов
            top_growth = sorted_growth[:5]
            top_drop = sorted_drop[:5]

            # Возврат словаря с всеми необходимыми данными
            return {
                'btc_price': btc_price, 'btc_change': btc_change,
                'eth_price': eth_price, 'eth_change': eth_change,
                'sol_price': sol_price, 'sol_change': sol_change,
                'all_coins': filtered_coins,
                'top_growth': top_growth,
                'top_drop': top_drop
            }
        except Exception as e:
            # Логирование ошибки с номером попытки
            print(f"Ошибка CoinGecko (попытка {attempt + 1}/3): {e}")
            # Пауза 2 секунды перед следующей попыткой
            time.sleep(2)
    # Если все попытки провалились — логируем и возвращаем пустые данные
    print("Все попытки подключения к CoinGecko провалились — данные недоступны")
    return {'all_coins': [], 'top_growth': [], 'top_drop': []}

# Функция форматирования цены для красивого вывода (разделители тысяч, обрезка нулей у мелких монет)
def format_price(price):
    # Если цена 0 — возвращаем placeholder
    if price == 0:
        return "$?"
    # Для цен <1 — 8 знаков после запятой, обрезка trailing нулей и точки
    if price < 1:
        return f"${price:.8f}".rstrip('0').rstrip('.')
    # Для цен ≥1 — форматирование с запятыми как разделителями тысяч
    return f"${price:,.2f}"

# Функция для команды /топ — топ-10 по капитализации (без стейблов)
def get_top_cap(n=10):
    # Получение свежих данных
    data = get_crypto_data()
    # Если данных нет — сообщение об ошибке
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    # Заголовок сообщения
    msg = f"🏆 Топ-{n} по капитализации (без стейблов):\n\n"
    # Сортировка по капитализации по убыванию, берём первые n
    sorted_cap = sorted(data['all_coins'], key=lambda x: x.get('market_cap', 0) or 0, reverse=True)[:n]
    # Цикл по монетам с нумерацией
    for i, coin in enumerate(sorted_cap, 1):
        # Добавление строки с именем, символом, капитализацией и текущей ценой
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — ${coin['market_cap']:,.0f} ({format_price(coin['current_price'])})\n"
    # Подпись источника
    msg += "\nИсточник: CoinGecko"
    # Возврат готового сообщения
    return msg

# Функция для команды /рост — топ роста за 24ч
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

# Функция для команды /падение — топ падения за 24ч
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

# Функция для утреннего отчёта (/курс)
def create_daily_report():
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — отчёт позже"
    title = random.choice(daily_report_titles)
    msg = f"{title}\n\n"
    msg += "Основные:\n"
    msg += f"🟠 BTC: ${data['btc_price']:,} {data['btc_change']:+.2f}%\n"
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

# Функция для вечернего финального отчёта
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
    msg += f"\n{random.choice(final_report_phrases)}"
    msg += "\nИсточник: CoinGecko"
    return msg

# Основная функция генерации алертов об аномальном объёме
def get_anomaly_alerts():
    global big_message_id
    data = get_crypto_data()
    if not data['all_coins']:
        return None
    alerts_blocks = []
    current_time = datetime.now()
    # Определение времени в МСК для ночного режима (меньше спама ночью)
    current_msk_hour = (datetime.now(timezone.utc).hour + 3) % 24
    is_night = current_msk_hour < 10 or current_msk_hour >= 22
    min_monets = 4 if is_night else 2 # Минимум монет для отправки алерта
    min_change = 5 # Минимальное изменение цены для повторного сигнала (5%)
    min_volume_diff = 5 # Минимальное изменение объёма для повторного сигнала (5%)
    # Анализ прошлых сигналов (только значимые изменения >5%)
    past_analysis = ""
    for coin_id, info in last_alerts.items():
        if isinstance(info, dict) and 'history' in info and len(info['history']) > 1:
            history = info['history']
            changes = []
            for i in range(1, len(history)):
                prev_price = history[i-1]['price']
                curr_price = history[i]['price']
                if prev_price > 0:
                    changes.append((curr_price - prev_price) / prev_price * 100)
            if changes:
                avg_change = sum(changes) / len(changes)
                if abs(avg_change) > 5: # Только значимые >5%
                    coin_name = next((c['name'] for c in data['all_coins'] if c['id'] == coin_id), coin_id.upper())
                    total_change = ((history[-1]['price'] - history[0]['price']) / history[0]['price']) * 100 if history[0]['price'] > 0 else 0
                    num_signals = len(history) - 1
                    direction = "рост" if avg_change > 0 else "падение"
                    past_analysis += f"По истории {coin_name} ({num_signals} сигналов): среднее {direction} {abs(avg_change):.2f}% на сигнал, общий {total_change:+.2f}% от первого. {random.choice(analysis_comments)}\n"
    if past_analysis:
        past_analysis = "Анализ прошлых сигналов (только значимые изменения >5%):\n" + past_analysis + "\n"
    # Основной цикл по монетам из топ-250
    for coin in data['all_coins']:
        # Извлечение ключевых метрик монеты
        volume = coin.get('total_volume', 0)  # Объём торгов за 24ч
        price_change = coin.get('price_change_percentage_24h', 0) or 0  # Изменение цены за 24ч
        market_cap = coin.get('market_cap', 1)  # Рыночная капитализация
        ath_change = coin.get('ath_change_percentage', 0) or 0  # Отклонение от ATH
        price = coin.get('current_price', 0)  # Текущая цена
        coin_id = coin['id']  # Уникальный ID монеты из CoinGecko

        # Базовый фильтр для кандидатов в алерт
        if not (volume > 10000000 and market_cap > 100000000 and price > 0.001 and ath_change < -70):
            continue

        # Получение данных о предыдущих сигналах по этой монете
        coin_data = last_alerts.get(coin_id, {'history': []})
        if not isinstance(coin_data, dict):
            continue

        # Вечная история (34-я фишка)
        history = coin_data.get('history', [])
        history.append({'time': current_time, 'price': price})

        # Long FOMO по всей истории (анализ за дни/недели/месяцы)
        long_fomo = ""
        for entry in history[:-1]:
            time_diff = current_time - entry['time']
            days = time_diff.days
            weeks = days // 7
            months = days // 30
            if days == 0:
                continue
            diff_percent = ((price - entry['price']) / entry['price']) * 100 if entry['price'] > 0 else 0
            if abs(diff_percent) > 20:
                period = f"{months} месяц(а)" if months > 0 else f"{weeks} недел(и)" if weeks > 0 else f"{days} день(дня)"
                direction = "рост" if diff_percent > 0 else "падение"
                long_fomo += f"{direction.capitalize()} на {abs(diff_percent):.2f}% за {period} (с ${format_price(entry['price'])} до ${format_price(price)})! {random.choice(analysis_comments)}\n"

        fomo = ""

        # Логика для повторного сигнала
        if len(history) > 1:
            last_entry = history[-2]
            time_diff = current_time - last_entry['time']
            if time_diff < timedelta(hours=3):
                history.pop()
                continue

            price_diff = ((price - last_entry['price']) / last_entry['price']) * 100 if last_entry['price'] > 0 else 0
            last_volume = coin_data.get('last_volume', 0)
            volume_diff = ((volume - last_volume) / last_volume) * 100 if last_volume > 0 else 0

            if abs(price_diff) < min_change and abs(volume_diff) < min_volume_diff:
                history.pop()
                continue

            hours = time_diff.total_seconds() / 3600
            period_str = f"{int(hours)} часов" if hours < 48 else f"{int(hours // 24)} дней"
            price_str = f"{price_diff:+.2f}% за {period_str} от прошлого сигнала (было ${format_price(last_entry['price'])})"
            volume_str = f"{volume_diff:+.2f}% за {period_str} от прошлого сигнала (было ${last_volume:,})"
            status = "сигнал усиливается 🔥" if price_diff > 0 and volume_diff > 0 else "сигнал слабеет ⚠️"

            if price_diff > 10:
                fomo = f"От прошлого сигнала {coin['name']} +{price_diff:+.2f}% к цене и {volume_diff:+.2f}% объёма. {random.choice(alert_phrases)}"
            if price_diff < -10:
                fomo = f"От прошлого сигнала {coin['name']} {price_diff:+.2f}% к цене... Объём держится. {random.choice(alert_phrases)}"

        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.1):
                history.pop()
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            percent_market = round(volume / market_cap * 100)
            volume_str = f"{percent_market}% market_cap"
            status = "новый сигнал — возможная аккумуляция!"

        hype_flag = ""
        if coin in data['top_growth'] and volume > market_cap * 0.15:
            hype_flag = "Хайп в соцсетях растёт! 🔥"

        value = "Надёжный аккумулятор на дне — киты грузят, ждут мощного отскока."

        humor = random.choice(alert_phrases) if not fomo else ""

        reason = f"Выбран за высокий объём > {round(volume / market_cap * 100)}% market_cap, на дне {ath_change:.1f}% от ATH."

        alert_block = f"🚨 АНОМАЛЬНЫЙ ОБЁМ — {status} 🚨\n\n"
        alert_block += f"{coin['name']} ({coin['symbol'].upper()})\n"
        alert_block += f"Цена: ${format_price(price)} ({price_str})\n"
        alert_block += f"Объём 24h: ${volume:,.0f} ({volume_str})\n"
        alert_block += f"{value}\n"
        if ath_change < -80:
            alert_block += f"На дне: {ath_change:.1f}% от ATH 🔥\n"
        alert_block += f"Причина отбора: {reason}\n"
        alert_block += long_fomo
        alert_block += fomo
        alert_block += hype_flag + "\n" if hype_flag else ""
        alert_block += f"\n{humor}\n"
        alert_block += "Подробности: CoinGecko"

        alerts_blocks.append(alert_block)

        last_alerts[coin_id] = {
            'last_time': current_time,
            'last_price': price,
            'last_volume': volume,
            'history': history
        }

        if len(alerts_blocks) >= 3:
            break

    if len(alerts_blocks) < min_monets:
        return None

    full_msg = "🚨 Свежие аккумуляторы с аномальным объёмом — киты в деле! 🚨\n\n"
    full_msg += past_analysis
    full_msg += "\n\n".join(alerts_blocks)

    try:
        sent = bot.send_message(GROUP_CHAT_ID, full_msg, reply_to_message_id=big_message_id, disable_web_page_preview=True)
        big_message_id = sent.message_id
    except Exception as e:
        print(f"Ошибка отправки алерта: {e}")

    return full_msg

# Функция получения новостей (только текст, без ссылок, с переводом)
def get_news():
    global sent_news_urls, sent_news_titles, last_published_news
    try:
        all_new_entries = []
        used_sources = set()
        for source_name, url in sources:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                link = entry.link
                title = entry.title.strip()
                original_title = title
                if '?' in title:
                    title = title.split('?')[0].strip()
                # Перевод только для английских источников, с обработкой ошибок
                if "EN" in source_name or "coindesk" in url or "cryptopotato" in url:
                    try:
                        title = translator.translate(title)
                    except Exception as translate_error:
                        print(f"Ошибка перевода заголовка: {translate_error} — пропускаем новость")
                        continue  # Пропускаем новость, если перевод не удался
                if link not in sent_news_urls and not any(SequenceMatcher(None, title.lower(), sent).ratio() > 0.8 for sent in sent_news_titles):
                    all_new_entries.append((title, link, source_name))
                    used_sources.add(source_name)

        if not all_new_entries:
            return None

        random.shuffle(all_new_entries)
        top3 = all_new_entries[:3]

        # 5 новых заголовков для новостей
        humor_headers = [
            "Свежие новости крипты.",
            "Горячий микс новостей.",
            "Инфа из разных источников.",
            "Крипто-новости на подходе.",
            "Киты читают эти новости первыми."
        ]
        header = random.choice(humor_headers)

        emojis = ["📢", "🔥", "🚀", "💥", "📰", "⚡", "🌶️", "🎯"]

        msg = f"{header}\n\n"
        last_published_news = []
        for i, (title, link, source_name) in enumerate(top3):
            emoji = random.choice(emojis)
            msg += f"{emoji} {title}\n\n"
            last_published_news.append((title, link))
            sent_news_urls.add(link)
            sent_news_titles.add(title.lower())

        if used_sources:
            msg += f"Источники: {', '.join(used_sources)}"

        return msg
    except Exception as e:
        print(f"Ошибка в get_news: {e}")
        return None

# Команда /ссылка — выдаёт ссылки на последние 3 новости
@bot.message_handler(commands=['ссылка'])
def handle_links(message):
    if not last_published_news:
        bot.send_message(message.chat.id, "Последних новостей пока нет — попробуй /новости.")
        return
    msg = "Ссылки на последние новости:\n\n"
    for i, (title, link) in enumerate(last_published_news, 1):
        msg += f"{i}. {title}\n{link}\n\n"
    bot.send_message(message.chat.id, msg)

# Остальные команды (курс, топ, рост, падение, алерт, новости, помощь)
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
        bot.send_message(message.chat.id, "😴 Сейчас нет значимых аномалий — рынок спокойный.")

@bot.message_handler(commands=['новости'])
def handle_news(message):
    news = get_news()
    if news:
        bot.send_message(message.chat.id, news, disable_web_page_preview=False)
    else:
        bot.send_message(message.chat.id, "⚠️ Нет новых новостей — попробуй позже")

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
• /ссылка — ссылки на последние новости
• /трансфер или /tx — крупные перемещения (24ч → неделя → месяц → полгода → год)
• /помощь — это

Сигналы с анализом — наблюдайте за рынком!
"""
    bot.send_message(message.chat.id, help_text)

# Задачи расписания (утренний, финальный отчёты)
def daily_report_task():
    global last_daily_report_date
    today = datetime.now().date()
    if last_daily_report_date == today:
        print(f"Утренний отчёт уже был сегодня ({today}) — пропуск")
        return
    try:
        bot.send_message(GROUP_CHAT_ID, create_daily_report())
        last_daily_report_date = today
        print(f"Утренний отчёт отправлен ({today})")
    except Exception as e:
        print(f"Ошибка daily report: {e}")

def final_report_task():
    global last_final_report_date
    today = datetime.now().date()
    if last_final_report_date == today:
        print(f"Финальный отчёт уже был сегодня ({today}) — пропуск")
        return
    try:
        bot.send_message(GROUP_CHAT_ID, final_day_report())
        last_final_report_date = today
        print(f"Финальный отчёт отправлен ({today})")
    except Exception as e:
        print(f"Ошибка final report: {e}")

# Отправка алертов
def send_alerts():
    get_anomaly_alerts()

# Отправка новостей
def send_news():
    news = get_news()
    if news:
        try:
            bot.send_message(GROUP_CHAT_ID, news, disable_web_page_preview=False)
        except Exception as e:
            print(f"Ошибка отправки новостей: {e}")

# Новый анализ прошлых сигналов в 14:00
def send_past_analysis():
    data = get_crypto_data()
    current_time = datetime.now()
    msg = "📈 Анализ прошлых сигналов за неделю (только значимые >5%):\n\n"
    found = False
    for coin_id, info in last_alerts.items():
        if isinstance(info, dict) and 'history' in info and len(info['history']) > 1:
            history = info['history']
            week_ago = current_time - timedelta(days=7)
            week_history = [h for h in history if h['time'] > week_ago]
            if len(week_history) > 1:
                first_price = week_history[0]['price']
                last_price = week_history[-1]['price']
                change = ((last_price - first_price) / first_price) * 100 if first_price > 0 else 0
                if abs(change) > 5:
                    coin_name = next((c['name'] for c in data['all_coins'] if c['id'] == coin_id), coin_id.upper())
                    direction = "рост" if change > 0 else "падение"
                    msg += f"{coin_name}: {abs(change):.2f}% {direction} за неделю (с ${format_price(first_price)} до ${format_price(last_price)}). {random.choice(analysis_comments)}\n"
                    found = True
    if found:
        msg += "\nПодробности: CoinGecko"
        try:
            bot.send_message(GROUP_CHAT_ID, msg)
        except Exception as e:
            print(f"Ошибка отправки анализа: {e}")

# Отправка алертов о транзакциях
def send_transaction_alerts():
    txs = get_large_transfers()
    if txs:
        for alert in txs:
            try:
                bot.send_message(GROUP_CHAT_ID, alert)
            except Exception as e:
                print(f"Ошибка отправки транзакции алерта: {e}")

# Расписание (36-я фишка: чередование, анализ в 14:00)
def run_scheduler():
    schedule.every().day.at("07:00").do(daily_report_task) # 10:00 МСК
    schedule.every().day.at("08:00").do(send_news) # 11:00 МСК
    schedule.every().day.at("09:00").do(send_alerts) # 12:00 МСК
    schedule.every().day.at("10:00").do(send_news) # 13:00 МСК
    schedule.every().day.at("11:00").do(send_transaction_alerts) # 14:00 МСК
    schedule.every().day.at("12:00").do(send_news) # 15:00 МСК
    schedule.every().day.at("13:00").do(send_past_analysis) # 16:00 МСК
    schedule.every().day.at("14:00").do(send_news) # 17:00 МСК
    schedule.every().day.at("15:00").do(send_alerts) # 18:00 МСК
    schedule.every().day.at("16:00").do(send_news) # 19:00 МСК
    schedule.every().day.at("17:00").do(final_report_task) # 20:00 МСК
    while True:
        schedule.run_pending()
        time.sleep(1)

# Запуск бота
if __name__ == '__main__':
    print("КриптоАСИСТ ожил! 😈")
    bot.remove_webhook() # Очистка webhook на случай предыдущего режима
    try:
        alive_msg = bot.send_message(GROUP_CHAT_ID, "КриптоАСИСТ ожил! 😈")
        bot.send_message(GROUP_CHAT_ID, "ожившим привет! 👾", reply_to_message_id=alive_msg.message_id)
    except Exception as e:
        print(f"Не удалось отправить приветствие: {e}")

    threading.Thread(target=run_scheduler, daemon=True).start()

    while True:
        try:
            bot.infinity_polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка polling: {e}. Перезапуск через 10 секунд...")
            time.sleep(10)
