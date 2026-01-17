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

# --- ЛОКАЛИЗАЦИЯ ---
STRINGS = {
    "ru": {
        "choose_lang": "<b>Выберите язык / Choose language:</b>",
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
        "help_text": "Просто отправь ссылку на видео из TikTok, YT или Insta. Бот сам предложит варианты скачивания.",
        "sub_ok": "✅ Спасибо за подписку! Теперь можешь отправлять ссылки.",
        "sub_fail": "❌ Ты всё еще не подписан!",
        "cancel_text": "Действие отменено. Отправь мне новую ссылку, и я всё скачаю! 👇",
        "err_lost": "Ошибка: ссылка потерялась. Пришли её ещё раз.",
        "step_1": "⏳ [1/4] Анализирую ссылку...",
        "step_2": "📥 [2/4] Загружаю файл на сервер...",
        "step_3": "⚙️ [3/4] Обрабатываю и сжимаю...",
        "step_4": "📤 [4/4] Отправляю файл тебе...",
        "promo": "\n\n🚀 <b>Скачано через: @youtodownloadbot</b>",
        "err_heavy": "❌ Видео слишком тяжелое для Telegram (даже после сжатия).",
        "err_timeout": "❌ Видео обрабатывалось слишком долго. Попробуй другое."
    },
    "en": {
        "choose_lang": "<b>Choose language / Выберите язык:</b>",
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
        "help_text": "Just send a video link from TikTok, YT or Insta. The bot will offer download options.",
        "sub_ok": "✅ Thanks for subscribing! Now you can send links.",
        "sub_fail": "❌ You are still not subscribed!",
        "cancel_text": "Action canceled. Send me a new link! 👇",
        "err_lost": "Error: link lost. Send it again.",
        "step_1": "⏳ [1/4] Analyzing link...",
        "step_2": "📥 [2/4] Downloading to server...",
        "step_3": "⚙️ [3/4] Processing and compressing...",
        "step_4": "📤 [4/4] Sending file to you...",
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

def register_user(user_id: int):
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

# --- ХЕНДЛЕРЫ ---

@video_router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    register_user(message.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang_en")
        ]
    ])
    await message.answer(STRINGS["ru"]["choose_lang"], parse_mode="HTML", reply_markup=kb)
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

    await callback.message.edit_text("⚙️ Настройки", reply_markup=kb)
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

    await callback.message.edit_text(
        STRINGS[lang]["welcome"].format(name=callback.from_user.full_name),
        reply_markup=kb
    )
    await callback.answer()

# --- ОБРАБОТКА ССЫЛОК ---

@video_router.message(F.text.regexp(r'(https?://\S+)'))
async def process_video_url(message: types.Message, state: FSMContext):
    register_user(message.from_user.id)
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

    await message.answer(STRINGS[lang]["link_ok"], reply_markup=kb)
    await state.set_state(DownloadStates.choosing_format)

@video_router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.message.edit_text(STRINGS[lang]["sub_ok"])
    else:
        await callback.answer(STRINGS[lang]["sub_fail"], show_alert=True)

@video_router.callback_query(F.data == "help_info")
async def help_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await callback.message.answer(STRINGS[lang]["help_text"])
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

    await callback.message.edit_text(STRINGS[lang]["cancel_text"], reply_markup=kb)
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
            clean_title = video_data.title[:900]
            caption = f"🎬 <b>{clean_title}</b>{STRINGS[lang]['promo']}"

            if mode == 'video':
                await callback.message.answer_video(
                    video=file, caption=caption, parse_mode="HTML",
                    width=video_data.width, height=video_data.height,
                    duration=video_data.duration, supports_streaming=True, request_timeout=300
                )
            else:
                await callback.message.answer_audio(
                    audio=file, caption=f"🎵 <b>{clean_title}</b>{STRINGS[lang]['promo']}",
                    parse_mode="HTML", title=video_data.title, performer=video_data.author,
                    duration=video_data.duration, request_timeout=300
                )

            await status_msg.delete()
            await state.clear()

    except Exception as e:
        err_text = str(e)
        msg = f"❌ Error: {err_text[:100]}"
        if "Too Large" in err_text:
            msg = STRINGS[lang]["err_heavy"]
        elif "Timeout" in err_text:
            msg = STRINGS[lang]["err_timeout"]
        await status_msg.edit_text(msg)
        await state.clear()
    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass

# --- АДМИНКА ---

@video_router.message(Command("broadcast"))
async def start_broadcast(message: types.Message, state: FSMContext):
    if str(message.from_user.id) != str(conf.admin_id):
        return
    await message.answer("Пришли сообщение для рассылки.")
    await state.set_state(AdminStates.waiting_for_broadcast)

@video_router.message(AdminStates.waiting_for_broadcast)
async def perform_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    if not os.path.exists(conf.users_db_path):
        return
    with open(conf.users_db_path, "r") as f:
        user_ids = f.read().splitlines()
    count, blocked = 0, 0
    status_msg = await message.answer(f"🚀 Рассылка...")
    for user_id in user_ids:
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05)
        except:
            blocked += 1
    await status_msg.edit_text(f"✅ Готово! Успешно: {count}, Блок: {blocked}")
