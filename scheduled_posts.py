from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from zoneinfo import ZoneInfo
from states import PostCreationFlow
import supabase_db
from __init__ import TEXTS
import re
import json

router = Router()

# Текстовые команды для ИИ-агента
TEXT_COMMANDS = {
    "skip": ["skip", "пропустить", "/skip"],
    "cancel": ["cancel", "отмена", "/cancel", "отменить"],
    "back": ["back", "назад", "/back"],
    "next": ["next", "далее", "/next"],
    "confirm": ["confirm", "подтвердить", "/confirm", "да", "yes"],
    "edit": ["edit", "редактировать", "/edit"],
    "draft": ["draft", "черновик"],
    "now": ["now", "сейчас"]
}

def is_command(text: str, command: str) -> bool:
    """Проверить, является ли текст командой"""
    if not text:
        return False
    text_lower = text.strip().lower()
    return text_lower in TEXT_COMMANDS.get(command, [])

def get_navigation_keyboard(current_step: str, lang: str = "ru", can_skip: bool = True):
    """Создать клавиатуру навигации для текущего шага"""
    buttons = []
    
    # Кнопки навигации
    nav_row = []
    if current_step != "step_text":  # Не на первом шаге
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back"))
    
    if can_skip:
        nav_row.append(InlineKeyboardButton(text="⏭️ Пропустить", callback_data="post_nav_skip"))
    
    if nav_row:
        buttons.append(nav_row)
    
    # Кнопка отмены
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_format_keyboard(lang: str = "ru"):
    """Клавиатуру выбора формата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 HTML", callback_data="format_html")],
        [InlineKeyboardButton(text="📋 Markdown", callback_data="format_markdown")],
        [InlineKeyboardButton(text="📄 Без форматирования", callback_data="format_none")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="post_nav_skip")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])

def get_time_options_keyboard(lang: str = "ru"):
    """Клавиатуру опций времени публикации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data="time_now")],
        [InlineKeyboardButton(text="📝 Сохранить как черновик", callback_data="time_draft")],
        [InlineKeyboardButton(text="⏰ Запланировать время", callback_data="time_schedule")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])

def get_channels_keyboard(channels: list, lang: str = "ru"):
    """Клавиатуру выбора канала"""
    buttons = []
    
    for i, channel in enumerate(channels):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text = f"{admin_status} {channel['name']}"
        buttons.append([InlineKeyboardButton(
            text=text, 
            callback_data=f"channel_select:{channel['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")])
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_preview_keyboard(lang: str = "ru"):
    """Клавиатуру предварительного просмотра"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="post_confirm")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_edit_menu")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])

def get_edit_menu_keyboard(lang: str = "ru"):
    """Клавиатуру меню редактирования"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить текст", callback_data="edit_field:text")],
        [InlineKeyboardButton(text="🖼 Изменить медиа", callback_data="edit_field:media")],
        [InlineKeyboardButton(text="🎨 Изменить формат", callback_data="edit_field:format")],
        [InlineKeyboardButton(text="🔘 Изменить кнопки", callback_data="edit_field:buttons")],
        [InlineKeyboardButton(text="⏰ Изменить время", callback_data="edit_field:time")],
        [InlineKeyboardButton(text="📺 Изменить канал", callback_data="edit_field:channel")],
        [InlineKeyboardButton(text="🔙 К предпросмотру", callback_data="post_preview")]
    ])

def get_post_actions_keyboard(post_id: int, is_scheduled: bool = False):
    """Клавиатура действий с постом после создания"""
    buttons = []
    
    # Кнопки просмотра
    buttons.append([
        InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_full_view:{post_id}"),
    ])
    
    # Если пост запланирован, предлагаем редактирование
    if is_scheduled:
        buttons.append([
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_direct:{post_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post_delete_cmd:{post_id}")
        ])
    
    # Навигационные кнопки
    buttons.append([
        InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_offer_keyboard(post_id: int, lang: str = "ru"):
    """Клавиатура предложения редактирования для запланированного поста"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Да, редактировать", callback_data=f"edit_offer_accept"),
            InlineKeyboardButton(text="✅ Нет, всё хорошо", callback_data="edit_offer_decline")
        ]
    ])

def get_content_missing_keyboard(lang: str = "ru"):
    """Клавиатура для случая отсутствия контента"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Добавить текст", callback_data="missing_content_add_text")],
        [InlineKeyboardButton(text="🖼 Добавить медиа", callback_data="missing_content_add_media")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])

def validate_post_content(data: dict) -> tuple[bool, str]:
    """Валидация контента поста (текст или медиа должны быть)"""
    has_text = bool(data.get("text") and data.get("text").strip())
    has_media = bool(data.get("media_file_id"))
    
    if not has_text and not has_media:
        return False, "Пост должен содержать текст или медиа"
    
    return True, ""

@router.message(Command("create"))
async def cmd_create_post(message: Message, state: FSMContext):
    """Начать создание поста"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем наличие каналов, где пользователь является администратором
    channels = supabase_db.db.list_channels(user_id=user_id)
    if not channels:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📺 Добавить канал", callback_data="channels_add")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "❌ **Нет доступных каналов**\n\n"
            "У вас нет каналов, где вы являетесь администратором.\n"
            "Добавьте канал через /channels",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    # Инициализируем данные поста
    await state.set_data({
        "user_id": user_id,
        "text": None,
        "media_type": None,
        "media_file_id": None,
        "parse_mode": "HTML",
        "buttons": None,
        "publish_time": None,
        "repeat_interval": None,
        "channel_id": None,
        "draft": False,
        "step_history": [],
        "current_step": "step_text"
    })
    
    await start_text_step(message, state, lang)

@router.message(Command("quickpost"))
async def cmd_quick_post(message: Message, state: FSMContext):
    """Быстрое создание поста: /quickpost <канал> <время> <текст>"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    
    # Парсим аргументы
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "📝 **Быстрое создание поста**\n\n"
            "Формат: `/quickpost <канал> <время> <текст>`\n\n"
            "Примеры:\n"
            "• `/quickpost @channel now Текст поста`\n"
            "• `/quickpost 1 draft Черновик поста`\n"
            "• `/quickpost 2 2024-12-25_15:30 Запланированный пост`\n\n"
            "Канал: @username, ID или номер в списке\n"
            "Время: now, draft или YYYY-MM-DD_HH:MM",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    channel_ref = parts[1]
    time_ref = parts[2]
    text = parts[3]
    
    # Находим канал среди доступных пользователю
    channels = supabase_db.db.list_channels(user_id=user_id)
    channel = None
    
    if channel_ref.isdigit():
        idx = int(channel_ref) - 1
        if 0 <= idx < len(channels):
            channel = channels[idx]
    else:
        for ch in channels:
            if (ch.get('username') and f"@{ch['username']}" == channel_ref) or \
               str(ch['chat_id']) == channel_ref or \
               str(ch['id']) == channel_ref:
                channel = ch
                break
    
    if not channel:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📺 Управление каналами", callback_data="channels_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(f"❌ Канал '{channel_ref}' не найден среди ваших каналов", reply_markup=keyboard)
        return
    
    # Парсим время
    publish_time = None
    draft = False
    
    if time_ref.lower() == "now":
        publish_time = datetime.now(ZoneInfo("UTC"))
    elif time_ref.lower() == "draft":
        draft = True
    else:
        try:
            dt = datetime.strptime(time_ref, "%Y-%m-%d_%H:%M")
            tz = ZoneInfo(user.get("timezone", "UTC"))
            local_dt = dt.replace(tzinfo=tz)
            publish_time = local_dt.astimezone(ZoneInfo("UTC"))
        except ValueError:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer(
                "❌ Неверный формат времени. Используйте: YYYY-MM-DD_HH:MM",
                reply_markup=keyboard
            )
            return
    
    # Создаем пост
    post_data = {
        "user_id": user_id,
        "channel_id": channel['id'],
        "chat_id": channel['chat_id'],  # Для совместимости с автопостингом
        "text": text,
        "parse_mode": "HTML",
        "publish_time": publish_time.isoformat() if publish_time else None,
        "draft": draft,
        "published": False
    }
    
    post = supabase_db.db.add_post(post_data)
    
    if post:
        status = "📝 черновик" if draft else "⏰ запланирован" if publish_time else "создан"
        
        # Определяем, запланирован ли пост
        is_scheduled = not draft and publish_time and publish_time > datetime.now(ZoneInfo("UTC"))
        keyboard = get_post_actions_keyboard(post['id'], is_scheduled)
        
        await message.answer(
            f"✅ **Пост #{post['id']} {status}**\n\n"
            f"Канал: {channel['name']}\n"
            f"Текст: {text[:50]}...",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_create_post_direct")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Ошибка создания поста", reply_markup=keyboard)

async def start_text_step(message: Message, state: FSMContext, lang: str):
    """Шаг 1: Ввод текста поста"""
    await state.set_state(PostCreationFlow.step_text)
    
    text = (
        "📝 **Создание поста - Шаг 1/7**\n\n"
        "**Введите текст поста**\n\n"
        "Текстовые команды:\n"
        "• `skip` или `пропустить` - пропустить шаг\n"
        "• `cancel` или `отмена` - отменить создание\n\n"
        "💡 *Форматирование можно будет настроить на следующем шаге*"
    )
    
    keyboard = get_navigation_keyboard("step_text", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_text, F.text)
async def handle_text_input(message: Message, state: FSMContext):
    """Обработка ввода текста"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем текстовые команды
    if is_command(message.text, "skip"):
        data = await state.get_data()
        data["text"] = None
        data["step_history"].append("step_text")
        await state.set_data(data)
        await start_media_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Создание поста отменено", reply_markup=keyboard)
        return
    
    # Сохраняем текст
    data = await state.get_data()
    data["text"] = message.text
    data["step_history"].append("step_text")
    await state.set_data(data)
    
    await start_media_step(message, state, lang)

async def start_media_step(message: Message, state: FSMContext, lang: str):
    """Шаг 2: Добавление медиа"""
    await state.set_state(PostCreationFlow.step_media)
    
    text = (
        "🖼 **Создание поста - Шаг 2/7**\n\n"
        "**Добавьте медиа к посту**\n\n"
        "Текстовые команды:\n"
        "• `skip` - пропустить медиа\n"
        "• `back` - вернуться к тексту\n"
        "• `cancel` - отменить создание\n\n"
        "Или отправьте фото/видео/GIF"
    )
    
    keyboard = get_navigation_keyboard("step_media", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_media, F.text | F.photo | F.video | F.animation)
async def handle_media_input(message: Message, state: FSMContext):
    """Обработка медиа или команд"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем текстовые команды
    if message.text and is_command(message.text, "skip"):
        data = await state.get_data()
        data["step_history"].append("step_media")
        await state.set_data(data)
        
        # ВАЖНО: Проверяем контент после медиа-шага
        is_valid, error_msg = validate_post_content(data)
        if not is_valid:
            await show_content_missing_dialog(message, state, lang)
            return
        
        await start_format_step(message, state, lang)
        return
    
    if message.text and is_command(message.text, "back"):
        await go_back_step(message, state, lang)
        return
    
    if message.text and is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Создание поста отменено", reply_markup=keyboard)
        return
    
    # Обработка медиа
    media_handled = False
    data = await state.get_data()
    
    if message.photo:
        data["media_type"] = "photo"
        data["media_file_id"] = message.photo[-1].file_id
        media_handled = True
    elif message.video:
        data["media_type"] = "video"
        data["media_file_id"] = message.video.file_id
        media_handled = True
    elif message.animation:
        data["media_type"] = "animation"
        data["media_file_id"] = message.animation.file_id
        media_handled = True
    
    if media_handled:
        data["step_history"].append("step_media")
        await state.set_data(data)
        await start_format_step(message, state, lang)
    else:
        if message.text:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="post_nav_skip")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
            ])
            await message.answer(
                "❌ **Неизвестная команда**\n\n"
                "Доступные команды:\n"
                "• `skip` - пропустить\n"
                "• `back` - назад\n"
                "• `cancel` - отмена\n\n"
                "Или отправьте медиа файл",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

async def show_content_missing_dialog(message: Message, state: FSMContext, lang: str):
    """Показать диалог об отсутствии контента"""
    text = (
        "⚠️ **Пост должен содержать контент**\n\n"
        "Ваш пост не содержит ни текста, ни медиа.\n"
        "Пост должен иметь хотя бы что-то одно.\n\n"
        "Что хотите добавить?"
    )
    
    keyboard = get_content_missing_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "missing_content_add_text")
async def handle_missing_content_add_text(callback: CallbackQuery, state: FSMContext):
    """Добавить текст когда контент отсутствует"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Возвращаемся к шагу текста
    data = await state.get_data()
    # Убираем step_media из истории, чтобы вернуться к тексту
    if "step_media" in data.get("step_history", []):
        data["step_history"].remove("step_media")
    await state.set_data(data)
    
    await callback.answer()
    await start_text_step(callback.message, state, lang)

@router.callback_query(F.data == "missing_content_add_media")
async def handle_missing_content_add_media(callback: CallbackQuery, state: FSMContext):
    """Добавить медиа когда контент отсутствует"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    await callback.answer()
    await start_media_step(callback.message, state, lang)

async def start_format_step(message: Message, state: FSMContext, lang: str):
    """Шаг 3: Выбор формата"""
    await state.set_state(PostCreationFlow.step_format)
    
    text = (
        "🎨 **Создание поста - Шаг 3/7**\n\n"
        "**Выберите формат текста**\n\n"
        "• **HTML** - <b>жирный</b>, <i>курсив</i>, <a href='#'>ссылки</a>\n"
        "• **Markdown** - **жирный**, *курсив*, [ссылки](url)\n"
        "• **Обычный** - без форматирования\n\n"
        "Текстовые команды:\n"
        "• `html` - HTML формат\n"
        "• `markdown` - Markdown формат\n"
        "• `none` - без форматирования\n"
        "• `skip` - HTML по умолчанию\n"
        "• `back` - назад"
    )
    
    keyboard = get_format_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_format, F.text)
async def handle_format_text_input(message: Message, state: FSMContext):
    """Обработка текстового выбора формата"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    text_lower = message.text.lower().strip()
    
    # Проверяем команды навигации
    if is_command(message.text, "skip"):
        data = await state.get_data()
        data["step_history"].append("step_format")
        await state.set_data(data)
        await start_buttons_step(message, state, lang)
        return
    
    if is_command(message.text, "back"):
        await go_back_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Создание поста отменено", reply_markup=keyboard)
        return
    
    # Выбор формата
    format_map = {
        "html": "HTML",
        "markdown": "Markdown",
        "md": "Markdown",
        "none": None,
        "обычный": None,
        "без форматирования": None
    }
    
    if text_lower in format_map:
        data = await state.get_data()
        data["parse_mode"] = format_map[text_lower]
        data["step_history"].append("step_format")
        await state.set_data(data)
        await start_buttons_step(message, state, lang)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 HTML", callback_data="format_html")],
            [InlineKeyboardButton(text="📋 Markdown", callback_data="format_markdown")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
        ])
        await message.answer(
            "❌ **Неизвестный формат**\n\n"
            "Доступные команды:\n"
            "• `html` - HTML форматирование\n"
            "• `markdown` - Markdown форматирование\n"
            "• `none` - без форматирования\n"
            "• `skip` - пропустить (HTML по умолчанию)\n"
            "• `back` - назад",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@router.callback_query(F.data.startswith("format_"))
async def handle_format_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора формата через кнопки"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    format_map = {
        "format_html": "HTML",
        "format_markdown": "Markdown",
        "format_none": None
    }
    
    data = await state.get_data()
    data["parse_mode"] = format_map.get(callback.data, "HTML")
    data["step_history"].append("step_format")
    await state.set_data(data)
    
    await callback.answer()
    await start_buttons_step(callback.message, state, lang)

async def start_buttons_step(message: Message, state: FSMContext, lang: str):
    """Шаг 4: Добавление кнопок"""
    await state.set_state(PostCreationFlow.step_buttons)
    
    text = (
        "🔘 **Создание поста - Шаг 4/7**\n\n"
        "**Добавьте кнопки к посту**\n\n"
        "Формат: `Текст кнопки | https://example.com`\n"
        "Каждая кнопка на новой строке\n\n"
        "Пример:\n"
        "```\n"
        "Наш сайт | https://example.com\n"
        "Telegram | https://t.me/channel\n"
        "```\n\n"
        "Текстовые команды:\n"
        "• `skip` - пропустить кнопки\n"
        "• `back` - назад\n"
        "• `cancel` - отмена"
    )
    
    keyboard = get_navigation_keyboard("step_buttons", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_buttons, F.text)
async def handle_buttons_input(message: Message, state: FSMContext):
    """Обработка ввода кнопок"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем команды
    if is_command(message.text, "skip"):
        data = await state.get_data()
        data["buttons"] = None
        data["step_history"].append("step_buttons")
        await state.set_data(data)
        await start_time_step(message, state, lang)
        return
    
    if is_command(message.text, "back"):
        await go_back_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Создание поста отменено", reply_markup=keyboard)
        return
    
    # Парсим кнопки
    try:
        buttons = []
        lines = message.text.strip().split('\n')
        
        for line in lines:
            if '|' in line:
                parts = line.split('|', 1)
                text = parts[0].strip()
                url = parts[1].strip()
                if text and url:
                    buttons.append({"text": text, "url": url})
        
        if not buttons:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="post_nav_skip")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
            ])
            await message.answer(
                "❌ **Неверный формат кнопок**\n\n"
                "Используйте формат: `Текст | URL`\n"
                "Каждая кнопка на новой строке\n\n"
                "Или используйте команды:\n"
                "• `skip` - пропустить\n"
                "• `back` - назад",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        data = await state.get_data()
        data["buttons"] = buttons
        data["step_history"].append("step_buttons")
        await state.set_data(data)
        
        await start_time_step(message, state, lang)
        
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="post_nav_skip")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
        ])
        await message.answer(
            "❌ **Ошибка в формате кнопок**\n\n"
            f"Ошибка: {str(e)}\n\n"
            "Используйте формат: `Текст | URL`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

async def start_time_step(message: Message, state: FSMContext, lang: str):
    """Шаг 5: Выбор времени публикации"""
    await state.set_state(PostCreationFlow.step_time)
    
    data = await state.get_data()
    user = supabase_db.db.get_user(data["user_id"])
    timezone = user.get("timezone", "UTC") if user else "UTC"
    
    text = (
        "⏰ **Создание поста - Шаг 5/7**\n\n"
        "**Когда опубликовать пост?**\n\n"
        "Текстовые команды:\n"
        "• `now` - опубликовать сейчас\n"
        "• `draft` - сохранить как черновик\n"
        "• Дата и время: `2024-12-25 15:30`\n\n"
        f"Ваш часовой пояс: {timezone}\n"
        "• `back` - назад\n"
        "• `cancel` - отмена"
    )
    
    keyboard = get_time_options_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_channel_step(message: Message, state: FSMContext, lang: str):
    """Шаг 6: Выбор канала"""
    await state.set_state(PostCreationFlow.step_channel)
    
    data = await state.get_data()
    user_id = data["user_id"]
    
    # Получаем каналы, где пользователь является администратором
    channels = supabase_db.db.list_channels(user_id=user_id)
    
    text = (
        "📺 **Создание поста - Шаг 6/7**\n\n"
        "**Выберите канал для публикации**\n\n"
    )
    
    # Список каналов с номерами
    for i, channel in enumerate(channels, 1):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text += f"{i}. {admin_status} {channel['name']}\n"
    
    text += (
        "\nТекстовые команды:\n"
        "• Номер канала (например: `1`)\n"
        "• @username канала\n"
        "• `back` - назад\n"
        "• `cancel` - отмена"
    )
    
    keyboard = get_channels_keyboard(channels, lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_preview_step(message: Message, state: FSMContext, lang: str):
    """Шаг 7: Предварительный просмотр"""
    await state.set_state(PostCreationFlow.step_preview)
    
    data = await state.get_data()
    
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(data["channel_id"])
    
    # Сначала отправляем превью самого поста
    await send_post_preview(message, data)
    
    # Затем отправляем информацию с кнопками действий
    info_text = "👀 **Предварительный просмотр - Шаг 7/7**\n\n"
    info_text += f"**Канал:** {channel['name'] if channel else 'Неизвестный'}\n"
    
    if data.get("publish_time"):
        if isinstance(data["publish_time"], datetime):
            user = supabase_db.db.get_user(data["user_id"])
            user_tz = user.get('timezone', 'UTC') if user else 'UTC'
            try:
                user_tz_obj = ZoneInfo(user_tz)
                local_time = data["publish_time"].astimezone(user_tz_obj)
                time_str = local_time.strftime('%Y-%m-%d %H:%M')
                info_text += f"**Время публикации:** {time_str} ({user_tz})\n"
            except:
                time_str = data["publish_time"].strftime('%Y-%m-%d %H:%M UTC')
                info_text += f"**Время публикации:** {time_str}\n"
        else:
            info_text += f"**Время публикации:** {data['publish_time']}\n"
    elif data.get("draft"):
        info_text += "**Статус:** Черновик\n"
    else:
        info_text += "**Статус:** Опубликовать сейчас\n"
    
    if data.get("parse_mode"):
        info_text += f"**Формат:** {data['parse_mode']}\n"
    
    info_text += (
        "\n**Текстовые команды:**\n"
        "• `confirm` или `подтвердить` - создать пост\n"
        "• `edit` или `редактировать` - редактировать\n"
        "• `back` - назад к выбору канала\n"
        "• `cancel` - отменить создание\n\n"
        "✅ Всё верно? Подтвердите создание поста."
    )
    
    keyboard = get_preview_keyboard(lang)
    await message.answer(info_text, reply_markup=keyboard, parse_mode="Markdown")

async def send_post_preview(message: Message, data: dict):
    """Отправить превью поста как он будет выглядеть в канале"""
    text = data.get("text", "")
    media_id = data.get("media_file_id")
    media_type = data.get("media_type")
    parse_mode = data.get("parse_mode")
    buttons = data.get("buttons")
    
    # Подготовка кнопок
    markup = None
    if buttons:
        kb = []
        for btn in buttons:
            if isinstance(btn, dict) and btn.get("text") and btn.get("url"):
                kb.append([InlineKeyboardButton(text=btn["text"], url=btn["url"])])
        if kb:
            markup = InlineKeyboardMarkup(inline_keyboard=kb)
    
    # Определяем parse_mode
    if parse_mode == "HTML":
        pm = "HTML"
    elif parse_mode == "Markdown":
        pm = "Markdown"
    else:
        pm = None
    
    # Отправка превью
    try:
        if media_id and media_type:
            if media_type == "photo":
                await message.answer_photo(
                    media_id,
                    caption=text or None,
                    parse_mode=pm,
                    reply_markup=markup
                )
            elif media_type == "video":
                await message.answer_video(
                    media_id,
                    caption=text or None,
                    parse_mode=pm,
                    reply_markup=markup
                )
            elif media_type == "animation":
                await message.answer_animation(
                    media_id,
                    caption=text or None,
                    parse_mode=pm,
                    reply_markup=markup
                )
        else:
            await message.answer(
                text or "📝 *[Пост без текста]*",
                parse_mode=pm or "Markdown",
                reply_markup=markup
            )
    except Exception as e:
        await message.answer(
            f"⚠️ **Ошибка предпросмотра**\n\n"
            f"Не удалось показать превью: {str(e)}\n"
            f"Проверьте форматирование текста.",
            parse_mode="Markdown"
        )

async def handle_post_confirmation_text(message: Message, state: FSMContext, is_callback: bool = False):
    """Подтверждение создания поста"""
    try:
        data = await state.get_data()
        user = supabase_db.db.get_user(data.get("user_id"))
        lang = user.get("language", "ru") if user else "ru"
        
        # Подготовка данных для сохранения
        post_data = {
            "user_id": data["user_id"],
            "channel_id": data["channel_id"],
            "text": data.get("text"),
            "media_type": data.get("media_type"),
            "media_id": data.get("media_file_id"),
            "parse_mode": data.get("parse_mode", "HTML"),
            "buttons": data.get("buttons"),
            "repeat_interval": data.get("repeat_interval"),
            "draft": data.get("draft", False),
            "published": False
        }
        
        # Получаем chat_id для совместимости с автопостингом
        channel = supabase_db.db.get_channel(data["channel_id"])
        if channel:
            post_data["chat_id"] = channel.get("chat_id")
        
        # Безопасная обработка времени публикации
        publish_time = data.get("publish_time")
        if publish_time:
            if isinstance(publish_time, datetime):
                post_data["publish_time"] = publish_time.isoformat()
            else:
                post_data["publish_time"] = str(publish_time)
        else:
            post_data["publish_time"] = None
        
        print(f"Создание поста: {post_data}")
        
        # Создаем пост
        post = supabase_db.db.add_post(post_data)
        
        if post:
            if data.get("draft"):
                status_text = "📝 **Черновик сохранен**"
                is_scheduled = False
            elif data.get("publish_time"):
                # Проверяем, запланирован ли пост на будущее
                if isinstance(data["publish_time"], datetime):
                    is_scheduled = data["publish_time"] > datetime.now(ZoneInfo("UTC"))
                else:
                    is_scheduled = True
                
                if is_scheduled:
                    status_text = "⏰ **Пост запланирован**"
                    # Предлагаем редактирование для запланированного поста
                    response_text = (
                        f"{status_text}\n\n"
                        f"**ID поста:** #{post['id']}\n\n"
                        f"✅ Пост создан успешно!\n\n"
                        f"🤔 **Хотите что-то изменить в посте?**"
                    )
                    
                    keyboard = get_edit_offer_keyboard(post['id'], lang)
                    
                    if is_callback:
                        await message.edit_text(response_text, parse_mode="Markdown", reply_markup=keyboard)
                    else:
                        await message.answer(response_text, parse_mode="Markdown", reply_markup=keyboard)
                    
                    await state.clear()
                    return
                else:
                    status_text = "🚀 **Пост будет опубликован**"
                    is_scheduled = False
            else:
                status_text = "🚀 **Пост будет опубликован**"
                is_scheduled = False
            
            # Для немедленной публикации или черновиков - обычная клавиатура
            response_text = (
                f"{status_text}\n\n"
                f"**ID поста:** #{post['id']}\n\n"
                f"✅ Пост создан успешно!"
            )
            
            keyboard = get_post_actions_keyboard(post['id'], is_scheduled)
            
            if is_callback:
                await message.edit_text(response_text, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await message.answer(response_text, parse_mode="Markdown", reply_markup=keyboard)
                
        else:
            error_text = (
                "❌ **Ошибка создания поста**\n\n"
                "Попробуйте еще раз или обратитесь к администратору."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            if is_callback:
                await message.edit_text(error_text, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await message.answer(error_text, parse_mode="Markdown", reply_markup=keyboard)
        
        await state.clear()
        
    except Exception as e:
        print(f"Ошибка при создании поста: {e}")
        
        error_text = (
            f"❌ **Ошибка создания поста**\n\n"
            f"Техническая ошибка: {str(e)}\n\n"
            f"Попробуйте еще раз."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="menu_create_post_direct")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        try:
            if is_callback:
                await message.edit_text(error_text, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await message.answer(error_text, parse_mode="Markdown", reply_markup=keyboard)
        except:
            pass
        
        await state.clear()

# Все остальные обработчики остаются аналогично оригиналу,
# но с обновленной логикой получения каналов через list_channels(user_id=user_id)

# Дублируем остальные callback обработчики из оригинального файла
@router.callback_query(F.data == "post_confirm")
async def handle_post_confirmation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение создания поста через кнопку"""
    await handle_post_confirmation_text(callback.message, state, is_callback=True)
    await callback.answer()

@router.callback_query(F.data == "edit_offer_accept")
async def handle_edit_offer_accept(callback: CallbackQuery, state: FSMContext):
    """Принятие предложения редактирования"""
    try:
        message_text = callback.message.text
        import re
        post_id_match = re.search(r'#(\d+)', message_text)
        if post_id_match:
            post_id = int(post_id_match.group(1))
        else:
            await callback.answer("❌ Не удалось определить ID поста")
            return
    except:
        await callback.answer("❌ Ошибка обработки")
        return
    
    user_id = callback.from_user.id
    
    # Проверяем права доступа через новую логику каналов
    if not supabase_db.db.can_user_access_post(user_id, post_id):
        await callback.answer("❌ Пост не найден или нет доступа!")
        return
    
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("❌ Пост не найден!")
        return
    
    if post.get("published"):
        await callback.answer("❌ Нельзя редактировать опубликованный пост!")
        return
    
    # Показываем главное меню редактирования
    try:
        from edit_post import show_edit_main_menu
        user = supabase_db.db.get_user(user_id)
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        await callback.answer()
    except ImportError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_direct:{post_id}")],
            [InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
        ])
        
        await callback.message.edit_text(
            f"✏️ **Редактирование поста #{post_id}**\n\n"
            f"Используйте команду `/edit {post_id}` для редактирования.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await callback.answer("Используйте команду /edit " + str(post_id))

@router.callback_query(F.data == "edit_offer_decline")
async def handle_edit_offer_decline(callback: CallbackQuery):
    """Отклонение предложения редактирования"""
    try:
        message_text = callback.message.text
        import re
        post_id_match = re.search(r'#(\d+)', message_text)
        if post_id_match:
            post_id = int(post_id_match.group(1))
        else:
            post_id = 0
    except:
        post_id = 0
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}" if post_id else "posts_menu")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "✅ **Отлично!**\n\n"
        "Пост готов к публикации в запланированное время.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

# Остальные обработчики времени, каналов и навигации остаются такими же,
# но с обновленными вызовами методов базы данных
async def go_back_step(message: Message, state: FSMContext, lang: str):
    """Логика возврата к предыдущему шагу"""
    data = await state.get_data()
    history = data.get("step_history", [])
    
    if not history:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
        ])
        await message.answer("❌ Это первый шаг!", reply_markup=keyboard)
        return
    
    # Удаляем последний шаг из истории
    history.pop()
    data["step_history"] = history
    
    # Очищаем флаги редактирования
    if "editing_field" in data:
        del data["editing_field"]
    if "editing_mode" in data:
        del data["editing_mode"]
    
    await state.set_data(data)
    
    # Определяем предыдущий шаг
    if not history:
        await start_text_step(message, state, lang)
    else:
        prev_step = history[-1]
        
        step_functions = {
            "step_text": start_text_step,
            "step_media": start_media_step,
            "step_format": start_format_step,
            "step_buttons": start_buttons_step,
            "step_time": start_time_step,
            "step_channel": start_channel_step,
        }
        
        if prev_step in step_functions:
            # Удаляем этот шаг тоже, чтобы вернуться к нему заново
            history.pop()
            data["step_history"] = history
            await state.set_data(data)
            
            await step_functions[prev_step](message, state, lang)

# Обработчики времени
@router.message(PostCreationFlow.step_time, F.text)
async def handle_time_text_input(message: Message, state: FSMContext):
    """Обработка текстового ввода времени"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    text_lower = message.text.lower().strip()
    
    # Проверяем команды
    if is_command(message.text, "back"):
        await go_back_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Создание поста отменено", reply_markup=keyboard)
        return
    
    data = await state.get_data()
    
    # Обработка времени
    if is_command(message.text, "now"):
        data["publish_time"] = datetime.now(ZoneInfo("UTC"))
        data["draft"] = False
    elif is_command(message.text, "draft"):
        data["publish_time"] = None
        data["draft"] = True
    else:
        # Пробуем распарсить дату
        try:
            # Поддерживаем разные форматы
            for fmt in ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M"]:
                try:
                    dt = datetime.strptime(message.text.strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("Не удалось распознать формат")
            
            tz = ZoneInfo(user.get("timezone", "UTC"))
            local_dt = dt.replace(tzinfo=tz)
            utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
            
            # Проверяем, что время в будущем
            if utc_dt <= datetime.now(ZoneInfo("UTC")):
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Сейчас", callback_data="time_now")],
                    [InlineKeyboardButton(text="📝 Черновик", callback_data="time_draft")],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
                ])
                await message.answer("❌ Время должно быть в будущем!", reply_markup=keyboard)
                return
            
            data["publish_time"] = utc_dt
            data["draft"] = False
            
        except ValueError:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Сейчас", callback_data="time_now")],
                [InlineKeyboardButton(text="📝 Черновик", callback_data="time_draft")],
                [InlineKeyboardButton(text="⏰ Запланировать", callback_data="time_schedule")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
            ])
            await message.answer(
                "❌ **Неверный формат времени**\n\n"
                "Доступные команды:\n"
                "• `now` - опубликовать сейчас\n"
                "• `draft` - сохранить черновик\n"
                "• Дата и время: `2024-12-25 15:30`\n"
                "• `back` - назад",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
    
    data["step_history"].append("step_time")
    await state.set_data(data)
    await start_channel_step(message, state, lang)

@router.callback_query(F.data == "time_now")
async def handle_time_now(callback: CallbackQuery, state: FSMContext):
    """Опубликовать сейчас"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["publish_time"] = datetime.now(ZoneInfo("UTC"))
    data["draft"] = False
    data["step_history"].append("step_time")
    await state.set_data(data)
    
    await callback.answer()
    await start_channel_step(callback.message, state, lang)

@router.callback_query(F.data == "time_draft")
async def handle_time_draft(callback: CallbackQuery, state: FSMContext):
    """Сохранить как черновик"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["publish_time"] = None
    data["draft"] = True
    data["step_history"].append("step_time")
    await state.set_data(data)
    
    await callback.answer()
    await start_channel_step(callback.message, state, lang)

@router.callback_query(F.data == "time_schedule")
async def handle_time_schedule(callback: CallbackQuery, state: FSMContext):
    """Запланировать время"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Меняем состояние для ожидания ввода времени
    await state.set_state(PostCreationFlow.step_time)
    
    user = supabase_db.db.get_user(callback.from_user.id)
    tz_name = user.get("timezone", "UTC")
    
    text = (
        f"📅 **Введите дату и время публикации**\n\n"
        f"Часовой пояс: {tz_name}\n\n"
        f"Форматы:\n"
        f"• `2024-12-25 15:30`\n"
        f"• `25.12.2024 15:30`\n"
        f"• `25/12/2024 15:30`\n\n"
        f"Или текстовые команды:\n"
        f"• `now` - опубликовать сейчас\n"
        f"• `draft` - сохранить черновик\n"
        f"• `back` - вернуться назад"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Сейчас", callback_data="time_now")],
        [InlineKeyboardButton(text="📝 Черновик", callback_data="time_draft")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

# Обработчики каналов
@router.message(PostCreationFlow.step_channel, F.text)
async def handle_channel_text_input(message: Message, state: FSMContext):
    """Обработка текстового выбора канала"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем команды
    if is_command(message.text, "back"):
        await go_back_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Создание поста отменено", reply_markup=keyboard)
        return
    
    data = await state.get_data()
    user_id = data["user_id"]
    channels = supabase_db.db.list_channels(user_id=user_id)
    
    text = message.text.strip()
    channel = None
    
    # Поиск канала по номеру
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(channels):
            channel = channels[idx]
    # Поиск по username или ID
    else:
        for ch in channels:
            if (ch.get('username') and f"@{ch['username']}" == text) or \
               str(ch['chat_id']) == text or \
               str(ch['id']) == text:
                channel = ch
                break
    
    if not channel:
        available_channels = ", ".join([f"{i+1}" for i in range(len(channels))])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
        ])
        await message.answer(
            f"❌ **Канал не найден**\n\n"
            f"Доступные варианты:\n"
            f"• Номера каналов: {available_channels}\n"
            f"• @username канала\n"
            f"• `back` - назад",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    data["channel_id"] = channel['id']
    data["step_history"].append("step_channel")
    await state.set_data(data)
    
    await start_preview_step(message, state, lang)

@router.callback_query(F.data.startswith("channel_select:"))
async def handle_channel_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора канала через кнопку"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    channel_id = int(callback.data.split(":", 1)[1])
    
    data = await state.get_data()
    data["channel_id"] = channel_id
    data["step_history"].append("step_channel")
    await state.set_data(data)
    
    await callback.answer()
    await start_preview_step(callback.message, state, lang)

# Навигационные обработчики
@router.callback_query(F.data == "post_nav_back")
async def handle_nav_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к предыдущему шагу"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    await go_back_step(callback.message, state, lang)
    await callback.answer()

@router.callback_query(F.data == "post_nav_skip")
async def handle_nav_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить текущий шаг"""
    current_state = await state.get_state()
    data = await state.get_data()
    
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Определяем следующий шаг
    if current_state == PostCreationFlow.step_text:
        data["text"] = None
        data["step_history"].append("step_text")
        await state.set_data(data)
        await start_media_step(callback.message, state, lang)
    elif current_state == PostCreationFlow.step_media:
        data["step_history"].append("step_media")
        await state.set_data(data)
        
        # Проверяем контент после пропуска медиа
        is_valid, error_msg = validate_post_content(data)
        if not is_valid:
            await show_content_missing_dialog(callback.message, state, lang)
            await callback.answer()
            return
        
        await start_format_step(callback.message, state, lang)
    elif current_state == PostCreationFlow.step_format:
        data["step_history"].append("step_format")
        await state.set_data(data)
        await start_buttons_step(callback.message, state, lang)
    elif current_state == PostCreationFlow.step_buttons:
        data["buttons"] = None
        data["step_history"].append("step_buttons")
        await state.set_data(data)
        await start_time_step(callback.message, state, lang)
    
    await callback.answer()

@router.callback_query(F.data == "post_nav_cancel")
async def handle_nav_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменить создание поста"""
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        "❌ **Создание поста отменено**\n\n"
        "Все данные удалены.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()
