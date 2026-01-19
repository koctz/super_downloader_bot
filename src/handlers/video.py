import os
import time
import asyncio
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo

from src.services.downloader import VideoDownloader
from src.db import add_user, count_users, get_all_user_ids
from src.config import conf

video_router = Router()
downloader = VideoDownloader()

CHANNEL_ID = conf.channel_id
CHANNEL_URL = conf.channel_url

# Инициализируем Telethon
tele_client = TelegramClient('telethon_bot', conf.api_id, conf.api_hash)

STRINGS = {
    "ru": {
        "choose_lang": "Выберите язык / Choose language:",
        "welcome": "Привет, {name}! 👋\n\nЯ помогу тебе скачать видео из <b>TikTok, YouTube, Instagram или VK</b>.\nПросто пришли мне ссылку!",
        "sub_req": "⚠️ <b>Для использования бота нужно подписаться на наш канал!</b>",
        "btn_sub": "✅ Подписаться",
        "btn_check_sub": "🔄 Проверить подписку",
        "btn_channel": "📢 Наш канал",
        "btn_settings": "⚙️ Настройки",
        "btn_video": "🎬 Видео (Max)",
        "btn_audio": "🎵 Аудио (MP3)",
        "btn_cancel": "❌ Отмена",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_back": "⬅️ Назад",
        "link_ok": "Выберите качество видео:",
        "link_ok_general": "Ссылка принята! Что скачиваем?",
        "step_1": "🔍 Анализирую ссылку...",
        "step_2": "📥 Загружаю: {p}",
        "step_3": "⚙️ Обработка файла...",
        "promo": "\n\n🚀 <b>Скачано через: @youtodownloadbot</b>"
    },
    "en": {
        "choose_lang": "Choose language / Выберите язык:",
        "welcome": "Hello, {name}! 👋\n\nI can download from <b>TikTok, YouTube, Instagram or VK</b>.",
        "sub_req": "⚠️ <b>Please subscribe to our channel!</b>",
        "btn_sub": "✅ Subscribe",
        "btn_check_sub": "🔄 Check",
        "btn_channel": "📢 Channel",
        "btn_settings": "⚙️ Settings",
        "btn_video": "🎬 Video (Max)",
        "btn_audio": "🎵 Audio (MP3)",
        "btn_cancel": "❌ Cancel",
        "btn_change_lang": "🌐 Language",
        "btn_back": "⬅️ Back",
        "link_ok": "Choose video quality:",
        "link_ok_general": "Link accepted! What to download?",
        "step_1": "🔍 Analyzing...",
        "step_2": "Downloading: {p}",
        "step_3": "⚙️ Processing...",
        "promo": "\n\n🚀 <b>Via: @youtodownloadbot</b>"
    }
}

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

@video_router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    add_user(user_id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name, lang="ru")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
        InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
    ]])
    await message.answer(STRINGS["ru"]["choose_lang"], reply_markup=kb)

@video_router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(lang=lang)
    kb_rows = [
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ]
    if str(callback.from_user.id) == str(conf.admin_id):
        kb_rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])
    await callback.message.edit_text(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def handle_url(message: types.Message, state: FSMContext):
    u_data = await state.get_data()
    lang = u_data.get("lang", "ru")
    
    if not await is_subscribed(message.bot, message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=STRINGS[lang]["btn_sub"], url=CHANNEL_URL)],
            [InlineKeyboardButton(text=STRINGS[lang]["btn_check_sub"], callback_data="check_sub")]
        ])
        return await message.answer(STRINGS[lang]["sub_req"], parse_mode="HTML", reply_markup=kb)

    url = message.text.strip()
    await state.update_data(download_url=url)
    
    tmp = await message.answer(STRINGS[lang]["step_1"])
    info = await downloader.get_video_info(url)
    
    is_yt = any(x in url.lower() for x in ['youtube.com', 'youtu.be']) and 'shorts' not in url.lower()
    
    rows = []
    if is_yt:
        rows.append([InlineKeyboardButton(text="📹 1080p", callback_data="dl_res_1080"), InlineKeyboardButton(text="📹 720p", callback_data="dl_res_720")])
        rows.append([InlineKeyboardButton(text="📹 480p", callback_data="dl_res_480"), InlineKeyboardButton(text="📹 360p", callback_data="dl_res_360")])
    else:
        rows.append([InlineKeyboardButton(text=STRINGS[lang]["btn_video"], callback_data="dl_video")])
    
    rows.append([InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")])
    rows.append([InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await tmp.delete()

    title = info['title'] if info else "Video"
    caption = f"🎬 <b>{title}</b>\n\n{STRINGS[lang]['link_ok'] if is_yt else STRINGS[lang]['link_ok_general']}"
    
    if info and info.get('thumbnail'):
        await message.answer_photo(photo=info['thumbnail'], caption=caption, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(caption, parse_mode="HTML", reply_markup=kb)

@video_router.callback_query(F.data.startswith("dl_"))
async def start_dl(callback: types.CallbackQuery, state: FSMContext):
    u_data = await state.get_data()
    url = u_data.get("download_url")
    lang = u_data.get("lang", "ru")
    
    if not url: return await callback.answer("Ошибка: ссылка потеряна")

    parts = callback.data.split("_")
    # --- ИСПРАВЛЕННАЯ ЛОГИКА ОПРЕДЕЛЕНИЯ КАЧЕСТВА ---
    if parts[1] == 'audio':
        mode, quality = 'audio', None
    elif parts[1] == 'res':
        mode, quality = 'video', parts[2] # Берет 1080, 720 и т.д.
    else:
        mode, quality = 'video', None

    try: await callback.message.delete()
    except: pass
    
    status = await callback.message.answer(STRINGS[lang]["step_1"], parse_mode="HTML")
    last_upd = [0]

    async def prog_cb(p_str):
        if time.time() - last_upd[0] < 2: return
        try:
            await status.edit_text(STRINGS[lang]["step_2"].format(p=p_str), parse_mode="HTML")
            last_upd[0] = time.time()
        except: pass

    try:
        res = await downloader.download(url, mode=mode, quality=quality, progress_callback=prog_cb)
        await status.edit_text(STRINGS[lang]["step_3"])
        
        if not tele_client.is_connected(): await tele_client.start(bot_token=conf.bot_token)
        
        cap = f"🎬 <b>{res.title}</b>{STRINGS[lang]['promo']}"
        if mode == 'audio': cap = f"🎵 <b>{res.title}</b>{STRINGS[lang]['promo']}"

        await tele_client.send_file(
            callback.message.chat.id, 
            res.path, 
            caption=cap, 
            parse_mode='html',
            supports_streaming=True,
            attributes=[DocumentAttributeVideo(
                duration=res.duration, 
                w=res.width, 
                h=res.height, 
                supports_streaming=True
            )] if mode == 'video' else []
        )
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:100]}")
    finally:
        if 'res' in locals() and os.path.exists(res.path): 
            try: os.remove(res.path)
            except: pass
