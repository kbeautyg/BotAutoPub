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

# Текстовые команды для ИИ-агента (такие же как в create.py)
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

def get_edit_navigation_keyboard(current_step: str, lang: str = "ru", can_skip: bool = True):
    """Создать клавиатуру навигации для редактирования"""
    buttons = []
    
    # Кнопки навигации
    nav_row = []
    if can_skip:
        nav_row.append(InlineKeyboardButton(text="⏭️ Пропустить", callback_data="edit_nav_skip"))
    
    if nav_row:
        buttons.append(nav_row)
    
    # Кнопка отмены
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="edit_nav_cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_format_keyboard(lang: str = "ru"):
    """Клавиатуру выбора формата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 HTML", callback_data="edit_format_html")],
        [InlineKeyboardButton(text="📋 Markdown", callback_data="edit_format_markdown")],
        [InlineKeyboardButton(text="📄 Без форматирования", callback_data="edit_format_none")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="edit_nav_skip")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_nav_cancel")]
    ])

def get_time_options_keyboard(lang: str = "ru"):
    """Клавиатуру опций времени публикации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data="edit_time_now")],
        [InlineKeyboardButton(text="📝 Сохранить как черновик", callback_data="edit_time_draft")],
        [InlineKeyboardButton(text="⏰ Запланировать время", callback_data="edit_time_schedule")],
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="edit_nav_skip")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_nav_cancel")]
    ])

def get_channels_keyboard(channels: list, lang: str = "ru"):
    """Клавиатуру выбора канала"""
    buttons = []
    
    for i, channel in enumerate(channels):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text = f"{admin_status} {channel['name']}"
        buttons.append([InlineKeyboardButton(
            text=text, 
            callback_data=f"edit_channel_select:{channel['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="⏭️ Пропустить", callback_data="edit_nav_skip")])
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="edit_nav_cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_preview_keyboard(lang: str = "ru"):
    """Клавиатуру предварительного просмотра"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить изменения", callback_data="edit_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="edit_nav_cancel")]
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
    """Команда редактирования поста с современным интерфейсом"""
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
    
    # Инициализируем данные для редактирования
    await state.set_data({
        "post_id": post_id,
        "original_post": post,
        "user_settings": user,
        "current_step": "text",
        "changes": {}
    })
    
    await start_edit_text_step(message, state, lang)

async def start_edit_text_step(message: Message, state: FSMContext, lang: str):
    """Шаг 1: Редактирование текста"""
    await state.set_state(EditPost.text)
    
    data = await state.get_data()
    original_post = data["original_post"]
    current_text = original_post.get("text") or "Пост без текста"
    
    text = (
        f"📝 **Редактирование поста #{original_post['id']} - Шаг 1/6**\n\n"
        f"**Текущий текст:**\n"
        f"{current_text[:300]}{'...' if len(current_text) > 300 else ''}\n\n"
        f"**Отправьте новый текст или используйте команды:**\n"
        f"• `skip` - оставить текущий текст\n"
        f"• `cancel` - отменить редактирование\n\n"
        f"💡 *Вы можете использовать любое форматирование*"
    )
    
    keyboard = get_edit_navigation_keyboard("text", lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.text, F.text)
async def handle_edit_text_input(message: Message, state: FSMContext):
    """Обработка ввода нового текста"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем команды
    if is_command(message.text, "skip"):
        data = await state.get_data()
        await state.set_data(data)
        await start_edit_media_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Редактирование отменено")
        return
    
    # Сохраняем новый текст
    data = await state.get_data()
    data["changes"]["text"] = message.text
    await state.set_data(data)
    
    await start_edit_media_step(message, state, lang)

async def start_edit_media_step(message: Message, state: FSMContext, lang: str):
    """Шаг 2: Редактирование медиа"""
    await state.set_state(EditPost.media)
    
    data = await state.get_data()
    original_post = data["original_post"]
    
    media_info = "нет медиа"
    if original_post.get("media_id"):
        media_type = original_post.get("media_type", "медиа")
        if media_type == "photo":
            media_info = "📷 фото"
        elif media_type == "video":
            media_info = "🎬 видео"
        elif media_type == "animation":
            media_info = "🎞 GIF"
        else:
            media_info = f"📎 {media_type}"
    
    text = (
        f"🖼 **Редактирование медиа - Шаг 2/6**\n\n"
        f"**Текущее медиа:** {media_info}\n\n"
        f"**Отправьте новое медиа или используйте команды:**\n"
        f"• Отправьте фото/видео/GIF\n"
        f"• `skip` - оставить текущее медиа\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = get_edit_navigation_keyboard("media", lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.media, F.text | F.photo | F.video | F.animation)
async def handle_edit_media_input(message: Message, state: FSMContext):
    """Обработка медиа или команд"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем текстовые команды
    if message.text and is_command(message.text, "skip"):
        data = await state.get_data()
        await state.set_data(data)
        await start_edit_format_step(message, state, lang)
        return
    
    if message.text and is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Редактирование отменено")
        return
    
    # Обработка медиа
    data = await state.get_data()
    media_handled = False
    
    if message.photo:
        data["changes"]["media_type"] = "photo"
        data["changes"]["media_id"] = message.photo[-1].file_id
        media_handled = True
    elif message.video:
        data["changes"]["media_type"] = "video"
        data["changes"]["media_id"] = message.video.file_id
        media_handled = True
    elif message.animation:
        data["changes"]["media_type"] = "animation"
        data["changes"]["media_id"] = message.animation.file_id
        media_handled = True
    
    if media_handled:
        await state.set_data(data)
        await start_edit_format_step(message, state, lang)
    else:
        if message.text:
            await message.answer(
                "❌ **Неизвестная команда**\n\n"
                "Доступные команды:\n"
                "• `skip` - пропустить\n"
                "• `cancel` - отмена\n\n"
                "Или отправьте медиа файл",
                parse_mode="Markdown"
            )

async def start_edit_format_step(message: Message, state: FSMContext, lang: str):
    """Шаг 3: Редактирование формата"""
    await state.set_state(EditPost.format)
    
    data = await state.get_data()
    original_post = data["original_post"]
    current_format = original_post.get("parse_mode") or original_post.get("format") or "HTML"
    
    text = (
        f"🎨 **Редактирование формата - Шаг 3/6**\n\n"
        f"**Текущий формат:** {current_format}\n\n"
        f"**Выберите новый формат:**\n"
        f"• **HTML** - <b>жирный</b>, <i>курсив</i>, <a href='#'>ссылки</a>\n"
        f"• **Markdown** - **жирный**, *курсив*, [ссылки](url)\n"
        f"• **Обычный** - без форматирования\n\n"
        f"Текстовые команды:\n"
        f"• `html` - HTML формат\n"
        f"• `markdown` - Markdown формат\n"
        f"• `none` - без форматирования\n"
        f"• `skip` - оставить текущий формат\n"
        f"• `cancel` - отменить"
    )
    
    keyboard = get_format_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.format, F.text)
async def handle_edit_format_text_input(message: Message, state: FSMContext):
    """Обработка текстового выбора формата"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    text_lower = message.text.lower().strip()
    
    # Проверяем команды
    if is_command(message.text, "skip"):
        data = await state.get_data()
        await state.set_data(data)
        await start_edit_buttons_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Редактирование отменено")
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
        data["changes"]["parse_mode"] = format_map[text_lower]
        await state.set_data(data)
        await start_edit_buttons_step(message, state, lang)
    else:
        await message.answer(
            "❌ **Неизвестный формат**\n\n"
            "Доступные команды:\n"
            "• `html` - HTML форматирование\n"
            "• `markdown` - Markdown форматирование\n"
            "• `none` - без форматирования\n"
            "• `skip` - пропустить\n"
            "• `cancel` - отменить",
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("edit_format_"))
async def handle_edit_format_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора формата через кнопки"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    format_map = {
        "edit_format_html": "HTML",
        "edit_format_markdown": "Markdown",
        "edit_format_none": None
    }
    
    data = await state.get_data()
    data["changes"]["parse_mode"] = format_map.get(callback.data, "HTML")
    await state.set_data(data)
    
    await callback.answer()
    await start_edit_buttons_step(callback.message, state, lang)

async def start_edit_buttons_step(message: Message, state: FSMContext, lang: str):
    """Шаг 4: Редактирование кнопок"""
    await state.set_state(EditPost.buttons)
    
    data = await state.get_data()
    original_post = data["original_post"]
    
    # Получаем текущие кнопки
    current_buttons = original_post.get("buttons", [])
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
        f"🔘 **Редактирование кнопок - Шаг 4/6**\n\n"
        f"**Текущие кнопки:**\n{buttons_text}\n\n"
        f"**Отправьте новые кнопки:**\n"
        f"Формат: `Текст кнопки | https://example.com`\n"
        f"Каждая кнопка на новой строке\n\n"
        f"Пример:\n"
        f"```\n"
        f"Наш сайт | https://example.com\n"
        f"Telegram | https://t.me/channel\n"
        f"```\n\n"
        f"Текстовые команды:\n"
        f"• `skip` - оставить текущие кнопки\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = get_edit_navigation_keyboard("buttons", lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.buttons, F.text)
async def handle_edit_buttons_input(message: Message, state: FSMContext):
    """Обработка ввода кнопок"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем команды
    if is_command(message.text, "skip"):
        data = await state.get_data()
        await state.set_data(data)
        await start_edit_time_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Редактирование отменено")
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
        
        data = await state.get_data()
        data["changes"]["buttons"] = buttons
        await state.set_data(data)
        
        await start_edit_time_step(message, state, lang)
        
    except Exception as e:
        await message.answer(
            "❌ **Ошибка в формате кнопок**\n\n"
            f"Ошибка: {str(e)}\n\n"
            "Используйте формат: `Текст | URL`",
            parse_mode="Markdown"
        )

async def start_edit_time_step(message: Message, state: FSMContext, lang: str):
    """Шаг 5: Редактирование времени публикации"""
    await state.set_state(EditPost.time)
    
    data = await state.get_data()
    original_post = data["original_post"]
    user_settings = data["user_settings"]
    
    # Форматируем текущее время
    current_time_str = "черновик"
    if original_post.get("publish_time"):
        try:
            pub_time_str = original_post["publish_time"]
            if isinstance(pub_time_str, str):
                if pub_time_str.endswith('Z'):
                    pub_time_str = pub_time_str[:-1] + '+00:00'
                pub_dt = datetime.fromisoformat(pub_time_str)
            else:
                pub_dt = pub_time_str
            
            # Конвертируем в часовой пояс пользователя
            tz_name = user_settings.get("timezone", "UTC")
            try:
                tz = ZoneInfo(tz_name)
                local_dt = pub_dt.astimezone(tz)
                current_time_str = local_dt.strftime('%Y-%m-%d %H:%M')
            except:
                current_time_str = pub_dt.strftime('%Y-%m-%d %H:%M UTC')
        except:
            current_time_str = "ошибка формата"
    elif original_post.get("draft"):
        current_time_str = "черновик"
    
    timezone = user_settings.get("timezone", "UTC")
    
    text = (
        f"⏰ **Редактирование времени - Шаг 5/6**\n\n"
        f"**Текущее время:** {current_time_str}\n"
        f"**Ваш часовой пояс:** {timezone}\n\n"
        f"**Выберите новое время публикации:**\n\n"
        f"Текстовые команды:\n"
        f"• `now` - опубликовать сейчас\n"
        f"• `draft` - сохранить как черновик\n"
        f"• Дата и время: `2024-12-25 15:30`\n"
        f"• `skip` - оставить текущее время\n"
        f"• `cancel` - отменить редактирование"
    )
    
    keyboard = get_time_options_keyboard(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.time, F.text)
async def handle_edit_time_text_input(message: Message, state: FSMContext):
    """Обработка текстового ввода времени"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    text_lower = message.text.lower().strip()
    
    # Проверяем команды
    if is_command(message.text, "skip"):
        data = await state.get_data()
        await state.set_data(data)
        await start_edit_channel_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Редактирование отменено")
        return
    
    data = await state.get_data()
    
    # Обработка времени
    if is_command(message.text, "now"):
        data["changes"]["publish_time"] = datetime.now(ZoneInfo("UTC"))
        data["changes"]["draft"] = False
    elif is_command(message.text, "draft"):
        data["changes"]["publish_time"] = None
        data["changes"]["draft"] = True
    else:
        # Пробуем распарсить дату
        try:
            new_time = parse_time_improved(user, message.text)
            
            # Проверяем, что время в будущем
            if new_time <= datetime.now(ZoneInfo("UTC")):
                await message.answer("❌ Время должно быть в будущем!")
                return
            
            data["changes"]["publish_time"] = new_time
            data["changes"]["draft"] = False
            
        except ValueError as e:
            await message.answer(
                f"❌ **Неверный формат времени**\n\n"
                f"Ошибка: {str(e)}\n\n"
                f"Доступные команды:\n"
                f"• `now` - опубликовать сейчас\n"
                f"• `draft` - сохранить черновик\n"
                f"• Дата и время: `2024-12-25 15:30`\n"
                f"• `skip` - пропустить\n"
                f"• `cancel` - отменить",
                parse_mode="Markdown"
            )
            return
    
    await state.set_data(data)
    await start_edit_channel_step(message, state, lang)

@router.callback_query(F.data == "edit_time_now")
async def handle_edit_time_now(callback: CallbackQuery, state: FSMContext):
    """Опубликовать сейчас"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["changes"]["publish_time"] = datetime.now(ZoneInfo("UTC"))
    data["changes"]["draft"] = False
    await state.set_data(data)
    
    await callback.answer()
    await start_edit_channel_step(callback.message, state, lang)

@router.callback_query(F.data == "edit_time_draft")
async def handle_edit_time_draft(callback: CallbackQuery, state: FSMContext):
    """Сохранить как черновик"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    data["changes"]["publish_time"] = None
    data["changes"]["draft"] = True
    await state.set_data(data)
    
    await callback.answer()
    await start_edit_channel_step(callback.message, state, lang)

@router.callback_query(F.data == "edit_time_schedule")
async def handle_edit_time_schedule(callback: CallbackQuery, state: FSMContext):
    """Запланировать время"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Меняем состояние для ожидания ввода времени
    await state.set_state(EditPost.time)
    
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
        f"• `skip` - пропустить\n"
        f"• `cancel` - отменить"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

async def start_edit_channel_step(message: Message, state: FSMContext, lang: str):
    """Шаг 6: Редактирование канала"""
    await state.set_state(EditPost.channel)
    
    data = await state.get_data()
    original_post = data["original_post"]
    user_settings = data["user_settings"]
    
    # Получаем текущий канал
    current_channel_name = "неизвестный канал"
    current_channel = supabase_db.db.get_channel(original_post.get("channel_id"))
    if current_channel:
        current_channel_name = current_channel["name"]
    
    # Получаем список доступных каналов
    project_id = user_settings.get("current_project")
    channels = supabase_db.db.list_channels(project_id=project_id)
    
    if not channels:
        await message.answer("❌ Нет доступных каналов для переноса")
        await start_edit_preview_step(message, state, lang)
        return
    
    text = (
        f"📺 **Редактирование канала - Шаг 6/6**\n\n"
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
    
    keyboard = get_channels_keyboard(channels, lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.channel, F.text)
async def handle_edit_channel_text_input(message: Message, state: FSMContext):
    """Обработка текстового выбора канала"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверяем команды
    if is_command(message.text, "skip"):
        data = await state.get_data()
        await state.set_data(data)
        await start_edit_preview_step(message, state, lang)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Редактирование отменено")
        return
    
    data = await state.get_data()
    user_settings = data["user_settings"]
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
    
    data["changes"]["channel_id"] = channel['id']
    data["changes"]["chat_id"] = channel.get('chat_id')
    await state.set_data(data)
    
    await start_edit_preview_step(message, state, lang)

@router.callback_query(F.data.startswith("edit_channel_select:"))
async def handle_edit_channel_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора канала через кнопку"""
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    channel_id = int(callback.data.split(":", 1)[1])
    channel = supabase_db.db.get_channel(channel_id)
    
    data = await state.get_data()
    data["changes"]["channel_id"] = channel_id
    if channel:
        data["changes"]["chat_id"] = channel.get('chat_id')
    await state.set_data(data)
    
    await callback.answer()
    await start_edit_preview_step(callback.message, state, lang)

async def start_edit_preview_step(message: Message, state: FSMContext, lang: str):
    """Шаг 7: Предварительный просмотр изменений"""
    await state.set_state(EditPost.confirm)
    
    data = await state.get_data()
    original_post = data["original_post"]
    changes = data["changes"]
    
    # Подготавливаем данные для превью (комбинируем оригинал + изменения)
    preview_data = original_post.copy()
    preview_data.update(changes)
    
    # Сначала отправляем превью поста
    await send_edit_post_preview(message, preview_data)
    
    # Затем отправляем информацию об изменениях
    info_text = f"👀 **Предварительный просмотр изменений - Пост #{original_post['id']}**\n\n"
    
    # Показываем что изменилось
    changes_list = []
    
    if "text" in changes:
        changes_list.append("📝 Текст")
    if "media_id" in changes:
        changes_list.append("🖼 Медиа")
    if "parse_mode" in changes:
        changes_list.append("🎨 Формат")
    if "buttons" in changes:
        changes_list.append("🔘 Кнопки")
    if "publish_time" in changes or "draft" in changes:
        changes_list.append("⏰ Время публикации")
    if "channel_id" in changes:
        changes_list.append("📺 Канал")
    
    if changes_list:
        info_text += f"**Изменения:** {', '.join(changes_list)}\n\n"
    else:
        info_text += "**Изменения:** нет изменений\n\n"
    
    # Показываем информацию о канале
    channel_id = preview_data.get("channel_id")
    if channel_id:
        channel = supabase_db.db.get_channel(channel_id)
        if channel:
            info_text += f"**Канал:** {channel['name']}\n"
    
    # Показываем время публикации
    if preview_data.get("draft"):
        info_text += "**Статус:** Черновик\n"
    elif preview_data.get("publish_time"):
        user_settings = data["user_settings"]
        try:
            pub_time = preview_data["publish_time"]
            if isinstance(pub_time, datetime):
                tz_name = user_settings.get("timezone", "UTC")
                try:
                    tz = ZoneInfo(tz_name)
                    local_time = pub_time.astimezone(tz)
                    time_str = local_time.strftime('%Y-%m-%d %H:%M')
                    info_text += f"**Время публикации:** {time_str} ({tz_name})\n"
                except:
                    time_str = pub_time.strftime('%Y-%m-%d %H:%M UTC')
                    info_text += f"**Время публикации:** {time_str}\n"
            else:
                info_text += f"**Время публикации:** {pub_time}\n"
        except:
            info_text += "**Время публикации:** текущее из поста\n"
    
    if preview_data.get("parse_mode"):
        info_text += f"**Формат:** {preview_data['parse_mode']}\n"
    
    info_text += (
        f"\n**Текстовые команды:**\n"
        f"• `confirm` или `подтвердить` - сохранить изменения\n"
        f"• `cancel` или `отмена` - отменить редактирование\n\n"
        f"✅ Всё верно? Подтвердите сохранение изменений."
    )
    
    keyboard = get_preview_keyboard(lang)
    await message.answer(info_text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(EditPost.confirm, F.text)
async def handle_edit_preview_text_input(message: Message, state: FSMContext):
    """Обработка текстовых команд в предпросмотре"""
    user = supabase_db.db.get_user(message.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    if is_command(message.text, "confirm"):
        await handle_edit_confirmation_text(message, state)
        return
    
    if is_command(message.text, "cancel"):
        await state.clear()
        await message.answer("❌ Редактирование отменено")
        return
    
    await message.answer(
        "❌ **Неизвестная команда**\n\n"
        "Доступные команды:\n"
        "• `confirm` - подтвердить изменения\n"
        "• `cancel` - отменить",
        parse_mode="Markdown"
    )

async def send_edit_post_preview(message: Message, preview_data: dict):
    """Отправить превью отредактированного поста"""
    text = preview_data.get("text", "")
    media_id = preview_data.get("media_id")
    media_type = preview_data.get("media_type")
    parse_mode = preview_data.get("parse_mode")
    buttons = preview_data.get("buttons")
    
    # Подготовка кнопок
    markup = None
    if buttons:
        kb = []
        if isinstance(buttons, str):
            try:
                buttons = json.loads(buttons)
            except:
                buttons = []
        
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

@router.callback_query(F.data == "edit_confirm")
async def handle_edit_confirmation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение сохранения изменений через кнопку"""
    await handle_edit_confirmation_text(callback.message, state, is_callback=True)
    await callback.answer()

async def handle_edit_confirmation_text(message: Message, state: FSMContext, is_callback: bool = False):
    """Подтверждение сохранения изменений"""
    try:
        data = await state.get_data()
        post_id = data["post_id"]
        changes = data["changes"]
        user = data["user_settings"]
        lang = user.get("language", "ru") if user else "ru"
        
        # Проверяем, что пост еще не опубликован
        latest_post = supabase_db.db.get_post(post_id)
        if not latest_post:
            error_text = "❌ Пост не найден"
            if is_callback:
                await message.edit_text(error_text, parse_mode="Markdown")
            else:
                await message.answer(error_text, parse_mode="Markdown")
            await state.clear()
            return
        
        if latest_post.get("published"):
            error_text = "❌ Нельзя редактировать опубликованный пост"
            if is_callback:
                await message.edit_text(error_text, parse_mode="Markdown")
            else:
                await message.answer(error_text, parse_mode="Markdown")
            await state.clear()
            return
        
        # Подготавливаем обновления
        updates = {}
        
        # Преобразуем изменения в нужный формат
        for key, value in changes.items():
            if key == "publish_time" and isinstance(value, datetime):
                updates[key] = value.isoformat()
            elif key == "buttons" and isinstance(value, list):
                updates[key] = json.dumps(value) if value else None
            else:
                updates[key] = value
        
        # Сбрасываем флаг уведомления если изменилось время
        if "publish_time" in updates:
            updates["notified"] = False
        
        print(f"Обновление поста {post_id}: {updates}")  # Для отладки
        
        # Применяем изменения
        if updates:
            supabase_db.db.update_post(post_id, updates)
        
        # Формируем ответ
        changes_count = len(changes)
        if changes_count == 0:
            response_text = f"ℹ️ **Изменения не обнаружены**\n\nПост #{post_id} остался без изменений."
        else:
            response_text = (
                f"✅ **Изменения сохранены**\n\n"
                f"Пост #{post_id} успешно обновлен!\n"
                f"Применено изменений: {changes_count}\n\n"
                f"**Команды для управления:**\n"
                f"• `/view {post_id}` - просмотр\n"
                f"• `/edit {post_id}` - редактировать снова\n"
                f"• `/delete {post_id}` - удалить\n"
                f"• `/list` - список всех постов"
            )
        
        # Создаем клавиатуру с действиями
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👀 Просмотр", callback_data=f"post_full_view:{post_id}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_cmd:{post_id}")
            ],
            [
                InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ])
        
        if is_callback:
            await message.edit_text(response_text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await message.answer(response_text, parse_mode="Markdown", reply_markup=keyboard)
        
        await state.clear()
        
    except Exception as e:
        print(f"Ошибка при сохранении изменений: {e}")
        
        error_text = (
            f"❌ **Ошибка сохранения**\n\n"
            f"Не удалось сохранить изменения: {str(e)}\n\n"
            f"Попробуйте еще раз."
        )
        
        try:
            if is_callback:
                await message.edit_text(error_text, parse_mode="Markdown")
            else:
                await message.answer(error_text, parse_mode="Markdown")
        except:
            pass
        
        await state.clear()

# Обработчики навигации
@router.callback_query(F.data == "edit_nav_skip")
async def handle_edit_nav_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить текущий шаг редактирования"""
    current_state = await state.get_state()
    user = supabase_db.db.get_user(callback.from_user.id)
    lang = user.get("language", "ru") if user else "ru"
    
    data = await state.get_data()
    
    # Определяем следующий шаг
    if current_state == EditPost.text:
        await start_edit_media_step(callback.message, state, lang)
    elif current_state == EditPost.media:
        await start_edit_format_step(callback.message, state, lang)
    elif current_state == EditPost.format:
        await start_edit_buttons_step(callback.message, state, lang)
    elif current_state == EditPost.buttons:
        await start_edit_time_step(callback.message, state, lang)
    elif current_state == EditPost.time:
        await start_edit_channel_step(callback.message, state, lang)
    elif current_state == EditPost.channel:
        await start_edit_preview_step(callback.message, state, lang)
    
    await callback.answer()

@router.callback_query(F.data == "edit_nav_cancel")
async def handle_edit_nav_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменить редактирование поста"""
    await state.clear()
    await callback.message.edit_text(
        "❌ **Редактирование отменено**\n\n"
        "Все изменения отменены.",
        parse_mode="Markdown"
    )
    await callback.answer()
