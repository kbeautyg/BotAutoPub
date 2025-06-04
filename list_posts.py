from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
import supabase_db
from datetime import datetime
from zoneinfo import ZoneInfo

router = Router()

def format_post_time(post: dict, user: dict) -> str:
    """Форматировать время поста для отображения"""
    if post.get("published"):
        return "✅ Опубликован"
    elif post.get("draft"):
        return "📝 Черновик"
    elif post.get("publish_time"):
        try:
            # Парсим время
            time_str = post["publish_time"]
            if isinstance(time_str, str):
                if time_str.endswith('Z'):
                    time_str = time_str[:-1] + '+00:00'
                utc_time = datetime.fromisoformat(time_str)
            else:
                utc_time = time_str
            
            # Конвертируем в часовой пояс пользователя
            user_tz = ZoneInfo(user.get('timezone', 'UTC'))
            local_time = utc_time.astimezone(user_tz)
            
            # Форматируем
            return f"⏰ {local_time.strftime('%d.%m %H:%M')}"
        except:
            return "⏰ Запланирован"
    else:
        return "❓ Без времени"

def get_posts_list_keyboard(has_scheduled: bool = False, has_drafts: bool = False, has_published: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для списка постов"""
    buttons = []
    
    if has_scheduled:
        buttons.append([InlineKeyboardButton(text="⏰ Запланированные", callback_data="posts_scheduled")])
    if has_drafts:
        buttons.append([InlineKeyboardButton(text="📝 Черновики", callback_data="posts_drafts")])
    if has_published:
        buttons.append([InlineKeyboardButton(text="✅ Опубликованные", callback_data="posts_published")])
    
    buttons.append([
        InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("list"))
async def cmd_list_posts(message: Message):
    """Показать список всех постов"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        await message.answer("❌ Нет активного проекта. Создайте проект через /project")
        return
    
    # Получаем все посты
    all_posts = supabase_db.db.list_posts(project_id=project_id, only_pending=False)
    
    if not all_posts:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать первый пост", callback_data="menu_create_post_direct")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await message.answer(
            "📋 **Список постов**\n\n"
            "У вас пока нет постов. Создайте первый!",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    # Разделяем посты по категориям
    scheduled_posts = []
    draft_posts = []
    published_posts = []
    
    for post in all_posts:
        if post.get("published"):
            published_posts.append(post)
        elif post.get("draft"):
            draft_posts.append(post)
        elif post.get("publish_time"):
            scheduled_posts.append(post)
    
    # Сортируем
    scheduled_posts.sort(key=lambda x: x.get("publish_time") or "")
    draft_posts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    published_posts.sort(key=lambda x: x.get("publish_time") or "", reverse=True)
    
    # Формируем текст
    text = f"📋 **Все посты проекта**\n\n"
    text += f"Всего постов: {len(all_posts)}\n"
    
    if scheduled_posts:
        text += f"\n⏰ **Запланированные ({len(scheduled_posts)}):**\n"
        for i, post in enumerate(scheduled_posts[:5], 1):
            channel = supabase_db.db.get_channel(post.get("channel_id"))
            channel_name = channel.get("name", "?") if channel else "?"
            time_str = format_post_time(post, user)
            post_text = post.get("text", "Без текста")[:30]
            text += f"{i}. #{post['id']} • {channel_name} • {time_str}\n   {post_text}...\n"
        if len(scheduled_posts) > 5:
            text += f"   _...и еще {len(scheduled_posts) - 5} постов_\n"
    
    if draft_posts:
        text += f"\n📝 **Черновики ({len(draft_posts)}):**\n"
        for i, post in enumerate(draft_posts[:3], 1):
            channel = supabase_db.db.get_channel(post.get("channel_id"))
            channel_name = channel.get("name", "?") if channel else "?"
            post_text = post.get("text", "Без текста")[:30]
            text += f"{i}. #{post['id']} • {channel_name}\n   {post_text}...\n"
        if len(draft_posts) > 3:
            text += f"   _...и еще {len(draft_posts) - 3} черновиков_\n"
    
    if published_posts:
        text += f"\n✅ **Опубликованные ({len(published_posts)}):**\n"
        text += f"   _Показаны последние {min(3, len(published_posts))} из {len(published_posts)}_\n"
    
    keyboard = get_posts_list_keyboard(
        has_scheduled=bool(scheduled_posts),
        has_drafts=bool(draft_posts),
        has_published=bool(published_posts)
    )
    
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Callback для кнопки "Мои посты" из меню
@router.callback_query(F.data == "posts_menu")
async def callback_posts_menu(callback: CallbackQuery):
    """Показать меню постов через callback"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        await callback.message.edit_text("❌ Нет активного проекта.")
        await callback.answer()
        return
    
    # Получаем все посты
    all_posts = supabase_db.db.list_posts(project_id=project_id, only_pending=False)
    
    if not all_posts:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать первый пост", callback_data="menu_create_post_direct")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            "📋 **Список постов**\n\n"
            "У вас пока нет постов. Создайте первый!",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    # Разделяем посты по категориям
    scheduled_posts = []
    draft_posts = []
    published_posts = []
    
    for post in all_posts:
        if post.get("published"):
            published_posts.append(post)
        elif post.get("draft"):
            draft_posts.append(post)
        elif post.get("publish_time"):
            scheduled_posts.append(post)
    
    # Формируем текст
    text = f"📋 **Управление постами**\n\n"
    
    if scheduled_posts:
        text += f"⏰ Запланированных: {len(scheduled_posts)}\n"
    if draft_posts:
        text += f"📝 Черновиков: {len(draft_posts)}\n"
    if published_posts:
        text += f"✅ Опубликованных: {len(published_posts)}\n"
    
    text += f"\nВсего постов: {len(all_posts)}"
    
    keyboard = get_posts_list_keyboard(
        has_scheduled=bool(scheduled_posts),
        has_drafts=bool(draft_posts),
        has_published=bool(published_posts)
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "posts_scheduled")
async def callback_posts_scheduled(callback: CallbackQuery):
    """Показать запланированные посты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        await callback.answer("Нет активного проекта")
        return
    
    # Получаем запланированные посты
    posts = supabase_db.db.get_scheduled_posts_by_channel(project_id)
    
    if not posts:
        text = "⏰ **Запланированные посты**\n\n❌ Нет запланированных постов."
    else:
        text = "⏰ **Запланированные посты**\n\n"
        
        current_channel = None
        for post in posts:
            # Группируем по каналам
            channel_info = post.get("channels", {})
            channel_name = channel_info.get("name", "Неизвестный канал")
            
            if channel_name != current_channel:
                if current_channel is not None:
                    text += "\n"
                text += f"**📺 {channel_name}:**\n"
                current_channel = channel_name
            
            # Форматируем время
            time_str = format_post_time(post, user)
            post_text = post.get("text", "Без текста")[:50]
            
            text += f"• #{post['id']} {time_str}\n  {post_text}...\n"
    
    # Добавляем кнопки для навигации по постам
    buttons = []
    if posts:
        # Показываем первые 5 постов как кнопки
        for post in posts[:5]:
            channel_info = post.get("channels", {})
            channel_name = channel_info.get("name", "?")[:10]
            buttons.append([InlineKeyboardButton(
                text=f"#{post['id']} • {channel_name}",
                callback_data=f"post_view:{post['id']}"
            )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "posts_drafts")
async def callback_posts_drafts(callback: CallbackQuery):
    """Показать черновики"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        await callback.answer("Нет активного проекта")
        return
    
    # Получаем черновики
    posts = supabase_db.db.get_draft_posts_by_channel(project_id)
    
    if not posts:
        text = "📝 **Черновики**\n\n❌ Нет сохраненных черновиков."
    else:
        text = "📝 **Черновики**\n\n"
        
        for i, post in enumerate(posts, 1):
            channel_info = post.get("channels", {})
            channel_name = channel_info.get("name", "Канал не выбран")
            post_text = post.get("text", "Без текста")[:50]
            
            created_at = post.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    date_str = dt.strftime("%d.%m.%Y")
                except:
                    date_str = ""
            else:
                date_str = ""
            
            text += f"{i}. **#{post['id']}** • {channel_name}\n"
            if date_str:
                text += f"   📅 {date_str}\n"
            text += f"   {post_text}...\n\n"
    
    # Добавляем кнопки для навигации
    buttons = []
    if posts:
        for post in posts[:5]:
            buttons.append([InlineKeyboardButton(
                text=f"#{post['id']} • Открыть",
                callback_data=f"post_view:{post['id']}"
            )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "posts_published")
async def callback_posts_published(callback: CallbackQuery):
    """Показать опубликованные посты"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    project_id = user.get("current_project") if user else None
    
    if not project_id:
        await callback.answer("Нет активного проекта")
        return
    
    # Получаем все посты и фильтруем опубликованные
    all_posts = supabase_db.db.list_posts(project_id=project_id, only_pending=False)
    posts = [p for p in all_posts if p.get("published")]
    posts.sort(key=lambda x: x.get("publish_time") or "", reverse=True)
    
    if not posts:
        text = "✅ **Опубликованные посты**\n\n❌ Нет опубликованных постов."
    else:
        text = f"✅ **Опубликованные посты**\n\nВсего: {len(posts)}\n\n"
        
        # Показываем последние 10
        for i, post in enumerate(posts[:10], 1):
            channel = supabase_db.db.get_channel(post.get("channel_id"))
            channel_name = channel.get("name", "?") if channel else "?"
            post_text = post.get("text", "Без текста")[:50]
            
            # Форматируем дату публикации
            pub_time = post.get("publish_time")
            if pub_time:
                try:
                    dt = datetime.fromisoformat(pub_time.replace('Z', '+00:00'))
                    date_str = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    date_str = "Дата неизвестна"
            else:
                date_str = "Дата неизвестна"
            
            text += f"{i}. **#{post['id']}** • {channel_name}\n"
            text += f"   📅 {date_str}\n"
            text += f"   {post_text}...\n\n"
        
        if len(posts) > 10:
            text += f"_...и еще {len(posts) - 10} постов_"
    
    buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# Обработчик просмотра поста по callback
@router.callback_query(F.data.startswith("post_view:"))
async def callback_view_post(callback: CallbackQuery):
    """Просмотр поста через callback"""
    post_id = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("Пост не найден")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer("Нет доступа к посту")
        return
    
    # Используем функции из view_post для отображения
    from view_post import send_post_preview, format_time_for_user, get_post_management_keyboard
    
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    # Отправляем превью
    await send_post_preview(callback.message, post, channel)
    
    # Информация о посте
    info_text = f"📋 **Информация о посте #{post_id}**\n\n"
    
    if channel:
        info_text += f"**Канал:** {channel['name']}\n"
    
    if post.get("published"):
        info_text += "**Статус:** ✅ Опубликован\n"
    elif post.get("draft"):
        info_text += "**Статус:** 📝 Черновик\n"
    elif post.get("publish_time"):
        formatted_time = format_time_for_user(post['publish_time'], user)
        info_text += f"**Статус:** ⏰ Запланирован на {formatted_time}\n"
    
    parse_mode_value = post.get("parse_mode") or post.get("format")
    if parse_mode_value:
        info_text += f"**Формат:** {parse_mode_value}\n"
    
    if post.get("repeat_interval") and post["repeat_interval"] > 0:
        from edit_post_improved import format_interval
        info_text += f"**Повтор:** каждые {format_interval(post['repeat_interval'])}\n"
    
    # Кнопки управления
    keyboard = get_post_management_keyboard(post_id, post.get("published", False))
    
    await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()
