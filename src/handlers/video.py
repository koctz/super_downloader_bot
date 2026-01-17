import os
import asyncio
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from src.services.downloader import VideoDownloader

# Настройки 
from src.config import conf

CHANNEL_ID = conf.channel_id
CHANNEL_URL = conf.channel_url

video_router = Router()
downloader = VideoDownloader()

# Состояния
class DownloadStates(StatesGroup):
    choosing_format = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

# --- СЛУЖЕБНЫЕ ФУНКЦИИ ---

def register_user(user_id: int):
    """Добавляет ID пользователя в файл для рассылки, если его там нет"""
    user_id_str = str(user_id)
    if not os.path.exists(conf.users_db_path):
        os.makedirs(os.path.dirname(conf.users_db_path), exist_ok=True)
        with open(conf.users_db_path, "w") as f:
            pass
            
    with open(conf.users_db_path, "r") as f:
        users = f.read().splitlines()
    
    if user_id_str not in users:
        with open(conf.users_db_path, "a") as f:
            f.write(user_id_str + "\n")

async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- АДМИНСКАЯ РАССЫЛКА ---

@video_router.message(Command("broadcast"))
async def start_broadcast(message: types.Message, state: FSMContext):
    if str(message.from_user.id) != str(conf.admin_id):
        return

    await message.answer("Пришли сообщение для рассылки (текст, фото или видео).")
    await state.set_state(AdminStates.waiting_for_broadcast)

@video_router.message(AdminStates.waiting_for_broadcast)
async def perform_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    
    if not os.path.exists(conf.users_db_path):
        await message.answer("База пользователей пуста.")
        return

    with open(conf.users_db_path, "r") as f:
        user_ids = f.read().splitlines()

    count = 0
    blocked = 0
    status_msg = await message.answer(f"🚀 Начинаю рассылку на {len(user_ids)} пользователей...")

    for user_id in user_ids:
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05) 
        except Exception:
            blocked += 1

    await status_msg.edit_text(f"✅ Рассылка завершена!\n\nУспешно: {count}\nЗаблокировали бота: {blocked}")

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---

@video_router.message(Command("start"))
async def start_cmd(message: types.Message):
    register_user(message.from_user.id)
    
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

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
    register_user(message.from_user.id)
    
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
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_download")
        ]
    ])
    
    await message.answer("Ссылка принята! Что именно скачиваем?", reply_markup=kb)
    await state.set_state(DownloadStates.choosing_format)

@video_router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery):
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.message.edit_text("✅ Спасибо за подписку! Теперь можешь отправлять ссылки.")
    else:
        await callback.answer("❌ Ты всё еще не подписан!", show_alert=True)

@video_router.callback_query(F.data == "help_info")
async def help_handler(callback: types.CallbackQuery):
    await callback.message.answer("Просто отправь ссылку на видео из TikTok, YT или Insta. Бот сам предложит варианты скачивания.")
    await callback.answer()

@video_router.callback_query(F.data == "cancel_download")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Наш канал", url=conf.channel_url)],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help_info")]
    ])
    
    await callback.message.edit_text(
        "Действие отменено. Отправь мне новую ссылку, и я всё скачаю! 👇",
        reply_markup=kb
    )
    await callback.answer()

@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = user_data.get("download_url")
    
    if not url:
        await callback.answer("Ошибка: ссылка потерялась. Пришли её ещё раз.", show_alert=True)
        return

    mode = callback.data.split("_")[1]
    status_msg = await callback.message.edit_text("⏳ [1/4] Анализирую ссылку...")
    
    video_path = None
    try:
        action = ChatActionSender.upload_video if mode == 'video' else ChatActionSender.upload_document
        async with action(chat_id=callback.message.chat.id, bot=callback.bot):
            # ЭТАП 2
            await status_msg.edit_text("📥 [2/4] Загружаю файл на сервер...")
            video_data = await downloader.download(url, mode=mode)
            video_path = video_data.path
            
            # ЭТАП 3
            await status_msg.edit_text("⚙️ [3/4] Обрабатываю и сжимаю...")
            
            # ЭТАП 4
            await status_msg.edit_text("📤 [4/4] Отправляю файл тебе...")
            file = FSInputFile(video_path)
            
            # Подпись с рекламой бота
            promo = "\n\n🚀 <b>Скачано через: @youtodownloadbot</b>"
            clean_title = video_data.title[:900]
            
            if mode == 'video':
                await callback.message.answer_video(
                    video=file, 
                    caption=f"🎬 <b>{clean_title}</b>{promo}",
                    parse_mode="HTML", 
                    width=video_data.width, 
                    height=video_data.height,
                    duration=video_data.duration, 
                    supports_streaming=True,
                    request_timeout=300 # Таймаут 5 минут для тяжелых видео
                )
            else:
                await callback.message.answer_audio(
                    audio=file, 
                    caption=f"🎵 <b>{clean_title}</b>{promo}",
                    parse_mode="HTML", 
                    title=video_data.title, 
                    performer=video_data.author,
                    duration=video_data.duration,
                    request_timeout=300
                )
            
            await status_msg.delete()
            await state.clear()
            
    except Exception as e:
        err_text = str(e)
        if "Request Entity Too Large" in err_text:
            msg = "❌ Видео слишком тяжелое для Telegram (даже после сжатия)."
        elif "Timeout" in err_text:
            msg = "❌ Видео обрабатывалось слишком долго. Попробуй другое."
        else:
            msg = f"❌ Ошибка: {err_text[:100]}"
            
        await status_msg.edit_text(msg)
        await state.clear()
        
    finally:
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except: pass
