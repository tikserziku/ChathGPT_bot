import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
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
        conn.commit()

def add_user(user_id, unique_link):
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute('''
                INSERT INTO users (user_id, unique_link, access_granted)
                VALUES (%s, %s, %s)
                ''', (user_id, unique_link, True))
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                conn.rollback()
                return False

def check_access(user_id):
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
                    if datetime.now() - created_at > timedelta(days=30):
                        cur.execute('''
                        UPDATE users SET access_granted = %s 
                        WHERE user_id = %s
                        ''', (False, user_id))
                        conn.commit()
                        return False
                    return True
    return False

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
        await update.message.reply_text("Пожалуйста, используйте команду /start с уникальной ссылкой.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if check_access(user.id):
        message = update.message.text
        if message.lower().startswith("нарисуй"):
            await generate_image(update, context)
        else:
            await chat_with_gpt(update, context)
    else:
        await update.message.reply_text("Извините, ваш доступ истек или не активирован.")

async def chat_with_gpt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": message})

    try:
        trimmed_history = trim_chat_history(conversation_history[user_id])

        response = openai.ChatCompletion.create(
            model="chatgpt-4o-latest",  # Using GPT-4
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

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == '__main__':
    main()
