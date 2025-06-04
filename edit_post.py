from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from zoneinfo import ZoneInfo
from states import PostCreationFlow
import supabase_db
from __init__ import TEXTS
import json

router = Router()

# Переиспользуем функции из create.py для единообразия
def get_edit_navigation_keyboard(can_skip: bool = True):
    """Клавиатура навигации при редактировании"""
    buttons = []
    
    nav_row = []
    if can_skip:
        nav_row.append(InlineKeyboardButton(text="⏭️ Оставить без изменений", callback_data="edit_skip"))
    nav_row.append(InlineKeyboardButton(text="❌ Отменить", callback_data="edit_cancel"))
    
    if nav_row:
        buttons.append(nav_row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_main_menu(post_id: int):
    """Главное меню редактирования поста"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить текст", callback_data=f"edit_field:{post_id}:text")],
        [InlineKeyboardButton(text="🖼 Изменить медиа", callback_data=f"edit_field:{post_id}:media")],
        [InlineKeyboardButton(text="🎨 Изменить формат", callback_data=f"edit_field:{post_id}:format")],
        [InlineKeyboardButton(text="🔘 Изменить кнопки", callback_data=f"edit_field:{post_id}:buttons")],
        [InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"edit_field:{post_id}:time")],
        [InlineKeyboardButton(text="📺 Изменить канал", callback_data=f"edit_field:{post_id}:channel")],
        [InlineKeyboardButton(text="🔄 Изменить повтор", callback_data=f"edit_field:{post_id}:repeat")],
        [InlineKeyboardButton(text="👀 Предпросмотр", callback_data=f"edit_preview:{post_id}")],
        [InlineKeyboardButton(text="✅ Сохранить изменения", callback_data=f"edit_save:{post_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"post_view:{post_id}")]
    ])

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    """Команда редактирования поста"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(TEXTS[lang]['edit_usage'])
        return
    
    try:
        post_id = int(args[1])
    except:
        await message.answer(TEXTS[lang]['edit_invalid_id'])
        return
    
    # Сразу показываем меню редактирования
    await show_edit_menu(message, post_id, user_id, lang)

async def show_edit_menu(message: Message, post_id: int, user_id: int, lang: str):
    """Показать красивое меню редактирования"""
    post = supabase_db.db.get_post(post_id)
    
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer(TEXTS[lang]['edit_post_not_found'])
        return
    
    if post.get("published"):
        await message.answer(TEXTS[lang]['edit_post_published'])
        return
    
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    channel_name = channel.get("name", "Неизвестный канал") if channel else "Канал не выбран"
    
    # Формируем текст с текущими параметрами
    text = f"✏️ **Редактирование поста #{post_id}**\n\n"
    text += f"📺 **Канал:** {channel_name}\n"
    
    # Текст
    post_text = post.get("text", "")
    if post_text:
        text += f"📝 **Текст:** {post_text[:50]}{'...' if len(post_text) > 50 else ''}\n"
    else:
        text += f"📝 **Текст:** _не задан_\n"
    
    # Медиа
    if post.get("media_id"):
        media_type = post.get("media_type", "медиа")
        text += f"🖼 **Медиа:** {TEXTS[lang].get(f'media_{media_type}', media_type)}\n"
    else:
        text += f"🖼 **Медиа:** _не добавлено_\n"
    
    # Формат
    format_type = post.get("parse_mode") or post.get("format") or "none"
    text += f"🎨 **Формат:** {format_type}\n"
    
    # Кнопки
    buttons = post.get("buttons")
    if buttons:
        try:
            if isinstance(buttons, str):
                buttons_list = json.loads(buttons)
            else:
                buttons_list = buttons
            text += f"🔘 **Кнопок:** {len(buttons_list)}\n"
        except:
            text += f"🔘 **Кнопки:** _ошибка_\n"
    else:
        text += f"🔘 **Кнопки:** _не добавлены_\n"
    
    # Время
    if post.get("publish_time"):
        try:
            from view_post import format_time_for_user
            time_str = format_time_for_user(post["publish_time"], user)
            text += f"⏰ **Время:** {time_str}\n"
        except:
            text += f"⏰ **Время:** {post['publish_time']}\n"
    elif post.get("draft"):
        text += f"⏰ **Статус:** Черновик\n"
    else:
        text += f"⏰ **Время:** _не задано_\n"
    
    # Повтор
    repeat = post.get("repeat_interval", 0)
    if repeat > 0:
        text += f"🔄 **Повтор:** каждые {format_interval(repeat)}\n"
    else:
        text += f"🔄 **Повтор:** _отключен_\n"
    
    text += "\n**Выберите, что хотите изменить:**"
    
    keyboard = get_edit_main_menu(post_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

def format_interval(seconds: int) -> str:
    """Форматировать интервал"""
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} дн."
    elif seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} ч."
    else:
        minutes = seconds // 60
        return f"{minutes} мин."

# Обработчик для кнопок редактирования
@router.callback_query(F.data.startswith("post_edit_cmd:"))
async def callback_edit_post(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки редактирования - сразу открываем меню"""
    user_id = callback.from_user.id
    post_id = int(callback.data.split(":", 1)[1])
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await show_edit_menu(callback.message, post_id, user_id, lang)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_field:"))
async def callback_edit_field(callback: CallbackQuery, state: FSMContext):
    """Редактирование конкретного поля"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    field = parts[2]
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден")
        return
    
    # Сохраняем данные в состоянии
    await state.update_data(
        editing_post_id=post_id,
        editing_field=field,
        original_post=post,
        user_data=user
    )
    
    if field == "text":
        await state.set_state(PostCreationFlow.step_text)
        current_text = post.get("text", "")
        text = (
            f"📝 **Редактирование текста поста #{post_id}**\n\n"
            f"**Текущий текст:**\n{current_text[:500]}{'...' if len(current_text) > 500 else ''}\n\n"
            f"Отправьте новый текст или нажмите кнопку ниже, чтобы оставить текущий."
        )
        keyboard = get_edit_navigation_keyboard(can_skip=True)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    elif field == "media":
        await state.set_state(PostCreationFlow.step_media)
        text = f"🖼 **Редактирование медиа поста #{post_id}**\n\n"
        if post.get("media_id"):
            media_type = post.get("media_type", "медиа")
            text += f"**Текущее медиа:** {TEXTS[lang].get(f'media_{media_type}', media_type)}\n\n"
        else:
            text += "**Текущее медиа:** _не добавлено_\n\n"
        text += "Отправьте новое фото/видео/GIF или нажмите кнопку ниже."
        keyboard = get_edit_navigation_keyboard(can_skip=True)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    elif field == "format":
        text = f"🎨 **Редактирование формата поста #{post_id}**\n\n"
        current_format = post.get("parse_mode") or post.get("format") or "none"
        text += f"**Текущий формат:** {current_format}\n\n"
        text += "Выберите новый формат:"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 HTML", callback_data=f"edit_format:{post_id}:HTML")],
            [InlineKeyboardButton(text="📋 Markdown", callback_data=f"edit_format:{post_id}:Markdown")],
            [InlineKeyboardButton(text="📄 Без форматирования", callback_data=f"edit_format:{post_id}:none")],
            [InlineKeyboardButton(text="⏭️ Оставить текущий", callback_data=f"edit_skip_format:{post_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_menu:{post_id}")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    elif field == "buttons":
        await state.set_state(PostCreationFlow.step_buttons)
        text = f"🔘 **Редактирование кнопок поста #{post_id}**\n\n"
        
        buttons = post.get("buttons", [])
        if buttons:
            try:
                if isinstance(buttons, str):
                    buttons_list = json.loads(buttons)
                else:
                    buttons_list = buttons
                text += "**Текущие кнопки:**\n"
                for btn in buttons_list:
                    if isinstance(btn, dict):
                        text += f"• {btn.get('text', '')} | {btn.get('url', '')}\n"
                text += "\n"
            except:
                text += "**Текущие кнопки:** _ошибка чтения_\n\n"
        else:
            text += "**Текущие кнопки:** _не добавлены_\n\n"
        
        text += (
            "Отправьте новые кнопки в формате:\n"
            "```\n"
            "Текст кнопки | https://example.com\n"
            "Вторая кнопка | https://example2.com\n"
            "```"
        )
        keyboard = get_edit_navigation_keyboard(can_skip=True)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    elif field == "time":
        text = f"⏰ **Редактирование времени публикации поста #{post_id}**\n\n"
        
        if post.get("publish_time"):
            try:
                from view_post import format_time_for_user
                time_str = format_time_for_user(post["publish_time"], user)
                text += f"**Текущее время:** {time_str}\n\n"
            except:
                text += f"**Текущее время:** {post['publish_time']}\n\n"
        elif post.get("draft"):
            text += "**Текущий статус:** Черновик\n\n"
        
        text += "Выберите новое время или действие:"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"edit_time_now:{post_id}")],
            [InlineKeyboardButton(text="📝 Сохранить как черновик", callback_data=f"edit_time_draft:{post_id}")],
            [InlineKeyboardButton(text="⏰ Указать время", callback_data=f"edit_time_custom:{post_id}")],
            [InlineKeyboardButton(text="⏭️ Оставить текущее", callback_data=f"edit_skip_time:{post_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_menu:{post_id}")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    elif field == "channel":
        project_id = post.get("project_id")
        channels = supabase_db.db.list_channels(project_id=project_id)
        
        text = f"📺 **Редактирование канала поста #{post_id}**\n\n"
        
        current_channel_id = post.get("channel_id")
        current_channel = None
        for ch in channels:
            if ch["id"] == current_channel_id:
                current_channel = ch
                break
        
        if current_channel:
            text += f"**Текущий канал:** {current_channel['name']}\n\n"
        
        text += "Выберите новый канал:"
        
        buttons = []
        for channel in channels:
            if channel["id"] != current_channel_id:
                admin_status = "✅" if channel.get('is_admin_verified') else "❓"
                buttons.append([InlineKeyboardButton(
                    text=f"{admin_status} {channel['name']}", 
                    callback_data=f"edit_channel:{post_id}:{channel['id']}"
                )])
        
        buttons.append([InlineKeyboardButton(text="⏭️ Оставить текущий", callback_data=f"edit_skip_channel:{post_id}")])
        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_menu:{post_id}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    elif field == "repeat":
        text = f"🔄 **Редактирование повтора поста #{post_id}**\n\n"
        
        current_repeat = post.get("repeat_interval", 0)
        if current_repeat > 0:
            text += f"**Текущий интервал:** каждые {format_interval(current_repeat)}\n\n"
        else:
            text += "**Текущий интервал:** _повтор отключен_\n\n"
        
        text += "Выберите новый интервал:"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Каждый час", callback_data=f"edit_repeat:{post_id}:3600")],
            [InlineKeyboardButton(text="📅 Каждый день", callback_data=f"edit_repeat:{post_id}:86400")],
            [InlineKeyboardButton(text="📆 Каждую неделю", callback_data=f"edit_repeat:{post_id}:604800")],
            [InlineKeyboardButton(text="❌ Отключить повтор", callback_data=f"edit_repeat:{post_id}:0")],
            [InlineKeyboardButton(text="⚙️ Свой интервал", callback_data=f"edit_repeat_custom:{post_id}")],
            [InlineKeyboardButton(text="⏭️ Оставить текущий", callback_data=f"edit_skip_repeat:{post_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_menu:{post_id}")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    await callback.answer()

# Обработчики skip для всех полей
@router.callback_query(F.data == "edit_skip")
async def callback_edit_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить редактирование текущего поля"""
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    
    if not post_id:
        await callback.answer("Ошибка: не найден ID поста")
        return
    
    # Возвращаемся в меню редактирования
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("edit_skip_"))
async def callback_edit_skip_specific(callback: CallbackQuery, state: FSMContext):
    """Пропустить редактирование конкретного поля"""
    post_id = int(callback.data.split(":")[-1])
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    await callback.answer()

@router.callback_query(F.data == "edit_cancel")
async def callback_edit_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменить редактирование"""
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    
    await state.clear()
    
    if post_id:
        # Возвращаемся к просмотру поста
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            f"❌ Редактирование поста #{post_id} отменено",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text("❌ Редактирование отменено")
    
    await callback.answer()

# Обработчики для времени
@router.callback_query(F.data.startswith("edit_time_now:"))
async def callback_edit_time_now(callback: CallbackQuery, state: FSMContext):
    """Установить время публикации на сейчас"""
    post_id = int(callback.data.split(":")[-1])
    
    await state.update_data(
        new_publish_time=datetime.now(ZoneInfo("UTC")),
        new_draft=False
    )
    
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    await callback.answer("Время изменено на: Опубликовать сейчас")

@router.callback_query(F.data.startswith("edit_time_draft:"))
async def callback_edit_time_draft(callback: CallbackQuery, state: FSMContext):
    """Сохранить как черновик"""
    post_id = int(callback.data.split(":")[-1])
    
    await state.update_data(
        new_publish_time=None,
        new_draft=True
    )
    
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    await callback.answer("Изменено на: Черновик")

@router.callback_query(F.data.startswith("edit_time_custom:"))
async def callback_edit_time_custom(callback: CallbackQuery, state: FSMContext):
    """Ввод произвольного времени"""
    post_id = int(callback.data.split(":")[-1])
    user = supabase_db.db.get_user(callback.from_user.id)
    
    await state.set_state(PostCreationFlow.step_time)
    await state.update_data(editing_custom_time=True)
    
    text = (
        f"📅 **Введите новое время публикации**\n\n"
        f"Часовой пояс: {user.get('timezone', 'UTC')}\n\n"
        f"Форматы:\n"
        f"• `2024-12-25 15:30`\n"
        f"• `25.12.2024 15:30`\n"
        f"• `25/12/2024 15:30`"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_menu:{post_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# Обработчики ввода текста при редактировании
@router.message(PostCreationFlow.step_text, F.text)
async def handle_edit_text_input(message: Message, state: FSMContext):
    """Обработка нового текста"""
    data = await state.get_data()
    
    if not data.get("editing_post_id"):
        return  # Это не редактирование
    
    post_id = data["editing_post_id"]
    
    # Сохраняем новый текст
    await state.update_data(new_text=message.text)
    
    # Возвращаемся в меню
    user_id = message.from_user.id
    await show_edit_menu(message, post_id, user_id, "ru")
    await state.clear()

@router.message(EditPost.time, Command("skip"))
async def skip_edit_time(message: Message, state: FSMContext):
    """Пропустить редактирование времени"""
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    # Оставляем текущее время без изменений
    await state.update_data(new_publish_time=orig_post.get("publish_time"))
    await ask_edit_repeat(message, state)

@router.message(PostCreationFlow.step_media, F.photo | F.video | F.animation)
async def handle_edit_media_input(message: Message, state: FSMContext):
    """Обработка нового медиа"""
    data = await state.get_data()
    
    if not data.get("editing_post_id"):
        return
    
    post_id = data["editing_post_id"]
    
    # Сохраняем новое медиа
    if message.photo:
        await state.update_data(
            new_media_type="photo",
            new_media_id=message.photo[-1].file_id
        )
    elif message.video:
        await state.update_data(
            new_media_type="video",
            new_media_id=message.video.file_id
        )
    elif message.animation:
        await state.update_data(
            new_media_type="animation",
            new_media_id=message.animation.file_id
        )
    
    # Возвращаемся в меню
    await show_edit_menu(message, post_id, message.from_user.id, "ru")
    await state.clear()

@router.message(PostCreationFlow.step_buttons, F.text)
async def handle_edit_buttons_input(message: Message, state: FSMContext):
    """Обработка новых кнопок"""
    data = await state.get_data()
    
    if not data.get("editing_post_id"):
        return
    
    post_id = data["editing_post_id"]
    
    # Парсим кнопки
    buttons = []
    lines = message.text.strip().split('\n')
    
    for line in lines:
        if '|' in line:
            parts = line.split('|', 1)
            text = parts[0].strip()
            url = parts[1].strip()
            if text and url:
                buttons.append({"text": text, "url": url})
    
    if buttons:
        await state.update_data(new_buttons=buttons)
        await show_edit_menu(message, post_id, message.from_user.id, "ru")
    else:
        await message.answer(
            "❌ **Неверный формат кнопок**\n\n"
            "Используйте формат:\n"
            "```\n"
            "Текст кнопки | https://example.com\n"
            "```",
            parse_mode="Markdown"
        )
    
    await state.clear()

@router.message(PostCreationFlow.step_time, F.text)
async def handle_edit_time_input(message: Message, state: FSMContext):
    """Обработка нового времени"""
    data = await state.get_data()
    
    if not data.get("editing_post_id") or not data.get("editing_custom_time"):
        return
    
    post_id = data["editing_post_id"]
    user = data.get("user_data", {})
    
    try:
        # Парсим время
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
        
        await state.update_data(new_publish_time=utc_dt)
        await show_edit_menu(message, post_id, message.from_user.id, "ru")
        
    except ValueError:
        await message.answer(
            "❌ **Неверный формат времени**\n\n"
            "Используйте один из форматов:\n"
            "• `2024-12-25 15:30`\n"
            "• `25.12.2024 15:30`\n"
            "• `25/12/2024 15:30`",
            parse_mode="Markdown"
        )
    
    await state.clear()

# Обработчики для других полей
@router.callback_query(F.data.startswith("edit_format:"))
async def callback_edit_format(callback: CallbackQuery, state: FSMContext):
    """Изменить формат"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    new_format = parts[2]
    
    await state.update_data(new_format=new_format)
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    await callback.answer(f"Формат изменен на: {new_format}")

@router.callback_query(F.data.startswith("edit_channel:"))
async def callback_edit_channel(callback: CallbackQuery, state: FSMContext):
    """Изменить канал"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    channel_id = int(parts[2])
    
    await state.update_data(new_channel_id=channel_id)
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    await callback.answer("Канал изменен")

@router.callback_query(F.data.startswith("edit_repeat:"))
async def callback_edit_repeat(callback: CallbackQuery, state: FSMContext):
    """Изменить интервал повтора"""
    parts = callback.data.split(":")
    post_id = int(parts[1])
    interval = int(parts[2])
    
    await state.update_data(new_repeat_interval=interval)
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    
    if interval > 0:
        await callback.answer(f"Интервал изменен на: каждые {format_interval(interval)}")
    else:
        await callback.answer("Повтор отключен")

@router.callback_query(F.data.startswith("edit_repeat_custom:"))
async def callback_edit_repeat_custom(callback: CallbackQuery, state: FSMContext):
    """Ввод произвольного интервала"""
    post_id = int(callback.data.split(":")[-1])
    
    await state.set_state(PostCreationFlow.step_repeat)
    
    text = (
        f"🔄 **Введите интервал повтора**\n\n"
        f"Форматы:\n"
        f"• `30m` - 30 минут\n"
        f"• `2h` - 2 часа\n"
        f"• `1d` - 1 день\n"
        f"• `7d` - 7 дней"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"edit_menu:{post_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.message(PostCreationFlow.step_repeat, F.text)
async def handle_edit_repeat_input(message: Message, state: FSMContext):
    """Обработка интервала повтора"""
    data = await state.get_data()
    
    if not data.get("editing_post_id"):
        return
    
    post_id = data["editing_post_id"]
    text = message.text.strip().lower()
    
    # Парсим интервал
    try:
        if text.endswith('m'):
            minutes = int(text[:-1])
            interval = minutes * 60
        elif text.endswith('h'):
            hours = int(text[:-1])
            interval = hours * 3600
        elif text.endswith('d'):
            days = int(text[:-1])
            interval = days * 86400
        else:
            raise ValueError()
        
        if interval > 0:
            await state.update_data(new_repeat_interval=interval)
            await show_edit_menu(message, post_id, message.from_user.id, "ru")
        else:
            raise ValueError()
        
    except ValueError:
        await message.answer(
            "❌ **Неверный формат интервала**\n\n"
            "Используйте:\n"
            "• `30m` - минуты\n"
            "• `2h` - часы\n"
            "• `1d` - дни",
            parse_mode="Markdown"
        )
    
    await state.clear()

# Предпросмотр изменений
@router.callback_query(F.data.startswith("edit_preview:"))
async def callback_edit_preview(callback: CallbackQuery, state: FSMContext):
    """Показать предпросмотр с изменениями"""
    post_id = int(callback.data.split(":")[-1])
    
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден")
        return
    
    # Получаем все изменения из состояния
    data = await state.get_data()
    
    # Применяем изменения к превью
    preview_data = post.copy()
    
    if "new_text" in data:
        preview_data["text"] = data["new_text"]
    if "new_media_id" in data:
        preview_data["media_id"] = data["new_media_id"]
        preview_data["media_type"] = data["new_media_type"]
    if "new_format" in data:
        preview_data["parse_mode"] = data["new_format"]
    if "new_buttons" in data:
        preview_data["buttons"] = data["new_buttons"]
    if "new_channel_id" in data:
        preview_data["channel_id"] = data["new_channel_id"]
    
    # Отправляем превью
    from view_post import send_post_preview
    channel = supabase_db.db.get_channel(preview_data.get("channel_id"))
    await send_post_preview(callback.message, preview_data, channel)
    
    # Показываем кнопки действий
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить изменения", callback_data=f"edit_save:{post_id}")],
        [InlineKeyboardButton(text="🔙 Вернуться к редактированию", callback_data=f"edit_menu:{post_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"post_view:{post_id}")]
    ])
    
    await callback.message.answer(
        "👀 **Предпросмотр изменений**\n\n"
        "Так будет выглядеть пост после сохранения изменений.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

# Сохранение изменений
@router.callback_query(F.data.startswith("edit_save:"))
async def callback_edit_save(callback: CallbackQuery, state: FSMContext):
    """Сохранить все изменения"""
    post_id = int(callback.data.split(":")[-1])
    
    # Получаем все изменения
    data = await state.get_data()
    
    updates = {}
    if "new_text" in data:
        updates["text"] = data["new_text"]
    if "new_media_id" in data:
        updates["media_id"] = data["new_media_id"]
        updates["media_type"] = data["new_media_type"]
    if "new_format" in data:
        updates["parse_mode"] = data["new_format"]
    if "new_buttons" in data:
        updates["buttons"] = data["new_buttons"]
    if "new_publish_time" in data:
        updates["publish_time"] = data["new_publish_time"]
    if "new_draft" in data:
        updates["draft"] = data["new_draft"]
    if "new_channel_id" in data:
        updates["channel_id"] = data["new_channel_id"]
    if "new_repeat_interval" in data:
        updates["repeat_interval"] = data["new_repeat_interval"]
    
    if updates:
        # Сохраняем изменения
        supabase_db.db.update_post(post_id, updates)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_view:{post_id}")],
            [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_menu:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            f"✅ **Изменения сохранены**\n\n"
            f"Пост #{post_id} успешно обновлен.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("❌ Нет изменений для сохранения")
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("edit_menu:"))
async def callback_return_to_edit_menu(callback: CallbackQuery, state: FSMContext):
    """Вернуться в меню редактирования"""
    post_id = int(callback.data.split(":")[-1])
    await state.clear()
    await show_edit_menu(callback.message, post_id, callback.from_user.id, "ru")
    await callback.answer()
