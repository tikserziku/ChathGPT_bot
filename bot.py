import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import openai
import time
import random

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка токенов из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Инициализация чата
chat_history = []
MAX_EXCHANGES = 5  # Максимальное количество обменов репликами

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Привет! Я бот, который имитирует диалог между Сократом и Кантом. Напиши тему для обсуждения, и я начну диалог.')

def handle_topic(update: Update, context: CallbackContext) -> None:
    topic = update.message.text
    update.message.reply_text(f"Начинаем диалог на тему: {topic}")
    
    global chat_history
    chat_history = [{"role": "system", "content": f"Вы участвуете в философском диалоге между Сократом и Кантом на тему '{topic}'. Сократ начинает диалог."}]
    
    generate_dialogue(update, context)

def generate_dialogue(update: Update, context: CallbackContext) -> None:
    for i in range(MAX_EXCHANGES):
        # Сократ говорит
        socrates_message = generate_philosopher_message("Сократ", chat_history)
        update.message.reply_text(f"Сократ: {socrates_message}")
        chat_history.append({"role": "assistant", "content": f"Сократ: {socrates_message}"})
        time.sleep(random.uniform(1, 3))  # Пауза между сообщениями

        # Кант отвечает
        kant_message = generate_philosopher_message("Кант", chat_history)
        update.message.reply_text(f"Кант: {kant_message}")
        chat_history.append({"role": "assistant", "content": f"Кант: {kant_message}"})
        time.sleep(random.uniform(1, 3))  # Пауза между сообщениями

    update.message.reply_text("Диалог завершен. Если хотите начать новый, просто отправьте новую тему.")

def generate_philosopher_message(philosopher: str, history: list) -> str:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=history + [{"role": "user", "content": f"Теперь ты {philosopher}. Ответь в своем философском стиле, продолжая диалог."}],
            max_tokens=150
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        logger.error(f"Error in generating message for {philosopher}: {e}")
        return f"Извините, произошла ошибка при генерации ответа для {philosopher}."

def main() -> None:
    updater = Updater(TELEGRAM_TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_topic))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
