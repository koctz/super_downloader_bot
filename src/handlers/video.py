import os
import logging
from aiogram import Router, types, F
from aiogram.types import FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from src.services.downloader import VideoDownloader, DownloadError

video_router = Router()
downloader = VideoDownloader()

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message):
    status_msg = await message.answer("⏳ Начинаю работу...")
    url = message.text.strip()
    video_path = None
    
    try:
        async with ChatActionSender.upload_video(chat_id=message.chat.id, bot=message.bot):
            print(f"DEBUG: Начинаю загрузку {url}")
            await status_msg.edit_text("⬇️ Скачиваю и подготавливаю видео...")
            
            video_data = await downloader.download(url)
            video_path = video_data.path
            
            print(f"DEBUG: Загрузка завершена. Файл: {video_path}, Размер: {video_data.file_size}")

            # КРИТИЧЕСКАЯ ПРОВЕРКА: Telegram не примет файл больше 50МБ (52428800 байт)
            if video_data.file_size > 52428800:
                print("DEBUG: Файл слишком большой для Telegram")
                await status_msg.edit_text(f"❌ Файл слишком тяжелый ({video_data.file_size // 1048576} MB). Лимит Telegram для ботов — 50 MB.")
                return

            await status_msg.edit_text(f"⬆️ Отправляю в Telegram ({video_data.file_size // 1048576} MB)...")
            print("DEBUG: Отправка video_file в Telegram API...")
            
            video_file = FSInputFile(video_path)
            
            await message.answer_video(
                video=video_file,
                caption=f"🎬 <b>{video_data.title}</b>\n👤 {video_data.author}",
                parse_mode="HTML",
                width=video_data.width,
                height=video_data.height,
                duration=video_data.duration,
                supports_streaming=True
            )
            print("DEBUG: Видео успешно отправлено!")
            await status_msg.delete()

    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
