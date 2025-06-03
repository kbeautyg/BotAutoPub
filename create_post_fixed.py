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
    """Клавиатура выбора формата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 HTML", callback_data="format_html")],
        [InlineKeyboardButton(text="📋 Markdown", callback_data="format_markdown")],
        [InlineKeyboardButton(text="📄 Без форматирования", callback_data="format_none")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])

def get_time_options_keyboard(lang: str = "ru"):
    """Клавиатура опций времени публикации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data="time_now")],
        [InlineKeyboardButton(text="📝 Сохранить как черновик", callback_data="time_draft")],
        [InlineKeyboardButton(text="⏰ Запланировать время", callback_data="time_schedule")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="post_nav_back")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])

def get_channels_keyboard(channels: list, lang: str = "ru"):
    """Клавиатура выбора канала"""
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
    """Клавиатура предварительного просмотра"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="post_confirm")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_edit_menu")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="post_nav_cancel")]
    ])

def get_edit_menu_keyboard(lang: str = "ru"):
    """Клавиатура меню редактирования"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить текст", callback_data="edit_field:text")],
        [InlineKeyboardButton(text="🖼 Изменить медиа", callback_data="edit_field:media")],
        [InlineKeyboardButton(text="🎨 Изменить формат", callback_data="edit_field:format")],
        [InlineKeyboardButton(text="🔘 Изменить кнопки", callback_data="edit_field:buttons")],
        [InlineKeyboardButton(text="⏰ Изменить время", callback_data="edit_field:time")],
        [InlineKeyboardButton(text="📺 Изменить канал", callback_data="edit_field:channel")],
        [InlineKeyboardButton(text="🔙 К предпросмотру", callback_data="post_preview")]
    ])

@router.message(Command("create"))
async def cmd_create_post(message: Message, state: FSMContext):
    """Начать создание поста"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем наличие проекта
    project_id = user.get("current_project")
    if not project_id:
        await message.answer("❌ Нет активного проекта. Создайте проект через /project")
        return
    
    # Проверяем наличие каналов
    channels = supabase_db.db.list_channels(project_id=project_id)
    if not channels:
        await message.answer(
            "❌ **Нет доступных каналов**\n\n"
            "Сначала добавьте канал через /channels",
            parse_mode="Markdown"
        )
        return
    
    # Инициализируем данные поста
    await state.set_data({
        "user_id": user_id,
        "project_id": project_id,
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

# Быстрое создание поста одной командой
@router.message(Command("quickpost"))
async def cmd_quick_post(message: Message, state: FSMContext):
    """Быстрое создание поста: /quickpost <канал> <время> <текст>"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    project_id = user.get("current_project")
    
    if not project_id:
        await message.answer("❌ Нет активного проекта")
        return
    
    # Парсим аргументы
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "📝 **Быстрое создание поста**\n\n"
            "Формат: `/quickpost <канал> <время> <текст>`\n\n"
            "Примеры:\n"
            "• `/quickpost @channel now Текст поста`\n"
            "• `/quickpost 1 draft Черновик поста`\n"
            "• `/quickpost 2 2024-12-25_15:30 Запланированный пост`\n\n"
            "Канал: @username, ID или номер в списке\n"
            "Время: now, draft или YYYY-MM-DD_HH:MM",
            parse_mode="Markdown"
        )
        return
    
    channel_ref = parts[1]
    time_ref = parts[2]
    text = parts[3]
    
    # Находим канал
    channels = supabase_db.db.list_channels(project_id=project_id)
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
        await message.answer(f"❌ Канал '{channel_ref}' не найден")
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
            await message.answer("❌ Неверный формат времени. Используйте: YYYY-MM-DD_HH:MM")
            return
    
    # Создаем пост
    post_data = {
        "user_id": user_id,
        "project_id": project_id,
        "channel_id": channel['id'],
        "text": text,
        "parse_mode": "HTML",
        "publish_time": publish_time.isoformat() if publish_time else None,
        "draft": draft,
        "published": False
    }
    
    post = supabase_db.db.add_post(post_data)
    
    if post:
        status = "📝 черновик" if draft else "⏰ запланирован" if publish_time else "создан"
        await message.answer(
            f"✅ **Пост #{post['id']} {status}**\n\n"
            f"Канал: {channel['name']}\n"
            f"Текст: {text[:50]}...",
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Ошибка создания поста")

async def start_text_step(message: Message, state: FSMContext, lang: str):
    """Шаг 1: Ввод текста поста"""
    await state.set_state(PostCreationFlow.step_text)
    
    text = (
        "📝 **Создание поста - Шаг 1/7**\n\n"
        "**Введите текст поста**\n\n"
        "Вы можете:\n"
        "• Написать текст поста\n"
        "• Отправить `skip` или `пропустить` для поста без текста\n"
        "• Отправить `cancel` или `отмена` для отмены\n\n"
        "💡 *Форматирование можно будет настроить на следующем шаге*"
    )
    
    keyboard = get_navigation_keyboard("step_text", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_text)
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
        await message.answer("❌ Создание поста отменено")
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
        "Вы можете:\n"
        "• Отправить фото, видео или GIF\n"
        "• Отправить `skip` для пропуска\n"
        "• Отправить `back` для возврата\n\n"
        "💡 *Медиа будет прикреплено к тексту поста*"
    )
    
    keyboard = get_navigation_keyboard("step_media", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_media)
async def handle_media_input(message: Message, state: FSMContext):
    """Обработка медиа или команд"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем текстовые команды
    if message.text and is_command(message.text, "skip"):
        data = await state.get_data()
        data["step_history"].append("step_media")
        await state.set_data(data)
        await start_format_step(message, state, lang)
        return
    
    if message.text and is_command(message.text, "back"):
        await go_back_step(message, state, lang)
        return
    
    if message.text and is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Создание поста отменено")
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
        await message.answer(
            "❌ Отправьте медиа файл (фото/видео/GIF) или команду:\n"
            "• `skip` - пропустить\n"
            "• `back` - назад\n"
            "• `cancel` - отмена",
            parse_mode="Markdown"
        )

async def start_format_step(message: Message, state: FSMContext, lang: str):
    """Шаг 3: Выбор формата"""
    await state.set_state(PostCreationFlow.step_format)
    
    text = (
        "🎨 **Создание поста - Шаг 3/7**\n\n"
        "**Выберите формат текста**\n\n"
        "• **HTML** - <b>жирный</b>, <i>курсив</i>, <a href='#'>ссылки</a>\n"
        "• **Markdown** - **жирный**, *курсив*, [ссылки](url)\n"
        "• **Обычный** - без форматирования\n\n"
        "Отправьте: `html`, `markdown`, `none` или `skip`"
    )
    
    keyboard = get_format_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_format)
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
        await message.answer("❌ Создание поста отменено")
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
        await message.answer(
            "❌ Выберите формат:\n"
            "• `html` - HTML форматирование\n"
            "• `markdown` - Markdown форматирование\n"
            "• `none` - без форматирования\n"
            "• `skip` - пропустить (HTML по умолчанию)",
            parse_mode="Markdown"
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
        "Отправьте кнопки или `skip` для пропуска"
    )
    
    keyboard = get_navigation_keyboard("step_buttons", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_buttons)
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
        await message.answer("❌ Создание поста отменено")
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
            await message.answer(
                "❌ Не найдено корректных кнопок\n\n"
                "Используйте формат: `Текст | URL`",
                parse_mode="Markdown"
            )
            return
        
        data = await state.get_data()
        data["buttons"] = buttons
        data["step_history"].append("step_buttons")
        await state.set_data(data)
        
        await start_time_step(message, state, lang)
        
    except Exception as e:
        await message.answer(
            "❌ **Ошибка в формате кнопок**\n\n"
            f"Ошибка: {str(e)}\n\n"
            "Используйте формат: `Текст | URL`",
            parse_mode="Markdown"
        )

async def start_time_step(message: Message, state: FSMContext, lang: str):
    """Шаг 5: Выбор времени публикации"""
    await state.set_state(PostCreationFlow.step_time)
    
    text = (
        "⏰ **Создание поста - Шаг 5/7**\n\n"
        "**Когда опубликовать пост?**\n\n"
        "Отправьте:\n"
        "• `now` - опубликовать сейчас\n"
        "• `draft` - сохранить как черновик\n"
        "• Дату и время: `2024-12-25 15:30`\n\n"
        "Ваш часовой пояс: " + state.get_data().get('timezone', 'UTC')
    )
    
    keyboard = get_time_options_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_time)
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
        await message.answer("❌ Создание поста отменено")
        return
    
    data = await state.get_data()
    
    # Обработка времени
    if text_lower in ["now", "сейчас"]:
        data["publish_time"] = datetime.now(ZoneInfo("UTC"))
        data["draft"] = False
    elif text_lower in ["draft", "черновик"]:
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
                await message.answer("❌ Время должно быть в будущем!")
                return
            
            data["publish_time"] = utc_dt
            data["draft"] = False
            
        except ValueError:
            await message.answer(
                "❌ **Неверный формат времени**\n\n"
                "Используйте один из форматов:\n"
                "• `2024-12-25 15:30`\n"
                "• `25.12.2024 15:30`\n"
                "• `25/12/2024 15:30`\n"
                "• `now` - сейчас\n"
                "• `draft` - черновик",
                parse_mode="Markdown"
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
        f"Или отправьте:\n"
        f"• `now` - опубликовать сейчас\n"
        f"• `draft` - сохранить черновик\n"
        f"• `back` - вернуться назад"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

async def start_channel_step(message: Message, state: FSMContext, lang: str):
    """Шаг 6: Выбор канала"""
    await state.set_state(PostCreationFlow.step_channel)
    
    data = await state.get_data()
    project_id = data["project_id"]
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    
    text = (
        "📺 **Создание поста - Шаг 6/7**\n\n"
        "**Выберите канал для публикации**\n\n"
    )
    
    # Список каналов с номерами
    for i, channel in enumerate(channels, 1):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text += f"{i}. {admin_status} {channel['name']}\n"
    
    text += "\nОтправьте номер канала или его @username"
    
    keyboard = get_channels_keyboard(channels, lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_channel)
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
        await message.answer("❌ Создание поста отменено")
        return
    
    data = await state.get_data()
    project_id = data["project_id"]
    channels = supabase_db.db.list_channels(project_id=project_id)
    
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
        await message.answer(
            f"❌ Канал '{text}' не найден\n\n"
            "Отправьте номер канала из списка или @username",
            parse_mode="Markdown"
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

async def start_preview_step(message: Message, state: FSMContext, lang: str):
    """Шаг 7: Предварительный просмотр"""
    await state.set_state(PostCreationFlow.step_preview)
    
    data = await state.get_data()
    
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(data["channel_id"])
    
    # Сначала отправляем превью самого поста
    await send_post_preview(message, data)
    
    # Затем отправляем информацию с кнопками действий
    info_text = "👀 **Предварительный просмотр**\n\n"
    info_text += f"**Канал:** {channel['name']}\n"
    
    if data.get("publish_time"):
        if isinstance(data["publish_time"], datetime):
            time_str = data["publish_time"].strftime('%Y-%m-%d %H:%M UTC')
        else:
            time_str = str(data["publish_time"])
        info_text += f"**Время публикации:** {time_str}\n"
    elif data.get("draft"):
        info_text += "**Статус:** Черновик\n"
    else:
        info_text += "**Статус:** Опубликовать сейчас\n"
    
    if data.get("parse_mode"):
        info_text += f"**Формат:** {data['parse_mode']}\n"
    
    info_text += "\n✅ Всё верно? Подтвердите или отредактируйте."
    
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

@router.callback_query(F.data == "post_confirm")
async def handle_post_confirmation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение создания поста"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    
    # Подготовка данных для сохранения
    post_data = {
        "user_id": data["user_id"],
        "project_id": data["project_id"],
        "channel_id": data["channel_id"],
        "text": data.get("text"),
        "media_type": data.get("media_type"),
        "media_id": data.get("media_file_id"),  # Исправлено: media_id вместо media_file_id
        "format": data.get("parse_mode"),  # Исправлено: format вместо parse_mode
        "buttons": data.get("buttons"),
        "publish_time": data.get("publish_time").isoformat() if isinstance(data.get("publish_time"), datetime) else data.get("publish_time"),
        "repeat_interval": data.get("repeat_interval"),
        "draft": data.get("draft", False),
        "published": False
    }
    
    post = supabase_db.db.add_post(post_data)
    
    if post:
        if data.get("draft"):
            status_text = "📝 **Черновик сохранен**"
        elif data.get("publish_time"):
            status_text = "⏰ **Пост запланирован**"
        else:
            status_text = "🚀 **Пост будет опубликован**"
        
        await callback.message.edit_text(
            f"{status_text}\n\n"
            f"**ID поста:** #{post['id']}\n\n"
            f"✅ Пост создан успешно!\n\n"
            f"Команды для управления:\n"
            f"• `/view {post['id']}` - просмотр\n"
            f"• `/edit {post['id']}` - редактировать\n"
            f"• `/delete {post['id']}` - удалить",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "❌ **Ошибка создания поста**\n\n"
            "Попробуйте еще раз или обратитесь к администратору.",
            parse_mode="Markdown"
        )
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "post_edit_menu")
async def handle_edit_menu(callback: CallbackQuery, state: FSMContext):
    """Показать меню редактирования"""
    text = (
        "✏️ **Редактирование поста**\n\n"
        "Что хотите изменить?"
    )
    
    keyboard = get_edit_menu_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("edit_field:"))
async def handle_edit_field(callback: CallbackQuery, state: FSMContext):
    """Редактирование конкретного поля"""
    field = callback.data.split(":", 1)[1]
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["editing_field"] = field
    await state.set_data(data)
    
    if field == "text":
        await state.set_state(PostCreationFlow.step_text)
        current_text = data.get("text", "")
        await callback.message.edit_text(
            f"📝 **Редактирование текста**\n\n"
            f"Текущий текст:\n{current_text[:200]}...\n\n"
            f"Отправьте новый текст или `cancel` для отмены",
            parse_mode="Markdown"
        )
    elif field == "media":
        await state.set_state(PostCreationFlow.step_media)
        await callback.message.edit_text(
            "🖼 **Редактирование медиа**\n\n"
            "Отправьте новое фото/видео или `cancel` для отмены",
            parse_mode="Markdown"
        )
    elif field == "format":
        await callback.message.edit_text(
            "🎨 **Редактирование формата**\n\n"
            "Выберите новый формат:",
            reply_markup=get_format_keyboard(lang),
            parse_mode="Markdown"
        )
    elif field == "buttons":
        await state.set_state(PostCreationFlow.step_buttons)
        current_buttons = data.get("buttons", [])
        buttons_text = "\n".join([f"{b['text']} | {b['url']}" for b in current_buttons]) if current_buttons else "Нет кнопок"
        await callback.message.edit_text(
            f"🔘 **Редактирование кнопок**\n\n"
            f"Текущие кнопки:\n{buttons_text}\n\n"
            f"Отправьте новые кнопки или `cancel` для отмены",
            parse_mode="Markdown"
        )
    elif field == "time":
        await callback.message.edit_text(
            "⏰ **Редактирование времени**\n\n"
            "Когда опубликовать пост?",
            reply_markup=get_time_options_keyboard(lang),
            parse_mode="Markdown"
        )
    elif field == "channel":
        channels = supabase_db.db.list_channels(project_id=data["project_id"])
        await callback.message.edit_text(
            "📺 **Редактирование канала**\n\n"
            "Выберите новый канал:",
            reply_markup=get_channels_keyboard(channels, lang),
            parse_mode="Markdown"
        )
    
    await callback.answer()

@router.callback_query(F.data == "post_preview")
async def handle_back_to_preview(callback: CallbackQuery, state: FSMContext):
    """Вернуться к предпросмотру после редактирования"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Очищаем флаг редактирования
    data = await state.get_data()
    if "editing_field" in data:
        del data["editing_field"]
    await state.set_data(data)
    
    await start_preview_step(callback.message, state, lang)
    await callback.answer()

# Обработчики навигации
@router.callback_query(F.data == "post_nav_back")
async def handle_nav_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к предыдущему шагу"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    await go_back_step(callback.message, state, lang)
    await callback.answer()

async def go_back_step(message: Message, state: FSMContext, lang: str):
    """Логика возврата к предыдущему шагу"""
    data = await state.get_data()
    history = data.get("step_history", [])
    
    if not history:
        await message.answer("Это первый шаг!")
        return
    
    # Удаляем последний шаг из истории
    history.pop()
    data["step_history"] = history
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

@router.callback_query(F.data == "post_nav_skip")
async def handle_nav_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить текущий шаг"""
    current_state = await state.get_state()
    data = await state.get_data()
    
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Определяем следующий шаг
    if current_state == PostCreationFlow.step_text:
        data["step_history"].append("step_text")
        await state.set_data(data)
        await start_media_step(callback.message, state, lang)
    elif current_state == PostCreationFlow.step_media:
        data["step_history"].append("step_media")
        await state.set_data(data)
        await start_format_step(callback.message, state, lang)
    elif current_state == PostCreationFlow.step_buttons:
        data["step_history"].append("step_buttons")
        await state.set_data(data)
        await start_time_step(callback.message, state, lang)
    
    await callback.answer()

@router.callback_query(F.data == "post_nav_cancel")
async def handle_nav_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменить создание поста"""
    await state.clear()
    await callback.message.edit_text(
        "❌ **Создание поста отменено**\n\n"
        "Все данные удалены.",
        parse_mode="Markdown"
    )
    await callback.answer()