from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import supabase_db
from __init__ import TEXTS
from datetime import datetime
from zoneinfo import ZoneInfo
import json

router = Router()

def format_time_for_user(time_str: str, user: dict) -> str:
    """Форматировать время для отображения пользователю в его часовом поясе"""
    try:
        # Парсим время из ISO формата
        if isinstance(time_str, str):
            if time_str.endswith('Z'):
                time_str = time_str[:-1] + '+00:00'
            utc_time = datetime.fromisoformat(time_str)
        else:
            utc_time = time_str
        
        # Получаем часовой пояс пользователя
        user_tz_name = user.get('timezone', 'UTC')
        try:
            user_tz = ZoneInfo(user_tz_name)
            local_time = utc_time.astimezone(user_tz)
        except:
            local_time = utc_time
            user_tz_name = 'UTC'
        
        # Форматируем согласно настройкам пользователя
        date_format = user.get('date_format', 'YYYY-MM-DD')
        time_format = user.get('time_format', 'HH:MM')
        
        # Конвертируем формат в strftime
        if date_format == 'DD.MM.YYYY':
            date_str = local_time.strftime('%d.%m.%Y')
        elif date_format == 'DD/MM/YYYY':
            date_str = local_time.strftime('%d/%m/%Y')
        elif date_format == 'MM/DD/YYYY':
            date_str = local_time.strftime('%m/%d/%Y')
        else:  # YYYY-MM-DD
            date_str = local_time.strftime('%Y-%m-%d')
        
        if time_format == 'hh:MM AM':
            time_str = local_time.strftime('%I:%M %p')
        else:  # HH:MM
            time_str = local_time.strftime('%H:%M')
        
        return f"{date_str} {time_str}"
    except Exception as e:
        # Fallback на оригинальную строку
        return str(time_str)

def get_posts_main_menu(lang: str = "ru"):
    """Главное меню управления постами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Запланированные", callback_data="posts_scheduled")],
        [InlineKeyboardButton(text="📝 Черновики", callback_data="posts_drafts")],
        [InlineKeyboardButton(text="✅ Опубликованные", callback_data="posts_published")],
        [InlineKeyboardButton(text="📺 По каналам", callback_data="posts_by_channels")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

def get_channel_filter_keyboard(channels: list, lang: str = "ru"):
    """Клавиатура фильтрации по каналам"""
    buttons = []
    
    # Кнопка "Все каналы"
    buttons.append([InlineKeyboardButton(text="📺 Все каналы", callback_data="filter_all_channels")])
    
    # Кнопки для каждого канала
    for channel in channels:
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text = f"{admin_status} {channel['name']}"
        buttons.append([InlineKeyboardButton(
            text=text, 
            callback_data=f"filter_channel:{channel['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_post_actions_keyboard(post_id: int, is_published: bool = False, lang: str = "ru"):
    """Клавиатура действий с постом"""
    buttons = []
    
    # Кнопка просмотра всегда есть
    buttons.append([InlineKeyboardButton(text="👀 Полный просмотр", callback_data=f"post_full_view:{post_id}")])
    
    if not is_published:
        buttons.append([
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_cmd:{post_id}"),
            InlineKeyboardButton(text="🚀 Опубликовать", callback_data=f"post_publish_cmd:{post_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="📅 Перенести", callback_data=f"post_reschedule_cmd:{post_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post_delete_cmd:{post_id}")
        ])
    else:
        buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data=f"post_stats:{post_id}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 К списку", callback_data="posts_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_post_preview(post: dict, user: dict = None) -> str:
    """Форматировать предварительный просмотр поста"""
    text = f"📋 **Пост #{post['id']}**\n\n"
    
    # Статус поста
    if post.get('published'):
        text += "✅ **Статус:** Опубликован\n"
    elif post.get('draft'):
        text += "📝 **Статус:** Черновик\n"
    elif post.get('publish_time'):
        formatted_time = format_time_for_user(post['publish_time'], user or {})
        user_tz = user.get('timezone', 'UTC') if user else 'UTC'
        text += f"⏰ **Запланировано:** {formatted_time} ({user_tz})\n"
    else:
        text += "❓ **Статус:** Неопределен\n"
    
    # Канал
    if post.get('channels'):
        text += f"📺 **Канал:** {post['channels']['name']}\n"
    
    # Формат текста
    fmt = post.get('parse_mode') or post.get('format')
    if fmt:
        text += f"🎨 **Формат:** {fmt}\n"
    
    text += "\n" + "─" * 30 + "\n\n"
    
    # Текст поста
    if post.get('text'):
        preview_text = post['text']
        if len(preview_text) > 200:
            preview_text = preview_text[:200] + "..."
        text += preview_text
    else:
        text += "*[Пост без текста]*"
    
    # Медиа
    if post.get('media_type'):
        text += f"\n\n📎 **Медиа:** {post['media_type']}"
    
    # Кнопки
    if post.get('buttons'):
        try:
            buttons = json.loads(post['buttons']) if isinstance(post['buttons'], str) else post['buttons']
            text += f"\n🔘 **Кнопок:** {len(buttons)}"
        except:
            text += f"\n🔘 **Кнопки:** есть"
    
    return text

async def send_full_post_preview(callback: CallbackQuery, post: dict, user: dict):
    """Отправить полный превью поста как он будет выглядеть в канале"""
    text = post.get("text", "")
    media_id = post.get("media_id")
    media_type = post.get("media_type")
    parse_mode = post.get("parse_mode") or post.get("format")
    buttons = post.get("buttons")
    
    # Подготовка кнопок
    markup = None
    if buttons:
        try:
            if isinstance(buttons, str):
                buttons_list = json.loads(buttons)
            else:
                buttons_list = buttons
            
            if buttons_list:
                kb = []
                for btn in buttons_list:
                    if isinstance(btn, dict) and btn.get("text") and btn.get("url"):
                        kb.append([InlineKeyboardButton(text=btn["text"], url=btn["url"])])
                if kb:
                    markup = InlineKeyboardMarkup(inline_keyboard=kb)
        except:
            pass
    
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
                await callback.message.answer_photo(
                    media_id,
                    caption=text or None,
                    parse_mode=pm,
                    reply_markup=markup
                )
            elif media_type == "video":
                await callback.message.answer_video(
                    media_id,
                    caption=text or None,
                    parse_mode=pm,
                    reply_markup=markup
                )
            elif media_type == "animation":
                await callback.message.answer_animation(
                    media_id,
                    caption=text or None,
                    parse_mode=pm,
                    reply_markup=markup
                )
        else:
            await callback.message.answer(
                text or "📝 *[Пост без текста]*",
                parse_mode=pm or "Markdown",
                reply_markup=markup
            )
    except Exception as e:
        await callback.message.answer(
            f"⚠️ **Ошибка предпросмотра**\n\n"
            f"Не удалось показать превью: {str(e)}\n"
            f"Проверьте форматирование текста.",
            parse_mode="Markdown"
        )

@router.message(Command("list"))
async def cmd_list_posts(message: Message, state: FSMContext):
    """Показать список постов"""
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await show_posts_menu(message, user, lang)

async def show_posts_menu(message: Message, user: dict, lang: str):
    """Показать главное меню постов"""
    text = "📋 **Управление постами**\n\nВыберите категорию:"
    keyboard = get_posts_main_menu(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "posts_menu")
async def callback_posts_menu(callback: CallbackQuery):
    """Вернуться в главное меню постов"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = "📋 **Управление постами**\n\nВыберите категорию:"
    keyboard = get_posts_main_menu(lang)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "posts_scheduled")
async def callback_scheduled_posts(callback: CallbackQuery):
    """Показать запланированные посты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    project_id = user.get("current_project")
    
    if not project_id:
        text = "❌ Нет активного проекта."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    posts = supabase_db.db.get_scheduled_posts_by_channel(project_id)
    
    if not posts:
        text = "⏰ **Запланированные посты**\n\n❌ Нет запланированных постов."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать пост", callback_data="create_post")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        return
    
    # Группируем посты по каналам
    channels_posts = {}
    for post in posts:
        channel_name = post.get('channels', {}).get('name', 'Неизвестный канал')
        if channel_name not in channels_posts:
            channels_posts[channel_name] = []
        channels_posts[channel_name].append(post)
    
    text = "⏰ **Запланированные посты**\n\n"
    buttons = []
    
    for channel_name, channel_posts in channels_posts.items():
        text += f"📺 **{channel_name}** ({len(channel_posts)} постов)\n"
        for post in channel_posts[:3]:  # Показываем только первые 3
            try:
                formatted_time = format_time_for_user(post['publish_time'], user)
                time_str = formatted_time.split()[1] if ' ' in formatted_time else formatted_time[:5]  # Только время
                
                post_text = post.get('text', 'Без текста')[:30]
                text += f"  • {time_str} - {post_text}...\n"
                
                # Кнопка для каждого поста
                buttons.append([InlineKeyboardButton(
                    text=f"📋 Пост #{post['id']} ({time_str})",
                    callback_data=f"post_view:{post['id']}"
                )])
            except:
                text += f"  • Пост #{post['id']}\n"
                buttons.append([InlineKeyboardButton(
                    text=f"📋 Пост #{post['id']}",
                    callback_data=f"post_view:{post['id']}"
                )])
        
        if len(channel_posts) > 3:
            text += f"  ... и еще {len(channel_posts) - 3} постов\n"
        text += "\n"
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "posts_drafts")
async def callback_draft_posts(callback: CallbackQuery):
    """Показать черновики"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    project_id = user.get("current_project")
    
    if not project_id:
        text = "❌ Нет активного проекта."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    posts = supabase_db.db.get_draft_posts_by_channel(project_id)
    
    if not posts:
        text = "📝 **Черновики**\n\n❌ Нет сохраненных черновиков."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать пост", callback_data="create_post")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        return
    
    text = "📝 **Черновики**\n\n"
    buttons = []
    
    for i, post in enumerate(posts[:10], 1):  # Показываем первые 10
        channel_name = post.get('channels', {}).get('name', 'Неизвестный канал')
        post_text = post.get('text', 'Без текста')[:30]
        
        text += f"{i}. **{channel_name}**\n"
        text += f"   {post_text}...\n\n"
        
        buttons.append([InlineKeyboardButton(
            text=f"📝 Черновик #{post['id']}",
            callback_data=f"post_view:{post['id']}"
        )])
    
    if len(posts) > 10:
        text += f"... и еще {len(posts) - 10} черновиков"
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "posts_published")
async def callback_published_posts(callback: CallbackQuery):
    """Показать опубликованные посты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    project_id = user.get("current_project")
    
    if not project_id:
        text = "❌ Нет активного проекта."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    # Получаем опубликованные посты
    all_posts = supabase_db.db.list_posts(project_id=project_id, only_pending=False)
    published_posts = [p for p in all_posts if p.get('published')]
    
    if not published_posts:
        text = "✅ **Опубликованные посты**\n\n❌ Нет опубликованных постов."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать пост", callback_data="create_post")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        return
    
    text = "✅ **Опубликованные посты**\n\n"
    buttons = []
    
    # Сортируем по дате публикации (самые новые сначала)
    published_posts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    for i, post in enumerate(published_posts[:10], 1):  # Показываем первые 10
        # Получаем информацию о канале
        channel = supabase_db.db.get_channel(post.get('channel_id'))
        channel_name = channel['name'] if channel else 'Неизвестный канал'
        
        post_text = post.get('text', 'Без текста')[:30]
        
        text += f"{i}. **{channel_name}**\n"
        text += f"   {post_text}...\n\n"
        
        buttons.append([InlineKeyboardButton(
            text=f"✅ Пост #{post['id']}",
            callback_data=f"post_view:{post['id']}"
        )])
    
    if len(published_posts) > 10:
        text += f"... и еще {len(published_posts) - 10} опубликованных постов"
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "posts_by_channels")
async def callback_posts_by_channels(callback: CallbackQuery):
    """Показать посты по каналам"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    project_id = user.get("current_project")
    
    if not project_id:
        text = "❌ Нет активного проекта."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    
    if not channels:
        text = "❌ Нет доступных каналов."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="channels_add")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    text = "📺 **Посты по каналам**\n\nВыберите канал:"
    keyboard = get_channel_filter_keyboard(channels, lang)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("filter_channel:"))
async def callback_filter_by_channel(callback: CallbackQuery):
    """Фильтр постов по каналу"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    channel_id = int(callback.data.split(":", 1)[1])
    channel = supabase_db.db.get_channel(channel_id)
    
    if not channel:
        await callback.answer("Канал не найден!")
        return
    
    # Получаем все посты канала
    posts = supabase_db.db.list_posts_by_channel(channel_id, only_pending=False)
    
    if not posts:
        text = f"📺 **Канал: {channel['name']}**\n\n❌ Постов не найдено."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать пост", callback_data="create_post")],
            [InlineKeyboardButton(text="🔙 К каналам", callback_data="posts_by_channels")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        return
    
    # Группируем посты по статусу
    scheduled = [p for p in posts if not p.get('published') and not p.get('draft') and p.get('publish_time')]
    drafts = [p for p in posts if p.get('draft')]
    published = [p for p in posts if p.get('published')]
    
    text = f"📺 **Канал: {channel['name']}**\n\n"
    text += f"⏰ Запланированных: {len(scheduled)}\n"
    text += f"📝 Черновиков: {len(drafts)}\n"
    text += f"✅ Опубликованных: {len(published)}\n\n"
    
    buttons = []
    
    # Показываем последние посты
    recent_posts = sorted(posts, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
    
    if recent_posts:
        text += "**Последние посты:**\n"
        for post in recent_posts:
            status = "✅" if post.get('published') else "⏰" if post.get('publish_time') else "📝"
            post_text = post.get('text', 'Без текста')[:25]
            text += f"{status} {post_text}...\n"
            
            buttons.append([InlineKeyboardButton(
                text=f"{status} Пост #{post['id']}",
                callback_data=f"post_view:{post['id']}"
            )])
    
    buttons.append([InlineKeyboardButton(text="🔙 К каналам", callback_data="posts_by_channels")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("post_view:"))
async def callback_view_post(callback: CallbackQuery):
    """Просмотр конкретного поста"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    post_id = int(callback.data.split(":", 1)[1])
    post = supabase_db.db.get_post(post_id)
    
    if not post:
        await callback.message.edit_text("❌ Пост не найден.")
        await callback.answer()
        return
    
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(post['channel_id'])
    if channel:
        post['channels'] = channel
    
    text = format_post_preview(post, user)
    keyboard = get_post_actions_keyboard(post_id, post.get('published', False), lang)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("post_full_view:"))
async def callback_full_view_post(callback: CallbackQuery):
    """Полный просмотр поста (как он будет выглядеть в канале)"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    post_id = int(callback.data.split(":", 1)[1])
    post = supabase_db.db.get_post(post_id)
    
    if not post:
        await callback.answer("Пост не найден!")
        return
    
    # Отправляем полный превью поста
    await send_full_post_preview(callback, post, user)
    
    # Отправляем информацию с кнопками
    channel = supabase_db.db.get_channel(post['channel_id'])
    channel_name = channel['name'] if channel else 'Неизвестный канал'
    
    info_text = f"👀 **Полный просмотр поста #{post_id}**\n\n"
    info_text += f"📺 **Канал:** {channel_name}\n"
    
    if post.get('published'):
        info_text += "✅ **Статус:** Опубликован\n"
    elif post.get('draft'):
        info_text += "📝 **Статус:** Черновик\n"
    elif post.get('publish_time'):
        formatted_time = format_time_for_user(post['publish_time'], user)
        user_tz = user.get('timezone', 'UTC')
        info_text += f"⏰ **Запланировано:** {formatted_time} ({user_tz})\n"
    
    keyboard = get_post_actions_keyboard(post_id, post.get('published', False))
    
    await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

# Обработчики команд управления постами через кнопки
@router.callback_query(F.data.startswith("post_edit_cmd:"))
async def callback_edit_post_cmd(callback: CallbackQuery):
    """Команда редактирования поста через кнопку"""
    post_id = int(callback.data.split(":", 1)[1])
    await callback.message.answer(f"Используйте команду `/edit {post_id}` для редактирования поста.")
    await callback.answer()

@router.callback_query(F.data.startswith("post_publish_cmd:"))
async def callback_publish_post_cmd(callback: CallbackQuery):
    """Команда публикации поста через кнопку"""
    user_id = callback.from_user.id
    post_id = int(callback.data.split(":", 1)[1])
    
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден!")
        return
    
    if post.get('published'):
        await callback.answer("Пост уже опубликован!")
        return
    
    # Обновляем время публикации на текущее
    now = datetime.now(ZoneInfo("UTC"))
    supabase_db.db.update_post(post_id, {
        "publish_time": now,
        "draft": False
    })
    
    await callback.message.edit_text(
        f"🚀 **Пост #{post_id} поставлен в очередь на публикацию**\n\n"
        f"Пост будет опубликован в ближайшее время.",
        parse_mode="Markdown"
    )
    await callback.answer("Пост поставлен в очередь на публикацию!")

@router.callback_query(F.data.startswith("post_reschedule_cmd:"))
async def callback_reschedule_post_cmd(callback: CallbackQuery):
    """Команда переноса поста через кнопку"""
    post_id = int(callback.data.split(":", 1)[1])
    await callback.message.answer(f"Используйте команду `/reschedule {post_id} YYYY-MM-DD HH:MM` для переноса поста.")
    await callback.answer()

@router.callback_query(F.data.startswith("post_delete_cmd:"))
async def callback_delete_post_cmd(callback: CallbackQuery):
    """Команда удаления поста через кнопку"""
    post_id = int(callback.data.split(":", 1)[1])
    
    # Подтверждение удаления
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"post_delete_confirm:{post_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"post_view:{post_id}")
        ]
    ])
    
    await callback.message.edit_text(
        f"🗑 **Удаление поста #{post_id}**\n\n"
        f"Вы уверены, что хотите удалить этот пост?\n"
        f"Это действие нельзя отменить.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("post_delete_confirm:"))
async def callback_confirm_delete_post(callback: CallbackQuery):
    """Подтвердить удаление поста"""
    post_id = int(callback.data.split(":", 1)[1])
    
    try:
        supabase_db.db.delete_post(post_id)
        await callback.message.edit_text(
            f"✅ **Пост #{post_id} удален**\n\n"
            f"Пост успешно удален из базы данных.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ **Ошибка удаления**\n\n"
            f"Не удалось удалить пост: {str(e)}",
            parse_mode="Markdown"
        )
    
    await callback.answer()

@router.callback_query(F.data == "posts_back")
async def callback_posts_back(callback: CallbackQuery):
    """Вернуться к списку постов"""
    await callback_posts_menu(callback)

@router.callback_query(F.data == "create_post")
async def callback_create_post(callback: CallbackQuery):
    """Создать новый пост"""
    # Перенаправляем на команду создания поста
    await callback.message.answer("Используйте команду /create для создания нового поста.")
    await callback.answer()
