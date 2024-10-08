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

# Проверка версии OpenAI и инициализация клиента, если это новая версия
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
CHOOSE_VOICE, CHOOSE_EMOTION, GET_TONE, GET_TEXT = range(4)

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

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": message})

    try:
        trimmed_history = trim_chat_history(conversation_history[user_id])

        if hasattr(client, 'chat'):
            response = client.chat.completions.create(
                model="gpt-4",
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
    """Сохраняет выбранную эмоцию и запрашивает инструкции по тону."""
    context.user_data['emotion'] = update.message.text
    update.message.reply_text(
        'Теперь вы можете дать дополнительные инструкции по тону речи (например, "скажи очень женственно") или просто напишите "нет" для пропуска этого шага:',
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_TONE

def get_tone(update: Update, context: CallbackContext) -> int:
    """Сохраняет инструкции по тону и запрашивает текст."""
    tone = update.message.text
    if tone.lower() != 'нет':
        context.user_data['tone'] = tone
    else:
        context.user_data['tone'] = ''
    update.message.reply_text('Теперь введите текст для озвучивания:')
    return GET_TEXT

def generate_speech(update: Update, context: CallbackContext) -> int:
    """Генерирует речь из текста и отправляет аудиофайл."""
    text = update.message.text
    voice = context.user_data['voice']
    emotion = emotions[context.user_data['emotion']]
    tone = context.user_data.get('tone', '')
    
    logger.info(f"Generating speech for text: '{text}', voice: {voice}, emotion: {emotion}, tone: {tone}")
    
    try:
        temp_file = f"temp_audio_{update.effective_user.id}.mp3"
        
        # Формируем инструкцию для модели
        instruction = f"Озвучь следующий текст {emotion}"
        if tone:
            instruction += f", {tone}"
        instruction += ":"
        
        full_text = f"{instruction} {text}"
        
        if hasattr(client, 'audio'):
            # Новый клиент
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=full_text
            )
            response.stream_to_file(temp_file)
        else:
            # Старый клиент
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=full_text
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
        entry_points=[CommandHandler('tts', tts_start)],
        states={
            CHOOSE_VOICE: [MessageHandler(Filters.text & ~Filters.command, choose_voice)],
            CHOOSE_EMOTION: [MessageHandler(Filters.text & ~Filters.command, choose_emotion)],
            GET_TONE: [MessageHandler(Filters.text & ~Filters.command, get_tone)],
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
