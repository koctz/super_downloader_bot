import os
from aiogram import Router, types, F
from aiogram.types import FSInputFile
from aiogram.utils.chat_action import ChatActionSender

from src.services.downloader import VideoDownloader, DownloadError

video_router = Router()
downloader = VideoDownloader()

URL_PATTERN = r'(https?://\S+)'

@video_router.message(F.text.regexp(URL_PATTERN))
async def process_video_url(message: types.Message):
    status_msg = await message.answer("🔎 Изучаю ссылку...")
    
    url = message.text.strip()
    
    async with ChatActionSender.upload_video(chat_id=message.chat.id, bot=message.bot):
        try:
            # Обновляем статус: скачивание
            await status_msg.edit_text("⬇️ Начинаю загрузку...")
            
            # Мы добавим проверку времени, чтобы юзер не думал, что бот завис
            video = await downloader.download(url)
            
            await status_msg.edit_text("⬆️ Отправляю видео в Telegram...")
            
            video_file = FSInputFile(video.path)
            
            caption = (
                f"🎬 <b>{video.title}</b>\n"
                f"👤 {video.author}\n"
                f"⏱ {video.duration} сек. | 💾 {video.file_size / 1024 / 1024:.1f} MB"
            )

            await message.answer_video(
                video=video_file,
                caption=caption,
                parse_mode="HTML",
                width=video.width,
                height=video.height,
                duration=video.duration,
                supports_streaming=True
            )
            
            await status_msg.delete()

        except DownloadError as e:
            await status_msg.edit_text(f"⚠️ <b>Ошибка загрузки:</b>\n{str(e)}", parse_mode="HTML")
            
        except Exception as e:
            await status_msg.edit_text(f"☠️ <b>Произошла ошибка:</b>\n{str(e)}", parse_mode="HTML")
            
        finally:
            if 'video' in locals() and video and os.path.exists(video.path):
                os.remove(video.path)
