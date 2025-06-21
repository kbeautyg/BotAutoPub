from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from zoneinfo import ZoneInfo
from states import PostCreationFlow
import supabase_db
import json
import re
import html

router = Router()

def get_edit_main_menu_keyboard(post_id: int, lang: str = "ru"):
    """Главное меню редактирования поста"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Текст", callback_data=f"edit_field:{post_id}:text"),
            InlineKeyboardButton(text="🖼 Медиа", callback_data=f"edit_field:{post_id}:media")
        ],
        [
            InlineKeyboardButton(text="🎨 Формат", callback_data=f"edit_field:{post_id}:format"),
            InlineKeyboardButton(text="🔘 Кнопки", callback_data=f"edit_field:{post_id}:buttons")
        ],
        [
            InlineKeyboardButton(text="⏰ Время", callback_data=f"edit_field:{post_id}:time"),
            InlineKeyboardButton(text="📺 Канал", callback_data=f"edit_field:{post_id}:channel")
        ],
        [
            InlineKeyboardButton(text="🔄 Полное пересоздание", callback_data=f"edit_recreate:{post_id}")
        ],
        [
            InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}"),
            InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")
        ]
    ])

def format_post_summary(post: dict, channel: dict = None) -> str:
    """Создать краткое описание поста"""
    text = "📝 **Редактирование поста**\n\n"
    
    if channel:
        text += f"**Канал:** {channel['name']}\n"
    
    if post.get("published"):
        text += "**Статус:** ✅ Опубликован (редактирование недоступно)\n"
    elif post.get("draft"):
        text += "**Статус:** 📝 Черновик\n"
    elif post.get("publish_time"):
        text += f"**Статус:** ⏰ Запланирован\n"
    
    # Краткое содержание
    if post.get("text"):
        content_preview = post["text"][:100] + "..." if len(post["text"]) > 100 else post["text"]
        text += f"**Содержание:** {content_preview}\n"
    
    if post.get("media_type"):
        text += f"**Медиа:** {post['media_type']}\n"
    
    if post.get("parse_mode"):
        text += f"**Формат:** {post['parse_mode']}\n"
    
    text += "\n**Выберите что изменить:**"
    
    return text

@router.message(Command("edit"))
async def cmd_edit_post(message: Message, state: FSMContext):
    """Редактировать пост по ID"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    args = message.text.split(maxsplit=1)
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
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ ID поста должен быть числом", reply_markup=keyboard)
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(f"❌ Пост #{post_id} не найден", reply_markup=keyboard)
        return
    
    # Проверяем доступ через канал
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ У вас нет доступа к этому посту", reply_markup=keyboard)
        return
    
    if post.get("published"):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
        ])
        await message.answer("❌ Нельзя редактировать опубликованный пост", reply_markup=keyboard)
        return
    
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    # Показываем главное меню редактирования
    await show_edit_main_menu(message, post_id, post, user, lang)

async def show_edit_main_menu(message: Message, post_id: int, post: dict, user: dict, lang: str):
    """Показать главное меню редактирования"""
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    text = format_post_summary(post, channel)
    keyboard = get_edit_main_menu_keyboard(post_id, lang)
    
    if hasattr(message, 'edit_text'):
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Обработчики для глобальных callback'ов из main.py
async def handle_edit_field_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка редактирования поля (вызывается из main.py)"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    field = parts[2]
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("❌ Пост не найден!")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        await callback.answer("❌ У вас нет доступа к этому посту!")
        return
    
    if post.get("published"):
        await callback.answer("❌ Нельзя редактировать опубликованный пост!")
        return
    
    # Инициализируем состояние редактирования
    await state.set_data({
        "edit_mode": True,
        "post_id": post_id,
        "original_post": post,
        "current_field": field,
        "changes": {}
    })
    
    await start_field_edit(callback.message, state, field, post, user)
    await callback.answer()

async def handle_edit_recreate(callback: CallbackQuery, state: FSMContext):
    """Полное пересоздание поста"""
    post_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("❌ Пост не найден!")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        await callback.answer("❌ У вас нет доступа к этому посту!")
        return
    
    if post.get("published"):
        await callback.answer("❌ Нельзя редактировать опубликованный пост!")
        return
    
    # Инициализируем полное пересоздание
    await state.set_data({
        "edit_mode": True,
        "recreate_mode": True,
        "post_id": post_id,
        "user_id": user_id,
        "text": post.get("text"),
        "media_type": post.get("media_type"),
        "media_file_id": post.get("media_id"),
        "parse_mode": post.get("parse_mode", "HTML"),
        "buttons": json.loads(post["buttons"]) if post.get("buttons") and isinstance(post["buttons"], str) else post.get("buttons"),
        "publish_time": post.get("publish_time"),
        "repeat_interval": post.get("repeat_interval"),
        "channel_id": post.get("channel_id"),
        "draft": post.get("draft", False),
        "step_history": [],
        "current_step": "step_text"
    })
    
    # Запускаем процесс пересоздания с первого шага
    from scheduled_posts import start_text_step
    await state.set_state(PostCreationFlow.step_text)
    
    await callback.message.edit_text(
        f"🔄 **Полное пересоздание поста #{post_id}**\n\n"
        f"Вы можете заново пройти все шаги создания поста.\n"
        f"Текущие данные будут использованы как основа.\n\n"
        f"Начинаем с первого шага:",
        parse_mode="Markdown"
    )
    
    await start_text_step(callback.message, state, user.get("language", "ru"))
    await callback.answer()

async def handle_edit_menu_return(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню редактирования"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    if not post_id:
        await callback.answer("❌ Ошибка: не найден ID поста")
        return
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    post = supabase_db.db.get_post(post_id)
    
    if not post:
        await callback.answer("❌ Пост не найден!")
        return
    
    await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
    await callback.answer()

async def handle_edit_confirm_callback(callback: CallbackQuery, state: FSMContext):
    """Подтверждение изменений"""
    data = await state.get_data()
    post_id = data.get("post_id")
    changes = data.get("changes", {})
    
    if not post_id or not changes:
        await callback.answer("❌ Нет изменений для сохранения")
        return
    
    # Применяем изменения
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
        ])
        
        await callback.message.edit_text(
            f"✅ **Изменения сохранены**\n\n"
            f"Пост #{post_id} успешно обновлен.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            f"❌ **Ошибка сохранения**\n\n"
            f"Не удалось сохранить изменения.",
            parse_mode="Markdown"
        )
    
    await state.clear()
    await callback.answer()

async def handle_edit_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить редактирование поля"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    if not post_id:
        await callback.answer("❌ Ошибка: не найден ID поста")
        return
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    post = supabase_db.db.get_post(post_id)
    
    await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
    await callback.answer()

async def handle_edit_save(callback: CallbackQuery, state: FSMContext):
    """Сохранить изменения поля"""
    data = await state.get_data()
    post_id = data.get("post_id")
    field = data.get("current_field")
    new_value = data.get("new_value")
    
    if not post_id or not field:
        await callback.answer("❌ Ошибка: недостаточно данных")
        return
    
    # Сохраняем изменение
    changes = {field: new_value}
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        await callback.answer("✅ Изменения сохранены")
    else:
        await callback.answer("❌ Ошибка сохранения")

async def handle_edit_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменить редактирование"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    await state.clear()
    
    if post_id:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            "❌ **Редактирование отменено**\n\n"
            "Все несохраненные изменения потеряны.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            "❌ Редактирование отменено",
            reply_markup=keyboard
        )
    
    await callback.answer()

async def start_field_edit(message: Message, state: FSMContext, field: str, post: dict, user: dict):
    """Начать редактирование конкретного поля"""
    lang = user.get("language", "ru")
    
    if field == "text":
        await start_edit_text_step(message, state, lang)
    elif field == "media":
        await start_edit_media_step(message, state, lang)
    elif field == "format":
        await start_edit_format_step(message, state, lang)
    elif field == "buttons":
        await start_edit_buttons_step(message, state, lang)
    elif field == "time":
        await start_edit_time_step(message, state, lang)
    elif field == "channel":
        await start_edit_channel_step(message, state, lang)

async def start_edit_text_step(message: Message, state: FSMContext, lang: str):
    """Редактирование текста поста"""
    await state.set_state(PostCreationFlow.step_text)
    
    data = await state.get_data()
    post = data.get("original_post", {})
    current_text = post.get("text", "")
    
    text = (
        "📝 **Редактирование текста**\n\n"
        f"**Текущий текст:**\n"
        f"{current_text[:300]}{'...' if len(current_text) > 300 else ''}\n\n"
        f"**Отправьте новый текст** или используйте команды:\n"
        f"• `skip` - оставить текущий текст\n"
        f"• `clear` - удалить текст\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Оставить текущий", callback_data="edit_skip")],
        [InlineKeyboardButton(text="🗑 Очистить текст", callback_data="edit_clear_text")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{data.get('post_id')}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])
    
    if hasattr(message, 'edit_text'):
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_edit_media_step(message: Message, state: FSMContext, lang: str):
    """Редактирование медиа поста"""
    await state.set_state(PostCreationFlow.step_media)
    
    data = await state.get_data()
    post = data.get("original_post", {})
    current_media = post.get("media_type", "нет")
    
    text = (
        "🖼 **Редактирование медиа**\n\n"
        f"**Текущее медиа:** {current_media}\n\n"
        f"**Отправьте новое медиа** (фото/видео/GIF) или команды:\n"
        f"• `skip` - оставить текущее медиа\n"
        f"• `remove` - удалить медиа\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Оставить текущее", callback_data="edit_skip")],
        [InlineKeyboardButton(text="🗑 Удалить медиа", callback_data="edit_remove_media")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{data.get('post_id')}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])
    
    if hasattr(message, 'edit_text'):
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_edit_format_step(message: Message, state: FSMContext, lang: str):
    """Редактирование формата поста"""
    data = await state.get_data()
    post = data.get("original_post", {})
    current_format = post.get("parse_mode", "HTML")
    
    text = (
        "🎨 **Редактирование формата**\n\n"
        f"**Текущий формат:** {current_format}\n\n"
        f"**Выберите новый формат:**"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 HTML", callback_data="edit_format_html")],
        [InlineKeyboardButton(text="📋 Markdown", callback_data="edit_format_markdown")],
        [InlineKeyboardButton(text="📄 Без форматирования", callback_data="edit_format_none")],
        [InlineKeyboardButton(text="⏭️ Оставить текущий", callback_data="edit_skip")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{data.get('post_id')}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])
    
    if hasattr(message, 'edit_text'):
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_edit_buttons_step(message: Message, state: FSMContext, lang: str):
    """Редактирование кнопок поста"""
    await state.set_state(PostCreationFlow.step_buttons)
    
    data = await state.get_data()
    post = data.get("original_post", {})
    
    current_buttons = []
    if post.get("buttons"):
        try:
            if isinstance(post["buttons"], str):
                current_buttons = json.loads(post["buttons"])
            else:
                current_buttons = post["buttons"]
        except:
            current_buttons = []
    
    buttons_text = "\n".join([f"• {btn.get('text', '')} | {btn.get('url', '')}" for btn in current_buttons]) if current_buttons else "Нет кнопок"
    
    text = (
        "🔘 **Редактирование кнопок**\n\n"
        f"**Текущие кнопки:**\n{buttons_text}\n\n"
        f"**Отправьте новые кнопки** в формате:\n"
        f"`Текст | URL`\n"
        f"Каждая кнопка на новой строке\n\n"
        f"Или используйте команды:\n"
        f"• `skip` - оставить текущие кнопки\n"
        f"• `remove` - удалить все кнопки\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Оставить текущие", callback_data="edit_skip")],
        [InlineKeyboardButton(text="🗑 Удалить кнопки", callback_data="edit_remove_buttons")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{data.get('post_id')}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])
    
    if hasattr(message, 'edit_text'):
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_edit_time_step(message: Message, state: FSMContext, lang: str):
    """Редактирование времени публикации"""
    data = await state.get_data()
    post = data.get("original_post", {})
    
    if post.get("draft"):
        current_time = "Черновик"
    elif post.get("publish_time"):
        current_time = f"Запланировано: {post['publish_time']}"
    else:
        current_time = "Немедленная публикация"
    
    text = (
        "⏰ **Редактирование времени публикации**\n\n"
        f"**Текущее время:** {current_time}\n\n"
        f"**Выберите новое время или отправьте дату:**\n"
        f"Формат: `YYYY-MM-DD HH:MM`\n"
        f"Пример: `2024-12-25 15:30`\n\n"
        f"Команды:\n"
        f"• `now` - опубликовать сейчас\n"
        f"• `draft` - сохранить как черновик\n"
        f"• `skip` - оставить текущее время\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Сейчас", callback_data="edit_time_now")],
        [InlineKeyboardButton(text="📝 Черновик", callback_data="edit_time_draft")],
        [InlineKeyboardButton(text="⏭️ Оставить текущее", callback_data="edit_skip")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{data.get('post_id')}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])
    
    if hasattr(message, 'edit_text'):
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_edit_channel_step(message: Message, state: FSMContext, lang: str):
    """Редактирование канала поста"""
    data = await state.get_data()
    post = data.get("original_post", {})
    user_id = data.get("original_post", {}).get("created_by")
    
    if not user_id:
        await message.answer("❌ Ошибка: не найден создатель поста")
        return
    
    # Получаем каналы пользователя
    channels = supabase_db.db.get_user_channels(user_id)
    current_channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    text = (
        "📺 **Редактирование канала**\n\n"
        f"**Текущий канал:** {current_channel['name'] if current_channel else 'Неизвестный'}\n\n"
        f"**Выберите новый канал:**\n\n"
    )
    
    buttons = []
    for i, channel in enumerate(channels, 1):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        is_current = channel['id'] == post.get("channel_id")
        text += f"{i}. {admin_status} {channel['name']}" + (" (текущий)" if is_current else "") + "\n"
        
        buttons.append([InlineKeyboardButton(
            text=f"{admin_status} {channel['name']}" + (" ✓" if is_current else ""),
            callback_data=f"edit_channel_select:{channel['id']}"
        )])
    
    buttons.extend([
        [InlineKeyboardButton(text="⏭️ Оставить текущий", callback_data="edit_skip")],
        [InlineKeyboardButton(text="🔙 К меню", callback_data=f"edit_menu:{data.get('post_id')}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel")]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    if hasattr(message, 'edit_text'):
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Обработчики для callback'ов редактирования
@router.callback_query(F.data.startswith("edit_format_"))
async def handle_edit_format_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора формата"""
    format_map = {
        "edit_format_html": "HTML",
        "edit_format_markdown": "Markdown",
        "edit_format_none": None
    }
    
    new_format = format_map.get(callback.data, "HTML")
    data = await state.get_data()
    post_id = data.get("post_id")
    
    # Сохраняем изменение
    changes = {"parse_mode": new_format}
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        await callback.answer(f"✅ Формат изменен на {new_format or 'без форматирования'}")
    else:
        await callback.answer("❌ Ошибка сохранения")

@router.callback_query(F.data.startswith("edit_time_"))
async def handle_edit_time_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора времени"""
    action = callback.data.split("_")[-1]  # now, draft
    data = await state.get_data()
    post_id = data.get("post_id")
    
    if action == "now":
        changes = {
            "publish_time": datetime.now(ZoneInfo("UTC")).isoformat(),
            "draft": False
        }
    elif action == "draft":
        changes = {
            "publish_time": None,
            "draft": True
        }
    else:
        await callback.answer("❌ Неизвестное действие")
        return
    
    # Сохраняем изменение
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        status = "немедленной публикации" if action == "now" else "черновика"
        await callback.answer(f"✅ Время изменено на {status}")
    else:
        await callback.answer("❌ Ошибка сохранения")

@router.callback_query(F.data.startswith("edit_channel_select:"))
async def handle_edit_channel_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора канала"""
    channel_id = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    post_id = data.get("post_id")
    
    # Получаем новый канал для chat_id
    new_channel = supabase_db.db.get_channel(channel_id)
    if not new_channel:
        await callback.answer("❌ Канал не найден")
        return
    
    # Сохраняем изменение
    changes = {
        "channel_id": channel_id,
        "chat_id": new_channel["chat_id"]
    }
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        await callback.answer(f"✅ Канал изменен на {new_channel['name']}")
    else:
        await callback.answer("❌ Ошибка сохранения")

# Обработчики для удаления/очистки
@router.callback_query(F.data == "edit_clear_text")
async def handle_edit_clear_text(callback: CallbackQuery, state: FSMContext):
    """Очистить текст поста"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    changes = {"text": None}
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        await callback.answer("✅ Текст удален")
    else:
        await callback.answer("❌ Ошибка сохранения")

@router.callback_query(F.data == "edit_remove_media")
async def handle_edit_remove_media(callback: CallbackQuery, state: FSMContext):
    """Удалить медиа поста"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    changes = {
        "media_type": None,
        "media_id": None
    }
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        await callback.answer("✅ Медиа удалено")
    else:
        await callback.answer("❌ Ошибка сохранения")

@router.callback_query(F.data == "edit_remove_buttons")
async def handle_edit_remove_buttons(callback: CallbackQuery, state: FSMContext):
    """Удалить кнопки поста"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    changes = {"buttons": None}
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
        await callback.answer("✅ Кнопки удалены")
    else:
        await callback.answer("❌ Ошибка сохранения")

# Обработчики для ввода текста при редактировании
@router.message(PostCreationFlow.step_text, F.text)
async def handle_edit_text_input(message: Message, state: FSMContext):
    """Обработка нового текста при редактировании"""
    data = await state.get_data()
    
    # Проверяем, находимся ли мы в режиме редактирования
    if not data.get("edit_mode"):
        return  # Пропускаем, если это не режим редактирования
    
    post_id = data.get("post_id")
    
    # Проверяем команды
    if message.text.lower().strip() in ["skip", "пропустить"]:
        user_id = message.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        await show_edit_main_menu(message, post_id, post, user, user.get("language", "ru"))
        return
    
    if message.text.lower().strip() in ["cancel", "отмена"]:
        await handle_edit_cancel_text(message, state)
        return
    
    # Сохраняем новый текст
    changes = {"text": message.text}
    success = supabase_db.db.update_post(post_id, changes)
    
    if success:
        user_id = message.from_user.id
        user = supabase_db.db.get_user(user_id)
        post = supabase_db.db.get_post(post_id)
        
        await show_edit_main_menu(message, post_id, post, user, user.get("language", "ru"))
        await message.answer("✅ Текст обновлен!")
    else:
        await message.answer("❌ Ошибка сохранения текста")

async def handle_edit_cancel_text(message: Message, state: FSMContext):
    """Отменить редактирование через текстовую команду"""
    data = await state.get_data()
    post_id = data.get("post_id")
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}" if post_id else "posts_menu")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await message.answer(
        "❌ **Редактирование отменено**\n\n"
        "Все несохраненные изменения потеряны.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
