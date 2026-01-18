import os
import asyncio
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from telethon import TelegramClient

from src.services.downloader import VideoDownloader
from src.db import add_user
from src.config import conf

CHANNEL_ID = conf.channel_id
CHANNEL_URL = conf.channel_url

video_router = Router()
downloader = VideoDownloader()

# Инициализируем Telethon (в режиме бота)
# 'bot_session' — имя файла сессии
tele_client = TelegramClient('bot_session', conf.api_id, conf.api_hash)

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

# Состояния
class DownloadStates(StatesGroup):
    choosing_language = State()
    choosing_format = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

# --- СЛУЖЕБНЫЕ ФУНКЦИИ ---
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

    # Запись пользователя в SQLite
    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        lang="ru"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
        ]
    ])
    await message.answer(STRINGS["ru"]["choose_lang"], reply_markup=kb)
    await state.set_state(DownloadStates.choosing_language)


@video_router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(lang=lang)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ])

    if str(callback.from_user.id) == str(conf.admin_id):
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text="🛠 Админ‑панель", callback_data="admin_panel")]
        )

    await callback.message.edit_text(
        STRINGS[lang]["welcome"].format(name=callback.from_user.full_name),
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(None)
    await callback.answer()

# --- МЕНЮ НАСТРОЕК ---

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

@video_router.callback_query(F.data == "change_language")
async def change_language(callback: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
        ]
    ])

    await callback.message.edit_text(
        STRINGS["ru"]["choose_lang"],
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(DownloadStates.choosing_language)
    await callback.answer()

@video_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ])

    if str(callback.from_user.id) == str(conf.admin_id):
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text="🛠 Админ‑панель", callback_data="admin_panel")]
        )

    await callback.message.edit_text(
        STRINGS[lang]["welcome"].format(name=callback.from_user.full_name),
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

# --- АДМИН-ПАНЕЛЬ ---

@video_router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(conf.admin_id):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_page_0")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])

    await callback.message.edit_text("🛠 <b>Админ‑панель</b>", parse_mode="HTML", reply_markup=kb)
    await callback.answer()

USERS_PER_PAGE = 20

from src.db import get_users, count_users

USERS_PER_PAGE = 20

@video_router.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(conf.admin_id):
        return

    page = int(callback.data.split("_")[-1])
    total = count_users()

    offset = page * USERS_PER_PAGE
    users = get_users(offset=offset, limit=USERS_PER_PAGE)

    if not users:
        await callback.message.edit_text("Пользователей пока нет.", parse_mode="HTML")
        await callback.answer()
        return

    lines = []
    for uid, username, full_name, lang, downloads, last_active in users:
        status = "🟢"
        lines.append(
            f"{status} <code>{uid}</code> — {username or '—'} — {lang.upper()} — DL: {downloads}"
        )

    text = (
        f"👥 <b>Пользователи</b>\n"
        f"Всего: <b>{total}</b>\n"
        f"Страница: <b>{page + 1}</b>\n\n" +
        "\n".join(lines)
    )

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_users_page_{page - 1}"))
    if offset + USERS_PER_PAGE < total:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_users_page_{page + 1}"))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        buttons if buttons else [],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

# --- ОБРАБОТКА ССЫЛОК ---

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
    # SQLite
    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        lang="ru"
    )

    data = await state.get_data()
    lang = data.get("lang", "ru")

    if not await is_subscribed(message.bot, message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=STRINGS[lang]["btn_sub"], url=CHANNEL_URL)],
            [InlineKeyboardButton(text=STRINGS[lang]["btn_check_sub"], callback_data="check_sub")]
        ])
        await message.answer(STRINGS[lang]["sub_req"], parse_mode="HTML", reply_markup=kb)
        return

    await state.update_data(download_url=message.text.strip())

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=STRINGS[lang]["btn_video"], callback_data="dl_video"),
            InlineKeyboardButton(text=STRINGS[lang]["btn_audio"], callback_data="dl_audio")
        ],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_cancel"], callback_data="cancel_download")]
    ])

    await message.answer(STRINGS[lang]["link_ok"], parse_mode="HTML", reply_markup=kb)
    await state.set_state(DownloadStates.choosing_format)

@video_router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.message.edit_text(STRINGS[lang]["sub_ok"], parse_mode="HTML")
    else:
        await callback.answer(STRINGS[lang]["sub_fail"], show_alert=True)

@video_router.callback_query(F.data == "help_info")
async def help_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await callback.message.answer(STRINGS[lang]["help_text"], parse_mode="HTML")
    await callback.answer()

@video_router.callback_query(F.data == "cancel_download")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]["btn_channel"], url=CHANNEL_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_help"], callback_data="help_info")],
        [InlineKeyboardButton(text=STRINGS[lang]["btn_settings"], callback_data="settings_menu")]
    ])

    if str(callback.from_user.id) == str(conf.admin_id):
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text="🛠 Админ‑панель", callback_data="admin_panel")]
        )

    await callback.message.edit_text(STRINGS[lang]["cancel_text"], parse_mode="HTML", reply_markup=kb)
    await callback.answer()

# --- СКАЧИВАНИЕ ---

@video_router.callback_query(F.data.startswith("dl_"))
async def handle_download(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = user_data.get("download_url")
    lang = user_data.get("lang", "ru")

    if not url:
        await callback.answer(STRINGS[lang]["err_lost"], show_alert=True)
        return

    mode = callback.data.split("_")[1]
    status_msg = await callback.message.edit_text(STRINGS[lang]["step_1"], parse_mode="HTML")

    video_path = None
    try:
        action = ChatActionSender.upload_video if mode == 'video' else ChatActionSender.upload_document
        async with action(chat_id=callback.message.chat.id, bot=callback.bot):
            await status_msg.edit_text(STRINGS[lang]["step_2"], parse_mode="HTML")
            
            # Скачиваем файл через downloader
            video_data = await downloader.download(url, mode=mode)
            video_path = video_data.path
            
            # Проверяем размер файла в МБ
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            print(f"DEBUG: File size: {file_size_mb:.2f} MB")

            await status_msg.edit_text(STRINGS[lang]["step_3"], parse_mode="HTML")
            await status_msg.edit_text(STRINGS[lang]["step_4"], parse_mode="HTML")

            clean_title = video_data.title[:900]
            caption = f"🎬 <b>{clean_title}</b>{STRINGS[lang]['promo']}"

            # --- ВЫБОР СПОСОБА ОТПРАВКИ ---
            if file_size_mb > 50:
                # Отправка через Telethon (MTProto)
                # Передаем bot_token для авторизации, если еще не авторизованы
                if not tele_client.is_connected():
                    await tele_client.start(bot_token=conf.bot_token)
                
                if mode == 'video':
                    await tele_client.send_file(
                        callback.message.chat.id,
                        video_path,
                        caption=caption,
                        supports_streaming=True,
                        attributes=[
                            # Это добавит метаданные видео (длительность и размер)
                            type(video_data).width if hasattr(video_data, 'width') else 0, 
                            type(video_data).height if hasattr(video_data, 'height') else 0
                        ] if mode == 'video' else []
                    )
                else:
                    await tele_client.send_file(
                        callback.message.chat.id,
                        video_path,
                        caption=f"🎵 <b>{clean_title}</b>{STRINGS[lang]['promo']}",
                        voice=False # Отправляем как музыку
                    )
            from src.db import increment_downloads
            increment_downloads(callback.from_user.id)

            await status_msg.delete()
            await state.clear()

    except Exception as e:
        print(f"ERROR in handle_download: {e}")
        err_text = str(e)
        msg = f"❌ Error: {err_text[:100]}"
        if "Too Large" in err_text:
            msg = STRINGS[lang]["err_heavy"]
        elif "Timeout" in err_text:
            msg = STRINGS[lang]["err_timeout"]
        await status_msg.edit_text(msg, parse_mode="HTML")
        await state.clear()
        
    finally:
        # Удаляем файл в любом случае
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass

# --- АДМИНКА: РАССЫЛКА ---

from src.db import get_all_user_ids

@video_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(conf.admin_id):
        return

    await callback.message.answer("Пришли сообщение для рассылки.", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()


@video_router.message(AdminStates.waiting_for_broadcast)
async def perform_broadcast(message: types.Message, state: FSMContext):

    user_ids = get_all_user_ids()

    if not user_ids:
        await message.answer("❌ Нет пользователей в базе.", parse_mode="HTML")
        await state.clear()
        return

    count, blocked = 0, 0
    status_msg = await message.answer("🚀 Рассылка запущена...", parse_mode="HTML")

    for user_id in user_ids:
        try:
            await message.copy_to(chat_id=int(user_id))
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            blocked += 1
            continue

    await status_msg.edit_text(
        f"✅ Готово!\n\n"
        f"Отправлено: <b>{count}</b>\n"
        f"Недоступно: <b>{blocked}</b>",
        parse_mode="HTML"
    )

    # ← ВОТ ТУТ, В КОНЦЕ
    await state.clear()

