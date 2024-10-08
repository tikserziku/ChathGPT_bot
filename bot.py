import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from openai import OpenAI

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка токенов из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Инициализация клиента OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

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

def handle_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает входящие сообщения и отправляет их в ChatGPT или создает изображение."""
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
        # Обрезаем историю, чтобы не превысить лимит токенов
        trimmed_history = trim_chat_history(conversation_history[user_id])

        # Отправляем запрос к ChatGPT
        response = client.chat.completions.create(
            model="gpt-4",  # Используем GPT-4
            messages=trimmed_history
        )

        # Получаем ответ от ChatGPT
        chatgpt_response = response.choices[0].message.content

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
        # Отправляем запрос к DALL-E 3
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024"
        )

        # Получаем URL сгенерированного изображения
        image_url = response.data[0].url

        # Отправляем изображение пользователю
        update.message.reply_photo(image_url, caption=f"Вот изображение по запросу: {prompt}")

    except Exception as e:
        logger.error(f"Error in image generation: {e}")
        update.message.reply_text("Извините, произошла ошибка при генерации изображения.")

def trim_chat_history(history: list) -> list:
    """Обрезает историю чата, чтобы она не превышала максимальное количество токенов"""
    while len(str(history)) > MAX_TOKENS:
        if len(history) > 1:
            history.pop(1)  # Удаляем второе сообщение (после системного)
        else:
            break
    return history

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
    
    logger.info(f"Generating speech for text: '{text}', voice: {voice}, emotion: {context.user_data['emotion']}")
    
    try:
        logger.info("Sending request to OpenAI API")
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=f"{emotion}{text}"
        )
        logger.info("Received response from OpenAI API")

        # Сохраняем аудио во временный файл
        temp_file = f"temp_audio_{update.effective_user.id}.mp3"
        logger.info(f"Saving audio to temporary file: {temp_file}")
        response.stream_to_file(temp_file)

        # Отправляем аудиофайл
        logger.info("Sending audio file to user")
        with open(temp_file, "rb") as audio:
            update.message.reply_audio(audio)

        # Удаляем временный файл
        logger.info(f"Removing temporary file: {temp_file}")
        os.remove(temp_file)

    except Exception as e:
        logger.error(f"Error in speech generation: {str(e)}", exc_info=True)
        update.message.reply_text(f"Извините, произошла ошибка при генерации речи: {str(e)}")

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
