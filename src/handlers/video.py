import os
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from src.services.downloader import VideoDownloader

video_router = Router()
downloader = VideoDownloader()

# Обработка ссылки: показываем кнопки
@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message):
    url = message.text.strip()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Видео", callback_data=f"dl_video_{url}"),
            InlineKeyboardButton(text="🎵 Аудио (MP3)", callback_data=f"dl_audio_{url}")
        ]
    ])
    
    await message.answer("Что скачать?", reply_markup=kb)

# Обработка нажатия кнопок
@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery):
    # Разделяем тип загрузки и URL
    # dl_video_https://... -> mode='video', url='https://...'
    data = callback.data.split("_")
    mode = data[1] # video или audio
    url = "_".join(data[2:]) # На случай если в URL есть подчеркивания
    
    status_msg = await callback.message.edit_text("⏳ Начинаю работу...")
    video_path = None
    
    try:
        # Выбираем действие для ChatAction
        action = ChatActionSender.upload_video if mode == 'video' else ChatActionSender.upload_document
        
        async with action(chat_id=callback.message.chat.id, bot=callback.bot):
            await status_msg.edit_text(f"⬇️ Скачиваю {'видео' if mode == 'video' else 'аудио'}...")
            
            # В downloader.download нужно добавить поддержку mode (сделаем в шаге 2)
            video_data = await downloader.download(url, mode=mode)
            video_path = video_data.path

            if video_data.file_size > 52428800:
                await status_msg.edit_text("❌ Файл слишком тяжелый для Telegram (лимит 50MB).")
                return

            await status_msg.edit_text("⬆️ Отправляю файл...")
            file = FSInputFile(video_path)
            
            if mode == 'video':
                await callback.message.answer_video(
                    video=file,
                    caption=f"🎬 <b>{video_data.title}</b>",
                    parse_mode="HTML",
                    width=video_data.width,
                    height=video_data.height,
                    duration=video_data.duration,
                    supports_streaming=True
                )
            else:
                await callback.message.answer_audio(
                    audio=file,
                    caption=f"🎵 <b>{video_data.title}</b>",
                    parse_mode="HTML",
                    title=video_data.title,
                    performer=video_data.author,
                    duration=video_data.duration
                )
            
            await status_msg.delete()

    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
