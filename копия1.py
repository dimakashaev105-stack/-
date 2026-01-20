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
    try:
        conn = sqlite3.connect('game.db', timeout=10)
        # Включаем WAL-режим для лучшей производительности
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA foreign_keys=ON')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Ошибка подключения к БД: {e}")
        raise

# === ИЗМЕНЕНО: полностью переписанная инициализация БД ===
def init_db():
    """Инициализация базы данных с корректной структурой"""
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
            last_bonus TIMESTAMP
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
# === КОНЕЦ ИЗМЕНЕНИЙ ===

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
            interest = int(bank_deposit * 0.005 * interest_hours)  # 0.5% за каждый час
            
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


# Главное меню
def create_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    balance_button = KeyboardButton("Баланс")
    mining_button = KeyboardButton("Майнинг")
    bank_button = KeyboardButton("Банк")
    casino_button = KeyboardButton("Казино")
    work_button = KeyboardButton("Работа")
    majors_button = KeyboardButton("Мажоры")
    top_scam_button = KeyboardButton("Топ скам")
    clan_panel_button = KeyboardButton("Панель клана")
    bonus_button = KeyboardButton("Бонус")
    markup.add(balance_button, mining_button, bank_button, casino_button,
               work_button, majors_button, top_scam_button, clan_panel_button)
    return markup





# Обработчик команды /start с реферальной системой
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
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        is_new_user = False
        
        if not user_data:
            # Пользователь новый - создаем его
            is_new_user = True
            referral_code = f"ref{user_id}"
            
            cursor.execute(
                'INSERT INTO users (user_id, username, first_name, balance, referral_code, video_cards, deposit, last_mining_collect, click_streak, bank_deposit, captcha_passed, is_banned, last_interest_calc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (user_id, username, first_name, 0, referral_code, 0, 0, 0, 0, 0, 0, 0, datetime.now().timestamp())
            )
            conn.commit()
            
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
        
        # Обработка реферальных ссылок и чеков (только если есть код в ссылке)
        if len(message.text.split()) > 1:
            ref_code = message.text.split()[1].strip()
            
            # Проверяем, это чек?
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('SELECT amount, max_activations, current_activations FROM checks WHERE code = ?', (ref_code,))
            check_data = cursor.fetchone()
            
            if check_data:
                amount, max_activations, current_activations = check_data
                
                # Проверяем, активировал ли пользователь уже этот чек
                cursor.execute('SELECT * FROM check_activations WHERE user_id = ? AND check_code = ?', (user_id, ref_code))
                already_activated = cursor.fetchone()
                
                if already_activated:
                    bot.send_message(message.chat.id, "❌ Вы уже активировали этот чек!")
                elif current_activations >= max_activations:
                    bot.send_message(message.chat.id, "❌ Чек уже использован максимальное количество раз!")
                else:
                    # Атомарное обновление счетчика активаций (решает проблему гонки условий)
                    cursor.execute('UPDATE checks SET current_activations = current_activations + 1 WHERE code = ? AND current_activations < max_activations', (ref_code,))
                    
                    # Проверяем, была ли обновлена хотя бы одна строка
                    rows_updated = cursor.rowcount
                    
                    if rows_updated > 0:
                        # Чек был успешно активирован
                        try:
                            # Добавляем запись об активации
                            cursor.execute('INSERT OR IGNORE INTO check_activations (user_id, check_code) VALUES (?, ?)', (user_id, ref_code))
                            
                            # Начисляем деньги пользователю
                            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
                            
                            conn.commit()
                            bot.send_message(message.chat.id, f"🎉 Вы активировали чек на ❄️{format_balance(amount)}!")
                        except sqlite3.Error as e:
                            print(f"Ошибка при активации чека: {e}")
                            # Откатываем изменения
                            cursor.execute('UPDATE checks SET current_activations = current_activations - 1 WHERE code = ?', (ref_code,))
                            conn.rollback()
                            bot.send_message(message.chat.id, "❌ Ошибка при активации чека. Попробуйте позже.")
                    else:
                        # Чек уже был активирован кем-то другим в этот момент
                        bot.send_message(message.chat.id, "❌ Чек уже был активирован другим пользователем!")
            
            conn.close()
        
        # Показываем главное меню
        markup = create_main_menu()
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка. Попробуйте снова.")

# === УДАЛИТЕ ВСЮ СТАРУЮ ФУНКЦИЮ ТОПА И ДОБАВЬТЕ ЭТУ ===

# Глобальная переменная для хранения текущей страницы топа для каждого пользователя
user_top_page = {}

# =============== ФУНКЦИЯ ПОЛУЧЕНИЯ ТОПА С ПАГИНАЦИЕЙ ===============
def get_top_majors_page(page=1, limit=5, user_id=None):
    """Получает топ пользователей для конкретной страницы с пагинацией"""
    offset = (page - 1) * limit
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем топ пользователей для страницы
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
    
    # Получаем общее количество пользователей с балансом > 0
    cursor.execute('SELECT COUNT(*) FROM users WHERE balance > 0 AND is_banned = 0')
    total_users = cursor.fetchone()[0]
    
    total_pages = (total_users + limit - 1) // limit
    
    # Получаем позицию текущего пользователя (если передан user_id)
    user_position = None
    if user_id:
        cursor.execute('''
        SELECT position FROM (
            SELECT user_id, ROW_NUMBER() OVER (ORDER BY balance DESC) as position
            FROM users 
            WHERE balance > 0 AND is_banned = 0
        ) WHERE user_id = ?
        ''', (user_id,))
        user_position_result = cursor.fetchone()
        user_position = user_position_result[0] if user_position_result else None
    
    conn.close()
    
    return {
        'users': top_users,
        'total': total_users,
        'current_page': page,
        'total_pages': total_pages,
        'user_position': user_position
    }
# =============== КОНЕЦ ФУНКЦИИ ===============

# =============== ОБРАБОТЧИК КОМАНДЫ "ТОП СНЕЖКОВ" ===============
@bot.message_handler(func=lambda message: message.text in ["Мажоры", "топ", "Топ", "Топ снежков", "топ снежков", "Топ баланса"])
def handle_majors(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
        
        user_id = message.from_user.id
        
        # Устанавливаем первую страницу
        user_top_page[user_id] = 1
        
        # Создаем сообщение с топом
        top_message = create_top_message(user_id, 1)
        
        # Создаем клавиатуру с пагинацией
        markup = create_top_keyboard(user_id, 1)
        
        bot.send_message(message.chat.id, top_message, reply_markup=markup, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_majors: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки топа. Попробуйте снова.")
# =============== КОНЕЦ ОБРАБОТЧИКА ===============

# =============== ФУНКЦИЯ СОЗДАНИЯ СООБЩЕНИЯ ТОПА ===============
def create_top_message(user_id, page=1):
    """Создает сообщение с топом пользователей"""
    try:
        # Получаем данные для страницы
        top_data = get_top_majors_page(page, 5, user_id)
        top_users = top_data['users']
        total_pages = top_data['total_pages']
        current_page = top_data['current_page']
        user_position = top_data['user_position']
        
        # Получаем данные текущего пользователя для отображения его позиции
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 
            CASE 
                WHEN username IS NOT NULL AND username != '' THEN '@' || username 
                ELSE first_name 
            END as display_name,
            balance
        FROM users 
        WHERE user_id = ?
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        conn.close()
        
        # Создаем сообщение
        message_text = "🎅 <b>Топ снежков</b> 🎅\n\n"
        
        if not top_users:
            message_text += "📭 Топ пока пуст! Станьте первым!\n\n"
            message_text += "<i>Зарабатывайте ❄️ в казино или работах</i>"
        else:
            # Добавляем места с эмодзи
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            
            for user in top_users:
                user_id_db, display_name, balance, position = user
                
                # Определяем номер позиции на текущей странице (1-5)
                page_position = ((page - 1) * 5) + (top_users.index(user) + 1)
                
                # Используем эмодзи для первых 5 позиций, затем цифры
                if page_position <= 3:
                    medal = medals[page_position-1]
                elif page_position <= 5:
                    medal = medals[page_position-1]
                else:
                    medal = f"{page_position}."
                
                # Форматируем имя (обрезаем если слишком длинное)
                if len(display_name) > 20:
                    display_name = display_name[:17] + "..."
                
                message_text += f"{medal} {display_name} ⟨{format_balance(balance)}❄️⟩\n"
        
        # Добавляем информацию о текущей странице
        message_text += f"\n📄 Страница {current_page}/{total_pages}"
        
        # Добавляем информацию о позиции пользователя
        if user_data and user_position:
            user_display_name, user_balance = user_data
            
            # Обрезаем длинное имя
            if len(user_display_name) > 20:
                user_display_name = user_display_name[:17] + "..."
            
            message_text += f"\n\n🎯 <b>Твоя позиция:</b> #{user_position}\n"
            message_text += f"👤 {user_display_name}\n"
            message_text += f"💰 {format_balance(user_balance)}❄️"
        
        return message_text
        
    except Exception as e:
        logging.error(f"Ошибка создания сообщения топа: {e}")
        return "❌ Ошибка загрузки топа. Попробуйте позже."
# =============== КОНЕЦ ФУНКЦИИ ===============

# =============== ФУНКЦИЯ СОЗДАНИЯ КЛАВИАТУРЫ ПАГИНАЦИИ ===============
def create_top_keyboard(user_id, current_page):
    """Создает клавиатуру для навигации по топу"""
    markup = InlineKeyboardMarkup(row_width=3)
    
    # Получаем общее количество страниц
    top_data = get_top_majors_page(current_page, 5)
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
    
    # Кнопка обновления (всегда показываем)
    markup.row(InlineKeyboardButton("🔄 Обновить", callback_data="top_refresh"))
    
    return markup
# =============== КОНЕЦ ФУНКЦИИ ===============

# =============== ОБРАБОТЧИК КОЛБЭКОВ ДЛЯ ТОПА ===============
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
# =============== КОНЕЦ ОБРАБОТЧИКА ===============

# =============== ДОПОЛНИТЕЛЬНАЯ КОМАНДА "МОЙТОП" ===============
@bot.message_handler(func=lambda message: message.text.lower() in ['мойтоп', 'позиция', 'моя позиция', '/мойтоп'])
def handle_my_position(message):
    """Показывает позицию пользователя в топе"""
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
        
        # Получаем позицию пользователя
        cursor.execute('''
        SELECT 
            position,
            CASE 
                WHEN username IS NOT NULL AND username != '' THEN '@' || username 
                ELSE first_name 
            END as display_name,
            balance,
            (SELECT COUNT(*) FROM users WHERE balance > 0 AND is_banned = 0) as total_in_top
        FROM (
            SELECT 
                user_id,
                username,
                first_name,
                balance,
                ROW_NUMBER() OVER (ORDER BY balance DESC) as position
            FROM users 
            WHERE balance > 0 AND is_banned = 0
        ) ranked_users
        WHERE user_id = ?
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        conn.close()
        
        if not user_data:
            bot.send_message(message.chat.id, 
                           "📭 Вы еще не в топе!\n\n"
                           "❄️ Начните зарабатывать снежки:\n"
                           "• 🎰 Казино\n"
                           "• ❄️ Чистка снега\n"
                           "• 🖱️ Кликер\n"
                           "• 🎁 Бонус")
            return
        
        position, display_name, balance, total_in_top = user_data
        
        # Создаем сообщение
        message_text = "🎅 <b>Твоя позиция в топе</b> 🎅\n\n"
        
        # Эмодзи для позиции
        if position == 1:
            medal = "👑"
        elif position == 2:
            medal = "🥈"
        elif position == 3:
            medal = "🥉"
        elif position <= 10:
            medal = "⭐"
        else:
            medal = "🎯"
        
        message_text += f"{medal} <b>Позиция:</b> #{position} из {total_in_top}\n"
        message_text += f"👤 <b>Имя:</b> {display_name}\n"
        message_text += f"💰 <b>Баланс:</b> {format_balance(balance)}❄️\n\n"
        
        # Рекомендации для поднятия в топе
        if position > 10 and total_in_top >= 10:
            # Получаем баланс 10-го места
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT balance FROM (
                    SELECT balance, ROW_NUMBER() OVER (ORDER BY balance DESC) as position
                    FROM users WHERE balance > 0 AND is_banned = 0
                ) WHERE position = 10
            ''')
            tenth_balance_result = cursor.fetchone()
            conn.close()
            
            if tenth_balance_result:
                tenth_balance = tenth_balance_result[0]
                needed = tenth_balance - balance
                if needed > 0:
                    message_text += f"📈 <b>До топ-10 нужно:</b> +{format_balance(needed)}❄️\n\n"
        
        message_text += "🎰 <i>Зарабатывайте больше в казино и работах!</i>"
        
        # Кнопки
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("📊 Весь топ", callback_data="top_page_1"),
            InlineKeyboardButton("🔄 Обновить", callback_data="mypos_refresh")
        )
        
        bot.send_message(message.chat.id, message_text, reply_markup=markup, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в handle_my_position: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки позиции. Попробуйте снова.")
# =============== КОНЕЦ КОМАНДЫ ===============

# =============== ОБРАБОТЧИК ДЛЯ ОБНОВЛЕНИЯ ПОЗИЦИИ ===============
@bot.callback_query_handler(func=lambda call: call.data == 'mypos_refresh')
def mypos_refresh_handler(call):
    """Обновляет информацию о позиции пользователя"""
    try:
        user_id = call.from_user.id
        
        # Просто вызываем обработчик "мойтоп" заново
        class FakeMessage:
            def __init__(self):
                self.chat = type('obj', (object,), {'id': call.message.chat.id})()
                self.from_user = type('obj', (object,), {'id': user_id})()
                self.text = "мойтоп"
        
        fake_message = FakeMessage()
        handle_my_position(fake_message)
        
        bot.answer_callback_query(call.id, "✅ Позиция обновлена!")
        
    except Exception as e:
        logging.error(f"Ошибка в mypos_refresh_handler: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обновления")
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
            message_text += f"❄️ Баланс: ❄️{format_balance(balance)}\n"
            message_text += f"🖥 Видеокарт: {video_cards}\n"
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

# =============== ОБРАБОТЧИК ЧИСТКИ СНЕГА ===============

@bot.message_handler(func=lambda message: message.text == "❄️ Чистка снега")
def handle_snow_work(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Проверяем отдышку
        cursor.execute('SELECT snow_cooldown_end FROM users WHERE user_id = ?', (user_id,))
        cooldown_data = cursor.fetchone()
        
        current_time = datetime.now()
        
        if cooldown_data and cooldown_data[0]:
            cooldown_end = None
            
            if isinstance(cooldown_data[0], str):
                try:
                    cooldown_end = datetime.strptime(cooldown_data[0], '%Y-%m-%d %H:%M:%S')
                except:
                    cooldown_end = None
            elif isinstance(cooldown_data[0], (int, float)):
                cooldown_end = datetime.fromtimestamp(cooldown_data[0])
            
            if cooldown_end and current_time < cooldown_end:
                time_left = (cooldown_end - current_time).seconds
                minutes = time_left // 60
                seconds = time_left % 60
                
                cool_msg = "❄️ Отдышка после работы!\n\n"
                cool_msg += f"⏳ Отдохните еще:\n"
                cool_msg += f"{minutes} минут {seconds} секунд\n\n"
                cool_msg += f"⚡ Можно работать через команду: /snow"
                
                bot.send_message(message.chat.id, cool_msg)
                conn.close()
                return
        
        # Зимние ивентовые места
        winter_territories = [
            {"name": "🏠 Дом Деда Мороза", "icon": "🏠", "desc": "Усадьба волшебника"},
            {"name": "🎅 Мастерская эльфов", "icon": "🎅", "desc": "Место создания подарков"},
            {"name": "❄️ Ледяной дворец", "icon": "❄️", "desc": "Хрустальные покои"},
            {"name": "🦌 Оленья ферма", "icon": "🦌", "desc": "Стойбище северных оленей"},
            {"name": "🎄 Площадь ёлок", "icon": "🎄", "desc": "Главная новогодняя площадь"},
            {"name": "⛸️ Каток желаний", "icon": "⛸️", "desc": "Ледяная арена"},
            {"name": "🏰 Снежная крепость", "icon": "🏰", "desc": "Замок из снега"},
            {"name": "🎁 Фабрика подарков", "icon": "🎁", "desc": "Цех упаковки сюрпризов"},
            {"name": "🌲 Заснеженный лес", "icon": "🌲", "desc": "Волшебная чаща"},
            {"name": "🔥 Котельная гномов", "icon": "🔥", "desc": "Теплое убежище"},
            {"name": "✨ Алмазная пещера", "icon": "✨", "desc": "Сокровищница льда"},
            {"name": "🚂 Полярный экспресс", "icon": "🚂", "desc": "Снежный вокзал"},
            {"name": "🍬 Конфетная фабрика", "icon": "🍬", "desc": "Сладкое производство"},
            {"name": "🎪 Зимний цирк", "icon": "🎪", "desc": "Ледяное шоу"},
            {"name": "🏔️ Ледниковое озеро", "icon": "🏔️", "desc": "Хрустальные воды"}
        ]
        
        territory = random.choice(winter_territories)
        
        # Создаем новую работу
        squares = random.randint(50, 200)
        earnings = squares * 5
        work_duration = 120  # 2 минуты
        
        job_end_time = current_time + timedelta(seconds=work_duration)
        cooldown_end_time = job_end_time + timedelta(seconds=300)  # +5 минут отдышки
        
        cursor.execute('''
            UPDATE users SET 
                current_snow_job = ?,
                snow_job_progress = 0,
                snow_job_total = ?,
                snow_job_end_time = ?,
                snow_cooldown_end = ?,
                last_snow_work = CURRENT_TIMESTAMP,
                snow_territory = ?
            WHERE user_id = ?
        ''', (f"clean_{squares}", squares, job_end_time, cooldown_end_time, territory['name'], user_id))
        
        conn.commit()
        
        # Получаем текущий баланс
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        current_balance = cursor.fetchone()[0]
        
        conn.close()
        
        # Формируем красивое сообщение
        message_text = "❄️ ЧИСТКА СНЕГА\n\n"
        message_text += f"{territory['icon']} Место: {territory['name']}\n"
        message_text += f"📋 {territory['desc']}\n\n"
        message_text += f"📐 Участок: {squares} м²\n"
        message_text += f"💰 Заработок: {earnings}❄️\n"
        message_text += f"⏱️ Время работы: 2 минуты\n"
        message_text += f"⏳ Отдышка: 5 минут\n\n"
        message_text += f"💎 Тариф: 5❄️ за 1 м²\n"
        message_text += f"🎯 Максимум: 200 м² × 5 = 1000❄️\n\n"
        message_text += f"📊 Текущий баланс: {format_balance(current_balance)}❄️\n\n"
        message_text += "Нажми кнопку ниже чтобы начать уборку"
        
        # Создаем кнопку
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❄️ НАЧАТЬ УБОРКУ", callback_data="snow_start"))
        
        bot.send_message(message.chat.id, message_text, reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в handle_snow_work: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка. Попробуйте /snow")

# =============== КОЛБЭК ДЛЯ НАЧАЛА РАБОТЫ ===============

# =============== КОЛБЭК ДЛЯ НАЧАЛА РАБОТЫ ===============

@bot.callback_query_handler(func=lambda call: call.data == "snow_start")
def start_snow_work(call):
    try:
        user_id = call.from_user.id
        
        # Проверяем бан
        banned, reason = is_banned(user_id)
        if banned:
            bot.answer_callback_query(call.id, "🚫 Вы забанены!")
            return
        
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # Получаем данные работы
        cursor.execute('''
            SELECT snow_job_total, snow_job_end_time, snow_territory 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        job_data = cursor.fetchone()
        
        if not job_data or job_data[0] is None or job_data[0] == 0:
            bot.answer_callback_query(call.id, "❌ Работа не найдена!")
            conn.close()
            return
        
        squares = job_data[0]
        
        # Обрабатываем время окончания
        job_end = None
        if job_data[1]:
            if isinstance(job_data[1], str):
                try:
                    job_end = datetime.strptime(job_data[1], '%Y-%m-%d %H:%M:%S')
                except:
                    job_end = datetime.now() + timedelta(seconds=120)  # Дефолт 2 минуты
            elif isinstance(job_data[1], (int, float)):
                job_end = datetime.fromtimestamp(job_data[1])
            else:
                job_end = datetime.now() + timedelta(seconds=120)
        else:
            job_end = datetime.now() + timedelta(seconds=120)
        
        # Обрабатываем территорию
        territory = job_data[2] if job_data[2] else "❄️ Зимняя территория"
        
        current_time = datetime.now()
        
        # Проверяем не закончилось ли время
        if current_time > job_end:
            bot.answer_callback_query(call.id, "⏳ Время вышло!")
            # Очищаем работу
            cursor.execute('''
                UPDATE users SET 
                    current_snow_job = NULL,
                    snow_job_progress = 0,
                    snow_job_total = 0,
                    snow_job_end_time = NULL,
                    snow_territory = NULL
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            conn.close()
            return
        
        # Увеличиваем прогресс
        cursor.execute('UPDATE users SET snow_job_progress = snow_job_progress + 1 WHERE user_id = ?', (user_id,))
        cursor.execute('SELECT snow_job_progress FROM users WHERE user_id = ?', (user_id,))
        progress_result = cursor.fetchone()
        
        if not progress_result:
            bot.answer_callback_query(call.id, "❌ Ошибка прогресса!")
            conn.close()
            return
        
        progress = progress_result[0]
        
        # Если работа завершена
        if progress >= squares:
            earnings = squares * 5
            
            # Начисляем деньги
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (earnings, user_id))
            
            # Очищаем работу
            cursor.execute('''
                UPDATE users SET 
                    current_snow_job = NULL,
                    snow_job_progress = 0,
                    snow_job_total = 0,
                    snow_job_end_time = NULL,
                    snow_territory = NULL
                WHERE user_id = ?
            ''', (user_id,))
            
            conn.commit()
            
            # Получаем новый баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            balance_result = cursor.fetchone()
            new_balance = balance_result[0] if balance_result else 0
            
            conn.close()
            
            # Отправляем результат
            result_text = "✅ РАБОТА ВЫПОЛНЕНА!\n\n"
            result_text += f"{territory}\n\n"
            result_text += f"📐 Очищено: {squares} м²\n"
            result_text += f"💰 Заработано: {earnings}❄️\n"
            result_text += f"📊 Баланс: {format_balance(new_balance)}❄️"
            
            bot.answer_callback_query(call.id, f"✅ +{earnings}❄️")
            
            try:
                bot.edit_message_text(
                    result_text,
                    call.message.chat.id,
                    call.message.message_id
                )
            except:
                # Если не получилось редактировать, ничего страшного
                pass
        else:
            # Работа продолжается
            conn.commit()
            
            # Считаем оставшееся время
            time_left = (job_end - current_time).seconds
            if time_left < 0:
                time_left = 0
                
            minutes_left = time_left // 60
            seconds_left = time_left % 60
            
            # Формируем короткое сообщение с прогрессом
            progress_text = "❄️ ИДЕТ УБОРКА\n\n"
            progress_text += f"{territory}\n\n"
            progress_text += f"📊 {progress}/{squares} м²\n"
            progress_text += f"💰 {progress * 5}❄️\n"
            
            if time_left > 0:
                progress_text += f"⏱️ {minutes_left}:{seconds_left:02d}"
            
            # Создаем новую кнопку
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(f"🗑️ ЧИСТИТЬ ({progress}/{squares})", callback_data="snow_start"))
            
            bot.answer_callback_query(call.id, f"🗑️ +5❄️")
            
            # Обновляем сообщение
            try:
                bot.edit_message_text(
                    progress_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            except Exception as edit_error:
                print(f"Ошибка редактирования сообщения: {edit_error}")
                # Пробуем отправить новое сообщение
                try:
                    bot.send_message(call.message.chat.id, progress_text, reply_markup=markup)
                except:
                    pass
            
            conn.close()
    
    except Exception as e:
        print(f"Ошибка в start_snow_work: {e}")
        import traceback
        traceback.print_exc()  # Печатаем полный трейс ошибки
        
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка!")
        except:
            pass

# =============== КОМАНДА /SNOW ===============

@bot.message_handler(commands=['snow'])
def snow_command(message):
    # Просто вызываем обработчик кнопки
    handle_snow_work(message)
# Обработчик кнопки "👥 Скам"
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
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            ref_code = result[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
            ref_count = cursor.fetchone()[0]
            
            earned = ref_count * 25
            
            ref_link = f"https://t.me/{(bot.get_me()).username}?start={ref_code}"
            
            message_text = f"👨🏻‍💻 Твоя скам-ссылка:\n{ref_link}\n(нажми на неё, чтобы скопировать)\n\n"
            message_text += f"📊 Статистика:\n"
            message_text += f"Заскамлено людей: {ref_count}\n"
            message_text += f"Заработано: ❄️{format_balance(earned)}\n\n"
            message_text += "💡 Кидай ссылку друзьям и скамь их на бабки!"
            
            bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "❌ Реферальный код не найден")
        
        conn.close()
    except Exception as e:
        print(f"Ошибка в handle_scam: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка базы данных. Попробуйте снова.")

# Обработчик кнопки "Топ скам"
@bot.message_handler(func=lambda message: message.text == "Топ скам")
def handle_top_scam(message):
    try:
        if is_spam(message.from_user.id):
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены в боте!\nПричина: {reason}")
            return
            
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT u.first_name, u.username, COUNT(r.user_id) as ref_count
        FROM users u
        JOIN users r ON u.user_id = r.referred_by
        WHERE u.is_banned = 0
        GROUP BY u.user_id
        ORDER BY ref_count DESC
        LIMIT 10
        ''')
        top_scammers = cursor.fetchall()
        
        message_text = "❄️ ТОП СКАМА ❄️\n\n"
        
        if top_scammers:
            medals = ["👑", "🥈", '🥉', "🔰", "🔰", "🔰", "🔰", "🔰", "🔰", "🔰"]
            for i, (first_name, username, ref_count) in enumerate(top_scammers):
                medal = medals[i] if i < len(medals) else "🔰"
                display_name = f"@{username}" if username else first_name
                message_text += f"{medal} {i+1}. {display_name}: {ref_count} скам\n"
        else:
            message_text += "Топ скама пока пуст!\n"
        
        message_text += "\n💡 Скамь друзей и попади в топ!"
        
        bot.send_message(message.chat.id, message_text)
        
        conn.close()
    except Exception as e:
        print(f"Ошибка в handle_top_scam: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка базы данных. Попробуйте снова.")

@bot.message_handler(func=lambda message: message.text in ["Баланс", "б", "/balance"])
def handle_balance(message):
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
        bot.send_message(message.chat.id, f" Ваш баланс: ❄️{format_balance(balance)}")
    except Exception as e:
        print(f"Ошибка в handle_balance: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка базы данных. Попробуйте снова.")



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

• куб/кости [число] [сумма]
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
def get_roulette_photo(winning_number):
    """Найти файл изображения для числа рулетки"""
    # Сначала проверяем в текущей директории
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Форматы файлов для проверки
    formats = ['.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG']
    
    for fmt in formats:
        filename = f"{winning_number}{fmt}"
        filepath = os.path.join(base_dir, filename)
        
        if os.path.exists(filepath):
            print(f"✅ Найден файл: {filename}")
            return filepath
    
    print(f"❌ Файл для числа {winning_number} не найден в {base_dir}")
    
    # Проверяем также без пути
    for fmt in formats:
        filename = f"{winning_number}{fmt}"
        if os.path.exists(filename):
            print(f"✅ Найден файл (относительный путь): {filename}")
            return filename
    
    return None
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
        
        if win:
            win_amount = bet_amount * multiplier
            update_balance(user_id, win_amount)
            new_balance = get_balance(user_id)
            
            # Определяем цвет выпавшего числа для сообщения
            color = "🔴" if winning_number in red_numbers else "⚫" if winning_number in black_numbers else "🟢"
            
            bot.send_message(message.chat.id, 
                           f"🎉 Ставка на {bet_type_name} выиграла!\n"
                           f"🎯 Выпало: {winning_number} {color}\n"
                           f"💰 Вы выиграли ❄️{format_balance(win_amount)}!\n"
                           f"❄️ Баланс: ❄️{format_balance(new_balance)}")
        else:
            new_balance = get_balance(user_id)
            
            # Определяем цвет выпавшего числа для сообщения
            color = "🔴" if winning_number in red_numbers else "⚫" if winning_number in black_numbers else "🟢"
            
            bot.send_message(message.chat.id, 
                           f"❌ Ставка на {bet_type_name} проиграла!\n"
                           f"🎯 Выпало: {winning_number} {color}\n"
                           f"💸 Вы проиграли ❄️{format_balance(bet_amount)}.\n"
                           f"❄️ Баланс: ❄️{format_balance(new_balance)}")
    
    except Exception as e:
        print(f"Ошибка в handle_roulette: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка в игре. Попробуйте снова.")

# Обработчик костей
@bot.message_handler(func=lambda message: message.text.lower().startswith(('куб ', 'кости ')))
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
                f"❄️ Сумма за активацию: ❄️{format_balance(amount)}\n"
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
                f"✅ Админский чек создан!\n"
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
# Обработчик для проверки математической капчи
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
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET captcha_passed = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            # Удаляем капчу из памяти
            if user_id in user_captcha_status:
                del user_captcha_status[user_id]
            
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
        print(f"Ошибка в check_captcha_answer: {e}")
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
CHANNEL_USERNAME = "@FECTIZ"  # Только канал, без чата
BONUS_AMOUNT = 151
BONUS_COOLDOWN = 1800  # 30 минут в секундах

# === ИСПРАВЛЕННЫЙ ОБРАБОТЧИК БОНУСА ===
@bot.message_handler(func=lambda message: message.text.lower() in ['бонус', 'Бонус'])
def handle_bonus(message):
    try:
        if is_spam(message.from_user.id):
            bot.send_message(message.chat.id, "⏳ Слишком быстро! Подождите секунду.")
            return
        
        # Проверяем бан
        banned, reason = is_banned(message.from_user.id)
        if banned:
            bot.send_message(message.chat.id, f"🚫 Вы забанены!\nПричина: {reason}")
            return
            
        user_id = message.from_user.id
        
        # Проверяем подписку только на канал
        try:
            channel_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
            
            channel_ok = channel_member.status in ['member', 'administrator', 'creator']
            
            if not channel_ok:
                # Не подписан - показываем кнопку для подписки
                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")
                )
                markup.row(
                    InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_subs")
                )
                
                error_msg = "🎁 БОНУС\n\n"
                error_msg += "❄️ +121\n"
                error_msg += "🕐 каждые 30 мин\n\n"
                error_msg += "⚠️ Для получения бонуса необходимо:\n"
                error_msg += f"Подписаться на {CHANNEL_USERNAME}\n\n"
                error_msg += f"<a href='https://t.me/{CHANNEL_USERNAME[1:]}'>Нажмите здесь</a> чтобы перейти в канал"
                
                bot.send_message(message.chat.id, error_msg, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
                return
                
        except Exception as e:
            logging.error(f"Ошибка проверки подписки: {e}")
            bot.send_message(message.chat.id, 
                           f"❌ Ошибка проверки подписки.\n"
                           f"Пожалуйста, подпишитесь на канал:\n"
                           f"{CHANNEL_USERNAME}\n\n"
                           f"После подписки попробуйте снова.")
            return
        
        # Подписка есть - проверяем отдышку
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем отдышку
        cursor.execute('SELECT last_bonus, balance FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        current_time = datetime.now()
        can_get_bonus = True
        time_left = 0
        
        if user_data:
            last_bonus, current_balance = user_data
            
            if last_bonus:
                # Преобразуем last_bonus в datetime
                if isinstance(last_bonus, str):
                    try:
                        last_bonus_time = datetime.strptime(last_bonus, '%Y-%m-%d %H:%M:%S')
                    except:
                        last_bonus_time = datetime.now()
                elif isinstance(last_bonus, (int, float)):
                    last_bonus_time = datetime.fromtimestamp(last_bonus)
                else:
                    last_bonus_time = datetime.now()
                
                time_passed = (current_time - last_bonus_time).total_seconds()
                
                if time_passed < BONUS_COOLDOWN:
                    can_get_bonus = False
                    time_left = BONUS_COOLDOWN - int(time_passed)
        
        # Формируем сообщение
        bonus_text = "🎁 БОНУС\n\n"
        bonus_text += "❄️ +121\n"
        bonus_text += "🕐 каждые 30 мин\n\n"
        
        markup = InlineKeyboardMarkup()
        
        if can_get_bonus:
            # Можно получить бонус
            bonus_text += "✅ Подписка проверена\n"
            bonus_text += "✅ Можно забрать бонус"
            
            markup.add(InlineKeyboardButton("🎁 Забрать", callback_data="get_bonus_now"))
        else:
            # Нужно ждать
            minutes = time_left // 60
            seconds = time_left % 60
            
            bonus_text += "✅ Подписка проверена\n"
            bonus_text += f"⏳ Доступно через: {minutes} мин {seconds} сек"
            
            markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_bonus_cooldown"))
        
        # Добавляем кнопку проверки подписки
        markup.add(InlineKeyboardButton("🔍 Проверить подписку", callback_data="check_subs"))
        
        # Показываем текущий баланс
        if user_data:
            bonus_text += f"\n\n💰 Ваш баланс: {format_balance(current_balance)}❄️"
        
        conn.close()
        
        bot.send_message(message.chat.id, bonus_text, reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка в handle_bonus: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка получения бонуса")
# === КОНЕЦ ОБРАБОТЧИКА ===

# === ИСПРАВЛЕННЫЙ КОЛБЭК ДЛЯ ПРОВЕРКИ ПОДПИСКИ ===
@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
def check_subscription_callback(call):
    try:
        user_id = call.from_user.id
        
        # Проверяем подписку только на канал
        try:
            channel_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
            
            channel_ok = channel_member.status in ['member', 'administrator', 'creator']
            
            if channel_ok:
                # Подписка есть
                bot.answer_callback_query(call.id, "✅ Подписка проверена!")
                
                # Проверяем отдышку для обновления сообщения
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute('SELECT last_bonus FROM users WHERE user_id = ?', (user_id,))
                last_bonus_data = cursor.fetchone()
                
                current_time = datetime.now()
                can_get_bonus = True
                time_left = 0
                
                if last_bonus_data and last_bonus_data[0]:
                    last_bonus = last_bonus_data[0]
                    
                    if isinstance(last_bonus, str):
                        try:
                            last_bonus_time = datetime.strptime(last_bonus, '%Y-%m-%d %H:%M:%S')
                        except:
                            last_bonus_time = datetime.now()
                    elif isinstance(last_bonus, (int, float)):
                        last_bonus_time = datetime.fromtimestamp(last_bonus)
                    
                    if last_bonus_time:
                        time_passed = (current_time - last_bonus_time).total_seconds()
                        
                        if time_passed < BONUS_COOLDOWN:
                            can_get_bonus = False
                            time_left = BONUS_COOLDOWN - int(time_passed)
                
                conn.close()
                
                # Формируем обновленное сообщение
                bonus_text = "🎁 БОНУС\n\n"
                bonus_text += "❄️ +121\n"
                bonus_text += "🕐 каждые 30 мин\n\n"
                
                markup = InlineKeyboardMarkup()
                
                if can_get_bonus:
                    bonus_text += "✅ Подписка проверена\n"
                    bonus_text += "✅ Можно забрать бонус"
                    markup.add(InlineKeyboardButton("🎁 Забрать", callback_data="get_bonus_now"))
                else:
                    minutes = time_left // 60
                    seconds = time_left % 60
                    bonus_text += "✅ Подписка проверена\n"
                    bonus_text += f"⏳ Доступно через: {minutes} мин {seconds} сек"
                    markup.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_bonus_cooldown"))
                
                markup.add(InlineKeyboardButton("🔍 Проверить подписку", callback_data="check_subs"))
                
                try:
                    bot.edit_message_text(
                        bonus_text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=markup
                    )
                except:
                    pass
                
            else:
                # Не подписан
                bot.answer_callback_query(call.id, "❌ Нужно подписаться на канал!")
                
                # Обновляем сообщение
                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")
                )
                markup.row(
                    InlineKeyboardButton("🔄 Проверить снова", callback_data="check_subs")
                )
                
                error_msg = "🎁 БОНУС\n\n"
                error_msg += "❄️ +121\n"
                error_msg += "🕐 каждые 30 мин\n\n"
                error_msg += "⚠️ Для получения бонуса необходимо:\n"
                error_msg += f"Подписаться на {CHANNEL_USERNAME}\n\n"
                error_msg += f"Нажмите кнопку ниже чтобы подписаться"
                
                try:
                    bot.edit_message_text(
                        error_msg,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=markup
                    )
                except:
                    pass
                
        except Exception as e:
            logging.error(f"Ошибка проверки подписки в колбэке: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка проверки!")
            
    except Exception as e:
        logging.error(f"Ошибка в check_subscription_callback: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка!")
# === КОНЕЦ КОЛБЭКА ===

# === ИСПРАВЛЕННЫЙ КОЛБЭК ДЛЯ ПОЛУЧЕНИЯ БОНУСА ===
@bot.callback_query_handler(func=lambda call: call.data == "get_bonus_now")
def get_bonus_callback(call):
    try:
        user_id = call.from_user.id
        
        # Сначала проверим подписку (на всякий случай)
        try:
            channel_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
            
            channel_ok = channel_member.status in ['member', 'administrator', 'creator']
            
            if not channel_ok:
                bot.answer_callback_query(call.id, "❌ Нужно подписаться на канал!")
                return
                
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки подписки!")
            return
        
        # Проверяем отдышку
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT last_bonus, balance FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        current_time = datetime.now()
        
        if user_data:
            last_bonus, current_balance = user_data
            
            if last_bonus:
                # Преобразуем last_bonus в datetime
                if isinstance(last_bonus, str):
                    try:
                        last_bonus_time = datetime.strptime(last_bonus, '%Y-%m-%d %H:%M:%S')
                    except:
                        last_bonus_time = datetime.now()
                elif isinstance(last_bonus, (int, float)):
                    last_bonus_time = datetime.fromtimestamp(last_bonus)
                
                if last_bonus_time:
                    time_passed = (current_time - last_bonus_time).total_seconds()
                    
                    if time_passed < BONUS_COOLDOWN:
                        time_left = BONUS_COOLDOWN - int(time_passed)
                        minutes = time_left // 60
                        seconds = time_left % 60
                        
                        bot.answer_callback_query(call.id, f"⏳ Ждите {minutes} мин {seconds} сек")
                        conn.close()
                        return
        
        # Выдаем бонус
        try:
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?,
                    last_bonus = ?
                WHERE user_id = ?
            ''', (BONUS_AMOUNT, current_time, user_id))
            
            conn.commit()
            
            # Получаем новый баланс
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            new_balance_result = cursor.fetchone()
            new_balance = new_balance_result[0] if new_balance_result else (current_balance if current_balance else 0)
            
            conn.close()
            
            bot.answer_callback_query(call.id, f"✅ +{BONUS_AMOUNT}❄️")
            
            # Показываем результат
            bonus_msg = "✨ БОНУС ПОЛУЧЕН! ✨\n\n"
            bonus_msg += "🎉 Поздравляем с получением бонуса!\n\n"
            bonus_msg += f"💎 Начислено: {BONUS_AMOUNT}❄️\n"
            bonus_msg += f"📊 Ваш баланс: {format_balance(new_balance)}❄️\n\n"
            bonus_msg += f"⏰ Следующий бонус через 30 минут\n\n"
            bonus_msg += f"📢 Канал: {CHANNEL_USERNAME}"
            
            try:
                bot.edit_message_text(
                    bonus_msg,
                    call.message.chat.id,
                    call.message.message_id
                )
            except Exception as edit_error:
                # Если не удалось редактировать, отправляем новое сообщение
                bot.send_message(call.message.chat.id, bonus_msg)
                logging.info(f"Бонус выдан пользователю {user_id}: +{BONUS_AMOUNT}❄️")
            
        except Exception as e:
            logging.error(f"Ошибка выдачи бонуса: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка выдачи бонуса!")
            if conn:
                conn.rollback()
                conn.close()
            
    except Exception as e:
        logging.error(f"Ошибка в get_bonus_callback: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка получения бонуса!")
        except:
            pass
# === КОНЕЦ КОЛБЭКА ===
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

@bot.message_handler(content_types=['document'], func=lambda message: is_admin(message.from_user.id))
def handle_db_document(message):
    try:
        if message.document.file_name != 'game.db':
            bot.send_message(message.chat.id, "❌ Файл должен называться game.db")
            return
            
        bot.send_message(message.chat.id, "⏳ Загружаю и проверяю базу данных...")
        
        # Скачиваем файл
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем как временный файл
        temp_filename = f"temp_game_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        with open(temp_filename, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Проверяем структуру
        try:
            test_conn = sqlite3.connect(temp_filename)
            test_cursor = test_conn.cursor()
            
            # Проверяем основные таблицы
            test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not test_cursor.fetchone():
                raise Exception("Нет таблицы users")
                
            test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checks'")
            if not test_cursor.fetchone():
                raise Exception("Нет таблицы checks")
            
            test_cursor.execute("SELECT COUNT(*) FROM users")
            users_count = test_cursor.fetchone()[0]
            
            test_conn.close()
            
        except Exception as e:
            os.remove(temp_filename)
            bot.send_message(message.chat.id, f"❌ Неверный формат базы: {e}")
            return
        
        # Делаем бэкап старой базы (если она существует)
        backup_name = None
        if os.path.exists('game.db'):
            backup_name = f"backup_before_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2('game.db', backup_name)
            logging.info(f"Создан бэкап: {backup_name}")
        
        # Заменяем базу
        os.replace(temp_filename, 'game.db')
        
        # Переинициализируем базу
        init_db()
        
        response_msg = f"✅ База данных обновлена!\n👥 Пользователей: {users_count}\n"
        
        if backup_name:
            response_msg += f"💾 Бэкап сохранен как: {backup_name}\n"
        
        response_msg += "\n🔄 Бот продолжит работу с новой базой"
        
        bot.send_message(message.chat.id, response_msg)
        
    except Exception as e:
        logging.error(f"Ошибка загрузки базы: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:200]}")
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
        
        # Создаем копию базы данных
        backup_filename = f"game_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        # Копируем файл с помощью shutil
        shutil.copy2('game.db', backup_filename)
        
        # Отправляем файл
        with open(backup_filename, 'rb') as db_file:
            bot.send_document(
                message.chat.id, 
                db_file, 
                caption=f"📦 База данных\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
        
        # Удаляем временный файл
        os.remove(backup_filename)
        
        # Статистика
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM checks')
        checks_count = cursor.fetchone()[0]
        conn.close()
        
        bot.send_message(message.chat.id, 
                       f"✅ База данных отправлена\n"
                       f"👥 Пользователей: {users_count}\n"
                       f"💳 Чеков: {checks_count}\n"
                       f"💾 Размер: {os.path.getsize('game.db') / 1024:.1f} KB")
        
    except Exception as e:
        logging.error(f"Ошибка скачивания базы: {e}")
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
                    click_power = 1,
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
    print("Бот запущен...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        print("Перезапустите бота.")