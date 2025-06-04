import json
import re
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from zoneinfo import ZoneInfo
from states import EditPost
import supabase_db
from __init__ import TEXTS

router = Router()

TOKEN_MAP = {
    "YYYY": "%Y", "YY": "%y",
    "MM": "%m",   "DD": "%d",
    "HH": "%H",   "hh": "%I",
    "mm": "%M",   "SS": "%S",
    "AM": "%p",   "PM": "%p",
    "am": "%p",   "pm": "%p",
}
_rx = re.compile("|".join(sorted(TOKEN_MAP, key=len, reverse=True)))

def format_to_strptime(date_fmt: str, time_fmt: str) -> str:
    return _rx.sub(lambda m: TOKEN_MAP[m.group(0)], f"{date_fmt} {time_fmt}")

def parse_time(user: dict, text: str):
    date_fmt = user.get("date_format", "YYYY-MM-DD")
    time_fmt = user.get("time_format", "HH:mm")
    tz_name = user.get("timezone", "UTC")
    # Adjust time format for correct parsing
    if "MM" in time_fmt:
        time_fmt = time_fmt.replace("MM", "mm")
    fmt = format_to_strptime(date_fmt, time_fmt)
    dt = datetime.strptime(text, fmt)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    local_dt = dt.replace(tzinfo=tz)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return utc_dt

def format_example(user: dict):
    date_fmt = user.get("date_format", "YYYY-MM-DD")
    time_fmt = user.get("time_format", "HH:mm")
    if "MM" in time_fmt:
        time_fmt = time_fmt.replace("MM", "mm")
    fmt = format_to_strptime(date_fmt, time_fmt)
    now = datetime.now()
    try:
        return now.strftime(fmt)
    except Exception:
        return now.strftime("%Y-%m-%d %H:%M")

def get_edit_navigation_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура навигации для редактирования"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="edit_skip")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])

def get_edit_menu_keyboard(post_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Улучшенное меню редактирования с красивыми кнопками"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Текст", callback_data=f"edit_start:text:{post_id}"),
            InlineKeyboardButton(text="🖼 Медиа", callback_data=f"edit_start:media:{post_id}")
        ],
        [
            InlineKeyboardButton(text="🎨 Формат", callback_data=f"edit_start:format:{post_id}"),
            InlineKeyboardButton(text="🔘 Кнопки", callback_data=f"edit_start:buttons:{post_id}")
        ],
        [
            InlineKeyboardButton(text="⏰ Время", callback_data=f"edit_start:time:{post_id}"),
            InlineKeyboardButton(text="📺 Канал", callback_data=f"edit_start:channel:{post_id}")
        ],
        [
            InlineKeyboardButton(text="🔄 Заново", callback_data=f"edit_restart:{post_id}"),
            InlineKeyboardButton(text="✅ Готово", callback_data=f"edit_finish:{post_id}")
        ],
        [
            InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ])

def get_format_selection_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора формата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 HTML", callback_data="format_select:html")],
        [InlineKeyboardButton(text="📋 Markdown", callback_data="format_select:markdown")],
        [InlineKeyboardButton(text="📄 Без форматирования", callback_data="format_select:none")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="edit_skip")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    
    if len(args) < 2:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/edit <ID поста>`\n\n"
            "Пример: `/edit 123`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    try:
        post_id = int(args[1])
    except:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "❌ **Неверный ID поста**\n\n"
            "ID должен быть числом.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    post = supabase_db.db.get_post(post_id)
    # Permission check: user must be member of the project containing this post
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            f"❌ **Пост #{post_id} не найден**\n\n"
            "Возможно, у вас нет доступа к этому посту.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    if post.get("published"):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            f"❌ **Пост #{post_id} уже опубликован**\n\n"
            "Опубликованные посты редактировать нельзя.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    # Показываем меню редактирования
    await show_edit_menu(message, post_id, user, lang)

async def show_edit_menu(message: Message, post_id: int, user: dict, lang: str):
    """Показать красивое меню редактирования"""
    post = supabase_db.db.get_post(post_id)
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    text = f"✏️ **Редактирование поста #{post_id}**\n\n"
    
    # Показываем краткую информацию о посте
    if channel:
        text += f"📺 **Канал:** {channel['name']}\n"
    
    if post.get("text"):
        preview_text = post["text"][:50] + "..." if len(post["text"]) > 50 else post["text"]
        text += f"📝 **Текст:** {preview_text}\n"
    else:
        text += "📝 **Текст:** не задан\n"
    
    if post.get("media_id"):
        media_type = post.get("media_type", "медиа")
        text += f"🖼 **Медиа:** {media_type}\n"
    else:
        text += "🖼 **Медиа:** не прикреплено\n"
    
    format_val = post.get("parse_mode") or post.get("format") or "none"
    text += f"🎨 **Формат:** {format_val}\n"
    
    if post.get("buttons"):
        try:
            buttons = json.loads(post["buttons"]) if isinstance(post["buttons"], str) else post["buttons"]
            text += f"🔘 **Кнопки:** {len(buttons)} шт.\n"
        except:
            text += "🔘 **Кнопки:** не заданы\n"
    else:
        text += "🔘 **Кнопки:** не заданы\n"
    
    if post.get("publish_time"):
        text += f"⏰ **Время:** запланировано\n"
    elif post.get("draft"):
        text += "⏰ **Время:** черновик\n"
    else:
        text += "⏰ **Время:** не задано\n"
    
    text += "\n**Выберите, что хотите изменить:**"
    
    keyboard = get_edit_menu_keyboard(post_id, lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Обработчики кнопок меню редактирования
@router.callback_query(F.data.startswith("edit_start:"))
async def handle_edit_start(callback: CallbackQuery, state: FSMContext):
    """Обработка начала редактирования конкретного поля"""
    data_parts = callback.data.split(":")
    field = data_parts[1]
    post_id = int(data_parts[2])
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден!")
        return
    
    # Initialize FSM for editing
    await state.update_data(
        orig_post=post, 
        user_settings=(user or supabase_db.db.ensure_user(user_id, default_lang=lang)),
        editing_field=field
    )
    
    if field == "text":
        await state.set_state(EditPost.text)
        current_text = post.get("text") or "не задан"
        text = (
            f"📝 **Редактирование текста поста #{post_id}**\n\n"
            f"**Текущий текст:**\n{current_text}\n\n"
            f"Отправьте новый текст или используйте кнопки ниже:"
        )
        keyboard = get_edit_navigation_keyboard(lang)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    elif field == "media":
        await ask_edit_media(callback.message, state, is_callback=True)
    
    elif field == "format":
        await ask_edit_format(callback.message, state, is_callback=True)
    
    elif field == "buttons":
        await ask_edit_buttons(callback.message, state, is_callback=True)
    
    elif field == "time":
        await ask_edit_time(callback.message, state, is_callback=True)
    
    elif field == "channel":
        await ask_edit_channel(callback.message, state, is_callback=True)
    
    await callback.answer()

@router.callback_query(F.data.startswith("edit_restart:"))
async def handle_edit_restart(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование заново"""
    post_id = int(callback.data.split(":")[1])
    
    # Перенаправляем на создание нового поста
    await callback.message.edit_text(
        f"🔄 **Полное редактирование поста #{post_id}**\n\n"
        f"Используйте команду `/edit {post_id}` для пошагового редактирования всех полей.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_finish:"))
async def handle_edit_finish(callback: CallbackQuery, state: FSMContext):
    """Завершить редактирование"""
    post_id = int(callback.data.split(":")[1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"✅ **Редактирование завершено**\n\n"
        f"Пост #{post_id} готов к публикации.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "edit_skip")
async def handle_edit_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить текущее поле"""
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    user = data.get("user_settings", {})
    lang = user.get("language", "ru")
    
    # Возвращаемся к меню редактирования
    await show_edit_menu(callback.message, post_id, user, lang)
    await state.clear()
    await callback.answer("Пропущено")

@router.callback_query(F.data == "edit_cancel")
async def handle_edit_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменить редактирование"""
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "❌ **Редактирование отменено**\n\n"
        "Изменения не сохранены.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()
    await callback.answer()

@router.message(EditPost.text)
async def edit_step_text(message: Message, state: FSMContext):
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    user = data.get("user_settings", {})
    lang = user.get("language", "ru")
    
    # Обновляем текст поста
    new_text = message.text or ""
    supabase_db.db.update_post(post_id, {"text": new_text})
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **Текст обновлен**\n\n"
        f"Новый текст сохранен для поста #{post_id}.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

async def ask_edit_media(message: Message, state: FSMContext, is_callback: bool = False):
    await state.set_state(EditPost.media)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    post_id = orig_post.get("id")
    lang = data.get("user_settings", {}).get("language", "ru")
    
    if orig_post.get("media_id"):
        media_type = orig_post.get("media_type", "медиа")
        text = (
            f"🖼 **Редактирование медиа поста #{post_id}**\n\n"
            f"**Текущее медиа:** {media_type}\n\n"
            f"Отправьте новое фото, видео или GIF, либо используйте кнопки:"
        )
    else:
        text = (
            f"🖼 **Добавление медиа к посту #{post_id}**\n\n"
            f"**Текущее медиа:** не прикреплено\n\n"
            f"Отправьте фото, видео или GIF, либо используйте кнопки:"
        )
    
    keyboard = get_edit_navigation_keyboard(lang)
    
    if is_callback:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.media, F.photo)
async def edit_step_media_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    
    # Обновляем медиа поста
    supabase_db.db.update_post(post_id, {
        "media_id": message.photo[-1].file_id,
        "media_type": "photo"
    })
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **Фото обновлено**\n\n"
        f"Новое фото прикреплено к посту #{post_id}.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

@router.message(EditPost.media, F.video)
async def edit_step_media_video(message: Message, state: FSMContext):
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    
    # Обновляем медиа поста
    supabase_db.db.update_post(post_id, {
        "media_id": message.video.file_id,
        "media_type": "video"
    })
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **Видео обновлено**\n\n"
        f"Новое видео прикреплено к посту #{post_id}.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

@router.message(EditPost.media, F.animation)
async def edit_step_media_animation(message: Message, state: FSMContext):
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    
    # Обновляем медиа поста
    supabase_db.db.update_post(post_id, {
        "media_id": message.animation.file_id,
        "media_type": "animation"
    })
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **GIF обновлено**\n\n"
        f"Новый GIF прикреплен к посту #{post_id}.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

async def ask_edit_format(message: Message, state: FSMContext, is_callback: bool = False):
    await state.set_state(EditPost.format)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    post_id = orig_post.get("id")
    lang = data.get("user_settings", {}).get("language", "ru")
    
    current_format = orig_post.get("parse_mode") or orig_post.get("format") or "none"
    
    text = (
        f"🎨 **Редактирование формата поста #{post_id}**\n\n"
        f"**Текущий формат:** {current_format}\n\n"
        f"Выберите новый формат текста:"
    )
    
    keyboard = get_format_selection_keyboard(lang)
    
    if is_callback:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("format_select:"))
async def handle_format_select(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора формата"""
    format_type = callback.data.split(":")[1]
    
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    
    # Обновляем формат поста
    supabase_db.db.update_post(post_id, {"parse_mode": format_type})
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await callback.message.edit_text(
        f"✅ **Формат обновлен**\n\n"
        f"Новый формат ({format_type}) установлен для поста #{post_id}.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()
    await callback.answer()

@router.message(EditPost.format)
async def edit_step_format(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    
    new_fmt = None
    if raw:
        if raw.startswith("markdown"):
            new_fmt = "markdown"
        elif raw.startswith("html") or raw.startswith("htm"):
            new_fmt = "html"
        elif raw in ("none", "без", "без форматирования"):
            new_fmt = "none"
    
    if new_fmt is None:
        # Если формат не распознан, оставляем текущий
        new_fmt = (data.get("orig_post", {}).get("parse_mode") or data.get("orig_post", {}).get("format") or "none")
    
    # Обновляем формат поста
    supabase_db.db.update_post(post_id, {"parse_mode": new_fmt})
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **Формат обновлен**\n\n"
        f"Новый формат ({new_fmt}) установлен для поста #{post_id}.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

async def ask_edit_buttons(message: Message, state: FSMContext, is_callback: bool = False):
    await state.set_state(EditPost.buttons)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    post_id = orig_post.get("id")
    lang = data.get("user_settings", {}).get("language", "ru")
    
    if orig_post.get("buttons"):
        # Present current buttons list
        btns = orig_post.get("buttons")
        if isinstance(btns, str):
            try:
                btns = json.loads(btns)
            except:
                btns = []
        if not isinstance(btns, list):
            btns = []
        if btns:
            buttons_list = "\n".join([f"• {b.get('text', '')} | {b.get('url', '')}" if isinstance(b, dict) else f"• {b}" for b in btns])
        else:
            buttons_list = "не заданы"
        
        text = (
            f"🔘 **Редактирование кнопок поста #{post_id}**\n\n"
            f"**Текущие кнопки:**\n{buttons_list}\n\n"
            f"Отправьте новые кнопки в формате 'Текст | URL' (каждая на новой строке):"
        )
    else:
        text = (
            f"🔘 **Добавление кнопок к посту #{post_id}**\n\n"
            f"**Текущие кнопки:** не заданы\n\n"
            f"Отправьте кнопки в формате 'Текст | URL' (каждая на новой строке):"
        )
    
    keyboard = get_edit_navigation_keyboard(lang)
    
    if is_callback:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.buttons)
async def edit_step_buttons(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    post = data.get("orig_post", {})
    post_id = post.get("id")
    
    if text.strip().lower() in ("нет", "none", ""):
        # Удаляем кнопки
        supabase_db.db.update_post(post_id, {"buttons": None})
        status_text = "удалены"
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        new_buttons = []
        for line in lines:
            parts = line.split("|")
            if len(parts) >= 2:
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                if btn_text and btn_url:
                    new_buttons.append({"text": btn_text, "url": btn_url})
        
        # Обновляем кнопки поста
        supabase_db.db.update_post(post_id, {"buttons": new_buttons})
        status_text = f"обновлены ({len(new_buttons)} кнопок)"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **Кнопки {status_text}**\n\n"
        f"Кнопки для поста #{post_id} {status_text}.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

async def ask_edit_time(message: Message, state: FSMContext, is_callback: bool = False):
    await state.set_state(EditPost.time)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    post_id = orig_post.get("id")
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    
    if orig_post.get("publish_time"):
        # Show current scheduled time
        orig_time = orig_post.get("publish_time")
        try:
            pub_dt = datetime.fromisoformat(orig_time) if isinstance(orig_time, str) else orig_time
        except:
            pub_dt = datetime.strptime(orig_time, "%Y-%m-%dT%H:%M:%S")
            pub_dt = pub_dt.replace(tzinfo=ZoneInfo("UTC"))
        
        tz_name = user.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except:
            tz = ZoneInfo("UTC")
        
        local_dt = pub_dt.astimezone(tz)
        fmt = format_to_strptime(user.get("date_format", "YYYY-MM-DD"), user.get("time_format", "HH:mm"))
        current_time_str = local_dt.strftime(fmt)
        
        text = (
            f"⏰ **Редактирование времени поста #{post_id}**\n\n"
            f"**Текущее время:** {current_time_str} ({tz_name})\n\n"
            f"Отправьте новое время в формате {user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}\n"
            f"Или отправьте:\n"
            f"• `now` - опубликовать сейчас\n"
            f"• `draft` - сохранить как черновик"
        )
    elif orig_post.get("draft"):
        text = (
            f"⏰ **Редактирование времени поста #{post_id}**\n\n"
            f"**Текущий статус:** черновик\n\n"
            f"Отправьте время в формате {user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}\n"
            f"Или отправьте:\n"
            f"• `now` - опубликовать сейчас\n"
            f"• `draft` - оставить черновиком"
        )
    else:
        text = (
            f"⏰ **Установка времени для поста #{post_id}**\n\n"
            f"**Текущий статус:** время не задано\n\n"
            f"Отправьте время в формате {user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}\n"
            f"Или отправьте:\n"
            f"• `now` - опубликовать сейчас\n"
            f"• `draft` - сохранить как черновик"
        )
    
    keyboard = get_edit_navigation_keyboard(lang)
    
    if is_callback:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.time)
async def edit_step_time(message: Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {}) or {}
    post = data.get("orig_post", {})
    post_id = post.get("id")
    lang = user.get("language", "ru")
    text = (message.text or "").strip().lower()
    
    if text in ("none", "нет", "skip", "пропустить"):
        # Возвращаемся к меню без изменений
        await show_edit_menu(message, post_id, user, lang)
        await state.clear()
        return
    elif text in ("now", "сейчас"):
        # Устанавливаем время на сейчас
        now = datetime.now(ZoneInfo("UTC"))
        supabase_db.db.update_post(post_id, {
            "publish_time": now.isoformat(),
            "draft": False,
            "notified": False
        })
        status_text = "установлено на сейчас"
    elif text in ("draft", "черновик"):
        # Делаем черновиком
        supabase_db.db.update_post(post_id, {
            "publish_time": None,
            "draft": True,
            "notified": False
        })
        status_text = "сохранен как черновик"
    else:
        try:
            new_time = parse_time(user, message.text)
        except:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"edit_start:time:{post_id}")],
                [InlineKeyboardButton(text="✏️ Меню редактирования", callback_data=f"edit_menu:{post_id}")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_finish:{post_id}")]
            ])
            
            example = format_example(user)
            await message.answer(
                f"❌ **Неверный формат времени**\n\n"
                f"Используйте формат: {user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}\n"
                f"Пример: {example}\n\n"
                f"Или отправьте `now` / `draft`",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        now = datetime.now(ZoneInfo("UTC"))
        if new_time <= now:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"edit_start:time:{post_id}")],
                [InlineKeyboardButton(text="✏️ Меню редактирования", callback_data=f"edit_menu:{post_id}")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_finish:{post_id}")]
            ])
            
            await message.answer(
                f"❌ **Время должно быть в будущем**\n\n"
                f"Указанное время уже прошло.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        # Обновляем время публикации
        supabase_db.db.update_post(post_id, {
            "publish_time": new_time.isoformat(),
            "draft": False,
            "notified": False
        })
        
        # Форматируем время для отображения
        tz_name = user.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
            local_time = new_time.astimezone(tz)
            fmt = format_to_strptime(user.get("date_format", "YYYY-MM-DD"), user.get("time_format", "HH:mm"))
            time_str = local_time.strftime(fmt)
            status_text = f"запланировано на {time_str} ({tz_name})"
        except:
            status_text = f"запланировано на {new_time.strftime('%Y-%m-%d %H:%M UTC')}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **Время {status_text}**\n\n"
        f"Время публикации поста #{post_id} обновлено.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

async def ask_edit_channel(message: Message, state: FSMContext, is_callback: bool = False):
    await state.set_state(EditPost.channel)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    post_id = orig_post.get("id")
    lang = data.get("user_settings", {}).get("language", "ru")
    
    # List channels available in current project
    user_settings = data.get("user_settings", {})
    project_id = user_settings.get("current_project")
    channels = supabase_db.db.list_channels(project_id=project_id)
    
    if not channels:
        text = (
            f"📺 **Редактирование канала поста #{post_id}**\n\n"
            f"❌ Нет доступных каналов в проекте."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📺 Добавить канал", callback_data="channels_add")],
            [InlineKeyboardButton(text="✏️ Меню редактирования", callback_data=f"edit_menu:{post_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_finish:{post_id}")]
        ])
        
        if is_callback:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        return
    
    # Determine current channel name for reference
    current_channel_name = "неизвестен"
    chan_id = orig_post.get("channel_id")
    chat_id = orig_post.get("chat_id")
    
    for ch in channels:
        if chan_id and ch.get("id") == chan_id:
            current_channel_name = ch.get("name") or str(ch.get("chat_id"))
            break
        if chat_id and ch.get("chat_id") == chat_id:
            current_channel_name = ch.get("name") or str(ch.get("chat_id"))
            break
    
    text = (
        f"📺 **Редактирование канала поста #{post_id}**\n\n"
        f"**Текущий канал:** {current_channel_name}\n\n"
        f"Выберите новый канал:"
    )
    
    # Создаем кнопки для каналов
    buttons = []
    for i, ch in enumerate(channels, 1):
        admin_status = "✅" if ch.get('is_admin_verified') else "❓"
        name = ch.get("name") or str(ch.get("chat_id"))
        buttons.append([InlineKeyboardButton(
            text=f"{admin_status} {name}", 
            callback_data=f"edit_channel_select:{ch['id']}:{post_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="⏭️ Пропустить", callback_data="edit_skip")])
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    if is_callback:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("edit_channel_select:"))
async def handle_edit_channel_select(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора канала"""
    data_parts = callback.data.split(":")
    channel_id = int(data_parts[1])
    post_id = int(data_parts[2])
    
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(channel_id)
    if not channel:
        await callback.answer("Канал не найден!")
        return
    
    # Обновляем канал поста
    supabase_db.db.update_post(post_id, {
        "channel_id": channel_id,
        "chat_id": channel.get("chat_id")
    })
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await callback.message.edit_text(
        f"✅ **Канал обновлен**\n\n"
        f"Пост #{post_id} теперь будет опубликован в канале: {channel['name']}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()
    await callback.answer()

@router.message(EditPost.channel)
async def choose_edit_channel(message: Message, state: FSMContext):
    data = await state.get_data()
    channels = data.get("_chan_map", [])
    post = data.get("orig_post", {})
    post_id = post.get("id")
    raw = (message.text or "").strip()
    chosen = None
    
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(channels):
            chosen = channels[idx - 1]
    else:
        for ch in channels:
            if str(ch["chat_id"]) == raw or (ch["name"] and ("@" + ch["name"]) == raw):
                chosen = ch
                break
    
    if not chosen:
        lang = data.get("user_settings", {}).get("language", "ru")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"edit_start:channel:{post_id}")],
            [InlineKeyboardButton(text="✏️ Меню редактирования", callback_data=f"edit_menu:{post_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_finish:{post_id}")]
        ])
        
        await message.answer(
            f"❌ **Канал не найден**\n\n"
            f"Проверьте номер канала или название.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    # Обновляем канал поста
    supabase_db.db.update_post(post_id, {
        "channel_id": chosen.get("id"),
        "chat_id": chosen.get("chat_id")
    })
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish:{post_id}")],
        [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_view:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **Канал обновлен**\n\n"
        f"Пост #{post_id} теперь будет опубликован в канале: {chosen.get('name')}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

# Обработчик для возврата к меню редактирования
@router.callback_query(F.data.startswith("edit_menu:"))
async def handle_edit_menu_return(callback: CallbackQuery, state: FSMContext):
    """Возврат к меню редактирования"""
    post_id = int(callback.data.split(":")[1])
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await show_edit_menu(callback.message, post_id, user, lang)
    await state.clear()
    await callback.answer()
