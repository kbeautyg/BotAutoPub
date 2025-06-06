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
    "confirm": ["confirm", "подтвердить", "/confirm", "да", "yes"],
    "now": ["now", "сейчас"],
    "draft": ["draft", "черновик"]
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
            InlineKeyboardButton(text="📝 Текст", callback_data=f"edit_single:text:{post_id}"),
            InlineKeyboardButton(text="🖼 Медиа", callback_data=f"edit_single:media:{post_id}")
        ],
        [
            InlineKeyboardButton(text="🎨 Формат", callback_data=f"edit_single:format:{post_id}"),
            InlineKeyboardButton(text="🔘 Кнопки", callback_data=f"edit_single:buttons:{post_id}")
        ],
        [
            InlineKeyboardButton(text="⏰ Время", callback_data=f"edit_single:time:{post_id}"),
            InlineKeyboardButton(text="📺 Канал", callback_data=f"edit_single:channel:{post_id}")
        ],
        [
            InlineKeyboardButton(text="👀 Предпросмотр", callback_data=f"edit_preview:{post_id}"),
            InlineKeyboardButton(text="🔄 Пересоздать пост", callback_data=f"edit_recreate:{post_id}")
        ],
        [
            InlineKeyboardButton(text="📋 К посту", callback_data=f"post_full_view:{post_id}"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ])

def get_field_edit_keyboard(post_id: int, field: str, can_skip: bool = True):
    """Клавиатура для редактирования конкретного поля"""
    buttons = []
    
    if can_skip:
        buttons.append([InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"edit_skip:{post_id}:{field}")])
    
    buttons.append([
        InlineKeyboardButton(text="🔙 В меню", callback_data=f"edit_menu:{post_id}"),
        InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_cancel:{post_id}")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_format_edit_keyboard(post_id: int):
    """Клавиатура выбора формата при редактировании"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 HTML", callback_data=f"edit_format_set:{post_id}:HTML")],
        [InlineKeyboardButton(text="📋 Markdown", callback_data=f"edit_format_set:{post_id}:Markdown")],
        [InlineKeyboardButton(text="📄 Без форматирования", callback_data=f"edit_format_set:{post_id}:None")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"edit_skip:{post_id}:format")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_cancel:{post_id}")]
    ])

def get_time_edit_keyboard(post_id: int):
    """Клавиатура опций времени при редактировании"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"edit_time_set:{post_id}:now")],
        [InlineKeyboardButton(text="📝 Сохранить как черновик", callback_data=f"edit_time_set:{post_id}:draft")],
        [InlineKeyboardButton(text="⏰ Ввести время", callback_data=f"edit_time_input:{post_id}")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"edit_skip:{post_id}:time")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_cancel:{post_id}")]
    ])

def get_preview_edit_keyboard(post_id: int):
    """Клавиатура предпросмотра при редактировании"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить изменения", callback_data=f"edit_save:{post_id}")],
        [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="❌ Отменить изменения", callback_data=f"edit_cancel:{post_id}")]
    ])

def format_interval(seconds: int) -> str:
    """Форматировать интервал повтора в человекочитаемый вид"""
    if seconds == 0:
        return "нет"
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

def parse_time_improved(user: dict, text: str):
    """Улучшенный парсинг времени с поддержкой разных форматов"""
    try:
        # Поддерживаем разные форматы
        formats = ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M"]
        
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(text.strip(), fmt)
                break
            except ValueError:
                continue
        
        if dt is None:
            raise ValueError("Не удалось распознать формат времени")
        
        # Применяем часовой пояс пользователя
        tz_name = user.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        
        local_dt = dt.replace(tzinfo=tz)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
        
        return utc_dt
    except Exception as e:
        raise ValueError(f"Ошибка парсинга времени: {str(e)}")

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    """Команда редактирования поста с улучшенным интерфейсом"""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    if len(args) < 2:
        await message.answer(
            "📝 **Редактирование поста**\n\n"
            "Использование: `/edit <ID поста>`\n\n"
            "Пример: `/edit 123`",
            parse_mode="Markdown"
        )
        return
    
    try:
        post_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID поста должен быть числом")
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer("❌ Пост не найден или у вас нет доступа")
        return
    
    if post.get("published"):
        await message.answer("❌ Нельзя редактировать опубликованный пост")
        return
    
    # Показываем главное меню редактирования
    await show_edit_main_menu(message, post_id, post, user, lang)

async def show_edit_main_menu(message: Message, post_id: int, post: dict, user: dict, lang: str):
    """Показать главное меню редактирования"""
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    channel_name = channel["name"] if channel else "Неизвестный канал"
    
    # Форматируем информацию о посте
    text = f"✏️ **Редактирование поста #{post_id}**\n\n"
    
    # Базовая информация
    text += f"📺 **Канал:** {channel_name}\n"
    
    # Статус поста
    if post.get("draft"):
        text += "📝 **Статус:** Черновик\n"
    elif post.get("publish_time"):
        try:
            from view_post import format_time_for_user
            formatted_time = format_time_for_user(post['publish_time'], user)
            text += f"⏰ **Запланирован:** {formatted_time}\n"
        except:
            text += f"⏰ **Запланирован:** {post['publish_time']}\n"
    
    # Краткое содержание
    post_text = post.get("text", "")
    if post_text:
        preview = post_text[:100] + "..." if len(post_text) > 100 else post_text
        text += f"\n📝 **Текст:** {preview}\n"
    
    # Медиа
    if post.get("media_id"):
        media_type = post.get("media_type", "медиа")
        text += f"🖼 **Медиа:** {media_type}\n"
    
    # Формат
    parse_mode = post.get("parse_mode", "HTML")
    text += f"🎨 **Формат:** {parse_mode}\n"
    
    # Кнопки
    buttons = post.get("buttons")
    if buttons:
        try:
            if isinstance(buttons, str):
                buttons_list = json.loads(buttons)
            else:
                buttons_list = buttons
            if buttons_list:
                text += f"🔘 **Кнопки:** {len(buttons_list)} шт.\n"
        except:
            pass
    
    text += "\n**Выберите, что хотите изменить:**"
    
    keyboard = get_edit_main_menu_keyboard(post_id, lang)
    
    if hasattr(message, 'edit_text'):
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Обработчики для редактирования отдельных полей
@router.callback_query(F.data.startswith("edit_single:"))
async def handle_single_field_edit(callback: CallbackQuery, state: FSMContext):
    """Редактирование одного поля поста"""
    parts = callback.data.split(":")
    field = parts[1]
    post_id = int(parts[2])
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer("❌ Пост не найден или нет доступа!")
        return
    
    # Сохраняем состояние редактирования
    await state.set_data({
        "editing_post_id": post_id,
        "editing_field": field,
        "original_post": post,
        "user_settings": user
    })
    
    if field == "text":
        await edit_text_field(callback, state, post)
    elif field == "media":
        await edit_media_field(callback, state, post)
    elif field == "format":
        await edit_format_field(callback, state, post)
    elif field == "buttons":
        await edit_buttons_field(callback, state, post)
    elif field == "time":
        await edit_time_field(callback, state, post)
    elif field == "channel":
        await edit_channel_field(callback, state, post)
    
    await callback.answer()

async def edit_text_field(callback: CallbackQuery, state: FSMContext, post: dict):
    """Редактирование текста поста"""
    await state.set_state(EditPost.text)
    
    current_text = post.get("text", "Нет текста")
    text = (
        f"📝 **Редактирование текста поста #{post['id']}**\n\n"
        f"**Текущий текст:**\n"
        f"{current_text[:300]}{'...' if len(current_text) > 300 else ''}\n\n"
        f"**Отправьте новый текст поста:**\n\n"
        f"Команды:\n"
        f"• `skip` - оставить текущий текст\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = get_field_edit_keyboard(post['id'], "text")
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.text, F.text)
async def handle_text_edit_input(message: Message, state: FSMContext):
    """Обработка ввода нового текста"""
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    
    if is_command(message.text, "skip"):
        await finish_field_edit(message, state, post_id, "text", None)
        return
    
    if is_command(message.text, "cancel"):
        await cancel_edit(message, state, post_id)
        return
    
    # Сохраняем новый текст
    await finish_field_edit(message, state, post_id, "text", message.text)

async def edit_media_field(callback: CallbackQuery, state: FSMContext, post: dict):
    """Редактирование медиа поста"""
    await state.set_state(EditPost.media)
    
    media_info = "нет медиа"
    if post.get("media_id"):
        media_type = post.get("media_type", "медиа")
        if media_type == "photo":
            media_info = "📷 фото"
        elif media_type == "video":
            media_info = "🎬 видео"
        elif media_type == "animation":
            media_info = "🎞 GIF"
        else:
            media_info = f"📎 {media_type}"
    
    text = (
        f"🖼 **Редактирование медиа поста #{post['id']}**\n\n"
        f"**Текущее медиа:** {media_info}\n\n"
        f"**Отправьте новое медиа:**\n"
        f"• Фото\n"
        f"• Видео\n"
        f"• GIF/анимация\n\n"
        f"Команды:\n"
        f"• `skip` - оставить текущее медиа\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = get_field_edit_keyboard(post['id'], "media")
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.media, F.text | F.photo | F.video | F.animation)
async def handle_media_edit_input(message: Message, state: FSMContext):
    """Обработка ввода нового медиа"""
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    
    if message.text and is_command(message.text, "skip"):
        await finish_field_edit(message, state, post_id, "media", None)
        return
    
    if message.text and is_command(message.text, "cancel"):
        await cancel_edit(message, state, post_id)
        return
    
    # Обработка медиа
    media_data = None
    if message.photo:
        media_data = {"media_type": "photo", "media_id": message.photo[-1].file_id}
    elif message.video:
        media_data = {"media_type": "video", "media_id": message.video.file_id}
    elif message.animation:
        media_data = {"media_type": "animation", "media_id": message.animation.file_id}
    
    if media_data:
        await finish_field_edit(message, state, post_id, "media", media_data)
    else:
        await message.answer(
            "❌ **Неизвестная команда**\n\n"
            "Отправьте медиа файл или используйте команды:\n"
            "• `skip` - пропустить\n"
            "• `cancel` - отменить"
        )

async def edit_format_field(callback: CallbackQuery, state: FSMContext, post: dict):
    """Редактирование формата поста"""
    current_format = post.get("parse_mode", "HTML")
    
    text = (
        f"🎨 **Редактирование формата поста #{post['id']}**\n\n"
        f"**Текущий формат:** {current_format}\n\n"
        f"**Выберите новый формат:**\n"
        f"• **HTML** - <b>жирный</b>, <i>курсив</i>, <a href='#'>ссылки</a>\n"
        f"• **Markdown** - **жирный**, *курсив*, [ссылки](url)\n"
        f"• **Обычный** - без форматирования"
    )
    
    keyboard = get_format_edit_keyboard(post['id'])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("edit_format_set:"))
async def handle_format_set(callback: CallbackQuery, state: FSMContext):
    """Установка формата"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    format_value = parts[2]
    
    if format_value == "None":
        format_value = None
    
    await finish_field_edit_callback(callback, state, post_id, "format", format_value)

async def edit_buttons_field(callback: CallbackQuery, state: FSMContext, post: dict):
    """Редактирование кнопок поста"""
    await state.set_state(EditPost.buttons)
    
    # Получаем текущие кнопки
    current_buttons = post.get("buttons", [])
    if isinstance(current_buttons, str):
        try:
            current_buttons = json.loads(current_buttons)
        except:
            current_buttons = []
    
    buttons_text = "нет кнопок"
    if current_buttons:
        buttons_list = []
        for btn in current_buttons:
            if isinstance(btn, dict) and btn.get("text") and btn.get("url"):
                buttons_list.append(f"• {btn['text']} | {btn['url']}")
        if buttons_list:
            buttons_text = "\n".join(buttons_list)
    
    text = (
        f"🔘 **Редактирование кнопок поста #{post['id']}**\n\n"
        f"**Текущие кнопки:**\n{buttons_text}\n\n"
        f"**Отправьте новые кнопки:**\n"
        f"Формат: `Текст кнопки | https://example.com`\n"
        f"Каждая кнопка на новой строке\n\n"
        f"Пример:\n"
        f"```\n"
        f"Наш сайт | https://example.com\n"
        f"Telegram | https://t.me/channel\n"
        f"```\n\n"
        f"Команды:\n"
        f"• `skip` - оставить текущие кнопки\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = get_field_edit_keyboard(post['id'], "buttons")
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.buttons, F.text)
async def handle_buttons_edit_input(message: Message, state: FSMContext):
    """Обработка ввода новых кнопок"""
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    
    if is_command(message.text, "skip"):
        await finish_field_edit(message, state, post_id, "buttons", None)
        return
    
    if is_command(message.text, "cancel"):
        await cancel_edit(message, state, post_id)
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
        
        await finish_field_edit(message, state, post_id, "buttons", buttons)
        
    except Exception as e:
        await message.answer(
            "❌ **Ошибка в формате кнопок**\n\n"
            f"Ошибка: {str(e)}\n\n"
            "Используйте формат: `Текст | URL`",
            parse_mode="Markdown"
        )

async def edit_time_field(callback: CallbackQuery, state: FSMContext, post: dict):
    """Редактирование времени публикации"""
    data = await state.get_data()
    user_settings = data["user_settings"]
    
    # Форматируем текущее время
    current_time_str = "черновик"
    if post.get("publish_time"):
        try:
            from view_post import format_time_for_user
            current_time_str = format_time_for_user(post['publish_time'], user_settings)
        except:
            current_time_str = str(post.get("publish_time"))
    elif post.get("draft"):
        current_time_str = "черновик"
    
    timezone = user_settings.get("timezone", "UTC")
    
    text = (
        f"⏰ **Редактирование времени поста #{post['id']}**\n\n"
        f"**Текущее время:** {current_time_str}\n"
        f"**Ваш часовой пояс:** {timezone}\n\n"
        f"**Выберите новое время публикации:**"
    )
    
    keyboard = get_time_edit_keyboard(post['id'])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("edit_time_set:"))
async def handle_time_set(callback: CallbackQuery, state: FSMContext):
    """Установка времени публикации"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    time_option = parts[2]
    
    if time_option == "now":
        time_value = {"publish_time": datetime.now(ZoneInfo("UTC")), "draft": False}
    elif time_option == "draft":
        time_value = {"publish_time": None, "draft": True}
    
    await finish_field_edit_callback(callback, state, post_id, "time", time_value)

@router.callback_query(F.data.startswith("edit_time_input:"))
async def handle_time_input_request(callback: CallbackQuery, state: FSMContext):
    """Запрос ввода времени"""
    post_id = int(callback.data.split(":")[1])
    
    await state.set_state(EditPost.time)
    data = await state.get_data()
    user_settings = data["user_settings"]
    tz_name = user_settings.get("timezone", "UTC")
    
    text = (
        f"📅 **Введите дату и время публикации**\n\n"
        f"Часовой пояс: {tz_name}\n\n"
        f"Форматы:\n"
        f"• `2024-12-25 15:30`\n"
        f"• `25.12.2024 15:30`\n"
        f"• `25/12/2024 15:30`\n\n"
        f"Команды:\n"
        f"• `now` - опубликовать сейчас\n"
        f"• `draft` - сохранить черновик\n"
        f"• `cancel` - отменить"
    )
    
    keyboard = get_field_edit_keyboard(post_id, "time", can_skip=False)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.message(EditPost.time, F.text)
async def handle_time_edit_input(message: Message, state: FSMContext):
    """Обработка ввода времени"""
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    user_settings = data["user_settings"]
    
    if is_command(message.text, "cancel"):
        await cancel_edit(message, state, post_id)
        return
    
    # Обработка времени
    if is_command(message.text, "now"):
        time_value = {"publish_time": datetime.now(ZoneInfo("UTC")), "draft": False}
    elif is_command(message.text, "draft"):
        time_value = {"publish_time": None, "draft": True}
    else:
        # Пробуем распарсить дату
        try:
            new_time = parse_time_improved(user_settings, message.text)
            
            # Проверяем, что время в будущем
            if new_time <= datetime.now(ZoneInfo("UTC")):
                await message.answer("❌ Время должно быть в будущем!")
                return
            
            time_value = {"publish_time": new_time, "draft": False}
            
        except ValueError as e:
            await message.answer(
                f"❌ **Неверный формат времени**\n\n"
                f"Ошибка: {str(e)}\n\n"
                f"Используйте один из форматов или команды.",
                parse_mode="Markdown"
            )
            return
    
    await finish_field_edit(message, state, post_id, "time", time_value)

async def edit_channel_field(callback: CallbackQuery, state: FSMContext, post: dict):
    """Редактирование канала публикации"""
    data = await state.get_data()
    user_settings = data["user_settings"]
    
    # Получаем текущий канал
    current_channel_name = "неизвестный канал"
    current_channel = supabase_db.db.get_channel(post.get("channel_id"))
    if current_channel:
        current_channel_name = current_channel["name"]
    
    # Получаем список доступных каналов
    project_id = user_settings.get("current_project")
    channels = supabase_db.db.list_channels(project_id=project_id)
    
    if not channels:
        await callback.message.edit_text("❌ Нет доступных каналов для переноса")
        await callback.answer()
        return
    
    text = (
        f"📺 **Редактирование канала поста #{post['id']}**\n\n"
        f"**Текущий канал:** {current_channel_name}\n\n"
        f"**Выберите новый канал:**\n\n"
    )
    
    # Список каналов с номерами
    for i, channel in enumerate(channels, 1):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text += f"{i}. {admin_status} {channel['name']}\n"
    
    text += (
        f"\nТекстовые команды:\n"
        f"• Номер канала (например: `1`)\n"
        f"• @username канала\n"
        f"• `skip` - оставить текущий канал\n"
        f"• `cancel` - отменить редактирование"
    )
    
    # Создаем кнопки для каналов
    buttons = []
    for i, channel in enumerate(channels):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        button_text = f"{admin_status} {channel['name']}"
        buttons.append([InlineKeyboardButton(
            text=button_text, 
            callback_data=f"edit_channel_set:{post['id']}:{channel['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"edit_skip:{post['id']}:channel")])
    buttons.append([InlineKeyboardButton(text="🔙 В меню", callback_data=f"edit_menu:{post['id']}")])
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_cancel:{post['id']}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("edit_channel_set:"))
async def handle_channel_set(callback: CallbackQuery, state: FSMContext):
    """Установка канала"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    channel_id = int(parts[2])
    
    # Получаем канал для получения chat_id
    channel = supabase_db.db.get_channel(channel_id)
    channel_data = {"channel_id": channel_id}
    if channel:
        channel_data["chat_id"] = channel.get("chat_id")
    
    await finish_field_edit_callback(callback, state, post_id, "channel", channel_data)

@router.message(EditPost.channel, F.text)
async def handle_channel_edit_text_input(message: Message, state: FSMContext):
    """Обработка текстового выбора канала при редактировании"""
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    user_settings = data["user_settings"]
    
    if is_command(message.text, "skip"):
        await finish_field_edit(message, state, post_id, "channel", None)
        return
    
    if is_command(message.text, "cancel"):
        await cancel_edit(message, state, post_id)
        return
    
    project_id = user_settings.get("current_project")
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
        available_channels = ", ".join([f"{i+1}" for i in range(len(channels))])
        await message.answer(
            f"❌ **Канал не найден**\n\n"
            f"Доступные варианты:\n"
            f"• Номера каналов: {available_channels}\n"
            f"• @username канала\n"
            f"• `skip` - пропустить",
            parse_mode="Markdown"
        )
        return
    
    # Получаем канал для получения chat_id
    channel_data = {"channel_id": channel['id']}
    if channel:
        channel_data["chat_id"] = channel.get("chat_id")
    
    await finish_field_edit(message, state, post_id, "channel", channel_data)

# Обработчики предпросмотра и завершения редактирования
@router.callback_query(F.data.startswith("edit_preview:"))
async def handle_edit_preview(callback: CallbackQuery, state: FSMContext):
    """Предпросмотр поста при редактировании"""
    post_id = int(callback.data.split(":")[1])
    
    # Получаем актуальную версию поста
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("❌ Пост не найден!")
        return
    
    # Отправляем превью
    try:
        from view_post import send_post_preview
        await send_post_preview(callback.message, post)
    except ImportError:
        # Fallback превью
        text = post.get("text", "Пост без текста")[:500]
        await callback.message.answer(f"👀 **Предпросмотр поста #{post_id}**\n\n{text}")
    
    # Информация и кнопки
    info_text = f"👀 **Предпросмотр поста #{post_id}**\n\n"
    
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    if channel:
        info_text += f"📺 **Канал:** {channel['name']}\n"
    
    if post.get("draft"):
        info_text += "📝 **Статус:** Черновик\n"
    elif post.get("publish_time"):
        info_text += f"⏰ **Статус:** Запланирован\n"
    
    parse_mode_value = post.get("parse_mode")
    if parse_mode_value:
        info_text += f"🎨 **Формат:** {parse_mode_value}\n"
    
    keyboard = get_preview_edit_keyboard(post_id)
    await callback.message.answer(info_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("edit_save:"))
async def handle_edit_save(callback: CallbackQuery, state: FSMContext):
    """Сохранение всех изменений"""
    post_id = int(callback.data.split(":")[1])
    
    # Очищаем состояние
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать снова", callback_data=f"post_edit_direct:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"✅ **Изменения сохранены**\n\n"
        f"Пост #{post_id} успешно обновлен!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer("Изменения сохранены!")

@router.callback_query(F.data.startswith("edit_menu:"))
async def handle_edit_menu_return(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню редактирования"""
    post_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    # Получаем актуальную версию поста
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("❌ Пост не найден!")
        return
    
    # Очищаем состояние редактирования
    await state.clear()
    
    # Показываем главное меню
    await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
    await callback.answer()

@router.callback_query(F.data.startswith("edit_cancel:"))
async def handle_edit_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена редактирования"""
    post_id = int(callback.data.split(":")[1])
    
    # Очищаем состояние
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"❌ **Редактирование отменено**\n\n"
        f"Изменения в посте #{post_id} не сохранены.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer("Редактирование отменено")

@router.callback_query(F.data.startswith("edit_skip:"))
async def handle_edit_skip(callback: CallbackQuery, state: FSMContext):
    """Пропуск редактирования поля"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    field = parts[2]
    
    await finish_field_edit_callback(callback, state, post_id, field, None)

@router.callback_query(F.data.startswith("edit_recreate:"))
async def handle_edit_recreate(callback: CallbackQuery, state: FSMContext):
    """Пересоздание поста с нуля"""
    post_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer("❌ Пост не найден или нет доступа!")
        return
    
    if post.get("published"):
        await callback.answer("❌ Нельзя пересоздать опубликованный пост!")
        return
    
    # Показываем подтверждение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, пересоздать", callback_data=f"edit_recreate_confirm:{post_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"edit_menu:{post_id}")
        ]
    ])
    
    await callback.message.edit_text(
        f"🔄 **Пересоздание поста #{post_id}**\n\n"
        f"Вы действительно хотите пересоздать пост с нуля?\n"
        f"Это запустит полный процесс создания поста заново.\n\n"
        f"⚠️ Текущие данные поста будут потеряны!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_recreate_confirm:"))
async def handle_edit_recreate_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение пересоздания поста"""
    post_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    # Удаляем старый пост
    supabase_db.db.delete_post(post_id)
    
    # Очищаем состояние
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Создать новый пост", callback_data="menu_create_post_direct")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"🔄 **Пост #{post_id} удален**\n\n"
        f"Старый пост удален. Теперь вы можете создать новый пост с нуля.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer("Пост удален, создайте новый")

# Вспомогательные функции
async def finish_field_edit(message: Message, state: FSMContext, post_id: int, field: str, value):
    """Завершить редактирование поля (для сообщений)"""
    if value is not None:
        # Обновляем пост в базе данных
        updates = {}
        
        if field == "text":
            updates["text"] = value
        elif field == "media":
            if isinstance(value, dict):
                updates.update(value)
        elif field == "format":
            updates["parse_mode"] = value
        elif field == "buttons":
            updates["buttons"] = value
        elif field == "time":
            if isinstance(value, dict):
                updates.update(value)
                # Сбрасываем флаг уведомления если изменилось время
                if "publish_time" in updates:
                    updates["notified"] = False
        elif field == "channel":
            if isinstance(value, dict):
                updates.update(value)
        
        if updates:
            supabase_db.db.update_post(post_id, updates)
    
    # Очищаем состояние
    await state.clear()
    
    # Получаем обновленный пост
    post = supabase_db.db.get_post(post_id)
    user = supabase_db.db.get_user(message.from_user.id)
    
    # Возвращаемся в главное меню редактирования
    await show_edit_main_menu(message, post_id, post, user, user.get("language", "ru"))

async def finish_field_edit_callback(callback: CallbackQuery, state: FSMContext, post_id: int, field: str, value):
    """Завершить редактирование поля (для callback)"""
    if value is not None:
        # Обновляем пост в базе данных
        updates = {}
        
        if field == "text":
            updates["text"] = value
        elif field == "media":
            if isinstance(value, dict):
                updates.update(value)
        elif field == "format":
            updates["parse_mode"] = value
        elif field == "buttons":
            updates["buttons"] = value
        elif field == "time":
            if isinstance(value, dict):
                updates.update(value)
                # Сбрасываем флаг уведомления если изменилось время
                if "publish_time" in updates:
                    updates["notified"] = False
        elif field == "channel":
            if isinstance(value, dict):
                updates.update(value)
        
        if updates:
            supabase_db.db.update_post(post_id, updates)
    
    # Очищаем состояние
    await state.clear()
    
    # Получаем обновленный пост
    post = supabase_db.db.get_post(post_id)
    user = supabase_db.db.get_user(callback.from_user.id)
    
    # Возвращаемся в главное меню редактирования
    await show_edit_main_menu(callback.message, post_id, post, user, user.get("language", "ru"))
    await callback.answer()

async def cancel_edit(message: Message, state: FSMContext, post_id: int):
    """Отменить редактирование (для сообщений)"""
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await message.answer(
        f"❌ **Редактирование отменено**\n\n"
        f"Изменения в посте #{post_id} не сохранены.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# Глобальные обработчики для совместимости с main.py
async def handle_edit_field_callback(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик редактирования полей (для main.py)"""
    await handle_single_field_edit(callback, state)

async def handle_edit_confirm_callback(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик подтверждения (для main.py)"""
    await handle_edit_save(callback, state)

# Экспортируемые функции для других модулей
__all__ = [
    'show_edit_main_menu',
    'handle_edit_field_callback', 
    'handle_edit_confirm_callback',
    'handle_edit_menu_return',
    'handle_edit_skip',
    'handle_edit_save',
    'handle_edit_cancel',
    'handle_edit_recreate'
]
