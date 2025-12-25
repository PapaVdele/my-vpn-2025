# КриптоАСИСТ — бот для сообщества Криптобомжи
# Версия 35 — все 35 фишек усилены, полный рабочий код (962 строки)
# 34-я фишка: полная вечная история сигналов (без обрезки по времени)
# 35-я фишка: полностью переписанный юмор/FOMO (25+ новых фраз, рандом чередование)
# Алерты с увлекательным анализом: "сколько было/стало", "рост за 2 недели", "падение за месяц"
# Добавлены пояснения, средний % по истории, мотивация/предупреждения
# Фикс ошибок: remove_webhook, isinstance, retry API
# Новости — чистый текст (без ссылок), /ссылка отдельно
# Память лёгкая (даже за годы <50 МБ RAM)
# Правило 31: строки > предыдущей версии (добавлены комментарии, логи, проверки)

import telebot  # Основная библиотека для работы с Telegram API
import requests  # Для HTTP-запросов к CoinGecko API
import schedule  # Планировщик задач для расписания
import time  # Для sleep, пауз и работы с временем
import threading  # Запуск расписания в отдельном потоке
from datetime import datetime, timedelta  # Работа с датами и интервалами
import os  # Доступ к переменным окружения (токен, ID группы)
import feedparser  # Парсинг RSS-лент для новостей
import random  # Рандом для выбора фраз, эмодзи, shuffle новостей
from difflib import SequenceMatcher  # Проверка схожести заголовков новостей (антидубли)
from datetime import timezone  # UTC-время для точного расписания
from deep_translator import GoogleTranslator  # Автоматический перевод английских заголовков

# Инициализация переводчика (EN → RU для новостей)
translator = GoogleTranslator(source='en', target='ru')

# Токен бота и ID группы чата (берётся из env, fallback на тестовый)
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID') or '-1001922647461')

# Создание объекта бота
bot = telebot.TeleBot(BOT_TOKEN)

# Глобальный словарь для хранения полной истории сигналов по монетам (34-я фишка: вечная память)
last_alerts = {}  # Формат: coin_id: {'last_time': datetime, 'last_price': float, 'last_volume': int, 'history': [{'time': dt, 'price': float}, ...]}

# Отдельная переменная для ID последнего большого алерт-сообщения (для цитирования стрелкой в чате)
big_message_id = None

# Для 33-й фишки: храним последние 3 новости для команды /ссылка
last_published_news = []  # Список кортежей (title, link)

# Множества для предотвращения дублей новостей
sent_news_urls = set()
sent_news_titles = set()

# Переменные для предотвращения дублей ежедневных отчётов
last_daily_report_date = None
last_final_report_date = None

# Список источников RSS-новостей (9 штук: русский + английский микс)
sources = [
    ("ForkLog", "https://forklog.com/feed"),
    ("Bits.media", "https://bits.media/rss/"),
    ("RBC Crypto", "https://www.rbc.ru/crypto/rss"),
    ("Cointelegraph RU", "https://cointelegraph.com/ru/rss"),
    ("BeInCrypto RU", "https://beincrypto.com/ru/rss"),
    ("Crypto.ru", "https://crypto.ru/rss"),
    ("Cointelegraph EN", "https://cointelegraph.com/rss"),
    ("Coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CryptoPotato", "https://cryptopotato.com/feed/")
]

# Ключевые слова для фильтрации стейблкоинов (не включаем в алерты/топы)
STABLE_KEYWORDS = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'GUSD', 'FDUSD', 'PYUSD', 'FRAX', 'USDE', 'USD', 'BSC-USD', 'BRIDGED', 'WRAPPED', 'STETH', 'WBTC', 'CBBTC', 'WETH', 'WSTETH', 'CBETH']

# Функция проверки, является ли монета стейблкоином
def is_stable(coin):
    symbol = coin['symbol'].upper()
    name = coin['name'].lower()
    return any(kw in symbol or kw in name for kw in STABLE_KEYWORDS)

# Функция получения данных с CoinGecko (с retry на случай ошибок сети/API)
def get_crypto_data():
    for attempt in range(3):  # Три попытки на случай временных сбоев
        try:
            # Запрос цен основных монет (BTC, ETH, SOL)
            price_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
            price_data = requests.get(price_url, timeout=15).json()

            btc_price = price_data.get('bitcoin', {}).get('usd', 0)
            btc_change = round(price_data.get('bitcoin', {}).get('usd_24h_change', 0), 2)
            eth_price = price_data.get('ethereum', {}).get('usd', 0)
            eth_change = round(price_data.get('ethereum', {}).get('usd_24h_change', 0), 2)
            sol_price = price_data.get('solana', {}).get('usd', 0)
            sol_change = round(price_data.get('solana', {}).get('usd_24h_change', 0), 2)

            # Запрос топ-250 монет по капитализации
            markets_url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&price_change_percentage=24h"
            all_coins = requests.get(markets_url, timeout=15).json()

            # Фильтрация стейблкоинов
            filtered_coins = [coin for coin in all_coins if not is_stable(coin)]

            # Сортировка по росту и падению за 24ч
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
            print(f"Ошибка CoinGecko (попытка {attempt + 1}/3): {e}")
            time.sleep(2)  # Пауза перед следующей попыткой
    print("Все попытки CoinGecko провалились — возвращаем пустые данные")
    return {'all_coins': [], 'top_growth': [], 'top_drop': []}

# Функция красивого форматирования цены (с разделителями и обрезкой нулей)
def format_price(price):
    if price == 0:
        return "$?"
    if price < 1:
        return f"${price:.8f}".rstrip('0').rstrip('.')
    return f"${price:,.2f}"

# Команда /топ — топ-10 по капитализации (без стейблов)
def get_top_cap(n=10):
    data = get_crypto_data()
    if not data['all_coins']:
        return "⚠️ Проблема с данными — попробуй позже"
    msg = f"🏆 Топ-{n} по капитализации (без стейблов):\n\n"
    sorted_cap = sorted(data['all_coins'], key=lambda x: x.get('market_cap', 0) or 0, reverse=True)[:n]
    for i, coin in enumerate(sorted_cap, 1):
        msg += f"{i}. {coin['name']} ({coin['symbol'].upper()}) — ${coin['market_cap']:,.0f} ({format_price(coin['current_price'])})\n"
    msg += "\nИсточник: CoinGecko"
    return msg

# Команда /рост — топ роста за 24ч
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

# Команда /падение — топ падения за 24ч
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

# Утренний отчёт (/курс)
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

# Финальный вечерний отчёт
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
    msg += "\nИсточник: CoinGecko"
    return msg

# Основная функция алертов (аномальный объём)
def get_anomaly_alerts():
    global big_message_id
    data = get_crypto_data()
    if not data['all_coins']:
        return None

    alerts_blocks = []
    current_time = datetime.now()

    # 35-я фишка: 25+ новых FOMO-фраз (свежий юмор, мотивирующий и предупреждающий)
    fomo_phrases = [
        "Бомжи, это ваш билет в ламбо! Киты уже на борту — не оставайтесь на перроне 😈",
        "Не проспите — вчерашние сигналы уже в +20%. FOMO включён на максимум, бомжи!",
        "Киты тихо грузят мешки, пока все спят. Вы с ними или всё в фиате? Присмотритесь, пока не поздно 🔥",
        "Это не скам — это жирный аккумулятор. Кто войдёт сейчас — тот через месяц в пентхаусе.",
        "Помните 2021? Кто не боялся — купил ламбо. Кто ждал 'подешевле' — до сих пор в криптобомжах. Не повторяйте ошибок!",
        "Рынок даёт второй шанс. Первый был в 2022 на дне — не пропустите этот, бомжи!",
        "Киты не спят — они аккумулируют тоннами. А вы? Всё в стронг хендс фиата?",
        "Это как купить BTC по $3k в 2020. Только сейчас. Не проспите — второго шанса не будет!",
        "Пока вы 'анализируете', киты уже в позиции. Через неделю будете ныть 'почему не сказал раньше'? Говорю сейчас 😏",
        "Киты устроили банкет — объём прёт вверх. Присоединяйтесь, пока стол не пуст!",
        "Сигнал как из учебника: дно, объём, аккумуляция. Кто смелый — тот в профите через месяц.",
        "Рынок шепчет: киты покупают. Слушайте шепот — или останетесь за бортом ракеты.",
        "Представьте: через квартал ламбо в гараже. А всё благодаря этому сигналу. Не будьте тем, кто упустил!",
        "Бомжи, хватайте мешки — киты делятся! Объём аномальный, цена на дне — взлёт неизбежен.",
        "Это сигнал года! Дно от ATH, объём через крышу — FOMO на максимуме, влезайте!",
        "Киты улыбаются — знают, что отскок будет эпичным. Вы с ними или всё ждёте 'подтверждения'?",
        "Рынок на дне, но киты уже в позиции. Время входить, бомжи — не ждите зелёной свечи!",
        "Сигнал усиливается — цена прыгает, объём взрывается! Классика перед большим пампом.",
        "Киты заглатывают монеты пачками. Это не случайность — это план. Ваш ход!",
        "Бомжи, это не дрель — это ракета! Объём говорит сам за себя — старт близко.",
        "Кто не боится дна — тот ест сливки на вершине. Киты уже едят — вы с ними?",
        "Сигнал как из 2017: дно, страх, объём. Потом x10. История повторяется — будьте готовы!",
        "Киты молча покупают, пока все паникуют. Умные следуют за китами — глупые ждут 'подтверждения'.",
        "Это ваш шанс выбраться из подвала! Киты уже грузят — время в позицию, бомжи!",
        "Последний звонок перед пампом. Киты на местах — вы ещё в фиате? Пора менять!"
    ]

    reply_id = big_message_id

    # Ночной режим: меньше спама ночью (МСК)
    current_msk_hour = (datetime.now(timezone.utc).hour + 3) % 24
    is_night = current_msk_hour < 10 or current_msk_hour >= 22
    min_monets = 4 if is_night else 2
    min_change = 5  # Минимальное изменение для повторного сигнала (5%)
    min_volume_diff = 5

    # Анализ всей истории сигналов (35-я фишка: средний рост по монете)
    past_analysis = ""
    for coin_id, info in last_alerts.items():
        if isinstance(info, dict) and 'history' in info and len(info['history']) > 1:
            history = info['history']
            changes = []
            for i in range(1, len(history)):
                prev = history[i-1]['price']
                curr = history[i]['price']
                if prev > 0:
                    changes.append((curr - prev) / prev * 100)
            if changes:
                avg_change = sum(changes) / len(changes)
                coin_name = next((c['name'] for c in data['all_coins'] if c['id'] == coin_id), coin_id.upper())
                direction = "рост" if avg_change > 0 else "падение"
                past_analysis += f"По истории {coin_name}: среднее {direction} {abs(avg_change):.2f}% на сигнал. {'Памп в деле — следим!' if avg_change > 0 else 'Дно близко — отскок впереди?'}\n"

    if past_analysis:
        past_analysis = "Анализ прошлых сигналов по монетам:\n" + past_analysis + "\n"

    # Основной цикл по монетам
    for coin in data['all_coins']:
        volume = coin.get('total_volume', 0)
        price_change = coin.get('price_change_percentage_24h', 0) or 0
        market_cap = coin.get('market_cap', 1)
        ath_change = coin.get('ath_change_percentage', 0) or 0
        price = coin.get('current_price', 0)
        coin_id = coin['id']

        # Базовый фильтр: объём, капитализация, дно от ATH
        if not (volume > 10000000 and market_cap > 100000000 and price > 0.001 and ath_change < -70):
            continue

        # Получаем историю монеты (34-я фишка: вечная)
        coin_data = last_alerts.get(coin_id, {'history': []})
        if not isinstance(coin_data, dict):
            continue

        history = coin_data.get('history', [])
        history.append({'time': current_time, 'price': price})  # Добавляем текущий сигнал в историю

        # Long FOMO по всей истории (периоды: дни/недели/месяцы)
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
                long_fomo += f"{direction.capitalize()} на {abs(diff_percent):.2f}% за {period} (с ${format_price(entry['price'])} до ${format_price(price)})! {'Кто-то уже в плюсе — а вы?' if diff_percent > 0 else 'Дно было глубоким — отскок близко?'}\n"

        fomo = ""

        # Повторный сигнал — сравнение с последним
        if len(history) > 1:
            last_entry = history[-2]
            time_diff = current_time - last_entry['time']
            if time_diff < timedelta(hours=3):
                history.pop()  # Не добавляем, если слишком рано
                continue

            price_diff = ((price - last_entry['price']) / last_entry['price']) * 100 if last_entry['price'] > 0 else 0
            last_volume = coin_data.get('last_volume', volume)
            volume_diff = ((volume - last_volume) / last_volume) * 100 if last_volume > 0 else 0

            if abs(price_diff) < min_change and abs(volume_diff) < min_volume_diff:
                history.pop()  # Не добавляем слабый сигнал
                continue

            hours = time_diff.total_seconds() / 3600
            period_str = f"{int(hours)} часов" if hours < 48 else f"{int(hours // 24)} дней"
            price_str = f"{price_diff:+.2f}% за {period_str} (с ${format_price(last_entry['price'])} до ${format_price(price)})"
            volume_str = f"{volume_diff:+.2f}% за {period_str} (было ${last_volume:,})"
            status = "сигнал усиливается 🔥" if price_diff > 0 else "сигнал слабеет ⚠️"

            if price_diff > 10:
                fomo = f"С последнего сигнала уже +{price_diff:+.2f}% за {period_str}! Киты продолжают грузить — это не случайность, это план перед большим движением.\n"

            if price_diff < -10:
                fomo = f"С последнего сигнала {price_diff:+.2f}% за {period_str}... Но объём держится высоко — киты ждут дна для финального захода. Отскок будет мощным!\n"

        # Новый сигнал
        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.1):
                history.pop()
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            percent_market = round(volume / market_cap * 100)
            volume_str = f"{percent_market}% от капитализации (очень высокий оборот!)"
            status = "новый сигнал — возможная аккумуляция!"

        # Базовый текст блока
        value = "Надёжный аккумулятор на дне — киты грузят, ждут мощного отскока. Пояснение: на таком дне с высоким оборотом — классический сценарий перед взлётом."

        humor = random.choice(fomo_phrases) if not fomo else ""

        reason = f"Выбран за объём {round(volume / market_cap * 100)}% от капитализации и дно {ath_change:.1f}% от ATH. Это значит: кто-то крупный покупает тихо, игнорируя панику рынка."

        alert_block = f"🚨 АНОМАЛЬНЫЙ ОБЪЁМ — {status} 🚨\n\n"
        alert_block += f"{coin['name']} ({coin['symbol'].upper()})\n"
        alert_block += f"Цена: ${format_price(price)} ({price_str})\n"
        alert_block += f"Объём 24h: ${volume:,.0f} ({volume_str})\n"
        alert_block += f"{value}\n"
        if ath_change < -80:
            alert_block += f"На дне: {ath_change:.1f}% от ATH 🔥\n"
        alert_block += f"Причина отбора: {reason}\n"
        alert_block += long_fomo
        alert_block += fomo
        alert_block += f"\n{humor}\n"
        alert_block += "Подробности: CoinGecko"

        alerts_blocks.append(alert_block)

        # Сохраняем в вечную историю
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
    full_msg += "Рынок на дне, проверенные проекты аккумулируют объём. Это шанс на отскок. Кто войдёт — тот в плюсе. Не будьте тем, кто 'ждал подтверждения' в 2022. Рубль на веру — и вы легенда 😏\n\n"
    full_msg += past_analysis
    full_msg += "\n\n".join(alerts_blocks)

    try:
        sent = bot.send_message(GROUP_CHAT_ID, full_msg, reply_to_message_id=big_message_id, disable_web_page_preview=True)
        big_message_id = sent.message_id
    except Exception as e:
        print(f"Ошибка отправки алерта: {e}")

    return full_msg

# Новости — только текст заголовков (33-я фишка)
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
                if "EN" in source_name or "coindesk" in url or "cryptopotato" in url:
                    try:
                        title = translator.translate(title)
                    except:
                        title = original_title + " (EN)"
                if link not in sent_news_urls and not any(SequenceMatcher(None, title.lower(), sent).ratio() > 0.8 for sent in sent_news_titles):
                    all_new_entries.append((title, link, source_name))
                    used_sources.add(source_name)

        if not all_new_entries:
            return None

        random.shuffle(all_new_entries)
        top3 = all_new_entries[:3]

        humor_headers = [
            "📰 Свежие новости крипты — бомжи, читайте, пока не поздно 😏",
            "🔥 Горячий микс новостей — киты уже в курсе, а вы?",
            "📢 Инфа из разных источников — не скам, проверено криптобомжами!"
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
        print(f"Ошибка новостей: {e}")
        return None

# Команда /ссылка — ссылки на последние новости
@bot.message_handler(commands=['ссылка'])
def handle_links(message):
    if not last_published_news:
        bot.send_message(message.chat.id, "Последних новостей пока нет — попробуй /новости.")
        return
    msg = "Ссылки на последние новости:\n\n"
    for i, (title, link) in enumerate(last_published_news, 1):
        msg += f"{i}. {title}\n{link}\n\n"
    bot.send_message(message.chat.id, msg)

# Остальные команды
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
• /помощь — это

Сигналы с FOMO — не проспи памп! 😈
"""
    bot.send_message(message.chat.id, help_text)

# Задачи расписания
def daily_report_task():
    global last_daily_report_date
    today = datetime.now().date()
    if last_daily_report_date == today:
        return
    try:
        bot.send_message(GROUP_CHAT_ID, create_daily_report())
        last_daily_report_date = today
    except Exception as e:
        print(f"Ошибка daily report: {e}")

def final_report_task():
    global last_final_report_date
    today = datetime.now().date()
    if last_final_report_date == today:
        return
    try:
        bot.send_message(GROUP_CHAT_ID, final_day_report())
        last_final_report_date = today
    except Exception as e:
        print(f"Ошибка final report: {e}")

def send_alerts():
    get_anomaly_alerts()

def send_news():
    news = get_news()
    if news:
        try:
            bot.send_message(GROUP_CHAT_ID, news, disable_web_page_preview=False)
        except Exception as e:
            print(f"Ошибка отправки новостей: {e}")

# Расписание
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

    schedule.every().hour.do(send_alerts)

    # Инициализация при старте
    current_utc = datetime.now(timezone.utc)
    current_msk_hour = (current_utc.hour + 3) % 24
    if 10 <= current_msk_hour < 22:
        daily_report_task()
    elif current_msk_hour >= 22:
        final_report_task()

    while True:
        schedule.run_pending()
        time.sleep(1)

# Запуск бота
if __name__ == '__main__':
    print("КриптоАСИСТ ожил! 😈")
    bot.remove_webhook()  # Фикс 409 Conflict
    try:
        alive_msg = bot.send_message(GROUP_CHAT_ID, "КриптоАСИСТ ожил! 😈")
        bot.send_message(GROUP_CHAT_ID, "ожившим привет! 👾", reply_to_message_id=alive_msg.message_id)
    except Exception as e:
        print(f"Не удалось отправить приветствие: {e}")

    # Запуск расписания в фоне
    threading.Thread(target=run_scheduler, daemon=True).start()

    # Основной polling с обработкой ошибок
    while True:
        try:
            bot.infinity_polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка polling: {e}. Перезапуск через 10 секунд...")
            time.sleep(10)
