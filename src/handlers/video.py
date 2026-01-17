import os
import logging
from aiogram import Router, types, F
from aiogram.types import FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from src.services.downloader import VideoDownloader, DownloadError

video_router = Router()
downloader = VideoDownloader()

URL_PATTERN = r'(https?://\S+)'

@video_router.message(F.text.regexp(URL_PATTERN))
async def process_video_url(message: types.Message):
    status_msg = await message.answer("⏳ Начинаю работу...")
    url = message.text.strip()
    
    # Путь к видео сохраним во внешней переменной для блока finally
    video_path = None
    
    try:
        async with ChatActionSender.upload_video(chat_id=message.chat.id, bot=message.bot):
            await status_msg.edit_text("⬇️ Скачиваю и подготавливаю видео...")
            
            video_data = await downloader.download(url)
            video_path = video_data.path # Сохраняем путь для удаления
            
            # Проверка: существует ли файл на диске перед отправкой
            if not os.path.exists(video_path):
                raise DownloadError("Файл пропал после обработки.")

            await status_msg.edit_text(f"⬆️ Отправляю в Telegram ({video_data.file_size // 1048576} MB)...")
            
            video_file = FSInputFile(video_path)
            
            await message.answer_video(
                video=video_file,
                caption=f"🎬 <b>{video_data.title}</b>\n💾 {video_data.file_size // 1048576} MB",
                parse_mode="HTML",
                width=video_data.width,
                height=video_data.height,
                duration=video_data.duration,
                supports_streaming=True
            )
            
            await status_msg.delete()

    except Exception as e:
        logging.error(f"Ошибка при обработке: {e}")
        # Выводим конкретную ошибку пользователю
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            
    finally:
        # Глобальная очистка: удаляем всё, что связано с этим видео
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
        
        # Дополнительная чистка по ID (на случай если остались raw файлы)
        # Это "подчистит" застрявшие файлы из вашего вопроса
        try:
            unique_id = str(hash(url))[-8:]
            for f in os.listdir("downloads"):
                if unique_id in f:
                    os.remove(os.path.join("downloads", f))
        except:
            pass
