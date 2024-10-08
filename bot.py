import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import openai

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка токенов из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Проверка версии OpenAI и инициализация клиента
try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("Using new OpenAI client")
except ImportError:
    client = openai
    logger.info("Using legacy OpenAI client")

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
    "Нейтральный": "нейтрально",
    "Счастливый": "радостно",
    "Грустный": "грустно",
    "Злой": "сердито",
    "Удивленный": "удивленно",
    "Испуганный": "испуганно"
}

# Команды для активации TTS
tts_commands = ["озвучь", "произнеси", "озвучь мне текст", "произнеси следующий текст", "igarsink"]

def start(update: Update, context: CallbackContext) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    update.message.reply_text('Привет! Я бот, который может общаться с помощью ChatGPT, создавать изображения и преобразовывать текст в речь. Используй /tts или напиши "озвучь" для преобразования текста в речь!')

def handle_voice(update: Update, context: CallbackContext) -> None:
    """Обрабатывает голосовые сообщения."""
    update.message.reply_text("Извините, я пока не умею распознавать голосовые сообщения. Пожалуйста, напишите текстом.")

def handle_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает входящие текстовые сообщения."""
    message = update.message.text.lower()
    
    if message.startswith("нарисуй"):
        generate_image(update, context)
    elif any(message.startswith(cmd) for cmd in tts_commands):
        return tts_start(update, context)
    else:
        chat_with_gpt(update, context)

def chat_with_gpt(update: Update, context: CallbackContext) -> None:
    """Обрабатывает диалог с ChatGPT."""
    user_id = update.effective_user.id
    message = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": message})

    try:
        trimmed_history = trim_chat_history(conversation_history[user_id])

        if hasattr(client, 'chat'):
            response = client.chat.completions.create(
                model="chatgpt-4o-latest",
                messages=trimmed_history
            )
            chatgpt_response = response.choices[0].message.content
        else:
            response = client.ChatCompletion.create(
                model="gpt-4",
                messages=trimmed_history
            )
            chatgpt_response = response.choices[0].message['content']

        conversation_history[user_id].append({"role": "assistant", "content": chatgpt_response})
        conversation_history[user_id] = conversation_history[user_id][-10:]

        update.message.reply_text(chatgpt_response)

    except Exception as e:
        logger.error(f"Error in ChatGPT request: {e}")
        update.message.reply_text("Извините, произошла ошибка при обработке вашего запроса.")

def generate_image(update: Update, context: CallbackContext) -> None:
    """Генерирует изображение на основе запроса пользователя."""
    prompt = update.message.text[7:].strip()
    
    if not prompt:
        update.message.reply_text("Пожалуйста, укажите, что нарисовать после слова 'нарисуй'.")
        return

    try:
        if hasattr(client, 'images'):
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
            image_url = response.data[0].url
        else:
            response = client.Image.create(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
            image_url = response['data'][0]['url']

        update.message.reply_photo(image_url, caption=f"Вот изображение по запросу: {prompt}")

    except Exception as e:
        logger.error(f"Error in image generation: {e}")
        update.message.reply_text("Извините, произошла ошибка при генерации изображения.")

def trim_chat_history(history: list) -> list:
    """Обрезает историю чата, чтобы она не превышала максимальное количество токенов"""
    while len(str(history)) > MAX_TOKENS:
        if len(history) > 1:
            history.pop(1)
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
    update.message.reply_text('Теперь введите текст для озвучивания:', reply_markup=ReplyKeyboardRemove())
    return GET_TEXT

def generate_speech(update: Update, context: CallbackContext) -> int:
    """Генерирует речь из текста и отправляет аудиофайл."""
    text = update.message.text
    voice = context.user_data['voice']
    emotion = emotions[context.user_data['emotion']]
    
    logger.info(f"Generating speech for text: '{text}', voice: {voice}, emotion: {emotion}")
    
    try:
        temp_file = f"temp_audio_{update.effective_user.id}.mp3"
        
        if hasattr(client, 'audio'):
            # Новый клиент
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text
            )
            response.stream_to_file(temp_file)
        else:
            # Старый клиент
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text
            )
            with open(temp_file, 'wb') as f:
                f.write(response.content)

        logger.info("Sending audio file to user")
        with open(temp_file, "rb") as audio:
            update.message.reply_audio(audio)

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

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('tts', tts_start),
                      MessageHandler(Filters.regex(f'^({"|".join(tts_commands)})'), tts_start)],
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
    dp.add_handler(MessageHandler(Filters.voice, handle_voice))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
