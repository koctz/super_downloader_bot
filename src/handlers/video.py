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

# Импорты ваших модулей (убедитесь, что пути правильные)
from src.services.downloader import VideoDownloader
from src.db import add_user, get_users, count_users, get_all_user_ids
from src.config import conf

CHANNEL_ID = conf.channel_id
CHANNEL_URL = conf.channel_url

video_router = Router()
downloader = VideoDownloader()

# Инициализируем Telethon
tele_client = TelegramClient('telethon_bot', conf.api_id, conf.api_hash)

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
        "btn_video": "🎬 Видео (Max)",
        "btn_audio": "🎵 Аудио (MP3)",
        "btn_cancel": "❌ Отмена",
        "btn_settings": "⚙️ Настройки",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_back": "⬅️ Назад",
        "link_ok": "Ссылка принята! Выберите качество:",
        "link_ok_general": "Ссылка принята! Что скачиваем?",
        "help_text": "<b>Как пользоваться ботом?</b>\n\nПросто отправь ссылку на видео из TikTok, YouTube, Instagram или VK.",
        "sub_ok": "✅ Спасибо за подписку! Теперь можешь отправлять ссылки.",
        "sub_fail": "❌ Ты всё еще не подписан!",
        "cancel_text": "❌ Действие отменено.",
        "err_lost": "Ошибка: ссылка устарела. Пришли её ещё раз.",
        "step_1": "⏳ <b>[1/4]</b> Анализирую ссылку...",
        "step_2": "📥 <b>[2/4]</b> Загружаю файл на сервер...",
        "step_3": "⚙️ <b>[3/4]</b> Обрабатываю и сжимаю...",
        "step_4": "📤 <b>[4/4]</b> Отправляю файл тебе...",
        "promo": "\n\n🚀 <b>Скачано через: @youtodownloadbot</b>"
    },
    "en": {
        "choose_lang": "Choose language / Выберите язык:",
        "welcome": "Hello, {name}! 👋\n\nI will help you download videos from <b>TikTok, YouTube, Instagram or VK</b>.\nJust send me a link!",
        "sub_req": "⚠️ <b>You must subscribe to our channel to use this bot!</b>",
        "btn_sub": "✅ Subscribe",
        "btn_check_sub": "🔄 Check subscription",
        "btn_channel": "📢 Our Channel",
        "btn_help": "🆘 Help",
        "btn_video": "🎬 Video (Max)",
        "btn_audio": "🎵 Audio (MP3)",
        "btn_cancel": "❌ Cancel",
        "btn_settings": "⚙️ Settings",
        "btn_change_lang": "🌐 Change language",
        "btn_back": "⬅️ Back",
        "link_ok": "Link received! Choose quality:",
        "link_ok_general": "Link received! What to download?",
        "help_text": "Just send a video link from TikTok, YouTube, Instagram or VK.",
        "sub_ok": "✅ Thanks for subscribing! Now you can send links.",
        "sub_fail": "❌ You are still not subscribed!",
        "cancel_text": "❌ Action canceled.",
        "err_lost": "Error: link lost. Send it again.",
        "step_1": "⏳ <b>[1/4]</b> Analyzing link...",
        "step_2": "📥 <b>[2/4]</b> Downloading to server...",
        "step_3": "⚙️ <b>[3/4]</b> Processing...",
        "step_4": "📤 <b>[4/4]</b> Sending file to you...",
        "promo": "\n\n🚀 <b>Via: @youtodownloadbot</b>"
    }
}

class DownloadStates(StatesGroup):
    choosing_language = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False # Лучше вернуть False, чтобы при ошибке просил подписку, или True если канал недоступен

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
    
    kb_rows = [
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ]
    # Приводим оба ID к строке для точного сравнения
    if str(callback.from_user.id) == str(conf.admin_id):
        kb_rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await callback.message.edit_text(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=kb)
    await state.set_state(None)
    await callback.answer()

@video_router.callback_query(F.data == "settings_menu")
async def settings_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear() # Сбрасываем состояния
    data = await state.get_data()
    lang = data.get("lang", "ru")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]["btn_change_lang"], callback_data="change_language")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_back"], callback_data="back_to_main")]
    ])
    try:
        await callback.message.edit_text("⚙️ Настройки", parse_mode="HTML", reply_markup=kb)
    except:
        await callback.message.answer("⚙️ Настройки", parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@video_router.callback_query(F.data == "change_language")
async def change_language_handler(callback: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
        InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
    ]])
    await callback.message.edit_text(STRINGS["ru"]["choose_lang"], reply_markup=kb)

@video_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    kb_rows = [
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ]
    if str(callback.from_user.id) == str(conf.admin_id):
        kb_rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    try:
        await callback.message.edit_text(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=kb)
    except:
        await callback.message.answer(STRINGS[lang]["welcome"].format(name=callback.from_user.full_name), parse_mode="HTML", reply_markup=kb)
    await callback.answer()

# --- ОТМЕНА (FIX) ---
@video_router.callback_query(F.data == "cancel_download")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(download_url=None)
    data = await state.get_data()
    lang = data.get("lang", "ru")
    try:
        await callback.message.delete()
        # Либо можно отредактировать: await callback.message.edit_text(STRINGS[lang]["cancel_text"])
    except:
        pass
    await callback.answer(STRINGS[lang]["cancel_text"])

# --- АДМИН-ПАНЕЛЬ (FIX) ---

@video_router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(conf.admin_id): 
        return await callback.answer("Access denied")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_page_0")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    try:
        await callback.message.edit_text("🛠 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=kb)
    except:
        await callback.message.answer("🛠 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@video_router.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(conf.admin_id): return
    page = int(callback.data.split("_")[-1])
    total = count_users()
    offset = page * 20
    users = get_users(offset=offset, limit=20)
    
    if not users:
        await callback.answer("Нет пользователей")
        return

    # Убедимся что данные есть (индексы зависят от структуры вашей БД, предположим 0=id, 1=username, 3=lang)
    # Если падает ошибка, проверьте что возвращает get_users()
    lines = []
    for u in users:
        try:
            lines.append(f"🟢 <code>{u[0]}</code> — {u[1] or '—'}")
        except: pass
        
    text = f"👥 <b>Пользователи</b>\nВсего: <b>{total}</b>\nСтраница: <b>{page + 1}</b>\n\n" + "\n".join(lines)
    
    buttons = []
    if page > 0: buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_users_page_{page - 1}"))
    if offset + 20 < total: buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_users_page_{page + 1}"))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons, [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# --- ОБРАБОТКА ССЫЛОК (FIX С КНОПКАМИ ЮТУБА) ---

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
    
    # ОПРЕДЕЛЯЕМ ИСТОЧНИК ДЛЯ РАЗНЫХ КНОПОК
    is_youtube = any(x in url.lower() for x in ['youtube.com', 'youtu.be']) and 'shorts' not in url.lower()
    
    rows = []
    if is_youtube:
        # Кнопки качества для YouTube
        rows.append([
            InlineKeyboardButton(text="📹 1080p", callback_data="dl_res_1080"),
            InlineKeyboardButton(text="📹 720p", callback_data="dl_res_720")
        ])
        rows.append([
            InlineKeyboardButton(text="📹 480p", callback_data="dl_res_480"),
            InlineKeyboardButton(text="📹 360p", callback_data="dl_res_360")
        ])
        text_msg = STRINGS[lang]["link_ok"]
    else:
        # Обычные кнопки для Shorts, TikTok, Instagram
        rows.append([InlineKeyboardButton(text=STRINGS[lang]["btn_video"], callback_data="dl_video")])
        text_msg = STRINGS[lang]["link_ok_general"]

    # Кнопка аудио и отмены общие для всех
    rows.append([InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")])
    rows.append([InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(text_msg, parse_mode="HTML", reply_markup=kb)

@video_router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.message.edit_text(STRINGS[lang]["sub_ok"], parse_mode="HTML")
    else:
        await callback.answer(STRINGS[lang]["sub_fail"], show_alert=True)

# --- СКАЧИВАНИЕ И ПРОГРЕСС (FIX) ---

@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = user_data.get("download_url")
    lang = user_data.get("lang", "ru")
    
    if not url:
        await callback.message.edit_text(STRINGS[lang]["err_lost"])
        return

    # Разбор callback_data
    # Возможные варианты: dl_video, dl_audio, dl_res_1080, dl_res_720 ...
    action_parts = callback.data.split("_")
    
    mode = 'video'
    quality = None
    
    if action_parts[1] == 'audio':
        mode = 'audio'
    elif action_parts[1] == 'res':
        mode = 'video'
        quality = action_parts[2] # 1080, 720 и т.д.
    else:
        mode = 'video' # default (best)

    status_msg = await callback.message.edit_text(STRINGS[lang]["step_1"], parse_mode="HTML")
    video_path = None
    last_edit = [time.time()]

    async def download_progress(p_str):
        if time.time() - last_edit[0] < 3: return
        try:
            await status_msg.edit_text(f"📥 <b>[2/4]</b> Загружаю на сервер: <b>{p_str}</b>", parse_mode="HTML")
            last_edit[0] = time.time()
        except: pass

    async def upload_progress(current, total):
        if time.time() - last_edit[0] < 3: return
        percent = (current / total) * 100
        try:
            await status_msg.edit_text(f"📤 <b>[4/4]</b> Отправляю тебе: <b>{percent:.1f}%</b>", parse_mode="HTML")
            last_edit[0] = time.time()
        except: pass

    try:
        # Передаем параметр quality в загрузчик
        video_data = await downloader.download(url, mode=mode, quality=quality, progress_callback=download_progress)
        
        video_path = video_data.path
        await status_msg.edit_text(STRINGS[lang]["step_3"], parse_mode="HTML")
        
        if not tele_client.is_connected():
            await tele_client.start(bot_token=conf.bot_token)

        file_size_mb = os.path.getsize(video_path) / (1024*1024)
        
        # Формируем подпись
        res_text = f" ({quality}p)" if quality else ""
        caption = f"🎬 <b>{video_data.title[:800]}</b>{res_text}{STRINGS[lang]['promo']}"
        if mode == 'audio':
             caption = f"🎵 <b>{video_data.title[:900]}</b>{STRINGS[lang]['promo']}"

        chat_id = callback.message.chat.id
        
        if mode == 'video':
            attr = [DocumentAttributeVideo(
                duration=int(video_data.duration or 0), 
                w=video_data.width or 0, 
                h=video_data.height or 0, 
                supports_streaming=True
            )]
            await tele_client.send_file(
                chat_id, video_path, 
                caption=caption, 
                attributes=attr, 
                parse_mode='html', 
                progress_callback=upload_progress if file_size_mb > 5 else None
            )
        else:
            await tele_client.send_file(
                chat_id, video_path, 
                caption=caption, 
                parse_mode='html',
                progress_callback=upload_progress if file_size_mb > 5 else None
            )
        
        await status_msg.delete()
        
    except Exception as e:
        print(f"Global Error: {e}")
        try: await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        except: pass
    finally:
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except: pass

# --- АДМИНКА РАССЫЛКА ---

@video_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(conf.admin_id): return
    await callback.message.answer("Пришли сообщение для рассылки.")
    await state.set_state(AdminStates.waiting_for_broadcast)

@video_router.message(AdminStates.waiting_for_broadcast)
async def perform_broadcast(message: types.Message, state: FSMContext):
    user_ids = get_all_user_ids()
    count, blocked = 0, 0
    status = await message.answer("🚀 Рассылка запущена...")
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=int(uid))
            count += 1
            await asyncio.sleep(0.05)
        except: blocked += 1
    await status.edit_text(f"✅ Готово!\nОтправлено: {count}\nЗаблокировано: {blocked}")
    await state.clear()
