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
    update.message.reply_text('Привет! Я бот, который может общаться с помощью ChatGPT и создавать изображения. Просто напиши мне что-нибудь или попроси "нарисуй [описание]"!')

def handle_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает входящие сообщения и отправляет их в ChatGPT или создает изображение."""
    user_id = update.effective_user.id
    message = update.message.text

    if message.lower().startswith("нарисуй"):
        generate_image(update, context)
    else:
        chat_with_gpt(update, context)

def chat_with_gpt(update: Update, context: CallbackContext) -> None:
    """Обрабатывает диалог с ChatGPT."""
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
            model="chatgpt-4o-latest",
            messages=conversation_history[user_id]
        )

        # Получаем ответ от ChatGPT
        chatgpt_response = response.choices[0].message['content']

        # Добавляем ответ ChatGPT в историю
        conversation_history[user_id].append({"role": "assistant", "content": chatgpt_response})

        # Ограничиваем историю последними 10 сообщениями
        conversation_history[user_id] = conversation_history[user_id][-10:]

        # Отправляем ответ пользователю
        update.message.reply_text(chatgpt_response)

    except Exception as e:
        logger.error(f"Error in ChatGPT request: {e}")
        update.message.reply_text("Извините, произошла ошибка при обработке вашего запроса.")

def generate_image(update: Update, context: CallbackContext) -> None:
    """Генерирует изображение на основе запроса пользователя."""
    prompt = update.message.text[7:].strip()  # Убираем "нарисуй " из начала сообщения
    
    if not prompt:
        update.message.reply_text("Пожалуйста, укажите, что нарисовать после слова 'нарисуй'.")
        return

    try:
        # Отправляем запрос к DALL-E
        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="1024x1024"
        )

        # Получаем URL сгенерированного изображения
        image_url = response['data'][0]['url']

        # Отправляем изображение пользователю
        update.message.reply_photo(image_url, caption=f"Вот изображение по запросу: {prompt}")

    except Exception as e:
        logger.error(f"Error in image generation: {e}")
        update.message.reply_text("Извините, произошла ошибка при генерации изображения.")

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
