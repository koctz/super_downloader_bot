import os
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from src.services.downloader import VideoDownloader

# Настройки (Замени на свои данные)
CHANNEL_ID = "-100XXXXXXXXXX"  # ID твоего канала (начинается с -100)
CHANNEL_URL = "https://t.me/твой_канал" # Ссылка на твой канал

video_router = Router()
downloader = VideoDownloader()

class DownloadStates(StatesGroup):
    choosing_format = State()

# Проверка подписки
async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Если статус не 'left', значит пользователь подписан
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# Команда /start
@video_router.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help_info")]
    ])
    
    await message.answer(
        f"Привет, {message.from_user.full_name}! 👋\n\n"
        "Я помогу тебе скачать видео из <b>TikTok, YouTube, Instagram или VK</b>.\n"
        "Просто пришли мне ссылку!",
        parse_mode="HTML",
        reply_markup=kb
    )

# Обработка ссылки с проверкой подписки
@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
    # Проверяем подписку
    subscribed = await is_subscribed(message.bot, message.from_user.id)
    
    if not subscribed:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подписаться", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
        ])
        await message.answer(
            "⚠️ <b>Для использования бота нужно подписаться на наш канал!</b>\n\n"
            "Это помогает нам поддерживать сервер в рабочем состоянии.",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    url = message.text.strip()
    await state.update_data(download_url=url)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Видео", callback_data="dl_video"),
            InlineKeyboardButton(text="🎵 Аудио (MP3)", callback_data="dl_audio")
        ]
    ])
    
    await message.answer("Формат принят! Что именно скачиваем?", reply_markup=kb)
    await state.set_state(DownloadStates.choosing_format)

# Обработка кнопки "Проверить подписку"
@video_router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery):
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.message.edit_text("✅ Спасибо за подписку! Теперь можешь отправлять ссылки.")
    else:
        await callback.answer("❌ Ты всё еще не подписан!", show_alert=True)

# Инфо-кнопка
@video_router.callback_query(F.data == "help_info")
async def help_handler(callback: types.CallbackQuery):
    await callback.message.answer("Просто отправь ссылку на видео из TikTok, YT или Insta. Бот сам предложит варианты скачивания.")
    await callback.answer()

# Дальше идет твой стандартный handle_download (без изменений)
@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = user_data.get("download_url")
    
    if not url:
        await callback.answer("Ошибка: ссылка потерялась. Пришли её ещё раз.", show_alert=True)
        return

    mode = callback.data.split("_")[1]
    status_msg = await callback.message.edit_text("⏳ Начинаю работу...")
    
    video_path = None
    try:
        action = ChatActionSender.upload_video if mode == 'video' else ChatActionSender.upload_document
        async with action(chat_id=callback.message.chat.id, bot=callback.bot):
            video_data = await downloader.download(url, mode=mode)
            video_path = video_data.path
            await status_msg.edit_text("⬆️ Отправляю...")
            file = FSInputFile(video_path)
            
            if mode == 'video':
                await callback.message.answer_video(
                    video=file, caption=f"🎬 <b>{video_data.title}</b>",
                    parse_mode="HTML", width=video_data.width, height=video_data.height,
                    duration=video_data.duration, supports_streaming=True
                )
            else:
                await callback.message.answer_audio(
                    audio=file, caption=f"🎵 <b>{video_data.title}</b>",
                    parse_mode="HTML", title=video_data.title, performer=video_data.author,
                    duration=video_data.duration
                )
            await status_msg.delete()
            await state.clear()
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except: pass
