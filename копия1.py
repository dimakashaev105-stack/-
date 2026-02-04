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
import io
from PIL import Image
import base64
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
# === ДОБАВЬТЕ ЭТУ ФУНКЦИЮ ПЕРЕД init_db() ===
def get_db_connection():
    """Создает соединение с базой данных"""
    conn = sqlite3.connect('game.db')
    conn.row_factory = sqlite3.Row  # Чтобы получать результаты как словари
    return conn
# === ИСПРАВЛЕННАЯ ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    """Инициализация базы данных с корректной структурой"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            nickname TEXT,
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
            last_bonus INTEGER DEFAULT 0,
            mining_trees INTEGER DEFAULT 0
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
        
        # Таблица домов пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_houses (
            user_id INTEGER,
            house_id TEXT,
            is_current INTEGER DEFAULT 0,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, house_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица реферальных бонусов от выигрышей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS referral_wins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referee_id INTEGER,
            win_amount INTEGER,
            bonus_amount INTEGER,
            game_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (referee_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица конкурсов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS contests (
            contest_id TEXT PRIMARY KEY,
            channel_id INTEGER,
            channel_title TEXT,
            max_participants INTEGER,
            winners_count INTEGER,
            prizes_text TEXT,
            creator_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (creator_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Таблица участников конкурсов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS contest_participants (
            contest_id TEXT,
            user_id INTEGER,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (contest_id, user_id),
            FOREIGN KEY (contest_id) REFERENCES contests(contest_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')
        
        # Индексы для производительности
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_registered_at ON users(registered_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_checks_code ON checks(code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_checks_created_by ON checks(created_by)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_houses_user ON user_houses(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_houses_current ON user_houses(is_current)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_wins_referrer ON referral_wins(referrer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_referral_wins_created ON referral_wins(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_creator ON contests(creator_id)')
        
        # Проверяем существующие колонки и добавляем отсутствующие
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Добавляем отсутствующие колонки
        required_columns = [
            ('nickname', 'TEXT'),
            ('mining_trees', 'INTEGER DEFAULT 0'),
            ('last_snow_work', 'TIMESTAMP'),
            ('snow_cooldown_end', 'TIMESTAMP'),
            ('current_snow_job', 'TEXT'),
            ('snow_job_progress', 'INTEGER DEFAULT 0'),
            ('snow_job_total', 'INTEGER DEFAULT 0'),
            ('snow_job_end_time', 'TIMESTAMP'),
            ('snow_territory', 'TEXT'),
            ('last_bonus', 'INTEGER DEFAULT 0')
        ]
        
        for column_name, column_type in required_columns:
            if column_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                    logging.info(f"✅ Добавлена колонка {column_name}")
                except sqlite3.Error as e:
                    logging.error(f"❌ Ошибка добавления колонки {column_name}: {e}")
        
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
def is_private_chat(chat_id):
    """Проверяем, является ли чат личным диалогом с ботом"""
    return chat_id > 0  # ID личных чатов положительные, групп/каналов - отрицательные
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

# === ДОБАВЛЯЕМ ФУНКЦИЮ ДЛЯ УВЕДОМЛЕНИЙ О ПРОЦЕНТАХ ===
def notify_interest(user_id, interest_amount, bank_deposit):
    """Отправляет уведомление о начислении процентов"""
    try:
        bot.send_message(
            user_id,
            f"🏦 *НАЧИСЛЕНЫ ПРОЦЕНТЫ ПО ВКЛАДУ!*\n\n"
            f"💰 На вкладе: ❄️{format_balance(bank_deposit)}\n"
            f"📈 Начислено: +❄️{format_balance(interest_amount)}\n"
            f"⏰ Проценты начисляются каждый час",
            parse_mode='Markdown'
        )
        logging.info(f"Пользователю {user_id} начислены проценты: {interest_amount}❄️")
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления о процентах для {user_id}: {e}")

# === ОБНОВЛЯЕМ ФУНКЦИЮ НАЧИСЛЕНИЯ ПРОЦЕНТОВ ===
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
            interest = int(bank_deposit * 0.01 * interest_hours)  # 0.5% за каждый час (0.5% = 0.005)
            
            if interest > 0:
                # Начисляем проценты
                cursor.execute('UPDATE users SET balance = balance + ?, last_interest_calc = ? WHERE user_id = ?',
                             (interest, current_time, user_id))
                conn.commit()
                
                # Отправляем уведомление пользователю
                try:
                    notify_interest(user_id, interest, bank_deposit)
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление о процентах для {user_id}: {e}")
    
    conn.close()

# === ДОБАВЛЯЕМ ОБРАБОТЧИК ДЛЯ РУЧНОЙ ПРОВЕРКИ ПРОЦЕНТОВ ===
@bot.message_handler(func=lambda message: message.text.lower() == 'проценты')
def handle_check_interest(message):
    """Показывает информацию о процентах и принудительно начисляет их"""
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        # Принудительно начисляем проценты (если есть)
        calculate_interest(user_id)
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Получаем актуальные данные
        cursor.execute('''
            SELECT bank_deposit, balance, last_interest_calc 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        if result:
            bank_deposit, balance, last_calc = result
            
            message_text = "🏦 *ИНФОРМАЦИЯ О ПРОЦЕНТАХ*\n\n"
            
            if bank_deposit > 0:
                # Рассчитываем следующий час начислений
                current_time = time.time()
                
                if last_calc:
                    if isinstance(last_calc, str):
                        try:
                            last_calc_time = datetime.strptime(last_calc, '%Y-%m-%d %H:%M:%S').timestamp()
                        except:
                            last_calc_time = current_time - 3600
                    else:
                        last_calc_time = last_calc
                    
                    time_since_last = current_time - last_calc_time
                    time_to_next = 3600 - time_since_last
                    
                    if time_to_next > 0:
                        minutes = int(time_to_next // 60)
                        seconds = int(time_to_next % 60)
                        message_text += f"⏳ *До следующих процентов:* {minutes} мин {seconds} сек\n"
                    else:
                        message_text += "✅ *Следующие проценты скоро будут начислены*\n"
                
                # Расчет процентов в час
                interest_per_hour = int(bank_deposit * 0.005)
                
                message_text += f"\n💰 *На вкладе:* ❄️{format_balance(bank_deposit)}\n"
                message_text += f"📈 *Проценты в час:* +❄️{format_balance(interest_per_hour)}\n"
                message_text += f"📊 *Текущий баланс:* ❄️{format_balance(balance)}\n"
                message_text += f"💎 *Ставка:* 0.5% в час\n\n"
                message_text += "*Проценты начисляются автоматически каждый час!*"
                
            else:
                message_text += "💼 *У вас нет вклада в банке*\n\n"
                message_text += "📝 Чтобы получать проценты:\n"
                message_text += "1. Положите деньги на вклад\n"
                message_text += "2. Каждый час будете получать +0.5%\n\n"
                message_text += "💰 *Пример:*\n"
                message_text += "Вклад: 1.000.000❄️\n"
                message_text += "Проценты в час: +5.000❄️\n"
                message_text += "Проценты в день: +120.000❄️\n\n"
                message_text += "🔧 *Команда:* `вклад [сумма]`"
            
            bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
            
        else:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
        
        conn.close()
    
    except Exception as e:
        logging.error(f"Ошибка в handle_check_interest: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка проверки процентов")


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


# Главное меню - разные для группового чата и ЛС
def create_main_menu(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if chat_id > 0:  # Личные сообщения с ботом
        # Меню для ЛС (полное меню)
        markup.add(
            KeyboardButton("Я"),
            KeyboardButton("Майнинг"),
            KeyboardButton("Банк"),
            KeyboardButton("Игры"),
            KeyboardButton("Работа"),
            KeyboardButton("Топ снежков"),
            KeyboardButton("🏠 Дом"),
            KeyboardButton("Бонус")
        )
    else:  # Групповой чат/канал
        # Упрощенное меню для группового чата
        markup.add(
            KeyboardButton("Баланс"),
            KeyboardButton("Топ"),
            KeyboardButton("Игры")
        )
    
    return markup





# === ГЛОБАЛЬНЫЙ СЛОВАРЬ ДЛЯ ХРАНЕНИЯ РЕФЕРАЛЬНЫХ КОДОВ ВО ВРЕМЯ КАПЧИ ===
pending_ref_codes = {}  # {user_id: ref_code}
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
        
        # Используем существующую функцию для создания меню
        markup = create_main_menu(message.chat.id)
        
        # Тексты приветствия в зависимости от типа чата
        if message.chat.id > 0:  # ЛС
            welcome_text = "✨ *Добро пожаловать!* ✨\n\nВыберите действие из меню ниже:"
        else:  # Групповой чат
            welcome_text = f"👋 Привет, {first_name}!\n\nИспользуйте меню ниже для работы с ботом в этом чате.\n\n💡 *Для полного функционала напишите мне в ЛС!*"
        
        # Отправляем приветственное сообщение с соответствующим меню
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')
    
    except Exception as e:
        logging.error(f"Ошибка в start: {e}", exc_info=True)
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте снова позже.")

# Обработчик для кнопки "Баланс" в группе
@bot.message_handler(func=lambda message: message.text == "Баланс" and message.chat.id < 0)
def handle_balance_group(message):
    try:
        user_id = message.from_user.id
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!")
            return
            
        balance = get_balance(user_id)
        
        # Получаем никнейм или имя пользователя
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT first_name, nickname FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            first_name, nickname = result
            display_name = nickname if nickname and nickname.strip() else first_name
        else:
            display_name = message.from_user.first_name
        
        response = f"👤 {display_name}\n💰 Баланс: ❄️{format_balance(balance)}"
        
        bot.send_message(message.chat.id, response)
        
    except Exception as e:
        logging.error(f"Ошибка в handle_balance_group: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# Обработчик для кнопки "Топ" в группе
@bot.message_handler(func=lambda message: message.text == "Топ" and message.chat.id < 0)
def handle_top_group(message):
    try:
        user_id = message.from_user.id
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!")
            return
        
        # Показываем мини-топ (первые 3 места)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Топ по балансу
        cursor.execute('''
        SELECT user_id, balance, 
               CASE 
                   WHEN username IS NOT NULL AND username != '' THEN '@' || username 
                   ELSE first_name 
               END as display_name
        FROM users 
        WHERE balance > 0 AND is_banned = 0
        ORDER BY balance DESC
        LIMIT 3
        ''')
        
        top_users = cursor.fetchall()
        
        response = "🏆 *Топ снежков:*\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (user_id_db, balance, display_name) in enumerate(top_users, 1):
            # Получаем nickname если есть
            cursor.execute('SELECT nickname FROM users WHERE user_id = ?', (user_id_db,))
            nickname_result = cursor.fetchone()
            
            if nickname_result and nickname_result[0]:
                display_name = nickname_result[0]
            
            response += f"{medals[i-1]} {display_name}: ❄️{format_balance(balance)}\n"
        
        conn.close()
        
        # Добавляем позицию текущего пользователя
        user_position = get_user_position_in_top(user_id, 'balance')
        user_balance = get_balance(user_id)
        
        if user_position:
            response += f"\n🎯 Твоя позиция: #{user_position}\n💰 Твой баланс: ❄️{format_balance(user_balance)}"
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_top_group: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")
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
                    REFERRAL_BONUS = 888
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





# === ОБНОВЛЕННЫЙ ОБРАБОТЧИК /start ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ И КОНКУРСОВ ===
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
        
        # Проверяем есть ли код в ссылке (реферальный или конкурс)
        start_code = None
        if len(message.text.split()) > 1:
            start_code = message.text.split()[1].strip()
            logging.info(f"Пользователь {user_id} пришел по ссылке с кодом: {start_code}")
        
        # ПРОВЕРЯЕМ КОНКУРС ПРЕЖДЕ ВСЕГО
        if start_code and start_code.startswith('contest_'):
            # Это участие в конкурсе
            contest_id = start_code
            
            if contest_id in ACTIVE_CONTESTS:
                contest = ACTIVE_CONTESTS[contest_id]
                
                # Проверяем статус конкурса
                if contest.get('status') != 'active':
                    bot.send_message(message.chat.id, "❌ Этот конкурс уже завершен")
                    return
                
                # Сначала проверяем/создаем пользователя
                user_data = get_or_create_user(user_id, username, first_name)
                
                # Проверяем капчу
                if user_data['captcha_passed'] == 0:
                    # Показываем капчу для доступа
                    captcha_question, correct_answer = generate_captcha()
                    user_captcha_status[user_id] = correct_answer
                    
                    bot.send_message(message.chat.id, 
                                   f"🔒 Для участия в конкурсе решите пример:\n\n"
                                   f"{captcha_question}\n\n"
                                   f"Отправьте ответ числом в чат.")
                    return
                
                # Проверяем подписку на канал
                channel_id = contest.get('channel_id')
                if channel_id:
                    try:
                        chat_member = bot.get_chat_member(channel_id, user_id)
                        if chat_member.status not in ['member', 'administrator', 'creator']:
                            channel_name = contest.get('channel_title', 'канал')
                            bot.send_message(
                                message.chat.id,
                                f"❌ Для участия в конкурсе подпишитесь на канал:\n"
                                f"{channel_name}\n\n"
                                f"После подписки нажмите на ссылку снова"
                            )
                            return
                    except:
                        # Если не можем проверить, продолжаем
                        pass
                
                # Проверяем участие
                if user_id in CONTEST_PARTICIPANTS.get(contest_id, []):
                    bot.send_message(message.chat.id, "✅ Вы уже участвуете в этом конкурсе!")
                else:
                    # Проверяем лимит
                    current = len(CONTEST_PARTICIPANTS.get(contest_id, []))
                    max_limit = contest.get('max_participants', 0)
                    
                    if current >= max_limit:
                        bot.send_message(message.chat.id, "❌ Конкурс уже набрал участников")
                        return
                    
                    # Добавляем участника
                    if contest_id not in CONTEST_PARTICIPANTS:
                        CONTEST_PARTICIPANTS[contest_id] = []
                    
                    CONTEST_PARTICIPANTS[contest_id].append(user_id)
                    current = len(CONTEST_PARTICIPANTS[contest_id])
                    
                    # Уведомляем
                    response = f"✅ *ВЫ УЧАСТВУЕТЕ!*\n\n"
                    response += f"📢 {contest.get('channel_title', 'Конкурс')}\n"
                    response += f"👥 Участников: {current}/{max_limit}\n"
                    response += f"🏆 Победителей: {contest.get('winners_count', 'N/A')}\n\n"
                    response += f"*⏳ Ждите результатов!*"
                    
                    bot.send_message(message.chat.id, response, parse_mode='Markdown')
                    
                    # Уведомляем создателя если набрали
                    if current == max_limit:
                        try:
                            bot.send_message(
                                contest['creator_id'],
                                f"🎉 *КОНКУРС НАБРАЛ УЧАСТНИКОВ!*\n\n"
                                f"Конкурс: {contest.get('channel_title', 'N/A')}\n"
                                f"Участников: {current}/{max_limit}\n\n"
                                f"Используйте: `итоги {contest_id}`",
                                parse_mode='Markdown'
                            )
                        except:
                            pass
                    
                    logging.info(f"Участник {user_id} присоединился к {contest_id}")
                
                # Показываем главное меню
                markup = create_main_menu()
                bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)
                return
        
        # Обычная регистрация (не конкурс)
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
                REFERRAL_BONUS = 888  # Бонус за реферала
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


# =============== МИНИМАЛИСТИЧНАЯ СИСТЕМА 3% БОНУСА ОТ ВЫИГРЫШЕЙ ===============

def add_referral_win_bonus(user_id, win_amount, game_name):
    """Добавляет бонус рефереру за выигрыш реферала (3%)"""
    try:
        if win_amount < 1:
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result or not result[0]:
            conn.close()
            return
        
        referrer_id = result[0]
        
        cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (referrer_id,))
        referrer_data = cursor.fetchone()
        
        if not referrer_data or referrer_data[0] == 1:
            conn.close()
            return
        
        bonus_amount = int(win_amount * 0.03)
        if bonus_amount < 1:
            bonus_amount = 1
        
        # Сохраняем в БД
        cursor.execute('''
        INSERT INTO referral_wins (referrer_id, referee_id, win_amount, bonus_amount, game_name)
        VALUES (?, ?, ?, ?, ?)
        ''', (referrer_id, user_id, win_amount, bonus_amount, game_name))
        
        # Начисляем бонус
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', 
                     (bonus_amount, referrer_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка бонуса от выигрыша: {e}")

@bot.message_handler(func=lambda message: message.text == "👥 Скам")
def handle_scam(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем наличие таблицы referral_wins
        cursor.execute("PRAGMA table_info(referral_wins)")
        referral_wins_exists = cursor.fetchone()
        
        if not referral_wins_exists:
            # Создаем таблицу если ее нет
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_wins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referee_id INTEGER,
                win_amount INTEGER,
                bonus_amount INTEGER,
                game_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            conn.commit()
        
        cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.send_message(message.chat.id, "❌ Реферальный код не найден")
            conn.close()
            return
        
        ref_code = result[0]
        
        # Получаем количество рефералов
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
        ref_count_result = cursor.fetchone()
        ref_count = ref_count_result[0] if ref_count_result else 0
        
        # Получаем статистику бонусов
        cursor.execute('''
            SELECT 
                SUM(bonus_amount) as total_bonus,
                COUNT(*) as total_wins
            FROM referral_wins 
            WHERE referrer_id = ?
        ''', (user_id,))
        
        bonus_stats = cursor.fetchone()
        total_bonus = bonus_stats[0] if bonus_stats and bonus_stats[0] else 0
        total_wins = bonus_stats[1] if bonus_stats and bonus_stats[1] else 0
        
        ref_link = f"https://t.me/{(bot.get_me()).username}?start={ref_code}"
        
        # Формируем сообщение
        message_text = f"👥 *Твоя ссылка:*\n`{ref_link}`\n\n"
        message_text += f"📊 *Статистика:*\n"
        message_text += f"• Рефералов: {ref_count}\n"
        message_text += f"• Бонусы от игр: {format_balance(total_bonus)}❄️\n"
        message_text += f"• Выигрышей: {total_wins}\n\n"
        message_text += f"💡 *+3% от ВСЕХ выигрышей рефералов*"
        
        # Кнопка обновления
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄", callback_data="refresh_scam"))
        
        bot.send_message(message.chat.id, message_text, parse_mode='Markdown', reply_markup=markup)
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка в handle_scam: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:50]}")
@bot.callback_query_handler(func=lambda call: call.data == "refresh_scam")
def refresh_scam_callback(call):
    try:
        user_id = call.from_user.id
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            conn.close()
            return
        
        ref_code = result[0]
        
        # Количество рефералов
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_banned = 0', (user_id,))
        ref_count_result = cursor.fetchone()
        ref_count = ref_count_result[0] if ref_count_result else 0
        
        # Статистика бонусов
        cursor.execute('''
            SELECT 
                SUM(bonus_amount) as total_bonus,
                COUNT(*) as total_wins
            FROM referral_wins 
            WHERE referrer_id = ?
        ''', (user_id,))
        
        bonus_stats = cursor.fetchone()
        total_bonus = bonus_stats[0] if bonus_stats and bonus_stats[0] else 0
        total_wins = bonus_stats[1] if bonus_stats and bonus_stats[1] else 0
        
        ref_link = f"https://t.me/{(bot.get_me()).username}?start={ref_code}"
        
        # Обновляем сообщение
        message_text = f"👥 *Твоя ссылка:*\n`{ref_link}`\n\n"
        message_text += f"📊 *Статистика:*\n"
        message_text += f"• Рефералов: {ref_count}\n"
        message_text += f"• Бонусы от игр: {format_balance(total_bonus)}❄️\n"
        message_text += f"• Выигрышей: {total_wins}\n\n"
        message_text += f"💡 *+3% от ВСЕХ выигрышей рефералов*"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄", callback_data="refresh_scam"))
        
        try:
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            logging.error(f"Ошибка редактирования: {e}")
        
        bot.answer_callback_query(call.id, "✅")
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Ошибка refresh_scam: {e}")
        bot.answer_callback_query(call.id, "❌")



@bot.message_handler(func=lambda message: message.text.lower() == "я")
def handle_me(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT first_name, video_cards, bank_deposit, last_mining_collect, registered_at 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        if result:
            first_name, video_cards, bank_deposit, last_mining_collect, registered_at = result
            
            # Рассчитываем накопленные елки
            total_accumulated = 0
            if last_mining_collect and last_mining_collect > 0 and video_cards > 0:
                current_time = time.time()
                hours_passed = int((current_time - last_mining_collect) / 3600)
                if hours_passed > 0:
                    hourly_income = video_cards * (video_cards + 1) // 2
                    total_accumulated = hourly_income * hours_passed
            
            # Получаем престижные данные
            prestige_id = get_prestige_id(user_id)
            prestige_badge = get_prestige_badge(user_id)
            
            # Форматируем дату регистрации
            reg_date = "Неизвестно"
            if registered_at:
                try:
                    reg_date = registered_at[:10]  # Берем только дату
                except:
                    reg_date = str(registered_at)[:10]
            
            # Создаем сообщение
            message_text = f"👤 *{first_name}*\n"
            message_text += f"{prestige_id}\n\n"
            
            
            message_text += f"💰 *Баланс:* ❄️{format_balance(balance)}\n"
            
            if video_cards > 0:
                message_text += f"*Елки:* 🎄{total_accumulated}\n"
                
            else:
                message_text += f"🎄 *Елки:* 🎄0\n"
                
            
            if bank_deposit > 0:
                message_text += f"🏦 *В банке:* ❄️{format_balance(bank_deposit)}\n"
            
            message_text += f"📅 *Регистрация:* {reg_date}"
            
            # Получаем текущий дом
            current_house = get_current_house(user_id)
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                message_text += f"\n🏠 *Дом:* {house_name}"
            
            # Отправляем с фото дома если есть
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_image = house_info.get('image')
                
                if house_image and os.path.exists(house_image):
                    try:
                        with open(house_image, 'rb') as img_file:
                            bot.send_photo(message.chat.id, img_file, caption=message_text, parse_mode='Markdown')
                            conn.close()
                            return
                    except:
                        pass
            
            conn.close()
            
            # Пробуем отправить с g.png или просто текст
            try:
                if os.path.exists("g.png"):
                    with open('g.png', 'rb') as photo:
                        bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='Markdown')
                else:
                    bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
            except:
                bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
            
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")
# Глобальные переменные для системы домов
user_houses = {}  # {user_id: {"current_house": house_id, "houses": [house_id1, house_id2...]}}
HOUSE_SHOP = {}   # {house_id: {"name": "Название", "price": 1000, "image": "filename.png"}}

# === ЗАГРУЗКА МАГАЗИНА ПРИ ЗАПУСКЕ ===
def load_house_shop():
    """Загружает магазин домов из файла"""
    global HOUSE_SHOP
    try:
        if os.path.exists('house_shop.json'):
            import json
            with open('house_shop.json', 'r', encoding='utf-8') as f:
                HOUSE_SHOP = json.load(f)
            logging.info(f"✅ Загружен магазин домов: {len(HOUSE_SHOP)} домов")
    except Exception as e:
        logging.error(f"Ошибка загрузки магазина: {e}")
        HOUSE_SHOP = {}

def save_house_shop():
    """Сохраняет магазин домов в файл"""
    try:
        import json
        with open('house_shop.json', 'w', encoding='utf-8') as f:
            json.dump(HOUSE_SHOP, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения магазина: {e}")

# === ОБРАБОТЧИК КНОПКИ "🏠 Дом" ===
@bot.message_handler(func=lambda message: message.text == "🏠 Дом")
def handle_house(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        # Создаем клавиатуру для дома
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"),
            InlineKeyboardButton("🚪 Шкаф", callback_data="house_wardrobe"),
            InlineKeyboardButton("🏠 Текущий дом", callback_data="house_current"),
            InlineKeyboardButton("❓ Помощь", callback_data="house_help")
        )
        
        # Получаем текущий дом пользователя
        current_house = get_current_house(user_id)
        
        if current_house:
            house_info = HOUSE_SHOP.get(current_house, {})
            house_name = house_info.get('name', 'Неизвестный дом')
            response = f"🏠 *Ваш дом*\n\n🏡 *{house_name}*\n\nВыберите действие:"
        else:
            response = "🏠 *Ваш дом*\n\n🚫 У вас еще нет дома!\n\n🛒 Купите дом в магазине:"
        
        bot.send_message(message.chat.id, response, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в доме: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки дома")

# === ФУНКЦИИ ДЛЯ РАБОТЫ С ДОМАМИ ===
def get_current_house(user_id):
    """Получает текущий дом пользователя"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем есть ли таблица houses
        cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='user_houses'
        """)
        
        if not cursor.fetchone():
            # Создаем таблицу если ее нет
            cursor.execute("""
            CREATE TABLE user_houses (
                user_id INTEGER,
                house_id TEXT,
                is_current INTEGER DEFAULT 0,
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, house_id)
            )
            """)
            conn.commit()
        
        # Получаем текущий дом
        cursor.execute("""
        SELECT house_id FROM user_houses 
        WHERE user_id = ? AND is_current = 1
        """, (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
        
    except Exception as e:
        logging.error(f"Ошибка получения дома: {e}")
        return None

def get_user_houses(user_id):
    """Получает все дома пользователя"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT house_id, is_current FROM user_houses 
        WHERE user_id = ? ORDER BY purchased_at DESC
        """, (user_id,))
        
        houses = cursor.fetchall()
        conn.close()
        
        return houses
        
    except Exception as e:
        logging.error(f"Ошибка получения домов: {e}")
        return []

def purchase_house(user_id, house_id):
    """Покупка дома"""
    try:
        house_info = HOUSE_SHOP.get(house_id)
        if not house_info:
            return False, "Дом не найден в магазине"
        
        # Проверяем не куплен ли уже дом
        houses = get_user_houses(user_id)
        for house, _ in houses:
            if house == house_id:
                return False, "У вас уже есть этот дом"
        
        # Проверяем баланс
        price = house_info['price']
        balance = get_balance(user_id)
        
        if balance < price:
            return False, f"Недостаточно средств. Нужно: {format_balance(price)}❄️"
        
        # Списываем деньги
        update_balance(user_id, -price)
        
        # Добавляем дом в базу
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Если это первый дом, делаем его текущим
        is_first = len(houses) == 0
        
        cursor.execute("""
        INSERT INTO user_houses (user_id, house_id, is_current) 
        VALUES (?, ?, ?)
        """, (user_id, house_id, 1 if is_first else 0))
        
        conn.commit()
        conn.close()
        
        return True, "✅ Дом куплен!"
        
    except Exception as e:
        logging.error(f"Ошибка покупки дома: {e}")
        return False, "❌ Ошибка покупки"

def set_current_house(user_id, house_id):
    """Устанавливает текущий дом"""
    try:
        # Проверяем есть ли у пользователя этот дом
        houses = get_user_houses(user_id)
        has_house = False
        for house, _ in houses:
            if house == house_id:
                has_house = True
                break
        
        if not has_house:
            return False, "У вас нет этого дома"
        
        # Обновляем в базе
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Сначала сбрасываем все дома
        cursor.execute("""
        UPDATE user_houses SET is_current = 0 WHERE user_id = ?
        """, (user_id,))
        
        # Устанавливаем новый текущий дом
        cursor.execute("""
        UPDATE user_houses SET is_current = 1 
        WHERE user_id = ? AND house_id = ?
        """, (user_id, house_id))
        
        conn.commit()
        conn.close()
        
        return True, "✅ Дом установлен как текущий!"
        
    except Exception as e:
        logging.error(f"Ошибка установки дома: {e}")
        return False, "❌ Ошибка"

# === КОМАНДА АДМИНА ДЛЯ ДОБАВЛЕНИЯ ДОМА ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('дом ') and is_admin(message.from_user.id))
def handle_add_house(message):
    """Добавление дома в магазин"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, 
                           "❌ Формат: дом [цена] [название_файла.png]\n"
                           "Пример: дом 1000000 mansion.png")
            return
        
        try:
            price = int(parts[1])
            if price < 0:
                bot.send_message(message.chat.id, "❌ Цена не может быть отрицательной")
                return
        except:
            bot.send_message(message.chat.id, "❌ Неверная цена")
            return
        
        filename = parts[2].strip()
        
        # Проверяем существует ли файл
        if not os.path.exists(filename):
            bot.send_message(message.chat.id, f"❌ Файл '{filename}' не найден")
            return
        
        # Генерируем ID дома
        house_id = f"house_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Получаем имя дома из имени файла (без расширения)
        house_name = os.path.splitext(filename)[0].replace('_', ' ').title()
        
        # Добавляем дом в магазин
        HOUSE_SHOP[house_id] = {
            "name": house_name,
            "price": price,
            "image": filename,
            "added_by": message.from_user.id,
            "added_at": time.time()
        }
        
        # Сохраняем магазин в файл
        save_house_shop()
        
        bot.send_message(message.chat.id,
                       f"✅ Дом добавлен в магазин!\n\n"
                       f"🏡 Название: {house_name}\n"
                       f"💰 Цена: {format_balance(price)}❄️\n"
                       f"🖼 Файл: {filename}\n"
                       f"🔑 ID: {house_id}")
        
    except Exception as e:
        logging.error(f"Ошибка добавления дома: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

# === МАГАЗИН ДОМОВ С ИЗОБРАЖЕНИЯМИ ===
def create_house_shop_keyboard(page=1):
    """Создает клавиатуру для магазина домов с пагинацией"""
    markup = InlineKeyboardMarkup(row_width=2)
    
    # Получаем дома для текущей страницы
    house_ids = list(HOUSE_SHOP.keys())
    total_houses = len(house_ids)
    
    if total_houses == 0:
        markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
        return markup
    
    total_pages = total_houses  # Показываем по 1 дому на странице
    page = max(1, min(page, total_pages))
    
    # Кнопки навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"shop_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="shop_current"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"shop_page_{page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    # Кнопка покупки текущего дома
    current_house_id = house_ids[page-1]
    house_info = HOUSE_SHOP.get(current_house_id, {})
    
    markup.row(InlineKeyboardButton(f"💰 Купить за {format_balance(house_info.get('price', 0))}❄️", 
                                   callback_data=f"buy_house_{current_house_id}"))
    
    # Кнопки управления
    markup.row(
        InlineKeyboardButton("🚪 Шкаф", callback_data="house_wardrobe"),
        InlineKeyboardButton("🔙 Назад", callback_data="house_back")
    )
    
    return markup

# === ОБРАБОТЧИК МАГАЗИНА С ИЗОБРАЖЕНИЯМИ ===
@bot.callback_query_handler(func=lambda call: call.data in ["house_shop", "shop_current"] or call.data.startswith("shop_page_"))
def handle_shop_with_images(call):
    try:
        user_id = call.from_user.id
        
        # Определяем страницу
        if call.data == "house_shop":
            page = 1
        elif call.data.startswith("shop_page_"):
            page = int(call.data.split("_")[2])
        else:  # shop_current
            page = 1
        
        # Получаем данные дома для текущей страницы
        house_ids = list(HOUSE_SHOP.keys())
        total_houses = len(house_ids)
        
        if total_houses == 0:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
            
            bot.edit_message_text(
                "🛒 *Магазин домов*\n\n🚫 В магазине пока нет домов.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        
        page = max(1, min(page, total_houses))
        house_id = house_ids[page-1]
        house_info = HOUSE_SHOP.get(house_id, {})
        
        # Получаем изображение дома
        house_image = house_info.get('image')
        
        if house_image and os.path.exists(house_image):
            try:
                # Отправляем новое сообщение с изображением
                with open(house_image, 'rb') as img_file:
                    # Создаем подпись
                    caption = f"🛒 *Магазин домов*\n\n"
                    caption += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                    caption += f"💰 Цена: {format_balance(house_info.get('price', 0))}❄️\n"
                    caption += f"📊 Страница: {page}/{total_houses}\n\n"
                    caption += "💡 Нажмите '💰 Купить' чтобы приобрести этот дом"
                    
                    # Отправляем фото
                    bot.send_photo(
                        call.message.chat.id,
                        img_file,
                        caption=caption,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                
                # Удаляем старое сообщение
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                
            except Exception as e:
                logging.error(f"Ошибка отправки изображения: {e}")
                # Если не удалось отправить изображение, показываем только текст
                text = f"🛒 *Магазин домов*\n\n"
                text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                text += f"💰 Цена: {format_balance(house_info.get('price', 0))}❄️\n"
                text += f"📊 Страница: {page}/{total_houses}\n\n"
                text += "❌ Изображение недоступно"
                
                try:
                    bot.edit_message_text(
                        text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                except:
                    bot.send_message(
                        call.message.chat.id,
                        text,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
        else:
            # Если нет изображения, показываем только текст
            text = f"🛒 *Магазин домов*\n\n"
            text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
            text += f"💰 Цена: {format_balance(house_info.get('price', 0))}❄️\n"
            text += f"📊 Страница: {page}/{total_houses}\n\n"
            text += "❌ Изображение дома недоступно"
            
            try:
                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_house_shop_keyboard(page),
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    text,
                    reply_markup=create_house_shop_keyboard(page),
                    parse_mode='Markdown'
                )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logging.error(f"Ошибка в магазине: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# === ОБРАБОТЧИК ПОКУПКИ ДОМА ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_house_"))
def handle_buy_house(call):
    try:
        user_id = call.from_user.id
        house_id = call.data[10:]  # Убираем "buy_house_"
        house_info = HOUSE_SHOP.get(house_id)
        
        if not house_info:
            bot.answer_callback_query(call.id, "❌ Дом не найден")
            return
        
        house_name = house_info['name']
        house_price = house_info['price']
        
        # Проверяем баланс
        balance = get_balance(user_id)
        
        if balance < house_price:
            bot.answer_callback_query(
                call.id, 
                f"❌ Недостаточно средств! Нужно: {format_balance(house_price)}❄️",
                show_alert=True
            )
            return
        
        # Покупаем дом
        success, message = purchase_house(user_id, house_id)
        
        if success:
            # Определяем текущую страницу из сообщения
            page = 1
            if call.message.caption:
                import re
                match = re.search(r'Страница (\d+)/(\d+)', call.message.caption)
                if match:
                    page = int(match.group(1))
            
            # Обновляем магазин
            try:
                # Получаем данные для текущей страницы
                house_ids = list(HOUSE_SHOP.keys())
                total_houses = len(house_ids)
                page = max(1, min(page, total_houses))
                current_house_id = house_ids[page-1]
                current_house_info = HOUSE_SHOP.get(current_house_id, {})
                
                # Обновляем подпись
                caption = f"🛒 *Магазин домов*\n\n"
                caption += f"🏡 *{current_house_info.get('name', 'Неизвестный дом')}*\n"
                caption += f"💰 Цена: {format_balance(current_house_info.get('price', 0))}❄️\n"
                caption += f"📊 Страница: {page}/{total_houses}\n\n"
                caption += "✅ Дом куплен! Зайдите в шкаф чтобы выбрать его"
                
                # Если есть изображение, обновляем его
                house_image = current_house_info.get('image')
                if house_image and os.path.exists(house_image):
                    try:
                        with open(house_image, 'rb') as img_file:
                            bot.edit_message_media(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                media=telebot.types.InputMediaPhoto(
                                    media=img_file,
                                    caption=caption,
                                    parse_mode='Markdown'
                                ),
                                reply_markup=create_house_shop_keyboard(page)
                            )
                    except:
                        # Если не удалось обновить медиа, обновляем только текст
                        bot.edit_message_caption(
                            caption=caption,
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=create_house_shop_keyboard(page),
                            parse_mode='Markdown'
                        )
                else:
                    # Если нет изображения, обновляем текст
                    bot.edit_message_caption(
                        caption=caption,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=create_house_shop_keyboard(page),
                        parse_mode='Markdown'
                    )
                    
            except Exception as e:
                logging.error(f"Ошибка обновления магазина: {e}")
                # Если не удалось обновить, просто показываем сообщение об успехе
                pass
            
            bot.answer_callback_query(call.id, f"✅ Куплен дом '{house_name}'!")
            
            # Отправляем изображение купленного дома
            house_image = house_info.get('image')
            if house_image and os.path.exists(house_image):
                try:
                    with open(house_image, 'rb') as img_file:
                        bot.send_photo(
                            call.message.chat.id,
                            img_file,
                            caption=f"🎉 Вы купили новый дом!\n\n"
                                  f"🏡 *{house_name}*\n"
                                  f"💰 Цена: {format_balance(house_price)}❄️\n\n"
                                  f"💡 Зайдите в 🚪 Шкаф чтобы выбрать этот дом как текущий",
                            parse_mode='Markdown'
                        )
                except:
                    pass
        else:
            bot.answer_callback_query(call.id, message, show_alert=True)
            
    except Exception as e:
        logging.error(f"Ошибка покупки дома: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка покупки")

# === ШКАФ (ИНВЕНТАРЬ ДОМОВ) ===
def create_wardrobe_keyboard(user_id, page=1):
    """Создает клавиатуру для шкафа с пагинацией"""
    markup = InlineKeyboardMarkup(row_width=2)
    
    # Получаем дома пользователя
    houses = get_user_houses(user_id)
    total_houses = len(houses)
    
    if total_houses == 0:
        markup.row(InlineKeyboardButton("🛒 В магазин", callback_data="house_shop"))
        markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
        return markup
    
    total_pages = total_houses  # Показываем по 1 дому на странице
    page = max(1, min(page, total_pages))
    
    # Получаем текущий дом
    current_house = get_current_house(user_id)
    
    # Кнопки навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"wardrobe_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="wardrobe_current"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"wardrobe_page_{page+1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    # Получаем текущий дом на странице
    house_id, is_current = houses[page-1]
    house_info = HOUSE_SHOP.get(house_id, {"name": "Неизвестный дом"})
    
    # Кнопка выбора дома если он не текущий
    if house_id != current_house:
        markup.row(InlineKeyboardButton(f"✅ Выбрать {house_info['name']}", callback_data=f"set_house_{house_id}"))
    
    # Кнопки управления
    markup.row(
        InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"),
        InlineKeyboardButton("🔙 Назад", callback_data="house_back")
    )
    
    return markup

# === ОБРАБОТЧИКИ ШКАФА ===
@bot.callback_query_handler(func=lambda call: call.data == "house_wardrobe" or 
                                          call.data.startswith("wardrobe_page_") or 
                                          call.data == "wardrobe_current")
def handle_wardrobe(call):
    try:
        user_id = call.from_user.id
        
        # Определяем страницу
        if call.data == "house_wardrobe":
            page = 1
        elif call.data.startswith("wardrobe_page_"):
            page = int(call.data.split("_")[2])
        else:  # wardrobe_current
            page = 1
        
        # Получаем дома пользователя
        houses = get_user_houses(user_id)
        total_houses = len(houses)
        
        if total_houses == 0:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🛒 В магазин", callback_data="house_shop"))
            markup.row(InlineKeyboardButton("🔙 Назад", callback_data="house_back"))
            
            bot.edit_message_text(
                "🚪 *Шкаф*\n\n🚫 У вас еще нет домов.\n\n🛒 Купите дом в магазине!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        
        page = max(1, min(page, total_houses))
        house_id, is_current = houses[page-1]
        house_info = HOUSE_SHOP.get(house_id, {})
        current_house = get_current_house(user_id)
        
        # Получаем изображение дома
        house_image = house_info.get('image')
        
        if house_image and os.path.exists(house_image):
            try:
                # Создаем подпись
                caption = f"🚪 *Ваш шкаф*\n\n"
                caption += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                caption += f"📊 Страница: {page}/{total_houses}\n"
                
                if house_id == current_house:
                    caption += f"\n✅ *Текущий дом*\n"
                else:
                    caption += f"\n💡 Нажмите '✅ Выбрать' чтобы установить этот дом как текущий"
                
                # Отправляем новое сообщение с изображением
                with open(house_image, 'rb') as img_file:
                    bot.send_photo(
                        call.message.chat.id,
                        img_file,
                        caption=caption,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                
                # Удаляем старое сообщение
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                
            except Exception as e:
                logging.error(f"Ошибка отправки изображения шкафа: {e}")
                # Если не удалось отправить изображение, показываем только текст
                text = f"🚪 *Ваш шкаф*\n\n"
                text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                text += f"📊 Страница: {page}/{total_houses}\n"
                
                if house_id == current_house:
                    text += f"\n✅ *Текущий дом*\n"
                else:
                    text += f"\n💡 Нажмите '✅ Выбрать' чтобы установить этот дом как текущий"
                
                try:
                    bot.edit_message_text(
                        text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                except:
                    bot.send_message(
                        call.message.chat.id,
                        text,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
        else:
            # Если нет изображения, показываем только текст
            text = f"🚪 *Ваш шкаф*\n\n"
            text += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
            text += f"📊 Страница: {page}/{total_houses}\n"
            
            if house_id == current_house:
                text += f"\n✅ *Текущий дом*\n"
            else:
                text += f"\n💡 Нажмите '✅ Выбрать' чтобы установить этот дом как текущий"
            
            try:
                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_wardrobe_keyboard(user_id, page),
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    text,
                    reply_markup=create_wardrobe_keyboard(user_id, page),
                    parse_mode='Markdown'
                )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logging.error(f"Ошибка в шкафу: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# === ОБРАБОТЧИКИ ОСТАЛЬНЫХ КОЛБЭКОВ ДОМОВ ===
@bot.callback_query_handler(func=lambda call: call.data in ["house_current", "house_help", "house_back", "set_house_", "wardrobe_current"])
def house_other_callback_handler(call):
    try:
        user_id = call.from_user.id
        
        if call.data == "house_current":
            # Текущий дом
            current_house = get_current_house(user_id)
            
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                
                # Пытаемся отправить изображение
                house_image = house_info.get('image')
                if house_image and os.path.exists(house_image):
                    try:
                        with open(house_image, 'rb') as img_file:
                            bot.send_photo(
                                call.message.chat.id,
                                img_file,
                                caption=f"🏠 *Текущий дом*\n\n"
                                      f"🏡 *{house_name}*\n\n"
                                      f"💡 Чтобы сменить дом, зайдите в 🚪 Шкаф",
                                parse_mode='Markdown'
                            )
                    except:
                        bot.send_message(
                            call.message.chat.id,
                            f"🏠 *Текущий дом*\n\n"
                            f"🏡 *{house_name}*",
                            parse_mode='Markdown'
                        )
                else:
                    bot.send_message(
                        call.message.chat.id,
                        f"🏠 *Текущий дом*\n\n"
                        f"🏡 *{house_name}*",
                        parse_mode='Markdown'
                    )
            else:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🛒 В магазин", callback_data="house_shop"))
                
                bot.send_message(
                    call.message.chat.id,
                    "🚫 У вас еще нет дома!\n\n🛒 Купите дом в магазине:",
                    reply_markup=markup
                )
            
            bot.answer_callback_query(call.id)
            
        elif call.data == "house_help":
            # Помощь
            help_text = (
                "🏠 *Система домов*\n\n"
                "🛒 *Магазин* - Покупайте новые дома (отображаются с картинками)\n"
                "🚪 *Шкаф* - Управляйте своими домами\n"
                "🏠 *Текущий дом* - Просмотр активного дома\n\n"
                "*Как использовать:*\n"
                "1. Купите дом в магазине (перелистывайте кнопками ⬅️➡️)\n"
                "2. Выберите его в шкафе как текущий\n"
                "3. Ваш дом будет отображаться в профиле\n\n"
                "*Для администраторов:*\n"
                "`дом [цена] [файл.png]` - добавить дом в магазин"
            )
            
            try:
                bot.edit_message_text(
                    help_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    help_text,
                    parse_mode='Markdown'
                )
            
            bot.answer_callback_query(call.id)
            
        elif call.data == "house_back":
            # Назад к главному меню дома
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("🛒 Магазин", callback_data="house_shop"),
                InlineKeyboardButton("🚪 Шкаф", callback_data="house_wardrobe"),
                InlineKeyboardButton("🏠 Текущий дом", callback_data="house_current"),
                InlineKeyboardButton("❓ Помощь", callback_data="house_help")
            )
            
            current_house = get_current_house(user_id)
            
            if current_house:
                house_info = HOUSE_SHOP.get(current_house, {})
                house_name = house_info.get('name', 'Неизвестный дом')
                response = f"🏠 *Ваш дом*\n\n🏡 *{house_name}*\n\nВыберите действие:"
            else:
                response = "🏠 *Ваш дом*\n\n🚫 У вас еще нет дома!\n\n🛒 Купите дом в магазине:"
            
            try:
                bot.edit_message_text(
                    response,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    response,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            
            bot.answer_callback_query(call.id)
            
        elif call.data.startswith("set_house_"):
            # Установка текущего дома
            house_id = call.data[10:]  # Убираем "set_house_"
            house_info = HOUSE_SHOP.get(house_id)
            
            if not house_info:
                bot.answer_callback_query(call.id, "❌ Дом не найден")
                return
            
            # Устанавливаем дом как текущий
            success, message = set_current_house(user_id, house_id)
            
            if success:
                # Определяем текущую страницу
                page = 1
                if call.message.caption:
                    import re
                    match = re.search(r'Страница (\d+)/(\d+)', call.message.caption)
                    if match:
                        page = int(match.group(1))
                
                # Обновляем шкаф
                try:
                    houses = get_user_houses(user_id)
                    total_houses = len(houses)
                    page = max(1, min(page, total_houses))
                    
                    # Получаем текущий дом на странице
                    current_house_id = get_current_house(user_id)
                    house_info = HOUSE_SHOP.get(current_house_id, {})
                    
                    # Обновляем подпись
                    caption = f"🚪 *Ваш шкаф*\n\n"
                    caption += f"🏡 *{house_info.get('name', 'Неизвестный дом')}*\n"
                    caption += f"📊 Страница: {page}/{total_houses}\n"
                    caption += f"\n✅ *Теперь это текущий дом!*"
                    
                    bot.edit_message_caption(
                        caption=caption,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=create_wardrobe_keyboard(user_id, page),
                        parse_mode='Markdown'
                    )
                    
                except Exception as e:
                    logging.error(f"Ошибка обновления шкафа: {e}")
                    # Если не удалось обновить, просто показываем сообщение
                    pass
                
                bot.answer_callback_query(call.id, f"✅ Выбран дом '{house_info['name']}'!")
                
            else:
                bot.answer_callback_query(call.id, message, show_alert=True)
                
        elif call.data == "wardrobe_current":
            # Просто показ текущей страницы
            bot.answer_callback_query(call.id)
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике домов: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка")
        except:
            pass

# === ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ ДОМОВ ===
load_house_shop()

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
# === КОМАНДА ДЛЯ ПОЛУЧЕНИЯ ЛОГОВ ПОЛЬЗОВАТЕЛЯ ===

@bot.message_handler(func=lambda message: message.text.lower().startswith('лог ') and is_admin(message.from_user.id))
def handle_user_logs(message):
    """Отправляет файл логов с действиями конкретного пользователя"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: лог ID/@username\n"
                           "Примеры:\n"
                           "`лог 123456789`\n"
                           "`лог @username`\n"
                           "`лог all` - все логи", 
                           parse_mode='Markdown')
            return
        
        target = parts[1].strip()
        
        if target.lower() == 'all':
            # Отправляем все логи
            send_all_logs(message)
            return
        
        # Определяем ID пользователя
        user_id = None
        
        if target.startswith('@'):
            # Поиск по юзернейму
            username = target[1:].lower()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE LOWER(username) = ?', (username,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                user_id = result[0]
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь {target} не найден")
                return
        else:
            # Поиск по ID
            try:
                user_id = int(target)
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный ID. Используйте цифры или @username")
                return
        
        # Получаем информацию о пользователе
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, first_name, balance, bank_deposit, 
                   registered_at, last_activity, is_banned
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        conn.close()
        
        if not user_data:
            bot.send_message(message.chat.id, f"❌ Пользователь с ID {user_id} не найден")
            return
        
        username, first_name, balance, bank_deposit, registered_at, last_activity, is_banned = user_data
        
        # Создаем файл с логами
        log_filename = f"logs_user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        
        with open(log_filename, 'w', encoding='utf-8') as log_file:
            # Заголовок
            log_file.write(f"ЛОГИ ПОЛЬЗОВАТЕЛЯ\n")
            log_file.write(f"{'='*50}\n\n")
            
            # Информация о пользователе
            log_file.write(f"👤 ИНФОРМАЦИЯ:\n")
            log_file.write(f"ID: {user_id}\n")
            log_file.write(f"Username: @{username if username else 'нет'}\n")
            log_file.write(f"Имя: {first_name}\n")
            log_file.write(f"Баланс: {format_balance(balance)}❄️\n")
            log_file.write(f"В банке: {format_balance(bank_deposit)}❄️\n")
            log_file.write(f"Статус: {'🚫 ЗАБАНЕН' if is_banned else '✅ АКТИВЕН'}\n")
            log_file.write(f"Регистрация: {registered_at}\n")
            log_file.write(f"Последняя активность: {last_activity}\n\n")
            
            log_file.write(f"📊 АКТИВНОСТЬ:\n")
            log_file.write(f"{'='*50}\n")
            
            # Ищем логи в файле bot.log
            if os.path.exists('bot.log'):
                with open('bot.log', 'r', encoding='utf-8') as bot_log:
                    lines = bot_log.readlines()
                    user_logs = []
                    
                    for line in lines:
                        if str(user_id) in line:
                            user_logs.append(line)
                    
                    if user_logs:
                        # Последние 1000 строк (чтобы не перегружать)
                        for log_line in user_logs[-1000:]:
                            log_file.write(log_line)
                    else:
                        log_file.write("Логи не найдены\n")
            else:
                log_file.write("Файл логов не найден\n")
            
            # Добавляем статистику из БД
            log_file.write(f"\n{'='*50}\n")
            log_file.write(f"📈 СТАТИСТИКА ИЗ БАЗЫ:\n")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Рефералы
            cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
            ref_count = cursor.fetchone()[0]
            log_file.write(f"Рефералов: {ref_count}\n")
            
            # Чеки созданные
            cursor.execute('SELECT COUNT(*) FROM checks WHERE created_by = ?', (user_id,))
            checks_created = cursor.fetchone()[0]
            log_file.write(f"Чеков создано: {checks_created}\n")
            
            # Чеки активированные
            cursor.execute('SELECT COUNT(*) FROM check_activations WHERE user_id = ?', (user_id,))
            checks_activated = cursor.fetchone()[0]
            log_file.write(f"Чеков активировано: {checks_activated}\n")
            
            conn.close()
            
            # Снежная работа
            if user_id in SNOW_JOBS:
                job = SNOW_JOBS[user_id]
                log_file.write(f"\n❄️ СНЕЖНАЯ РАБОТА:\n")
                log_file.write(f"Прогресс: {job['clicks_done']}/150\n")
                log_file.write(f"Заработок: {format_balance(job['current_earnings'])}❄️\n")
                log_file.write(f"Ошибок: {job['wrong_clicks']}\n")
                log_file.write(f"Уборок: {job['completed']}\n")
            
            # Кулдауны
            if user_id in SNOW_COOLDOWN:
                log_file.write(f"Снег кулдаун: до {datetime.fromtimestamp(SNOW_COOLDOWN[user_id])}\n")
            
            log_file.write(f"\n{'='*50}\n")
            log_file.write(f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(f"Бот: @{(bot.get_me()).username}\n")
        
        # Отправляем файл
        with open(log_filename, 'rb') as file_to_send:
            caption = (
                f"📋 Логи пользователя\n"
                f"👤 ID: {user_id}\n"
                f"📛 Имя: {first_name}\n"
                f"📊 Баланс: {format_balance(balance)}❄️\n"
                f"📅 Регистрация: {registered_at}\n"
                f"⏰ Последняя активность: {last_activity}"
            )
            
            bot.send_document(
                message.chat.id,
                file_to_send,
                caption=caption,
                timeout=60
            )
        
        # Удаляем временный файл
        os.remove(log_filename)
        
    except Exception as e:
        logging.error(f"Ошибка в команде лог: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:200]}")

def send_all_logs(message):
    """Отправляет все логи бота"""
    try:
        if not os.path.exists('bot.log'):
            bot.send_message(message.chat.id, "❌ Файл логов не найден")
            return
        
        bot.send_message(message.chat.id, "⏳ Подготавливаю все логи...")
        
        # Создаем архив с логами
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        log_filename = f"all_logs_{timestamp}.txt"
        zip_filename = f"logs_{timestamp}.zip"
        
        # Копируем логи
        shutil.copy2('bot.log', log_filename)
        
        # Создаем ZIP архив
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(log_filename, os.path.basename(log_filename))
        
        # Отправляем архив
        with open(zip_filename, 'rb') as zip_file:
            bot.send_document(
                message.chat.id,
                zip_file,
                caption=f"📦 Все логи бота\n📅 {timestamp}",
                timeout=60
            )
        
        # Удаляем временные файлы
        os.remove(log_filename)
        os.remove(zip_filename)
        
    except Exception as e:
        logging.error(f"Ошибка отправки всех логов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

# === УЛУЧШЕННОЕ ЛОГИРОВАНИЕ ===
# Добавьте эту функцию для логирования действий пользователей

def log_user_action(user_id, action, details=""):
    """Логирует действие пользователя"""
    try:
        # Получаем информацию о пользователе
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        username = user_data[0] if user_data else "Unknown"
        first_name = user_data[1] if user_data else "Unknown"
        
        log_message = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"USER:{user_id} "
            f"NAME:{first_name} "
            f"USERNAME:@{username if username else 'none'} "
            f"ACTION:{action} "
            f"DETAILS:{details}"
        )
        
        logging.info(log_message)
        
        # Дополнительно сохраняем в отдельный файл для пользователей
        user_log_file = f"user_logs_{user_id % 100}.log"  # Разделяем по хешу
        with open(user_log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
            
    except Exception as e:
        logging.error(f"Ошибка логирования: {e}")



# === КОМАНДА ДЛЯ ОЧИСТКИ ЛОГОВ ===

@bot.message_handler(func=lambda message: message.text.lower() == 'очиститьлоги' and is_admin(message.from_user.id))
def handle_clear_logs(message):
    """Очищает старые логи"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ ДА, ОЧИСТИТЬ", callback_data="clear_logs_confirm"),
            InlineKeyboardButton("❌ ОТМЕНА", callback_data="clear_logs_cancel")
        )
        
        # Показываем размер файла
        if os.path.exists('bot.log'):
            size_mb = os.path.getsize('bot.log') / (1024 * 1024)
            size_info = f"📁 Текущий размер: {size_mb:.2f} MB\n"
        else:
            size_info = ""
        
        bot.send_message(
            message.chat.id,
            f"⚠️ ОЧИСТКА ЛОГОВ\n\n"
            f"{size_info}"
            f"Эта операция:\n"
            f"• Удалит логи старше 7 дней\n"
            f"• Оставит последние 1000 строк\n"
            f"• Создаст бэкап\n\n"
            f"Подтвердите очистку:",
            reply_markup=markup
        )
        
    except Exception as e:
        logging.error(f"Ошибка в очистке логов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('clear_logs_'))
def clear_logs_callback(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет прав!")
            return
            
        if call.data == "clear_logs_confirm":
            bot.answer_callback_query(call.id, "⏳ Очищаю...")
            
            if clear_old_logs():
                bot.edit_message_text(
                    "✅ Логи очищены!\n"
                    "Старые записи удалены,\n"
                    "оставлены последние 1000 строк.",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.edit_message_text(
                    "❌ Ошибка очистки логов",
                    call.message.chat.id,
                    call.message.message_id
                )
                
        elif call.data == "clear_logs_cancel":
            bot.answer_callback_query(call.id, "❌ Отменено")
            bot.edit_message_text(
                "❌ Очистка логов отменена",
                call.message.chat.id,
                call.message.message_id
            )
            
    except Exception as e:
        logging.error(f"Ошибка в callback очистки логов: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

def clear_old_logs():
    """Очищает старые логи"""
    try:
        if not os.path.exists('bot.log'):
            return False
        
        # Создаем бэкап
        backup_name = f"bot_log_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.log"
        shutil.copy2('bot.log', backup_name)
        
        # Читаем все строки
        with open('bot.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if len(lines) <= 1000:
            # Если мало строк, просто обрезаем
            lines_to_keep = lines
        else:
            # Оставляем последние 1000 строк
            lines_to_keep = lines[-1000:]
        
        # Записываем обратно
        with open('bot.log', 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
        
        # Удаляем старые бэкапы (старше 7 дней)
        for filename in os.listdir('.'):
            if filename.startswith('bot_log_backup_') and filename.endswith('.log'):
                file_time_str = filename[15:-4]  # Извлекаем дату из имени
                try:
                    file_time = datetime.strptime(file_time_str, '%Y%m%d_%H%M')
                    if (datetime.now() - file_time).days > 7:
                        os.remove(filename)
                except:
                    pass
        
        logging.info("Логи очищены")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка очистки логов: {e}")
        return False
# Обработчик кнопки "🖱️ Кликер"
@bot.message_handler(func=lambda message: message.text == "🖱️ Клиер")
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
    clicker_button = KeyboardButton("....")
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
                minutes = time_left // 160
                seconds = time_left % 160
                
                cool_msg = f"⏳ Отдых: {minutes}м {seconds}с"
                bot.send_message(message.chat.id, cool_msg)
                return
        
        # Проверяем активную работу
        if user_id in SNOW_JOBS:
            job = SNOW_JOBS[user_id]
            
            # Проверяем не устарело ли последнее сообщение (больше 30 секунд)
            if user_id in SNOW_LAST_MESSAGE:
                last_msg = SNOW_LAST_MESSAGE[user_id]
                if current_time - last_msg["timestamp"] > 60:
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
        bonus_per_job = 25
        earnings = base_earnings + (completed_jobs * bonus_per_job)
        
        # Создаем задание
        SNOW_JOBS[user_id] = {
            "clicks_left": 100,
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
            f"🎯 100 кликов\n"
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
    progress_percent = (clicks_done / 100) * 100
    
    # Простой прогресс-бар
    filled = int(progress_percent / 6.67)  # 6.67% за каждый символ
    progress_bar = "🟦" * filled + "⬜" * (15 - filled)
    
    message = (
        f"❄️ {clicks_done}/100\n"
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
            penalty = 50
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
                    f"🎯 Кликов: 100\n"
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
                    f"🎯 Кликов: 100\n"
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
def get_user_display_name(user_id, username, first_name, nickname=None):
    """Получает отображаемое имя пользователя для топов"""
    try:
        # Если есть кастомный ник, используем его
        if nickname and nickname.strip():
            return nickname.strip()
        
        # Иначе используем юзернейм или имя
        if username:
            return f"@{username}"
        else:
            return first_name if first_name else f"ID: {user_id}"
    except:
        return f"ID: {user_id}"
# Обработчик команды "ник" для смены никнейма
@bot.message_handler(func=lambda message: message.text.lower().startswith('ник '))
def handle_change_nickname(message):
    """Смена никнейма"""
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        # Получаем новый ник из сообщения
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: ник [ваш новый ник]\n"
                           "Пример: ник ⛄СнежныйВолк❄️\n"
                           "💡 Ник может содержать эмодзи и символы")
            return
        
        new_nickname = parts[1].strip()
        
        # Проверяем длину ника
        if len(new_nickname) > 32:
            bot.send_message(message.chat.id, "❌ Слишком длинный ник! Макс. 32 символа")
            return
        
        if len(new_nickname) < 2:
            bot.send_message(message.chat.id, "❌ Слишком короткий ник! Мин. 2 символа")
            return
        
        # Проверяем запрещенные символы
        forbidden_chars = ['<', '>', '&', '"', "'", '`', '\\', '/', ';']
        for char in forbidden_chars:
            if char in new_nickname:
                bot.send_message(message.chat.id, f"❌ Ник содержит запрещенный символ: {char}")
                return
        
        # Обновляем ник в базе данных
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Создаем колонку для никнейма если её нет
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'nickname' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
            conn.commit()
        
        # Обновляем ник
        cursor.execute('UPDATE users SET nickname = ? WHERE user_id = ?', 
                      (new_nickname, user_id))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, 
                       f"✅ Ваш ник изменен на: {new_nickname}\n\n"
                       f"💡 Теперь вас будут видеть с этим ником в топах!")
        
    except Exception as e:
        logging.error(f"Ошибка смены ника: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при смене ника. Попробуйте позже.")
# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ ТОПОВ ===
user_top_page = {}
user_top_mode = {}  # 'balance' или 'scam'

def get_balance_top_page(page=1, limit=5):
    """Получает топ пользователей по балансу"""
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Используем username для отображения, nickname будет получен отдельно
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


# === ИСПРАВЛЕННАЯ ФУНКЦИЯ get_scam_top_page ===
def get_scam_top_page(page=1, limit=5):
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем наличие колонки nickname
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    has_nickname = 'nickname' in columns
    
    if has_nickname:
        cursor.execute('''
        SELECT 
            u.user_id,
            u.nickname,
            u.username,
            u.first_name,
            COUNT(r.user_id) as ref_count,
            ROW_NUMBER() OVER (ORDER BY COUNT(r.user_id) DESC) as position
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
        WHERE u.is_banned = 0
        GROUP BY u.user_id
        HAVING COUNT(r.user_id) > 0
        ORDER BY ref_count DESC
        LIMIT ? OFFSET ?
        ''', (limit, offset))
    else:
        cursor.execute('''
        SELECT 
            u.user_id,
            NULL as nickname,
            u.username,
            u.first_name,
            COUNT(r.user_id) as ref_count,
            ROW_NUMBER() OVER (ORDER BY COUNT(r.user_id) DESC) as position
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
        WHERE u.is_banned = 0
        GROUP BY u.user_id
        HAVING COUNT(r.user_id) > 0
        ORDER BY ref_count DESC
        LIMIT ? OFFSET ?
        ''', (limit, offset))
    
    top_scammers = cursor.fetchall()
    
    cursor.execute('''
    SELECT COUNT(DISTINCT u.user_id) 
    FROM users u
    JOIN users r ON u.user_id = r.referred_by AND r.is_banned = 0
    ''')
    total_scammers = cursor.fetchone()[0] or 1
    
    total_pages = (total_scammers + limit - 1) // limit
    
    conn.close()
    
    return {
        'users': top_scammers,
        'total': total_scammers,
        'current_page': page,
        'total_pages': total_pages,
        'has_nickname': has_nickname
    }
# === КОМАНДА ДЛЯ ИЗМЕНЕНИЯ ЦЕНЫ ДОМА ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('ценадома ') and is_admin(message.from_user.id))
def handle_change_house_price(message):
    """Изменение цены дома в магазине"""
    try:
        if not is_admin(message.from_user.id):
            return
            
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, 
                           "❌ Формат: ценадома [ID_дома] [новая_цена]\n"
                           "Пример: ценадома house_12345 2000000\n\n"
                           "📝 Чтобы узнать ID дома, используйте команду: `магазин`")
            return
        
        house_id = parts[1].strip()
        try:
            new_price = int(parts[2])
            if new_price < 0:
                bot.send_message(message.chat.id, "❌ Цена не может быть отрицательной")
                return
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверная цена. Введите число")
            return
        
        if house_id not in HOUSE_SHOP:
            bot.send_message(message.chat.id, f"❌ Дом с ID '{house_id}' не найден")
            return
        
        # Сохраняем старую цену
        old_price = HOUSE_SHOP[house_id]['price']
        house_name = HOUSE_SHOP[house_id]['name']
        
        # Меняем цену
        HOUSE_SHOP[house_id]['price'] = new_price
        HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
        HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
        
        # Сохраняем изменения
        save_house_shop()
        
        bot.send_message(message.chat.id,
                       f"✅ Цена дома изменена!\n\n"
                       f"🏡 Дом: {house_name}\n"
                       f"🆔 ID: `{house_id}`\n"
                       f"💰 Старая цена: {format_balance(old_price)}❄️\n"
                       f"💰 Новая цена: {format_balance(new_price)}❄️\n\n"
                       f"💡 Изменения вступят в силу сразу")
        
    except Exception as e:
        logging.error(f"Ошибка изменения цены дома: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")



# === КОМАНДА ДЛЯ МАССОВОГО ИЗМЕНЕНИЯ ЦЕН ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('массцена ') and is_admin(message.from_user.id))
def handle_mass_price_change(message):
    """Массовое изменение цен всех домов"""
    try:
        if not is_admin(message.from_user.id):
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: массцена [процент] или массцена [фиксированная_сумма]\n"
                           "Примеры:\n"
                           "массцена +20% - увеличить все цены на 20%\n"
                           "массцена -10% - уменьшить все цены на 10%\n"
                           "массцена 1000000 - установить всем минимальную цену 1M")
            return
        
        change = parts[1].strip()
        
        if not HOUSE_SHOP:
            bot.send_message(message.chat.id, "❌ В магазине нет домов")
            return
        
        changed_count = 0
        report = "📊 *Массовое изменение цен*\n\n"
        
        if change.endswith('%'):
            # Процентное изменение
            try:
                percent = float(change[:-1])
                if percent == 0:
                    bot.send_message(message.chat.id, "❌ Процент не может быть 0%")
                    return
                
                report += f"📈 Изменение на {percent}%\n\n"
                
                for house_id, house_info in HOUSE_SHOP.items():
                    old_price = house_info['price']
                    multiplier = 1 + (percent / 100)
                    new_price = int(old_price * multiplier)
                    
                    # Округляем до кратного 1000
                    new_price = (new_price // 1000) * 1000
                    if new_price < 1000:
                        new_price = 1000
                    
                    HOUSE_SHOP[house_id]['price'] = new_price
                    HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
                    HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
                    
                    report += f"🏡 {house_info['name']}:\n"
                    report += f"   {format_balance(old_price)}❄️ → {format_balance(new_price)}❄️\n"
                    changed_count += 1
                
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный процент")
                return
                
        else:
            # Установка минимальной цены
            try:
                min_price = parse_bet_amount(change, float('inf'))
                if min_price is None or min_price < 0:
                    bot.send_message(message.chat.id, "❌ Неверная сумма")
                    return
                
                report += f"💰 Установка минимальной цены: {format_balance(min_price)}❄️\n\n"
                
                for house_id, house_info in HOUSE_SHOP.items():
                    old_price = house_info['price']
                    new_price = max(old_price, min_price)
                    
                    if new_price != old_price:
                        HOUSE_SHOP[house_id]['price'] = new_price
                        HOUSE_SHOP[house_id]['price_changed_at'] = time.time()
                        HOUSE_SHOP[house_id]['price_changed_by'] = message.from_user.id
                        
                        report += f"🏡 {house_info['name']}:\n"
                        report += f"   {format_balance(old_price)}❄️ → {format_balance(new_price)}❄️\n"
                        changed_count += 1
                
            except:
                bot.send_message(message.chat.id, "❌ Неверная сумма")
                return
        
        if changed_count > 0:
            # Сохраняем изменения
            save_house_shop()
            
            report += f"\n✅ Изменено: {changed_count}/{len(HOUSE_SHOP)} домов"
            bot.send_message(message.chat.id, report, parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, "ℹ️ Ни одна цена не была изменена")
        
    except Exception as e:
        logging.error(f"Ошибка массового изменения цен: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")


@bot.message_handler(func=lambda message: message.text.lower() == 'эко')
def handle_eco_oneline(message):
    """Одна строка: баланс + процент"""
    try:
        user_id = message.from_user.id
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Данные пользователя
        cursor.execute('SELECT balance, bank_deposit FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return
        
        user_total = user_data[0] + user_data[1]
        
        # Общая экономика
        cursor.execute('SELECT SUM(balance + bank_deposit) FROM users')
        total = cursor.fetchone()[0] or 1
        
        conn.close()
        
        percentage = (user_total / total) * 100
        
        # Одна строка
        bot.send_message(message.chat.id, 
                        f"💵 {format_balance(user_total)}❄️ |  {percentage:.4f}%")
        
    except:
        pass
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
# =============== СИСТЕМА БЛАТНЫХ ID ===============

def get_user_id_number(user_id):
    """Получает номер пользователя по порядку регистрации"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем всех пользователей отсортированных по дате регистрации
        cursor.execute('''
        SELECT user_id FROM users 
        WHERE is_banned = 0 
        ORDER BY registered_at ASC
        ''')
        
        all_users = cursor.fetchall()
        conn.close()
        
        # Ищем позицию пользователя
        for i, (db_user_id,) in enumerate(all_users, 1):
            if db_user_id == user_id:
                return i
        
        return 0  # Не найден
    except:
        return 0

def get_prestige_id(user_id):
    """Получает престижный ID пользователя"""
    try:
        id_number = get_user_id_number(user_id)
        
        if id_number == 0:
            return "ID: ?"
        
        # Особые престижные ID
        if id_number <= 10:
            return f"👑 ID: #{id_number}"
        elif id_number <= 50:
            return f"⭐ ID: #{id_number}"
        elif id_number <= 100:
            return f"✨ ID: #{id_number}"
        elif id_number <= 500:
            return f"🔹 ID: #{id_number}"
        else:
            return f"ID: #{id_number}"
    except:
        return "ID: ?"

def get_prestige_badge(user_id):
    """Получает бейдж престижа"""
    try:
        id_number = get_user_id_number(user_id)
        
        if id_number == 0:
            return ""
        
        if id_number == 1:
            return "👑 Первый пользователь"
        elif id_number <= 3:
            return "👑 Основатель"
        elif id_number <= 10:
            return "⭐ Первые 10"
        elif id_number <= 50:
            return "✨ Первые 50"
        elif id_number <= 100:
            return "🔹 Первые 100"
        elif id_number <= 500:
            return "🟢 Первые 500"
        else:
            return ""
    except:
        return ""

# =============== ОБНОВЛЕННАЯ КОМАНДА "Я" ===============



# =============== КОМАНДА ДЛЯ ПРОВЕРКИ ID ===============

@bot.message_handler(func=lambda message: message.text.lower() == 'мойид')
def handle_my_id(message):
    """Показывает детальную информацию о ID"""
    try:
        user_id = message.from_user.id
        
        prestige_id = get_prestige_id(user_id)
        prestige_badge = get_prestige_badge(user_id)
        id_number = get_user_id_number(user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT registered_at FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        reg_date = "Неизвестно"
        if result and result[0]:
            try:
                reg_date = result[0]
                if isinstance(reg_date, str):
                    reg_date = reg_date[:19]  # Берем дату и время
            except:
                reg_date = str(result[0])[:19]
        
        message_text = f"🆔 *ИНФОРМАЦИЯ О ID*\n\n"
        message_text += f"{prestige_id}\n"
        
        if prestige_badge:
            message_text += f"{prestige_badge}\n\n"
        else:
            message_text += f"\n"
        
        message_text += f"📊 *Номер регистрации:* {id_number}\n"
        message_text += f"📅 *Дата регистрации:* {reg_date}\n\n"
        
        # Показываем уровни престижа
        message_text += "*🎯 Уровни престижа:*\n"
        message_text += "👑 #1-3 - Основатель\n"
        message_text += "👑 #1-10 - Первые 10\n"
        message_text += "⭐ #11-50 - Первые 50\n"
        message_text += "✨ #51-100 - Первые 100\n"
        message_text += "🔹 #101-500 - Первые 500\n"
        message_text += "#501+ - Обычный ID\n\n"
        message_text += "*💡 ID навсегда - чем меньше номер, тем больше уважения!*"
        
        bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

# =============== ОБНОВЛЕННЫЙ ТОП С ИД ===============

def create_top_message(user_id, page=1):
    """Создает сообщение с топом с учетом ID"""
    try:
        mode = user_top_mode.get(user_id, 'balance')
        
        if mode == 'balance':
            top_data = get_balance_top_page(page, 5)
            title = "🎅 Топ снежков 🎅"
        else:
            top_data = get_scam_top_page(page, 5)
            title = "👥 Топ скама 👥"
        
        top_users = top_data['users']
        
        message_text = f"<b>{title}</b>\n\n"
        
        if top_users:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            
            for i, user in enumerate(top_users):
                if mode == 'balance':
                    user_id_db, display_name, value, position = user
                    value_text = f"⟨{format_balance(value)}❄️⟩"
                else:
                    user_id_db, nickname, username_db, first_name, value, position = user
                    value_text = f"⟨{value} скам⟩"
                    username = username_db
                
                # Получаем престижный ID
                user_prestige_id = get_user_id_number(user_id_db)
                
                # Формируем отображаемое имя с ID
                if user_prestige_id > 0:
                    if user_prestige_id <= 10:
                        id_display = f"👑#{user_prestige_id}"
                    elif user_prestige_id <= 50:
                        id_display = f"⭐#{user_prestige_id}"
                    elif user_prestige_id <= 100:
                        id_display = f"✨#{user_prestige_id}"
                    elif user_prestige_id <= 500:
                        id_display = f"🔹#{user_prestige_id}"
                    else:
                        id_display = f"#{user_prestige_id}"
                else:
                    id_display = "?#"
                
                # Получаем никнейм или имя
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT nickname, username FROM users WHERE user_id = ?', (user_id_db,))
                user_data = cursor.fetchone()
                conn.close()
                
                display_html = ""
                if user_data:
                    nickname_db, username = user_data
                    if nickname_db and nickname_db.strip():
                        if username:
                            display_html = f'<a href="https://t.me/{username}">{nickname_db.strip()}</a>'
                        else:
                            display_html = nickname_db.strip()
                    elif username:
                        display_html = f'<a href="https://t.me/{username}">@{username}</a>'
                    else:
                        display_html = first_name if 'first_name' in locals() else f"ID: {user_id_db}"
                else:
                    display_html = display_name if mode == 'balance' else first_name
                
                # Обрезаем если слишком длинное
                if len(display_html) > 20:
                    import re
                    text_only = re.sub(r'<[^>]+>', '', display_html)
                    if len(text_only) > 18:
                        display_html = display_html[:15] + "..."
                
                page_position = ((page - 1) * 5) + i + 1
                if page_position <= 3:
                    medal = medals[page_position-1]
                elif page_position <= 5:
                    medal = medals[page_position-1]
                else:
                    medal = f"{page_position}."
                
                message_text += f"{medal} {id_display} {display_html} {value_text}\n"
        
        # Добавляем ID текущего пользователя
        user_prestige_id = get_user_id_number(user_id)
        if user_prestige_id > 0:
            message_text += f"\n🎯 <b>Твой ID:</b> #{user_prestige_id}"
        
        return message_text
        
    except Exception as e:
        return "❌ Ошибка загрузки топа"
# === ИСПРАВЛЕННАЯ ФУНКЦИЯ get_user_position_in_top ===
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
# === КОМАНДА ДЛЯ ОБНОВЛЕНИЯ USERNAME В БАЗЕ ===
@bot.message_handler(func=lambda message: message.text.lower() == 'обновить' and is_admin(message.from_user.id))
def handle_update_usernames(message):
    """Обновляет username для всех пользователей в базе данных"""
    try:
        if not is_admin(message.from_user.id):
            return
        
        bot.send_message(message.chat.id, "⏳ Начинаю обновление username для всех пользователей...")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем всех пользователей
        cursor.execute('SELECT user_id, username FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        
        updated_count = 0
        failed_count = 0
        
        for user in users:
            user_id, current_username = user
            
            try:
                # Получаем актуальные данные из Telegram
                chat_user = bot.get_chat(user_id)
                new_username = chat_user.username
                
                # Если username изменился
                if new_username != current_username:
                    cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', 
                                  (new_username, user_id))
                    updated_count += 1
                    
            except Exception as e:
                failed_count += 1
                logging.warning(f"Не удалось обновить пользователя {user_id}: {e}")
            
            # Небольшая задержка чтобы не получить ограничение от Telegram
            time.sleep(0.1)
        
        conn.commit()
        conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ Обновление завершено!\n\n"
            f"📊 Статистика:\n"
            f"• Всего проверено: {len(users)}\n"
            f"• Обновлено: {updated_count}\n"
            f"• Ошибок: {failed_count}\n\n"
            f"💡 Теперь в топах и переводах будут использоваться актуальные username!"
        )
        
    except Exception as e:
        logging.error(f"Ошибка обновления username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")
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

# Списки рандомных фраз для кубика
WIN_PHRASES = [
    "🎉 Урааа!",
    "🎯 Попал в точку!",
    "🔥 В яблочко!",
    "✨ Невероятно!",
    "💰 мегагей",
    "💎 Радуйся суко!",
    "🌟 Фантастик момбастик!",
    "⚡ Иба четка",
    "🏆 Чемпион!",
    "💫 Залет!",
    "🎊 Праздник!",
    "🤑 Дальше больше!"
]

LOSE_PHRASES = [
    "❌ Не повезло...",
    "💸 Упс...",
    "😔 извинись потом",
    "📉 Не в этот раз",
    "🌀 Не судьба",
    "🌪️ Вращение не удалось",
    "💨 Унесло бабки",
    "⚰️ Похороны ставки",
    "📉 Дальше меньше",
    "🌧 Не твой день",
    "🎭 Луз",
    "🔚 Нечетенька"
]



# Списки рандомных фраз для баскетбола
BASKETBALL_WIN_PHRASES = [
    "🏀 Отличный бросок!",
    "🎯 Точное попадание!",
    "🔥 Забил!",
    "✨ Идеально!",
    "💰 Чистая игра!",
    "💎 Бросок мастера!",
    "🌟 Свисток! Это гол!",
    "⚡ Молниеносный бросок!",
    "🏆 Чемпионский бросок!",
    "💫 Волшебный мяч!",
    "🎊 Праздник в зале!",
    "🤑 Игрок месяца!"
]

BASKETBALL_LOSE_PHRASES = [
    "❌ Мяч не попал...",
    "💸 Почти забил",
    "😔 Мимо кольца",
    "📉 Не судьба",
    "🌀 Мяч улетел",
    "🌪️ Плохой бросок",
    "💨 Воздушный шар",
    "⚰️ Похороны мяча",
    "📉 Провальная атака",
    "🌧️ Дождь неудач",
    "🎭 Игра окончена",
    "🔚 Конец матча"
]

def update_game_with_bonus(user_id, win_amount, game_name):
    try:
        if win_amount > 0:
            update_balance(user_id, win_amount)
            add_referral_win_bonus(user_id, win_amount, game_name)
    except:
        pass

@bot.message_handler(func=lambda message: message.text.lower().startswith(('рул ', 'рулетка ')))
def handle_roulette(message):
    try:
        if is_spam(message.from_user.id):
            return
            
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_type = parts[1]
        bet_amount = parse_bet_amount(' '.join(parts[2:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        winning_number = random.randint(0, 36)
        win = False
        multiplier = 1
        
        red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
        
        try:
            number_bet = int(bet_type)
            if 0 <= number_bet <= 36:
                win = winning_number == number_bet
                multiplier = 36
            else:
                bot.send_message(message.chat.id, "❌ Число 0-36")
                update_balance(user_id, bet_amount)
                return
        except ValueError:
            if bet_type in ['красный', 'крас', 'кр', 'к']:
                win = winning_number in red_numbers
                multiplier = 2
            elif bet_type in ['черный', 'чер', 'чр', 'ч']:
                win = winning_number in black_numbers
                multiplier = 2
            elif bet_type in ['зеленый', 'зел', 'з', '0', 'зеро']:
                win = winning_number == 0
                multiplier = 36
            elif bet_type in ['большие', 'бол', 'б']:
                win = winning_number >= 19 and winning_number <= 36
                multiplier = 2
            elif bet_type in ['малые', 'мал', 'м']:
                win = winning_number >= 1 and winning_number <= 18
                multiplier = 2
            elif bet_type in ['чет', 'четные', 'четн']:
                win = winning_number % 2 == 0 and winning_number != 0
                multiplier = 2
            elif bet_type in ['нечет', 'нечетные', 'неч']:
                win = winning_number % 2 == 1 and winning_number != 0
                multiplier = 2
            else:
                bot.send_message(message.chat.id, "❌ Неверный тип")
                update_balance(user_id, bet_amount)
                return
        
        if win:
            win_amount = bet_amount * multiplier
            update_game_with_bonus(user_id, win_amount, "🎰 Рулетка")
            new_balance = get_balance(user_id)
            
            image_path = get_roulette_photo(winning_number)
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"<b>✅ Удача</b>\n\n<blockquote>Выиграли ❄️+{format_balance(win_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                            parse_mode='HTML'
                        )
                except:
                    bot.send_message(message.chat.id, 
                                   f"<b>✅ Удача</b>\n\n<blockquote>Выиграли ❄️+{format_balance(win_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                                   parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, 
                               f"<b>✅ Удача</b>\n\n<blockquote>Выиграли ❄️+{format_balance(win_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                               parse_mode='HTML')
        else:
            new_balance = get_balance(user_id)
            
            image_path = get_roulette_photo(winning_number)
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=f"<b>❌ Не повезло</b>\n\n<blockquote>Проиграли ❄️-{format_balance(bet_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                            parse_mode='HTML'
                        )
                except:
                    bot.send_message(message.chat.id, 
                                   f"<b>❌ Не повезло</b>\n\n<blockquote>Проиграли ❄️-{format_balance(bet_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                                   parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, 
                               f"<b>❌ Не повезло</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                               parse_mode='HTML')
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('куб ', 'кубик ')))
def handle_dice(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_type = parts[1]
        bet_amount = parse_bet_amount(' '.join(parts[2:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎲')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1
        
        if bet_type in ['бол', 'большие', 'б']:
            win = result in [4, 5, 6]
            multiplier = 2
        
        elif bet_type in ['мал', 'малые', 'м']:
            win = result in [1, 2, 3]
            multiplier = 2
        
        elif bet_type in ['чет', 'четные', 'четн']:
            win = result in [2, 4, 6]
            multiplier = 2
        
        elif bet_type in ['нечет', 'нечетные', 'неч']:
            win = result in [1, 3, 5]
            multiplier = 2
        
        else:
            try:
                target = int(bet_type)
                if 1 <= target <= 6:
                    win = result == target
                    multiplier = 6
                else:
                    bot.send_message(message.chat.id, "❌ Неверный тип")
                    update_balance(user_id, bet_amount)
                    return
            except:
                bot.send_message(message.chat.id, "❌ Неверный тип")
                update_balance(user_id, bet_amount)
                return
        
        if win:
            win_amount = bet_amount * multiplier
            update_game_with_bonus(user_id, win_amount, "🎲 Кубик")
            new_balance = get_balance(user_id)
            
            win_phrase = random.choice(WIN_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{win_phrase}</b>\n\n<blockquote>Выиграли ❄️{format_balance(win_amount)}!\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
        else:
            new_balance = get_balance(user_id)
            lose_phrase = random.choice(LOSE_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{lose_phrase}</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}.\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('бск ', 'баскетбол ')))
def handle_basketball(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🏀')
        time.sleep(2)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 2.5
        
        if result == 4 or result == 5:
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_game_with_bonus(user_id, win_amount, "🏀 Баскетбол")
            new_balance = get_balance(user_id)
            
            win_phrase = random.choice(BASKETBALL_WIN_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{win_phrase}</b>\n\n<blockquote>Выиграли ❄️{format_balance(win_amount)}!\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
        else:
            new_balance = get_balance(user_id)
            lose_phrase = random.choice(BASKETBALL_LOSE_PHRASES)
            bot.send_message(
                message.chat.id,
                f"<b>{lose_phrase}</b>\n\n<blockquote>Проиграли ❄️{format_balance(bet_amount)}.\nБаланс: ❄️{format_balance(new_balance)}</blockquote>",
                parse_mode='HTML'
            )
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('слот ', 'слоты ')))
def handle_slots(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎰')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1
        
        if result == 1:
            win = True
            multiplier = 64
        elif result == 22:
            win = True
            multiplier = 10
        elif result == 43:
            win = True
            multiplier = 5
        elif result == 64:
            win = True
            multiplier = 3
        
        if win:
            win_amount = bet_amount * multiplier
            update_game_with_bonus(user_id, win_amount, "🎰 Слоты")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 Выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('фтб ', 'футбол ')))
def handle_football(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='⚽')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        win = False
        multiplier = 1.5
        
        if result == 3 or result == 4 or result == 5:
            win = True
        
        if win:
            win_amount = int(bet_amount * multiplier)
            update_game_with_bonus(user_id, win_amount, "⚽ Футбол")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎉 ГОООЛ! Выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Мяч не забит! Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith('дартс '))
def handle_darts(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        max_loss = bet_amount * 2
        if max_loss > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно средств!\nНужно минимум: ❄️{format_balance(max_loss)}")
            return
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎯')
        time.sleep(4)
        
        result = dice_message.dice.value
        
        update_balance(user_id, -bet_amount)
        
        if result == 6:
            win_amount = bet_amount * 5
            update_game_with_bonus(user_id, win_amount, "🎯 Дартс")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, 
                           f"🎯 ПОПАДАНИЕ В ЯБЛОЧКО!\n✅ Выиграли ❄️{format_balance(win_amount)}!\n💰 Ставка: ❄️{format_balance(bet_amount)}\n📈 Коэффициент: ×5\n❄️ Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 1:
            update_balance(user_id, -bet_amount)
            total_loss = bet_amount * 2
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, 
                           f"🎯 ПОЛНЫЙ ПРОМАХ!\n❌ Списанно: ❄️{format_balance(total_loss)}\n💰 Ставка: ❄️{format_balance(bet_amount)}\n📉 Штраф: ×2\n❄️ Баланс: ❄️{format_balance(new_balance)}")
        
        else:
            new_balance = get_balance(user_id)
            ring = "внутреннее кольцо" if result == 5 else "внешнее кольцо"
            bot.send_message(message.chat.id, 
                           f"🎯 Попадание в {ring}\n❌ Проиграли ставку\n💸 Списанно: ❄️{format_balance(bet_amount)}\n❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower().startswith(('боул ', 'боулинг ')))
def handle_bowling(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.lower().split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат.")
            return
        
        bet_amount = parse_bet_amount(' '.join(parts[1:]), balance)
        
        if bet_amount is None or bet_amount <= 0 or bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Ошибка суммы")
            return
        
        update_balance(user_id, -bet_amount)
        
        dice_message = bot.send_dice(message.chat.id, emoji='🎳')
        time.sleep(3)
        
        result = dice_message.dice.value
        
        if result == 6:
            win_amount = bet_amount * 2
            update_game_with_bonus(user_id, win_amount, "🎳 Боулинг")
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"🎳 СТРАЙК! Все кегли сбиты! Выиграли ❄️{format_balance(win_amount)}! Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 5:
            update_balance(user_id, bet_amount)
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"⚖️ Осталась 1 кегля! Возврат ставки ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
        
        elif result == 1:
            new_balance = get_balance(user_id)
            bot.send_message(message.chat.id, f"❌ Сбито 1-2 кегли! Осталось 8-9. Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
        
        else:
            new_balance = get_balance(user_id)
            if result == 2:
                remaining = "6-7 кеглей"
            elif result == 3:
                remaining = "4-5 кеглей"
            elif result == 4:
                remaining = "2-3 кегли"
            else:
                remaining = "кеглей"
            
            bot.send_message(message.chat.id, f"❌ Осталось {remaining}! Проиграли ❄️{format_balance(bet_amount)}. Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка")

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

# Обработчик команды "чеф" для админов с новым дизайном
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
            bot.send_message(message.chat.id, "❌ Неверный формат. Пример: чеф 1000к 10")
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
        
        # Генерируем случайный код чека
        import random
        import string
        check_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        conn = get_db_connection()
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
        
        # Новый формат текста
        check_text = f"""
<code>🧾 Мультичек</code>
<b>❄️ +{format_balance(amount)}</b>
<b>🔢 Кол-во:</b> <b>{max_activations}</b>
        """.strip()
        
        bot.send_message(
            message.chat.id, 
            check_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
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

# === КОМАНДА БАН ПО ЮЗЕРНЕЙМУ ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('бан ') and is_admin(message.from_user.id))
def handle_ban_username(message):
    """Бан пользователя по юзернейму или ID"""
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: бан @username [причина]\n"
                           "       или: бан ID [причина]\n\n"
                           "Примеры:\n"
                           "• бан @ivan Нарушение правил\n"
                           "• бан 123456789 Спам\n"
                           "• бан @user (ответом на сообщение)")
            return
        
        target = parts[1].strip()
        ban_reason = "Нарушение правил"
        if len(parts) > 2:
            ban_reason = ' '.join(parts[2:])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Если это ответ на сообщение
        if message.reply_to_message:
            target_user_id = message.reply_to_message.from_user.id
            target_username = message.reply_to_message.from_user.username
            target_first_name = message.reply_to_message.from_user.first_name
            
            cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (target_user_id,))
            user_data = cursor.fetchone()
            
            if user_data:
                target_username, target_first_name = user_data
            
            target_name = f"@{target_username}" if target_username else target_first_name
            
            # Баним пользователя
            cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                          (ban_reason, target_user_id))
            conn.commit()
            
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
        
        # Если указан юзернейм (@username)
        elif target.startswith('@'):
            username = target[1:]  # Убираем @
            
            # Ищем пользователя в базе
            cursor.execute('SELECT user_id, first_name FROM users WHERE username = ?', (username,))
            user_data = cursor.fetchone()
            
            if user_data:
                target_user_id, target_first_name = user_data
                
                # Баним пользователя
                cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                              (ban_reason, target_user_id))
                conn.commit()
                
                bot.send_message(message.chat.id, 
                               f"✅ Пользователь @{username} забанен!\n"
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
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь @{username} не найден в базе данных")
        
        # Если указан ID
        else:
            try:
                target_user_id = int(target)
                
                # Ищем пользователя в базе
                cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (target_user_id,))
                user_data = cursor.fetchone()
                
                if user_data:
                    target_username, target_first_name = user_data
                    target_name = f"@{target_username}" if target_username else target_first_name
                    
                    # Баним пользователя
                    cursor.execute('UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                                  (ban_reason, target_user_id))
                    conn.commit()
                    
                    bot.send_message(message.chat.id, 
                                   f"✅ Пользователь {target_name} (ID: {target_user_id}) забанен!\n"
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
                else:
                    bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден в базе данных")
                    
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте @username или ID")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_ban_username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при бане пользователя: {str(e)[:100]}")

# === КОМАНДА РАЗБАН ПО ЮЗЕРНЕЙМУ ===
@bot.message_handler(func=lambda message: message.text.lower().startswith('разбан ') and is_admin(message.from_user.id))
def handle_unban_username(message):
    """Разбан пользователя по юзернейму или ID"""
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, 
                           "❌ Формат: разбан @username\n"
                           "       или: разбан ID\n\n"
                           "Примеры:\n"
                           "• разбан @ivan\n"
                           "• разбан 123456789\n"
                           "• разбан @user (ответом на сообщение)")
            return
        
        target = parts[1].strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Если это ответ на сообщение
        if message.reply_to_message:
            target_user_id = message.reply_to_message.from_user.id
            
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
            
            # Разбаниваем
            cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                          (target_user_id,))
            conn.commit()
            
            target_name = f"@{username}" if username else first_name
            bot.send_message(message.chat.id, f"✅ Пользователь {target_name} разбанен!")
            
            # Уведомляем пользователя
            try:
                bot.send_message(target_user_id, 
                               f"🎉 Вы разбанены в боте!\n"
                               f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
            except:
                pass
        
        # Если указан юзернейм (@username)
        elif target.startswith('@'):
            username = target[1:]  # Убираем @
            
            cursor.execute('SELECT user_id, first_name, is_banned FROM users WHERE username = ?', (username,))
            user_data = cursor.fetchone()
            
            if user_data:
                target_user_id, first_name, is_banned = user_data
                
                if is_banned == 0:
                    bot.send_message(message.chat.id, f"⚠️ Пользователь @{username} не забанен")
                    conn.close()
                    return
                
                # Разбаниваем
                cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                              (target_user_id,))
                conn.commit()
                
                bot.send_message(message.chat.id, f"✅ Пользователь @{username} разбанен!")
                
                # Уведомляем пользователя
                try:
                    bot.send_message(target_user_id, 
                                   f"🎉 Вы разбанены в боте!\n"
                                   f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
                except:
                    pass
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь @{username} не найден в базе данных")
        
        # Если указан ID
        else:
            try:
                target_user_id = int(target)
                
                cursor.execute('SELECT username, first_name, is_banned FROM users WHERE user_id = ?', (target_user_id,))
                user_data = cursor.fetchone()
                
                if user_data:
                    username, first_name, is_banned = user_data
                    
                    if is_banned == 0:
                        bot.send_message(message.chat.id, f"⚠️ Пользователь с ID {target_user_id} не забанен")
                        conn.close()
                        return
                    
                    # Разбаниваем
                    cursor.execute('UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
                                  (target_user_id,))
                    conn.commit()
                    
                    target_name = f"@{username}" if username else first_name
                    bot.send_message(message.chat.id, f"✅ Пользователь {target_name} (ID: {target_user_id}) разбанен!")
                    
                    # Уведомляем пользователя
                    try:
                        bot.send_message(target_user_id, 
                                       f"🎉 Вы разбанены в боте!\n"
                                       f"👮 Администратор: @{message.from_user.username if message.from_user.username else 'Неизвестно'}")
                    except:
                        pass
                else:
                    bot.send_message(message.chat.id, f"❌ Пользователь с ID {target_user_id} не найден в базе данных")
                    
            except ValueError:
                bot.send_message(message.chat.id, "❌ Неверный формат. Используйте @username или ID")
        
        conn.close()
    
    except Exception as e:
        print(f"Ошибка в handle_unban_username: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при разбане пользователя: {str(e)[:100]}")

# Обработчик команды "передать"/"кинуть"/"дать"
@bot.message_handler(func=lambda message: message.text.lower().startswith(('передать ', 'кинуть ', 'дать ')))
def handle_transfer(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        balance = get_balance(user_id)
        
        parts = message.text.split()
        
        # Вариант 1: Ответ на сообщение (самый простой формат)
        if message.reply_to_message:
            if len(parts) < 2:
                bot.send_message(message.chat.id, 
                               "❌ Формат ответа: `передать сумма`\n"
                               "Пример: `передать 1000к`",
                               parse_mode='Markdown')
                return
            
            target_user_id = message.reply_to_message.from_user.id
            target_username = message.reply_to_message.from_user.username
            target_first_name = message.reply_to_message.from_user.first_name
            
            # Сумма - это второй аргумент
            amount_text = ' '.join(parts[1:])
            transfer_amount = parse_bet_amount(amount_text, balance)
            
            target_identifier = f"@{target_username}" if target_username else target_first_name
            
        # Вариант 2: Передача с указанием получателя и суммы
        elif len(parts) >= 3:
            target_identifier = parts[1].strip()
            amount_text = ' '.join(parts[2:])
            
            # Определяем ID получателя
            target_user_id = None
            
            if target_identifier.startswith('@'):
                # Поиск по юзернейму
                username = target_identifier[1:].lower()
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM users WHERE LOWER(username) = ? AND is_banned = 0', (username,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    target_user_id = result[0]
                else:
                    bot.send_message(message.chat.id, f"❌ Пользователь {target_identifier} не найден или забанен")
                    return
            else:
                # Поиск по ID
                try:
                    target_user_id = int(target_identifier)
                except ValueError:
                    bot.send_message(message.chat.id, f"❌ Неверный формат. Используйте @username или ID")
                    return
            
            # Получаем информацию о получателе
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (target_user_id,))
            target_data = cursor.fetchone()
            conn.close()
            
            if target_data:
                target_username, target_first_name = target_data
                target_identifier = f"@{target_username}" if target_username else target_first_name
            else:
                # Если пользователя нет в базе
                target_first_name = "Неизвестный"
                target_username = None
                target_identifier = f"ID: {target_user_id}"
        
        else:
            bot.send_message(message.chat.id, 
                           "❌ Формат:\n"
                           "• Ответьте `передать сумма` на сообщение\n"
                           "• `передать @username сумма`\n"
                           "• `кинуть ID сумма`\n\n"
                           "Примеры:\n"
                           "`передать @ivan 1000к`\n"
                           "`кинуть 123456789 500к`\n"
                           "[Ответить] `дать 1000`")
            return
        
        # Проверяем что нашли получателя
        if not target_user_id:
            bot.send_message(message.chat.id, "❌ Получатель не найден")
            return
        
        # Проверяем не пытается ли передать самому себе
        if target_user_id == user_id:
            bot.send_message(message.chat.id, "❌ Нельзя передавать деньги самому себе")
            return
        
        # Проверяем бан получателя
        target_banned, target_reason = is_banned(target_user_id)
        if target_banned:
            bot.send_message(message.chat.id, f"❌ Получатель забанен!")
            return
        
        # Парсим сумму
        if 'transfer_amount' not in locals():
            transfer_amount = parse_bet_amount(amount_text, balance)
        
        if transfer_amount is None:
            bot.send_message(message.chat.id, 
                           "❌ Неверная сумма\n"
                           "Примеры: `1000`, `10к`, `100к`, `1кк`, `1ккк`",
                           parse_mode='Markdown')
            return
        
        if transfer_amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма: 10❄️")
            return
        
        if transfer_amount > balance:
            bot.send_message(message.chat.id, 
                           f"❌ Недостаточно средств!\n"
                           f"Ваш баланс: ❄️{format_balance(balance)}\n"
                           f"Нужно ещё: ❄️{format_balance(transfer_amount - balance)}")
            return
        
        # Убеждаемся что получатель существует в базе
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT first_name, username FROM users WHERE user_id = ?', (target_user_id,))
        target_data = cursor.fetchone()
        
        if not target_data:
            # Если пользователя нет в базе, создаем его
            if not target_username and not target_first_name:
                # Пытаемся получить информацию из Telegram
                try:
                    chat_member = bot.get_chat_member(target_user_id, target_user_id)
                    target_first_name = chat_member.user.first_name
                    target_username = chat_member.user.username
                except:
                    # Если не удалось, используем заглушки
                    target_first_name = "Пользователь"
                    target_username = None
            
            # Создаем пользователя
            get_or_create_user(target_user_id, target_username, target_first_name)
            target_display = f"@{target_username}" if target_username else target_first_name
        else:
            target_first_name, target_username = target_data
            target_display = f"@{target_username}" if target_username else target_first_name
        
        conn.close()
        
        # Переводим деньги
        update_balance(user_id, -transfer_amount)
        update_balance(target_user_id, transfer_amount)
        
        new_balance = get_balance(user_id)
        target_balance = get_balance(target_user_id)
        
        sender_username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        
        # Уведомление отправителю
        bot.send_message(message.chat.id,
                       f"✅ *Перевод выполнен!*\n\n"
                       f"👤 *Кому:* {target_display}\n"
                       f"💰 *Сумма:* ❄️{format_balance(transfer_amount)}\n"
                       f"📊 *Ваш баланс:* ❄️{format_balance(new_balance)}",
                       parse_mode='Markdown')
        
        # Уведомление получателю
        try:
            bot.send_message(target_user_id,
                           f"🎉 *Вам перевели деньги!*\n\n"
                           f"👤 *От:* {sender_username}\n"
                           f"💰 *Сумма:* ❄️{format_balance(transfer_amount)}\n"
                           f"📊 *Ваш баланс:* ❄️{format_balance(target_balance)}",
                           parse_mode='Markdown')
        except Exception as e:
            # Если не удалось отправить получателю (закрыл ЛС и т.д.)
            logging.warning(f"Не удалось уведомить получателя {target_user_id}: {e}")
        
        # Логируем передачу
        log_user_action(user_id, "TRANSFER_SUCCESS", f"to={target_user_id} amount={transfer_amount}")
        
    except Exception as e:
        logging.error(f"Ошибка в передаче денег: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при передаче. Попробуйте позже.")
def parse_prizes_from_text(prizes_text, winners_count):
    """Парсит призы из текста"""
    try:
        prizes = []
        
        # Разбиваем текст на строки
        lines = prizes_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Ищем числа в строке
            # Примеры форматов:
            # "1 место - 1.000.000❄️"
            # "1 место: 1000000"
            # "1 место 1000к"
            
            # Убираем эмодзи снежков
            line = line.replace('❄️', '').replace('⛄', '').replace('🎄', '').replace('💰', '')
            
            # Ищем числовую часть
            import re
            
            # Попробуем найти число с разделителями
            matches = re.findall(r'[\d\s.,]+', line)
            if matches:
                for match in matches:
                    try:
                        # Очищаем от пробелов и точек
                        clean_match = match.replace(' ', '').replace(',', '').replace('.', '')
                        
                        # Пробуем парсить с множителями (к, кк, ккк)
                        if 'ккк' in line.lower():
                            prize = int(float(clean_match.replace('ккк', '').replace('kkk', '')) * 1000000000)
                        elif 'кк' in line.lower():
                            prize = int(float(clean_match.replace('кк', '').replace('kk', '')) * 1000000)
                        elif 'к' in line.lower() or 'k' in line.lower():
                            prize = int(float(clean_match.replace('к', '').replace('k', '')) * 1000)
                        else:
                            prize = int(clean_match)
                            
                        if prize > 0:
                            prizes.append(prize)
                    except:
                        continue
        
        # Если не нашли призов в тексте, создаем стандартные
        if not prizes:
            # Стандартные призы: уменьшающиеся суммы
            base_prize = 1000000  # 1 миллион
            for i in range(winners_count):
                prize_amount = base_prize // (2 ** i)  # Каждый следующий в 2 раза меньше
                if prize_amount < 1000:  # Минимум 1000
                    prize_amount = 1000
                prizes.append(prize_amount)
        
        # Убедимся что количество призов = количеству победителей
        while len(prizes) < winners_count:
            # Если призов меньше чем победителей, дополняем минимальными
            prizes.append(1000)
            
        while len(prizes) > winners_count:
            # Если призов больше, обрезаем
            prizes = prizes[:winners_count]
            
        return prizes
        
    except Exception as e:
        logging.error(f"Ошибка парсинга призов: {e}")
        # Возвращаем стандартные призы
        prizes = []
        base_prize = 100
        for i in range(winners_count):
            prize_amount = base_prize // (2 ** i)
            if prize_amount < 100:
                prize_amount = 100
            prizes.append(prize_amount)
        return prizes
# =============== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ КОНКУРСОВ ===============
USER_CONTESTS = {}  # {user_id: {"step": X, "data": {}}}
ACTIVE_CONTESTS = {}  # {contest_id: {contest_data}}
CONTEST_PARTICIPANTS = {}  # {contest_id: [user_id1, user_id2, ...]}

# =============== КОМАНДА КОНКУРС ===============
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
            "1️⃣ *Шаг 1:* Пришлите ID канала или @username\n\n"
            "*Примеры:*\n"
            "• @channel_username\n"
            "• -1001234567890\n"
            "• https://t.me/channel_username\n\n"
            "⚠️ *Бот должен быть администратором канала*",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Ошибка начала конкурса: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка начала конкурса")

@bot.message_handler(func=lambda message: message.from_user.id in USER_CONTESTS)
def handle_contest_steps(message):
    """Обработка шагов создания конкурса"""
    user_id = message.from_user.id
    
    try:
        contest_data = USER_CONTESTS.get(user_id)
        
        if not contest_data:
            bot.send_message(message.chat.id, "❌ Сессия устарела. Используйте /конкурс")
            return
            
        step = contest_data["step"]
        data = contest_data["data"]
        
        if step == 1:
            # Шаг 1: Получаем канал
            channel_input = message.text.strip()
            
            bot.send_message(message.chat.id, "⏳ Проверяю канал...")
            
            try:
                # Обрабатываем разные форматы
                if channel_input.startswith('https://t.me/'):
                    channel_input = '@' + channel_input.replace('https://t.me/', '')
                
                # Получаем канал
                chat = bot.get_chat(channel_input)
                
                if chat.type != 'channel':
                    bot.send_message(message.chat.id, "❌ Это не канал")
                    return
                
                # Проверяем что бот админ
                bot_id = bot.get_me().id
                try:
                    admins = bot.get_chat_administrators(chat.id)
                    is_admin = any(admin.user.id == bot_id for admin in admins)
                    
                    if not is_admin:
                        bot.send_message(message.chat.id,
                                       f"❌ Бот не админ в канале!\n"
                                       f"Добавьте бота как администратора в: {chat.title}")
                        return
                except:
                    # Если не можем проверить, предупреждаем
                    bot.send_message(message.chat.id,
                                   f"⚠️ Не могу проверить права. Убедитесь что бот админ в: {chat.title}")
                
                # Сохраняем данные
                data["channel_id"] = chat.id
                data["channel_title"] = chat.title
                data["channel_username"] = f"@{chat.username}" if chat.username else f"ID: {chat.id}"
                contest_data["step"] = 2
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Канал: {chat.title}\n\n"
                    f"2️⃣ *Шаг 2:* Сколько участников нужно?\n"
                    f"• Минимум: 10\n"
                    f"• Максимум: 1000\n\n"
                    f"Пример: `100`",
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                error_msg = str(e).lower()
                if "not found" in error_msg:
                    bot.send_message(message.chat.id, "❌ Канал не найден")
                elif "forbidden" in error_msg:
                    bot.send_message(message.chat.id, "❌ Нет доступа к каналу")
                else:
                    bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:50]}")
                return
            
        elif step == 2:
            # Шаг 2: Количество участников
            try:
                max_participants = int(message.text.strip())
                if max_participants < 10:
                    bot.send_message(message.chat.id, "❌ Минимум 10 участников")
                    return
                if max_participants > 1000:
                    bot.send_message(message.chat.id, "❌ Максимум 1000 участников")
                    return
                    
                data["max_participants"] = max_participants
                contest_data["step"] = 3
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Участников: {max_participants}\n\n"
                    f"3️⃣ *Шаг 3:* Сколько будет победителей?\n"
                    f"• Минимум: 1\n"
                    f"• Максимум: {min(10, max_participants)}\n\n"
                    f"Пример: `5`",
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
                    f"4️⃣ *Шаг 4:* Введите призы\n\n"
                    f"*Пример:*\n"
                    f"1 место - 1.000.000❄️\n"
                    f"2 место - 500.000❄️\n"
                    f"3 место - 250.000❄️",
                    parse_mode='Markdown'
                )
                
            except ValueError:
                bot.send_message(message.chat.id, "❌ Введите число!")
                return
                
        elif step == 4:
            # Шаг 4: Призы
            prizes_text = message.text.strip()
            if not prizes_text:
                bot.send_message(message.chat.id, "❌ Введите призы")
                return
                
            data["prizes_text"] = prizes_text
            
            # Показываем превью
            preview_text = f"""
📋 *ПРЕДПРОСМОТР КОНКУРСА*

*🎯 Канал:* {data.get('channel_title', 'N/A')}
*👥 Участников:* {data.get('max_participants', 'N/A')}
*🏆 Победителей:* {data.get('winners_count', 'N/A')}

*💰 Призы:*
{data.get('prizes_text', 'N/A')}

*👤 Организатор:* {data.get('creator_name', 'N/A')}
"""
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("✅ ОПУБЛИКОВАТЬ", callback_data="contest_publish"),
                InlineKeyboardButton("✏️ ИЗМЕНИТЬ", callback_data="contest_edit"),
                InlineKeyboardButton("❌ ОТМЕНА", callback_data="contest_cancel")
            )
            
            bot.send_message(
                message.chat.id,
                preview_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
    except Exception as e:
        logging.error(f"Ошибка в шаге {step}: {e}", exc_info=True)
        bot.send_message(message.chat.id, f"❌ Ошибка. Начните заново: /конкурс")
        if user_id in USER_CONTESTS:
            del USER_CONTESTS[user_id]

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
            
            # Проверяем данные
            required = ['channel_id', 'max_participants', 'winners_count', 'prizes_text']
            for field in required:
                if field not in contest_data:
                    bot.answer_callback_query(call.id, f"❌ Нет данных: {field}", show_alert=True)
                    return
            
            # Создаем ID конкурса
            contest_id = f"contest_{user_id}_{int(time.time())}"
            
            try:
                # Создаем кнопку для участия
                bot_username = (bot.get_me()).username
                if not bot_username:
                    bot_username = "bot"
                
                participate_link = f"https://t.me/{bot_username}?start={contest_id}"
                
                # Создаем текст поста
                post_text = f"""🎊 *КОНКУРС!* 🎊


*👥 Участников:* {contest_data.get('max_participants', 'N/A')}
*🏆 Победителей:* {contest_data.get('winners_count', 'N/A')}

*💰 ПРИЗОВОЙ ФОНД:*
{contest_data.get('prizes_text', 'N/A')}



*👤 Организатор:* {contest_data.get('creator_name', 'N/A')}"""
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🎯 УЧАСТВОВАТЬ", url=participate_link))
                
                # Публикуем в канале
                bot.send_message(
                    contest_data['channel_id'],
                    post_text,
                    parse_mode='Markdown',
                    reply_markup=markup,
                    disable_web_page_preview=True
                )
                
                # Сохраняем конкурс
                ACTIVE_CONTESTS[contest_id] = {
                    **contest_data,
                    "contest_id": contest_id,
                    "created_at": time.time(),
                    "status": "active",
                    "published": True
                }
                
                CONTEST_PARTICIPANTS[contest_id] = []
                
                # Уведомляем создателя
                bot.edit_message_text(
                    f"✅ *КОНКУРС ОПУБЛИКОВАН!*\n\n"
                    f"📢 Канал: {contest_data.get('channel_title', 'N/A')}\n"
                    f"👥 Участников: 0/{contest_data.get('max_participants', 'N/A')}\n"
                    f"🏆 Победителей: {contest_data.get('winners_count', 'N/A')}\n"
                    f"🔗 ID конкурса: `{contest_id}`\n\n"
                    f"*Команды управления:*\n"
                    f"`итоги {contest_id}` — Подвести итоги\n"
                    f"`участники {contest_id}` — Список участников\n"
                    f"`отмена {contest_id}` — Отменить конкурс",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                
                bot.answer_callback_query(call.id, "✅ Опубликовано в канале!", show_alert=True)
                
                # Очищаем данные
                if user_id in USER_CONTESTS:
                    del USER_CONTESTS[user_id]
                
            except Exception as e:
                logging.error(f"Ошибка публикации: {e}")
                error_msg = str(e).lower()
                if "chat not found" in error_msg:
                    bot.answer_callback_query(call.id, "❌ Канал не найден", show_alert=True)
                elif "forbidden" in error_msg:
                    bot.answer_callback_query(call.id, "❌ Бот не может писать в канал", show_alert=True)
                elif "admin" in error_msg:
                    bot.answer_callback_query(call.id, "❌ Бот не админ канала", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)[:40]}", show_alert=True)
                return
            
        elif call.data == "contest_edit":
            # Редактирование
            if user_id in USER_CONTESTS:
                USER_CONTESTS[user_id]["step"] = 1
                
                bot.edit_message_text(
                    "✏️ *РЕДАКТИРОВАНИЕ*\n\n"
                    "Пришлите ID канала или @username:",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                bot.answer_callback_query(call.id, "✏️ Редактирование...")
            else:
                bot.answer_callback_query(call.id, "❌ Данные утеряны", show_alert=True)
                
        elif call.data == "contest_cancel":
            # Отмена
            if user_id in USER_CONTESTS:
                del USER_CONTESTS[user_id]
            
            try:
                bot.edit_message_text(
                    "❌ Создание отменено",
                    call.message.chat.id,
                    call.message.message_id
                )
            except:
                pass
            bot.answer_callback_query(call.id, "❌ Отменено")
            
    except Exception as e:
        logging.error(f"Ошибка в колбэке конкурса: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)
        except:
            pass



@bot.message_handler(func=lambda message: message.text.lower().startswith('итоги ') and is_admin(message.from_user.id))
def handle_contest_results(message):
    """Подведение итогов с автоматической выдачей призов"""
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
        
        # Выбираем победителей
        winners = random.sample(participants, contest['winners_count'])
        
        # Парсим призы из текста
        prizes_text = contest.get('prizes_text', '')
        prizes_list = parse_prizes_from_text(prizes_text, len(winners))
        
        # Формируем список победителей и начисляем призы
        winners_text = "🏆 *ПОБЕДИТЕЛИ И ПРИЗЫ:*\n\n"
        total_awarded = 0
        awards_given = 0
        awards_failed = 0
        
        for i, winner_id in enumerate(winners, 1):
            try:
                user = bot.get_chat(winner_id)
                username = f"@{user.username}" if user.username else user.first_name
                
                # Определяем приз для этого места
                prize_amount = 0
                if i <= len(prizes_list):
                    prize_amount = prizes_list[i-1]
                
                # Начисляем приз
                if prize_amount > 0:
                    update_balance(winner_id, prize_amount)
                    total_awarded += prize_amount
                    awards_given += 1
                    
                    winners_text += f"{i}. {username} - ❄️{format_balance(prize_amount)}\n"
                    
                    # Уведомляем победителя
                    try:
                        bot.send_message(
                            winner_id,
                            f"🎉 *ВЫ ВЫИГРАЛИ В КОНКУРСЕ!*\n\n"
                            f"🏆 Место: #{i}\n"
                            f"💰 Приз: ❄️{format_balance(prize_amount)}\n"
                            f"📢 Конкурс: {contest.get('channel_title', 'N/A')}\n\n"
                            f"🎰 Удачи в казино!",
                            parse_mode='Markdown'
                        )
                    except:
                        winners_text += " (не удалось уведомить)\n"
                        awards_failed += 1
                else:
                    winners_text += f"{i}. {username} - ❌ нет приза\n"
                    
            except Exception as e:
                logging.error(f"Ошибка начисления приза для {winner_id}: {e}")
                winners_text += f"{i}. ID: {winner_id} - ❌ ошибка начисления\n"
        
        winners_text += f"\n📊 Всего участников: {len(participants)}"
        winners_text += f"\n💰 Всего выдано: ❄️{format_balance(total_awarded)}"
        
        # Отправляем создателю
        bot.send_message(message.chat.id, winners_text, parse_mode='Markdown')
        
        # Создаем пост для канала
        channel_post = f"""🎊 *ИТОГИ КОНКУРСА!* 🎊

{winners_text}

Поздравляем победителей! 🎉

👤 Организатор: {contest.get('creator_name', 'N/A')}"""
        
        try:
            # Публикуем в канале
            bot.send_message(
                contest['channel_id'],
                channel_post,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Не удалось опубликовать в канале: {e}")
        
        # Завершаем конкурс
        ACTIVE_CONTESTS[contest_id]['status'] = 'finished'
        ACTIVE_CONTESTS[contest_id]['winners'] = winners
        ACTIVE_CONTESTS[contest_id]['prizes_awarded'] = prizes_list
        ACTIVE_CONTESTS[contest_id]['total_awarded'] = total_awarded
        
        # Отчет
        report = f"✅ Итоги подведены!\n\n"
        report += f"📊 Статистика:\n"
        report += f"👥 Участников: {len(participants)}\n"
        report += f"🏆 Победителей: {len(winners)}\n"
        report += f"💰 Выдано призов: {awards_given}/{len(winners)}\n"
        report += f"💸 Общая сумма: ❄️{format_balance(total_awarded)}\n"
        report += f"⚠️ Не удалось уведомить: {awards_failed}"
        
        bot.send_message(message.chat.id, report)
        
    except Exception as e:
        logging.error(f"Ошибка итогов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(func=lambda message: message.text.lower().startswith('участники ') and is_admin(message.from_user.id))
def handle_contest_participants(message):
    """Показать участников"""
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
        
        if not participants:
            bot.send_message(message.chat.id, "📭 Участников пока нет")
            return
        
        text = f"👥 *УЧАСТНИКИ:* {len(participants)}\n\n"
        
        for i, user_id in enumerate(participants[:20], 1):
            try:
                user = bot.get_chat(user_id)
                username = f"@{user.username}" if user.username else user.first_name
                text += f"{i}. {username}\n"
            except:
                text += f"{i}. ID: {user_id}\n"
        
        if len(participants) > 20:
            text += f"\n... и ещё {len(participants) - 20}"
        
        bot.send_message(message.chat.id, text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка участников: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

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
        
        # Завершаем
        ACTIVE_CONTESTS[contest_id]['status'] = 'cancelled'
        
        # Уведомляем в канале
        try:
            bot.send_message(
                contest['channel_id'],
                f"❌ *КОНКУРС ОТМЕНЕН*\n\n"
                f"Конкурс был отменен организатором.\n"
                f"Участников было: {participants}",
                parse_mode='Markdown'
            )
        except:
            pass
        
        bot.send_message(
            message.chat.id,
            f"✅ Конкурс отменен\n"
            f"👥 Участников было: {participants}"
        )
        
    except Exception as e:
        logging.error(f"Ошибка отмены: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text.lower() == 'моиконкурсы' and is_admin(message.from_user.id))
def handle_my_contests(message):
    """Мои конкурсы"""
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
        
        text = "🎯 *ВАШИ КОНКУРСЫ:*\n\n"
        
        for contest_id, contest, participants in my_contests:
            status = "✅" if contest.get('status') == 'active' else "🏁"
            text += f"{status} *{contest.get('channel_title', 'N/A')}*\n"
            text += f"ID: `{contest_id}`\n"
            text += f"Участников: {participants}/{contest.get('max_participants', 'N/A')}\n\n"
        
        text += "*Команды:*\n`итоги ID` `участники ID` `отмена ID`"
        
        bot.send_message(message.chat.id, text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка моих конкурсов: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# =============== ОЧИСТКА СТАРЫХ КОНКУРСОВ ===============
def cleanup_old_contests():
    """Очищает старые конкурсы"""
    while True:
        time.sleep(86400)  # Каждые 24 часа
        current_time = time.time()
        
        to_remove = []
        for contest_id, contest in ACTIVE_CONTESTS.items():
            # Удаляем завершенные конкурсы старше 7 дней
            if contest.get('status') in ['finished', 'cancelled']:
                if current_time - contest.get('created_at', current_time) > 604800:
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

*Команды управления:*
`итоги ID_конкурса` — Подвести итоги
`участники ID_конкурса` — Список участников
`отмена ID_конкурса` — Отменить конкурс

*Как участвовать:*
1. Найдите пост конкурса в канале
2. Нажмите кнопку "🎯 УЧАСТВОВАТЬ"
3. Бот проверит подписку на канал
4. Ждите результатов!

*Особенности:*
• Бот сам публикует конкурс в канале
• Проверка подписки на канал
• Победители выбираются случайно
• Автоматическое уведомление
"""
    
    bot.send_message(message.chat.id, info_text, parse_mode='Markdown')
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
BONUS_AMOUNT = 333


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
# === КОМАНДА РАЗБОНУС - РАЗОСЛАТЬ ВСЕМ БОНУС С КНОПКОЙ ===
@bot.message_handler(func=lambda message: message.text.lower() == 'разбонус' and is_admin(message.from_user.id))
def handle_mass_bonus(message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        bot.send_message(message.chat.id, "⏳ Начинаю массовую рассылку бонуса...")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем всех пользователей которые не забанены
        cursor.execute('SELECT user_id, username, first_name FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        conn.close()
        
        total_users = len(users)
        successful = 0
        failed = 0
        
        bot.send_message(message.chat.id, f"📊 Всего пользователей: {total_users}")
        
        current_time = int(time.time())
        
        # Рассылаем бонус с кнопкой
        for user in users:
            user_id, username, first_name = user
            
            try:
                # Проверяем подписку
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
                    # Для неподписанных отправляем сообщение с кнопкой подписки
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
# =============== ИГРА КРАШ С ЗАДАННЫМИ ШАНСАМИ ===============

CRASH_ODDS = {
    1.1: 80.0,   # 80% шанс на 1.1x
    1.2: 70.0,   # 70% шанс на 1.2x
    1.5: 60.0,   # 60% шанс на 1.5x
    2.0: 50.0,   # 50% шанс на 2.0x
    3.0: 25.0,   # 25% шанс на 3.0x
    5.0: 15.0,   # 15% шанс на 5.0x
    10.0: 5.0,   # 5% шанс на 10.0x
}

@bot.message_handler(func=lambda message: message.text.lower().startswith('краш'))
def crash_command(message):
    """Игра Краш с заданными шансами"""
    try:
        user_id = message.from_user.id
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
        
        # Проверяем формат команды
        parts = message.text.split()
        if len(parts) != 3:
            bot.send_message(
                message.chat.id,
                "📌 Формат: `краш X.XX сумма`\nПример: `краш 2.00 100к`",
                parse_mode='Markdown'
            )
            return
        
        try:
            # Парсим множитель
            multiplier = float(parts[1])
            
            # Проверяем допустимые множители
            allowed_multipliers = [1.1, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0]
            valid = False
            for allowed in allowed_multipliers:
                if abs(multiplier - allowed) < 0.05:  # Допуск 0.05
                    multiplier = allowed  # Исправляем до точного значения
                    valid = True
                    break
            
            if not valid:
                bot.send_message(
                    message.chat.id,
                    "⚠️ Допустимые множители:\n"
                    "1.1, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0"
                )
                return
            
            # Парсим ставку
            bet_amount = parse_bet_amount(parts[2], get_balance(user_id))
            
            if bet_amount is None:
                bot.send_message(message.chat.id, "❌ Неверный формат суммы")
                return
            
            # Минимальная ставка
            if bet_amount < 5:
                bot.send_message(message.chat.id, f"💰 Мин. ставка: 50.000❄️")
                return
            
            # Проверяем баланс
            balance = get_balance(user_id)
            if bet_amount > balance:
                bot.send_message(message.chat.id, f"❌ Недостаточно средств")
                return
            
            # Списываем ставку
            update_balance(user_id, -bet_amount)
            
            # Получаем шанс из таблицы
            win_chance = CRASH_ODDS[multiplier]
            
            # Отправляем подтверждение
            bot.send_message(
                message.chat.id,
                f"🎰 *Краш {multiplier:.1f}x*\n"
                f"💰 *{format_balance(bet_amount)}❄️*\n"
                f"🎯 *Шанс: {win_chance}%*\n"
                f"⏳ *3 сек...*",
                parse_mode='Markdown'
            )
            
            # Запускаем игру
            thread = threading.Thread(
                target=process_crash_with_fixed_odds,
                args=(user_id, bet_amount, multiplier, win_chance),
                daemon=True
            )
            thread.start()
            
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверный формат")
            
    except Exception as e:
        bot.send_message(message.chat.id, "⚡")

def process_crash_with_fixed_odds(user_id, bet_amount, multiplier, win_chance):
    """Обработка игры с фиксированными шансами"""
    time.sleep(3)  # Ждем 3 секунды
    
    # Генерируем случайное число от 0 до 100
    roll = random.uniform(0, 100)
    
    # Проверяем выиграл ли игрок
    if roll < win_chance:
        # ВЫИГРЫШ
        win_amount = int(bet_amount * multiplier)
        update_balance(user_id, win_amount)
        new_balance = get_balance(user_id)
        profit = win_amount - bet_amount
        
        # Генерируем "точку краха" (случайный множитель больше целевого)
        crash_point = round(multiplier + random.uniform(0.1, multiplier * 0.5), 2)
        
        # Отправляем результат
        try:
            bot.send_message(
                user_id,
                f"✅ {multiplier:.1f}x\n"
                f"🎯 {win_chance}%\n"
                f"💥 {crash_point:.2f}x\n"
                f"💰 +{format_balance(profit)}❄️\n"
                f"📊 {format_balance(new_balance)}❄️"
            )
        except:
            # Если ЛС недоступно, отправляем в чат
            pass
            
    else:
        # ПРОИГРЫШ
        new_balance = get_balance(user_id)
        
        # Генерируем "точку краха" (случайный множитель меньше целевого)
        crash_point = round(random.uniform(1.01, multiplier * 0.99), 2)
        
        # Отправляем результат
        try:
            bot.send_message(
                user_id,
                f"❌ {multiplier:.1f}x\n"
                f"🎯 {win_chance}%\n"
                f"💥 {crash_point:.2f}x\n"
                f"💸 -{format_balance(bet_amount)}❄️\n"
                f"📊 {format_balance(new_balance)}❄️"
            )
        except:
            # Если ЛС недоступно, отправляем в чат
            pass

# =============== КОМАНДА ДЛЯ ПРОСМОТРА ШАНСОВ ===============

@bot.message_handler(func=lambda message: message.text.lower() == 'шансы')
def show_crash_odds(message):
    """Показывает таблицу шансов"""
    odds_text = (
        "🎰 <b>ШАНСЫ КРАША</b>\n\n"
        f"<code>краш 1.1 сумма</code> - 80%\n"
        f"<code>краш 1.2 сумма</code> - 70%\n"
        f"<code>краш 1.5 сумма</code> - 60%\n"
        f"<code>краш 2.0 сумма</code> - 50%\n"
        f"<code>краш 3.0 сумма</code> - 25%\n"
        f"<code>краш 5.0 сумма</code> - 15%\n"
        f"<code>краш 10.0 сумма</code> - 5%\n\n"
        f"💰 <b>Мин. ставка:</b> 50.000❄️\n"
        f"⏱ <b>Время:</b> 3 секунды"
    )
    bot.send_message(message.chat.id, odds_text, parse_mode='HTML')

# =============== МИНИМАЛИСТИЧНАЯ ВЕРСИЯ ===============

@bot.message_handler(func=lambda message: message.text.lower().startswith('к '))
def mini_crash(message):
    """Минималистичная версия краша: к X.X сумма"""
    try:
        user_id = message.from_user.id
        parts = message.text.lower().split()
        
        if len(parts) != 3:
            return
        
        # Парсим множитель
        try:
            multiplier = float(parts[1])
            
            # Проверяем допустимые значения
            allowed = [1.1, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0]
            if multiplier not in allowed:
                return
        except:
            return
        
        # Ставка
        bet_amount = parse_bet_amount(parts[2], get_balance(user_id))
        if not bet_amount or bet_amount < 5:
            return
        
        # Игра
        update_balance(user_id, -bet_amount)
        bot.send_message(message.chat.id, f"🎲 {multiplier:.1f}x...")
        
        # Запускаем
        threading.Thread(
            target=quick_crash_result,
            args=(user_id, bet_amount, multiplier),
            daemon=True
        ).start()
        
    except:
        pass

def quick_crash_result(user_id, bet_amount, multiplier):
    """Быстрый результат для минималистичной версии"""
    time.sleep(2)
    
    # Получаем шанс из таблицы
    win_chance = CRASH_ODDS.get(multiplier, 50.0)
    
    # Проверяем выигрыш
    if random.uniform(0, 100) < win_chance:
        win_amount = int(bet_amount * multiplier)
        update_balance(user_id, win_amount)
        
        bot.send_message(
            user_id,
            f"✅ {multiplier:.1f}x\n"
            f"+{format_balance(win_amount)}"
        )
    else:
        bot.send_message(
            user_id,
            f"❌ {multiplier:.1f}x\n"
            f"-{format_balance(bet_amount)}"
        )
# =============== ИГРА ОРЁЛ И РЕШКА (МИНИМАЛИСТИЧНАЯ) ===============

COIN_COOLDOWN = {}

@bot.message_handler(func=lambda message: message.text.lower().startswith(('орёл ', 'орел ', 'решка ', 'монетка ')))
def handle_coin_game_minimal(message):
    """Минималистичная версия Орёл/Решка"""
    try:
        user_id = message.from_user.id
        
        # Кулдаун
        current_time = time.time()
        if user_id in COIN_COOLDOWN:
            if current_time - COIN_COOLDOWN[user_id] < 1:
                return
        COIN_COOLDOWN[user_id] = current_time
        
        # Парсим команду
        text = message.text.lower().strip()
        parts = text.split()
        
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Формат: орёл/решка [ставка]")
            return
        
        # Определяем выбор
        choice = 'орёл' if parts[0].startswith('ор') else 'решка' if parts[0].startswith('реш') else None
        if not choice:
            bot.send_message(message.chat.id, "❌ Только: орёл или решка")
            return
        
        # Ставка
        user_balance = get_balance(user_id)
        bet_amount = parse_bet_amount(' '.join(parts[1:]), user_balance)
        
        if not bet_amount or bet_amount < 10:
            bot.send_message(message.chat.id, "❌ Мин: 10❄️")
            return
        
        if bet_amount > user_balance:
            bot.send_message(message.chat.id, f"💸 Не хватает: {format_balance(bet_amount - user_balance)}❄️")
            return
        
        # Списываем
        update_balance(user_id, -bet_amount)
        
        # Анимация
        choice_icon = "🦅" if choice == 'орёл' else "🪙"
        msg = bot.send_message(message.chat.id, 
                             f"{choice_icon} Ставка: {format_balance(bet_amount)}❄️\n"
                             f"🎲 Бросок...")
        
        time.sleep(1.5)
        
        # Результат
        result = random.choice(['орёл', 'решка'])
        result_icon = "🦅" if result == 'орёл' else "🪙"
        
        if choice == result:
            win_amount = bet_amount * 2
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            
            bot.edit_message_text(
                f"🎯 {result_icon} {result.upper()}\n"
                f"✅ ВЫИГРЫШ ×2\n"
                f"💰 +{format_balance(win_amount)}❄️\n"
                f"📊 {format_balance(new_balance)}❄️",
                message.chat.id,
                msg.message_id
            )
            
            # Праздничный эмодзи для крупного выигрыша
            if win_amount > 10000:
                bot.send_message(message.chat.id, "🎰✨")
        else:
            new_balance = get_balance(user_id)
            
            bot.edit_message_text(
                f"🎯 {result_icon} {result.upper()}\n"
                f"❌ ПРОИГРЫШ\n"
                f"💸 -{format_balance(bet_amount)}❄️\n"
                f"📊 {format_balance(new_balance)}❄️",
                message.chat.id,
                msg.message_id
            )
    
    except Exception as e:
        bot.send_message(message.chat.id, "⚡")
# Глобальная переменная для хранения текущего состояния игр
user_game_menu_state = {}

@bot.message_handler(func=lambda message: message.text == "Игры")
def handle_games(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        user_game_menu_state[user_id] = "main"
        
        # Создаем инлайн-клавиатуру с играми
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🎲 Куб", callback_data="game_dice"),
            InlineKeyboardButton("🎰 Слоты", callback_data="game_slots"),
            InlineKeyboardButton("⚽ Футбол", callback_data="game_football"),
            InlineKeyboardButton("🏀 Баскетбол", callback_data="game_basketball"),
            InlineKeyboardButton("🎯 Дартс", callback_data="game_darts"),
            InlineKeyboardButton("🎳 Боулинг", callback_data="game_bowling"),
            InlineKeyboardButton("🎡 Рулетка", callback_data="game_roulette")
        )
        
        games_description = """
🎮 *ИГРЫ НА СНЕЖКИ*

Выберите игру из списка ниже ⬇️

*💰 Как делать ставки:*
`игра [ставка]` - например: `куб бол 1000`
`игра [число] [ставка]` - например: `рул красный 10к`

*📊 Примеры ставок:*
• `1000` - тысяча
• `10к` - десять тысяч
• `100к` - сто тысяч
• `1кк` - миллион
• `все` - весь баланс

*🎰 Выигрышные коэффициенты:*
🎲 Куб - до ×6
🎰 Слоты - до ×64
⚽ Футбол - ×1.5
🏀 Баскетбол - ×2.5
🎯 Дартс - до ×5
🎳 Боулинг - ×2
🎡 Рулетка - до ×36
"""
        
        # Отправляем сообщение с инлайн-кнопками
        bot.send_message(message.chat.id, games_description, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_games: {e}", exc_info=True)
        bot.send_message(message.chat.id, "❌ Ошибка загрузки игр. Попробуйте снова.")

# Обработчик для всех инлайн-кнопок игр
@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def handle_game_callback(call):
    try:
        user_id = call.from_user.id
        
        if is_spam(user_id):
            bot.answer_callback_query(call.id, "⏳ Слишком быстро!")
            return
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.answer_callback_query(call.id, "🚫 Вы забанены!")
            return
        
        game_type = call.data.replace("game_", "")
        
        # Определяем информацию о каждой игре
        if game_type == "dice":
            title = "🎲 КУБИК"
            description = """
*🎲 ИГРА В КУБИК*

*🎯 Типы ставок:*
• `куб [число] [ставка]` - на конкретное число (1-6)
• `куб бол [ставка]` - на большие числа (4-6)
• `куб мал [ставка]` - на малые числа (1-3)
• `куб чет [ставка]` - на четные числа (2,4,6)
• `куб неч [ставка]` - на нечетные числа (1,3,5)

*💰 Коэффициенты:*
• Конкретное число - ×6
• Большие/Малые - ×2
• Четные/Нечетные - ×2

*📝 Примеры:*
• `куб 3 1000` - на число 3 ставка 1000❄️
• `куб бол 10к` - на большие ставка 10.000❄️
• `куб мал все` - на малые весь баланс
• `куб чет 100к` - на четные 100.000❄️

*🎲 Как играть:*
Бросьте кубик, выиграйте если угадаете результат!
"""
            
        elif game_type == "slots":
            title = "🎰 СЛОТЫ"
            description = """
*🎰 ИГРОВОЙ АВТОМАТ*

*🎯 Как играть:*
`слоты [ставка]` - крутите барабаны

*💰 Выигрышные комбинации:*
• Джекпот (банан) - ×64
• Три семерки - ×10
• Три вишни - ×5
• Три одинаковых - ×3

*📝 Примеры:*
• `слоты 1000` - ставка 1000❄️
• `слоты 10к` - ставка 10.000❄️
• `слоты все` - поставить весь баланс

*🎰 Как играть:*
Нажмите кнопку, барабаны закрутятся!
Ждите пока слоты остановятся...
"""
            
        elif game_type == "football":
            title = "⚽ ФУТБОЛ"
            description = """
*⚽ ИГРА В ФУТБОЛ*

*🎯 Как играть:*
`фтб [ставка]` - бейте по воротам!

*💰 Коэффициент:*
• Гол - ×1.5
• Промах - проигрыш

*🎯 Результаты кубика:*
• 1 - мяч за пределами поля
• 2 - мяч попал в штангу
• 3 - гол (левая сторона)
• 4 - гол (правая сторона)
• 5 - гол (центр)
• 6 - мяч заблокирован вратарем

*📝 Примеры:*
• `фтб 1000` - ставка 1000❄️
• `фтб 10к` - ставка 10.000❄️
• `фтб все` - поставить весь баланс

*⚽ Как играть:*
Ударьте по мячу, попробуйте забить гол!
"""
            
        elif game_type == "basketball":
            title = "🏀 БАСКЕТБОЛ"
            description = """
*🏀 ИГРА В БАСКЕТБОЛ*

*🎯 Как играть:*
`бск [ставка]` - бросайте мяч в корзину!

*💰 Коэффициент:*
• Попадание - ×2.5
• Промах - проигрыш

*🎯 Результаты кубика:*
• 4 или 5 - попадание в корзину
• 1,2,3,6 - промах

*📝 Примеры:*
• `бск 1000` - ставка 1000❄️
• `бск 10к` - ставка 10.000❄️
• `бск все` - поставить весь баланс

*🏀 Как играть:*
Бросьте мяч, попадите в корзину!
"""
            
        elif game_type == "darts":
            title = "🎯 ДАРТС"
            description = """
*🎯 ИГРА В ДАРТС*

*🎯 Как играть:*
`дартс [ставка]` - бросайте дротик!

*💰 Коэффициенты:*
• Яблочко (центр) - ×5
• Внутреннее кольцо - ×1 (возврат)
• Внешнее кольцо - ×1 (возврат)
• Полный промах - ×0 (потеря двойной ставки)

*🎯 Результаты кубика:*
• 6 - яблочко (центр)
• 5 - внутреннее кольцо
• 4 - внешнее кольцо
• 1 - полный промах

*⚠️ Внимание:*
При полном промахе теряется ДВОЙНАЯ ставка!

*📝 Примеры:*
• `дартс 1000` - ставка 1000❄️
• `дартс 10к` - ставка 10.000❄️
"""
            
        elif game_type == "bowling":
            title = "🎳 БОУЛИНГ"
            description = """
*🎳 ИГРА В БОУЛИНГ*

*🎯 Как играть:*
`боул [ставка]` - катите шар по дорожке!

*💰 Коэффициенты:*
• Страйк (все кегли) - ×2
• 9 кеглей - возврат ставки
• Меньше 9 кеглей - проигрыш

*🎳 Результаты кубика:*
• 6 - страйк (все кегли сбиты)
• 5 - 9 кеглей сбито
• 4 - 7-8 кеглей сбито
• 3 - 5-6 кеглей сбито
• 2 - 3-4 кегли сбиты
• 1 - 1-2 кегли сбиты

*📝 Примеры:*
• `боул 1000` - ставка 1000❄️
• `боул 10к` - ставка 10.000❄️
• `боул все` - поставить весь баланс

*🎳 Как играть:*
Сбейте как можно больше кеглей!
"""
            
        elif game_type == "roulette":
            title = "🎡 РУЛЕТКА"
            description = """
*🎡 ИГРА В РУЛЕТКУ*

*🎯 Типы ставок:*
• `рул красный [ставка]` - на красное
• `рул черный [ставка]` - на черное
• `рул 0 [ставка]` - на ноль (зеленое)
• `рул [число] [ставка]` - на конкретное число (0-36)
• `рул большие [ставка]` - на большие (19-36)
• `рул малые [ставка]` - на малые (1-18)
• `рул чет [ставка]` - на четные
• `рул нечет [ставка]` - на нечетные

*💰 Коэффициенты:*
• Красное/Черное - ×2
• Большие/Малые - ×2
• Четные/Нечетные - ×2
• Конкретное число - ×36
• Ноль - ×36

*🎡 Красные числа:*
1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36

*🎡 Черные числа:*
2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35

*📝 Примеры:*
• `рул красный 1000` - на красное 1000❄️
• `рул 17 10к` - на число 17 ставка 10.000❄️
• `рул 0 100к` - на ноль 100.000❄️
• `рул бол все` - на большие весь баланс
"""
        
        # Создаем инлайн-кнопку "Назад"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("◀️ Назад к играм", callback_data="game_back"))
        
        # Формируем полное сообщение
        full_message = f"{title}\n{'='*30}\n{description}"
        
        # Редактируем существующее сообщение
        try:
            bot.edit_message_text(
                full_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            user_game_menu_state[user_id] = game_type
        except Exception as e:
            # Если не удалось редактировать (например, сообщение слишком старое)
            logging.error(f"Ошибка редактирования: {e}")
            bot.send_message(
                call.message.chat.id,
                full_message,
                reply_markup=markup,
                parse_mode='Markdown'
            )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logging.error(f"Ошибка в handle_game_callback: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# Обработчик кнопки "Назад"
@bot.callback_query_handler(func=lambda call: call.data == "game_back")
def handle_game_back(call):
    try:
        user_id = call.from_user.id
        
        # Возвращаемся к главному меню игр
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🎲 Куб", callback_data="game_dice"),
            InlineKeyboardButton("🎰 Слоты", callback_data="game_slots"),
            InlineKeyboardButton("⚽ Футбол", callback_data="game_football"),
            InlineKeyboardButton("🏀 Баскетбол", callback_data="game_basketball"),
            InlineKeyboardButton("🎯 Дартс", callback_data="game_darts"),
            InlineKeyboardButton("🎳 Боулинг", callback_data="game_bowling"),
            InlineKeyboardButton("🎡 Рулетка", callback_data="game_roulette")
        )
        
        games_description = """
🎮 *ИГРЫ НА СНЕЖКИ*

Выберите игру из списка ниже ⬇️

*💰 Как делать ставки:*
`игра [ставка]` - например: `куб бол 1000`
`игра [число] [ставка]` - например: `рул красный 10к`

*📊 Примеры ставок:*
• `1000` - тысяча
• `10к` - десять тысяч
• `100к` - сто тысяч
• `1кк` - миллион
• `все` - весь баланс

*🎰 Выигрышные коэффициенты:*
🎲 Куб - до ×6
🎰 Слоты - до ×64
⚽ Футбол - ×1.5
🏀 Баскетбол - ×2.5
🎯 Дартс - до ×5
🎳 Боулинг - ×2
🎡 Рулетка - до ×36
"""
        
        try:
            bot.edit_message_text(
                games_description,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            user_game_menu_state[user_id] = "main"
        except:
            bot.send_message(
                call.message.chat.id,
                games_description,
                reply_markup=markup,
                parse_mode='Markdown'
            )
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logging.error(f"Ошибка в handle_game_back: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")


# =============== КОМАНДА /COIN ДЛЯ ИНФО ===============

@bot.message_handler(commands=['coin'])
def coin_info(message):
    """Информация об игре"""
    info_text = (
        "🎲 <b>ОРЁЛ И РЕШКА</b>\n\n"
        "<code>орёл 1000</code> - ставка на орла\n"
        "<code>решка 5к</code> - ставка на решку\n\n"
        "🎯 Коэффициент: <b>2×</b>\n"
        "💰 Мин. ставка: <b>10❄️</b>\n\n"
        "📈 Шанс: <b>50/50</b>"
    )
    bot.send_message(message.chat.id, info_text, parse_mode='HTML')

# =============== ИНЛАЙН КНОПКИ (ОПЦИОНАЛЬНО) ===============

@bot.message_handler(func=lambda message: message.text.lower() == 'монетка')
def coin_menu(message):
    """Меню игры с кнопками"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🦅 Орёл", callback_data="coin_mini_орёл"),
        InlineKeyboardButton("🪙 Решка", callback_data="coin_mini_решка")
    )
    
    bot.send_message(
        message.chat.id,
        "🎲 <b>Быстрая монетка</b>\n💰 Введите ставку после выбора",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('coin_mini_'))
def coin_mini_callback(call):
    """Обработчик выбора через кнопки"""
    try:
        choice = call.data.split('_')[2]  # орёл или решка
        choice_icon = "🦅" if choice == 'орёл' else "🪙"
        
        bot.answer_callback_query(call.id, f"Выбрано: {choice}")
        
        bot.send_message(
            call.message.chat.id,
            f"{choice_icon} <b>{choice.upper()}</b>\n"
            f"💰 Введите ставку\n"
            f"Пример: <code>1000</code> или <code>5к</code>",
            parse_mode='HTML'
        )
        
        # Сохраняем выбор в памяти
        user_states[call.from_user.id] = {'coin_choice': choice}
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌")

# Добавьте в обработчик текстовых сообщений
user_states = {}

@bot.message_handler(func=lambda message: message.from_user.id in user_states and 'coin_choice' in user_states[message.from_user.id])
def handle_coin_bet_after_choice(message):
    """Обработка ставки после выбора через кнопки"""
    try:
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        
        if 'coin_choice' not in state:
            return
        
        choice = state['coin_choice']
        
        # Удаляем состояние
        del user_states[user_id]
        
        # Создаем полную команду
        full_command = f"{choice} {message.text}"
        
        # Вызываем основной обработчик
        handle_coin_game_minimal(type('Message', (), {
            'text': full_command,
            'from_user': type('User', (), {'id': user_id})(),
            'chat': type('Chat', (), {'id': message.chat.id})()
        })())
    
    except Exception as e:
        bot.send_message(message.chat.id, "⚡")

# =============== АЛЬТЕРНАТИВНАЯ УЛЬТРА-МИНИМАЛИСТИЧНАЯ ВЕРСИЯ ===============

@bot.message_handler(func=lambda message: message.text.lower().startswith(('ор', 'реш')) and message.text.split()[0].lower() in ['орёл', 'орел', 'решка'])
def ultra_minimal_coin(message):
    """Ультра-минималистичная версия"""
    try:
        user_id = message.from_user.id
        text = message.text.lower()
        parts = text.split()
        
        if len(parts) < 2:
            return
        
        # Быстрая проверка
        if user_id in COIN_COOLDOWN and time.time() - COIN_COOLDOWN[user_id] < 0.5:
            return
        
        COIN_COOLDOWN[user_id] = time.time()
        
        # Парсим
        choice = 'орёл' if parts[0].startswith('ор') else 'решка'
        bet = parse_bet_amount(' '.join(parts[1:]), get_balance(user_id))
        
        if not bet or bet < 10:
            return
        
        # Игра
        update_balance(user_id, -bet)
        
        result = random.choice(['орёл', 'решка'])
        win = (choice == result)
        
        if win:
            win_amount = bet * 2
            update_balance(user_id, win_amount)
            bot.send_message(message.chat.id, 
                           f"🎲 {result[0].upper()} | ✅ ×2 | +{format_balance(win_amount)}")
        else:
            bot.send_message(message.chat.id,
                           f"🎲 {result[0].upper()} | ❌ | -{format_balance(bet)}")
    
    except:
        pass
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
# =============== ЧИСТАЯ СИСТЕМА МАЙНИНГА ЕЛОК ===============

# Обработчик кнопки "Майнинг"
@bot.message_handler(func=lambda message: message.text == "Майнинг")
def handle_mining(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        # Получаем данные пользователя
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT video_cards, last_mining_collect FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            bot.send_message(message.chat.id, "❌ Пользователь не найден")
            return
        
        video_cards, last_mining_collect = result
        
        # Рассчитываем накопленные елки
        current_time = time.time()
        total_accumulated = 0
        
        if last_mining_collect and last_mining_collect > 0 and video_cards > 0:
            hours_passed = int((current_time - last_mining_collect) / 3600)
            if hours_passed > 0:
                # Доход за час: сумма арифметической прогрессии 1+2+3+...+n
                hourly_income = video_cards * (video_cards + 1) // 2
                total_accumulated = hourly_income * hours_passed
        
        # Добыча в час
        hourly_income = video_cards * (video_cards + 1) // 2 if video_cards > 0 else 0
        
        # Стоимость следующей карты
        next_card_price = 5000 * (2 ** video_cards)  # 5к × 2^n
        
        # Создаем сообщение
        message_text = "🎄 *МАЙНИНГ*\n\n"
        message_text += f"🖥 *Карт:* {video_cards}\n"
        
        if video_cards > 0:
            message_text += f"⏰ *Добыча:* 🎄{hourly_income}/час\n"
            
            if total_accumulated > 0:
                message_text += f"💰 *Накоплено:* 🎄{total_accumulated}\n"
            else:
                message_text += f"💰 *Накоплено:* 🎄0\n"
        
        message_text += f"💵 *Следующая:* ❄️{format_balance(next_card_price)}"
        
        # Создаем клавиатуру
        markup = InlineKeyboardMarkup(row_width=2)
        
        if total_accumulated > 0:
            markup.add(InlineKeyboardButton("🎄 Собрать", callback_data="mining_collect"))
        
        markup.add(
            InlineKeyboardButton("🖥 Купить карту", callback_data="mining_buy")
        )
        
        bot.send_message(message.chat.id, message_text, parse_mode='Markdown', reply_markup=markup)
    
    except Exception as e:
        logging.error(f"Ошибка в handle_mining: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка")

# Обработчик callback для майнинга
@bot.callback_query_handler(func=lambda call: call.data.startswith('mining_'))
def mining_callback_handler(call):
    try:
        user_id = call.from_user.id
        
        if call.data == "mining_collect":
            # Сбор елок
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT video_cards, last_mining_collect FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ Ошибка")
                return
            
            video_cards, last_mining_collect = result
            
            if video_cards == 0:
                bot.answer_callback_query(call.id, "❌ Нет видеокарт")
                conn.close()
                return
            
            current_time = time.time()
            
            if not last_mining_collect or last_mining_collect == 0:
                # Начинаем майнинг
                cursor.execute('UPDATE users SET last_mining_collect = ? WHERE user_id = ?', 
                             (current_time, user_id))
                conn.commit()
                conn.close()
                bot.answer_callback_query(call.id, "⏳ Майнинг начался")
                return
            
            # Рассчитываем накопления
            hours_passed = int((current_time - last_mining_collect) / 3600)
            
            if hours_passed < 1:
                bot.answer_callback_query(call.id, "⏳ Подождите час")
                conn.close()
                return
            
            # Рассчитываем елки
            hourly_income = video_cards * (video_cards + 1) // 2
            trees_earned = hourly_income * hours_passed
            
            # Обновляем время сбора
            cursor.execute('UPDATE users SET last_mining_collect = ? WHERE user_id = ?', 
                         (current_time, user_id))
            conn.commit()
            conn.close()
            
            # Обновляем сообщение
            next_card_price = 5000 * (2 ** video_cards)
            
            message_text = f"✅ *СОБРАНО!*\n\n"
            message_text += f"🖥 *Карт:* {video_cards}\n"
            message_text += f"⏰ *Прошло часов:* {hours_passed}\n"
            message_text += f"💰 *Собрано:* 🎄{trees_earned}\n"
            message_text += f"💵 *Следующая карта:* ❄️{format_balance(next_card_price)}"
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🖥 Купить карту", callback_data="mining_buy"))
            
            try:
                bot.edit_message_text(
                    message_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
            except:
                bot.send_message(call.message.chat.id, message_text, parse_mode='Markdown', reply_markup=markup)
            
            bot.answer_callback_query(call.id, f"✅ +🎄{trees_earned}")
            
        elif call.data == "mining_buy":
            # Покупка карты
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT video_cards, balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ Ошибка")
                return
            
            video_cards, balance = result
            
            # Цена карты
            card_price = 5000 * (2 ** video_cards)
            
            if balance < card_price:
                bot.answer_callback_query(call.id, 
                                        f"❌ Нужно ❄️{format_balance(card_price)}",
                                        show_alert=True)
                conn.close()
                return
            
            # Покупаем карту
            cursor.execute('UPDATE users SET balance = balance - ?, video_cards = video_cards + 1 WHERE user_id = ?',
                         (card_price, user_id))
            conn.commit()
            
            # Получаем новые данные
            cursor.execute('SELECT video_cards, balance FROM users WHERE user_id = ?', (user_id,))
            new_result = cursor.fetchone()
            new_video_cards, new_balance = new_result
            
            conn.close()
            
            # Рассчитываем доход
            old_income = video_cards * (video_cards + 1) // 2
            new_income = new_video_cards * (new_video_cards + 1) // 2
            
            # Обновляем сообщение
            next_card_price = 5000 * (2 ** new_video_cards)
            
            message_text = f"✅ *КАРТА КУПЛЕНА!*\n\n"
            message_text += f"🖥 *Карт:* {new_video_cards}\n"
            message_text += f"💰 *Стоимость:* ❄️{format_balance(card_price)}\n"
            message_text += f"❄️ *Баланс:* ❄️{format_balance(new_balance)}\n"
            message_text += f"⏰ *Доход:* 🎄{new_income}/час\n"
            message_text += f"📈 *Прирост:* +🎄{new_income - old_income}/час\n"
            message_text += f"💵 *Следующая:* ❄️{format_balance(next_card_price)}"
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🖥 Купить карту", callback_data="mining_buy"))
            
            try:
                bot.edit_message_text(
                    message_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
            except:
                bot.send_message(call.message.chat.id, message_text, parse_mode='Markdown', reply_markup=markup)
            
            bot.answer_callback_query(call.id, f"✅ +1 карта")
            
    except Exception as e:
        logging.error(f"Ошибка в майнинге: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")


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