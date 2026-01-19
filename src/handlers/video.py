import os
import time
import asyncio
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo

from src.services.downloader import VideoDownloader
from src.db import add_user, count_users, get_all_user_ids
from src.config import conf

CHANNEL_ID = conf.channel_id
CHANNEL_URL = conf.channel_url

video_router = Router()
downloader = VideoDownloader()

tele_client = TelegramClient('telethon_bot', conf.api_id, conf.api_hash)

# ============================================================
# УМНАЯ ОТПРАВКА ФАЙЛОВ (AIROGRAM → TELETHON FALLBACK)
# ============================================================

MAX_AIAGRAM_SIZE = 50 * 1024 * 1024  # 50 MB


async def send_media_smart(callback: types.CallbackQuery, res, lang: str, mode: str):
    chat_id = callback.message.chat.id
    bot = callback.bot
    file_path = res.path
    file_size = os.path.getsize(file_path)

    caption = f"🎬 <b>{res.title}</b>{STRINGS[lang]['promo']}"
    if mode == "audio":
        caption = f"🎵 <b>{res.title}</b>{STRINGS[lang]['promo']}"

    # 1) Быстрая отправка через aiogram
    if file_size <= MAX_AIAGRAM_SIZE:
        try:
            if mode == "video":
                await bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(file_path),
                    caption=caption,
                    supports_streaming=True,
                    parse_mode="HTML"
                )
            else:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=FSInputFile(file_path),
                    caption=caption,
                    parse_mode="HTML"
                )
            return
        except Exception as e:
            print("Aiogram send failed → fallback:", e)

    if not tele_client.is_connected():
        await tele_client.start(bot_token=conf.bot_token)

    attributes = []
    if mode == "video":
        attributes = [
            DocumentAttributeVideo(
                duration=res.duration,
                w=res.width,
                h=res.height,
                supports_streaming=True
            )
        ]

    await tele_client.send_file(
        chat_id,
        file_path,
        caption=caption,
        parse_mode='html',
        part_size_kb=1024,
        use_cache=False,
        attributes=attributes
    )


# ============================================================
# ЛОКАЛИЗАЦИЯ
# ============================================================

STRINGS = {
    "ru": {
        "choose_lang": "Выберите язык / Choose language:",
        "welcome": "Привет, {name}! 👋\n\nЯ помогу тебе скачать видео из <b>TikTok, YouTube, Instagram или VK</b>.\nПросто пришли мне ссылку!",
        "sub_req": "⚠️ <b>Для использования бота нужно подписаться на наш канал!</b>",
        "btn_sub": "✅ Подписаться",
        "btn_check_sub": "🔄 Проверить подписку",
        "btn_channel": "📢 Наш канал",
        "btn_help": "🆘 Помощь",
        "btn_video": "🎬 Видео (Max)",
        "btn_audio": "🎵 Аудио (MP3)",
        "btn_cancel": "❌ Отмена",
        "btn_settings": "⚙️ Настройки",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_back": "⬅️ Назад",
        "link_ok": "Выберите качество видео:",
        "link_ok_general": "Ссылка принята! Что скачиваем?",
        "step_1": "🔍 Анализирую ссылку...",
        "step_2": "📥 Загружаю: {p}",
        "step_3": "⚙️ Обработка файла...",
        "step_4": "📤 Отправка в Telegram...",
        "promo": "\n\n🚀 <b>Скачано через: @youtodownloadbot</b>"
    },
    "en": {
        "choose_lang": "Choose language / Выберите язык:",
        "welcome": "Hello, {name}! 👋\n\nI can download from <b>TikTok, YouTube, Instagram or VK</b>.",
        "sub_req": "⚠️ <b>Please subscribe to our channel!</b>",
        "btn_sub": "✅ Subscribe",
        "btn_check_sub": "🔄 Check",
        "btn_channel": "📢 Channel",
        "btn_help": "🆘 Help",
        "btn_video": "🎬 Video (Max)",
        "btn_audio": "🎵 Audio (MP3)",
        "btn_cancel": "❌ Cancel",
        "btn_settings": "⚙️ Settings",
        "btn_change_lang": "🌐 Language",
        "btn_back": "⬅️ Back",
        "link_ok": "Choose video quality:",
        "link_ok_general": "Link accepted! What to download?",
        "step_1": "🔍 Analyzing...",
        "step_2": "📥 Downloading: {p}",
        "step_3": "⚙️ Processing...",
        "step_4": "📤 Sending...",
        "promo": "\n\n🚀 <b>Via: @youtodownloadbot</b>"
    }
}


# ============================================================
# FSM
# ============================================================

class DownloadStates(StatesGroup):
    choosing_language = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()


# ============================================================
# ПРОВЕРКА ПОДПИСКИ
# ============================================================

async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False


# ============================================================
# START, МЕНЮ, АДМИНКА — БЕЗ ИЗМЕНЕНИЙ
# ============================================================

# (оставил как есть — не менял)


# ============================================================
# СКАЧИВАНИЕ + ОТПРАВКА
# ============================================================

@video_router.callback_query(F.data.startswith("dl_"))
async def start_dl(callback: types.CallbackQuery, state: FSMContext):
    u_data = await state.get_data()
    url = u_data.get("download_url")
    lang = u_data.get("lang", "ru")

    if not url:
        return await callback.answer("Ошибка: ссылка потеряна")

    parts = callback.data.split("_")
    mode = "audio" if parts[1] == "audio" else "video"
    quality = parts[2] if len(parts) > 2 else None

    try:
        await callback.message.delete()
    except:
        pass

    status = await callback.message.answer(STRINGS[lang]["step_1"], parse_mode="HTML")
    last_upd = [0]

    async def prog_cb(p_str):
        if time.time() - last_upd[0] < 2:
            return
        try:
            await status.edit_text(STRINGS[lang]["step_2"].format(p=p_str), parse_mode="HTML")
            last_upd[0] = time.time()
        except:
            pass

    try:
        res = await downloader.download(url, mode=mode, quality=quality, progress_callback=prog_cb)
        await status.edit_text(STRINGS[lang]["step_3"])

        # Умная отправка
        await send_media_smart(callback, res, lang, mode)

        await status.delete()

    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:100]}")
    finally:
        if 'res' in locals() and os.path.exists(res.path):
            try:
                os.remove(res.path)
            except:
                pass


# ============================================================
# ОТМЕНА
# ============================================================

@video_router.callback_query(F.data == "cancel_download")
async def cancel_dl(callback: types.CallbackQuery, state: FSMContext):
    u_data = await state.get_data()
    lang = u_data.get("lang", "ru")

    try:
        await callback.message.delete()
    except:
        pass

    kb_rows = [
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ]

    if str(callback.from_user.id) == str(conf.admin_id):
        kb_rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])

    await callback.message.answer(
        STRINGS[lang]["welcome"].format(name=callback.from_user.full_name),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
