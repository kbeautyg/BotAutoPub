from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import supabase_db
from __init__ import TEXTS
from datetime import datetime
from zoneinfo import ZoneInfo

router = Router()

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
    
    if not is_published:
        buttons.append([
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit:{post_id}"),
            InlineKeyboardButton(text="🚀 Опубликовать", callback_data=f"post_publish:{post_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="📅 Перенести", callback_data=f"post_reschedule:{post_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post_delete:{post_id}")
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
        # Конвертируем время в часовой пояс пользователя
        if user and user.get('timezone'):
            try:
                utc_time = datetime.fromisoformat(post['publish_time'].replace('Z', '+00:00'))
                user_tz = ZoneInfo(user['timezone'])
                local_time = utc_time.astimezone(user_tz)
                time_str = local_time.strftime('%Y-%m-%d %H:%M')
                text += f"⏰ **Запланировано:** {time_str} ({user['timezone']})\n"
            except:
                text += f"⏰ **Запланировано:** {post['publish_time']}\n"
        else:
            text += f"⏰ **Запланировано:** {post['publish_time']}\n"
    else:
        text += "❓ **Статус:** Неопределен\n"
    
    # Канал
    if post.get('channels'):
        text += f"📺 **Канал:** {post['channels']['name']}\n"
    
    # Формат
    if post.get('parse_mode'):
        text += f"🎨 **Формат:** {post['parse_mode']}\n"
    
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
            import json
            buttons = json.loads(post['buttons']) if isinstance(post['buttons'], str) else post['buttons']
            text += f"\n🔘 **Кнопок:** {len(buttons)}"
        except:
            text += f"\n🔘 **Кнопки:** есть"
    
    return text

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
                utc_time = datetime.fromisoformat(post['publish_time'].replace('Z', '+00:00'))
                if user.get('timezone'):
                    user_tz = ZoneInfo(user['timezone'])
                    local_time = utc_time.astimezone(user_tz)
                    time_str = local_time.strftime('%m-%d %H:%M')
                else:
                    time_str = utc_time.strftime('%m-%d %H:%M')
                
                post_text = post.get('text', 'Без текста')[:30]
                text += f"  • {time_str} - {post_text}...\n"
                
                # Кнопка для каждого поста
                buttons.append([InlineKeyboardButton(
                    text=f"📋 Пост #{post['id']} ({time_str})",
                    callback_data=f"post_view:{post['id']}"
                )])
            except:
                text += f"  • Пост #{post['id']}\n"
        
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

@router.callback_query(F.data.startswith("post_publish:"))
async def callback_publish_post(callback: CallbackQuery):
    """Опубликовать пост немедленно"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
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

@router.callback_query(F.data.startswith("post_delete:"))
async def callback_delete_post(callback: CallbackQuery):
    """Удалить пост"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
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
