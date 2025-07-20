import telebot
import whisper
import os
import time
import traceback
import requests  # Библиотека для отправки запросов к Ollama API
import json      # Для обработки ответов от Ollama
import re        # Библиотека для регулярных выражений, чтобы убирать теги
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
# --- Настройки ---
# Ваш токен от BotFather

TELEGRAM_BOT_TOKEN = "7931267680:AAEhFAIj8BgQXA9FSzWXdKtU5Auirn6UsDE"


# --- ### ОБНОВЛЕННЫЕ НАСТРОЙКИ ДЛЯ OLLAMA ### ---

# Установите True, чтобы включить исправление текста через Ollama, или False, чтобы отключить
ENABLE_OLLAMA_CORRECTION = True

# ### ИЗМЕНЕНИЕ ###: Указана новая модель, как вы и просили.
OLLAMA_MODEL_NAME = "deepseek-r1:32b-qwen-distill-q4_K_M"
OLLAMA_MODEL_NAME = "qwen3:32b-q4_K_M"
OLLAMA_MODEL_NAME = "qwen3:14b"
# Адрес локального API Ollama. Обычно он такой.
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_BASE_URL = "http://localhost:11434"  # ### НОВОЕ ###: Базовый URL для проверок
# ### ИСПРАВЛЕНИЕ ###: Убрана переменная OLLAMA_API_URL, чтобы избежать ошибок.
# Теперь используется только базовый адрес, а полный путь формируется в функции.
OLLAMA_BASE_URL = "http://localhost:11434"

# --- Хранилище для текстов ---
user_last_text = {}


# --- Проверка соединения с Ollama при запуске ---
def check_ollama_connection():
    """Проверяет соединение с Ollama и наличие нужной модели при старте."""
    print("--- Диагностика Ollama ---")
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        models_data = response.json()
        local_models = [model['name'] for model in models_data.get('models', [])]

        print("✅ Соединение с Ollama установлено.")
        if local_models:
            print(f"   Локально доступны модели: {', '.join(local_models)}")
        else:
            print("   ⚠️ Локально нет скачанных моделей.")

        if OLLAMA_MODEL_NAME not in local_models:
            print(
                f"\n⚠️ ВНИМАНИЕ: Модель '{OLLAMA_MODEL_NAME}' не найдена! Скачайте ее командой: ollama pull {OLLAMA_MODEL_NAME}\n")
        else:
            print(f"✅ Требуемая модель '{OLLAMA_MODEL_NAME}' найдена.")
        print("--------------------------")
        return True

    except requests.exceptions.RequestException as e:
        print(
            f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Ollama. Убедитесь, что приложение запущено.\n   Подробности: {e}\n")
        return False


# --- Загрузка модели Whisper ---
print("Загрузка локальной модели Whisper...")
try:
    local_whisper_model = whisper.load_model("small")
    print("✅ Модель Whisper успешно загружена!")
except Exception as e:
    print(f"❌ Ошибка при загрузке модели Whisper: {e}")
    exit()

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


# --- ### ИЗМЕНЕНИЕ: Финальная, исправленная функция для запросов к Ollama ### ---
def ask_ollama(prompt: str) -> (str | None):
    """Отправляет промпт в Ollama и возвращает ответ или None в случае ошибки."""
    api_url = f"{OLLAMA_BASE_URL}/api/chat"  # Правильный адрес для чат-моделей
    try:
        print(f"--- Отправка запроса в Ollama ({api_url}) с моделью {OLLAMA_MODEL_NAME} ---")
        payload = {
            "model": OLLAMA_MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        response = requests.post(api_url, json=payload, timeout=300)

        print(f"   Статус-код ответа: {response.status_code}")
        print(f"   Текст ответа: {response.text}")

        response.raise_for_status()
        response_data = response.json()

        if response_data.get("done_reason") == "load":
            print("❌ ОШИБКА OLLAMA: Модель не смогла загрузиться (нехватка RAM/VRAM).")
            return "MODEL_LOAD_ERROR"

        if "message" not in response_data or "content" not in response_data.get("message", {}):
            print(f"❌ Ошибка: Ответ от Ollama имеет неверный формат.")
            return None

        response_text = response_data["message"]["content"].strip()

        # ### ИСПРАВЛЕНИЕ ###: Возвращена строка для очистки ответа от тегов <think>.
        cleaned_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()

        print("--- Запрос к Ollama успешно обработан ---")
        return cleaned_text

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети при обращении к Ollama API: {e}")
        return None
    except Exception:
        print(f"❌ Непредвиденная ошибка в функции ask_ollama: {traceback.format_exc()}")
        return None


# --- Генератор кнопок ---
def generate_action_buttons():
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("✍️ Улучшить", callback_data="correct"),
        InlineKeyboardButton("📜 Кратко", callback_data="summarize"),
        InlineKeyboardButton("📌 Тезисы", callback_data="key_points")
    )
    return markup


# --- Обработчик нажатий на кнопки ---
@bot.callback_query_handler(func=lambda call: call.data in ["correct", "summarize", "key_points"])
def callback_query_handler(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    last_text = user_last_text.get(chat_id)

    if not last_text:
        bot.answer_callback_query(call.id, "⚠️ Текст не найден. Пожалуйста, отправьте аудио заново.", show_alert=True)
        return

    actions = {
        "correct": (
        "✍️ Улучшаю текст...", "**Исправленный текст:**", f'Ты — опытный редактор... Текст:\n"{last_text}"'),
        "summarize": (
        "📜 Создаю краткий пересказ...", "**Краткий пересказ:**", f'Сделай краткую выжимку... Текст:\n"{last_text}"'),
        "key_points": (
        "📌 Выделяю тезисы...", "**Ключевые тезисы:**", f'Выдели ключевые тезисы... Текст:\n"{last_text}"')
    }

    status_text, result_title, prompt = actions[call.data]

    bot.edit_message_text(status_text, chat_id, message_id)
    result = ask_ollama(prompt)

    if result == "MODEL_LOAD_ERROR":
        error_msg = f"❌ Ошибка загрузки модели '{OLLAMA_MODEL_NAME}'.\n\nВероятно, на вашем ПК не хватает оперативной памяти."
        bot.edit_message_text(error_msg, chat_id, message_id)
    elif result:
        if len(result) > 4096:
            file_path = f"{chat_id}_result.txt"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(result)
            with open(file_path, 'rb') as doc:
                bot.send_document(chat_id, doc, caption=result_title)
            os.remove(file_path)
            bot.delete_message(chat_id, message_id)
        else:
            bot.edit_message_text(f"{result_title}\n\n{result}", chat_id, message_id, parse_mode='Markdown')
    else:
        bot.edit_message_text("❌ Не удалось обработать текст. Проверьте консоль для подробностей.", chat_id, message_id)


# --- Остальные обработчики ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Я бот для работы с аудио...")


@bot.message_handler(commands=['summarize', 'key_points', 'translate'])
def handle_text_commands(message):
    chat_id = message.chat.id
    last_text = user_last_text.get(chat_id)
    command, *args = message.text.split()

    if not last_text:
        bot.reply_to(message, "Сначала нужно отправить аудио для расшифровки.")
        return

    status_message = bot.reply_to(message, "⏳ Обрабатываю...")

    if command == "/translate":
        if not args:
            bot.edit_message_text("Укажите язык для перевода. Пример: `/translate en`", chat_id,
                                  status_message.message_id)
            return
        lang = args[0]
        prompt = f"Переведи следующий текст на язык '{lang}'. Верни только перевод...\n\nТекст:\n\"{last_text}\""
        result = ask_ollama(prompt)
        result_title = f"**Перевод на {lang}:**"
    else:
        # Имитируем нажатие кнопки для /summarize и /key_points
        action = command.strip('/')

        class FakeCall:
            def __init__(self, msg, data):
                self.message = msg
                self.data = data

        callback_query_handler(FakeCall(status_message, action))
        return  # Выходим, т.к. callback_query_handler сам обработает ответ

    if result == "MODEL_LOAD_ERROR":
        error_msg = f"❌ Ошибка загрузки модели '{OLLAMA_MODEL_NAME}'."
        bot.edit_message_text(error_msg, chat_id, status_message.message_id)
    elif result:
        bot.edit_message_text(f"{result_title}\n\n{result}", chat_id, status_message.message_id, parse_mode='Markdown')
    else:
        bot.edit_message_text("❌ Не удалось выполнить команду.", chat_id, status_message.message_id)


def process_audio_message(message, file_id, file_name_hint):
    chat_id = message.chat.id
    status_message = None
    audio_file_path = None
    base_name = f"{message.from_user.id}_{message.message_id}"
    file_ext = os.path.splitext(file_name_hint)[1] if file_name_hint else ".ogg"
    audio_file_path = f"{base_name}{file_ext}"

    try:
        status_message = bot.send_message(chat_id, "⏳ Начинаю обработку аудио...")
        bot.edit_message_text("📥 Загружаю аудио...", chat_id, status_message.message_id)
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(audio_file_path, 'wb') as f:
            f.write(downloaded_file)
        bot.edit_message_text("🎤 Файл загружен, начинаю расшифровку...", chat_id, status_message.message_id)
        result = local_whisper_model.transcribe(audio_file_path, fp16=False)
        transcript = result["text"].strip()

        if not transcript:
            bot.edit_message_text("⚠️ Не удалось распознать речь в аудио.", chat_id, status_message.message_id)
            return

        user_last_text[chat_id] = transcript

        if len(transcript) > 4096:
            bot.edit_message_text("📄 Текст слишком длинный, отправляю файлом...", chat_id, status_message.message_id)
            file_path = f"{base_name}_transcript.txt"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            with open(file_path, 'rb') as doc:
                bot.send_document(chat_id, doc, caption="**Предварительная расшифровка:**",
                                  reply_to_message_id=message.message_id)
            os.remove(file_path)
            bot.send_message(chat_id, "Что сделать с этим текстом?", reply_markup=generate_action_buttons(),
                             reply_to_message_id=message.message_id)
            bot.delete_message(chat_id, status_message.message_id)
        else:
            bot.edit_message_text(
                f"**Предварительная расшифровка:**\n\n{transcript}",
                chat_id,
                status_message.message_id,
                reply_markup=generate_action_buttons(),
                parse_mode='Markdown'
            )

    except Exception:
        print(
            f"--- Произошла ошибка при обработке аудио ---\n{traceback.format_exc()}\n---------------------------------------------")
        error_text = "❌ Произошла непредвиденная ошибка."
        if status_message:
            bot.edit_message_text(error_text, chat_id, status_message.message_id)
        else:
            bot.send_message(chat_id, error_text, reply_to_message_id=message.message_id)
    finally:
        if audio_file_path and os.path.exists(audio_file_path):
            os.remove(audio_file_path)


@bot.message_handler(content_types=['voice', 'audio'])
def handle_media(message):
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file_name = "voice.ogg" if message.voice else message.audio.file_name
    process_audio_message(message, file_id, file_name)


# --- Запуск бота ---
if __name__ == '__main__':
    if check_ollama_connection():
        print(f"✅ Режим ИИ-ассистента включен. Модель: {OLLAMA_MODEL_NAME}")
        while True:
            try:
                print("🚀 Бот запущен и готов к работе!")
                bot.polling(none_stop=True)
            except Exception:
                print(f"--- КРИТИЧЕСКАЯ ОШИБКА БОТА ---\n{traceback.format_exc()}\n---------------------------------")
                print("Перезапуск через 15 секунд...")
                time.sleep(15)
    else:
        print("Бот не будет запущен из-за проблем с подключением к Ollama.")