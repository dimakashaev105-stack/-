import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import random
import os
import re
import shutil  
from datetime import datetime, timedelta
import threading
import logging
# Замените на свой токен
BOT_TOKEN = "8287060486:AAH0tRlAnM2s4rYXKQRDlIB-XMZOhTcMuyI"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
# ID администраторов (замените на свои)
ADMIN_IDS = [8139807344, 5255608302]  # Пример ID администраторов

bot = telebot.TeleBot(BOT_TOKEN)

# Словарь для защиты от спама
user_last_action = {}
user_captcha_status = {}

# === ИЗМЕНЕНО: улучшенная функция подключения к БД ===
def get_db_connection():
    """Создает безопасное подключение к базе данных"""
    conn = None
    try:
        conn = sqlite3.connect('game.db', timeout=10)
        
        # Проверяем целостность БД
        cursor = conn.cursor()
        
        try:
            cursor.execute('PRAGMA integrity_check')
            integrity = cursor.fetchone()[0]
            
            if integrity != 'ok':
                logging.warning(f"База данных повреждена: {integrity}")
                # Если база повреждена, не включаем WAL
                conn.row_factory = sqlite3.Row
                return conn
        except:
            # Если проверка целостности не удалась, пропускаем WAL
            conn.row_factory = sqlite3.Row
            return conn
        
        # Если база цела, включаем WAL
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA foreign_keys=ON')
        
        conn.row_factory = sqlite3.Row
        return conn
        
    except sqlite3.Error as e:
        if conn:
            conn.close()
        logging.error(f"Ошибка подключения к БД: {e}")
        
        # Пробуем создать новое подключение без WAL
        try:
            conn = sqlite3.connect('game.db', timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except:
            # Если не получается, создаем новую базу
            import os
            if os.path.exists('game.db'):
                os.remove('game.db')
            conn = sqlite3.connect('game.db', timeout=10)
            conn.row_factory = sqlite3.Row
            return conn

# === ИСПРАВЛЕННАЯ ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    """Инициализация базы данных с корректной структурой"""
    conn = None  # ВАЖНО: инициализируем переменную
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей (сразу со всеми колонками)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            last_click INTEGER DEFAULT 0,
            click_power INTEGER DEFAULT 2,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            video_cards INTEGER DEFAULT 0,
            deposit INTEGER DEFAULT 0,
            last_mining_collect INTEGER DEFAULT 0,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            click_streak INTEGER DEFAULT 0,
            bank_deposit INTEGER DEFAULT 0,
            captcha_passed INTEGER DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            banned_at TIMESTAMP,
            last_interest_calc INTEGER DEFAULT 0,
            last_snow_work TIMESTAMP,
            snow_cooldown_end TIMESTAMP,
            current_snow_job TEXT,
            snow_job_progress INTEGER DEFAULT 0,
            snow_job_total INTEGER DEFAULT 0,
            snow_job_end_time TIMESTAMP,
            snow_territory TEXT,
            last_bonus INTEGER DEFAULT 0
        )
        ''')
        
        # Таблица чеков
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS checks (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            max_activations INTEGER,
            current_activations INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица активаций чеков
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_activations (
            user_id INTEGER,
            check_code TEXT,
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, check_code),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (check_code) REFERENCES checks(code) ON DELETE CASCADE
        )
        ''')
        
        
        
        conn.commit()
        logging.info("✅ База данных успешно инициализирована")
        
        # Проверка целостности БД
        cursor.execute('PRAGMA integrity_check')
        integrity = cursor.fetchone()[0]
        if integrity == 'ok':
            logging.info("✅ Проверка целостности БД: OK")
        else:
            logging.warning(f"⚠️ Проблемы с целостностью БД: {integrity}")
            
    except sqlite3.Error as e:
        logging.error(f"❌ Ошибка инициализации БД: {e}")
        raise
    finally:
        if conn:
            conn.close()
# === КОНЕЦ ИСПРАВЛЕНИЙ ===

# Функция для проверки прав администратора
def is_admin(user_id):
    return user_id in ADMIN_IDS

# Функция для проверки бана
def is_banned(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned, ban_reason FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0] == 1:
        return True, result[1] if result[1] else "Причина не указана"
    return False, None

# Функция для проверки спама
def is_spam(user_id):
    current_time = time.time()
    if user_id in user_last_action:
        time_passed = current_time - user_last_action[user_id]
        if time_passed < 1:  # 1 секунда между действиями
            return True
    user_last_action[user_id] = current_time
    return False

# Функция для проверки капчи
def is_captcha_passed(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False

# Функция для генерации математической капчи
def generate_captcha():
    # Генерируем два случайных числа
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    
    # Выбираем случайную операцию
    operation = random.choice(['+', '-', '*'])
    
    # Вычисляем правильный ответ
    if operation == '+':
        answer = num1 + num2
    elif operation == '-':
        answer = num1 - num2
    else:  # '*'
        answer = num1 * num2
    
    # Формируем вопрос
    captcha_question = f"{num1} {operation} {num2} = ?"
    
    return captcha_question, str(answer)

# Функция для парсинга суммы ставки
def parse_bet_amount(bet_text, user_balance):
    if bet_text.lower() in ['все', 'all']:
        return user_balance
    
    bet_text = bet_text.lower().replace(' ', '')
    
    pattern = r'^(\d*\.?\d+)([кk]|[кk]{2,}|[mb]?)$'
    match = re.match(pattern, bet_text)
    
    if match:
        number_part = match.group(1)
        multiplier_part = match.group(2)
        
        try:
            number = float(number_part)
            
            if multiplier_part.startswith('к') or multiplier_part.startswith('k'):
                k_count = multiplier_part.count('к') + multiplier_part.count('k')
                if k_count == 1:
                    multiplier = 1000
                elif k_count == 2:
                    multiplier = 1000000
                else:
                    multiplier = 1000000000
            elif multiplier_part == 'm':
                multiplier = 1000000
            elif multiplier_part == 'b':
                multiplier = 1000000000
            else:
                multiplier = 1
            
            return int(number * multiplier)
        except:
            return None
    
    try:
        return int(bet_text)
    except:
        return None

# Функция для форматирования суммы с пробелами
def format_balance(balance):
    return f"{balance:,}".replace(",", " ")

# Функция для получения или создания пользователя
def get_or_create_user(user_id, username, first_name):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        referral_code = f"ref{user_id}"
        
        cursor.execute(
            'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp())
        )
        conn.commit()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

# Функция для обновления баланса с проверкой бана
def update_balance(user_id, amount):
    banned, reason = is_banned(user_id)
    if banned:
        return False
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ?, last_activity = CURRENT_TIMESTAMP WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()
    return True

# Функция для получения баланса с начислением процентов
def get_balance(user_id):
    # Сначала начисляем проценты
    calculate_interest(user_id)
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

# Функция для начисления процентов по вкладу
def calculate_interest(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    # Получаем данные о вкладе и последнем начислении
    cursor.execute('SELECT bank_deposit, last_interest_calc FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result and result[0] > 0:  # Если есть вклад
        bank_deposit, last_calc = result
        
        # Преобразуем last_calc в timestamp
        if isinstance(last_calc, str):
            try:
                last_calc_time = datetime.strptime(last_calc, '%Y-%m-%d %H:%M:%S').timestamp()
            except:
                last_calc_time = time.time() - 3600  # Если ошибка, считаем что прошёл час
        elif isinstance(last_calc, float) or isinstance(last_calc, int):
            last_calc_time = last_calc
        else:
            last_calc_time = time.time() - 3600
        
        current_time = time.time()
        hours_passed = (current_time - last_calc_time) / 3600
        
        if hours_passed >= 1:  # Прошёл минимум 1 час
            # Рассчитываем проценты (0.5% в час)
            interest_hours = int(hours_passed)  # Целые часы
            interest = int(bank_deposit * 0.01 * interest_hours)  # 0.5% за каждый час
            
            if interest > 0:
                # Начисляем проценты
                cursor.execute('UPDATE users SET balance = balance + ?, last_interest_calc = ? WHERE user_id = ?',
                             (interest, current_time, user_id))
                conn.commit()
    
    conn.close()

# Функция для получения банковского вклада
def get_bank_deposit(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT bank_deposit FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

# Функция для обновления банковского вклада
def update_bank_deposit(user_id, amount):
    banned, reason = is_banned(user_id)
    if banned:
        return False
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET bank_deposit = bank_deposit + ?, last_interest_calc = ? WHERE user_id = ?',
                  (amount, datetime.now().timestamp(), user_id))
    conn.commit()
    conn.close()
    return True

# Функция для получения серии кликов
def get_click_streak(user_id):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT click_streak FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

# Функция для обновления серии кликов
def update_click_streak(user_id, amount):
    banned, reason = is_banned(user_id)
    if banned:
        return False
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET click_streak = click_streak + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()
    return True





# Функция для расчета дохода майнинга
def calculate_mining_income(video_cards):
    base_income = 25000000
    return base_income * (2 ** (video_cards - 1)) if video_cards > 0 else 0

# Функция для расчета цены видеокарты
def calculate_video_card_price(video_cards):
    base_price = 500000000
    return base_price * (2 ** video_cards)

# Функция для создания клавиатуры майнинга
def create_mining_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("❄️ Собрать", callback_data="mining_collect"),
        InlineKeyboardButton("🖥 Купить видеокарту", callback_data="mining_buy")
    )
    return markup

# Функция для создания клавиатуры кликера
def create_clicker_keyboard():
    symbols = ["❌", "❌", "❌", "❌", "✅"]
    random.shuffle(symbols)
    
    markup = InlineKeyboardMarkup()
    row = []
    for i, symbol in enumerate(symbols):
        row.append(InlineKeyboardButton(symbol, callback_data=f"clicker_{symbol}"))
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    return markup


# Главное меню (компактный вариант)
def create_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # 8 кнопок в 4 строки
    markup.add(
        KeyboardButton("Баланс"),
        KeyboardButton("Майнинг"),
        KeyboardButton("Банк"),
        KeyboardButton("Казино"),
        KeyboardButton("Работа"),
        KeyboardButton("Топ снежков"),
        KeyboardButton("Панель клана"),
        KeyboardButton("Бонус")
    )
    
    return markup



# =============== ИСПРАВЛЕННАЯ СИСТЕМА КОНКУРСОВ (Telegram API совместимая) ===============

# Глобальные переменные для конкурсов
USER_CONTESTS = {}  # {user_id: {"step": X, "data": {}}}
ACTIVE_CONTESTS = {}  # {contest_id: {contest_data}}
CONTEST_PARTICIPANTS = {}  # {contest_id: [user_id1, user_id2, ...]}

@bot.message_handler(func=lambda message: message.text.lower() == 'конкурс')
def handle_contest_start(message):
    """Начало создания конкурса"""
    try:
        user_id = message.from_user.id
        
        # Проверяем права администратора бота
        if not is_admin(user_id):
            bot.send_message(message.chat.id, "❌ Только администраторы могут создавать конкурсы")
            return
        
        # Начинаем создание конкурса
        USER_CONTESTS[user_id] = {
            "step": 1,
            "data": {
                "creator_id": user_id,
                "creator_name": message.from_user.first_name,
                "creator_username": message.from_user.username if message.from_user.username else "",
                "start_time": time.time()
            }
        }
        
        bot.send_message(
            message.chat.id,
            "🎉 *СОЗДАНИЕ КОНКУРСА*\n\n"
            "1️⃣ *Шаг 1:* Пришлите *username* канала (без @)\n"
            "Пример: `my_channel`\n\n"
            "⚠️ *Требования:*\n"
            "• Канал должен быть публичным\n"
            "• Бот должен быть в канале\n"
            "• Вы организатор конкурса",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Ошибка начала конкурса: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка создания конкурса")

@bot.message_handler(func=lambda message: message.from_user.id in USER_CONTESTS)
def handle_contest_steps(message):
    """Обработка шагов создания конкурса"""
    try:
        user_id = message.from_user.id
        contest_data = USER_CONTESTS.get(user_id)
        
        if not contest_data:
            bot.send_message(message.chat.id, "❌ Сессия устарела, начните заново")
            return
            
        step = contest_data["step"]
        data = contest_data["data"]
        
        if step == 1:
            # Шаг 1: Получаем канал
            channel_input = message.text.strip()
            
            # Убираем @ если есть
            if channel_input.startswith('@'):
                channel_input = channel_input[1:]
            
            if not channel_input or len(channel_input) < 3:
                bot.send_message(message.chat.id, 
                               "❌ Неверный формат канала\n"
                               "Пример: `my_channel`")
                return
            
            # Сохраняем username канала
            data["channel_username"] = channel_input
            contest_data["step"] = 2
            
            bot.send_message(
                message.chat.id,
                f"✅ Канал сохранен: @{channel_input}\n\n"
                f"2️⃣ *Шаг 2:* Введите количество участников\n"
                f"Минимум: 2\n"
                f"Максимум: 500\n\n"
                f"Пример: `50`",
                parse_mode='Markdown'
            )
            
        elif step == 2:
            # Шаг 2: Количество участников
            try:
                max_participants = int(message.text.strip())
                if max_participants < 2:
                    bot.send_message(message.chat.id, "❌ Минимум 2 участника")
                    return
                if max_participants > 500:
                    bot.send_message(message.chat.id, "❌ Максимум 500 участников")
                    return
                    
                data["max_participants"] = max_participants
                contest_data["step"] = 3
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Участников: {max_participants}\n\n"
                    f"3️⃣ *Шаг 3:* Введите количество победителей\n"
                    f"Максимум: {min(10, max_participants)}\n\n"
                    f"Пример: `3`",
                    parse_mode='Markdown'
                )
                
            except ValueError:
                bot.send_message(message.chat.id, "❌ Введите число!")
                return
                
        elif step == 3:
            # Шаг 3: Количество победителей
            try:
                winners_count = int(message.text.strip())
                max_participants = data.get("max_participants", 10)
                
                if winners_count < 1:
                    bot.send_message(message.chat.id, "❌ Минимум 1 победитель")
                    return
                if winners_count > min(10, max_participants):
                    bot.send_message(message.chat.id, 
                                   f"❌ Максимум {min(10, max_participants)} победителей")
                    return
                    
                data["winners_count"] = winners_count
                contest_data["step"] = 4
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Победителей: {winners_count}\n\n"
                    f"4️⃣ *Шаг 4:* Введите призы для победителей\n"
                    f"Формат: место → приз\n\n"
                    f"*Пример:*\n"
                    f"```\n"
                    f"1 место - 1.000.000❄️\n"
                    f"2 место - 500.000❄️\n"
                    f"3 место - 250.000❄️\n"
                    f"```",
                    parse_mode='Markdown'
                )
                
            except ValueError:
                bot.send_message(message.chat.id, "❌ Введите число!")
                return
                
        elif step == 4:
            # Шаг 4: Призы
            prizes_text = message.text.strip()
            if not prizes_text:
                bot.send_message(message.chat.id, "❌ Введите текст призов")
                return
                
            data["prizes_text"] = prizes_text
            
            # Формируем итоговый текст
            preview_text = create_contest_preview(data)
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("✅ ОПУБЛИКОВАТЬ", callback_data="contest_publish"),
                InlineKeyboardButton("✏️ РЕДАКТИРОВАТЬ", callback_data="contest_edit"),
                InlineKeyboardButton("❌ ОТМЕНА", callback_data="contest_cancel")
            )
            
            bot.send_message(
                message.chat.id,
                preview_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
    except Exception as e:
        logging.error(f"Ошибка в шаге конкурса: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка, начните заново")
        if user_id in USER_CONTESTS:
            del USER_CONTESTS[user_id]

def create_contest_preview(contest_data):
    """Создает текст для предпросмотра конкурса"""
    
    text = f"""
🎉 *ПРЕДПРОСМОТР КОНКУРСА*

*📢 Канал:* @{contest_data.get('channel_username', 'N/A')}
*👥 Участников:* {contest_data.get('max_participants', 'N/A')}
*🏆 Победителей:* {contest_data.get('winners_count', 'N/A')}

*💰 ПРИЗЫ:*
{contest_data.get('prizes_text', 'N/A')}

*👤 Организатор:* {contest_data.get('creator_name', 'N/A')}

*📅 Создан:* {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    
    return text

@bot.callback_query_handler(func=lambda call: call.data.startswith('contest_'))
def contest_callback_handler(call):
    """Обработка колбэков конкурса"""
    try:
        user_id = call.from_user.id
        
        if call.data == "contest_publish":
            if user_id not in USER_CONTESTS:
                bot.answer_callback_query(call.id, "❌ Данные утеряны", show_alert=True)
                return
            
            contest_data = USER_CONTESTS[user_id]["data"]
            
            # Проверяем необходимые данные
            required_fields = ['channel_username', 'max_participants', 'winners_count', 'prizes_text']
            missing_fields = [f for f in required_fields if f not in contest_data]
            
            if missing_fields:
                bot.answer_callback_query(call.id, f"❌ Отсутствуют данные: {missing_fields}", show_alert=True)
                return
            
            # Генерируем ID конкурса
            contest_id = f"contest_{user_id}_{int(time.time())}"
            
            try:
                # Пытаемся получить информацию о канале
                channel_username = contest_data['channel_username']
                try:
                    chat = bot.get_chat(f"@{channel_username}")
                    contest_data["channel_title"] = chat.title
                except Exception as e:
                    logging.warning(f"Не могу получить канал @{channel_username}: {e}")
                    contest_data["channel_title"] = f"@{channel_username}"
                
                # Сохраняем активный конкурс
                ACTIVE_CONTESTS[contest_id] = {
                    **contest_data,
                    "contest_id": contest_id,
                    "created_at": time.time(),
                    "status": "active",
                    "published": False  # Флаг что пост не опубликован в канале
                }
                
                CONTEST_PARTICIPANTS[contest_id] = []
                
                # Создаем ссылку для участия
                bot_username = (bot.get_me()).username
                participate_link = f"https://t.me/{bot_username}?start={contest_id}"
                
                # Создаем текст для конкурса
                post_text = f"""
🎊 *КОНКУРС В БОТЕ!* 🎊

*📢 Канал:* @{contest_data['channel_username']}
*👥 Нужно участников:* {contest_data['max_participants']}
*🏆 Победителей:* {contest_data['winners_count']}

*💰 ПРИЗОВОЙ ФОНД:*
{contest_data['prizes_text']}

*📝 КАК УЧАСТВОВАТЬ:*
1. Нажмите кнопку ниже
2. Бот проверит подписку на канал
3. Ждите результатов!

*⏰ Участники набираются автоматически*
*🎲 Победители выбираются случайно*

*👤 Организатор:* {contest_data['creator_name']}
"""
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🎯 УЧАСТВОВАТЬ", url=participate_link))
                
                # Отправляем создателю для копирования в канал
                bot.edit_message_text(
                    f"✅ *КОНКУРС СОЗДАН!*\n\n"
                    f"📢 Канал: @{contest_data['channel_username']}\n"
                    f"👥 Участников: 0/{contest_data['max_participants']}\n"
                    f"🏆 Победителей: {contest_data['winners_count']}\n"
                    f"🔗 ID конкурса: `{contest_id}`\n\n"
                    f"*📋 СКОПИРУЙТЕ ТЕКСТ НИЖЕ И ОПУБЛИКУЙТЕ В КАНАЛЕ:*",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                
                # Отправляем текст для публикации
                bot.send_message(
                    user_id,
                    post_text,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                
                # Отправляем инструкцию
                bot.send_message(
                    user_id,
                    f"📋 *ИНСТРУКЦИЯ:*\n\n"
                    f"1. Скопируйте сообщение выше\n"
                    f"2. Опубликуйте в канале @{contest_data['channel_username']}\n"
                    f"3. Пользователи нажимают кнопку для участия\n\n"
                    f"*Команды для управления:*\n"
                    f"`итоги {contest_id}` — Подвести итоги\n"
                    f"`участники {contest_id}` — Список участников\n"
                    f"`отмена {contest_id}` — Отменить конкурс",
                    parse_mode='Markdown'
                )
                
                bot.answer_callback_query(call.id, "✅ Конкурс создан!", show_alert=True)
                
            except Exception as e:
                logging.error(f"Ошибка создания конкурса: {e}")
                bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
                return
            
            # Очищаем данные
            del USER_CONTESTS[user_id]
            
        elif call.data == "contest_edit":
            # Возвращаем к редактированию
            if user_id in USER_CONTESTS:
                USER_CONTESTS[user_id]["step"] = 1
                
                bot.edit_message_text(
                    "✏️ *РЕДАКТИРОВАНИЕ КОНКУРСА*\n\n"
                    "Пришлите username канала (без @):",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                
                bot.answer_callback_query(call.id, "✏️ Редактирование...")
            else:
                bot.answer_callback_query(call.id, "❌ Данные утеряны", show_alert=True)
                
        elif call.data == "contest_cancel":
            # Отмена создания
            if user_id in USER_CONTESTS:
                del USER_CONTESTS[user_id]
                
            try:
                bot.edit_message_text(
                    "❌ Создание конкурса отменено",
                    call.message.chat.id,
                    call.message.message_id
                )
            except:
                pass
                
            bot.answer_callback_query(call.id, "❌ Отменено")
            
    except Exception as e:
        logging.error(f"Ошибка в колбэке конкурса: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка обработки", show_alert=True)
        except:
            pass

# =============== УЧАСТИЕ В КОНКУРСЕ ===============

@bot.message_handler(func=lambda message: message.text and message.text.startswith('/start contest_'))
def handle_contest_participation(message):
    """Обработка участия в конкурсе"""
    try:
        user_id = message.from_user.id
        
        # Извлекаем ID конкурса
        parts = message.text.split()
        if len(parts) < 2:
            return
            
        contest_id = parts[1]
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.send_message(message.chat.id, "❌ Конкурс не найден или завершен")
            return
        
        contest = ACTIVE_CONTESTS[contest_id]
        
        # Проверяем статус конкурса
        if contest.get('status') != 'active':
            bot.send_message(message.chat.id, "❌ Конкурс завершен")
            return
        
        # Проверяем подписку на канал (если есть username)
        channel_username = contest.get('channel_username')
        subscribed = False
        
        if channel_username:
            try:
                chat_member = bot.get_chat_member(f"@{channel_username}", user_id)
                if chat_member.status in ['member', 'administrator', 'creator']:
                    subscribed = True
                else:
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url=f"https://t.me/{channel_username}"))
                    
                    bot.send_message(
                        message.chat.id,
                        f"❌ Для участия подпишитесь на канал\n"
                        f"📢 @{channel_username}\n\n"
                        f"После подписки нажмите на ссылку снова",
                        reply_markup=markup
                    )
                    return
            except Exception as e:
                logging.warning(f"Ошибка проверки подписки: {e}")
                # Если не можем проверить, продолжаем без проверки
        
        # Проверяем уже ли участвует
        if user_id in CONTEST_PARTICIPANTS.get(contest_id, []):
            bot.send_message(message.chat.id, "✅ Вы уже участвуете в конкурсе!")
            return
        
        # Проверяем лимит участников
        current_count = len(CONTEST_PARTICIPANTS.get(contest_id, []))
        max_participants = contest.get('max_participants', 0)
        
        if current_count >= max_participants:
            bot.send_message(message.chat.id, "❌ Конкурс уже набрал максимальное количество участников")
            return
        
        # Добавляем участника
        if contest_id not in CONTEST_PARTICIPANTS:
            CONTEST_PARTICIPANTS[contest_id] = []
        
        CONTEST_PARTICIPANTS[contest_id].append(user_id)
        
        # Обновляем счетчик
        current_count = len(CONTEST_PARTICIPANTS[contest_id])
        
        # Уведомляем участника
        response_text = f"✅ *ВЫ УЧАСТВУЕТЕ!*\n\n"
        response_text += f"🎯 Конкурс: @{contest.get('channel_username', 'N/A')}\n"
        response_text += f"👥 Участников: {current_count}/{max_participants}\n"
        response_text += f"🏆 Победителей: {contest.get('winners_count', 'N/A')}\n\n"
        
        if subscribed:
            response_text += "*✅ Вы подписаны на канал*\n"
        else:
            response_text += "*⚠️ Проверка подписки не выполнена*\n"
        
        response_text += "*⏳ Ждите результатов!*"
        
        bot.send_message(
            message.chat.id,
            response_text,
            parse_mode='Markdown'
        )
        
        # Уведомляем организатора если набрали участников
        if current_count == max_participants:
            try:
                bot.send_message(
                    contest['creator_id'],
                    f"🎉 *КОНКУРС НАБРАЛ УЧАСТНИКОВ!*\n\n"
                    f"Конкурс: @{contest.get('channel_username', 'N/A')}\n"
                    f"Участников: {current_count}/{max_participants}\n\n"
                    f"Используйте команду:\n"
                    f"`итоги {contest_id}`",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"Не удалось уведомить организатора: {e}")
        
        # Логируем участие
        log_user_action(user_id, "CONTEST_JOIN", f"contest={contest_id}")
        
    except Exception as e:
        logging.error(f"Ошибка участия в конкурсе: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка участия в конкурсе")

# =============== КОМАНДЫ УПРАВЛЕНИЯ КОНКУРСАМИ ===============

@bot.message_handler(func=lambda message: message.text.lower().startswith('итоги ') and is_admin(message.from_user.id))
def handle_contest_results(message):
    """Подведение итогов конкурса"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: итоги ID_конкурса")
            return
        
        contest_id = parts[1].strip()
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.send_message(message.chat.id, "❌ Конкурс не найден")
            return
        
        contest = ACTIVE_CONTESTS[contest_id]
        participants = CONTEST_PARTICIPANTS.get(contest_id, [])
        
        if len(participants) < contest.get('winners_count', 1):
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно участников!\n"
                           f"Нужно: {contest['winners_count']}\n"
                           f"Есть: {len(participants)}")
            return
        
        # Выбираем победителей случайно
        try:
            winners = random.sample(participants, contest['winners_count'])
        except ValueError as e:
            bot.send_message(message.chat.id, f"❌ Ошибка выбора победителей: {e}")
            return
        
        # Формируем список победителей
        winners_text = "🏆 *ПОБЕДИТЕЛИ КОНКУРСА:*\n\n"
        for i, winner_id in enumerate(winners, 1):
            try:
                user = bot.get_chat(winner_id)
                username = f"@{user.username}" if user.username else user.first_name
                winners_text += f"{i}. {username}\n"
            except:
                winners_text += f"{i}. ID: {winner_id}\n"
        
        winners_text += f"\n📊 Всего участников: {len(participants)}"
        
        # Отправляем результаты создателю
        bot.send_message(
            message.chat.id,
            winners_text,
            parse_mode='Markdown'
        )
        
        # Создаем текст для публикации в канале
        channel_post = f"""
🎊 *ИТОГИ КОНКУРСА!* 🎊

{winners_text}

Поздравляем победителей! 🎉

👤 Организатор: {contest.get('creator_name', 'N/A')}
"""
        
        # Отправляем создателю для публикации
        bot.send_message(
            message.chat.id,
            f"📋 *ТЕКСТ ДЛЯ ПУБЛИКАЦИИ В КАНАЛЕ:*\n\n{channel_post}",
            parse_mode='Markdown'
        )
        
        # Уведомляем победителей
        notified = 0
        for i, winner_id in enumerate(winners, 1):
            try:
                creator_username = contest.get('creator_username', '')
                contact = f"@{creator_username}" if creator_username else "организатору"
                
                bot.send_message(
                    winner_id,
                    f"🎉 *ВЫ ВЫИГРАЛИ В КОНКУРСЕ!*\n\n"
                    f"Конкурс: @{contest.get('channel_username', 'N/A')}\n"
                    f"Место: {i}\n\n"
                    f"Свяжитесь с {contact} для получения приза",
                    parse_mode='Markdown'
                )
                notified += 1
            except Exception as e:
                logging.error(f"Не удалось уведомить победителя {winner_id}: {e}")
        
        # Завершаем конкурс
        ACTIVE_CONTESTS[contest_id]['status'] = 'finished'
        ACTIVE_CONTESTS[contest_id]['finished_at'] = time.time()
        ACTIVE_CONTESTS[contest_id]['winners'] = winners
        
        bot.send_message(
            message.chat.id,
            f"✅ Итоги подведены!\n"
            f"👤 Уведомлено победителей: {notified}/{len(winners)}\n"
            f"📋 Текст для публикации отправлен выше"
        )
        
    except Exception as e:
        logging.error(f"Ошибка подведения итогов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower().startswith('участники ') and is_admin(message.from_user.id))
def handle_contest_participants(message):
    """Показывает участников конкурса"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: участники ID_конкурса")
            return
        
        contest_id = parts[1].strip()
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.send_message(message.chat.id, "❌ Конкурс не найден")
            return
        
        participants = CONTEST_PARTICIPANTS.get(contest_id, [])
        contest = ACTIVE_CONTESTS[contest_id]
        
        if not participants:
            bot.send_message(message.chat.id, "📭 Участников пока нет")
            return
        
        # Формируем список
        participants_text = f"👥 *УЧАСТНИКИ КОНКУРСА:*\n\n"
        participants_text += f"Всего: {len(participants)}/{contest.get('max_participants', 0)}\n\n"
        
        # Показываем только первые 20 участников
        for i, user_id in enumerate(participants[:20], 1):
            try:
                user = bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else user.first_name
                participants_text += f"{i}. {username}\n"
            except:
                participants_text += f"{i}. ID: {user_id}\n"
        
        if len(participants) > 20:
            participants_text += f"\n... и ещё {len(participants) - 20} участников"
        
        bot.send_message(message.chat.id, participants_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка показа участников: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка получения участников")

@bot.message_handler(func=lambda message: message.text.lower().startswith('моиконкурсы') and is_admin(message.from_user.id))
def handle_my_contests(message):
    """Показывает созданные конкурсы"""
    try:
        user_id = message.from_user.id
        
        my_contests = []
        for contest_id, contest in ACTIVE_CONTESTS.items():
            if contest.get('creator_id') == user_id:
                participants = len(CONTEST_PARTICIPANTS.get(contest_id, []))
                my_contests.append((contest_id, contest, participants))
        
        if not my_contests:
            bot.send_message(message.chat.id, "📭 У вас нет активных конкурсов")
            return
        
        contests_text = "🎯 *ВАШИ КОНКУРСЫ:*\n\n"
        
        for contest_id, contest, participants in my_contests:
            status_emoji = "✅" if contest.get('status') == 'active' else "🏁"
            status_text = "Активен" if contest.get('status') == 'active' else "Завершен"
            
            contests_text += (
                f"{status_emoji} *@{contest.get('channel_username', 'N/A')}*\n"
                f"ID: `{contest_id}`\n"
                f"Участников: {participants}/{contest.get('max_participants', 'N/A')}\n"
                f"Статус: {status_text}\n\n"
            )
        
        contests_text += "*Команды:*\n`итоги ID` `участники ID` `отмена ID`"
        
        bot.send_message(message.chat.id, contests_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка показа конкурсов: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка получения конкурсов")

@bot.message_handler(func=lambda message: message.text.lower().startswith('отмена ') and is_admin(message.from_user.id))
def handle_contest_cancel(message):
    """Отмена конкурса"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: отмена ID_конкурса")
            return
        
        contest_id = parts[1].strip()
        
        if contest_id not in ACTIVE_CONTESTS:
            bot.send_message(message.chat.id, "❌ Конкурс не найден")
            return
        
        contest = ACTIVE_CONTESTS[contest_id]
        participants = len(CONTEST_PARTICIPANTS.get(contest_id, []))
        
        # Меняем статус
        ACTIVE_CONTESTS[contest_id]['status'] = 'cancelled'
        ACTIVE_CONTESTS[contest_id]['cancelled_at'] = time.time()
        
        # Создаем текст для уведомления
        cancel_text = f"""
❌ *КОНКУРС ОТМЕНЕН*

Конкурс в канале @{contest.get('channel_username', 'N/A')}
был отменен организатором.

Участников было: {participants}

👤 Организатор: {contest.get('creator_name', 'N/A')}
"""
        
        # Отправляем создателю для публикации
        bot.send_message(
            message.chat.id,
            cancel_text,
            parse_mode='Markdown'
        )
        
        bot.send_message(
            message.chat.id,
            f"✅ Конкурс отменен\n"
            f"Участников было: {participants}\n"
            f"📋 Текст для публикации отправлен выше"
        )
        
    except Exception as e:
        logging.error(f"Ошибка отмены конкурса: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка отмены конкурса")

# =============== КОМАНДА ДЛЯ ВЫВОДА ВСЕХ КОНКУРСОВ ===============

@bot.message_handler(func=lambda message: message.text.lower() == 'всеконкурсы' and is_admin(message.from_user.id))
def handle_all_contests(message):
    """Показывает все активные конкурсы"""
    try:
        active_contests = {k: v for k, v in ACTIVE_CONTESTS.items() if v.get('status') == 'active'}
        
        if not active_contests:
            bot.send_message(message.chat.id, "📭 Нет активных конкурсов")
            return
        
        contests_text = "🎯 *ВСЕ АКТИВНЫЕ КОНКУРСЫ:*\n\n"
        
        for i, (contest_id, contest) in enumerate(active_contests.items(), 1):
            participants = len(CONTEST_PARTICIPANTS.get(contest_id, []))
            contests_text += (
                f"{i}. *@{contest.get('channel_username', 'N/A')}*\n"
                f"   ID: `{contest_id}`\n"
                f"   Участников: {participants}/{contest.get('max_participants', 'N/A')}\n"
                f"   Создатель: {contest.get('creator_name', 'N/A')}\n\n"
            )
        
        bot.send_message(message.chat.id, contests_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка показа всех конкурсов: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка получения конкурсов")

# =============== АВТООЧИСТКА СТАРЫХ КОНКУРСОВ ===============

def cleanup_old_contests():
    """Очищает старые конкурсы"""
    while True:
        time.sleep(86400)  # Каждые 24 часа
        current_time = time.time()
        
        to_remove = []
        for contest_id, contest in ACTIVE_CONTESTS.items():
            # Удаляем завершенные конкурсы старше 7 дней
            created_at = contest.get('created_at', current_time)
            if contest.get('status') in ['finished', 'cancelled'] and current_time - created_at > 604800:
                to_remove.append(contest_id)
        
        for contest_id in to_remove:
            try:
                del ACTIVE_CONTESTS[contest_id]
            except:
                pass
                
            try:
                del CONTEST_PARTICIPANTS[contest_id]
            except:
                pass
            
            logging.info(f"Удален старый конкурс: {contest_id}")

# Запускаем очистку в отдельном потоке
contest_cleanup_thread = threading.Thread(target=cleanup_old_contests, daemon=True)
contest_cleanup_thread.start()
# =============== ИНФОРМАЦИЯ О КОНКУРСАХ ===============

@bot.message_handler(func=lambda message: message.text.lower() == 'конкурсы')
def handle_contests_info(message):
    """Информация о системе конкурсов"""
    info_text = """
🎯 *СИСТЕМА КОНКУРСОВ*

*Для организаторов (админов):*
`конкурс` — Создать новый конкурс
`моиконкурсы` — Ваши конкурсы
`всеконкурсы` — Все активные конкурсы

*Команды управления:*
`итоги ID` — Подвести итоги
`участники ID` — Участники конкурса
`отмена ID` — Отменить конкурс

*Как участвовать:*
1. Найдите пост конкурса в канале
2. Нажмите кнопку "УЧАСТВОВАТЬ"
3. Подпишитесь на канал если нужно
4. Ждите результатов!

*Особенности:*
• Бот проверяет подписку на канал
• Победители выбираются случайно
• Организатор публикует результаты
"""
    
    bot.send_message(message.chat.id, info_text, parse_mode='Markdown')

@bot.message_handler(commands=['start'])
def start(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        # Проверяем бан ДО создания пользователя
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}\nОбратитесь к администратору.")
            return
        
        # Проверяем есть ли реферальный код в ссылке
        ref_code = None
        if len(message.text.split()) > 1:
            ref_code = message.text.split()[1].strip()
            logging.info(f"Пользователь {user_id} пришел по ссылке с кодом: {ref_code}")
        
        # Получаем информацию о пользователе (без создания)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        is_new_user = False
        
        if not user_data:
            # Пользователь новый - создаем его БЕЗ КАПЧИ
            is_new_user = True
            
            # Если есть реф-код, сохраняем его во временный словарь
            if ref_code:
                pending_ref_codes[user_id] = ref_code
                logging.info(f"Сохранен реф-код для нового пользователя {user_id}: {ref_code}")
            
            # Создаем пользователя с капчей не пройденной
            referral_code = f"ref{user_id}"
            
            cursor.execute(
                'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp())
            )
            conn.commit()
            
            # Генерируем капчу
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            # Сообщение о капче
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для регистрации решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        # Пользователь существует, проверяем прошел ли он капчу
        captcha_passed = user_data[0]
        
        if captcha_passed == 0:
            # Пользователь существует, но не прошел капчу
            # Если есть реф-код, сохраняем его
            if ref_code:
                pending_ref_codes[user_id] = ref_code
                logging.info(f"Сохранен реф-код для существующего пользователя {user_id}: {ref_code}")
            
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для доступа к боту решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        # Пользователь существует и прошел капчу
        conn.close()
        
        # Обрабатываем реферальную ссылку или чек ТОЛЬКО ЕСЛИ ЕСТЬ КОД
        if ref_code:
            process_ref_or_check(user_id, username, first_name, ref_code)
        
        # Показываем главное меню
        markup = create_main_menu()
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)
    
    except Exception as e:
        logging.error(f"Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка. Попробуйте снова.")

def process_ref_or_check(user_id, username, first_name, ref_code):
    """Обрабатывает реферальную ссылку или чек после капчи"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Сначала проверяем, это чек?
        cursor.execute('SELECT amount, max_activations, current_activations FROM checks WHERE code = ?', (ref_code,))
        check_data = cursor.fetchone()
        
        if check_data:
            # Это чек
            amount, max_activations, current_activations = check_data
            
            # Проверяем, активировал ли пользователь уже этот чек
            cursor.execute('SELECT * FROM check_activations WHERE user_id = ? AND check_code = ?', (user_id, ref_code))
            already_activated = cursor.fetchone()
            
            if already_activated:
                bot.send_message(user_id, "❌ Вы уже активировали этот чек!")
            elif current_activations >= max_activations:
                bot.send_message(user_id, "❌ Чек уже использован максимальное количество раз!")
            else:
                # Активируем чек
                cursor.execute('UPDATE checks SET current_activations = current_activations + 1 WHERE code = ? AND current_activations < max_activations', (ref_code,))
                
                if cursor.rowcount > 0:
                    cursor.execute('INSERT OR IGNORE INTO check_activations (user_id, check_code) VALUES (?, ?)', (user_id, ref_code))
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
                    conn.commit()
                    
                    bot.send_message(user_id, f"🎉 Вы активировали чек на ❄️{format_balance(amount)}!")
                    logging.info(f"Пользователь {user_id} активировал чек {ref_code} на сумму {amount}")
                else:
                    bot.send_message(user_id, "❌ Чек уже был активирован другим пользователем!")
            
            conn.close()
            return
        
        # Если не чек, проверяем реферальную ссылку (начинается с ref)
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])  # Убираем 'ref' и получаем ID
                
                # Проверяем существует ли реферер и не забанен ли он
                cursor.execute('SELECT user_id, username, first_name FROM users WHERE user_id = ? AND is_banned = 0', (referrer_id,))
                referrer_data = cursor.fetchone()
                
                if referrer_data:
                    # Проверяем, не пытается ли пользователь сам себя пригласить
                    if referrer_id == user_id:
                        bot.send_message(user_id, "❌ Нельзя использовать свою реферальную ссылку!")
                        conn.close()
                        return
                    
                    # Проверяем, есть ли уже реферер у пользователя
                    cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,))
                    existing_referrer = cursor.fetchone()
                    
                    if existing_referrer and existing_referrer[0]:
                        bot.send_message(user_id, "❌ У вас уже есть реферер!")
                        conn.close()
                        return
                    
                    # Устанавливаем реферера
                    cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referrer_id, user_id))
                    
                    # Начисляем бонус рефереру
                    REFERRAL_BONUS = 450
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (REFERRAL_BONUS, referrer_id))
                    
                    conn.commit()
                    
                    # Уведомляем реферера
                    try:
                        referrer_username = referrer_data[1] if referrer_data[1] else referrer_data[2]
                        new_user_name = f"@{username}" if username else first_name
                        
                        bot.send_message(
                            referrer_id,
                            f"🎉 Новый реферал!\n"
                            f"👤 {new_user_name}\n"
                            f"💰 +{REFERRAL_BONUS}❄️\n\n"
                            f"Теперь у вас {get_referral_count(referrer_id)} рефералов!"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка уведомления реферера: {e}")
                    
                    # Уведомляем нового пользователя
                    bot.send_message(user_id, f"✅ Вы зарегистрировались по приглашению!")
                    
                    logging.info(f"Пользователь {user_id} зарегистрирован по реферальной ссылке от {referrer_id}")
                    
                else:
                    bot.send_message(user_id, "❌ Реферальная ссылка недействительна!")
                
            except ValueError:
                bot.send_message(user_id, "❌ Неверный формат реферальной ссылки!")
        else:
            bot.send_message(user_id, "❌ Неизвестный код!")
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка обработки реф/чека: {e}")
        try:
            conn.close()
        except:
            pass

def get_referral_count(user_id):
    """Получает количество рефералов пользователя"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ ТОПОВ ===
user_top_page = {}
user_top_mode = {}  # 'balance' или 'scam'

# === ФУНКЦИЯ ПОЛУЧЕНИЯ ТОПА БАЛАНСОВ ===
def get_balance_top_page(page=1, limit=5):
    """Получает топ пользователей по балансу"""
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT 
        user_id,
        CASE 
            WHEN username IS NOT NULL AND username != '' THEN '@' || username 
            ELSE first_name 
        END as display_name,
        balance,
        ROW_NUMBER() OVER (ORDER BY balance DESC) as position
    FROM users 
    WHERE balance > 0 AND is_banned = 0
    LIMIT ? OFFSET ?
    ''', (limit, offset))
    
    top_users = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE balance > 0 AND is_banned = 0')
    total_users = cursor.fetchone()[0]
    
    total_pages = (total_users + limit - 1) // limit
    
    conn.close()
    
    return {
        'users': top_users,
        'total': total_users,
        'current_page': page,
        'total_pages': total_pages
    }

# === ИСПРАВЛЕННАЯ ФУНКЦИЯ ПОЛУЧЕНИЯ ТОПА СКАМА ===
def get_scam_top_page(page=1, limit=5):
    """Получает топ пользователей по количеству рефералов"""
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Исправленный запрос для подсчета рефералов
    cursor.execute('''
    SELECT 
        u.user_id,
        CASE 
            WHEN u.username IS NOT NULL AND u.username != '' THEN '@' || u.username 
            ELSE u.first_name 
        END as display_name,
        COUNT(r.user_id) as ref_count,
        ROW_NUMBER() OVER (ORDER BY COUNT(r.user_id) DESC) as position
    FROM users u
    LEFT JOIN users r ON u.user_id = r.referred_by
    WHERE u.is_banned = 0 AND r.is_banned = 0
    GROUP BY u.user_id
    HAVING COUNT(r.user_id) > 0
    ORDER BY ref_count DESC
    LIMIT ? OFFSET ?
    ''', (limit, offset))
    
    top_scammers = cursor.fetchall()
    
    cursor.execute('''
    SELECT COUNT(DISTINCT u.user_id) 
    FROM users u
    JOIN users r ON u.user_id = r.referred_by
    WHERE u.is_banned = 0 AND r.is_banned = 0
    ''')
    total_scammers = cursor.fetchone()[0] or 1
    
    total_pages = (total_scammers + limit - 1) // limit
    
    conn.close()
    
    return {
        'users': top_scammers,
        'total': total_scammers,
        'current_page': page,
        'total_pages': total_pages
    }

# === ОБНОВЛЕННЫЙ ОБРАБОТЧИК /start ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ ===
@bot.message_handler(commands=['start'])
def start(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        # Проверяем бан ДО создания пользователя
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}\nОбратитесь к администратору.")
            return
        
        # Получаем информацию о пользователе (без создания)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        is_new_user = False
        
        if not user_data:
            # Пользователь новый - создаем его
            is_new_user = True
            referral_code = f"ref{user_id}"
            
            # ПРОВЕРЯЕМ РЕФЕРАЛЬНУЮ ССЫЛКУ
            referred_by = None
            if len(message.text.split()) > 1:
                ref_code = message.text.split()[1].strip()
                # Проверяем, это реферальная ссылка (начинается с ref)
                if ref_code.startswith('ref'):
                    try:
                        referrer_id = int(ref_code[3:])  # Убираем 'ref' и получаем ID
                        # Проверяем существует ли реферер
                        cursor.execute('SELECT user_id FROM users WHERE user_id = ? AND is_banned = 0', (referrer_id,))
                        if cursor.fetchone():
                            referred_by = referrer_id
                    except:
                        pass
            
            cursor.execute(
                'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc, referred_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp(), referred_by)
            )
            conn.commit()
            
            # Если есть реферер, начисляем ему бонус
            if referred_by:
                REFERRAL_BONUS = 450  # Бонус за реферала
                cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (REFERRAL_BONUS, referred_by))
                conn.commit()
                
                try:
                    # Уведомляем реферера
                    bot.send_message(referred_by, f"🎉 Новый реферал!\n👤 @{username if username else first_name}\n💰 +{REFERRAL_BONUS}❄️")
                except:
                    pass
            
            # После создания пользователя требуем капчу
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для регистрации решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        # Пользователь существует, проверяем прошел ли он капчу
        captcha_passed = user_data[0]
        
        if captcha_passed == 0:
            # Пользователь существует, но не прошел капчу (старый аккаунт)
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            conn.close()
            
            bot.send_message(message.chat.id, 
                           f"🔒 Для доступа к боту решите пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        # Пользователь существует и прошел капчу - сразу показываем меню
        conn.close()
        
        # Показываем главное меню
        markup = create_main_menu()
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка. Попробуйте снова.")

# === ГЛАВНЫЙ ОБРАБОТЧИК ТОПОВ ===
@bot.message_handler(func=lambda message: message.text in ["Топ снежков", "Топ скам"])
def handle_top_menu(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        user_id = message.from_user.id
        
        # Определяем режим
        if message.text == "Топ снежков":
            user_top_mode[user_id] = 'balance'
            title = "🎅 Топ снежков 🎅"
        else:  # "Топ скам"
            user_top_mode[user_id] = 'scam'
            title = "👥 Топ скама 👥"
        
        # Устанавливаем первую страницу
        user_top_page[user_id] = 1
        
        # Создаем сообщение с топом
        top_message = create_top_message(user_id, 1)
        
        # Создаем клавиатуру с пагинацией
        markup = create_top_keyboard(user_id, 1)
        
        bot.send_message(message.chat.id, top_message, reply_markup=markup, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_top_menu: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки топа. Попробуйте снова.")

# === СОЗДАНИЕ СООБЩЕНИЯ ТОПА ===
def create_top_message(user_id, page=1):
    """Создает сообщение с топом пользователей"""
    try:
        mode = user_top_mode.get(user_id, 'balance')
        
        if mode == 'balance':
            # Топ снежков
            top_data = get_balance_top_page(page, 5)
            title = "🎅 Топ снежков 🎅"
            empty_message = "📭 Топ пока пуст! Станьте первым!\n\nЗарабатывайте ❄️ в казино или работах"
        else:
            # Топ скама
            top_data = get_scam_top_page(page, 5)
            title = "👥 Топ скама 👥"
            empty_message = "📭 Топ скама пока пуст!\n\nПриглашайте друзей чтобы попасть в топ!"
        
        top_users = top_data['users']
        total_pages = top_data['total_pages']
        current_page = top_data['current_page']
        
        # Получаем позицию текущего пользователя
        user_position = get_user_position_in_top(user_id, mode)
        
        # Создаем сообщение
        message_text = f"<b>{title}</b>\n\n"
        
        if not top_users:
            message_text += empty_message
        else:
            # Добавляем места с эмодзи
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            
            for i, user in enumerate(top_users):
                if mode == 'balance':
                    user_id_db, display_name, value, position = user
                    value_text = f"⟨{format_balance(value)}❄️⟩"
                else:
                    user_id_db, display_name, value, position = user
                    value_text = f"⟨{value} скам⟩"
                
                # Определяем номер позиции на текущей странице
                page_position = ((page - 1) * 5) + i + 1
                
                # Используем эмодзи для первых позиций
                if page_position <= 3:
                    medal = medals[page_position-1]
                elif page_position <= 5:
                    medal = medals[page_position-1]
                else:
                    medal = f"{page_position}."
                
                # Форматируем имя
                if len(display_name) > 20:
                    display_name = display_name[:17] + "..."
                
                message_text += f"{medal} {display_name} {value_text}\n"
        
        # Добавляем информацию о текущей странице
        if total_pages > 1:
            message_text += f"\n📄 Страница {current_page}/{total_pages}"
        
        # Добавляем информацию о позиции пользователя
        if user_position:
            if mode == 'balance':
                # Получаем баланс пользователя
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                user_balance = cursor.fetchone()
                conn.close()
                
                if user_balance:
                    balance = user_balance[0] if user_balance[0] is not None else 0
                    message_text += f"\n\n🎯 <b>Твоя позиция:</b> #{user_position}\n"
                    message_text += f"💰 Баланс: {format_balance(balance)}❄️"
            else:
                # Получаем количество рефералов пользователя
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
                ref_count = cursor.fetchone()[0]
                conn.close()
                
                message_text += f"\n\n🎯 <b>Твоя позиция:</b> #{user_position if user_position > 0 else 'не в топе'}\n"
                message_text += f"👥 Рефералов: {ref_count}"
        
        return message_text
        
    except Exception as e:
        logging.error(f"Ошибка создания сообщения топа: {e}")
        return "❌ Ошибка загрузки топа. Попробуйте позже."

# === ФУНКЦИЯ ПОЛУЧЕНИЯ ПОЗИЦИИ ПОЛЬЗОВАТЕЛЯ ===
def get_user_position_in_top(user_id, mode='balance'):
    """Получает позицию пользователя в топе"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if mode == 'balance':
            cursor.execute('''
            SELECT position FROM (
                SELECT user_id, ROW_NUMBER() OVER (ORDER BY balance DESC) as position
                FROM users 
                WHERE balance > 0 AND is_banned = 0
            ) WHERE user_id = ?
            ''', (user_id,))
        else:
            cursor.execute('''
            SELECT position FROM (
                SELECT 
                    u.user_id,
                    ROW_NUMBER() OVER (ORDER BY COUNT(r.user_id) DESC) as position
                FROM users u
                LEFT JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
                WHERE u.is_banned = 0
                GROUP BY u.user_id
                HAVING COUNT(r.user_id) > 0
            ) WHERE user_id = ?
            ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
        
    except Exception as e:
        logging.error(f"Ошибка получения позиции пользователя: {e}")
        return None

# === СОЗДАНИЕ КЛАВИАТУРЫ ДЛЯ ТОПА ===
def create_top_keyboard(user_id, current_page):
    """Создает клавиатуру для навигации по топу"""
    markup = InlineKeyboardMarkup(row_width=3)
    
    # Определяем текущий режим
    mode = user_top_mode.get(user_id, 'balance')
    
    # Получаем общее количество страниц
    if mode == 'balance':
        top_data = get_balance_top_page(current_page, 5)
    else:
        top_data = get_scam_top_page(current_page, 5)
    
    total_pages = top_data['total_pages']
    
    # Кнопки навигации
    buttons = []
    
    if current_page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"top_page_{current_page-1}"))
    
    # Кнопка с номером страницы
    page_button_text = f"{current_page}/{total_pages}"
    if total_pages > 1:
        page_button_text = f"📄 {current_page}/{total_pages}"
    buttons.append(InlineKeyboardButton(page_button_text, callback_data="top_current"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"top_page_{current_page+1}"))
    
    # Если есть кнопки для отображения
    if buttons:
        markup.row(*buttons)
    
    # Кнопки переключения между топами
    mode_buttons = []
    if mode == 'balance':
        mode_buttons.append(InlineKeyboardButton("❄️ Снежки", callback_data="top_mode_balance"))
        mode_buttons.append(InlineKeyboardButton("👥 Скам", callback_data="top_mode_scam"))
    else:
        mode_buttons.append(InlineKeyboardButton("👥 Скам", callback_data="top_mode_scam"))
        mode_buttons.append(InlineKeyboardButton("❄️ Снежки", callback_data="top_mode_balance"))
    
    markup.row(*mode_buttons)
    
    # Кнопка обновления
    markup.row(InlineKeyboardButton("🔄 Обновить", callback_data="top_refresh"))
    
    return markup

# === ОБРАБОТЧИК КОЛБЭКОВ ДЛЯ ТОПА ===
@bot.callback_query_handler(func=lambda call: call.data.startswith('top_'))
def top_callback_handler(call):
    try:
        user_id = call.from_user.id
        
        if call.data.startswith('top_page_'):
            # Переход на страницу
            page = int(call.data.split('_')[2])
            
            # Обновляем страницу пользователя
            user_top_page[user_id] = page
            
            # Создаем новое сообщение
            top_message = create_top_message(user_id, page)
            markup = create_top_keyboard(user_id, page)
            
            bot.edit_message_text(
                top_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id)
            
        elif call.data.startswith('top_mode_'):
            # Переключение режима
            mode = call.data.split('_')[2]  # balance или scam
            
            # Обновляем режим
            user_top_mode[user_id] = mode
            user_top_page[user_id] = 1
            
            # Создаем новое сообщение
            top_message = create_top_message(user_id, 1)
            markup = create_top_keyboard(user_id, 1)
            
            bot.edit_message_text(
                top_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id, f"✅ Переключено на {'снежки' if mode == 'balance' else 'скам'}")
            
        elif call.data == 'top_refresh':
            # Обновление топа
            page = user_top_page.get(user_id, 1)
            top_message = create_top_message(user_id, page)
            markup = create_top_keyboard(user_id, page)
            
            bot.edit_message_text(
                top_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id, "✅ Топ обновлен!")
            
        elif call.data == 'top_current':
            # Просто показываем текущую страницу
            bot.answer_callback_query(call.id)
            
    except Exception as e:
        logging.error(f"Ошибка в top_callback_handler: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка обновления топа")
        except:
            pass


# === ОБНОВЛЕННЫЙ ОБРАБОТЧИК СКАМА ===
@bot.message_handler(func=lambda message: message.text == "👥 Скам")
def handle_scam(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            ref_code = result[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
            ref_count = cursor.fetchone()[0]
            
            REFERRAL_BONUS = 450  # Бонус за каждого реферала
            earned = ref_count * REFERRAL_BONUS
            
            ref_link = f"https://t.me/{(bot.get_me()).username}?start={ref_code}"
            
            message_text = f"👨🏻‍💻 Твоя скам-ссылка:\n{ref_link}\n(нажми на неё, чтобы скопировать)\n\n"
            message_text += f"📊 Статистика:\n"
            message_text += f"Заскамлено людей: {ref_count}\n"
            message_text += f"Заработано: {format_balance(earned)}❄️\n\n"
            message_text += "💡 Кидай ссылку друзьям и скамь их на бабки!"
            
            bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "❌ Реферальный код не найден")
        
        conn.close()
    except Exception as e:
        print(f"Ошибка в handle_scam: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка базы данных. Попробуйте снова.")
# =============== КОНЕЦ ОБРАБОТЧИКА ===============
# Обработчик команды "я"
@bot.message_handler(func=lambda message: message.text.lower() == "я")
def handle_me(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        # Начисляем проценты перед отображением
        calculate_interest(user_id)
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT first_name, balance, video_cards, bank_deposit FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            first_name, balance, video_cards, bank_deposit = result
            
            message_text = f"👤 Имя: {first_name}\n"
            message_text += f"Баланс: ❄️{format_balance(balance)}\n"
            message_text += f"Видеокарт: {video_cards}\n"
            message_text += f"🏦 В банке: ❄️{format_balance(bank_deposit)} (+0.5%/час)"
            
            # Пробуем отправить картинку с подписью
            try:
                with open('g.jpg', 'rb') as photo:
                    bot.send_photo(message.chat.id, photo, caption=message_text)
            except Exception as e:
                print(f"Ошибка при отправке фото: {e}")
                # Если картинки нет, отправляем только текст
                bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
    
    except Exception as e:
        print(f"Ошибка в handle_me: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка базы данных. Попробуйте снова.")
# Обработчик кнопки "Майнинг"
@bot.message_handler(func=lambda message: message.text == "Майнинг")
def handle_mining(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        # Просто показываем сообщение о разработке
        message_text = "🖥 Майнинг ферма\n\n"
        message_text += "⏳ Функция майнинга находится в разработке!\n"
        message_text += "Скоро здесь будет интересный функционал!\n\n"
        message_text += "💡 Следите за обновлениями!"
        
        bot.send_message(message.chat.id, message_text)
    
    except Exception as e:
        print(f"Ошибка в handle_mining: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка. Попробуйте снова.")

# Обработчик callback для майнинга (если остались старые callback'и)
@bot.callback_query_handler(func=lambda call: call.data.startswith('mining_'))
def mining_callback_handler(call):
    if is_spam(call.from_user.id):
        bot.answer_callback_query(call.id, "⏳ Слишком быстро! Подождите немного.")
        return
        
    user_id = call.from_user.id
    
    # Проверяем бан
    banned, reason = is_banned(user_id)
    if banned:
        bot.answer_callback_query(call.id, "🚫 Вы забанены!")
        return
    
    # Просто показываем сообщение о разработке
    bot.answer_callback_query(call.id, "⏳ Майнинг в разработке!")
    
    message_text = "🖥 Майнинг ферма\n\n"
    message_text += "⏳ Функция майнинга находится в разработке!\n"
    message_text += "Скоро здесь будет интересный функционал!\n\n"
    message_text += "💡 Следите за обновлениями!"
    
    # Если сообщение можно редактировать, редактируем его
    try:
        bot.edit_message_text(
            message_text,
            call.message.chat.id,
            call.message.message_id
        )
    except:
        # Если не получается редактировать, отправляем новое сообщение
        bot.send_message(call.message.chat.id, message_text)

# Обработчик кнопки "Работа"
@bot.message_handler(func=lambda message: message.text == "Работа")
def handle_work(message):
    if is_spam(message.from_user.id):
        return
    
    # Проверяем бан
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
        return
        
    bot.send_message(message.chat.id, "💼 Выберите способ заработка:", reply_markup=create_work_menu())

# Обработчик кнопки "◀️ Назад"
@bot.message_handler(func=lambda message: message.text == "◀️ Назад")
def handle_back(message):
    if is_spam(message.from_user.id):
        return
    
    # Проверяем бан
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
        return
        
    markup = create_main_menu()
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)

# Обработчик кнопки "🖱️ Кликер"
@bot.message_handler(func=lambda message: message.text == "🖱️ Кликер")
def handle_clicker(message):
    if is_spam(message.from_user.id):
        return
    
    # Проверяем бан
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
        return
        
    bot.send_message(message.chat.id, "🎯 Найди правильную кнопку:", reply_markup=create_clicker_keyboard())

# Обработчик callback для кликера
@bot.callback_query_handler(func=lambda call: call.data.startswith('clicker_'))
def clicker_callback_handler(call):
    if is_spam(call.from_user.id):
        bot.answer_callback_query(call.id, "⏳ Слишком быстро! Подождите немного.")
        return
        
    user_id = call.from_user.id
    
    # Проверяем бан
    banned, reason = is_banned(user_id)
    if banned:
        bot.answer_callback_query(call.id, "🚫 Вы забанены!")
        return
    
    symbol = call.data.split('_')[1]
    
    try:
        if symbol == "✅":
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT click_power, click_streak FROM users WHERE user_id = ?', (user_id,))
            click_power, click_streak = cursor.fetchone()
            
            new_streak = click_streak + 1
            cursor.execute('UPDATE users SET click_streak = ? WHERE user_id = ?', (new_streak, user_id))
            
            cursor.execute(
                'UPDATE users SET balance = balance + ?, last_click = ? WHERE user_id = ?',
                (click_power, time.time(), user_id)
            )
            conn.commit()
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            new_balance = cursor.fetchone()[0]
            
            conn.close()
            
            bot.answer_callback_query(call.id, "✅ Верно! +❄️" + format_balance(click_power))
            bot.edit_message_text(
                f"👻 Серия: {new_streak}\n❄️ Баланс: ❄️{format_balance(new_balance)}",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_clicker_keyboard()
            )
        else:
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET click_streak = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            bot.answer_callback_query(call.id, "❌ Неверно! Серия сброшена.")
            bot.edit_message_text(
                "❌ Неверный выбор! Серия сброшена.\n🎯 Найди правильную кнопку:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_clicker_keyboard()
            )
    
    except Exception as e:
        print(f"Ошибка в clicker_callback_handler: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка базы данных")


def create_work_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    clicker_button = KeyboardButton("🖱️ Кликер")
    scam_button = KeyboardButton("👥 Скам")
    snow_button = KeyboardButton("❄️ Чистка снега")
    back_button = KeyboardButton("◀️ Назад")
    markup.add(clicker_button, scam_button, snow_button, back_button)
    return markup

# =============== УЛУЧШЕННАЯ УБОРКА СНЕГА С ШТРАФАМИ ===============

# Глобальные переменные для снежной уборки
SNOW_COOLDOWN = {}  # {user_id: timestamp_end}
SNOW_JOBS = {}  # {user_id: {"clicks_left": X, "total_earnings": X, "completed": X, "current_earnings": X}}
SNOW_LAST_MESSAGE = {}  # {user_id: {"chat_id": X, "message_id": X, "timestamp": X}}

@bot.message_handler(func=lambda message: message.text == "❄️ Чистка снега")
def handle_snow_work_new(message):
    try:
        user_id = message.from_user.id
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        # Проверяем кулдаун
        current_time = time.time()
        if user_id in SNOW_COOLDOWN:
            cooldown_end = SNOW_COOLDOWN[user_id]
            if current_time < cooldown_end:
                time_left = int(cooldown_end - current_time)
                minutes = time_left // 60
                seconds = time_left % 60
                
                cool_msg = f"⏳ Отдых: {minutes}м {seconds}с"
                bot.send_message(message.chat.id, cool_msg)
                return
        
        # Проверяем активную работу
        if user_id in SNOW_JOBS:
            job = SNOW_JOBS[user_id]
            
            # Проверяем не устарело ли последнее сообщение (больше 30 секунд)
            if user_id in SNOW_LAST_MESSAGE:
                last_msg = SNOW_LAST_MESSAGE[user_id]
                if current_time - last_msg["timestamp"] > 30:
                    # Сообщение устарело - удаляем работу
                    del SNOW_JOBS[user_id]
                    bot.send_message(message.chat.id, "❄️ Прошлая уборка устарела\nНачните заново")
                    return
            
            # Показываем текущий прогресс
            progress_msg = get_snow_progress_message(job)
            markup = create_snow_keyboard(job["clicks_left"], job["current_earnings"])
            
            bot.send_message(message.chat.id, progress_msg, reply_markup=markup)
            return
        
        # Создаем новую работу
        completed_jobs = SNOW_JOBS.get(user_id, {}).get("completed", 0) if user_id in SNOW_JOBS else 0
        
        # Расчет заработка: 1000 + 50 за каждую предыдущую работу
        base_earnings = 1000
        bonus_per_job = 50
        earnings = base_earnings + (completed_jobs * bonus_per_job)
        
        # Создаем задание
        SNOW_JOBS[user_id] = {
            "clicks_left": 150,
            "clicks_done": 0,
            "total_earnings": earnings,
            "current_earnings": earnings,  # Текущий заработок (с учетом штрафов)
            "completed": completed_jobs,
            "start_time": current_time,
            "wrong_clicks": 0
        }
        
        # Статистика
        stats_msg = (
            f"❄️ УБОРКА СНЕГА\n\n"
            f"🎯 150 кликов\n"
            f"💰 {format_balance(earnings)}❄️\n"
            f"📈 Надбавка: +50❄️\n"
            f"❗ Штраф: -100❄️ за ошибку\n"
            f"🏆 Выполнено: {completed_jobs}"
        )
        
        markup = create_snow_keyboard(150, earnings)
        msg = bot.send_message(message.chat.id, stats_msg, reply_markup=markup)
        
        # Сохраняем ID сообщения
        SNOW_LAST_MESSAGE[user_id] = {
            "chat_id": msg.chat.id,
            "message_id": msg.message_id,
            "timestamp": current_time
        }
        
    except Exception as e:
        logging.error(f"Ошибка в уборке снега: {e}")
        bot.send_message(message.chat.id, "❄️ Ошибка")

def create_snow_keyboard(clicks_left, current_earnings):
    """Создает клавиатуру с 5 кнопками (1 снежинка + 4 ловушки)"""
    markup = InlineKeyboardMarkup(row_width=5)
    
    # Определяем позицию снежинки (случайно от 0 до 4)
    snow_position = random.randint(0, 4)
    
    buttons = []
    for i in range(5):
        if i == snow_position:
            # Снежинка
            buttons.append(InlineKeyboardButton("❄️", callback_data="snow_correct"))
        else:
            # Ловушки с разными символами
            trap_symbols = ["•", "○", "●", "◌"]
            trap_symbol = random.choice(trap_symbols)
            buttons.append(InlineKeyboardButton(trap_symbol, callback_data="snow_wrong"))
    
    markup.row(*buttons)
    
    # Добавляем кнопку с текущим заработком
    markup.row(InlineKeyboardButton(f"💰 {format_balance(current_earnings)}❄️", callback_data="snow_balance"))
    
    return markup

def get_snow_progress_message(job):
    """Создает сообщение о прогрессе уборки"""
    clicks_done = job["clicks_done"]
    progress_percent = (clicks_done / 150) * 100
    
    # Простой прогресс-бар
    filled = int(progress_percent / 6.67)  # 6.67% за каждый символ
    progress_bar = "🟦" * filled + "⬜" * (15 - filled)
    
    message = (
        f"❄️ {clicks_done}/150\n"
        f"{progress_bar}\n"
        f"💰 {format_balance(job['current_earnings'])}❄️\n"
        f"❌ Ошибок: {job['wrong_clicks']}"
    )
    
    return message

@bot.callback_query_handler(func=lambda call: call.data in ["snow_correct", "snow_wrong", "snow_balance"])
def handle_snow_click(call):
    try:
        user_id = call.from_user.id
        current_time = time.time()
        
        # Проверяем наличие работы
        if user_id not in SNOW_JOBS:
            bot.answer_callback_query(call.id, "❌ Работа не найдена")
            return
        
        # Проверяем не устарело ли сообщение
        if user_id in SNOW_LAST_MESSAGE:
            last_msg = SNOW_LAST_MESSAGE[user_id]
            if (last_msg["chat_id"] != call.message.chat.id or 
                last_msg["message_id"] != call.message.message_id):
                # Это не последнее сообщение
                bot.answer_callback_query(call.id, "❌ Сообщение устарело")
                return
        
        job = SNOW_JOBS[user_id]
        
        if call.data == "snow_balance":
            # Просто показываем баланс
            bot.answer_callback_query(call.id, f"💰 {format_balance(job['current_earnings'])}❄️")
            return
        
        elif call.data == "snow_wrong":
            # Клик на ловушку - ШТРАФ
            penalty = 100
            if job["current_earnings"] > penalty:
                job["current_earnings"] -= penalty
            else:
                job["current_earnings"] = 0  # Не может быть отрицательным
            
            job["wrong_clicks"] += 1
            
            # Обновляем клавиатуру
            markup = create_snow_keyboard(job["clicks_left"], job["current_earnings"])
            progress_msg = get_snow_progress_message(job)
            
            try:
                bot.edit_message_text(
                    progress_msg,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            except:
                # Сообщение уже устарело
                bot.answer_callback_query(call.id, "❌ Сообщение устарело")
                del SNOW_JOBS[user_id]
                return
            
            bot.answer_callback_query(call.id, f"💸 -100❄️")
            return
        
        # Клик на снежинку (правильный)
        job["clicks_left"] -= 1
        job["clicks_done"] += 1
        
        # Обновляем время последнего сообщения
        if user_id in SNOW_LAST_MESSAGE:
            SNOW_LAST_MESSAGE[user_id]["timestamp"] = current_time
        
        # Проверяем завершение работы
        if job["clicks_left"] <= 0:
            # Завершаем работу
            earnings = job["current_earnings"]
            
            if earnings > 0:  # Только если остался хоть какой-то заработок
                # Начисляем деньги
                update_balance(user_id, earnings)
                new_balance = get_balance(user_id)
            else:
                earnings = 0
                new_balance = get_balance(user_id)
            
            # Увеличиваем счетчик выполненных работ
            job["completed"] += 1
            
            # Устанавливаем кулдаун (3 минуты = 180 секунд)
            cooldown_duration = 180
            SNOW_COOLDOWN[user_id] = time.time() + cooldown_duration
            
            # Сохраняем статистику перед удалением
            completed_count = job["completed"]
            wrong_clicks = job["wrong_clicks"]
            
            # Удаляем работу
            del SNOW_JOBS[user_id]
            
            # Отправляем результат
            if earnings > 0:
                result_msg = (
                    f"✅ УБОРКА ЗАВЕРШЕНА!\n\n"
                    f"🎯 Кликов: 150\n"
                    f"❌ Ошибок: {wrong_clicks}\n"
                    f"💰 Заработано: {format_balance(earnings)}❄️\n"
                    f"📊 Баланс: {format_balance(new_balance)}❄️\n"
                    f"🏆 Уборок: {completed_count}\n\n"
                    f"⏳ Следующая через 3 мин"
                )
                bot.answer_callback_query(call.id, f"✅ +{format_balance(earnings)}❄️")
            else:
                result_msg = (
                    f"⚠️ УБОРКА ЗАВЕРШЕНА\n\n"
                    f"🎯 Кликов: 150\n"
                    f"❌ Ошибок: {wrong_clicks}\n"
                    f"💸 Все деньги потеряны!\n"
                    f"📊 Баланс: {format_balance(new_balance)}❄️\n\n"
                    f"⏳ Следующая через 3 мин"
                )
                bot.answer_callback_query(call.id, "💸 0❄️")
            
            try:
                bot.edit_message_text(
                    result_msg,
                    call.message.chat.id,
                    call.message.message_id
                )
            except:
                # Если не удалось редактировать, отправляем новое
                bot.send_message(call.message.chat.id, result_msg)
            
        else:
            # Продолжаем работу
            # Обновляем клавиатуру
            markup = create_snow_keyboard(job["clicks_left"], job["current_earnings"])
            progress_msg = get_snow_progress_message(job)
            
            try:
                bot.edit_message_text(
                    progress_msg,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            except:
                # Сообщение устарело
                bot.answer_callback_query(call.id, "❌ Сообщение устарело")
                return
            
            bot.answer_callback_query(call.id, "❄️")
            
    except Exception as e:
        logging.error(f"Ошибка в клике снега: {e}")
        bot.answer_callback_query(call.id, "❌")

# =============== КОМАНДА ДЛЯ СБРОСА ===============

@bot.message_handler(func=lambda message: message.text.lower() == "сбросснег")
def handle_snow_reset(message):
    """Сбрасывает зависшую работу"""
    user_id = message.from_user.id
    
    if user_id in SNOW_JOBS:
        del SNOW_JOBS[user_id]
        if user_id in SNOW_LAST_MESSAGE:
            del SNOW_LAST_MESSAGE[user_id]
        bot.send_message(message.chat.id, "✅ Уборка сброшена")
    else:
        bot.send_message(message.chat.id, "⚠️ Нет активной уборки")

# =============== КОМАНДА ДЛЯ СТАТИСТИКИ ===============

@bot.message_handler(func=lambda message: message.text.lower() == "снегстат")
def handle_snow_stat(message):
    """Показывает статистику уборки снега"""
    user_id = message.from_user.id
    
    message_text = "❄️ СТАТИСТИКА\n\n"
    
    if user_id in SNOW_JOBS:
        job = SNOW_JOBS[user_id]
        
        message_text += f"📊 Активная уборка:\n"
        message_text += f"🎯 {job['clicks_done']}/150\n"
        message_text += f"💰 {format_balance(job['current_earnings'])}❄️\n"
        message_text += f"❌ Ошибок: {job['wrong_clicks']}\n"
        message_text += f"🏆 Всего уборок: {job['completed']}"
    else:
        message_text += "📭 Нет активной уборки\n"
        message_text += "💡 Начните через 'Работа'"
    
    # Показываем кулдаун
    if user_id in SNOW_COOLDOWN:
        cooldown_end = SNOW_COOLDOWN[user_id]
        current_time = time.time()
        
        if current_time < cooldown_end:
            time_left = int(cooldown_end - current_time)
            minutes = time_left // 60
            seconds = time_left % 60
            
            message_text += f"\n\n⏳ До следующей: {minutes}м {seconds}с"
    
    bot.send_message(message.chat.id, message_text)

# =============== АВТООЧИСТКА ===============

def cleanup_snow_data():
    """Очищает старые данные уборки снега"""
    while True:
        time.sleep(60)  # Каждую минуту
        current_time = time.time()
        
        # Очищаем старые работы (старше 30 минут)
        snow_to_remove = []
        for user_id, job in SNOW_JOBS.items():
            if current_time - job.get("start_time", current_time) > 1800:
                snow_to_remove.append(user_id)
        
        for user_id in snow_to_remove:
            del SNOW_JOBS[user_id]
            if user_id in SNOW_LAST_MESSAGE:
                del SNOW_LAST_MESSAGE[user_id]
        
        # Очищаем устаревшие сообщения (старше 1 часа)
        msg_to_remove = []
        for user_id, msg_data in SNOW_LAST_MESSAGE.items():
            if current_time - msg_data.get("timestamp", current_time) > 3600:
                msg_to_remove.append(user_id)
        
        for user_id in msg_to_remove:
            del SNOW_LAST_MESSAGE[user_id]
        
        # Очищаем старые кулдауны (старше 4 часов)
        cooldown_to_remove = []
        for user_id, cooldown_end in SNOW_COOLDOWN.items():
            if current_time > cooldown_end + 14400:  # 4 часа после окончания
                cooldown_to_remove.append(user_id)
        
        for user_id in cooldown_to_remove:
            del SNOW_COOLDOWN[user_id]

# Запускаем очистку в отдельном потоке
snow_cleanup_thread = threading.Thread(target=cleanup_snow_data, daemon=True)
snow_cleanup_thread.start()
# Обработчик кнопки "Банк"
@bot.message_handler(func=lambda message: message.text == "Банк")
def handle_bank(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        bank_deposit = get_bank_deposit(user_id)
        
        bank_text = f"""🏦 Банковские услуги:

❄️ На вкладе: ❄️{format_balance(bank_deposit)}
📈 Проценты: 0.5% каждый час
❄️ Начисляются автоматически при любом действии

📝 Команды:
• вклад [сумма] - положить под 0.5% в час
• снять [сумма] - забрать с вклада"""
        
        bot.send_message(message.chat.id, bank_text)
    except Exception as e:
        print(f"Ошибка в handle_bank: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка базы данных. Попробуйте снова.")

# Обработчик команды "вклад"
@bot.message_handler(func=lambda message: message.text.lower().startswith('вклад '))
def handle_deposit(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        bank_deposit = get_bank_deposit(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: вклад 1000к")
            return
        
        deposit_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if deposit_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if deposit_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if deposit_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств на балансе")
            return
        
        update_balance(user_id, -deposit_amount)
        update_bank_deposit(user_id, deposit_amount)
        
        new_balance = get_balance(user_id)
        new_deposit = get_bank_deposit(user_id)
        
        bot.send_message(message.chat.id,
                       f"✅ Вы положили ❄️{format_balance(deposit_amount)} на вклад под 0.5% в час\n"
                       f"❄️ На вкладе: ❄️{format_balance(new_deposit)}\n"
                       f"❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_deposit: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в операции. Попробуйте снова.")

# Обработчик команды "снять"
@bot.message_handler(func=lambda message: message.text.lower().startswith('снять '))
def handle_withdraw(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        bank_deposit = get_bank_deposit(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: снять 1000к")
            return
        
        withdraw_amount = parse_bet_amount(' '.join(parts[1:]), bank_deposit)
        
        if withdraw_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if withdraw_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if withdraw_amount > bank_deposit:
            bot.send_message(message.chat.id, "❌ Недостаточно средств на вкладе")
            return
        
        update_balance(user_id, withdraw_amount)
        update_bank_deposit(user_id, -withdraw_amount)
        
        new_balance = get_balance(user_id)
        new_deposit = get_bank_deposit(user_id)
        
        bot.send_message(message.chat.id,
                       f"✅ Вы сняли ❄️{format_balance(withdraw_amount)} с вклада\n"
                       f"❄️ Осталось на вкладе: ❄️{format_balance(new_deposit)}\n"
                       f"❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_withdraw: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в операции. Попробуйте снова.")

# Обработчик кнопки "Казино"
@bot.message_handler(func=lambda message: message.text == "Казино")
def handle_casino(message):
    if is_spam(message.from_user.id):
        bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
        return
        
    casino_text = """🎰 Казино:

Добро пожаловать в казино!
Ознакомьтесь с командами. Желаем приятно провести время!

📝 Команды:
• рул/рулетка [тип ставки] [сумма]
Примеры ставок:
рул кра/красный 1000к
рул чер/черный все
рул бол/большие 1кк
рул мал/малые 1ккк

• куб [число] [сумма]
куб 1 1000к
куб 6 все
куб чет/нечет все

• слот/слоты [сумма]
слот 1000к

• бск/баскетбол [сумма]
бск 1000к

• фтб/футбол [сумма]
фтб 1000к

• дартс [сумма]
дартс 1000к

• боул/боулинг [сумма]
боул 1000к"""
    
    bot.send_message(message.chat.id, casino_text)
# Обработчик рулетки
@bot.message_handler(func=lambda message: message.text.lower().startswith(('рул ', 'рулетка ')))
def handle_roulette(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
            return
            
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: рул красный 1000к")
            return
        
        bet_type = parts[1]
        bet_amount = parse_bet_amount(' '.join(parts[2:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма ставки должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств для ставки")
            return
        
        # Сразу списываем ставку с баланса
        update_balance(user_id, -bet_amount)
        
        # Генерируем случайное число рулетки (0-36)
        winning_number = random.randint(0, 36)
        
        win = False
        multiplier = 1
        bet_type_name = ""
        
        # Определяем цвет выпавшего числа
        red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
        
        # Сначала пробуем распознать как число (0-36)
        try:
            number_bet = int(bet_type)
            if 0 <= number_bet <= 36:
                win = winning_number == number_bet
                multiplier = 36  # ×36 за угаданное число
                bet_type_name = f"число {number_bet}"
            else:
                bot.send_message(message.chat.id, "❌ Число должно быть от 0 до 36")
                update_balance(user_id, bet_amount)  # Возвращаем ставку
                return
        except ValueError:
            # Если не число, проверяем другие типы ставок
            if bet_type in ['красный', 'крас', 'кра', 'кр', 'к']:
                win = winning_number in red_numbers
                multiplier = 2
                bet_type_name = "красный"
            elif bet_type in ['черный', 'чер', 'черн', 'ч', 'чр']:
                win = winning_number in black_numbers
                multiplier = 2
                bet_type_name = "черный"
            elif bet_type in ['зеленый', 'зел', 'з', '0', 'зеро', 'ноль']:
                win = winning_number == 0
                multiplier = 36
                bet_type_name = "зеленый (0)"
            elif bet_type in ['большие', 'бол', 'б', 'бльш']:
                win = winning_number >= 19 and winning_number <= 36
                multiplier = 2
                bet_type_name = "большие (19-36)"
            elif bet_type in ['малые', 'мал', 'м', 'мл']:
                win = winning_number >= 1 and winning_number <= 18
                multiplier = 2
                bet_type_name = "малые (1-18)"
            elif bet_type in ['чет', 'четные', 'четн', 'ч']:
                # Четные: числа от 1 до 36, которые делятся на 2
                win = winning_number % 2 == 0 and winning_number != 0  # 0 не считается четным!
                multiplier = 2
                bet_type_name = "четные"
            elif bet_type in ['нечет', 'нечетные', 'неч', 'н', 'нечетн']:
                # Нечетные: числа от 1 до 36, которые не делятся на 2
                win = winning_number % 2 == 1 and winning_number != 0  # 0 не считается нечетным!
                multiplier = 2
                bet_type_name = "нечетные"
            else:
                bot.send_message(message.chat.id, "❌ Неверный тип ставки. Доступно: красный, черный, зеленый, большие, малые, чет, нечет, или число 0-36")
                update_balance(user_id, bet_amount)  # Возвращаем ставку
                return
        
        # Определяем цвет для сообщения
        color = "🔴" if winning_number in red_numbers else "⚫" if winning_number in black_numbers else "🟢"
        
        if win:
            win_amount = bet_amount * multiplier
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            
            # Пытаемся найти и отправить изображение
            image_path = get_roulette_photo(winning_number)
            
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"🎉 Ставка на {bet_type_name} выиграла!\n"
                                   f"🎯 Выпало: {winning_number} {color}\n"
                                   f"💰 Вы выиграли ❄️{format_balance(win_amount)}!\n"
                                   f"❄️ Баланс: ❄️{format_balance(new_balance)}"
                        )
                except Exception as e:
                    logging.error(f"Ошибка отправки фото рулетки: {e}")
                    # Если не удалось отправить фото, отправляем текст
                    bot.send_message(message.chat.id, 
                                   f"🎉 Ставка на {bet_type_name} выиграла!\n"
                                   f"🎯 Выпало: {winning_number} {color}\n"
                                   f"💰 Вы выиграли ❄️{format_balance(win_amount)}!\n"
                                   f"❄️ Баланс: ❄️{format_balance(new_balance)}")
            else:
                # Если изображение не найдено, отправляем только текст
                bot.send_message(message.chat.id, 
                               f"🎉 Ставка на {bet_type_name} выиграла!\n"
                               f"🎯 Выпало: {winning_number} {color}\n"
                               f"💰 Вы выиграли ❄️{format_balance(win_amount)}!\n"
                               f"❄️ Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            
            # Пытаемся найти и отправить изображение
            image_path = get_roulette_photo(winning_number)
            
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"❌ Ставка на {bet_type_name} проиграла!\n"
                                   f"🎯 Выпало: {winning_number} {color}\n"
                                   f"💸 Вы проиграли ❄️{format_balance(bet_amount)}.\n"
                                   f"❄️ Баланс: ❄️{format_balance(new_balance)}"
                        )
                except Exception as e:
                    logging.error(f"Ошибка отправки фото рулетки: {e}")
                    bot.send_message(message.chat.id, 
                                   f"❌ Ставка на {bet_type_name} проиграла!\n"
                                   f"🎯 Выпало: {winning_number} {color}\n"
                                   f"💸 Вы проиграли ❄️{format_balance(bet_amount)}.\n"
                                   f"❄️ Баланс: ❄️{format_balance(new_balance)}")
            else:
                bot.send_message(message.chat.id, 
                               f"❌ Ставка на {bet_type_name} проиграла!\n"
                               f"🎯 Выпало: {winning_number} {color}\n"
                               f"💸 Вы проиграли ❄️{format_balance(bet_amount)}.\n"
                               f"❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        logging.error(f"Ошибка в handle_roulette: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")

def get_roulette_photo(winning_number):
    """Найти файл изображения для числа рулетки"""
    try:
        # Прямой путь к файлу в /app
        filename = f"{winning_number}.png"
        filepath = f"/app/{filename}"
        
        # Проверяем существует ли файл
        if os.path.exists(filepath):
            logging.info(f"✅ Найдено изображение рулетки: {filepath}")
            return filepath
        
        # Если не нашли .png, проверяем другие форматы
        other_formats = ['.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']
        for ext in other_formats:
            filename = f"{winning_number}{ext}"
            filepath = f"/app/{filename}"
            if os.path.exists(filepath):
                logging.info(f"✅ Найдено изображение рулетки: {filepath}")
                return filepath
        
        # Пробуем в текущей директории
        current_dir = os.getcwd()
        for ext in ['.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']:
            filename = f"{winning_number}{ext}"
            filepath = os.path.join(current_dir, filename)
            if os.path.exists(filepath):
                logging.info(f"✅ Найдено изображение рулетки: {filepath}")
                return filepath
        
        logging.warning(f"❌ Изображение для числа {winning_number} не найдено")
        return None
        
    except Exception as e:
        logging.error(f"Ошибка поиска изображения рулетки: {e}")
        return None

# Обработчик костей
@bot.message_handler(func=lambda message: message.text.lower().startswith(('куб ', 'кубик ')))
def handle_dice(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: куб 1 1000к или куб бол все")
            return
        
        bet_type = parts[1]
        bet_amount = parse_bet_amount(' '.join(parts[2:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма ставки должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств для ставки")
            return
        
        # Сразу списываем ставку с баланса
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎲')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1
        
        # Проверяем тип ставки
        if bet_type in ['бол', 'большие', 'больше', 'б']:
            # Большие: 4, 5, 6
            win = result in [4, 5, 6]
            multiplier = 2
            bet_type_name = "большие (4-5-6)"
        
        elif bet_type in ['мал', 'малые', 'меньше', 'м']:
            # Малые: 1, 2, 3
            win = result in [1, 2, 3]
            multiplier = 2
            bet_type_name = "малые (1-2-3)"
        
        elif bet_type in ['чет', 'четные', 'четн', 'ч']:
            # Четные: 2, 4, 6
            win = result in [2, 4, 6]
            multiplier = 2
            bet_type_name = "четные"
        
        elif bet_type in ['нечет', 'нечетные', 'неч', 'н']:
            # Нечетные: 1, 3, 5
            win = result in [1, 3, 5]
            multiplier = 2
            bet_type_name = "нечетные"
        
        else:
            try:
                target = int(bet_type)
                if 1 <= target <= 6:
                    # Конкретное число
                    win = result == target
                    multiplier = 6
                    bet_type_name = f"число {target}"
                else:
                    bot.send_message(message.chat.id, "❌ Неверный тип ставки. Доступно: 1-6, бол, мал, чет, нечет")
                    # Возвращаем ставку при ошибке
                    update_balance(user_id, bet_amount)
                    return
            except:
                bot.send_message(message.chat.id, "❌ Неверный тип ставки. Доступно: 1-6, бол, мал, чет, нечет")
                # Возвращаем ставку при ошибке
                update_balance(user_id, bet_amount)
                return
        
        if win:
            win_amount = bet_amount * multiplier
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 Ставка на {bet_type_name} выиграла! Выпало: {result}\nВы выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Ставка на {bet_type_name} проиграла! Выпало: {result}\nВы проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_dice: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")

# Обработчик слотов
@bot.message_handler(func=lambda message: message.text.lower().startswith(('слот ', 'слоты ')))
def handle_slots(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: слот 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма ставки должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств для ставки")
            return
        
        # Сразу списываем ставку с баланса
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎰')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1
        
        if result == 1:  # Джекпот
            win = True
            multiplier = 64
        elif result == 22:  # Три семерки
            win = True
            multiplier = 10
        elif result == 43:  # Три вишни
            win = True
            multiplier = 5
        elif result == 64:  # Три одинаковых символа
            win = True
            multiplier = 3
        
        if win:
            win_amount = bet_amount * multiplier
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 Вы выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Вы проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_slots: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")

# Обработчик баскетбола
@bot.message_handler(func=lambda message: message.text.lower().startswith(('бск ', 'баскетбол ')))
def handle_basketball(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: бск 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма ставки должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств для ставки")
            return
        
        # Сразу списываем ставку с баланса
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🏀')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 2.5  # Изменено с 2 на 2.5
        
        if result == 4 or result == 5:  # Попадание
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 Вы выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Вы проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_basketball: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")

# Обработчик футбола
@bot.message_handler(func=lambda message: message.text.lower().startswith(('фтб ', 'футбол ')))
def handle_football(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: фтб 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма ставки должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств для ставки")
            return
        
        # Сразу списываем ставку с баланса
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='⚽')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1.5  # Коэффициент выигрыша
        
        # В футболе значения кубика:
        # 1 - мяч за пределами поля
        # 2 - мяч попал в штангу
        # 3 - гол (левая сторона)
        # 4 - гол (правая сторона) 
        # 5 - гол (центр)
        # 6 - мяч заблокирован вратарем
        
        # Все голы (3, 4, 5) считаются победой
        if result == 3 or result == 4 or result == 5:  # Гол
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 ГОООЛ! Вы выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Мяч не забит! Вы проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_football: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")

# Обработчик дартса
@bot.message_handler(func=lambda message: message.text.lower().startswith('дартс '))
def handle_darts(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: дартс 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма ставки должна быть больше 0")
            return
        
        # Проверяем хватит ли денег на максимальный проигрыш (двойная ставка для полного промаха)
        max_possible_loss = bet_amount * 2  # В худшем случае (полный промах)
        if max_possible_loss > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно средств для ставки!\n"
                           f"Нужно минимум: ❄️{format_balance(max_possible_loss)}\n"
                           f"Ваш баланс: ❄️{format_balance(balance)}\n"
                           f"💡 При полном промахе списывается двойная ставка!")
            return
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎯')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        # Значения кубика дартса в Telegram:
        # 1: полный промах (вообще не попал в мишень) → ДВОЙНАЯ СТАВКА
        # 4: попадание во внешнее кольцо → ПРОИГРЫШ СТАВКИ
        # 5: попадание во внутреннее кольцо → ПРОИГРЫШ СТАВКИ
        # 6: попадание в яблочко (центр) → ВЫИГРЫШ ×5
        
        # Сразу списываем базовую ставку
        update_balance(user_id, -bet_amount)
        
        if result == 6:  # Яблочко (центр) - ВЫИГРЫШ ×5
            win_amount = bet_amount * 5
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            
            bot.send_message(message.chat.id, 
                           f"🎯 ПОПАДАНИЕ В ЯБЛОЧКО! 🎯\n"
                           f"✅ Вы выиграли ❄️{format_balance(win_amount)}!\n"
                           f"💰 Ставка: ❄️{format_balance(bet_amount)}\n"
                           f"📈 Коэффициент: ×5\n"
                           f"❄️ Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 1:  # Полный промах - ДВОЙНАЯ СТАВКА
            # Уже списали базовую ставку, списываем еще одну
            update_balance(user_id, -bet_amount)
            total_loss = bet_amount * 2
            new_balance = get_balance(user_id)
            
            bot.send_message(message.chat.id, 
                           f"🎯 ПОЛНЫЙ ПРОМАХ! 🎯\n"
                           f"❌ Вы вообще не попали в мишень!\n"
                           f"💸 Списанно: ❄️{format_balance(total_loss)} (двойная ставка)\n"
                           f"💰 Ставка: ❄️{format_balance(bet_amount)}\n"
                           f"📉 Штраф: ×2\n"
                           f"❄️ Баланс: ❄️{format_balance(new_balance)}")
        
        else:  # 4 или 5 - попадание в кольцо, но не в центр
            new_balance = get_balance(user_id)
            
            if result == 5:
                ring = "внутреннее кольцо"
            else:  # result == 4
                ring = "внешнее кольцо"
            
            bot.send_message(message.chat.id, 
                           f"🎯 Попадание в {ring}\n"
                           f"❌ Вы проиграли ставку\n"
                           f"💸 Списанно: ❄️{format_balance(bet_amount)}\n"
                           f"❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_darts: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")
# Обработчик боулинга
@bot.message_handler(func=lambda message: message.text.lower().startswith(('боул ', 'боулинг ')))
def handle_bowling(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите 1 секунду между командами.")
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: боул 1000к")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма ставки")
            return
        
        if bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма ставки должна быть больше 0")
            return
        
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств для ставки")
            return
        
        # Сразу списываем ставку с баланса
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎳')
        time.sleep(3)
        
        result = dice_message.dice.value
        
        # Значения кубика боулинга в Telegram и сколько кеглей осталось:
        # 6 - страйк (все 10 кеглей сбиты) = 0 осталось
        # 5 - сбито 9 кеглей = 1 осталась
        # 4 - сбито 7-8 кеглей = 2-3 осталось
        # 3 - сбито 5-6 кеглей = 4-5 осталось
        # 2 - сбито 3-4 кегли = 6-7 осталось
        # 1 - сбито 1-2 кегли = 8-9 осталось
        
        if result == 6:  # Все кегли сбиты (0 осталось)
            win_amount = bet_amount * 2  # ×2 за страйк
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎳 СТРАЙК! Все кегли сбиты! Вы выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 5:  # 9 кеглей сбито (1 осталась)
            # Возврат ставки
            update_balance(user_id, bet_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"⚖️ Осталась 1 кегля! Возврат ставки ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 1:  # 1-2 кегли сбито (8-9 осталось)
            # Это тоже "почти все" по вашей логике? 
            # Если да, то возвращаем ставку, если нет - оставляем проигрыш
            # Здесь оставляю проигрыш, так как сбито мало кеглей
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Сбито всего 1-2 кегли! Осталось 8-9. Вы проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
        
        else:  # result 2, 3, 4 - проигрыш (осталось 2+ кеглей)
            new_balance = get_balance(user_id)
            # Определяем сколько примерно кеглей осталось
            if result == 2:
                remaining = "6-7 кеглей"
            elif result == 3:
                remaining = "4-5 кеглей"
            elif result == 4:
                remaining = "2-3 кегли"
            else:
                remaining = "кеглей"
            
            bot.send_message(message.chat.id, f"❌ Осталось {remaining}! Вы проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_bowling: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")

# Обработчик команды "чек" (для пользователей)
@bot.message_handler(func=lambda message: message.text.lower().startswith('чек ') and not is_admin(message.from_user.id))
def handle_check(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: чек 10ккк 2")
            return
        
        # Парсим сумму
        amount = parse_bet_amount(parts[1], balance)
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        # Парсим количество активаций
        try:
            activations = int(parts[2])
            if activations <= 0 or activations > 100:
                bot.send_message(message.chat.id, "❌ Количество активаций должно быть от 1 до 100")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверное количество активаций")
            return
        
        # Рассчитываем общую сумму для списания
        total_amount = amount * activations
        
        if total_amount > balance:
            bot.send_message(message.chat.id, f"❌ Недостаточно средств для создания чека! Нужно: ❄️{format_balance(total_amount)}")
            return
        
        # Списываем общую сумму с баланса
        update_balance(user_id, -total_amount)
        
        # Генерируем случайный код чека
        code = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Создаем чек
        cursor.execute(
            'INSERT INTO checks (code, amount, max_activations, created_by) VALUES (?, ?, ?, ?)',
            (code, amount, activations, user_id)
        )
        
        conn.commit()
        conn.close()
        
        check_link = f"https://t.me/{(bot.get_me()).username}?start={code}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Активировать❄️", url=check_link))
        
        bot.send_message(message.chat.id,
                f"💳 Чек создан!\n"
                f"❄️ Сумма: ❄️{format_balance(amount)}\n"
                f"🔢 Активаций: {activations}\n",  # <-- Добавьте запятую здесь
                reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в создании чека: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании чека. Попробуйте снова.")

# Обработчик команды "чек" для админов
@bot.message_handler(func=lambda message: message.text.lower().startswith('чеф ') and is_admin(message.from_user.id))
def handle_admin_check(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: чек 1000к 10")
            return
        
        # Парсим сумму
        amount = parse_bet_amount(parts[1], float('inf'))
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        # Парсим количество активаций
        try:
            max_activations = int(parts[2])
            if max_activations <= 0:
                bot.send_message(message.chat.id, "❌ Количество активаций должно быть больше 0")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверное количество активаций")
            return
        
        check_code = f"check{random.randint(100000, 999999)}"
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO checks (code, amount, max_activations, created_by) VALUES (?, ?, ?, ?)',
            (check_code, amount, max_activations, message.from_user.id)
        )
        conn.commit()
        conn.close()
        
        check_link = f"https://t.me/{(bot.get_me()).username}?start={check_code}"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Активировать❄️", url=check_link))
        
        bot.send_message(message.chat.id, 
                f"✅ Чек\n"
                f"❄️ Сумма за активацию: ❄️{format_balance(amount)}\n"
                f"🔢 Активаций: {max_activations}\n",  # <-- Добавьте запятую
                reply_markup=markup)
                       
    
    except Exception as e:
        print(f"Ошибка в handle_admin_check: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании чека")

# Обработчик команды "выдать" для админов
@bot.message_handler(func=lambda message: message.text.lower().startswith('выдать ') and is_admin(message.from_user.id))
def handle_give_money(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: выдать @username 1000к")
            return
        
        target = parts[1]
        amount = parse_bet_amount(' '.join(parts[2:]), float('inf'))
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        if target.startswith('@'):
            cursor.execute('UPDATE users SET balance = balance + ? WHERE username = ?', (amount, target[1:]))
        else:
            try:
                target_id = int(target)
                cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, target_id))
            except:
                bot.send_message(message.chat.id, "❌ Неверный ID пользователя")
                conn.close()
                return
        
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ Выдано ❄️{format_balance(amount)} пользователю {target}")
    
    except Exception as e:
        print(f"Ошибка в handle_give_money: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при выдаче денег")

# Обработчик команды "забрать" для админов
@bot.message_handler(func=lambda message: message.text.lower().startswith('забрать ') and is_admin(message.from_user.id))
def handle_take_money(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        if not message.reply_to_message:
            bot.send_message(message.chat.id, "❌ Ответьте на сообщение пользователя, у которого хотите забрать деньги")
            return
        
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username
        target_first_name = message.reply_to_message.from_user.first_name
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: забрать 1000к")
            return
        
        amount = parse_bet_amount(' '.join(parts[1:]), float('inf'))
        
        if amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        # Создаем пользователя если его нет
        get_or_create_user(target_user_id, target_username, target_first_name)
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Проверяем баланс пользователя
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (target_user_id,))
        user_balance = cursor.fetchone()
        
        if user_balance:
            balance = user_balance[0]
            if balance < amount:
                bot.send_message(message.chat.id, f"❌ У пользователя недостаточно средств! Баланс: ❄️{format_balance(balance)}")
                conn.close()
                return
            
            # Забираем деньги
            cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, target_user_id))
            conn.commit()
            
            # Получаем новое имя пользователя
            target_name = f"@{target_username}" if target_username else target_first_name
            
            bot.send_message(message.chat.id, 
                           f"✅ Забрано ❄️{format_balance(amount)} у пользователя {target_name}\n"
                           f"❄️ Новый баланс пользователя: ❄️{format_balance(balance - amount)}")
            
            # Уведомляем пользователя
            try:
                bot.send_message(target_user_id, 
                               f"⚠️ У вас забрали ❄️{format_balance(amount)} администратором\n"
                               f"❄️ Новый баланс: ❄️{format_balance(balance - amount)}")
            except:
                pass
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_take_money: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при заборе денег")

# Обработчик команды "бан" для админов
@bot.message_handler(func=lambda message: message.text.lower().startswith('бан ') and is_admin(message.from_user.id))
def handle_ban(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        if not message.reply_to_message:
            bot.send_message(message.chat.id, "❌ Ответьте на сообщение пользователя, которого хотите забанить")
            return
        
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username
        target_first_name = message.reply_to_message.from_user.first_name
        
        parts = message.text.split()
        ban_reason = "Нарушение правил"
        if len(parts) > 1:
            ban_reason = ' '.join(parts[1:])
        
        # Создаем пользователя если его нет
        get_or_create_user(target_user_id, target_username, target_first_name)
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Баним пользователя
        cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                      (ban_reason, target_user_id))
        conn.commit()
        conn.close()
        
        target_name = f"@{target_username}" if target_username else target_first_name
        
        bot.send_message(message.chat.id, 
                       f"✅ Пользователь {target_name} забанен!\n"
                       f"📝 Причина: {ban_reason}")
        
        # Уведомляем пользователя
        try:
            bot.send_message(target_user_id, 
                           f"🚫 Вы забанены в боте!\n"
                           f"📝 Причина: {ban_reason}\n"
                           f"⏰ Время бана: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                           f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
        except:
            pass
    
    except Exception as e:
        print(f"Ошибка в handle_ban: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при бане пользователя")

# Обработчик команды "разбан" для админов
@bot.message_handler(func=lambda message: message.text.lower().startswith('разбан ') and is_admin(message.from_user.id))
def handle_unban(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        if not message.reply_to_message:
            bot.send_message(message.chat.id, "❌ Ответьте на сообщение пользователя, которого хотите разбанить")
            return
        
        target_user_id = message.reply_to_message.from_user.id
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT username, first_name, is_banned FROM users WHERE user_id = ?', (target_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            bot.send_message(message.chat.id, "❌ Пользователь не найден в базе данных")
            conn.close()
            return
        
        username, first_name, is_banned = user_data
        
        if is_banned == 0:
            bot.send_message(message.chat.id, "⚠️ Пользователь не забанен")
            conn.close()
            return
        
        # Разбаниваем пользователя
        cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                      (target_user_id,))
        conn.commit()
        conn.close()
        
        target_name = f"@{username}" if username else first_name
        
        bot.send_message(message.chat.id, 
                       f"✅ Пользователь {target_name} разбанен!")
        
        # Уведомляем пользователя
        try:
            bot.send_message(target_user_id, 
                           f"🎉 Вы разбанены в боте!\n"
                           f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}\n"
                           f"⏰ Время разбана: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except:
            pass
    
    except Exception as e:
        print(f"Ошибка в handle_unban: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при разбане пользователя")

# Обработчик команды "передать"/"кинуть"
@bot.message_handler(func=lambda message: message.text.lower().startswith(('передать ', 'кинуть ')))
def handle_transfer(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        if not message.reply_to_message:
            bot.send_message(message.chat.id, "❌ Ответьте на сообщение пользователя, которому хотите передать деньги")
            return
        
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username
        target_first_name = message.reply_to_message.from_user.first_name
        
        if target_user_id == user_id:
            bot.send_message(message.chat.id, "❌ Нельзя передавать деньги самому себе")
            return
        
        # Проверяем бан получателя
        target_banned, target_reason = is_banned(target_user_id)
        if target_banned:
            bot.send_message(message.chat.id, "❌ Невозможно передать деньги забаненному пользователю")
            return
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: передать 1000к")
            return
        
        transfer_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if transfer_amount is None:
            bot.send_message(message.chat.id, "❌ Неверная сумма")
            return
        
        if transfer_amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0")
            return
        
        if transfer_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств для передачи")
            return
        
        # Создаем получателя если его нет
        get_or_create_user(target_user_id, target_username, target_first_name)
        
        # Переводим деньги
        update_balance(user_id, -transfer_amount)
        update_balance(target_user_id, transfer_amount)
        
        new_balance = get_balance(user_id)
        target_balance = get_balance(target_user_id)
        
        sender_username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        target_name = f"@{target_username}" if target_username else target_first_name
        
        bot.send_message(message.chat.id,
                       f"✅ Вы передали ❄️{format_balance(transfer_amount)} пользователю {target_name}\n"
                       f"❄️ Ваш баланс: ❄️{format_balance(new_balance)}")
        
        bot.send_message(target_user_id,
                       f"🎉 Вам передали ❄️{format_balance(transfer_amount)} от {sender_username}\n"
                       f"❄️ Ваш баланс: ❄️{format_balance(target_balance)}")
    
    except Exception as e:
        print(f"Ошибка в передаче денег: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при передаче денег. Попробуйте снова.")
# Обработчик команды "рассылка" для админов
@bot.message_handler(func=lambda message: message.text.lower().startswith('рассылка ') and is_admin(message.from_user.id))
def handle_broadcast(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        # Получаем текст рассылки (все после "рассылка ")
        broadcast_text = message.text[len('рассылка '):].strip()
        
        if not broadcast_text:
            bot.send_message(message.chat.id, "❌ Введите текст для рассылки. Пример: рассылка Привет всем!")
            return
        
        bot.send_message(message.chat.id, f"⏳ Начинаю рассылку...\nТекст: {broadcast_text[:100]}...")
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Получаем всех пользователей которые не забанены
        cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        conn.close()
        
        total_users = len(users)
        successful = 0
        failed = 0
        
        bot.send_message(message.chat.id, f"📊 Всего пользователей для рассылки: {total_users}")
        
        # Рассылаем сообщения
        for user_data in users:
            user_id = user_data[0]
            try:
                bot.send_message(user_id, f"📢 Рассылка от администрации:\n\n{broadcast_text}")
                successful += 1
                
                # Небольшая задержка чтобы не превысить лимиты Telegram
                time.sleep(0.05)
                
            except Exception as e:
                failed += 1
                print(f"Ошибка при отправке пользователю {user_id}: {e}")
        
        # Отправляем отчет
        report_message = f"✅ Рассылка завершена!\n\n"
        report_message += f"📊 Статистика:\n"
        report_message += f"• Всего пользователей: {total_users}\n"
        report_message += f"• Успешно отправлено: {successful}\n"
        report_message += f"• Не удалось отправить: {failed}\n"
        
        bot.send_message(message.chat.id, report_message)
    
    except Exception as e:
        print(f"Ошибка в рассылке: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при рассылке: {e}")

# Обработчик команды "статистика" для админов
@bot.message_handler(func=lambda message: message.text.lower() == 'статистика' and is_admin(message.from_user.id))
def handle_statistics(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Получаем общую статистику
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
        banned_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE captcha_passed = 1')
        active_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(registered_at) = DATE("now")')
        new_today = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(balance) FROM users')
        total_balance = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(bank_deposit) FROM users')
        total_deposits = cursor.fetchone()[0] or 0
        
        conn.close()
        
        stats_message = f"📊 Статистика бота:\n\n"
        stats_message += f"👥 Всего пользователей: {total_users}\n"
        stats_message += f"✅ Активных (прошли капчу): {active_users}\n"
        stats_message += f"🚫 Забанено: {banned_users}\n"
        stats_message += f"📈 Новых сегодня: {new_today}\n"
        stats_message += f"💰 Общий баланс: ❄️{format_balance(total_balance)}\n"
        stats_message += f"🏦 Общая сумма в банке: ❄️{format_balance(total_deposits)}\n"
        
        bot.send_message(message.chat.id, stats_message)
    
    except Exception as e:
        print(f"Ошибка в статистике: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при получении статистики: {e}")

# Обработчик команды "поиск" для админов
@bot.message_handler(func=lambda message: message.text.lower().startswith('поиск ') and is_admin(message.from_user.id))
def handle_search_user(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        search_query = message.text[len('поиск '):].strip()
        
        if not search_query:
            bot.send_message(message.chat.id, "❌ Введите поисковый запрос. Пример: поиск @username или поиск 123456789")
            return
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Ищем пользователя по ID, username или имени
        cursor.execute('''
            SELECT user_id, username, first_name, balance, is_banned, 
                   registered_at, last_activity 
            FROM users 
            WHERE user_id = ? OR username LIKE ? OR first_name LIKE ?
            LIMIT 10
        ''', (search_query, f'%{search_query}%', f'%{search_query}%'))
        
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            bot.send_message(message.chat.id, f"❌ Пользователи по запросу '{search_query}' не найдены")
            return
        
        result_message = f"🔍 Результаты поиска '{search_query}':\n\n"
        
        for i, user in enumerate(users, 1):
            user_id, username, first_name, balance, is_banned, registered_at, last_activity = user
            
            display_name = f"@{username}" if username else first_name
            status = "🚫 Забанен" if is_banned == 1 else "✅ Активен"
            
            # Форматируем даты
            try:
                reg_date = registered_at[:10] if registered_at else "Неизвестно"
                last_active = last_activity[:16] if last_activity else "Неизвестно"
            except:
                reg_date = "Неизвестно"
                last_active = "Неизвестно"
            
            result_message += f"{i}. {display_name} (ID: {user_id})\n"
            result_message += f"   Статус: {status}\n"
            result_message += f"   Баланс: ❄️{format_balance(balance)}\n"
            result_message += f"   Регистрация: {reg_date}\n"
            result_message += f"   Последняя активность: {last_active}\n\n"
        
        bot.send_message(message.chat.id, result_message)
    
    except Exception as e:
        print(f"Ошибка в поиске: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при поиске: {e}")
# Обработчик кнопки "Панель клана"
@bot.message_handler(func=lambda message: message.text == "Панель клана")
def handle_clan_panel(message):
    if is_spam(message.from_user.id):
        return
    
    # Проверяем бан
    banned, reason = is_banned(message.from_user.id)
    if banned:
        bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
        return
        
    bot.send_message(message.chat.id, "Панель клана в разработке...")
@bot.message_handler(func=lambda message: message.from_user.id in user_captcha_status)
def check_captcha_answer(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            if user_id in user_captcha_status:
                del user_captcha_status[user_id]
            return
        
        # Получаем правильный ответ
        correct_answer = user_captcha_status.get(user_id)
        
        if not correct_answer:
            # Если капча устарела, создаем новую
            captcha_question, correct_answer = generate_captcha()
            user_captcha_status[user_id] = correct_answer
            
            bot.send_message(message.chat.id, 
                           f"🔄 Капча устарела. Решите новый пример:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
            return
        
        # Проверяем ответ пользователя
        user_answer = message.text.strip()
        
        if user_answer == correct_answer:
            # Помечаем капчу как пройденную
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET captcha_passed = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            # Удаляем капчу из памяти
            if user_id in user_captcha_status:
                del user_captcha_status[user_id]
            
            # ПРОВЕРЯЕМ ЕСТЬ ЛИ ОЖИДАЮЩИЙ РЕФ/ЧЕК КОД
            if user_id in pending_ref_codes:
                ref_code = pending_ref_codes[user_id]
                logging.info(f"Обрабатываем отложенный реф/чек код для {user_id}: {ref_code}")
                
                # Обрабатываем реферал или чек
                process_ref_or_check(user_id, username, first_name, ref_code)
                
                # Удаляем из временного хранилища
                del pending_ref_codes[user_id]
            
            # Показываем меню после успешной капчи
            markup = create_main_menu()
            bot.send_message(message.chat.id, "✅ Капча пройдена!", reply_markup=markup)
        else:
            # Генерируем новую капчу
            captcha_question, new_correct_answer = generate_captcha()
            user_captcha_status[user_id] = new_correct_answer
            
            bot.send_message(message.chat.id, 
                           f"❌ Неверный ответ! Попробуйте еще раз:\n\n"
                           f"{captcha_question}\n\n"
                           f"Отправьте ответ числом в чат.")
    
    except Exception as e:
        logging.error(f"Ошибка в check_captcha_answer: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка проверки капчи. Попробуйте команду /start снова.")
# Функция для очистки старых капч
def clean_old_captchas():
    while True:
        time.sleep(300)  # Каждые 5 минут
        current_time = time.time()
        to_remove = []
        for user_id, captcha_data in list(user_captcha_status.items()):
            # Вместо проверки времени, просто очищаем старые капчи
            # Мы храним только правильный ответ, так что просто очищаем периодически
            to_remove.append(user_id)
        
        for user_id in to_remove:
            if user_id in user_captcha_status:
                del user_captcha_status[user_id]
                print(f"Очищена старая капча для пользователя {user_id}")
# === НАСТРОЙКИ БОНУСА ===
# Глобальные переменные для блокировки повторных кликов
user_bonus_cooldown = {}  # {user_id: timestamp}
bonus_processing = set()  # Множество пользователей, которые уже получают бонус

REQUIRED_CHANNEL = "@FECTIZ"  # Канал для подписки
BONUS_AMOUNT = 212


@bot.message_handler(func=lambda message: message.text == "Бонус")
def handle_daily_bonus(message):
    try:
        user_id = message.from_user.id
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        # Проверяем подписку
        try:
            channel_member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            if channel_member.status not in ['member', 'administrator', 'creator']:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
                
                bot.send_message(
                    message.chat.id,
                    "🎁 Бонус\n\n"
                    f"❄️ +{BONUS_AMOUNT}\n"
                    f"🕐 каждые 30 мин\n\n"
                    "❌ Для бонуса подпишитесь на канал:\n"
                    f"📢 {REQUIRED_CHANNEL}\n\n"
                    "После подписки нажмите '🔄 Проверить'",
                    reply_markup=markup
                )
                return
        except Exception as e:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
            markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
            
            bot.send_message(
                message.chat.id,
                "🎁 Бонус\n\n"
                f"❄️ +{BONUS_AMOUNT}\n"
                f"🕐 каждые 30 мин\n\n"
                f"❌ Ошибка проверки подписки.\n"
                f"Подпишитесь на: {REQUIRED_CHANNEL}\n\n"
                "После подписки нажмите '🔄 Проверить'",
                reply_markup=markup
            )
            return
        
        # Проверяем время с блокировкой
        current_time = int(time.time())
        
        # Проверяем не обрабатывается ли уже бонус
        if user_id in bonus_processing:
            bot.send_message(message.chat.id, "⏳ Бонус уже обрабатывается...")
            return
        
        # Проверяем кулдаун
        if user_id in user_bonus_cooldown:
            last_bonus_time = user_bonus_cooldown[user_id]
            time_passed = current_time - last_bonus_time
            
            if time_passed < 2:  # 2 секунды для защиты от двойного клика
                time_left = 2 - time_passed
                bot.send_message(message.chat.id, f"⏳ Подождите {time_left} секунд")
                return
        
        # Устанавливаем временный кулдаун
        user_bonus_cooldown[user_id] = current_time
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Получаем время последнего бонуса
            cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_bonus = result[0]
                
                # Преобразуем last_bonus в timestamp
                if isinstance(last_bonus, str):
                    try:
                        last_bonus_time = int(float(last_bonus))
                    except:
                        try:
                            last_bonus_time = int(last_bonus)
                        except:
                            last_bonus_time = 0
                else:
                    last_bonus_time = int(last_bonus) if last_bonus else 0
                
                if last_bonus_time > 0:
                    time_passed = current_time - last_bonus_time
                    
                    if time_passed < 1800:  # 30 минут
                        time_left = 1800 - time_passed
                        minutes = time_left // 60
                        seconds = time_left % 60
                        bot.send_message(message.chat.id, f"⏳ {minutes}:{seconds:02d}")
                        
                        # Удаляем временный кулдаун
                        if user_id in user_bonus_cooldown:
                            del user_bonus_cooldown[user_id]
                        return
                        
        except Exception as e:
            # Игнорируем ошибки проверки времени
            pass
        finally:
            if conn:
                conn.close()
        
        # Показываем бонус с защитой от повторного клика
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎁 Забрать", callback_data=f"claim_bonus_{current_time}"))
        
        bonus_text = f"🎁 Бонус\n\n"
        bonus_text += f"❄️ +{BONUS_AMOUNT}\n"
        bonus_text += f"🕐 каждые 30 мин"
        
        bot.send_message(message.chat.id, bonus_text, reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка в бонусе: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub_bonus")
def handle_check_subscription_bonus(call):
    try:
        user_id = call.from_user.id
        current_time = int(time.time())
        
        # Блокировка от повторных кликов
        if user_id in user_bonus_cooldown:
            if current_time - user_bonus_cooldown[user_id] < 2:
                bot.answer_callback_query(call.id, "⏳ Подождите немного")
                return
        
        user_bonus_cooldown[user_id] = current_time
        
        try:
            channel_member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            if channel_member.status in ['member', 'administrator', 'creator']:
                bot.answer_callback_query(call.id, "✅ Подписка подтверждена")
                
                # Обновляем сообщение
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🎁 Забрать", callback_data=f"claim_bonus_{current_time}"))
                
                bot.edit_message_text(
                    "🎁 Бонус\n\n"
                    f"❄️ +{BONUS_AMOUNT}\n"
                    f"🕐 каждые 30 мин\n\n"
                    "✅ Подписка подтверждена!",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            else:
                bot.answer_callback_query(call.id, "❌ Вы не подписаны")
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
                
                bot.edit_message_text(
                    "🎁 Бонус\n\n"
                    f"❄️ +{BONUS_AMOUNT}\n"
                    f"🕐 каждые 30 мин\n\n"
                    "❌ Вы еще не подписались!\n\n"
                    f"📢 Канал: {REQUIRED_CHANNEL}\n"
                    "После подписки нажмите '🔄 Проверить'",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
                
        except Exception as e:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки")
            
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_bonus_"))
def handle_claim_bonus(call):
    conn = None
    try:
        user_id = call.from_user.id
        current_time = int(time.time())
        
        # Извлекаем timestamp из callback_data
        callback_parts = call.data.split('_')
        if len(callback_parts) != 3:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            return
            
        callback_timestamp = int(callback_parts[2])
        
        # Проверяем не устарела ли кнопка (больше 60 секунд)
        if current_time - callback_timestamp > 60:
            bot.answer_callback_query(call.id, "❌ Время истекло, обновите страницу")
            return
        
        # Проверяем не обрабатывается ли уже бонус
        if user_id in bonus_processing:
            bot.answer_callback_query(call.id, "⏳ Уже получаете бонус...")
            return
        
        # Добавляем пользователя в обработку
        bonus_processing.add(user_id)
        
        try:
            # Проверяем подписку
            try:
                channel_member = bot.get_chat_member("@FECTIZ", user_id)
                if channel_member.status not in ['member', 'administrator', 'creator']:
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                    markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub_bonus"))
                    
                    bot.edit_message_text(
                        "❌ Подписка не найдена!\n"
                        f"📢 {REQUIRED_CHANNEL}",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=markup
                    )
                    bot.answer_callback_query(call.id, "❌ Проверьте подписку")
                    return
            except:
                bot.answer_callback_query(call.id, "❌ Ошибка проверки подписки")
                return
            
            # Проверяем время через БД с транзакцией
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Начинаем транзакцию для атомарной проверки
            cursor.execute('BEGIN IMMEDIATE TRANSACTION')
            
            # Получаем время последнего бонуса с блокировкой строки
            cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                last_bonus = result[0]
                
                # Преобразуем last_bonus в timestamp
                if isinstance(last_bonus, str):
                    try:
                        last_bonus_time = int(float(last_bonus))
                    except:
                        try:
                            last_bonus_time = int(last_bonus)
                        except:
                            last_bonus_time = 0
                else:
                    last_bonus_time = int(last_bonus) if last_bonus else 0
                
                if last_bonus_time > 0:
                    time_passed = current_time - last_bonus_time
                    
                    if time_passed < 1700:  # 28 минут для надежности
                        cursor.execute('ROLLBACK')
                        conn.close()
                        
                        time_left = 1800 - time_passed
                        minutes = time_left // 60
                        seconds = time_left % 60
                        bot.answer_callback_query(call.id, f"⏳ Ждите {minutes}:{seconds:02d}")
                        return
            
            # Выдаем бонус
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (BONUS_AMOUNT, user_id))
            
            # Обновляем время
            cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', (current_time, user_id))
            
            # Коммитим транзакцию
            cursor.execute('COMMIT')
            
            # Получаем баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            balance_result = cursor.fetchone()
            new_balance = balance_result[0] if balance_result else BONUS_AMOUNT
            
            # Показываем результат
            bot.edit_message_text(
                f"✅ Бонус получен\n\n"
                f"💰 +{BONUS_AMOUNT}❄️\n"
                f"📊 Баланс: {format_balance(new_balance)}❄️",
                call.message.chat.id,
                call.message.message_id
            )
            
            bot.answer_callback_query(call.id, "✅")
            
            # Устанавливаем временный кулдаун на 5 секунд
            user_bonus_cooldown[user_id] = current_time
            
            # Логируем успешное получение
            logging.info(f"Пользователь {user_id} получил бонус {BONUS_AMOUNT}❄️")
            
        except Exception as e:
            # Откатываем транзакцию при ошибке
            try:
                if conn:
                    cursor.execute('ROLLBACK')
            except:
                pass
            logging.error(f"Ошибка получения бонуса: {e}")
            
            # Показываем более детальную ошибку в логах
            import traceback
            logging.error(f"Трассировка ошибки: {traceback.format_exc()}")
            
            # Пробуем альтернативный метод (без транзакции)
            try:
                if conn:
                    conn.close()
                
                # Простая проверка без транзакции
                simple_conn = get_db_connection()
                simple_cursor = simple_conn.cursor()
                
                simple_cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
                simple_result = simple_cursor.fetchone()
                
                if simple_result and simple_result[0]:
                    last_bonus = simple_result[0]
                    
                    if isinstance(last_bonus, str):
                        try:
                            last_bonus_time = int(float(last_bonus))
                        except:
                            try:
                                last_bonus_time = int(last_bonus)
                            except:
                                last_bonus_time = 0
                    else:
                        last_bonus_time = int(last_bonus) if last_bonus else 0
                    
                    if last_bonus_time > 0:
                        time_passed = current_time - last_bonus_time
                        
                        if time_passed < 1700:
                            time_left = 1800 - time_passed
                            minutes = time_left // 60
                            seconds = time_left % 60
                            bot.answer_callback_query(call.id, f"⏳ Ждите {minutes}:{seconds:02d}")
                            return
                
                # Выдаем бонус
                simple_cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (BONUS_AMOUNT, user_id))
                simple_cursor.execute('UPDATE users SET last_bonus = ? WHERE user_id = ?', (current_time, user_id))
                simple_conn.commit()
                
                simple_cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                balance_result = simple_cursor.fetchone()
                new_balance = balance_result[0] if balance_result else BONUS_AMOUNT
                
                bot.edit_message_text(
                    f"✅ Бонус получен\n\n"
                    f"💰 +{BONUS_AMOUNT}❄️\n"
                    f"📊 Баланс: {format_balance(new_balance)}❄️",
                    call.message.chat.id,
                    call.message.message_id
                )
                
                bot.answer_callback_query(call.id, "✅")
                logging.info(f"Пользователь {user_id} получил бонус {BONUS_AMOUNT}❄️ (альтернативный метод)")
                
                simple_conn.close()
                
            except Exception as e2:
                logging.error(f"Ошибка альтернативного метода: {e2}")
                bot.answer_callback_query(call.id, "❌ Ошибка получения")
                
        finally:
            # Удаляем пользователя из обработки
            if user_id in bonus_processing:
                bonus_processing.remove(user_id)
            if conn:
                conn.close()
                
    except Exception as e:
        logging.error(f"Критическая ошибка в бонусе: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")
        
        # Удаляем пользователя из обработки
        if user_id in bonus_processing:
            bonus_processing.remove(user_id)
def cleanup_bonus_cooldowns():
    """Очищает старые записи о кулдаунах"""
    while True:
        time.sleep(60)  # Каждую минуту
        current_time = time.time()
        
        # Очищаем старые кулдауны (старше 10 секунд)
        to_remove = []
        for user_id, timestamp in user_bonus_cooldown.items():
            if current_time - timestamp > 10:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del user_bonus_cooldown[user_id]
        
        # Очищаем обработку (на всякий случай)
        bonus_processing.clear()

# Запускаем очистку в отдельном потоке
import threading
cleanup_thread = threading.Thread(target=cleanup_bonus_cooldowns, daemon=True)
cleanup_thread.start()
# === ФУНКЦИЯ ДЛЯ СОЗДАНИЯ КОЛОНКИ БОНУСА ===
def ensure_bonus_column():
    """Создает колонку для бонуса если её нет"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'last_bonus' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_bonus INTEGER DEFAULT 0")
            conn.commit()
            logging.info("✅ Колонка last_bonus создана")
            
    except Exception as e:
        logging.error(f"Ошибка создания колонки: {e}")
    finally:
        if conn:
            conn.close()


# === УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ БЕЗ ПОДТВЕРЖДЕНИЙ ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('удалить ') and is_admin(message.from_user.id))
def handle_delete_user(message):
    conn = None
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: удалить ID")
            return
        
        target_user_id = int(parts[1].strip())
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Удаляем чеки пользователя
        cursor.execute('DELETE FROM checks WHERE created_by = ?', (target_user_id,))
        
        # Удаляем активации чеков
        cursor.execute('DELETE FROM check_activations WHERE user_id = ?', (target_user_id,))
        
        # Удаляем пользователя
        cursor.execute('DELETE FROM users WHERE user_id = ?', (target_user_id,))
        
        conn.commit()
        
        bot.send_message(message.chat.id, f"✅ Пользователь {target_user_id} удален")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")
    finally:
        if conn:
            conn.close()
            
@bot.message_handler(func=lambda message: message.text.lower() == 'разбонус' and is_admin(message.from_user.id))
def handle_mass_bonus(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        bot.send_message(message.chat.id, "⏳ Начинаю массовую рассылку бонуса...")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        
        cursor.execute('SELECT user_id, username, first_name FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        conn.close()
        
        total_users = len(users)
        successful = 0
        failed = 0
        
        bot.send_message(message.chat.id, f"📊 Всего пользователей: {total_users}")
        
        current_time = int(time.time())
        
        
        for user in users:
            user_id, username, first_name = user
            
            try:
                
                try:
                    channel_member = bot.get_chat_member("@FECTIZ", user_id)
                    is_subscribed = channel_member.status in ['member', 'administrator', 'creator']
                except:
                    is_subscribed = False
                
                # Создаем сообщение с кнопкой
                if is_subscribed:
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("🎁 Забрать", callback_data=f"mass_bonus_{current_time}_{user_id}"))
                    
                    # Отправляем сообщение с кнопкой
                    bot.send_message(
                        user_id,
                        f"🎉 АДМИНИСТРАЦИЯ ВЫДАЛА МАССОВЫЙ БОНУС!\n\n"
                        f"💰 +{BONUS_AMOUNT}❄️\n"
                        f"📢 Канал: @FECTIZ\n\n"
                        f"🎰 Зарабатывайте больше в казино!",
                        reply_markup=markup
                    )
                    successful += 1
                else:
                    
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("📢 Подписаться на канал", url="https://t.me/FECTIZ"))
                    markup.add(InlineKeyboardButton("🔄 Проверить", callback_data=f"check_sub_mass_{user_id}"))
                    
                    bot.send_message(
                        user_id,
                        f"🎁 АДМИНИСТРАЦИЯ ВЫДАЕТ МАССОВЫЙ БОНУС!\n\n"
                        f"💰 +{BONUS_AMOUNT}❄️\n\n"
                        f"❌ Для получения бонуса подпишитесь на канал:\n"
                        f"📢 @FECTIZ\n\n"
                        f"После подписки нажмите '🔄 Проверить'",
                        reply_markup=markup
                    )
                    failed += 1
                
                # Небольшая задержка
                time.sleep(0.1)
                
            except Exception as e:
                failed += 1
                print(f"Ошибка отправки пользователю {user_id}: {e}")
        
        # Отчет
        report = f"✅ Массовая рассылка бонуса завершена!\n\n"
        report += f"📊 Статистика:\n"
        report += f"• Всего пользователей: {total_users}\n"
        report += f"• Получили предложение: {successful}\n"
        report += f"• Не подписаны/ошибки: {failed}\n\n"
        report += f"💡 Пользователи получат бонус только после нажатия кнопки '🎁 Забрать'!"
        
        bot.send_message(message.chat.id, report)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка рассылки: {e}")

# === ОБРАБОТЧИК МАССОВОГО БОНУСА ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("mass_bonus_"))
def handle_mass_bonus_claim(call):
    conn = None
    try:
        user_id = call.from_user.id
        current_time = int(time.time())
        
        # Извлекаем данные из callback_data
        # Формат: mass_bonus_TIMESTAMP_TARGET_USER_ID
        callback_parts = call.data.split('_')
        
        if len(callback_parts) != 4:
            bot.answer_callback_query(call.id, "❌ Ошибка данных")
            return
            
        callback_timestamp = int(callback_parts[2])
        target_user_id = int(callback_parts[3])
        
        # Проверяем что пользователь нажимает на свою кнопку
        if user_id != target_user_id:
            bot.answer_callback_query(call.id, "❌ Это не ваш бонус!")
            return
        
        # Проверяем не устарела ли кнопка (больше 7 дней)
        if current_time - callback_timestamp > 604800:  # 7 дней в секундах
            bot.answer_callback_query(call.id, "❌ Время получения бонуса истекло")
            return
        
        # Проверяем не обрабатывается ли уже бонус
        if user_id in bonus_processing:
            bot.answer_callback_query(call.id, "⏳ Бонус уже обрабатывается...")
            return
        
        # Добавляем пользователя в обработку
        bonus_processing.add(user_id)
        
        try:
            # Проверяем подписку
            try:
                channel_member = bot.get_chat_member("@FECTIZ", user_id)
                if channel_member.status not in ['member', 'administrator', 'creator']:
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/FECTIZ"))
                    markup.add(InlineKeyboardButton("🔄 Проверить", callback_data=f"check_sub_mass_{user_id}"))
                    
                    bot.edit_message_text(
                        "❌ Подписка не найдена!\n"
                        f"📢 @FECTIZ\n\n"
                        "Подпишитесь на канал и нажмите '🔄 Проверить'",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=markup
                    )
                    bot.answer_callback_query(call.id, "❌ Проверьте подписку")
                    return
            except:
                bot.answer_callback_query(call.id, "❌ Ошибка проверки подписки")
                return
            
            # Выдаем бонус
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Начисляем бонус
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (BONUS_AMOUNT, user_id))
            
            # Получаем баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            balance_result = cursor.fetchone()
            new_balance = balance_result[0] if balance_result else BONUS_AMOUNT
            
            conn.commit()
            
            # Показываем результат
            bot.edit_message_text(
                f"✅ МАССОВЫЙ БОНУС ПОЛУЧЕН!\n\n"
                f"💰 +{BONUS_AMOUNT}❄️\n"
                f"📊 Баланс: {format_balance(new_balance)}❄️\n\n"
                f"🎰 Удачи в казино!",
                call.message.chat.id,
                call.message.message_id
            )
            
            bot.answer_callback_query(call.id, "✅ Бонус получен!")
            
            # Логируем
            logging.info(f"Пользователь {user_id} получил массовый бонус {BONUS_AMOUNT}❄️")
            
        except Exception as e:
            logging.error(f"Ошибка получения массового бонуса: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка получения бонуса")
            
        finally:
            # Удаляем пользователя из обработки
            if user_id in bonus_processing:
                bonus_processing.remove(user_id)
            if conn:
                conn.close()
                
    except Exception as e:
        logging.error(f"Критическая ошибка в массовом бонусе: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# === ОБРАБОТЧИК ПРОВЕРКИ ПОДПИСКИ ДЛЯ МАССОВОГО БОНУСА ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("check_sub_mass_"))
def handle_check_sub_mass_bonus(call):
    try:
        user_id = call.from_user.id
        
        # Извлекаем целевой user_id
        target_user_id = int(call.data.split('_')[3])
        
        # Проверяем что пользователь проверяет свою подписку
        if user_id != target_user_id:
            bot.answer_callback_query(call.id, "❌ Это не ваше сообщение!")
            return
        
        try:
            channel_member = bot.get_chat_member("@FECTIZ", user_id)
            if channel_member.status in ['member', 'administrator', 'creator']:
                bot.answer_callback_query(call.id, "✅ Подписка подтверждена!")
                
                # Создаем новую кнопку для получения бонуса
                current_time = int(time.time())
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🎁 Забрать", callback_data=f"mass_bonus_{current_time}_{user_id}"))
                
                bot.edit_message_text(
                    f"✅ Подписка подтверждена!\n\n"
                    f"🎉 АДМИНИСТРАЦИЯ ВЫДАЛА МАССОВЫЙ БОНУС!\n\n"
                    f"💰 +{BONUS_AMOUNT}❄️\n"
                    f"📢 Канал: @FECTIZ\n\n"
                    f"Нажмите кнопку ниже чтобы забрать бонус!",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            else:
                bot.answer_callback_query(call.id, "❌ Вы еще не подписаны!")
                
        except Exception as e:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки подписки")
            
    except Exception as e:
        logging.error(f"Ошибка проверки подписки для массового бонуса: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")
@bot.message_handler(func=lambda message: message.text.lower() == 'загрузитьбазу' and is_admin(message.from_user.id))
def handle_upload_db(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        bot.send_message(message.chat.id, 
                       "📤 Отправьте файл базы данных (game.db)\n\n"
                       "⚠️ ВНИМАНИЕ: Текущая база будет заменена!\n"
                       "Сначала скачайте текущую через /база")
        
    except Exception as e:
        print(f"Ошибка: {e}")


@bot.message_handler(func=lambda message: message.text.lower() == 'база' and is_admin(message.from_user.id))
def handle_download_db(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        bot.send_message(message.chat.id, "⏳ Подготавливаю базу данных...")
        
        # Проверяем существует ли файл базы
        if not os.path.exists('game.db'):
            bot.send_message(message.chat.id, "❌ Файл базы данных не найден!")
            return
        
        # Шаг 1: Завершаем все транзакции
        logging.info("Завершаю все транзакции...")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Коммитим все активные транзакции
            try:
                cursor.execute('COMMIT')
            except:
                pass
            
            # Проверяем и закрываем WAL
            cursor.execute('PRAGMA journal_mode')
            journal_mode = cursor.fetchone()[0]
            
            if journal_mode == 'wal':
                # Для WAL режима делаем checkpoint
                cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                logging.info("WAL checkpoint выполнен")
            
            conn.close()
            time.sleep(0.5)  # Даем время на запись
            
        except Exception as e:
            logging.error(f"Ошибка при завершении транзакций: {e}")
        
        # Шаг 2: Создаем копию базы с блокировкой
        backup_filename = f"game_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        try:
            # Используем VACUUM INTO для создания чистой копии
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute(f'VACUUM INTO "{backup_filename}"')
            conn.close()
            
            logging.info(f"Создана копия базы через VACUUM INTO: {backup_filename}")
            
        except Exception as e:
            logging.error(f"Ошибка VACUUM INTO: {e}, использую обычное копирование")
            # Если VACUUM не сработал, используем обычное копирование
            shutil.copy2('game.db', backup_filename)
        
        # Шаг 3: Проверяем целостность копии
        try:
            check_conn = sqlite3.connect(backup_filename)
            check_cursor = check_conn.cursor()
            check_cursor.execute('PRAGMA integrity_check')
            integrity = check_cursor.fetchone()[0]
            check_conn.close()
            
            if integrity != 'ok':
                logging.warning(f"Копия базы повреждена: {integrity}")
                os.remove(backup_filename)
                bot.send_message(message.chat.id, "❌ Ошибка: копия базы повреждена")
                return
                
        except Exception as e:
            logging.error(f"Ошибка проверки целостности: {e}")
            os.remove(backup_filename)
            bot.send_message(message.chat.id, f"❌ Ошибка проверки базы: {e}")
            return
        
        # Шаг 4: Отправляем файл
        try:
            with open(backup_filename, 'rb') as db_file:
                # Отправляем с progress сообщением
                bot.send_chat_action(message.chat.id, 'upload_document')
                
                bot.send_document(
                    message.chat.id, 
                    db_file, 
                    caption=f"📦 База данных\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n✅ Все транзакции завершены",
                    timeout=60
                )
            
            # Шаг 5: Получаем и отправляем статистику
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM users')
            users_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
            banned_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM checks')
            checks_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT SUM(balance) FROM users')
            total_balance = cursor.fetchone()[0] or 0
            
            # Последние действия
            cursor.execute('''
                SELECT COUNT(*) FROM users 
                WHERE last_activity > datetime('now', '-1 hour')
            ''')
            active_last_hour = cursor.fetchone()[0]
            
            conn.close()
            
            # Статистика файла
            file_size = os.path.getsize(backup_filename)
            
            stats_text = f"✅ База данных отправлена\n\n"
            stats_text += f"📊 Статистика:\n"
            stats_text += f"👥 Пользователей: {users_count}\n"
            stats_text += f"🚫 Забанено: {banned_count}\n"
            stats_text += f"💳 Чеков: {checks_count}\n"
            stats_text += f"💰 Общий баланс: {format_balance(total_balance)}❄️\n"
            stats_text += f"👤 Активных (час): {active_last_hour}\n"
            stats_text += f"💾 Размер: {file_size / 1024:.1f} KB\n\n"
            stats_text += f"📁 Файл: {backup_filename}"
            
            bot.send_message(message.chat.id, stats_text)
            
        except Exception as e:
            logging.error(f"Ошибка отправки файла: {e}")
            bot.send_message(message.chat.id, f"❌ Ошибка отправки: {e}")
        
        finally:
            # Шаг 6: Очищаем временный файл
            try:
                if os.path.exists(backup_filename):
                    os.remove(backup_filename)
                    logging.info(f"Временный файл удален: {backup_filename}")
            except Exception as e:
                logging.error(f"Ошибка удаления временного файла: {e}")
        
    except Exception as e:
        logging.error(f"Общая ошибка скачивания базы: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:200]}")
def create_backup():
    """Создает резервную копию базы данных"""
    try:
        if not os.path.exists('game.db'):
            logging.warning("Файл game.db не найден для создания бэкапа")
            return None
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"game_backup_{timestamp}.db"
        
        shutil.copy2('game.db', backup_name)
        
        logging.info(f"Создан бэкап: {backup_name}")
        return backup_name
    except Exception as e:
        logging.error(f"Ошибка создания бэкапа: {e}")
        return None
@bot.message_handler(content_types=['document'], func=lambda message: is_admin(message.from_user.id))
def handle_db_document(message):
    try:
        if message.document.file_name != 'game.db':
            bot.send_message(message.chat.id, "❌ Файл должен называться game.db")
            return
            
        bot.send_message(message.chat.id, "⏳ Загружаю и проверяю базу данных...")
        
        # Создаем резервную копию текущей базы
        backup_name = None
        if os.path.exists('game.db'):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"backup_before_upload_{timestamp}.db"
            shutil.copy2('game.db', backup_name)
            logging.info(f"Создан бэкап: {backup_name}")
            bot.send_message(message.chat.id, f"💾 Создан бэкап: {backup_name}")
        
        # Скачиваем файл
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем как временный файл
        temp_filename = f"temp_game_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        with open(temp_filename, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # УСИЛЕННАЯ ПРОВЕРКА ЦЕЛОСТНОСТИ
        try:
            test_conn = sqlite3.connect(temp_filename)
            test_cursor = test_conn.cursor()
            
            # 1. Проверяем целостность базы данных
            test_cursor.execute("PRAGMA integrity_check")
            integrity_result = test_cursor.fetchone()[0]
            
            if integrity_result != 'ok':
                test_conn.close()
                os.remove(temp_filename)
                error_msg = f"❌ Файл базы поврежден: {integrity_result}"
                logging.error(error_msg)
                
                # Восстанавливаем бэкап
                if backup_name and os.path.exists(backup_name):
                    os.replace(backup_name, 'game.db')
                    init_db()
                    bot.send_message(message.chat.id, 
                                   f"{error_msg}\n\n"
                                   f"✅ Восстановлена предыдущая версия базы из бэкапа")
                else:
                    # Создаем новую пустую базу
                    init_db()
                    bot.send_message(message.chat.id, 
                                   f"{error_msg}\n\n"
                                   f"📂 Создана новая пустая база данных")
                return
            
            # 2. Проверяем основные таблицы
            test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in test_cursor.fetchall()]
            
            required_tables = ['users', 'checks', 'check_activations']
            missing_tables = [table for table in required_tables if table not in tables]
            
            if missing_tables:
                test_conn.close()
                os.remove(temp_filename)
                bot.send_message(message.chat.id, 
                               f"❌ В базе отсутствуют таблицы: {', '.join(missing_tables)}")
                # Восстанавливаем бэкап
                if backup_name and os.path.exists(backup_name):
                    os.replace(backup_name, 'game.db')
                else:
                    init_db()
                return
            
            # 3. Проверяем структуру таблицы users
            test_cursor.execute("PRAGMA table_info(users)")
            user_columns = [col[1] for col in test_cursor.fetchall()]
            
            # Основные колонки, которые должны быть
            essential_columns = ['user_id', 'balance', 'username', 'first_name']
            missing_columns = [col for col in essential_columns if col not in user_columns]
            
            if missing_columns:
                test_conn.close()
                os.remove(temp_filename)
                bot.send_message(message.chat.id, 
                               f"❌ В таблице users отсутствуют колонки: {', '.join(missing_columns)}")
                # Восстанавливаем бэкап
                if backup_name and os.path.exists(backup_name):
                    os.replace(backup_name, 'game.db')
                else:
                    init_db()
                return
            
            # 4. Проверяем WAL режим и переключаем на нормальный
            test_cursor.execute('PRAGMA journal_mode')
            journal_mode = test_cursor.fetchone()[0]
            
            if journal_mode == 'wal':
                # Переключаем на DELETE режим для надежности
                test_cursor.execute('PRAGMA journal_mode=DELETE')
                test_cursor.execute('PRAGMA synchronous=FULL')
            
            # 5. Получаем статистику
            test_cursor.execute("SELECT COUNT(*) FROM users")
            users_count = test_cursor.fetchone()[0]
            
            test_cursor.execute("SELECT COUNT(*) FROM checks")
            checks_count = test_cursor.fetchone()[0]
            
            test_cursor.execute("SELECT COUNT(*) FROM check_activations")
            activations_count = test_cursor.fetchone()[0]
            
            test_conn.commit()
            test_conn.close()
            
            logging.info(f"База проверена: {users_count} пользователей, {checks_count} чеков")
            
        except sqlite3.Error as e:
            os.remove(temp_filename)
            logging.error(f"Ошибка проверки базы: {e}")
            
            # Восстанавливаем бэкап
            if backup_name and os.path.exists(backup_name):
                os.replace(backup_name, 'game.db')
                init_db()
                bot.send_message(message.chat.id, 
                               f"❌ Ошибка проверки базы: {str(e)[:150]}\n\n"
                               f"✅ Восстановлена предыдущая версия базы")
            else:
                # Создаем новую базу
                init_db()
                bot.send_message(message.chat.id, 
                               f"❌ Ошибка проверки базы: {str(e)[:150]}\n\n"
                               f"📂 Создана новая база данных")
            return
        
        # ЗАМЕНА БАЗЫ ДАННЫХ
        try:
            # Даем время на закрытие всех соединений
            time.sleep(1)
            
            # Заменяем старую базу на новую
            os.replace(temp_filename, 'game.db')
            
            # Переинициализируем базу с новыми настройками
            init_db()
            
            # Дополнительная проверка после замены
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('PRAGMA integrity_check')
            final_integrity = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            final_users_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM checks")
            final_checks_count = cursor.fetchone()[0]
            
            # Получаем несколько последних действий для проверки
            cursor.execute('''
                SELECT user_id, balance, last_activity 
                FROM users 
                ORDER BY last_activity DESC 
                LIMIT 5
            ''')
            recent_activity = cursor.fetchall()
            
            conn.close()
            
            if final_integrity != 'ok':
                raise Exception(f"База повреждена после замены: {final_integrity}")
            
            # Формируем сообщение об успехе
            response_msg = f"✅ База данных успешно обновлена!\n\n"
            response_msg += f"📊 Статистика:\n"
            response_msg += f"👥 Пользователей: {users_count} → {final_users_count}\n"
            response_msg += f"💳 Чеков: {checks_count} → {final_checks_count}\n"
            response_msg += f"🔗 Активаций: {activations_count}\n"
            
            # Добавляем информацию о последних действиях
            response_msg += f"\n🔄 Последние действия:\n"
            for user in recent_activity[:3]:
                user_id, balance, last_activity = user
                response_msg += f"👤 {user_id}: {format_balance(balance)}❄️\n"
            
            if backup_name:
                response_msg += f"\n💾 Бэкап сохранен: {backup_name}\n"
            
            response_msg += f"\n🔄 Бот продолжит работу с новой базой"
            
            bot.send_message(message.chat.id, response_msg)
            
            # Логируем успешную загрузку
            logging.info(f"База успешно заменена. Пользователей: {final_users_count}")
            
        except Exception as e:
            logging.error(f"Ошибка замены базы: {e}")
            
            # Пытаемся восстановить из бэкапа
            if backup_name and os.path.exists(backup_name):
                try:
                    os.replace(backup_name, 'game.db')
                    init_db()
                    bot.send_message(message.chat.id, 
                                   f"❌ Ошибка при замене базы: {str(e)[:150]}\n\n"
                                   f"✅ Восстановлен бэкап")
                except Exception as restore_error:
                    logging.error(f"Ошибка восстановления: {restore_error}")
                    init_db()
                    bot.send_message(message.chat.id, 
                                   f"❌ Критическая ошибка! Создана новая база")
            else:
                init_db()
                bot.send_message(message.chat.id, 
                               f"❌ Ошибка! Создана новая база данных")
        
    except Exception as e:
        logging.error(f"Общая ошибка загрузки базы: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка загрузки: {str(e)[:200]}")
def force_commit_all_transactions():
    """Принудительно завершает все транзакции в базе"""
    try:
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Завершаем все активные транзакции
        try:
            cursor.execute('COMMIT')
        except:
            pass
        
        # Очищаем WAL если он используется
        cursor.execute('PRAGMA journal_mode')
        journal_mode = cursor.fetchone()[0]
        
        if journal_mode == 'wal':
            cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            logging.info("WAL checkpoint выполнен")
        
        # Переключаем в безопасный режим
        cursor.execute('PRAGMA synchronous=FULL')
        cursor.execute('PRAGMA journal_mode=DELETE')
        
        conn.commit()
        conn.close()
        
        logging.info("Все транзакции завершены")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка завершения транзакций: {e}")
        return False

@bot.message_handler(func=lambda message: message.text.lower() == 'завершитьтранзакции' and is_admin(message.from_user.id))
def handle_commit_transactions(message):
    """Команда для принудительного завершения транзакций"""
    if not is_admin(message.from_user.id):
        return
    
    bot.send_message(message.chat.id, "⏳ Завершаю все транзакции...")
    
    if force_commit_all_transactions():
        bot.send_message(message.chat.id, "✅ Все транзакции завершены и сохранены")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка завершения транзакций")
@bot.message_handler(func=lambda message: message.text.lower() == 'статбаза' and is_admin(message.from_user.id))
def handle_db_stats(message):
    """Показывает статистику базы данных"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        stats = "📊 СТАТИСТИКА БАЗЫ ДАННЫХ:\n\n"
        
        # Пользователи
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
        banned_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE balance > 0')
        users_with_money = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(balance) FROM users')
        total_balance = cursor.fetchone()[0] or 0
        
        stats += f"👥 ПОЛЬЗОВАТЕЛИ:\n"
        stats += f"• Всего: {total_users}\n"
        stats += f"• Забанено: {banned_users}\n"
        stats += f"• С балансом >0: {users_with_money}\n"
        stats += f"• Общий баланс: {format_balance(total_balance)}❄️\n\n"
        
        # Чеки
        cursor.execute('SELECT COUNT(*) FROM checks')
        total_checks = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(amount * max_activations) FROM checks')
        total_checks_amount = cursor.fetchone()[0] or 0
        
        stats += f"💳 ЧЕКИ:\n"
        stats += f"• Активных: {total_checks}\n"
        stats += f"• Общая сумма: {format_balance(total_checks_amount)}❄️\n\n"
        
        # Размер файла
        db_size = os.path.getsize('game.db')
        stats += f"📁 ФАЙЛ БАЗЫ:\n"
        stats += f"• Размер: {db_size / 1024:.1f} KB\n"
        stats += f"• Имя: game.db"
        
        conn.close()
        
        bot.send_message(message.chat.id, stats)
        
    except Exception as e:
        print(f"Ошибка статистики базы: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
# Обработчик команды "обнул" для админов
@bot.message_handler(func=lambda message: message.text.lower() == 'обнул' and is_admin(message.from_user.id))
def handle_reset_all(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        # Создаем клавиатуру с подтверждением
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ ДА, ОБНУЛИТЬ ВСЁ", callback_data="reset_confirm"),
            InlineKeyboardButton("❌ ОТМЕНА", callback_data="reset_cancel")
        )
        
        bot.send_message(message.chat.id, 
                       "⚠️ ВНИМАНИЕ: ОПАСНАЯ КОМАНДА!\n\n"
                       "Эта команда обнулит:\n"
                       "• Все балансы пользователей\n"
                       "• Все банковские вклады\n"
                       "• Все активные чеки\n"
                       "• Прогресс чисток снега\n\n"
                       "Вы уверены что хотите обнулить ВСЁ?",
                       reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в handle_reset_all: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

# Обработчик колбэков для подтверждения обнуления
@bot.callback_query_handler(func=lambda call: call.data.startswith('reset_'))
def reset_callback_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет прав!")
            return
            
        if call.data == "reset_confirm":
            # Начинаем обнуление
            bot.answer_callback_query(call.id, "⏳ Начинаю обнуление...")
            
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            
            # 1. Обнуляем балансы всех пользователей (кроме админов)
            cursor.execute('''
                UPDATE users 
                SET balance = 0, 
                    bank_deposit = 0,
                    click_streak = 0,
                    video_cards = 0,
                    deposit = 0,
                    last_mining_collect = 0,
                    click_power = 2,
                    last_snow_work = NULL,
                    snow_cooldown_end = NULL,
                    current_snow_job = NULL,
                    snow_job_progress = 0,
                    snow_job_total = 0,
                    snow_job_end_time = NULL,
                    snow_territory = NULL
                WHERE user_id NOT IN (''' + ','.join(map(str, ADMIN_IDS)) + ''')
            ''')
            
            # 2. Удаляем ВСЕ чеки
            cursor.execute('DELETE FROM checks')
            
            # 3. Удаляем ВСЕ активации чеков
            cursor.execute('DELETE FROM check_activations')
            
            # 4. Сбрасываем реферальную систему
            cursor.execute('UPDATE users SET referred_by = NULL WHERE 1')
            
            conn.commit()
            
            # Получаем статистику
            cursor.execute('SELECT COUNT(*) FROM users WHERE user_id NOT IN (' + ','.join(map(str, ADMIN_IDS)) + ')')
            users_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM checks')
            checks_count = cursor.fetchone()[0]
            
            conn.close()
            
            # Отправляем результат
            result_text = "✅ ВСЁ ОБНУЛЕНО!\n\n"
            result_text += f"📊 Статистика обнуления:\n"
            result_text += f"• Пользователей: {users_count}\n"
            result_text += f"• Чеков удалено: {checks_count}\n"
            result_text += f"• Балансы: 0❄️\n"
            result_text += f"• Вклады: 0❄️\n"
            result_text += f"• Чеки: удалены\n\n"
            result_text += f"⚠️ Все данные сброшены до начального состояния!"
            
            bot.edit_message_text(
                result_text,
                call.message.chat.id,
                call.message.message_id
            )
            
            # Отправляем уведомление всем пользователям (если много, может быть долго)
            try:
                notify_users_about_reset()
            except:
                pass
            
        elif call.data == "reset_cancel":
            bot.answer_callback_query(call.id, "❌ Отменено")
            bot.edit_message_text(
                "❌ Обнуление отменено",
                call.message.chat.id,
                call.message.message_id
            )
    
    except Exception as e:
        print(f"Ошибка в reset_callback_handler: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обнуления!")

def notify_users_about_reset():
    """Отправляет уведомление всем пользователям об обнулении"""
    try:
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Получаем всех пользователей кроме админов
        cursor.execute('SELECT user_id FROM users WHERE user_id NOT IN (' + ','.join(map(str, ADMIN_IDS)) + ')')
        users = cursor.fetchall()
        
        notification_text = (
            "📢 ВНИМАНИЕ: СИСТЕМНОЕ ОБНУЛЕНИЕ!\n\n"
            "Администратор выполнил полное обнуление системы:\n"
            "• Все балансы обнулены\n"
            "• Все вклады обнулены\n"
            "• Все чеки удалены\n"
            "• Реферальная система сброшена\n\n"
            "💡 Начинайте зарабатывать заново!"
        )
        
        notified = 0
        failed = 0
        
        for user in users:
            user_id = user[0]
            try:
                bot.send_message(user_id, notification_text)
                notified += 1
                time.sleep(0.05)  # Задержка чтобы не превысить лимиты
            except:
                failed += 1
        
        conn.close()
        
        print(f"Уведомления отправлены: {notified} успешно, {failed} не удалось")
        
    except Exception as e:
        print(f"Ошибка при отправке уведомлений: {e}")



# Запускаем очистку капч в отдельном потоке
captcha_cleaner_thread = threading.Thread(target=clean_old_captchas, daemon=True)
captcha_cleaner_thread.start()

# Инициализация базы данных при запуске
init_db()

# Запускаем бота
if __name__ == "__main__":
    print("Проверяю колонку для бонуса...")
    ensure_bonus_column()  
    
    print("Бот запущен...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        print("Перезапустите бота.")