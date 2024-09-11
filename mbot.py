import os
import logging
import uuid
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load tokens from environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')

# Initialize OpenAI
openai.api_key = OPENAI_API_KEY

# Dictionary to store conversation history
conversation_history = {}

# Maximum number of tokens for the request
MAX_TOKENS = 4000

# Database functions
def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                unique_link TEXT UNIQUE,
                access_granted BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            cur.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE
            )''')
            cur.execute('''
            CREATE TABLE IF NOT EXISTS invitation_links (
                id SERIAL PRIMARY KEY,
                link TEXT UNIQUE,
                is_used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
        conn.commit()

def generate_unique_link():
    return str(uuid.uuid4())

def add_invitation_link():
    link = generate_unique_link()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
            INSERT INTO invitation_links (link) VALUES (%s)
            ''', (link,))
        conn.commit()
    return link

def get_unused_links():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
            SELECT link FROM invitation_links WHERE is_used = FALSE
            ''')
            return [row[0] for row in cur.fetchall()]

def mark_link_as_used(link):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
            UPDATE invitation_links SET is_used = TRUE WHERE link = %s
            ''', (link,))
        conn.commit()

def add_user(user_id, unique_link):
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute('''
                INSERT INTO users (user_id, unique_link, access_granted)
                VALUES (%s, %s, %s)
                ''', (user_id, unique_link, True))
                mark_link_as_used(unique_link)
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                conn.rollback()
                return False

def check_access(user_id):
    if is_admin(user_id):
        return True, -1  # Админы всегда имеют доступ

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
            SELECT access_granted, created_at FROM users 
            WHERE user_id = %s
            ''', (user_id,))
            result = cur.fetchone()
            if result:
                access_granted, created_at = result
                if access_granted:
                    time_passed = datetime.now() - created_at
                    if time_passed > timedelta(days=30):
                        cur.execute('''
                        UPDATE users SET access_granted = %s 
                        WHERE user_id = %s
                        ''', (False, user_id))
                        conn.commit()
                        return False, 0
                    return True, 30 - time_passed.days
            return False, -1

def is_admin(user_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM admins WHERE user_id = %s', (user_id,))
            return cur.fetchone() is not None

def add_admin(user_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute('INSERT INTO admins (user_id) VALUES (%s)', (user_id,))
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                conn.rollback()
                return False

def remove_admin(user_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM admins WHERE user_id = %s', (user_id,))
            return cur.rowcount > 0

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if context.args and len(context.args) > 0:
        unique_link = context.args[0]
        if add_user(user.id, unique_link):
            await update.message.reply_text(f"Добро пожаловать, {user.mention_html()}! Ваш доступ активирован на 1 месяц.")
        else:
            await update.message.reply_text("Извините, эта ссылка уже использована или недействительна.")
    else:
        await update.message.reply_text("Пожалуйста, используйте команду /start с уникальной ссылкой для активации доступа.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    access_granted, days_left = check_access(user.id)
    if access_granted:
        message = update.message.text
        if message.lower().startswith("нарисуй"):
            await generate_image(update, context)
        else:
            await chat_with_gpt(update, context)
        if days_left > 0 and days_left <= 5:
            await update.message.reply_text(f"Внимание! У вас осталось {days_left} дней доступа.")
    elif days_left == 0:
        await update.message.reply_text("Извините, ваш доступ истек. Пожалуйста, обратитесь к администратору для продления.")
    else:
        await update.message.reply_text("Доступ не активирован. Используйте команду /start с уникальной ссылкой для активации.")

async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": message})

    try:
        trimmed_history = trim_chat_history(conversation_history[user_id])

        response = openai.ChatCompletion.create(
            model="gpt-4",  # Using GPT-4
            messages=trimmed_history
        )

        chatgpt_response = response.choices[0].message['content']

        conversation_history[user_id].append({"role": "assistant", "content": chatgpt_response})

        conversation_history[user_id] = conversation_history[user_id][-10:]

        await update.message.reply_text(chatgpt_response)

    except Exception as e:
        logger.error(f"Error in ChatGPT request: {e}")
        await update.message.reply_text("Извините, произошла ошибка при обработке вашего запроса.")

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prompt = update.message.text[7:].strip()
    
    if not prompt:
        await update.message.reply_text("Пожалуйста, укажите, что нарисовать после слова 'нарисуй'.")
        return

    try:
        response = openai.Image.create(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024"
        )

        image_url = response['data'][0]['url']

        await update.message.reply_photo(image_url, caption=f"Вот изображение по запросу: {prompt}")

    except Exception as e:
        logger.error(f"Error in image generation: {e}")
        await update.message.reply_text("Извините, произошла ошибка при генерации изображения.")

def trim_chat_history(history: list) -> list:
    while len(str(history)) > MAX_TOKENS:
        if len(history) > 1:
            history.pop(1)
        else:
            break
    return history

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        if context.args and len(context.args) > 0:
            new_admin_id = int(context.args[0])
            if add_admin(new_admin_id):
                await update.message.reply_text(f"Пользователь {new_admin_id} добавлен как администратор.")
            else:
                await update.message.reply_text("Не удалось добавить администратора. Возможно, он уже существует.")
        else:
            await update.message.reply_text("Пожалуйста, укажите ID пользователя для добавления в администраторы.")
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        if context.args and len(context.args) > 0:
            admin_id = int(context.args[0])
            if remove_admin(admin_id):
                await update.message.reply_text(f"Администратор {admin_id} удален.")
            else:
                await update.message.reply_text("Не удалось удалить администратора. Возможно, его не существует.")
        else:
            await update.message.reply_text("Пожалуйста, укажите ID администратора для удаления.")
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")

async def generate_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        link = add_invitation_link()
        full_link = f"https://t.me/{context.bot.username}?start={link}"
        await update.message.reply_text(f"Новая уникальная ссылка создана: {full_link}")
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")

async def list_links_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        unused_links = get_unused_links()
        if unused_links:
            message = "Неиспользованные ссылки:\n"
            for link in unused_links:
                full_link = f"https://t.me/{context.bot.username}?start={link}"
                message += f"{full_link}\n"
            await update.message.reply_text(message)
        else:
            await update.message.reply_text("Нет неиспользованных ссылок.")
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")

def main() -> None:
    init_db()  # Initialize the database
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    application.add_handler(CommandHandler("generate_link", generate_link_command))
    application.add_handler(CommandHandler("list_links", list_links_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Настройка логгера для скрытия токена
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    application.run_polling()

if __name__ == '__main__':
    main()
