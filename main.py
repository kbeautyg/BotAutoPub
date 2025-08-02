import asyncio
import os
import logging
import json
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
from view_post import clean_text_for_format

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing BOT_TOKEN or SUPABASE_URL or SUPABASE_KEY in environment")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize Supabase database interface
import supabase_db
supabase_db.db = supabase_db.SupabaseDB(SUPABASE_URL, SUPABASE_KEY)
supabase_db.db.init_schema()

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode=None)
dp = Dispatcher(storage=MemoryStorage())

# Функция для мгновенной публикации постов
async def publish_post_immediately(bot: Bot, post_id: int) -> bool:
    """Немедленно опубликовать конкретный пост"""
    try:
        # Получаем пост
        post = supabase_db.db.get_post(post_id)
        if not post or post.get("published") or post.get("draft"):
            return False
        
        # Определяем chat_id канала
        chat_id = None
        if post.get("chat_id"):
            chat_id = post["chat_id"]
        else:
            chan_id = post.get("channel_id")
            if chan_id:
                channel = supabase_db.db.get_channel(chan_id)
                if channel:
                    chat_id = channel.get("chat_id")
        
        if not chat_id:
            return False
        
        text = post.get("text") or ""
        media_id = post.get("media_id")
        media_type = post.get("media_type")
        parse_mode_field = post.get("parse_mode") or post.get("format") or ""
        buttons = []
        markup = None
        
        # Parse buttons
        if post.get("buttons"):
            try:
                buttons = json.loads(post["buttons"]) if isinstance(post["buttons"], str) else post["buttons"]
            except Exception:
                buttons = post["buttons"] or []
        
        if buttons:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = []
            for btn in buttons:
                if isinstance(btn, dict):
                    btn_text = btn.get("text")
                    btn_url = btn.get("url")
                elif isinstance(btn, (list, tuple)) and len(btn) >= 2:
                    btn_text, btn_url = btn[0], btn[1]
                else:
                    continue
                if btn_text and btn_url:
                    kb.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
            if kb:
                markup = InlineKeyboardMarkup(inline_keyboard=kb)
        
        # Determine parse mode
        parse_mode = None
        if parse_mode_field and parse_mode_field.lower() == "markdown":
            parse_mode = "MarkdownV2"
        elif parse_mode_field and parse_mode_field.lower() == "html":
            parse_mode = "HTML"

        cleaned_text = clean_text_for_format(
            text,
            parse_mode.replace("V2", "") if parse_mode else None,
        )

        # Импортируем умную функцию подготовки текста
        from auto_post_fixed import prepare_media_text_smart
        
        # Публикуем пост
        if media_id and media_type:
            caption_text, additional_text = prepare_media_text_smart(text, parse_mode, max_caption_length=1024)
            
            if media_type.lower() == "photo":
                await bot.send_photo(
                    chat_id, 
                    photo=media_id, 
                    caption=caption_text, 
                    parse_mode=parse_mode, 
                    reply_markup=markup
                )
            elif media_type.lower() == "video":
                await bot.send_video(
                    chat_id, 
                    video=media_id, 
                    caption=caption_text, 
                    parse_mode=parse_mode, 
                    reply_markup=markup
                )
            elif media_type.lower() == "animation":
                await bot.send_animation(
                    chat_id,
                    animation=media_id,
                    caption=caption_text,
                    parse_mode=parse_mode,
                    reply_markup=markup
                )
            
            if additional_text:
                await bot.send_message(
                    chat_id,
                    additional_text,
                    parse_mode=parse_mode
                )
        else:
            await bot.send_message(
                chat_id,
                cleaned_text or "Пост без текста",
                parse_mode=parse_mode,
                reply_markup=markup
            )
        
        # Отмечаем как опубликованный
        supabase_db.db.mark_post_published(post_id)
        print(f"✅ Пост #{post_id} немедленно опубликован в канал {chat_id}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка немедленной публикации поста #{post_id}: {e}")
        return False

# Глобальный обработчик ошибок
@dp.error()
async def error_handler(event, exception):
    """Глобальный обработчик ошибок"""
    import traceback
    
    # Логируем ошибку
    logging.error(f"Error in update {event}: {exception}")
    traceback.print_exc()
    
    # Пытаемся отправить пользователю уведомление об ошибке
    try:
        if hasattr(event, 'message') and event.message:
            await event.message.answer(
                "❌ **Произошла ошибка**\n\n"
                "Попробуйте еще раз или обратитесь к администратору.",
                parse_mode="Markdown"
            )
        elif hasattr(event, 'callback_query') and event.callback_query:
            await event.callback_query.answer("❌ Произошла ошибка. Попробуйте еще раз.")
            try:
                await event.callback_query.message.edit_text(
                    "❌ **Произошла ошибка**\n\n"
                    "Попробуйте еще раз или обратитесь к администратору.",
                    parse_mode="Markdown"
                )
            except:
                pass
    except Exception as e:
        print(f"Error in error handler: {e}")
    
    return True  # Обработано

# Include routers from command modules
import start
import help
import main_menu as main_menu
import channels
import scheduled_posts as create
import list_posts
import settings_improved
import view_post
import edit_post

# Регистрируем роутеры в правильном порядке
dp.include_router(start.router)
dp.include_router(help.router)
dp.include_router(channels.router)
dp.include_router(create.router)
dp.include_router(view_post.router)
dp.include_router(list_posts.router)
dp.include_router(settings_improved.router)
dp.include_router(edit_post.router)
dp.include_router(main_menu.router)

# Улучшенные глобальные обработчики для редактирования
@dp.callback_query(F.data.startswith("edit_field:"))
async def callback_edit_field_global(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик редактирования полей поста"""
    try:
        parts = callback.data.split(":")
        
        if len(parts) == 3 and parts[2] == "menu":
            # Это возврат в главное меню редактирования
            post_id = int(parts[1])
            user_id = callback.from_user.id
            user = supabase_db.db.get_user(user_id)
            
            # Получаем пост
            post = supabase_db.db.get_post(post_id)
            if not post:
                await callback.answer("❌ Пост не найден!")
                return
            
            # Проверяем доступ через канал
            if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
                await callback.answer("❌ У вас нет доступа к этому посту!")
                return
            
            if post.get("published"):
                await callback.answer("❌ Нельзя редактировать опубликованный пост!")
                return
            
            lang = user.get("language", "ru") if user else "ru"
            
            try:
                from edit_post import show_edit_main_menu
                await show_edit_main_menu(callback.message, post_id, post, user, lang)
            except ImportError:
                await callback.message.edit_text(f"Используйте команду `/edit {post_id}` для редактирования.")
            
            await callback.answer()
        else:
            # Обычное редактирование поля - передаем в edit_post модуль
            try:
                from edit_post import handle_edit_field_callback
                await handle_edit_field_callback(callback, state)
            except ImportError:
                post_id = int(parts[1]) if len(parts) > 1 else 0
                await callback.message.edit_text(f"Используйте команду `/edit {post_id}` для редактирования.")
                await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_field_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("edit_recreate:"))
async def callback_edit_recreate_global(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик полного пересоздания поста"""
    try:
        from edit_post import handle_edit_recreate
        await handle_edit_recreate(callback, state)
    except ImportError:
        parts = callback.data.split(":")
        post_id = int(parts[1]) if len(parts) > 1 else 0
        await callback.message.edit_text(f"Используйте команду `/edit {post_id}` для полного редактирования.")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_recreate_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("edit_menu:"))
async def callback_edit_menu_global(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик возврата в меню редактирования"""
    try:
        from edit_post import handle_edit_menu_return
        await handle_edit_menu_return(callback, state)
    except ImportError:
        parts = callback.data.split(":")
        post_id = int(parts[1]) if len(parts) > 1 else 0
        await callback.message.edit_text(f"Используйте команду `/edit {post_id}` для редактирования.")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_menu_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("edit_confirm:"))
async def callback_edit_confirm_global(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик подтверждения редактирования"""
    try:
        from edit_post import handle_edit_confirm_callback
        await handle_edit_confirm_callback(callback, state)
    except ImportError:
        await callback.message.edit_text("Ошибка: модуль редактирования недоступен.")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_confirm_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("edit_skip:"))
async def callback_edit_skip_global(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик пропуска шага редактирования"""
    try:
        from edit_post import handle_edit_skip
        await handle_edit_skip(callback, state)
    except ImportError:
        await callback.message.edit_text("Ошибка: модуль редактирования недоступен.")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_skip_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("edit_save:"))
async def callback_edit_save_global(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик сохранения редактирования"""
    try:
        from edit_post import handle_edit_save
        await handle_edit_save(callback, state)
    except ImportError:
        await callback.message.edit_text("Ошибка: модуль редактирования недоступен.")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_save_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("edit_cancel:"))
async def callback_edit_cancel_global(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик отмены редактирования"""
    try:
        from edit_post import handle_edit_cancel
        await handle_edit_cancel(callback, state)
    except ImportError:
        await callback.message.edit_text("Ошибка: модуль редактирования недоступен.")
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_cancel_global: {e}")
        await callback.answer("❌ Произошла ошибка")

# Глобальные обработчики callback'ов для управления постами
@dp.callback_query(F.data.startswith("post_edit_cmd:"))
async def callback_edit_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды редактирования поста"""
    try:
        post_id = int(callback.data.split(":", 1)[1])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать пост", callback_data=f"post_edit_direct:{post_id}")],
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
        ])
        
        await callback.message.edit_text(
            f"✏️ **Редактирование поста #{post_id}**\n\n"
            f"Выберите действие:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_edit_post_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("post_edit_direct:"))
async def callback_edit_post_global_updated(callback: CallbackQuery, state: FSMContext):
    """Глобальный обработчик команды редактирования поста (обновленный)"""
    try:
        post_id = int(callback.data.split(":", 1)[1])
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        
        # Получаем пост
        post = supabase_db.db.get_post(post_id)
        if not post:
            await callback.answer("❌ Пост не найден!")
            return
        
        # Проверяем доступ через канал
        if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
            await callback.answer("❌ У вас нет доступа к этому посту!")
            return
        
        if post.get("published"):
            await callback.answer("❌ Нельзя редактировать опубликованный пост!")
            return
        
        lang = user.get("language", "ru") if user else "ru"
        
        # Пытаемся использовать новое главное меню редактирования
        try:
            from edit_post import show_edit_main_menu
            await show_edit_main_menu(callback.message, post_id, post, user, lang)
            await callback.answer()
        except ImportError:
            # Fallback на старый интерфейс
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Редактировать пост", callback_data=f"post_edit_direct:{post_id}")],
                [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
                [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
            ])
            
            await callback.message.edit_text(
                f"✏️ **Редактирование поста #{post_id}**\n\n"
                f"Используйте команду `/edit {post_id}` для редактирования.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await callback.answer("Используйте команду /edit " + str(post_id))
    except Exception as e:
        print(f"Error in callback_edit_post_global_updated: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("post_publish_cmd:"))
async def callback_publish_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды публикации поста"""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        user_id = callback.from_user.id
        post_id = int(callback.data.split(":", 1)[1])
        
        post = supabase_db.db.get_post(post_id)
        if not post:
            await callback.answer("Пост не найден!")
            return
        
        if post.get('published'):
            await callback.answer("Пост уже опубликован!")
            return
        
        # Проверяем доступ через канал
        if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
            await callback.answer("У вас нет доступа к этому посту!")
            return
        
        # Обновляем время публикации на текущее (ИСПРАВЛЕНО - конвертируем в строку)
        now = datetime.now(ZoneInfo("UTC"))
        supabase_db.db.update_post(post_id, {
            "publish_time": now.isoformat(),  # Конвертируем в строку!
            "draft": False
        })
        
        # Пытаемся опубликовать немедленно
        published = await publish_post_immediately(bot, post_id)
        
        # Создаем клавиатуру с действиями
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        if published:
            await callback.message.edit_text(
                f"✅ **Пост #{post_id} опубликован!**\n\n"
                f"Пост успешно опубликован в канал.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await callback.answer("✅ Пост опубликован!")
        else:
            await callback.message.edit_text(
                f"🚀 **Пост #{post_id} поставлен в очередь**\n\n"
                f"Пост будет опубликован в ближайшее время.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await callback.answer("Пост поставлен в очередь на публикацию!")
    except Exception as e:
        print(f"Error in callback_publish_post_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("post_reschedule_cmd:"))
async def callback_reschedule_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды переноса поста"""
    try:
        post_id = int(callback.data.split(":", 1)[1])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            f"📅 **Перенос поста #{post_id}**\n\n"
            f"Используйте команду `/reschedule {post_id} YYYY-MM-DD HH:MM` для переноса поста.\n\n"
            f"Пример: `/reschedule {post_id} 2024-12-25 15:30`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_reschedule_post_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("post_delete_cmd:"))
async def callback_delete_post_global(callback: CallbackQuery):
    """Глобальный обработчик команды удаления поста"""
    try:
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
    except Exception as e:
        print(f"Error in callback_delete_post_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("post_delete_confirm:"))
async def callback_confirm_delete_post_global(callback: CallbackQuery):
    """Глобальный обработчик подтверждения удаления поста"""
    try:
        user_id = callback.from_user.id
        post_id = int(callback.data.split(":", 1)[1])
        
        # Проверяем доступ через канал
        post = supabase_db.db.get_post(post_id)
        if not post or not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
            await callback.answer("У вас нет доступа к этому посту!")
            return
        
        if supabase_db.db.delete_post(post_id):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await callback.message.edit_text(
                f"✅ **Пост #{post_id} удален**\n\n"
                f"Пост успешно удален из базы данных.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await callback.message.edit_text(
                f"❌ **Ошибка удаления**\n\n"
                f"Не удалось удалить пост",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_confirm_delete_post_global: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data.startswith("post_full_view:"))
async def callback_full_view_post_global(callback: CallbackQuery):
    """Глобальный обработчик полного просмотра поста"""
    try:
        user_id = callback.from_user.id
        user = supabase_db.db.get_user(user_id)
        
        post_id = int(callback.data.split(":", 1)[1])
        post = supabase_db.db.get_post(post_id)
        
        if not post:
            await callback.answer("Пост не найден!")
            return
        
        # Проверяем доступ через канал
        if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
            await callback.answer("У вас нет доступа к этому посту!")
            return
        
        # Импортируем функции для просмотра
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
                if user:
                    formatted_time = format_time_for_user(post['publish_time'], user)
                    info_text += f"⏰ **Запланировано:** {formatted_time}\n"
                else:
                    info_text += f"⏰ **Запланировано:** {post['publish_time']}\n"
            
            # Создаем клавиатуру действий
            buttons = []
            
            if not post.get('published'):
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
        print(f"Error in callback_full_view_post_global: {e}")
        await callback.answer("❌ Произошла ошибка")

# Обработчик для callback кнопки "Создать пост" из меню (обновленный)
@dp.callback_query(F.data == "menu_create_post_direct")
async def callback_create_post_direct_updated(callback: CallbackQuery):
    """Прямое создание поста через callback из меню (обновленный)"""
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Пошаговое создание", callback_data="create_step_by_step")],
            [InlineKeyboardButton(text="🚀 Быстрое создание", callback_data="create_quick_help")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            "📝 **Создание нового поста**\n\n"
            "Выберите способ создания поста:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_create_post_direct_updated: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data == "create_step_by_step")
async def callback_create_step_by_step(callback: CallbackQuery):
    """Пошаговое создание поста"""
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            "📝 **Пошаговое создание поста**\n\n"
            "Используйте команду `/create` для создания поста с пошаговым мастером.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await callback.answer("Используйте команду /create")
    except Exception as e:
        print(f"Error in callback_create_step_by_step: {e}")
        await callback.answer("❌ Произошла ошибка")

@dp.callback_query(F.data == "create_quick_help")
async def callback_create_quick_help(callback: CallbackQuery):
    """Помощь по быстрому созданию"""
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Пошаговое создание", callback_data="create_step_by_step")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            "🚀 **Быстрое создание поста**\n\n"
            "Используйте команду `/quickpost` для быстрого создания:\n\n"
            "**Формат:** `/quickpost <канал> <время> <текст>`\n\n"
            "**Примеры:**\n"
            "• `/quickpost @channel now Текст поста`\n"
            "• `/quickpost 1 draft Черновик поста`\n"
            "• `/quickpost 2 2024-12-25_15:30 Запланированный пост`\n\n"
            "**Параметры:**\n"
            "• Канал: @username, ID или номер в списке\n"
            "• Время: now, draft или YYYY-MM-DD_HH:MM\n"
            "• Текст: содержимое поста",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        print(f"Error in callback_create_quick_help: {e}")
        await callback.answer("❌ Произошла ошибка")

# Обработчик для меню постов
@dp.callback_query(F.data == "posts_menu")
async def callback_posts_menu_global(callback: CallbackQuery):
    """Глобальный обработчик меню постов"""
    try:
        from list_posts import callback_posts_menu
        await callback_posts_menu(callback)
    except Exception as e:
        print(f"Error in callback_posts_menu_global: {e}")
        await callback.answer("❌ Произошла ошибка")

# Import and start the scheduler
import auto_post_fixed as auto_post

async def main():
    print("🚀 Запуск бота...")
    print(f"📊 База данных: {SUPABASE_URL}")
    
    # Start background task for auto-posting
    asyncio.create_task(auto_post.start_scheduler(bot))
    print("⏰ Планировщик запущен")
    
    # Start polling
    print("🔄 Начинаем получение обновлений...")
    
    # Удаляем webhook если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        # Если ошибка связана с другим экземпляром бота, ждем и пробуем снова
        if "terminated by other getUpdates request" in str(e):
            print("⏳ Ожидание завершения другого экземпляра бота...")
            await asyncio.sleep(5)
            await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
