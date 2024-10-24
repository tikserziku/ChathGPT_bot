import os
import logging
import base64
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import openai
import anthropic

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка токенов из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Инициализация API
try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("Using new OpenAI client")
except ImportError:
    client = openai
    logger.info("Using legacy OpenAI client")

# Инициализация Claude
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Состояния и переменные из предыдущего кода остаются без изменений
conversation_history = {}
MAX_TOKENS = 4000
CHOOSE_VOICE, CHOOSE_EMOTION, GET_TEXT = range(3)

# Словари для голосов и эмоций остаются без изменений
voices = {
    "Alloy": "alloy",
    "Echo": "echo",
    "Fable": "fable",
    "Onyx": "onyx",
    "Nova": "nova",
    "Shimmer": "shimmer"
}

emotions = {
    "Нейтральный": "нейтрально",
    "Счастливый": "радостно",
    "Грустный": "грустно",
    "Злой": "сердито",
    "Удивленный": "удивленно",
    "Испуганный": "испуганно"
}

tts_commands = ["озвучь", "произнеси", "озвучь мне текст", "произнеси следующий текст", "igarsink"]

def start(update: Update, context: CallbackContext) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    update.message.reply_text(
        'Привет! Я бот, который может:\n'
        '1. Общаться с помощью ChatGPT\n'
        '2. Создавать изображения (напиши "нарисуй [описание]")\n'
        '3. Преобразовывать текст в речь (используй /tts или напиши "озвучь")\n'
        '4. Распознавать текст с фотографий\n\n'
        'Просто отправь мне сообщение, фото с текстом или используй команды!'
    )

# Добавляем новую функцию для распознавания текста с фото
def handle_photo(update: Update, context: CallbackContext) -> None:
    """Обрабатывает фотографии для распознавания текста."""
    try:
        # Отправляем сообщение о начале обработки
        processing_msg = update.message.reply_text("Обрабатываю фотографию...")

        # Получаем фото наилучшего качества
        photo_file = update.message.photo[-1].get_file()
        
        # Скачиваем фото
        buffer = BytesIO()
        photo_file.download(out=buffer)
        buffer.seek(0)
        
        # Конвертируем в base64
        base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')

        # Отправляем запрос к Claude
        response = claude.beta.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": "Пожалуйста, распознай текст на этом изображении. Сначала определи язык (русский, английский или литовский), затем выдели сам текст. Формат ответа:\nЯзык: [определенный язык]\nТекст: [распознанный текст]\n\nЕсли на изображении текст на нескольких языках, перечисли их все и раздели текст по языкам."
                        }
                    ]
                }
            ]
        )

        # Удаляем сообщение о обработке
        processing_msg.delete()

        # Отправляем результат
        result_text = response.content[0].text
        update.message.reply_text(result_text)

        # Добавляем кнопку для быстрого озвучивания распознанного текста
        update.message.reply_text(
            "Хотите озвучить распознанный текст? Используйте команду /tts",
            reply_markup=ReplyKeyboardMarkup([["Озвучить текст"]], one_time_keyboard=True)
        )

    except Exception as e:
        logger.error(f"Error in text recognition: {e}")
        update.message.reply_text(
            "Извините, произошла ошибка при распознавании текста. "
            "Пожалуйста, убедитесь, что фото четкое и текст хорошо виден."
        )

# Обновляем handle_message для обработки команды озвучивания распознанного текста
def handle_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает входящие текстовые сообщения."""
    message = update.message.text.lower()
    
    if message.startswith("нарисуй"):
        generate_image(update, context)
    elif message == "озвучить текст" or any(message.startswith(cmd) for cmd in tts_commands):
        return tts_start(update, context)
    else:
        chat_with_gpt(update, context)

# Остальные функции остаются без изменений...

def main() -> None:
    """Запускает бота."""
    updater = Updater(TELEGRAM_TOKEN)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('tts', tts_start),
            MessageHandler(Filters.regex(f'^({"|".join(tts_commands)})'), tts_start),
            MessageHandler(Filters.regex('^Озвучить текст$'), tts_start)
        ],
        states={
            CHOOSE_VOICE: [MessageHandler(Filters.text & ~Filters.command, choose_voice)],
            CHOOSE_EMOTION: [MessageHandler(Filters.text & ~Filters.command, choose_emotion)],
            GET_TEXT: [MessageHandler(Filters.text & ~Filters.command, generate_speech)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))  # Добавляем обработчик фото
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(MessageHandler(Filters.voice, handle_voice))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
