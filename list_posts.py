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
    try:
        user_id = message.from_user.id
        
        # Создаем пользователя если его нет
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        # Проверяем что user не None после создания
        if not user:
            await message.answer("❌ Ошибка инициализации пользователя. Попробуйте позже.")
            return
        
        # Получаем каналы пользователя
        user_channels = supabase_db.db.get_user_channels(user_id)
        
        if not user_channels:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📺 Добавить канал", callback_data="channels_add")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer(
                "❌ **Нет доступных каналов**\n\n"
                "Добавьте канал через /channels для начала работы с постами.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        # Получаем все посты каналов пользователя
        try:
            all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False)
            if all_posts is None:
                all_posts = []
        except Exception as e:
            print(f"Ошибка получения постов: {e}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="posts_menu")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer(
                "❌ **Ошибка загрузки постов**\n\n"
                "Не удалось загрузить список постов. Попробуйте позже.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        if not all_posts:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать первый пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await message.answer(
                "📋 **Список постов**\n\n"
                "🆕 У вас пока нет постов. Создайте первый!",
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
            else:
                # Посты без времени публикации и не черновики - считаем как запланированные
                scheduled_posts.append(post)
        
        # Сортируем
        scheduled_posts.sort(key=lambda x: x.get("publish_time") or "")
        draft_posts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        published_posts.sort(key=lambda x: x.get("publish_time") or "", reverse=True)
        
        # Формируем текст
        text = f"📋 **Все посты ваших каналов**\n\n"
        text += f"📊 Всего постов: {len(all_posts)}\n\n"
        
        if scheduled_posts:
            text += f"⏰ **Запланированные ({len(scheduled_posts)}):**\n"
            for i, post in enumerate(scheduled_posts[:5], 1):
                try:
                    channel = supabase_db.db.get_channel(post.get("channel_id"))
                    channel_name = channel.get("name", "?") if channel else "?"
                    time_str = format_post_time(post, user)
                    post_text = post.get("text", "Без текста")[:30]
                    text += f"{i}. #{post['id']} • {channel_name} • {time_str}\n   📝 {post_text}...\n"
                except Exception as e:
                    print(f"Error formatting post {post.get('id')}: {e}")
                    text += f"{i}. #{post.get('id', '?')} • Ошибка загрузки\n"
            if len(scheduled_posts) > 5:
                text += f"   _...и еще {len(scheduled_posts) - 5} постов_\n"
            text += "\n"
        
        if draft_posts:
            text += f"📝 **Черновики ({len(draft_posts)}):**\n"
            for i, post in enumerate(draft_posts[:3], 1):
                try:
                    channel = supabase_db.db.get_channel(post.get("channel_id"))
                    channel_name = channel.get("name", "?") if channel else "?"
                    post_text = post.get("text", "Без текста")[:30]
                    text += f"{i}. #{post['id']} • {channel_name}\n   📝 {post_text}...\n"
                except Exception as e:
                    print(f"Error formatting draft post {post.get('id')}: {e}")
                    text += f"{i}. #{post.get('id', '?')} • Ошибка загрузки\n"
            if len(draft_posts) > 3:
                text += f"   _...и еще {len(draft_posts) - 3} черновиков_\n"
            text += "\n"
        
        if published_posts:
            text += f"✅ **Опубликованные ({len(published_posts)}):**\n"
            text += f"   _Показаны последние {min(3, len(published_posts))} из {len(published_posts)}_\n"
            for i, post in enumerate(published_posts[:3], 1):
                try:
                    channel = supabase_db.db.get_channel(post.get("channel_id"))
                    channel_name = channel.get("name", "?") if channel else "?"
                    post_text = post.get("text", "Без текста")[:30]
                    text += f"{i}. #{post['id']} • {channel_name}\n   📝 {post_text}...\n"
                except Exception as e:
                    print(f"Error formatting published post {post.get('id')}: {e}")
                    text += f"{i}. #{post.get('id', '?')} • Ошибка загрузки\n"
        
        # Добавляем полезные команды
        text += (
            f"\n💡 **Полезные команды:**\n"
            f"• `/view <ID>` - просмотр поста\n"
            f"• `/edit <ID>` - редактировать пост\n"
            f"• `/delete <ID>` - удалить пост"
        )
        
        keyboard = get_posts_list_keyboard(
            has_scheduled=bool(scheduled_posts),
            has_drafts=bool(draft_posts),
            has_published=bool(published_posts)
        )
        
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error in cmd_list_posts: {e}")
        await message.answer("❌ Произошла ошибка при загрузке списка постов. Попробуйте позже.")

# Callback для кнопки "Мои посты" из меню
@router.callback_query(F.data == "posts_menu")
async def callback_posts_menu(callback: CallbackQuery):
    """Показать меню постов через callback"""
    try:
        user_id = callback.from_user.id
        
        # Создаем пользователя если его нет
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        if not user:
            await callback.message.edit_text("❌ Ошибка инициализации пользователя")
            await callback.answer()
            return
        
        # Получаем каналы пользователя
        user_channels = supabase_db.db.get_user_channels(user_id)
        
        if not user_channels:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📺 Добавить канал", callback_data="channels_add")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await callback.message.edit_text(
                "❌ **Нет доступных каналов**\n\n"
                "Добавьте канал через /channels для начала работы с постами.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await callback.answer()
            return
        
        # Получаем все посты каналов пользователя
        try:
            all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False)
            if all_posts is None:
                all_posts = []
        except Exception as e:
            print(f"Ошибка получения постов: {e}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="posts_menu")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await callback.message.edit_text(
                "❌ **Ошибка загрузки постов**\n\n"
                "Не удалось загрузить список постов. Попробуйте позже.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await callback.answer()
            return
        
        if not all_posts:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать первый пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(
                "📋 **Список постов**\n\n"
                "🆕 У вас пока нет постов. Создайте первый!",
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
            else:
                # Посты без времени публикации и не черновики
                scheduled_posts.append(post)
        
        # Формируем текст
        text = f"📋 **Управление постами**\n\n"
        text += f"📊 **Статистика:**\n"
        
        if scheduled_posts:
            text += f"⏰ Запланированных: {len(scheduled_posts)}\n"
        if draft_posts:
            text += f"📝 Черновиков: {len(draft_posts)}\n"
        if published_posts:
            text += f"✅ Опубликованных: {len(published_posts)}\n"
        
        text += f"\n🔢 Всего постов: {len(all_posts)}"
        
        keyboard = get_posts_list_keyboard(
            has_scheduled=bool(scheduled_posts),
            has_drafts=bool(draft_posts),
            has_published=bool(published_posts)
        )
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        
    except Exception as e:
        print(f"Error in callback_posts_menu: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "posts_scheduled")
async def callback_posts_scheduled(callback: CallbackQuery):
    """Показать запланированные посты"""
    try:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        if not user:
            await callback.message.edit_text("❌ Ошибка инициализации пользователя")
            await callback.answer()
            return
        
        # Получаем каналы пользователя
        user_channels = supabase_db.db.get_user_channels(user_id)
        
        if not user_channels:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
            ])
            await callback.message.edit_text("❌ Нет доступных каналов", reply_markup=keyboard)
            await callback.answer()
            return
        
        # Получаем запланированные посты каналов пользователя
        try:
            all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False)
            if all_posts is None:
                all_posts = []
            posts = [p for p in all_posts if not p.get("published") and not p.get("draft") and (p.get("publish_time") or not p.get("draft"))]
            posts.sort(key=lambda x: x.get("publish_time") or "")
        except Exception as e:
            print(f"Ошибка получения запланированных постов: {e}")
            posts = []
        
        if not posts:
            text = "⏰ **Запланированные посты**\n\n❌ Нет запланированных постов."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
            ])
        else:
            text = "⏰ **Запланированные посты**\n\n"
            
            current_channel = None
            for post in posts:
                try:
                    # Получаем информацию о канале
                    channel = supabase_db.db.get_channel(post.get("channel_id"))
                    channel_name = channel.get("name", "Неизвестный канал") if channel else "Неизвестный канал"
                    
                    if channel_name != current_channel:
                        if current_channel is not None:
                            text += "\n"
                        text += f"**📺 {channel_name}:**\n"
                        current_channel = channel_name
                    
                    # Форматируем время
                    time_str = format_post_time(post, user)
                    post_text = post.get("text", "Без текста")[:50]
                    
                    text += f"• #{post['id']} {time_str}\n  📝 {post_text}...\n"
                except Exception as e:
                    print(f"Error formatting scheduled post {post.get('id')}: {e}")
                    text += f"• #{post.get('id', '?')} Ошибка загрузки\n"
            
            # Добавляем кнопки для навигации по постам
            buttons = []
            if posts:
                # Показываем первые 5 постов как кнопки
                for post in posts[:5]:
                    try:
                        channel = supabase_db.db.get_channel(post.get("channel_id"))
                        channel_name = channel.get("name", "?")[:10] if channel else "?"
                        buttons.append([InlineKeyboardButton(
                            text=f"#{post['id']} • {channel_name}",
                            callback_data=f"post_view:{post['id']}"
                        )])
                    except Exception as e:
                        print(f"Error creating button for post {post.get('id')}: {e}")
            
            buttons.append([InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        
    except Exception as e:
        print(f"Error in callback_posts_scheduled: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "posts_drafts")
async def callback_posts_drafts(callback: CallbackQuery):
    """Показать черновики"""
    try:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        if not user:
            await callback.message.edit_text("❌ Ошибка инициализации пользователя")
            await callback.answer()
            return
        
        # Получаем каналы пользователя
        user_channels = supabase_db.db.get_user_channels(user_id)
        
        if not user_channels:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
            ])
            await callback.message.edit_text("❌ Нет доступных каналов", reply_markup=keyboard)
            await callback.answer()
            return
        
        # Получаем черновики каналов пользователя
        try:
            all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False)
            if all_posts is None:
                all_posts = []
            posts = [p for p in all_posts if p.get("draft")]
            posts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        except Exception as e:
            print(f"Ошибка получения черновиков: {e}")
            posts = []
        
        if not posts:
            text = "📝 **Черновики**\n\n❌ Нет сохраненных черновиков."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
            ])
        else:
            text = "📝 **Черновики**\n\n"
            
            for i, post in enumerate(posts, 1):
                try:
                    channel = supabase_db.db.get_channel(post.get("channel_id"))
                    channel_name = channel.get("name", "Канал не выбран") if channel else "Канал не выбран"
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
                    text += f"   📝 {post_text}...\n\n"
                except Exception as e:
                    print(f"Error formatting draft post {post.get('id')}: {e}")
                    text += f"{i}. **#{post.get('id', '?')}** • Ошибка загрузки\n\n"
            
            # Добавляем кнопки для навигации
            buttons = []
            if posts:
                for post in posts[:5]:
                    try:
                        buttons.append([InlineKeyboardButton(
                            text=f"#{post['id']} • Открыть",
                            callback_data=f"post_view:{post['id']}"
                        )])
                    except Exception as e:
                        print(f"Error creating button for draft post {post.get('id')}: {e}")
            
            buttons.append([InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        
    except Exception as e:
        print(f"Error in callback_posts_drafts: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data == "posts_published")
async def callback_posts_published(callback: CallbackQuery):
    """Показать опубликованные посты"""
    try:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        if not user:
            await callback.message.edit_text("❌ Ошибка инициализации пользователя")
            await callback.answer()
            return
        
        # Получаем каналы пользователя
        user_channels = supabase_db.db.get_user_channels(user_id)
        
        if not user_channels:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
            ])
            await callback.message.edit_text("❌ Нет доступных каналов", reply_markup=keyboard)
            await callback.answer()
            return
        
        # Получаем все посты и фильтруем опубликованные
        try:
            all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False)
            if all_posts is None:
                all_posts = []
            posts = [p for p in all_posts if p.get("published")]
            posts.sort(key=lambda x: x.get("publish_time") or "", reverse=True)
        except Exception as e:
            print(f"Ошибка получения опубликованных постов: {e}")
            posts = []
        
        if not posts:
            text = "✅ **Опубликованные посты**\n\n❌ Нет опубликованных постов."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")]
            ])
        else:
            text = f"✅ **Опубликованные посты**\n\nВсего: {len(posts)}\n\n"
            
            # Показываем последние 10
            for i, post in enumerate(posts[:10], 1):
                try:
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
                    text += f"   📝 {post_text}...\n\n"
                except Exception as e:
                    print(f"Error formatting published post {post.get('id')}: {e}")
                    text += f"{i}. **#{post.get('id', '?')}** • Ошибка загрузки\n\n"
            
            if len(posts) > 10:
                text += f"_...и еще {len(posts) - 10} постов_"
            
            buttons = []
            buttons.append([InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="posts_menu")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        
    except Exception as e:
        print(f"Error in callback_posts_published: {e}")
        await callback.answer("❌ Произошла ошибка")

# Обработчик просмотра поста по callback
@router.callback_query(F.data.startswith("post_view:"))
async def callback_view_post(callback: CallbackQuery):
    """Просмотр поста через callback"""
    try:
        post_id = int(callback.data.split(":")[-1])
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        if not user:
            user = supabase_db.db.ensure_user(user_id)
        
        if not user:
            await callback.answer("❌ Ошибка инициализации пользователя")
            return
        
        post = supabase_db.db.get_post(post_id)
        if not post:
            await callback.answer("❌ Пост не найден")
            return
        
        # Проверяем доступ через канал
        if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
            await callback.answer("❌ У вас нет доступа к этому посту")
            return
        
        # Показываем полный просмотр поста
        try:
            from view_post import send_post_preview, format_time_for_user
            
            # Отправляем полный превью поста
            await send_post_preview(callback.message, post)
            
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
                info_text += f"⏰ **Запланировано:** {formatted_time}\n"
            
            # Создаем клавиатуру действий
            buttons = []
            
            if not post.get('published'):
                buttons.append([
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_direct:{post_id}"),
                    InlineKeyboardButton(text="🚀 Опубликовать", callback_data=f"post_publish_cmd:{post_id}")
                ])
                buttons.append([
                    InlineKeyboardButton(text="📅 Перенести", callback_data=f"post_reschedule_cmd:{post_id}"),
                    InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post_delete_cmd:{post_id}")
                ])
            
            buttons.append([
                InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
            await callback.answer()
            
        except ImportError:
            # Fallback если модуль view_post недоступен
            info_text = f"👀 **Пост #{post_id}**\n\nИспользуйте команду `/view {post_id}` для полного просмотра."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
            await callback.answer()
            
    except Exception as e:
        print(f"Error in callback_view_post: {e}")
        await callback.answer("❌ Произошла ошибка")
