import telebot
import whisper
import os
import time  # ### ИЗМЕНЕНИЕ ###: Добавлен для задержки перед перезапуском
import traceback  # ### ИЗМЕНЕНИЕ ###: Добавлен для подробного логирования ошибок

# --- Настройки ---
# Ваш токен от BotFather

TELEGRAM_BOT_TOKEN = "7931267680:AAEhFAIj8BgQXA9FSzWXdKtU5Auirn6UsDE"

# --- Загрузка модели Whisper ---
print("Загрузка локальной модели Whisper...")
try:
    local_whisper_model = whisper.load_model("small")
    print("✅ Модель Whisper успешно загружена!")
except Exception as e:
    print(f"❌ Ошибка при загрузке модели Whisper: {e}")
    print("Убедитесь, что у вас установлены все зависимости и FFmpeg.")
    exit()

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


# --- Обработчики команд и сообщений ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обработчик команды /start и /help."""
    bot.reply_to(
        message,
        "👋 Привет! Отправь мне голосовое сообщение или аудиофайл, и я превращу его в текст."
    )


def process_audio_message(message, file_id, file_name_hint):
    """Универсальная функция для обработки аудио."""
    chat_id = message.chat.id
    status_message = None
    audio_file_path = None
    transcript_file_path = None

    base_name = f"{message.from_user.id}_{message.message_id}"
    file_ext = os.path.splitext(file_name_hint)[1] if file_name_hint else ".ogg"
    audio_file_path = f"{base_name}{file_ext}"

    try:
        # Отправляем временное сообщение о статусе
        status_message = bot.send_message(chat_id, "⏳ Начинаю обработку аудио...")

        # 1. Загрузка аудиофайла
        bot.edit_message_text("📥 Загружаю аудио...", chat_id, status_message.message_id)
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(audio_file_path, 'wb') as f:
            f.write(downloaded_file)

        # 2. Расшифровка с помощью Whisper
        bot.edit_message_text(
            "🎤 Файл загружен, начинаю расшифровку... Это может занять время.",
            chat_id,
            status_message.message_id
        )
        result = local_whisper_model.transcribe(audio_file_path, fp16=False)
        transcript = result["text"].strip()

        # 3. Отправка результата
        if transcript:
            # Если текст слишком длинный, отправляем его файлом
            if len(transcript) > 4000:
                bot.edit_message_text(
                    "📄 Расшифровка слишком длинная, отправляю в виде файла.",
                    chat_id,
                    status_message.message_id
                )
                transcript_file_path = f"{base_name}_transcript.txt"
                with open(transcript_file_path, 'w', encoding='utf-8') as f:
                    f.write(transcript)

                with open(transcript_file_path, 'rb') as doc:
                    # ### ИЗМЕНЕНИЕ ###: Отправляем документ как ответ на исходное сообщение
                    bot.send_document(
                        chat_id,
                        doc,
                        caption="Ваша расшифровка:",
                        reply_to_message_id=message.message_id
                    )
                # После отправки файла меняем статусное сообщение на "Готово"
                bot.edit_message_text("✅ Готово!", chat_id, status_message.message_id)

            else:
                # ### ИЗМЕНЕНИЕ ###: Отправляем текст как ответ на исходное сообщение
                bot.send_message(
                    chat_id,
                    f"**Расшифровка:**\n\n{transcript}",
                    reply_to_message_id=message.message_id,
                    parse_mode='Markdown'
                )
                # После отправки ответа удаляем временное статусное сообщение
                bot.delete_message(chat_id, status_message.message_id)
        else:
            # Если речь не распознана, просто редактируем статус
            bot.edit_message_text(
                "⚠️ Не удалось распознать речь в аудио.",
                chat_id,
                status_message.message_id
            )

    except Exception as e:
        print("--- Произошла ошибка при обработке аудио ---")
        print(f"Chat ID: {chat_id}, Message ID: {message.message_id}")
        print(traceback.format_exc())
        print("---------------------------------------------")

        error_text = "❌ Произошла непредвиденная ошибка. Попробуйте еще раз позже."
        if status_message:
            bot.edit_message_text(error_text, chat_id, status_message.message_id)
        else:
            bot.send_message(chat_id, error_text, reply_to_message_id=message.message_id)

    finally:
        # 4. Удаление временных файлов
        if audio_file_path and os.path.exists(audio_file_path):
            os.remove(audio_file_path)
        if transcript_file_path and os.path.exists(transcript_file_path):
            os.remove(transcript_file_path)


@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    """Обработчик голосовых сообщений."""
    process_audio_message(message, message.voice.file_id, "voice_message.ogg")


@bot.message_handler(content_types=['audio'])
def handle_audio_message(message):
    """Обработчик аудиофайлов."""
    process_audio_message(message, message.audio.file_id, message.audio.file_name)


# --- Запуск бота с автоматическим перезапуском ---
if __name__ == '__main__':
    while True:
        try:
            print("🚀 Бот запущен и готов к работе!")
            bot.polling(none_stop=True)
        except Exception as e:
            print("--- КРИТИЧЕСКАЯ ОШИБКА БОТА ---")
            print(traceback.format_exc())
            print("---------------------------------")
            print(f"Перезапуск через 15 секунд...")
            time.sleep(15)