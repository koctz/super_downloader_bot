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

class DownloadStates(StatesGroup):
    choosing_language = State()
    choosing_format = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

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
        "sub_req": "⚠️ <b>Для использования бота нужно подписаться на наш канал!</b>",
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
        "cancel_text": "Действие отменено. Отправь мне новую ссылку 👇",
        "err_lost": "Ошибка: ссылка потерялась. Пришли её ещё раз.",
        "step_1": "⏳ <b>[1/4]</b> Анализирую ссылку...",
        "step_2": "📥 <b>[2/4]</b> Загружаю на сервер...",
        "step_3": "⚙️ <b>[3/4]</b> Обрабатываю...",
        "step_4": "📤 <b>[4/4]</b> Отправляю...",
        "promo": "\n\n🚀 <b>Скачано через: @youtodownloadbot</b>"
    },
    "en": {
        "choose_lang": "Choose language:",
        "welcome": "Hello, {name}! 👋\n\nSend me a link!",
        "sub_req": "⚠️ <b>Subscribe to our channel!</b>",
        "btn_sub": "✅ Subscribe",
        "btn_check_sub": "🔄 Check sub",
        "btn_channel": "📢 Our Channel",
        "btn_help": "🆘 Help",
        "btn_video": "🎬 Video",
        "btn_audio": "🎵 Audio",
        "btn_cancel": "❌ Cancel",
        "btn_settings": "⚙️ Settings",
        "btn_change_lang": "🌐 Language",
        "btn_back": "⬅️ Back",
        "link_ok": "Link received!",
        "cancel_text": "Canceled.",
        "err_lost": "Error: link lost.",
        "step_1": "⏳ Analyzing...",
        "step_2": "📥 Downloading...",
        "step_3": "⚙️ Processing...",
        "step_4": "📤 Sending...",
        "promo": "\n\n🚀 <b>Via: @youtodownloadbot</b>"
    }
}

async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# --- ХЕНДЛЕРЫ СТАРТА ---

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
    kb = get_main_keyboard(lang, callback.from_user.id)
    await callback.message.edit_text(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=kb)

# --- АДМИН-ПАНЕЛЬ (ИСПРАВЛЕНО) ---

@video_router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if str(callback.from_user.id) != str(conf.admin_id): return
    total = count_users()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👥 Пользователи ({total})", callback_data="admin_users_0")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=kb)

@video_router.callback_query(F.data.startswith("admin_users_"))
async def admin_users_list(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    users = get_users(limit=10, offset=page*10)
    text = f"👥 <b>Список пользователей (Стр. {page+1}):</b>\n\n"
    for u in users:
        text += f"ID: <code>{u[0]}</code> | @{u[1] or 'no'} | {u[2]}\n"
    
    kb = []
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_{page-1}"))
    nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_users_{page+1}"))
    kb.append(nav)
    kb.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_panel")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@video_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введите текст для рассылки всем пользователям:")
    await state.set_state(AdminStates.waiting_for_broadcast)

@video_router.message(AdminStates.waiting_for_broadcast)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    user_ids = get_all_user_ids()
    count = 0
    await message.answer(f"🚀 Начинаю рассылку на {len(user_ids)} чел...")
    for uid in user_ids:
        try:
            await message.copy_to(uid)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка завершена. Получили: {count} чел.")
    await state.set_state(None)

# --- ОБРАБОТКА ВИДЕО (ИСПРАВЛЕНО) ---

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
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
    
    is_youtube = any(domain in url for domain in ["youtube.com", "youtu.be"])
    is_shorts = "shorts" in url

    yt_info = None
    if is_youtube and not is_shorts:
        wait_msg = await message.answer("⏳ Анализирую...")
        yt_info = await downloader.get_formats(url)
        await wait_msg.delete()

    if yt_info and yt_info.get("formats"):
        # YouTube с ПРЕВЬЮ и КАЧЕСТВОМ
        kb_list = []
        row = []
        for q in yt_info['formats']:
            row.append(InlineKeyboardButton(text=f"📺 {q}p", callback_data=f"dl_video_{q}"))
            if len(row) == 2:
                kb_list.append(row); row = []
        if row: kb_list.append(row)
        kb_list.append([InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")])
        kb_list.append([InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")])
        
        caption = f"🎬 <b>{yt_info['title']}</b>\n👤 {yt_info['uploader']}"
        await message.answer_photo(photo=yt_info['thumbnail'], caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
    else:
        # TikTok / Shorts / VK
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=STRINGS[lang]["btn_video"], callback_data="dl_video"),
             InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")],
            [InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")]
        ])
        await message.answer(STRINGS[lang]["link_ok"], reply_markup=kb)

@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = user_data.get("download_url")
    lang = user_data.get("lang", "ru")
    if not url: return await callback.answer(STRINGS[lang]["err_lost"])

    parts = callback.data.split("_")
    mode = parts[1]
    quality = parts[2] if len(parts) > 2 else None

    # Заменяем превью/кнопки на статус
    if callback.message.photo:
        status_msg = await callback.message.answer(STRINGS[lang]["step_1"])
        await callback.message.delete()
    else:
        status_msg = await callback.message.edit_text(STRINGS[lang]["step_1"])
    
    video_path = None
    # Явно берем текущий цикл событий
    current_loop = asyncio.get_event_loop()

    # Функция для безопасного обновления текста из любого потока
    def sync_progress_caller(p_str):
        async def update_text():
            try:
                await status_msg.edit_text(f"📥 <b>[2/4]</b> Загрузка: {p_str}", parse_mode="HTML")
            except:
                pass
        # Прокидываем задачу в основной поток
        asyncio.run_coroutine_threadsafe(update_text(), current_loop)

    async def upload_progress(current, total):
        p = (current / total) * 100
        try:
            await status_msg.edit_text(f"📤 <b>[4/4]</b> Отправка: {p:.1f}%", parse_mode="HTML")
        except:
            pass

    try:
        # Передаем нашу обертку progress_callback
        video_data = await downloader.download(
            url, 
            mode=mode, 
            progress_callback=sync_progress_caller, 
            quality=quality
        )
        
        video_path = video_data.path
        await status_msg.edit_text(STRINGS[lang]["step_3"])
        
        if not tele_client.is_connected():
            await tele_client.start(bot_token=conf.bot_token)
        
        caption = f"🎬 <b>{video_data.title[:900]}</b>{STRINGS[lang]['promo']}"
        attr = [DocumentAttributeVideo(
            duration=int(video_data.duration or 0), 
            w=video_data.width, 
            h=video_data.height, 
            supports_streaming=True
        )]
        
        await tele_client.send_file(
            callback.message.chat.id, 
            video_path, 
            caption=caption, 
            attributes=attr if mode=='video' else [], 
            parse_mode='html', 
            progress_callback=upload_progress
        )
        await status_msg.delete()
    except Exception as e:
        print(f"Download Error: {e}")
        try:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:50]}")
        except:
            pass
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)

@video_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data(); lang = data.get("lang", "ru")
    await callback.message.edit_text(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=get_main_keyboard(lang, callback.from_user.id))
