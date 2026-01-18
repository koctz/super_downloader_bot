import os
import time
import asyncio
import re
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo

from src.services.downloader import VideoDownloader
from src.db import add_user, get_users, count_users, get_all_user_ids
from src.config import conf

CHANNEL_ID = conf.channel_id
CHANNEL_URL = conf.channel_url

video_router = Router()
downloader = VideoDownloader()

# Инициализируем Telethon
tele_client = TelegramClient('telethon_bot', conf.api_id, conf.api_hash)

def get_main_keyboard(lang: str, user_id: int):
    kb_list = [
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ]
    if str(user_id) == str(conf.admin_id):
        kb_list.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb_list)

# --- ЛОКАЛИЗАЦИЯ ---
STRINGS = {
    "ru": {
        "choose_lang": "Выберите язык / Choose language:",
        "welcome": "Привет, {name}! 👋\n\nЯ помогу тебе скачать видео из <b>TikTok, YouTube, Instagram или VK</b>.\nПросто пришли мне ссылку!",
        "sub_req": "⚠️ <b>Для использования бота нужно подписаться на наш канал!</b>\n\nЭто помогает нам поддерживать сервер в рабочем состоянии.",
        "btn_sub": "✅ Подписаться",
        "btn_check_sub": "🔄 Проверить подписку",
        "btn_channel": "📢 Наш канал",
        "btn_help": "🆘 Помощь",
        "btn_video": "🎬 Видео",
        "btn_audio": "🎵 Аудио (MP3)",
        "btn_cancel": "❌ Отмена",
        "btn_settings": "⚙️ Настройки",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_back": "⬅️ Назад",
        "link_ok": "Ссылка принята! Что именно скачиваем?",
        "help_text": "<b>Как пользоваться ботом?</b>\n\nПросто отправь ссылку на видео из TikTok, YouTube, Instagram или VK — я сам предложу варианты скачивания.",
        "sub_ok": "✅ Спасибо за подписку! Теперь можешь отправлять ссылки.",
        "sub_fail": "❌ Ты всё еще не подписан!",
        "cancel_text": "Действие отменено. Отправь мне новую ссылку 👇",
        "err_lost": "Ошибка: ссылка потерялась. Пришли её ещё раз.",
        "step_1": "⏳ <b>[1/4]</b> Анализирую ссылку...",
        "step_2": "📥 <b>[2/4]</b> Загружаю файл на сервер...",
        "step_3": "⚙️ <b>[3/4]</b> Обрабатываю и сжимаю...",
        "step_4": "📤 <b>[4/4]</b> Отправляю файл тебе...",
        "promo": "\n\n🚀 <b>Скачано через: @youtodownloadbot</b>",
        "err_heavy": "❌ Видео слишком тяжелое для Telegram.",
        "err_timeout": "❌ Видео обрабатывалось слишком долго. Попробуй другое."
    },
    "en": {
        "choose_lang": "Choose language / Выберите язык:",
        "welcome": "Hello, {name}! 👋\n\nI will help you download videos from <b>TikTok, YouTube, Instagram or VK</b>.\nJust send me a link!",
        "sub_req": "⚠️ <b>You must subscribe to our channel to use this bot!</b>\n\nThis helps us keep the server running.",
        "btn_sub": "✅ Subscribe",
        "btn_check_sub": "🔄 Check subscription",
        "btn_channel": "📢 Our Channel",
        "btn_help": "🆘 Help",
        "btn_video": "🎬 Video",
        "btn_audio": "🎵 Audio (MP3)",
        "btn_cancel": "❌ Cancel",
        "btn_settings": "⚙️ Settings",
        "btn_change_lang": "🌐 Change language",
        "btn_back": "⬅️ Back",
        "link_ok": "Link received! What should I download?",
        "help_text": "<b>How to use the bot?</b>\n\nJust send a video link from TikTok, YouTube, Instagram or VK — I will offer download options.",
        "sub_ok": "✅ Thanks for subscribing! Now you can send links.",
        "sub_fail": "❌ You are still not subscribed!",
        "cancel_text": "Action canceled. Send me a new link 👇",
        "err_lost": "Error: link lost. Send it again.",
        "step_1": "⏳ <b>[1/4]</b> Analyzing link...",
        "step_2": "📥 <b>[2/4]</b> Downloading to server...",
        "step_3": "⚙️ <b>[3/4]</b> Processing and compressing...",
        "step_4": "📤 <b>[4/4]</b> Sending file to you...",
        "promo": "\n\n🚀 <b>Via: @youtodownloadbot</b>",
        "err_heavy": "❌ Video is too heavy for Telegram.",
        "err_timeout": "❌ Processing timeout. Try another video."
    }
}

class DownloadStates(StatesGroup):
    choosing_language = State()
    choosing_format = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- ХЕНДЛЕРЫ ---

@video_router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    add_user(user_id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name, lang="ru")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
        InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
    ]])
    await message.answer(STRINGS["ru"]["choose_lang"], reply_markup=kb)
    await state.set_state(DownloadStates.choosing_language)

@video_router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(lang=lang)
    kb = get_main_keyboard(lang, callback.from_user.id)
    await callback.message.edit_text(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=kb)
    await state.set_state(None)
    await callback.answer()

@video_router.callback_query(F.data == "settings_menu")
async def settings_menu(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]["btn_change_lang"], callback_data="change_language")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_back"], callback_data="back_to_main")]
    ])
    await callback.message.edit_text("⚙️ Настройки", parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@video_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    kb = get_main_keyboard(lang, callback.from_user.id)
    await callback.message.edit_text(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=kb)
    await callback.answer()

# --- ОБРАБОТКА ССЫЛОК ---

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
    add_user(user_id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name, lang="ru")
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    if not await is_subscribed(message.bot, message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=STRINGS[lang]["btn_sub"], url=CHANNEL_URL)],
            [InlineKeyboardButton(text=STRINGS[lang]["btn_check_sub"], callback_data="check_sub")]
        ])
        await message.answer(STRINGS[lang]["sub_req"], parse_mode="HTML", reply_markup=kb)
        return

    url = message.text.strip()
    await state.update_data(download_url=url)
    
    # Проверяем, является ли это обычным YouTube видео (не Shorts)
    is_youtube = any(domain in url for domain in ["youtube.com", "youtu.be"])
    is_shorts = "shorts" in url

    # Пытаемся получить форматы только для обычного YouTube
    yt_info = None
    if is_youtube and not is_shorts:
        wait_msg = await message.answer("⏳ Анализирую видео...")
        yt_info = await downloader.get_formats(url)
        await wait_msg.delete()

    if yt_info and yt_info.get("formats"):
        # Обычный YouTube с кнопками качества и превью
        caption = (f"🎬 <b>{yt_info['title']}</b>\n\n"
                   f"👤 Канал: <a href='{yt_info['uploader_url']}'>{yt_info['uploader']}</a>\n"
                   f"⚙️ Выберите качество видео или аудио:")
        
        kb_list = []
        row = []
        for q in yt_info['formats']:
            row.append(InlineKeyboardButton(text=f"📺 {q}p", callback_data=f"dl_video_{q}"))
            if len(row) == 2:
                kb_list.append(row)
                row = []
        if row: kb_list.append(row)
        
        kb_list.append([InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")])
        kb_list.append([InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")])
        
        await message.answer_photo(
            photo=yt_info['thumbnail'], 
            caption=caption, 
            parse_mode="HTML", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list)
        )
    else:
        # Для Shorts, TikTok, VK, Insta (как и было)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=STRINGS[lang]["btn_video"], callback_data="dl_video"),
             InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")],
            [InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")]
        ])
        await message.answer(STRINGS[lang]["link_ok"], parse_mode="HTML", reply_markup=kb)

@video_router.callback_query(F.data == "cancel_download")
async def cancel_download_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.update_data(download_url=None)
    kb = get_main_keyboard(lang, callback.from_user.id)
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(STRINGS[lang]["cancel_text"], parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.edit_text(STRINGS[lang]["cancel_text"], parse_mode="HTML", reply_markup=kb)
    await callback.answer()

# --- СКАЧИВАНИЕ И ПРОГРЕСС ---

@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = user_data.get("download_url")
    lang = user_data.get("lang", "ru")
    if not url:
        await callback.answer(STRINGS[lang]["err_lost"], show_alert=True)
        return

    # Парсим mode и quality
    # dl_video_720 -> parts=["dl", "video", "720"]
    # dl_video -> parts=["dl", "video"]
    parts = callback.data.split("_")
    mode = parts[1]
    quality = parts[2] if len(parts) > 2 else None

    if callback.message.photo:
        status_msg = await callback.message.answer(STRINGS[lang]["step_1"], parse_mode="HTML")
        await callback.message.delete()
    else:
        status_msg = await callback.message.edit_text(STRINGS[lang]["step_1"], parse_mode="HTML")
    
    video_path = None
    last_edit = [time.time()]

    async def download_progress(p_str):
        if time.time() - last_edit[0] < 4: return
        try:
            await status_msg.edit_text(f"📥 <b>[2/4]</b> Загружаю на сервер: <b>{p_str}</b>", parse_mode="HTML")
            last_edit[0] = time.time()
        except: pass

    async def upload_progress(current, total):
        if time.time() - last_edit[0] < 4: return
        percent = (current / total) * 100
        try:
            await status_msg.edit_text(f"📤 <b>[4/4]</b> Отправляю тебе: <b>{percent:.1f}%</b>", parse_mode="HTML")
            last_edit[0] = time.time()
        except: pass

    try:
        # Передаем и mode (video/audio) и quality (None или число)
        video_data = await downloader.download(url, mode=mode, progress_callback=download_progress, quality=quality)
        video_path = video_data.path
        await status_msg.edit_text(STRINGS[lang]["step_3"], parse_mode="HTML")
        
        if not tele_client.is_connected():
            await tele_client.start(bot_token=conf.bot_token)

        file_size = os.path.getsize(video_path) / (1024*1024)
        caption = f"🎬 <b>{video_data.title[:900]}</b>{STRINGS[lang]['promo']}"

        if mode == 'video':
            attr = [DocumentAttributeVideo(duration=int(video_data.duration or 0), 
                    w=video_data.width or 0, h=video_data.height or 0, supports_streaming=True)]
            await tele_client.send_file(callback.message.chat.id, video_path, caption=caption, 
                    attributes=attr, parse_mode='html', 
                    progress_callback=upload_progress if file_size > 5 else None)
        else:
            await tele_client.send_file(callback.message.chat.id, video_path, 
                    caption=f"🎵 <b>{video_data.title[:900]}</b>", parse_mode='html',
                    progress_callback=upload_progress if file_size > 5 else None)
        await status_msg.delete()
    except Exception as e:
        print(f"Error: {e}")
        try: await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
        except: pass
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
