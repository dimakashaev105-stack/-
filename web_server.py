from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import hashlib
import time
from datetime import datetime
import os

app = Flask(__name__)

# Секретный ключ (такой же как в bot.py)
SECRET_KEY = "basketball_bot_secret_key_2024_change_this"

def check_token(user_id, token):
    """Проверяет токен пользователя"""
    try:
        conn = sqlite3.connect('game.db')
        c = conn.cursor()
        c.execute('SELECT username FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        conn.close()
        
        if not user:
            return False
        
        username = user[0] or str(user_id)
        timestamp = int(time.time())
        
        # Проверяем несколько возможных токенов (за последние 5 минут)
        for t in range(timestamp - 300, timestamp + 1):
            data = f"{user_id}:{username}:{t}:{SECRET_KEY}"
            expected = hashlib.sha256(data.encode()).hexdigest()[:20]
            if token == expected:
                return True
                
        return False
    except:
        return False

# === API ДЛЯ МИНИ-ПРИЛОЖЕНИЯ ===

@app.route('/basketball')
def serve_game():
    """Отдает HTML страницу игры"""
    return send_from_directory('.', 'basketball.html')

@app.route('/basketball.js')
def serve_js():
    return send_from_directory('.', 'basketball.js')

@app.route('/basketball.css')
def serve_css():
    return send_from_directory('.', 'basketball.css')

@app.route('/api/init', methods=['POST'])
def api_init():
    """Инициализация игры - проверка пользователя"""
    try:
        data = request.json
        user_id = data.get('user_id')
        token = data.get('token')
        
        if not user_id or not token:
            return jsonify({"error": "Нет данных"}), 400
        
        if not check_token(user_id, token):
            return jsonify({"error": "Неверный токен"}), 403
        
        conn = sqlite3.connect('game.db')
        c = conn.cursor()
        
        # Данные пользователя
        c.execute('SELECT username, balance FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        
        # Статистика
        c.execute('SELECT * FROM basketball_stats WHERE user_id = ?', (user_id,))
        stats = c.fetchone()
        
        # Топ дня
        c.execute('''
            SELECT u.username, SUM(bd.score) as score 
            FROM basketball_daily bd
            JOIN users u ON bd.user_id = u.user_id
            WHERE bd.date = DATE('now')
            GROUP BY bd.user_id
            ORDER BY score DESC
            LIMIT 1
        ''')
        daily_top = c.fetchone()
        
        conn.close()
        
        response = {
            "success": True,
            "user": {
                "id": user_id,
                "name": user[0] if user else f"Игрок {user_id}",
                "balance": user[1] if user else 0
            },
            "stats": {
                "hits": stats[1] if stats else 0,
                "misses": stats[2] if stats else 0,
                "best_streak": stats[3] if stats else 0,
                "current_streak": stats[4] if stats else 0,
                "earned": stats[5] if stats else 0
            } if stats else None,
            "daily_top": {
                "name": daily_top[0] if daily_top else "Нет",
                "score": daily_top[1] if daily_top else 0
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/shoot', methods=['POST'])
def api_shoot():
    """Обработка броска"""
    try:
        data = request.json
        user_id = data.get('user_id')
        token = data.get('token')
        is_hit = data.get('hit', False)
        power = data.get('power', 50)  # Сила 0-100
        
        if not user_id or not token:
            return jsonify({"error": "Нет данных"}), 400
        
        if not check_token(user_id, token):
            return jsonify({"error": "Неверный токен"}), 403
        
        conn = sqlite3.connect('game.db')
        c = conn.cursor()
        
        # Получаем текущую статистику
        c.execute('SELECT * FROM basketball_stats WHERE user_id = ?', (user_id,))
        stats = c.fetchone()
        
        current_streak = stats[4] if stats else 0
        total_hits = stats[1] if stats else 0
        total_misses = stats[2] if stats else 0
        best_streak = stats[3] if stats else 0
        
        earned = 0
        
        if is_hit:
            # ПОПАДАНИЕ
            total_hits += 1
            current_streak += 1
            
            # Базовая награда
            base = 25
            
            # Бонус за силу
            power_bonus = int((power / 100) * 15)
            
            # Бонус за серию
            streak_bonus = current_streak * 10
            
            earned = base + power_bonus + streak_bonus
            
            # Обновляем баланс
            c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (earned, user_id))
            
            # Обновляем рекорд
            if current_streak > best_streak:
                best_streak = current_streak
        else:
            # ПРОМАХ
            total_misses += 1
            current_streak = 0
        
        # Сохраняем статистику
        if stats:
            c.execute('''
                UPDATE basketball_stats SET
                    total_hits = ?,
                    total_misses = ?,
                    best_streak = ?,
                    current_streak = ?,
                    total_earned = total_earned + ?,
                    last_played = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (total_hits, total_misses, best_streak, current_streak, earned, user_id))
        else:
            c.execute('''
                INSERT INTO basketball_stats 
                (user_id, total_hits, total_misses, best_streak, current_streak, total_earned)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, total_hits, total_misses, best_streak, current_streak, earned))
        
        # Записываем в дневную статистику
        c.execute('''
            INSERT INTO basketball_daily (user_id, score, earned)
            VALUES (?, ?, ?)
        ''', (user_id, 1 if is_hit else 0, earned))
        
        # Новый баланс
        c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        new_balance = c.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "result": {
                "hit": is_hit,
                "earned": earned,
                "new_streak": current_streak,
                "new_balance": new_balance
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "🏀 Telegram Basketball Bot работает! 🎯"

if __name__ == '__main__':
    print("🌐 Веб-сервер запускается...")
    print("📁 Файлы игры: /basketball")
    print("🔧 API: /api/init и /api/shoot")
    app.run(host='0.0.0.0', port=5000, debug=False)
