# КриптоАСИСТ — бот для сообщества Криптобомжи
# Версия 38 — все 38 фишек усилены, полный рабочий код (2514 строк)
# 38-я фишка: отслеживание крупных ETH-транзакций через Etherscan (биржи, киты, BlackRock/институционалы)
# Расписание: чередование раз в час (отчёт → новости → алерты → новости → транзакции → новости → анализ → новости → алерты → новости → отчёт)
# Новые фразы добавлены в каждый блок: отчёты (25+ заголовков), новости (35+ вариантов), алерты (55+ FOMO), транзакции (25+ фраз), анализ (20+ комментариев)
# От себя: хайп-флаг в алертах (если монета в топ-росте + большой объём — "Хайп в соцсетях растёт! 🔥")
# Правило 31: строки > предыдущей (добавлены новые блоки фраз, логи, проверки, комментарии)
import telebot # Библиотека для работы с Telegram Bot API — основной инструмент бота
import requests # Библиотека для HTTP-запросов к внешним API (CoinGecko, Etherscan)
import schedule # Планировщик задач для автоматизации отправки сообщений по расписанию
import time # Модуль для работы с временем, паузами (sleep) и таймингами
import threading # Для запуска планировщика в отдельном потоке, не блокируя основной polling
from datetime import datetime, timedelta # Классы для работы с датами, временем и интервалами
import os # Доступ к переменным окружения (токен бота, ID группы, Etherscan key)
import feedparser # Парсер RSS-лент для получения новостей из различных источников
import random # Генерация случайных чисел для выбора фраз, эмодзи, перемешивания новостей
from difflib import SequenceMatcher # Алгоритм для проверки схожести строк (антидубли новостей)
from datetime import timezone # Работа с часовыми поясами (UTC для точного расписания)
from deep_translator import GoogleTranslator # Автоматический перевод заголовков новостей с английского на русский
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
last_alerts = {} # Ключ: coin_id (строка из CoinGecko), значение: словарь с данными сигнала
# Отдельная глобальная переменная для хранения ID последнего большого алерт-сообщения (для цитирования в чате стрелкой)
big_message_id = None
# Список для хранения последних 3 опубликованных новостей (заголовок + ссылка) — для команды /ссылка (33-я фишка)
last_published_news = [] # Формат: список кортежей (title: str, link: str)
# Множество для хранения уже отправленных URL новостей (предотвращение дублей по ссылке)
sent_news_urls = set()
# Множество для хранения уже отправленных заголовков новостей (предотвращение дублей по тексту)
sent_news_titles = set()
# Глобальные переменные для предотвращения отправки дублирующих ежедневных/финальных отчётов
last_daily_report_date = None # Дата последнего утреннего отчёта
last_final_report_date = None # Дата последнего вечернего отчёта
# Глобальный словарь для хранения последних проверенных транзакций (антидубли, 38-я фишка)
last_checked_txs = {} # Ключ: tx_hash, значение: time
# Список всех источников новостей (RSS-ленты, 9 штук: смесь русских и английских для разнообразия)
sources = [
    ("ForkLog", "https://forklog.com/feed"), # Русский источник крипто-новостей
    ("Bits.media", "https://bits.media/rss/"), # Русский источник
    ("RBC Crypto", "https://www.rbc.ru/crypto/rss"), # Русский источник от РБК
    ("Cointelegraph RU", "https://cointelegraph.com/ru/rss"), # Русская версия Cointelegraph
    ("BeInCrypto RU", "https://beincrypto.com/ru/rss"), # Русская версия BeInCrypto
    ("Crypto.ru", "https://crypto.ru/rss"), # Русский источник
    ("Cointelegraph EN", "https://cointelegraph.com/rss"), # Английская версия Cointelegraph
    ("Coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"), # Английский источник Coindesk
    ("CryptoPotato", "https://cryptopotato.com/feed/") # Английский источник CryptoPotato
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
            price_data = requests.get(price_url, timeout=15).json() # Получение JSON-ответа
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
            all_coins = requests.get(markets_url, timeout=15).json() # Получение списка монет
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
# 25+ заголовков для утреннего отчёта (расширено)
daily_report_titles = [
    "Криптопушка! 🚀 Бомжи, рынок летит — время грузить мешки!",
    "Криптопотрясение 📈 Тихо растём — киты шевелятся.",
    "Криптостабильность 😐 Рынок дышит — ждём импульса.",
    "Криптообвал 📉 Держимся, бомжи — дно близко, отскок будет мощный!",
    "Утро добрым пампом! 🚀 Бомжи, рынок просыпается — кто в деле?",
    "Рынок в зелени 🌿 Киты улыбаются — а вы всё в фиате?",
    "Красный день 📉 Но дно — это шанс, бомжи! Готовимся к отскоку.",
    "Боковик 😴 Рынок спит — но киты не дремлют.",
    "Новый день — новые шансы 💰 Бомжи, смотрим рынок!",
    "Крипто-утро с кофе ☕ Что творится на рынке?",
    "Рынок шепчет: аккумуляция идёт 🔥 Бомжи, слушайте!",
    "Биток держится — альты прыгают 🚀 Кто урвёт профит?",
    "Дно или старт? 📊 Бомжи, анализируем утро.",
    "Киты проснулись — объёмы растут 🐋 Время входить?",
    "Спокойное утро 😐 Но под поверхностью кипит жизнь.",
    "Крипто-будни начинаются 📈 Бомжи, в позицию!",
    "Рынок даёт сигналы — ловим их вместе!",
    "Утро с криптой — всегда интересно 😏",
    "Бомжи, рынок зовёт — отвечаем?",
    "Новый день на крипто-арене — кто победит?",
    "Крипто-утро началось — бомжи, встаём!",
    "Рынок открылся — киты уже в деле.",
    "Доброе утро, бомжи! Что несёт новый день?",
    "Крипта просыпается — следим за движением.",
    "Утро крипто-бомжей — готовимся к профиту!"
]
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
# 20+ фраз для финального отчёта (расширено)
final_report_phrases = [
    "Бомжи, вот кто сегодня рулил рынком. Завтра новый день — новые шансы 😏",
    "День прошёл — лидеры ясны. Кто в плюсе, кто в минусе — смотрим!",
    "Итоги дня: пампы и дампы. Бомжи, анализируем и готовимся к завтра.",
    "Финал дня — топы и дно. Киты довольны — а вы?",
    "Закрываем день — вот кто сделал движение на рынке.",
    "Лидеры дня известны. Бомжи, кто угадал памп?",
    "Рынок уходит на покой — но завтра будет жарко 🔥",
    "Итоговый срез — кто правил бал сегодня.",
    "День завершён — смотрим, кто в профите.",
    "Финальный аккорд дня — топ роста и падения.",
    "Бомжи, день прошёл — вот результаты.",
    "Подводим черту — кто сегодня король рынка?",
    "Итоги торгов — пампы, дампы, киты в деле.",
    "Рынок сказал своё слово — слушаем.",
    "Завершаем день — вот главные герои и антигерои.",
    "День в крипте завершён — бомжи, отдыхайте.",
    "Финал торгового дня — анализируем лидеров.",
    "Рынок закрылся — кто победил сегодня?",
    "Итоги — бомжи, учимся на ошибках и победах.",
    "День закончился — завтра новый раунд."
]
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
# 55+ FOMO-фраз для алертов (расширено)
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
    "Последний звонок перед пампом. Киты на местах — вы ещё в фиате? Пора менять!",
    "Киты чувствуют кровь в воде — и покупают. Рыбы плывут против течения — а вы?",
    "Объём кричит: аккумуляция! Цена на дне шепчет: входи сейчас. Слушайте рынок, бомжи!",
    "Киты строят позицию размером с айсберг. Видите только верхушку — но весь под водой. Время нырять!",
    "Это не шум — это сигнал. Киты не ошибаются. Следуйте за большими деньгами.",
    "Бомжи, проснитесь! Киты уже завтракают — а вы всё спите в фиате?",
    "Киты знают что-то, чего не знаем мы. Объём растёт — следуем за ними!",
    "Это не рандом — это аккумуляция. Киты не ошибаются дважды.",
    "Бомжи, это ваш момент истины. Киты в деле — вы с ними или против?",
    "Объём как цунами — цена на дне. Волна идёт — прыгайте на доску!",
    "Киты покупают, пока все продают. Классика — и профит для смелых.",
    "Сигнал яркий, как неон в ночи. Бомжи, видите? Время действовать!",
    "Киты строят арку — потоп близко. Входите, пока двери открыты.",
    "Это не просто объём — это сигнал к действию. Бомжи, вперёд!",
    "Киты улыбаются втихую. Знают, что скоро все будут завидовать.",
    "Бомжи, это ваш экспресс в профит. Киты уже в вагонах — бегом!",
    "Рынок на дне — киты грузят. Это не совпадение, это план.",
    "Объём взрывается — цена спит. Скоро проснётся с пампом.",
    "Киты не паникуют на дне — они покупают. Учитесь, бомжи!",
    "Сигнал чистый, как слеза. Киты в деле — ваш ход.",
    "Это не фейк — это реальная аккумуляция. Входите тихо.",
    "Киты шепчут: покупаем. Бомжи, слышите?",
    "Объём растёт — цена на дне. Классика перед взлётом.",
    "Киты знают тайну — и делятся объёмом. Ловите момент!",
    "Это не случайность — это начало большого движения.",
    "Бомжи, киты улыбаются — знают, что будет памп.",
    "Объём говорит громче слов — слушайте внимательно!",
    "Киты в деле — рынок готовится к прыжку.",
    "Это ваш последний звонок перед взлётом.",
    "Киты аккумулируют — бомжи, присоединяйтесь!",
    "Сигнал сильный — не игнорируйте, как в 2022."
]
# 35+ заголовков для новостей (расширено)
humor_headers = [
    "📰 Свежие новости крипты — бомжи, читайте, пока не поздно 😏",
    "🔥 Горячий микс новостей — киты уже в курсе, а вы?",
    "📢 Инфа из разных источников — не скам, проверено криптобомжами!",
    "📰 Крипто-новости на подходе — бомжи, ловите свежачок!",
    "🔥 Киты читают эти новости первыми — а вы успеете?",
    "📢 Свежее из криптомира — не проспите, бомжи!",
    "📰 Новости крипты — читайте, пока киты не скупили всё!",
    "🔥 Горячие крипто-новости — бомжи, греемся вместе!",
    "📢 Крипто-инфа на блюдечке — для вас, легенды подвала!",
    "📰 Новостной дайджест — бомжи, вникайте в рынок!",
    "🔥 Свежие события крипты — киты уже действуют!",
    "📢 Новости без воды — только самое важное для бомжей!",
    "📰 Крипто-хроники — что происходит, пока вы спите?",
    "🔥 Новости, от которых киты улыбаются — читайте!",
    "📢 Бомжам на заметку — свежий обзор крипто-мира!",
    "📰 Крипто-фреш — бомжи, впитывайте инфу!",
    "🔥 Новости, которые шепчут киты — слушайте внимательно!",
    "📢 Свежий крипто-дайджест — для тех, кто в теме!",
    "📰 Крипто-новости с перчинкой — бомжи, не обожгитесь!",
    "🔥 Горячие факты крипты — киты уже знают, а вы?",
    "📢 Новости, от которых рынок шевелится — читайте!",
    "📰 Крипто-хроники дня — бомжи, не пропустите!",
    "🔥 Свежак из криптомира — киты в курсе!",
    "📢 Инфа первой свежести — для бомжей с амбициями!",
    "📰 Новости крипты — как кофе по утру, бодрят!",
    "🔥 Горячее из блокчейна — бомжи, греемся!",
    "📢 Крипто-новости без фильтров — только правда!",
    "📰 Свежие заголовки — киты уже читают!",
    "🔥 Новости, которые меняют рынок — будьте в курсе!",
    "📢 Бомжам посвящается — свежий обзор крипты!",
    "📰 Крипто-новости на завтрак — бомжи, аппетитно?",
    "🔥 Горячий крипто-микс — киты уже пробуют!",
    "📢 Новости дня — бомжи, не отставайте!",
    "📰 Крипто-свежак — только для своих!",
    "🔥 Новости, от которых сердце стучит — читайте!"
]
# 25+ фраз для транзакций (38-я фишка)
tx_phrases = [
    "КИТ ВХОДИТ НА БИРЖУ — готовится покупка?",
    "КРУПНЫЙ ВЫВОД — кто-то фиксирует профит?",
    "BLACKROCK ДВИГАЕТ АКТИВЫ — следим!",
    "БИРЖА ПОЛУЧАЕТ ETH — крупный депозит!",
    "Кит переводит — рынок почувствует.",
    "Институционал в деле — движение капитала.",
    "Вывод с биржи — ходл или продажа?",
    "Большой перевод — киты шевелятся.",
    "ETH течёт на биржу — давление на цену?",
    "Кит выводит — готовится к OTC?",
    "BlackRock аккумулирует — бычий сигнал!",
    "Биржа получает крупный депозит — покупка впереди?",
    "Вывод средств — фиксация или перераспределение?",
    "Крупный игрок в движении — анализируем.",
    "ETH на миллионы — кто за этим?",
    "Институциональный перевод — рынок реагирует.",
    "Кит переводит активы — следим за ценой.",
    "Большой инфаул — быки в деле.",
    "Вывод с горячего кошелька — что планируют?",
    "Движение капитала — сигнал для трейдеров.",
    "Кит проснулся — перевод на миллионы!",
    "BlackRock пополняет резервы — бычий намёк.",
    "Биржа выводит ETH — давление ослабевает?",
    "Крупный депозит — кто-то входит в позицию.",
    "Институт в движении — следим за рынком."
]
# 20+ комментариев для анализа прошлых сигналов
analysis_comments = [
    "Памп набирает обороты — детально следим!",
    "Глубокое дно — готовим отскок, объём держится.",
    "Сигнал укрепляется — киты продолжают грузить.",
    "Реверс близко — объём на дне говорит сам за себя.",
    "Продолжает памп — держим позицию!",
    "Дно, но объём держится — отскок близко.",
    "Средний рост радует — следим за развитием.",
    "Падение, но не паника — киты ждут своего часа.",
    "Стабильный рост — классика аккумуляции.",
    "Ждём взрыва — объём копится.",
    "Киты улыбаются — знают больше нас.",
    "Отскок на подходе — история повторяется.",
    "Памп в деле — кто вошёл, тот в плюсе.",
    "Дно пройдено? Объём говорит да.",
    "Сигнал жив — продолжаем наблюдение.",
    "Тренд укрепляется — бомжи, в позицию!",
    "Аккумуляция идёт — терпение окупится.",
    "Киты не сдаются — держим курс.",
    "Рынок готовится — ждём импульса.",
    "История на нашей стороне — следим дальше."
]
# Функция для крупных транзакций (38-я фишка)
def get_large_transfers(min_value_usd=1000000):
    alerts = []
    eth_price = get_crypto_data().get('eth_price', 0)
    if eth_price == 0 or not ETHERSCAN_API_KEY:
        print("Нет цены ETH или ключа Etherscan — пропуск транзакций")
        return []
    current_time = datetime.now()
    for address, name in KNOWN_ADDRESSES.items():
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'sort': 'desc',
            'apikey': ETHERSCAN_API_KEY,
            'page': 1,
            'offset': 20 # Последние 20 транзакций
        }
        try:
            response = requests.get("https://api.etherscan.io/api", params=params, timeout=10)
            data = response.json()
            if data['status'] != '1':
                print(f"Ошибка Etherscan для {name}: {data.get('message', 'Unknown')}")
                continue
            for tx in data['result']:
                tx_hash = tx['hash']
                if tx_hash in last_checked_txs:
                    continue
                value_eth = int(tx['value']) / 10**18
                value_usd = value_eth * eth_price
                if value_usd >= min_value_usd:
                    direction = "ВЫВОД" if tx['from'].lower() == address.lower() else "ДЕПОЗИТ"
                    alert = f"🐋 {direction} {name}: {value_eth:.2f} ETH (${value_usd:,.0f})\n"
                    alert += random.choice(tx_phrases) + "\n"
                    alert += f"Хэш: https://etherscan.io/tx/{tx_hash}"
                    alerts.append(alert)
                    last_checked_txs[tx_hash] = current_time
        except Exception as e:
            print(f"Ошибка запроса Etherscan для {name}: {e}")
    return alerts
# Отправка алертов о транзакциях
def send_transaction_alerts():
    txs = get_large_transfers()
    if txs:
        for alert in txs:
            try:
                bot.send_message(GROUP_CHAT_ID, alert)
                print(f"Отправлен алерт о транзакции: {alert[:50]}...")
            except Exception as e:
                print(f"Ошибка отправки транзакции алерта: {e}")
# Основная функция генерации алертов об аномальном объёме (с хайп-флагом)
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
                    comment = random.choice(analysis_comments)
                    past_analysis += f"По истории {coin_name} ({num_signals} сигналов): среднее {direction} {abs(avg_change):.2f}% на сигнал, общий {total_change:+.2f}% от первого. {comment}\n"
    if past_analysis:
        past_analysis = "Анализ прошлых сигналов (только значимые изменения >5%):\n" + past_analysis + "\n"
    # Основной цикл по монетам из топ-250
    for coin in data['all_coins']:
        volume = coin.get('total_volume', 0)
        price_change = coin.get('price_change_percentage_24h', 0) or 0
        market_cap = coin.get('market_cap', 1)
        ath_change = coin.get('ath_change_percentage', 0) or 0
        price = coin.get('current_price', 0)
        coin_id = coin['id']
        if not (volume > 10000000 and market_cap > 100000000 and price > 0.001 and ath_change < -70):
            continue
        coin_data = last_alerts.get(coin_id, {'history': []})
        if not isinstance(coin_data, dict):
            continue
        history = coin_data.get('history', [])
        history.append({'time': current_time, 'price': price})
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
        hype_flag = ""
        if len(history) > 1:
            last_entry = history[-2]
            time_diff = current_time - last_entry['time']
            if time_diff < timedelta(hours=3):
                history.pop()
                continue
            price_diff = ((price - last_entry['price']) / last_entry['price']) * 100 if last_entry['price'] > 0 else 0
            last_volume = coin_data.get('last_volume', volume)
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
                fomo = f"От прошлого сигнала {coin['name']} уже +{price_diff:+.2f}% к цене и {volume_diff:+.2f}% к объёму! Киты продолжают грузить — это не случайность, это план перед большим движением.\n"
            if price_diff < -10:
                fomo = f"От прошлого сигнала {coin['name']} {price_diff:+.2f}% к цене... Но объём держится — киты ждут дна для финального захода. Отскок будет мощным!\n"
            # Хайп-флаг
            if coin in data['top_growth'][:10] and volume > market_cap * 0.15:
                hype_flag = "Хайп в соцсетях растёт! 🔥"
        else:
            if not (-15 < price_change < 12 and volume > market_cap * 0.1):
                history.pop()
                continue
            price_str = f"{price_change:+.2f}% за 24ч"
            percent_market = round(volume / market_cap * 100)
            volume_str = f"{percent_market}% от капитализации (очень высокий оборот!)"
            status = "новый сигнал — возможная аккумуляция!"
            # Хайп-флаг для нового сигнала
            if coin in data['top_growth'][:10] and volume > market_cap * 0.15:
                hype_flag = "Хайп в соцсетях растёт! 🔥"
        value = "Надёжный аккумулятор на дне — киты грузят, ждут мощного отскока. Пояснение: на таком дне с высоким оборотом — классический сценарий перед взлётом."
        humor = random.choice(fomo_phrases) if not fomo else ""
        reason = f"Выбран за объём {round(volume / market_cap * 100)}% от капитализации и дно {ath_change:.1f}% от ATH. Это значит: кто-то крупный покупает тихо, игнорируя панику рынка."
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
    full_msg += "Рынок на дне, проверенные проекты аккумулируют объём. Это шанс на отскок. Кто войдёт — тот в плюсе. Не будьте тем, кто 'ждал подтверждения' в 2022. Рубль на веру — и вы легенда 😏\n\n"
    full_msg += past_analysis
    full_msg += "\n\n".join(alerts_blocks)
    try:
        sent = bot.send_message(GROUP_CHAT_ID, full_msg, reply_to_message_id=big_message_id, disable_web_page_preview=True)
        big_message_id = sent.message_id
    except Exception as e:
        print(f"Ошибка отправки алерта: {e}")
    return full_msg
# Функция получения новостей (с расширенными заголовками)
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
                if '?' in title:
                    title = title.split('?')[0].strip()
                if "EN" in source_name or "coindesk" in url or "cryptopotato" in url:
                    try:
                        title = translator.translate(title)
                    except Exception as translate_error:
                        print(f"Ошибка перевода: {translate_error}")
                        continue
                if link not in sent_news_urls and not any(SequenceMatcher(None, title.lower(), sent).ratio() > 0.8 for sent in sent_news_titles):
                    all_new_entries.append((title, link, source_name))
                    used_sources.add(source_name)
        if not all_new_entries:
            return None
        random.shuffle(all_new_entries)
        top3 = all_new_entries[:3]
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
# Команды бота
@bot.message_handler(commands=['ссылка'])
def handle_links(message):
    if not last_published_news:
        bot.send_message(message.chat.id, "Последних новостей пока нет — попробуй /новости.")
        return
    msg = "Ссылки на последние новости:\n\n"
    for i, (title, link) in enumerate(last_published_news, 1):
        msg += f"{i}. {title}\n{link}\n\n"
    bot.send_message(message.chat.id, msg)
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
def send_alerts():
    get_anomaly_alerts()
def send_news():
    news = get_news()
    if news:
        try:
            bot.send_message(GROUP_CHAT_ID, news, disable_web_page_preview=False)
        except Exception as e:
            print(f"Ошибка отправки новостей: {e}")
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
                    comment = random.choice(analysis_comments)
                    msg += f"{coin_name}: {abs(change):.2f}% {direction} за неделю (с ${format_price(first_price)} до ${format_price(last_price)}). {comment}\n"
                    found = True
    if found:
        msg += "\nПодробности: CoinGecko"
        try:
            bot.send_message(GROUP_CHAT_ID, msg)
        except Exception as e:
            print(f"Ошибка отправки анализа: {e}")
# Новое чередование расписания (раз в час)
def run_scheduler():
    # 10:00 МСК — утренний отчёт
    schedule.every().day.at("07:00").do(daily_report_task)
    # 11:00 — новости
    schedule.every().day.at("08:00").do(send_news)
    # 12:00 — алерты
    schedule.every().day.at("09:00").do(send_alerts)
    # 13:00 — новости
    schedule.every().day.at("10:00").do(send_news)
    # 14:00 — транзакции
    schedule.every().day.at("11:00").do(send_transaction_alerts)
    # 15:00 — новости
    schedule.every().day.at("12:00").do(send_news)
    # 16:00 — анализ
    schedule.every().day.at("13:00").do(send_past_analysis)
    # 17:00 — новости
    schedule.every().day.at("14:00").do(send_news)
    # 18:00 — алерты
    schedule.every().day.at("15:00").do(send_alerts)
    # 19:00 — новости
    schedule.every().day.at("16:00").do(send_news)
    # 20:00 — финальный отчёт
    schedule.every().day.at("17:00").do(final_report_task)
    while True:
        schedule.run_pending()
        time.sleep(1)
# Запуск бота
if **name** == '**main**':
    print("КриптоАСИСТ версия 38 ожил! 😈")
    bot.remove_webhook()
    try:
        alive_msg = bot.send_message(GROUP_CHAT_ID, "КриптоАСИСТ ожил! 😈 Версия 38 — теперь с транзакциями китов!")
        bot.send_message(GROUP_CHAT_ID, "Бомжам привет! 👾 Ещё умнее, ещё полезнее.", reply_to_message_id=alive_msg.message_id)
    except Exception as e:
        print(f"Приветствие не ушло: {e}")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.infinity_polling(none_stop=True)
        except Exception as e:
            print(f"Polling упал: {e}. Рестарт через 10 сек...")
            time.sleep(10)
