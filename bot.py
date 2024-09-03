import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import openai

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка токенов из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Словарь для хранения истории разговоров
conversation_history = {}

def start(update: Update, context: CallbackContext) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    update.message.reply_text('Привет! Я бот, который может общаться с помощью ChatGPT. Просто напиши мне что-нибудь!')

def handle_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает входящие сообщения и отправляет их в ChatGPT."""
    user_id = update.effective_user.id
    message = update.message.text

    # Получаем историю разговора для данного пользователя
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Добавляем сообщение пользователя в историю
    conversation_history[user_id].append({"role": "user", "content": message})

    try:
        # Отправляем запрос к ChatGPT
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=conversation_history[user_id]
        )

        # Получаем ответ от ChatGPT
        chatgpt_response = response.choices[0].message['content']

        # Добавляем ответ ChatGPT в историю
        conversation_history[user_id].append({"role": "assistant", "content": chatgpt_response})

        # Ограничиваем историю последними 10 сообщениями, чтобы избежать превышения лимитов токенов
        conversation_history[user_id] = conversation_history[user_id][-10:]

        # Отправляем ответ пользователю
        update.message.reply_text(chatgpt_response)

    except Exception as e:
        logger.error(f"Error in ChatGPT request: {e}")
        update.message.reply_text("Извините, произошла ошибка при обработке вашего запроса.")

def main() -> None:
    """Запускает бота."""
    updater = Updater(TELEGRAM_TOKEN)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
