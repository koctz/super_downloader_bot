import os
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.services.downloader import VideoDownloader

video_router = Router()
downloader = VideoDownloader()

# Состояния для хранения ссылки
class DownloadStates(StatesGroup):
    choosing_format = State()

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    
    # Сохраняем URL в память FSM
    await state.update_data(download_url=url)
    
    # Теперь в callback_data передаем только короткое действие
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Видео", callback_data="dl_video"),
            InlineKeyboardButton(text="🎵 Аудио (MP3)", callback_data="dl_audio")
        ]
    ])
    
    await message.answer("Что скачать?", reply_markup=kb)
    await state.set_state(DownloadStates.choosing_format)

@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    # Получаем URL из памяти
    user_data = await state.get_data()
    url = user_data.get("download_url")
    
    if not url:
        await callback.answer("Ошибка: ссылка потерялась. Пришли её ещё раз.", show_alert=True)
        return

    mode = callback.data.split("_")[1] # video или audio
    status_msg = await callback.message.edit_text("⏳ Начинаю работу...")
    
    video_path = None
    try:
        action = ChatActionSender.upload_video if mode == 'video' else ChatActionSender.upload_document
        
        async with action(chat_id=callback.message.chat.id, bot=callback.bot):
            await status_msg.edit_text(f"⬇️ Скачиваю {mode}...")
            
            video_data = await downloader.download(url, mode=mode)
            video_path = video_data.path

            await status_msg.edit_text("⬆️ Отправляю...")
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
            # Очищаем состояние после успешной загрузки
            await state.clear()

    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            
    finally:
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except: pass
