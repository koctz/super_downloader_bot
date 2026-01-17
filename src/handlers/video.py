import os
from aiogram import Router, types, F
from aiogram.types import FSInputFile
from aiogram.utils.chat_action import ChatActionSender

from src.services.downloader import VideoDownloader, DownloadError, VideoTooBigError

video_router = Router()
downloader = VideoDownloader()

# Регулярное выражение для поиска любых ссылок (http или https)
# Мы не ограничиваем домены, так как yt-dlp поддерживает тысячи сайтов
URL_PATTERN = r'(https?://\S+)'

@video_router.message(F.text.regexp(URL_PATTERN))
async def process_video_url(message: types.Message):
    # Отправляем сообщение о начале работы
    status_msg = await message.answer("🔎 Изучаю ссылку...")
    
    url = message.text.strip()
    
    # Показываем статус "bot is recording video..." в заголовке чата
    async with ChatActionSender.upload_video(chat_id=message.chat.id, bot=message.bot):
        try:
            await status_msg.edit_text("⬇️ Скачиваю видео на сервер...")
            
            # Вызываем наш сервис скачивания
            video = await downloader.download(url)
            
            await status_msg.edit_text("⬆️ Отправляю видео в Telegram...")
            
            # Подготавливаем файл для отправки
            video_file = FSInputFile(video.path)
            
            # Формируем подпись
            caption = (
                f"🎬 <b>{video.title}</b>\n"
                f"👤 {video.author}\n"
                f"⏱ {video.duration} сек. | 💾 {video.file_size / 1024 / 1024:.1f} MB"
            )

            # Отправляем видео
            # Важно передать width, height и duration, чтобы Telegram отрисовал плеер, а не файл
            await message.answer_video(
                video=video_file,
                caption=caption,
                parse_mode="HTML",
                width=video.width,
                height=video.height,
                duration=video.duration,
                supports_streaming=True
            )
            
            # Удаляем сообщение со статусом (чтобы не мусорить)
            await status_msg.delete()

        except VideoTooBigError as e:
            await status_msg.edit_text(f"❌ <b>Ошибка:</b> {str(e)}\nTelegram не разрешает ботам отправлять файлы больше 50 МБ.", parse_mode="HTML")
            
        except DownloadError as e:
            await status_msg.edit_text(f"⚠️ <b>Не удалось скачать:</b>\n{str(e)}", parse_mode="HTML")
            
        except Exception as e:
            await status_msg.edit_text(f"☠️ <b>Критическая ошибка:</b>\n{str(e)}", parse_mode="HTML")
            
        finally:
            # Очистка мусора: если файл был создан, удаляем его
            # video переменная может быть не определена, если ошибка случилась ДО скачивания
            if 'video' in locals() and video and os.path.exists(video.path):
                os.remove(video.path)
