from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
from datetime import datetime, timedelta
import sqlite3
import os
import pytz

# Определяем путь к базе данных
DB_PATH = os.path.join(os.getenv('DATA_DIR', ''), 'water_bot.db')

def init_database():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE water_intake (
                user_id INTEGER,
                amount INTEGER,
                timestamp DATETIME,
                PRIMARY KEY (user_id, timestamp)
            )
        ''')
        cursor.execute('''
            CREATE TABLE reminders (
                user_id INTEGER PRIMARY KEY,
                start_time TEXT,
                end_time TEXT,
                interval INTEGER,
                is_active BOOLEAN
            )
        ''')
        conn.commit()
        conn.close()

def add_water_record(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO water_intake (user_id, amount, timestamp)
        VALUES (?, ?, ?)
    ''', (user_id, amount, datetime.now()))
    conn.commit()
    conn.close()

def get_statistics(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.now().date()
    cursor.execute('''
        SELECT SUM(amount)
        FROM water_intake
        WHERE user_id = ? AND date(timestamp) = ?
    ''', (user_id, today))
    today_amount = cursor.fetchone()[0] or 0
    week_ago = today - timedelta(days=7)
    cursor.execute('''
        SELECT date(timestamp), SUM(amount)
        FROM water_intake
        WHERE user_id = ? AND date(timestamp) > ?
        GROUP BY date(timestamp)
        ORDER BY date(timestamp)
    ''', (user_id, week_ago))
    weekly_data = cursor.fetchall()
    conn.close()
    return today_amount, weekly_data

def set_reminder_settings(user_id: int, start_time: str, end_time: str, interval: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO reminders 
        (user_id, start_time, end_time, interval, is_active)
        VALUES (?, ?, ?, ?, TRUE)
    ''', (user_id, start_time, end_time, interval))
    conn.commit()
    conn.close()

def get_reminder_settings(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT start_time, end_time, interval, is_active FROM reminders WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_water_keyboard():
    keyboard = [
        ['☕️ 200 мл', '🥤 300 мл', '🫗 500 мл'],
        ['📊 Статистика за сегодня', '📈 Статистика за неделю'],
        ['⏰ Настроить напоминания', '🔕 Отключить напоминания']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def format_weekly_stats(weekly_data):
    if not weekly_data:
        return "За последнюю неделю нет данных о выпитой воде."
    total = 0
    days_count = 0
    result = "📈 Статистика за последние 7 дней:\n\n"
    for date_str, amount in weekly_data:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        day_name = date.strftime('%A')
        total += amount
        days_count += 1
        result += f"{day_name}: {amount} мл\n"
    average = total // days_count if days_count > 0 else 0
    result += f"\nСреднее количество: {average} мл в день"
    return result

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data['user_id']
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.now(moscow_tz).time()
    settings = get_reminder_settings(user_id)
    if not settings:
        return
    start_time = datetime.strptime(settings[0], '%H:%M').time()
    end_time = datetime.strptime(settings[1], '%H:%M').time()
    if start_time <= current_time <= end_time:
        today_amount, _ = get_statistics(user_id)
        await context.bot.send_message(
            user_id,
            f'🚰 Время пить воду! Сегодня вы выпили: {today_amount} мл\n'
            f'Рекомендуемая норма: 2000 мл в день'
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.from_user.first_name
    await update.message.reply_text(
        f'Привет, {name}! 👋\n'
        'Я бот для подсчета выпитой воды! 💧\n'
        'Выбери количество выпитой воды или введи вручную (например, "200" или "250 мл")\n\n'
        'Для настройки напоминаний используй команду /remind или кнопку "⏰ Настроить напоминания"',
        reply_markup=get_water_keyboard()
    )

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        start_time = context.args[0]
        end_time = context.args[1]
        interval = int(context.args[2])
        if interval < 30:
            await update.message.reply_text('Минимальный интервал - 30 минут!')
            return
        user_id = update.message.from_user.id
        set_reminder_settings(user_id, start_time, end_time, interval)
        current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
        for job in current_jobs:
            job.schedule_removal()
        context.job_queue.run_repeating(
            send_reminder,
            interval=interval * 60,
            first=1,
            name=str(user_id),
            data={'user_id': user_id}
        )
        await update.message.reply_text(
            f'Напоминания настроены!\n'
            f'Время: с {start_time} до {end_time}\n'
            f'Интервал: {interval} минут'
        )
    except (IndexError, ValueError):
        await update.message.reply_text(
            'Используйте формат:\n/remind 09:00 22:00 120'
        )

async def handle_water_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if text == '📊 Статистика за сегодня':
        today_amount, _ = get_statistics(user_id)
        await update.message.reply_text(
            f'Сегодня ты выпил: {today_amount} мл воды 💧\n'
            f'{"👍 Отличный результат!" if today_amount >= 2000 else "Не забывай пить больше воды! 💪"}',
            reply_markup=get_water_keyboard()
        )
        return
    
    elif text == '📈 Статистика за неделю':
        _, weekly_data = get_statistics(user_id)
        stats_message = format_weekly_stats(weekly_data)
        await update.message.reply_text(
            stats_message,
            reply_markup=get_water_keyboard()
        )
        return
    
    elif text == '⏰ Настроить напоминания':
        await update.message.reply_text(
            'Для настройки напоминаний, отправьте команду в формате:\n'
            '/remind 09:00 22:00 120\n'
            'где:\n'
            '09:00 - время начала напоминаний\n'
            '22:00 - время окончания напоминаний\n'
            '120 - интервал в минутах между напоминаниями'
        )
        return
    
    elif text == '🔕 Отключить напоминания':
        current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
        for job in current_jobs:
            job.schedule_removal()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE reminders SET is_active = FALSE WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text('Напоминания отключены!')
        return

    try:
        if '200' in text:
            amount = 200
        elif '300' in text:
            amount = 300
        elif '500' in text:
            amount = 500
        else:
            amount = int(''.join(filter(str.isdigit, text)))
        
        if amount <= 0 or amount > 2000:
            raise ValueError("Некорректное количество воды")

        add_water_record(user_id, amount)
        today_amount, _ = get_statistics(user_id)

        await update.message.reply_text(
            f'Добавлено {amount} мл воды! 💧\n'
            f'Всего за сегодня: {today_amount} мл',
            reply_markup=get_water_keyboard()
        )

    except (ValueError, TypeError):
        await update.message.reply_text(
            'Пожалуйста, введи корректное количество миллилитров (например, "200" или нажмите на кнопку)',
            reply_markup=get_water_keyboard()
        )

def main():
    print('Запускаем бота...')
    init_database()
    app = Application.builder().token('7832116453:AAELa5zby6f3Tld8yqLmnftsdAtsmHoZ9lU').build()
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('remind', remind_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_water_input))
    print('Бот запущен!')
    app.run_polling()

if __name__ == '__main__':
    main()
