import json
import re
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from zoneinfo import ZoneInfo
from states import EditPost
import supabase_db
from __init__ import TEXTS

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

def get_edit_main_menu_keyboard(post_id: int, lang: str = "ru"):
    """Главное меню редактирования поста"""
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
            InlineKeyboardButton(text="👀 Предпросмотр", callback_data=f"edit_preview:{post_id}"),
            InlineKeyboardButton(text="✅ Сохранить", callback_data=f"edit_save:{post_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"post_view:{post_id}")
        ]
    ])

def get_edit_step_keyboard(post_id: int, step: str, can_skip: bool = True):
    """Клавиатура для шага редактирования"""
    buttons = []
    
    nav_row = []
    if can_skip:
        nav_row.append(InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"edit_skip:{step}:{post_id}"))
    nav_row.append(InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{post_id}"))
    
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"post_view:{post_id}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_format_edit_keyboard(post_id: int):
    """Клавиатура выбора формата при редактировании"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 HTML", callback_data=f"edit_format_set:html:{post_id}")],
        [InlineKeyboardButton(text="📋 Markdown", callback_data=f"edit_format_set:markdown:{post_id}")],
        [InlineKeyboardButton(text="📄 Без форматирования", callback_data=f"edit_format_set:none:{post_id}")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"post_view:{post_id}")]
    ])

def get_time_edit_keyboard(post_id: int):
    """Клавиатура выбора времени при редактировании"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"edit_time_set:now:{post_id}")],
        [InlineKeyboardButton(text="📝 Сделать черновиком", callback_data=f"edit_time_set:draft:{post_id}")],
        [InlineKeyboardButton(text="⏰ Указать время", callback_data=f"edit_time_input:{post_id}")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"edit_skip:time:{post_id}")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"post_view:{post_id}")]
    ])

def get_channels_edit_keyboard(channels: list, post_id: int):
    """Клавиатура выбора канала при редактировании"""
    buttons = []
    
    for channel in channels:
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text = f"{admin_status} {channel['name']}"
        buttons.append([InlineKeyboardButton(
            text=text, 
            callback_data=f"edit_channel_set:{channel['id']}:{post_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"edit_skip:channel:{post_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{post_id}")])
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"post_view:{post_id}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_interval(seconds: int) -> str:
    """Форматировать интервал повтора"""
    if seconds == 0:
        return "не повторяется"
    elif seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days}d"
    elif seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours}h"
    elif seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes}m"
    else:
        return f"{seconds}s"

def parse_time_for_user(time_str: str, user: dict) -> datetime:
    """Парсить время от пользователя с учетом его настроек"""
    # Поддерживаем разные форматы
    formats = ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M"]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError("Неверный формат времени")
    
    # Применяем часовой пояс пользователя
    tz = ZoneInfo(user.get("timezone", "UTC"))
    local_dt = dt.replace(tzinfo=tz)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    
    return utc_dt

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    """Команда редактирования поста"""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
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
    
    # Проверки доступа
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await message.answer(
            f"❌ **Пост #{post_id} не найден**\n\n"
            f"Пост не существует или у вас нет к нему доступа.",
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
            f"Опубликованные посты нельзя редактировать.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    # Показываем меню редактирования
    await show_edit_menu(message, post_id, user, lang)

async def show_edit_menu(message: Message, post_id: int, user: dict, lang: str):
    """Показать главное меню редактирования"""
    post = supabase_db.db.get_post(post_id)
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    text = f"✏️ **Редактирование поста #{post_id}**\n\n"
    
    # Краткая информация о посте
    if post.get("text"):
        preview_text = post["text"][:100]
        if len(post["text"]) > 100:
            preview_text += "..."
        text += f"**Текст:** {preview_text}\n"
    else:
        text += "**Текст:** _не указан_\n"
    
    text += f"**Медиа:** {'есть' if post.get('media_id') else 'нет'}\n"
    text += f"**Формат:** {post.get('parse_mode', 'HTML')}\n"
    
    if post.get("buttons"):
        try:
            buttons = json.loads(post["buttons"]) if isinstance(post["buttons"], str) else post["buttons"]
            text += f"**Кнопки:** {len(buttons)} шт.\n"
        except:
            text += "**Кнопки:** есть\n"
    else:
        text += "**Кнопки:** нет\n"
    
    if channel:
        text += f"**Канал:** {channel['name']}\n"
    
    if post.get("publish_time"):
        from view_post import format_time_for_user
        formatted_time = format_time_for_user(post['publish_time'], user)
        text += f"**Время:** {formatted_time}\n"
    elif post.get("draft"):
        text += "**Статус:** Черновик\n"
    else:
        text += "**Статус:** Не запланирован\n"
    
    text += "\n**Выберите что изменить:**"
    
    keyboard = get_edit_main_menu_keyboard(post_id, lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Callback обработчики для меню редактирования
@router.callback_query(F.data.startswith("edit_menu:"))
async def callback_edit_menu(callback: CallbackQuery):
    """Показать меню редактирования через callback"""
    post_id = int(callback.data.split(":", 1)[1])
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    post = supabase_db.db.get_post(post_id)
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    text = f"✏️ **Редактирование поста #{post_id}**\n\n"
    
    # Краткая информация о посте
    if post.get("text"):
        preview_text = post["text"][:100]
        if len(post["text"]) > 100:
            preview_text += "..."
        text += f"**Текст:** {preview_text}\n"
    else:
        text += "**Текст:** _не указан_\n"
    
    text += f"**Медиа:** {'есть' if post.get('media_id') else 'нет'}\n"
    text += f"**Формат:** {post.get('parse_mode', 'HTML')}\n"
    
    if post.get("buttons"):
        try:
            buttons = json.loads(post["buttons"]) if isinstance(post["buttons"], str) else post["buttons"]
            text += f"**Кнопки:** {len(buttons)} шт.\n"
        except:
            text += "**Кнопки:** есть\n"
    else:
        text += "**Кнопки:** нет\n"
    
    if channel:
        text += f"**Канал:** {channel['name']}\n"
    
    if post.get("publish_time"):
        from view_post import format_time_for_user
        formatted_time = format_time_for_user(post['publish_time'], user)
        text += f"**Время:** {formatted_time}\n"
    elif post.get("draft"):
        text += "**Статус:** Черновик\n"
    else:
        text += "**Статус:** Не запланирован\n"
    
    text += "\n**Выберите что изменить:**"
    
    keyboard = get_edit_main_menu_keyboard(post_id, lang)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# Начало редактирования конкретного поля
@router.callback_query(F.data.startswith("edit_start:"))
async def callback_edit_start_field(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование конкретного поля"""
    parts = callback.data.split(":", 2)
    field = parts[1]
    post_id = int(parts[2])
    
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    post = supabase_db.db.get_post(post_id)
    
    # Сохраняем состояние редактирования
    await state.set_data({
        "post_id": post_id,
        "editing_field": field,
        "original_post": post
    })
    
    if field == "text":
        await state.set_state(EditPost.text)
        current_text = post.get("text", "")
        
        text = (
            f"📝 **Редактирование текста поста #{post_id}**\n\n"
            f"**Текущий текст:**\n{current_text}\n\n"
            f"Отправьте новый текст или используйте кнопки:"
        )
        
        keyboard = get_edit_step_keyboard(post_id, "text", can_skip=True)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    elif field == "media":
        await state.set_state(EditPost.media)
        has_media = bool(post.get("media_id"))
        media_type = post.get("media_type", "нет")
        
        text = (
            f"🖼 **Редактирование медиа поста #{post_id}**\n\n"
            f"**Текущее медиа:** {'есть (' + media_type + ')' if has_media else 'нет'}\n\n"
            f"Отправьте новое фото/видео/GIF или используйте кнопки:"
        )
        
        keyboard = get_edit_step_keyboard(post_id, "media", can_skip=True)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    elif field == "format":
        current_format = post.get("parse_mode", "HTML")
        
        text = (
            f"🎨 **Редактирование формата поста #{post_id}**\n\n"
            f"**Текущий формат:** {current_format}\n\n"
            f"Выберите новый формат:"
        )
        
        keyboard = get_format_edit_keyboard(post_id)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    elif field == "buttons":
        await state.set_state(EditPost.buttons)
        current_buttons = post.get("buttons")
        
        if current_buttons:
            try:
                buttons = json.loads(current_buttons) if isinstance(current_buttons, str) else current_buttons
                buttons_text = "\n".join([f"• {b['text']} | {b['url']}" for b in buttons])
            except:
                buttons_text = "Ошибка в формате кнопок"
        else:
            buttons_text = "Нет кнопок"
        
        text = (
            f"🔘 **Редактирование кнопок поста #{post_id}**\n\n"
            f"**Текущие кнопки:**\n{buttons_text}\n\n"
            f"Отправьте новые кнопки в формате:\n"
            f"`Текст кнопки | https://example.com`\n"
            f"Каждая кнопка на новой строке.\n\n"
            f"Или используйте кнопки:"
        )
        
        keyboard = get_edit_step_keyboard(post_id, "buttons", can_skip=True)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    elif field == "time":
        text = (
            f"⏰ **Редактирование времени поста #{post_id}**\n\n"
            f"Выберите новое время публикации:"
        )
        
        keyboard = get_time_edit_keyboard(post_id)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    elif field == "channel":
        project_id = post.get("project_id")
        channels = supabase_db.db.list_channels(project_id=project_id)
        
        current_channel = supabase_db.db.get_channel(post.get("channel_id"))
        current_name = current_channel.get("name", "Неизвестный") if current_channel else "Не выбран"
        
        text = (
            f"📺 **Редактирование канала поста #{post_id}**\n\n"
            f"**Текущий канал:** {current_name}\n\n"
            f"Выберите новый канал:"
        )
        
        keyboard = get_channels_edit_keyboard(channels, post_id)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    await callback.answer()

# Обработка ввода текста при редактировании
@router.message(EditPost.text)
async def handle_edit_text_input(message: Message, state: FSMContext):
    """Обработка ввода нового текста"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    if is_command(message.text, "skip"):
        await state.clear()
        await show_edit_menu_after_change(message, post_id, "Текст оставлен без изменений")
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 К посту", callback_data=f"post_view:{post_id}")]
        ])
        await message.answer("❌ Редактирование отменено", reply_markup=keyboard)
        return
    
    # Обновляем текст поста
    supabase_db.db.update_post(post_id, {"text": message.text})
    await state.clear()
    
    await show_edit_menu_after_change(message, post_id, "Текст обновлен")

# Обработка медиа при редактировании
@router.message(EditPost.media, F.photo | F.video | F.animation)
async def handle_edit_media_input(message: Message, state: FSMContext):
    """Обработка нового медиа"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    # Определяем тип и ID медиа
    if message.photo:
        media_type = "photo"
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_id = message.video.file_id
    elif message.animation:
        media_type = "animation"
        media_id = message.animation.file_id
    
    # Обновляем медиа поста
    supabase_db.db.update_post(post_id, {
        "media_type": media_type,
        "media_id": media_id
    })
    await state.clear()
    
    await show_edit_menu_after_change(message, post_id, f"Медиа обновлено ({media_type})")

@router.message(EditPost.media, F.text)
async def handle_edit_media_text(message: Message, state: FSMContext):
    """Обработка текстовых команд для медиа"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    if is_command(message.text, "skip"):
        await state.clear()
        await show_edit_menu_after_change(message, post_id, "Медиа оставлено без изменений")
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 К посту", callback_data=f"post_view:{post_id}")]
        ])
        await message.answer("❌ Редактирование отменено", reply_markup=keyboard)
        return
    
    await message.answer("❌ Отправьте фото, видео или GIF, либо используйте команды skip/cancel")

# Обработка кнопок при редактировании
@router.message(EditPost.buttons, F.text)
async def handle_edit_buttons_input(message: Message, state: FSMContext):
    """Обработка новых кнопок"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    if is_command(message.text, "skip"):
        await state.clear()
        await show_edit_menu_after_change(message, post_id, "Кнопки оставлены без изменений")
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 К посту", callback_data=f"post_view:{post_id}")]
        ])
        await message.answer("❌ Редактирование отменено", reply_markup=keyboard)
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
                "❌ **Неверный формат кнопок**\n\n"
                "Используйте формат: `Текст | URL`\n"
                "Каждая кнопка на новой строке.",
                parse_mode="Markdown"
            )
            return
        
        # Обновляем кнопки поста
        supabase_db.db.update_post(post_id, {"buttons": buttons})
        await state.clear()
        
        await show_edit_menu_after_change(message, post_id, f"Кнопки обновлены ({len(buttons)} шт.)")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка в формате кнопок: {str(e)}")

# Callback обработчики для быстрых действий
@router.callback_query(F.data.startswith("edit_format_set:"))
async def callback_set_format(callback: CallbackQuery):
    """Установить формат поста"""
    parts = callback.data.split(":", 2)
    format_type = parts[1]
    post_id = int(parts[2])
    
    format_map = {
        "html": "HTML",
        "markdown": "Markdown",
        "none": None
    }
    
    new_format = format_map.get(format_type, "HTML")
    supabase_db.db.update_post(post_id, {"parse_mode": new_format})
    
    await show_edit_menu_after_callback_change(callback, post_id, f"Формат изменен на {new_format or 'обычный'}")

@router.callback_query(F.data.startswith("edit_time_set:"))
async def callback_set_time_quick(callback: CallbackQuery):
    """Быстрая установка времени"""
    parts = callback.data.split(":", 2)
    time_type = parts[1]
    post_id = int(parts[2])
    
    if time_type == "now":
        now = datetime.now(ZoneInfo("UTC"))
        supabase_db.db.update_post(post_id, {
            "publish_time": now,
            "draft": False
        })
        message = "Пост будет опубликован сейчас"
    elif time_type == "draft":
        supabase_db.db.update_post(post_id, {
            "publish_time": None,
            "draft": True
        })
        message = "Пост сохранен как черновик"
    
    await show_edit_menu_after_callback_change(callback, post_id, message)

@router.callback_query(F.data.startswith("edit_time_input:"))
async def callback_time_input(callback: CallbackQuery, state: FSMContext):
    """Ввод времени вручную"""
    post_id = int(callback.data.split(":", 1)[1])
    
    user = supabase_db.db.get_user(callback.from_user.id)
    tz_name = user.get("timezone", "UTC")
    
    await state.set_data({"post_id": post_id, "editing_field": "time"})
    await state.set_state(EditPost.time)
    
    text = (
        f"📅 **Введите новое время публикации**\n\n"
        f"Ваш часовой пояс: {tz_name}\n\n"
        f"Форматы:\n"
        f"• `2024-12-25 15:30`\n"
        f"• `25.12.2024 15:30`\n"
        f"• `25/12/2024 15:30`\n\n"
        f"Или текстовые команды:\n"
        f"• `skip` - оставить текущее время\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = get_edit_step_keyboard(post_id, "time", can_skip=True)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.message(EditPost.time, F.text)
async def handle_edit_time_input(message: Message, state: FSMContext):
    """Обработка ввода времени"""
    data = await state.get_data()
    post_id = data.get("post_id")
    user = supabase_db.db.get_user(message.from_user.id)
    
    if is_command(message.text, "skip"):
        await state.clear()
        await show_edit_menu_after_change(message, post_id, "Время оставлено без изменений")
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 К посту", callback_data=f"post_view:{post_id}")]
        ])
        await message.answer("❌ Редактирование отменено", reply_markup=keyboard)
        return
    
    try:
        # Парсим новое время
        utc_time = parse_time_for_user(message.text, user)
        
        # Проверяем, что время в будущем
        if utc_time <= datetime.now(ZoneInfo("UTC")):
            await message.answer("❌ Время должно быть в будущем!")
            return
        
        # Обновляем время
        supabase_db.db.update_post(post_id, {
            "publish_time": utc_time,
            "draft": False,
            "notified": False
        })
        await state.clear()
        
        await show_edit_menu_after_change(message, post_id, f"Время изменено на {message.text}")
        
    except ValueError:
        await message.answer(
            "❌ **Неверный формат времени**\n\n"
            "Используйте один из форматов:\n"
            "• `2024-12-25 15:30`\n"
            "• `25.12.2024 15:30`\n"
            "• `25/12/2024 15:30`",
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("edit_channel_set:"))
async def callback_set_channel(callback: CallbackQuery):
    """Установить канал поста"""
    parts = callback.data.split(":", 2)
    channel_id = int(parts[1])
    post_id = int(parts[2])
    
    channel = supabase_db.db.get_channel(channel_id)
    supabase_db.db.update_post(post_id, {"channel_id": channel_id})
    
    channel_name = channel.get("name", "Неизвестный") if channel else "Неизвестный"
    await show_edit_menu_after_callback_change(callback, post_id, f"Канал изменен на {channel_name}")

# Обработчики пропуска и отмены
@router.callback_query(F.data.startswith("edit_skip:"))
async def callback_edit_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить редактирование поля"""
    parts = callback.data.split(":", 2)
    field = parts[1]
    post_id = int(parts[2])
    
    await state.clear()
    await show_edit_menu_after_callback_change(callback, post_id, f"{field.title()} оставлен без изменений")

# Предпросмотр и сохранение
@router.callback_query(F.data.startswith("edit_preview:"))
async def callback_edit_preview(callback: CallbackQuery):
    """Предпросмотр отредактированного поста"""
    post_id = int(callback.data.split(":", 1)[1])
    user = supabase_db.db.get_user(callback.from_user.id)
    
    post = supabase_db.db.get_post(post_id)
    
    # Отправляем предпросмотр поста
    from view_post import send_post_preview
    await send_post_preview(callback.message, post)
    
    # Информация о посте
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    info_text = f"👀 **Предпросмотр поста #{post_id}**\n\n"
    
    if channel:
        info_text += f"**Канал:** {channel['name']}\n"
    
    if post.get("published"):
        info_text += "**Статус:** ✅ Опубликован\n"
    elif post.get("draft"):
        info_text += "**Статус:** 📝 Черновик\n"
    elif post.get("publish_time"):
        from view_post import format_time_for_user
        formatted_time = format_time_for_user(post['publish_time'], user)
        info_text += f"**Статус:** ⏰ Запланирован на {formatted_time}\n"
    
    parse_mode_value = post.get("parse_mode")
    if parse_mode_value:
        info_text += f"**Формат:** {parse_mode_value}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К редактированию", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="✅ Сохранить изменения", callback_data=f"edit_save:{post_id}")],
        [InlineKeyboardButton(text="👀 К посту", callback_data=f"post_view:{post_id}")]
    ])
    
    await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_save:"))
async def callback_edit_save(callback: CallbackQuery):
    """Сохранить изменения и завершить редактирование"""
    post_id = int(callback.data.split(":", 1)[1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"✅ **Изменения сохранены**\n\n"
        f"Пост #{post_id} успешно отредактирован.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

# Вспомогательные функции
async def show_edit_menu_after_change(message: Message, post_id: int, change_message: str):
    """Показать меню редактирования после изменения через сообщение"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Показываем сообщение об изменении
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К редактированию", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="👀 Предпросмотр", callback_data=f"edit_preview:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_save:{post_id}")]
    ])
    
    await message.answer(
        f"✅ **{change_message}**\n\n"
        f"Что делать дальше?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def show_edit_menu_after_callback_change(callback: CallbackQuery, post_id: int, change_message: str):
    """Показать меню редактирования после изменения через callback"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К редактированию", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="👀 Предпросмотр", callback_data=f"edit_preview:{post_id}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_save:{post_id}")]
    ])
    
    await callback.message.edit_text(
        f"✅ **{change_message}**\n\n"
        f"Что делать дальше?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()
