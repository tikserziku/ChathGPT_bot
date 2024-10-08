import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import openai
import requests

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

# Максимальное количество токенов для запроса
MAX_TOKENS = 4000

# Состояния для ConversationHandler
CHOOSE_VOICE, CHOOSE_EMOTION, GET_TEXT = range(3)

# Словари для голосов и эмоций
voices = {
    "Alloy": "alloy",
    "Echo": "echo",
    "Fable": "fable",
    "Onyx": "onyx",
    "Nova": "nova",
    "Shimmer": "shimmer"
}

emotions = {
    "Нейтральный": "",
    "Счастливый": "Говорите это с радостью и энтузиазмом: ",
    "Грустный": "Говорите это с грустью и меланхолией: ",
    "Злой": "Говорите это с гневом и раздражением: ",
    "Удивленный": "Говорите это с удивлением и изумлением: ",
    "Испуганный": "Говорите это со страхом и тревогой: "
}

def start(update: Update, context: CallbackContext) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    update.message.reply_text('Привет! Я бот, который может общаться с помощью ChatGPT, создавать изображения и преобразовывать текст в речь. Используй /tts для преобразования текста в речь!')

def tts_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс преобразования текста в речь."""
    reply_keyboard = [list(voices.keys())]
    update.message.reply_text(
        'Выберите голос для озвучивания:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return CHOOSE_VOICE

def choose_voice(update: Update, context: CallbackContext) -> int:
    """Сохраняет выбранный голос и запрашивает эмоцию."""
    context.user_data['voice'] = voices[update.message.text]
    reply_keyboard = [list(emotions.keys())]
    update.message.reply_text(
        'Выберите эмоцию:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return CHOOSE_EMOTION

def choose_emotion(update: Update, context: CallbackContext) -> int:
    """Сохраняет выбранную эмоцию и запрашивает текст."""
    context.user_data['emotion'] = update.message.text
    update.message.reply_text(
        'Теперь введите текст для озвучивания:',
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_TEXT

def generate_speech(update: Update, context: CallbackContext) -> int:
    """Генерирует речь из текста и отправляет аудиофайл."""
    text = update.message.text
    voice = context.user_data['voice']
    emotion = emotions[context.user_data['emotion']]
    
    try:
        response = openai.Audio.create(
            model="tts-1",
            voice=voice,
            input=f"{emotion}{text}"
        )

        # Сохраняем аудио во временный файл
        with open("temp_audio.mp3", "wb") as f:
            f.write(response.content)

        # Отправляем аудиофайл
        with open("temp_audio.mp3", "rb") as audio:
            update.message.reply_audio(audio)

        # Удаляем временный файл
        os.remove("temp_audio.mp3")

    except Exception as e:
        logger.error(f"Error in speech generation: {e}")
        update.message.reply_text("Извините, произошла ошибка при генерации речи.")

    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет процесс и завершает разговор."""
    update.message.reply_text('Процесс отменен.', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main() -> None:
    """Запускает бота."""
    updater = Updater(TELEGRAM_TOKEN)
    dp = updater.dispatcher

    # Добавляем ConversationHandler для TTS
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('tts', tts_start)],
        states={
            CHOOSE_VOICE: [MessageHandler(Filters.text & ~Filters.command, choose_voice)],
            CHOOSE_EMOTION: [MessageHandler(Filters.text & ~Filters.command, choose_emotion)],
            GET_TEXT: [MessageHandler(Filters.text & ~Filters.command, generate_speech)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
