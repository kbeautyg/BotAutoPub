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

# Навигационные кнопки
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
        [InlineKeyboardButton(text="📝 Изменить текст", callback_data="edit_text")],
        [InlineKeyboardButton(text="🖼 Изменить медиа", callback_data="edit_media")],
        [InlineKeyboardButton(text="🎨 Изменить формат", callback_data="edit_format")],
        [InlineKeyboardButton(text="🔘 Изменить кнопки", callback_data="edit_buttons")],
        [InlineKeyboardButton(text="⏰ Изменить время", callback_data="edit_time")],
        [InlineKeyboardButton(text="📺 Изменить канал", callback_data="edit_channel")],
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
        "step_history": []
    })
    
    await start_text_step(message, state, lang)

async def start_text_step(message: Message, state: FSMContext, lang: str):
    """Шаг 1: Ввод текста поста"""
    await state.set_state(PostCreationFlow.step_text)
    
    text = (
        "📝 **Создание поста - Шаг 1/7**\n\n"
        "**Введите текст поста**\n\n"
        "Вы можете:\n"
        "• Написать текст поста\n"
        "• Пропустить этот шаг, если пост будет только с медиа\n\n"
        "💡 *Форматирование можно будет настроить на следующем шаге*"
    )
    
    keyboard = get_navigation_keyboard("step_text", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_text, F.text)
async def handle_text_input(message: Message, state: FSMContext):
    """Обработка ввода текста"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
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
        "• Отправить фото\n"
        "• Отправить видео\n"
        "• Отправить GIF/анимацию\n"
        "• Пропустить этот шаг\n\n"
        "💡 *Медиа будет прикреплено к тексту поста*"
    )
    
    keyboard = get_navigation_keyboard("step_media", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_media, F.photo)
async def handle_photo_input(message: Message, state: FSMContext):
    """Обработка фото"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["media_type"] = "photo"
    data["media_file_id"] = message.photo[-1].file_id
    data["step_history"].append("step_media")
    await state.set_data(data)
    
    await start_format_step(message, state, lang)

@router.message(PostCreationFlow.step_media, F.video)
async def handle_video_input(message: Message, state: FSMContext):
    """Обработка видео"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["media_type"] = "video"
    data["media_file_id"] = message.video.file_id
    data["step_history"].append("step_media")
    await state.set_data(data)
    
    await start_format_step(message, state, lang)

@router.message(PostCreationFlow.step_media, F.animation)
async def handle_animation_input(message: Message, state: FSMContext):
    """Обработка GIF/анимации"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["media_type"] = "animation"
    data["media_file_id"] = message.animation.file_id
    data["step_history"].append("step_media")
    await state.set_data(data)
    
    await start_format_step(message, state, lang)

async def start_format_step(message: Message, state: FSMContext, lang: str):
    """Шаг 3: Выбор формата"""
    await state.set_state(PostCreationFlow.step_format)
    
    text = (
        "🎨 **Создание поста - Шаг 3/7**\n\n"
        "**Выберите формат текста**\n\n"
        "• **HTML** - поддержка <b>жирного</b>, <i>курсива</i>, <a href='#'>ссылок</a>\n"
        "• **Markdown** - поддержка **жирного**, *курсива*, [ссылок](url)\n"
        "• **Без форматирования** - обычный текст\n\n"
        "💡 *Рекомендуется HTML для большей гибкости*"
    )
    
    keyboard = get_format_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("format_"))
async def handle_format_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора формата"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    format_map = {
        "format_html": "HTML",
        "format_markdown": "Markdown",
        "format_none": None
    }
    
    data = await state.get_data()
    data["parse_mode"] = format_map[callback.data]
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
        "Формат: каждая кнопка на новой строке\n"
        "`Текст кнопки | https://example.com`\n\n"
        "Пример:\n"
        "`Наш сайт | https://example.com`\n"
        "`Telegram | https://t.me/channel`\n\n"
        "Или пропустите этот шаг, если кнопки не нужны."
    )
    
    keyboard = get_navigation_keyboard("step_buttons", lang, can_skip=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(PostCreationFlow.step_buttons, F.text)
async def handle_buttons_input(message: Message, state: FSMContext):
    """Обработка ввода кнопок"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
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
        
        data = await state.get_data()
        data["buttons"] = buttons if buttons else None
        data["step_history"].append("step_buttons")
        await state.set_data(data)
        
        await start_time_step(message, state, lang)
        
    except Exception as e:
        await message.answer(
            "❌ **Ошибка в формате кнопок**\n\n"
            "Используйте формат: `Текст | URL`\n"
            "Каждая кнопка на новой строке.",
            parse_mode="Markdown"
        )

async def start_time_step(message: Message, state: FSMContext, lang: str):
    """Шаг 5: Выбор времени публикации"""
    await state.set_state(PostCreationFlow.step_time)
    
    text = (
        "⏰ **Создание поста - Шаг 5/7**\n\n"
        "**Когда опубликовать пост?**\n\n"
        "Выберите один из вариантов:"
    )
    
    keyboard = get_time_options_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

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
    
    # Получаем формат времени пользователя
    date_fmt = user.get("date_format", "YYYY-MM-DD")
    time_fmt = user.get("time_format", "HH:MM")
    tz_name = user.get("timezone", "UTC")
    
    text = (
        f"📅 **Введите дату и время публикации**\n\n"
        f"Формат: `{date_fmt} {time_fmt}`\n"
        f"Часовой пояс: {tz_name}\n\n"
        f"Пример: `2024-12-25 15:30`"
    )
    
    keyboard = get_navigation_keyboard("step_time", lang, can_skip=False)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.message(PostCreationFlow.step_time, F.text)
async def handle_scheduled_time_input(message: Message, state: FSMContext):
    """Обработка ввода запланированного времени"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    try:
        # Парсим время (упрощенная версия)
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        tz = ZoneInfo(user.get("timezone", "UTC"))
        local_dt = dt.replace(tzinfo=tz)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
        
        # Проверяем, что время в будущем
        if utc_dt <= datetime.now(ZoneInfo("UTC")):
            await message.answer(
                "❌ **Время должно быть в будущем**\n\n"
                "Введите корректную дату и время.",
                parse_mode="Markdown"
            )
            return
        
        data = await state.get_data()
        data["publish_time"] = utc_dt
        data["draft"] = False
        data["step_history"].append("step_time")
        await state.set_data(data)
        
        await start_channel_step(message, state, lang)
        
    except ValueError:
        await message.answer(
            "❌ **Неверный формат времени**\n\n"
            "Используйте формат: `YYYY-MM-DD HH:MM`\n"
            "Пример: `2024-12-25 15:30`",
            parse_mode="Markdown"
        )

async def start_channel_step(message: Message, state: FSMContext, lang: str):
    """Шаг 6: Выбор канала"""
    await state.set_state(PostCreationFlow.step_channel)
    
    data = await state.get_data()
    project_id = data["project_id"]
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    
    text = (
        "📺 **Создание поста - Шаг 6/7**\n\n"
        "**Выберите канал для публикации**\n\n"
        "✅ - Бот является администратором\n"
        "❓ - Статус не проверен\n\n"
        "⚠️ *Для публикации бот должен быть администратором канала*"
    )
    
    keyboard = get_channels_keyboard(channels, lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("channel_select:"))
async def handle_channel_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора канала"""
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
    
    # Формируем предварительный просмотр
    preview_text = "👀 **Предварительный просмотр поста**\n\n"
    preview_text += f"**Канал:** {channel['name']}\n"
    
    if data.get("publish_time"):
        preview_text += f"**Время публикации:** {data['publish_time'].strftime('%Y-%m-%d %H:%M UTC')}\n"
    elif data.get("draft"):
        preview_text += "**Статус:** Черновик\n"
    else:
        preview_text += "**Статус:** Опубликовать сейчас\n"
    
    if data.get("parse_mode"):
        preview_text += f"**Формат:** {data['parse_mode']}\n"
    
    preview_text += "\n" + "─" * 30 + "\n\n"
    
    # Добавляем текст поста
    if data.get("text"):
        preview_text += data["text"]
    else:
        preview_text += "*[Пост без текста]*"
    
    # Информация о медиа
    if data.get("media_type"):
        preview_text += f"\n\n📎 *Прикреплено: {data['media_type']}*"
    
    # Информация о кнопках
    if data.get("buttons"):
        preview_text += f"\n\n🔘 *Кнопок: {len(data['buttons'])}*"
    
    keyboard = get_preview_keyboard(lang)
    await message.answer(preview_text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "post_confirm")
async def handle_post_confirmation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение создания поста"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    
    # Создаем пост в базе данных
    post_data = {
        "user_id": data["user_id"],
        "project_id": data["project_id"],
        "channel_id": data["channel_id"],
        "text": data.get("text"),
        "media_type": data.get("media_type"),
        "media_file_id": data.get("media_file_id"),
        "parse_mode": data.get("parse_mode"),
        "buttons": data.get("buttons"),
        "publish_time": data.get("publish_time"),
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
            f"**ID поста:** #{post['id']}\n"
            f"Пост создан успешно! ✅",
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

# Обработчики навигации
@router.callback_query(F.data == "post_nav_back")
async def handle_nav_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к предыдущему шагу"""
    data = await state.get_data()
    history = data.get("step_history", [])
    
    if not history:
        await callback.answer("Это первый шаг!")
        return
    
    # Удаляем последний шаг из истории
    history.pop()
    data["step_history"] = history
    await state.set_data(data)
    
    # Определяем предыдущий шаг
    if not history:
        current_step = "step_text"
    else:
        current_step = history[-1]
    
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Переходим к предыдущему шагу
    step_functions = {
        "step_text": start_text_step,
        "step_media": start_media_step,
        "step_format": start_format_step,
        "step_buttons": start_buttons_step,
        "step_time": start_time_step,
        "step_channel": start_channel_step,
        "step_preview": start_preview_step
    }
    
    if current_step in step_functions:
        await step_functions[current_step](callback.message, state, lang)
    
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

@router.callback_query(F.data == "post_preview")
async def handle_back_to_preview(callback: CallbackQuery, state: FSMContext):
    """Вернуться к предпросмотру"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    await start_preview_step(callback.message, state, lang)
    await callback.answer()
