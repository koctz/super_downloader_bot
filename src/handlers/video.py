import os
import asyncio
import logging
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from src.services.downloader import VideoDownloader

# Настройки 
from src.config import conf

# Настройка логирования, чтобы видеть ошибки кнопок в консоли
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHANNEL_ID = conf.channel_id
CHANNEL_URL = conf.channel_url

video_router = Router()
downloader = VideoDownloader()

# --- СЛОВАРЬ ПЕРЕВОДОВ ---
STRINGS = {
    "ru": {
        "start": "Выберите язык / Choose language:",
        "welcome": "Привет! 👋\nЯ помогу тебе скачать видео из <b>TikTok, YouTube, Instagram или VK</b>.\nПросто пришли мне ссылку!",
        "sub_required": "⚠️ <b>Для использования бота нужно подписаться на наш канал!</b>\n\nЭто помогает нам поддерживать сервер в рабочем состоянии.",
        "subscribe": "✅ Подписаться",
        "check_sub": "🔄 Проверить подписку",
        "btn_channel": "📢 Наш канал",
        "btn_help": "🆘 Помощь",
        "btn_settings": "⚙️ Настройки",
        "settings_msg": "Здесь ты можешь изменить язык бота:",
        "help_msg": "Просто отправь ссылку на видео из TikTok, YT или Insta. Бот сам предложит варианты скачивания.",
        "link_received": "Ссылка принята! Что именно скачиваем?",
        "btn_video": "🎬 Видео",
        "btn_audio": "🎵 Аудио (MP3)",
        "btn_cancel": "❌ Отмена",
        "cancel_msg": "Действие отменено. Отправь мне новую ссылку!",
        "step_1": "⏳ Анализирую...",
        "step_2": "📥 Загружаю...",
        "step_3": "⚙️ Обрабатываю...",
        "step_4": "📤 Отправляю...",
        "promo": "🚀 <b>Скачано через: @youtodownloadbot</b>",
        "err_lost": "Ошибка: ссылка потерялась.",
        "err_large": "❌ Видео слишком тяжелое.",
        "err_timeout": "❌ Время вышло.",
        "err_sub": "❌ Ты не подписан!",
        "sub_ok": "✅ Подписка подтверждена!"
    },
    "en": {
        "start": "Choose language / Выберите язык:",
        "welcome": "Hello! 👋\nI can download from <b>TikTok, YouTube, Instagram, or VK</b>.\nSend me a link!",
        "sub_required": "⚠️ <b>Subscribe to our channel to use the bot!</b>",
        "subscribe": "✅ Subscribe",
        "check_sub": "🔄 Check Subscription",
        "btn_channel": "📢 Our Channel",
        "btn_help": "🆘 Help",
        "btn_settings": "⚙️ Settings",
        "settings_msg": "Choose language:",
        "help_msg": "Send a link from TikTok, YT, or Insta.",
        "link_received": "Link received! Choose format:",
        "btn_video": "🎬 Video",
        "btn_audio": "🎵 Audio (MP3)",
        "btn_cancel": "❌ Cancel",
        "cancel_msg": "Canceled. Send a new link!",
        "step_1": "⏳ Analyzing...",
        "step_2": "📥 Downloading...",
        "step_3": "⚙️ Processing...",
        "step_4": "📤 Sending...",
        "promo": "🚀 <b>Via: @youtodownloadbot</b>",
        "err_lost": "Error: link lost.",
        "err_large": "❌ File too large.",
        "err_timeout": "❌ Timeout.",
        "err_sub": "❌ Not subscribed!",
        "sub_ok": "✅ Subscribed!"
    }
}

class DownloadStates(StatesGroup):
    choosing_language = State()
    choosing_format = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

# --- СЛУЖЕБНЫЕ ФУНКЦИИ ---
def register_user(user_id: int):
    try:
        user_id_str = str(user_id)
        os.makedirs(os.path.dirname(conf.users_db_path), exist_ok=True)
        if not os.path.exists(conf.users_db_path):
            open(conf.users_db_path, 'a').close()
        with open(conf.users_db_path, "r") as f:
            users = f.read().splitlines()
        if user_id_str not in users:
            with open(conf.users_db_path, "a") as f:
                f.write(user_id_str + "\n")
    except Exception as e:
        logger.error(f"Error registering user: {e}")

async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# --- ХЕНДЛЕРЫ ---

@video_router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    register_user(message.from_user.id)
    
    # Создаем клавиатуру БЕЗ ссылок для теста (только callback)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
        ]
    ])
    
    try:
        await message.answer(STRINGS["ru"]["start"], reply_markup=kb)
        await state.set_state(DownloadStates.choosing_language)
    except Exception as e:
        logger.error(f"FAIL TO SEND KEYBOARD: {e}")
        await message.answer(f"Ошибка кнопок: {e}")

@video_router.callback_query(F.data == "open_settings")
async def open_settings(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
        ],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")]
    ])
    await callback.message.edit_text(STRINGS[lang]["settings_msg"], reply_markup=kb)
    await callback.answer()

@video_router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(lang=lang)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [
            InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info"),
            InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="open_settings")
        ]
    ])
    await callback.message.edit_text(STRINGS[lang]["welcome"], parse_mode="HTML", reply_markup=kb)
    await state.set_state(None)
    await callback.answer()

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    if not await is_subscribed(message.bot, message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=STRINGS[lang]["subscribe"], url=CHANNEL_URL)],
            [InlineKeyboardButton(text=STRINGS[lang]["check_sub"], callback_data="check_sub")]
        ])
        await message.answer(STRINGS[lang]["sub_required"], parse_mode="HTML", reply_markup=kb)
        return

    await state.update_data(download_url=message.text.strip())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=STRINGS[lang]["btn_video"], callback_data="dl_video"),
            InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")
        ],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")]
    ])
    await message.answer(STRINGS[lang]["link_received"], reply_markup=kb)
    await state.set_state(DownloadStates.choosing_format)

@video_router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.message.edit_text(STRINGS[lang]["sub_ok"])
    else:
        await callback.answer(STRINGS[lang]["err_sub"], show_alert=True)

@video_router.callback_query(F.data == "help_info")
async def help_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await callback.message.answer(STRINGS[lang]["help_msg"])
    await callback.answer()

@video_router.callback_query(F.data == "cancel_download")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [
            InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info"),
            InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="open_settings")
        ]
    ])
    await callback.message.edit_text(STRINGS[lang]["cancel_msg"], reply_markup=kb)
    await callback.answer()

@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = user_data.get("download_url")
    lang = user_data.get("lang", "ru")
    
    if not url:
        await callback.answer(STRINGS[lang]["err_lost"], show_alert=True)
        return

    mode = callback.data.split("_")[1]
    status_msg = await callback.message.edit_text(STRINGS[lang]["step_1"])
    
    video_path = None
    try:
        action = ChatActionSender.upload_video if mode == 'video' else ChatActionSender.upload_document
        async with action(chat_id=callback.message.chat.id, bot=callback.bot):
            await status_msg.edit_text(STRINGS[lang]["step_2"])
            video_data = await downloader.download(url, mode=mode)
            video_path = video_data.path
            await status_msg.edit_text(STRINGS[lang]["step_3"])
            await status_msg.edit_text(STRINGS[lang]["step_4"])
            
            file = FSInputFile(video_path)
            promo = f"\n\n{STRINGS[lang]['promo']}"
            
            if mode == 'video':
                await callback.message.answer_video(
                    video=file, caption=f"🎬 <b>{video_data.title[:900]}</b>{promo}",
                    parse_mode="HTML", width=video_data.width, height=video_data.height,
                    duration=video_data.duration, supports_streaming=True
                )
            else:
                await callback.message.answer_audio(
                    audio=file, caption=f"🎵 <b>{video_data.title[:900]}</b>{promo}",
                    parse_mode="HTML", title=video_data.title, duration=video_data.duration
                )
            await status_msg.delete()
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:50]}")
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)

@video_router.message(Command("broadcast"))
async def start_broadcast(message: types.Message, state: FSMContext):
    if str(message.from_user.id) != str(conf.admin_id): return
    await message.answer("Пришли сообщение для рассылки.")
    await state.set_state(AdminStates.waiting_for_broadcast)

@video_router.message(AdminStates.waiting_for_broadcast)
async def perform_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    with open(conf.users_db_path, "r") as f: user_ids = f.read().splitlines()
    count = 0
    for user_id in user_ids:
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка завершена! Получили: {count}")
