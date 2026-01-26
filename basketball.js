// Конфигурация
const CONFIG = {
    apiUrl: window.location.origin, // Автоматически определяет домен
    user_id: null,
    token: null,
    power: 50,
    isCharging: false,
    powerInterval: null,
    currentStreak: 0,
    sessionEarned: 0
};

// DOM элементы
const elements = {
    playerName: document.getElementById('player-name'),
    balance: document.getElementById('balance'),
    powerFill: document.getElementById('power-fill'),
    powerValue: document.getElementById('power-value'),
    chargeBtn: document.getElementById('charge-btn'),
    shootBtn: document.getElementById('shoot-btn'),
    ball: document.getElementById('ball'),
    hoop: document.getElementById('hoop'),
    streak: document.getElementById('streak'),
    lastResult: document.getElementById('last-result'),
    earned: document.getElementById('earned'),
    dailyTop: document.getElementById('daily-top'),
    message: document.getElementById('message')
};

// Инициализация игры
async function initGame() {
    console.log('🎮 Инициализация игры...');
    
    // Получаем параметры из URL
    const urlParams = new URLSearchParams(window.location.search);
    CONFIG.user_id = urlParams.get('user_id');
    CONFIG.token = urlParams.get('token');
    
    if (!CONFIG.user_id || !CONFIG.token) {
        showError('❌ Неверная ссылка. Запустите игру через бота.');
        return;
    }
    
    try {
        // Загружаем данные пользователя
        const response = await fetch(`${CONFIG.apiUrl}/api/init`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_id: CONFIG.user_id,
                token: CONFIG.token
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Обновляем интерфейс
            elements.playerName.textContent = data.user.name;
            elements.balance.textContent = data.user.balance.toLocaleString();
            
            if (data.stats) {
                CONFIG.currentStreak = data.stats.current_streak;
                elements.streak.textContent = CONFIG.currentStreak;
                elements.earned.textContent = data.stats.earned.toLocaleString() + ' ❄️';
            }
            
            if (data.daily_top) {
                elements.dailyTop.innerHTML = `
                    🏆 <strong>${data.daily_top.name}</strong><br>
                    ⭐ ${data.daily_top.score} очков<br>
                    💰 Приз: 10.000 ❄️
                `;
            }
            
            console.log('✅ Игра загружена!');
            setupControls();
            
        } else {
            showError('❌ Ошибка: ' + (data.error || 'Неизвестная ошибка'));
        }
        
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        showError('❌ Не удалось подключиться к серверу');
    }
}

// Настройка управления
function setupControls() {
    // Кнопка зарядки
    elements.chargeBtn.addEventListener('mousedown', startCharging);
    elements.chargeBtn.addEventListener('touchstart', startCharging);
    
    elements.chargeBtn.addEventListener('mouseup', stopCharging);
    elements.chargeBtn.addEventListener('touchend', stopCharging);
    
    // Кнопка броска
    elements.shootBtn.addEventListener('click', shoot);
    
    // Мяч (альтернативный клик)
    elements.ball.addEventListener('click', () => {
        if (CONFIG.power > 20) {
            shoot();
        }
    });
}

// Начало зарядки
function startCharging() {
    if (CONFIG.isCharging) return;
    
    CONFIG.isCharging = true;
    CONFIG.power = 0;
    
    // Виброотклик
    if (navigator.vibrate) navigator.vibrate(30);
    
    // Зарядка
    CONFIG.powerInterval = setInterval(() => {
        if (CONFIG.isCharging && CONFIG.power < 100) {
            CONFIG.power += 2;
            updatePowerDisplay();
        }
    }, 50);
    
    elements.chargeBtn.textContent = '⚡ ЗАРЯЖАЕТСЯ...';
    elements.shootBtn.disabled = false;
}

// Остановка зарядки
function stopCharging() {
    if (!CONFIG.isCharging) return;
    
    CONFIG.isCharging = false;
    clearInterval(CONFIG.powerInterval);
    elements.chargeBtn.textContent = '⚡ ЗАРЯДИТЬ';
}

// Обновление индикатора силы
function updatePowerDisplay() {
    elements.powerFill.style.width = CONFIG.power + '%';
    elements.powerValue.textContent = CONFIG.power + '%';
}

// Бросок мяча
async function shoot() {
    if (CONFIG.isCharging || CONFIG.power < 10) {
        showMessage('⚡ Сначала зарядите бросок!');
        return;
    }
    
    // Блокируем кнопки
    elements.chargeBtn.disabled = true;
    elements.shootBtn.disabled = true;
    
    // Анимация броска
    animateShot();
    
    // Виброотклик
    if (navigator.vibrate) navigator.vibrate(100);
    
    // Расчёт попадания (чем больше сила - выше шанс)
    const hitChance = 30 + (CONFIG.power * 0.5); // От 30% до 80%
    const isHit = Math.random() * 100 < hitChance;
    
    // Отправляем результат на сервер
    try {
        const response = await fetch(`${CONFIG.apiUrl}/api/shoot`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_id: CONFIG.user_id,
                token: CONFIG.token,
                hit: isHit,
                power: CONFIG.power
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Обновляем данные
            CONFIG.currentStreak = data.result.new_streak;
            CONFIG.sessionEarned += data.result.earned;
            
            // Обновляем интерфейс
            elements.balance.textContent = data.result.new_balance.toLocaleString();
            elements.streak.textContent = CONFIG.currentStreak;
            elements.earned.textContent = CONFIG.sessionEarned.toLocaleString() + ' ❄️';
            
            // Показываем результат
            if (isHit) {
                elements.lastResult.innerHTML = '✅ ПОПАДАНИЕ!';
                elements.lastResult.style.color = '#4cd137';
                
                if (data.result.earned > 0) {
                    showMessage(`🎯 Отлично! +${data.result.earned} ❄️`);
                }
            } else {
                elements.lastResult.innerHTML = '❌ ПРОМАХ';
                elements.lastResult.style.color = '#ff3838';
            }
            
        } else {
            showError('❌ Ошибка сервера: ' + data.error);
        }
        
    } catch (error) {
        console.error('Ошибка броска:', error);
        showError('❌ Ошибка соединения');
    }
    
    // Сброс
    setTimeout(() => {
        CONFIG.power = 50;
        updatePowerDisplay();
        resetBall();
        
        elements.chargeBtn.disabled = false;
        elements.shootBtn.disabled = false;
        elements.lastResult.innerHTML = '-';
        elements.lastResult.style.color = '#ffcc00';
    }, 1500);
}

// Анимация броска
function animateShot() {
    elements.ball.style.animation = 'shoot 0.5s forwards';
    
    // Через 0.5с показываем результат
    setTimeout(() => {
        // Здесь можно добавить анимацию попадания/промаха
    }, 500);
}

// Сброс мяча
function resetBall() {
    elements.ball.style.animation = 'none';
    setTimeout(() => {
        elements.ball.style.animation = '';
    }, 10);
}

// Показать сообщение
function showMessage(text) {
    elements.message.textContent = text;
    elements.message.style.display = 'block';
    
    setTimeout(() => {
        elements.message.style.display = 'none';
    }, 3000);
}

// Показать ошибку
function showError(text) {
    elements.message.textContent = text;
    elements.message.style.background = 'rgba(255, 56, 56, 0.9)';
    elements.message.style.display = 'block';
}

// Запуск игры при загрузке
window.addEventListener('DOMContentLoaded', initGame);
