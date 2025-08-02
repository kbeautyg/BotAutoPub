import asyncio
from datetime import datetime, timedelta, timezone
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import supabase_db
from __init__ import TEXTS
import json
from view_post import clean_text_for_format

def prepare_media_text(text: str, max_caption_length: int = 800) -> tuple[str, str]:
    """
    Подготовить текст для медиа с caption и возможное дополнительное сообщение
    Возвращает (caption_text, additional_text)
    
    Уменьшен лимит до 800 символов чтобы учесть экранирование MarkdownV2
    """
    if not text:
        return "", ""
    
    if len(text) <= max_caption_length:
        return text, ""
    
    # Обрезаем caption и оставляем остальное для отдельного сообщения
    # Ищем последний пробел в пределах лимита, чтобы не разрывать слова
    caption_text = text[:max_caption_length]
    last_space = caption_text.rfind(' ')
    
    if last_space > max_caption_length * 0.8:  # Если пробел найден не слишком далеко от конца
        caption_text = text[:last_space] + "..."
        additional_text = text[last_space:].strip()
    else:
        caption_text = text[:max_caption_length-3] + "..."
        additional_text = text[max_caption_length:].strip()
    
    return caption_text, additional_text

async def start_scheduler(bot: Bot, check_interval: int = 2):
    """Background task to publish scheduled posts and send notifications."""
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            
            # 1. Publish due posts
            due_posts = supabase_db.db.get_due_posts(now_utc)
            
            for post in due_posts:
                post_id = post["id"]
                user_id = post.get("user_id") or post.get("created_by")
                chat_id = None
                
                # Determine channel chat_id
                if post.get("chat_id"):
                    chat_id = post["chat_id"]
                else:
                    chan_id = post.get("channel_id")
                    if chan_id:
                        channel = supabase_db.db.get_channel(chan_id)
                        if channel:
                            chat_id = channel.get("chat_id")
                
                if not chat_id:
                    # No valid channel, mark as published to skip
                    supabase_db.db.mark_post_published(post_id)
                    continue
                
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

                # Try to publish
                try:
                    if media_id and media_type:
                        # Подготавливаем текст для медиа с caption (ИСПРАВЛЕНО - уменьшен лимит)
                        caption_text, additional_text = prepare_media_text(cleaned_text, max_caption_length=1000)
                        
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
                        
                        # Если есть дополнительный текст, отправляем его отдельным сообщением
                        if additional_text:
                            await bot.send_message(
                                chat_id,
                                additional_text,
                                parse_mode=parse_mode
                            )
                    else:
                        # Для текстовых сообщений без медиа ограничений caption нет
                        await bot.send_message(
                            chat_id,
                            cleaned_text or TEXTS['ru']['no_text'],
                            parse_mode=parse_mode,
                            reply_markup=markup
                        )
                    
                    print(f"✅ Пост #{post_id} успешно опубликован в канал {chat_id}")
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Ошибка публикации поста #{post_id}: {error_msg}")
                    
                    # Если ошибка связана с длинным caption, пробуем еще раз с меньшим лимитом
                    if "caption is too long" in error_msg.lower() and media_id and media_type:
                        try:
                            print(f"🔄 Повторная попытка с коротким caption для поста #{post_id}")
                            # Еще более короткий caption
                            caption_text, additional_text = prepare_media_text(cleaned_text, max_caption_length=500)
                            
                            if media_type.lower() == "photo":
                                await bot.send_photo(chat_id, photo=media_id, caption=caption_text, parse_mode=parse_mode, reply_markup=markup)
                            elif media_type.lower() == "video":
                                await bot.send_video(chat_id, video=media_id, caption=caption_text, parse_mode=parse_mode, reply_markup=markup)
                            elif media_type.lower() == "animation":
                                await bot.send_animation(chat_id, animation=media_id, caption=caption_text, parse_mode=parse_mode, reply_markup=markup)
                            
                            # Отправляем оставшийся текст отдельно
                            if additional_text:
                                await bot.send_message(chat_id, additional_text, parse_mode=parse_mode)
                            
                            print(f"✅ Пост #{post_id} опубликован после повторной попытки")
                            
                        except Exception as e2:
                            print(f"❌ Повторная попытка также провалилась для поста #{post_id}: {e2}")
                            # Уведомляем пользователя об ошибке
                            if user_id:
                                chan_name = str(chat_id)
                                channel = supabase_db.db.get_channel_by_chat_id(chat_id)
                                if channel:
                                    chan_name = channel.get("name") or str(chat_id)
                                
                                lang = "ru"
                                user = supabase_db.db.get_user(user_id)
                                if user:
                                    lang = user.get("language", "ru")
                                
                                msg_text = TEXTS[lang]['error_post_failed'].format(
                                    id=post_id, 
                                    channel=chan_name, 
                                    error=str(e2)
                                )
                                
                                try:
                                    await bot.send_message(user_id, msg_text)
                                except:
                                    pass
                    else:
                        # Другие ошибки - уведомляем пользователя
                        if user_id:
                            chan_name = str(chat_id)
                            channel = supabase_db.db.get_channel_by_chat_id(chat_id)
                            if channel:
                                chan_name = channel.get("name") or str(chat_id)
                            
                            lang = "ru"
                            user = supabase_db.db.get_user(user_id)
                            if user:
                                lang = user.get("language", "ru")
                            
                            msg_text = TEXTS[lang]['error_post_failed'].format(
                                id=post_id, 
                                channel=chan_name, 
                                error=error_msg
                            )
                            
                            try:
                                await bot.send_message(user_id, msg_text)
                            except:
                                pass
                    
                    supabase_db.db.mark_post_published(post_id)
                    continue
                
                # Handle repeating posts
                repeat_int = post.get("repeat_interval") or 0
                if repeat_int > 0:
                    try:
                        pub_time_str = post.get("publish_time")
                        if pub_time_str:
                            try:
                                # Parse datetime string
                                if isinstance(pub_time_str, str):
                                    # Remove 'Z' suffix if present
                                    if pub_time_str.endswith('Z'):
                                        pub_time_str = pub_time_str[:-1] + '+00:00'
                                    current_dt = datetime.fromisoformat(pub_time_str)
                                else:
                                    current_dt = pub_time_str
                            except Exception:
                                current_dt = datetime.strptime(pub_time_str, "%Y-%m-%dT%H:%M:%S")
                                current_dt = current_dt.replace(tzinfo=timezone.utc)
                        else:
                            current_dt = now_utc
                        
                        # Calculate next time
                        next_time = current_dt + timedelta(seconds=repeat_int)
                        
                        # Update post with new time (ИСПРАВЛЕНО - как строка)
                        supabase_db.db.update_post(post_id, {
                            "publish_time": next_time.isoformat(),
                            "published": False,
                            "notified": False
                        })
                        
                        print(f"🔄 Пост #{post_id} запланирован повторно на {next_time.isoformat()}")
                        continue  # do not mark published
                        
                    except Exception as e:
                        print(f"Failed to schedule next repeat for post {post_id}: {e}")
                
                # Mark as published
                supabase_db.db.mark_post_published(post_id)
            
            # 2. Send notifications for upcoming posts
            upcoming_posts = supabase_db.db.list_posts(only_pending=True)
            
            for post in upcoming_posts:
                if post.get("published") or post.get("draft"):
                    continue
                
                user_id = post.get("user_id") or post.get("created_by")
                if not user_id:
                    continue
                
                user = supabase_db.db.get_user(user_id)
                if not user:
                    continue
                
                notify_before = user.get("notify_before", 0)
                if notify_before and notify_before > 0:
                    try:
                        pub_time_str = post.get("publish_time")
                        if not pub_time_str:
                            continue
                        
                        # Parse publish time
                        try:
                            if isinstance(pub_time_str, str):
                                # Remove 'Z' suffix if present
                                if pub_time_str.endswith('Z'):
                                    pub_time_str = pub_time_str[:-1] + '+00:00'
                                pub_dt = datetime.fromisoformat(pub_time_str)
                            else:
                                pub_dt = pub_time_str
                        except Exception:
                            pub_dt = datetime.strptime(pub_time_str, "%Y-%m-%dT%H:%M:%S")
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        
                        # Ensure timezone aware
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        
                        now = datetime.now(timezone.utc)
                        threshold = pub_dt - timedelta(minutes=notify_before)
                        
                        # Check if it's time to notify
                        if threshold <= now < pub_dt and not post.get("notified"):
                            lang = user.get("language", "ru")
                            chan_name = ""
                            
                            chan_id = post.get("channel_id")
                            chat_id = post.get("chat_id")
                            channel = None
                            
                            if chan_id:
                                channel = supabase_db.db.get_channel(chan_id)
                            if not channel and chat_id:
                                channel = supabase_db.db.get_channel_by_chat_id(chat_id)
                            
                            if channel:
                                chan_name = channel.get("name") or str(channel.get("chat_id"))
                            else:
                                chan_name = str(chat_id) if chat_id else ""
                            
                            minutes_left = int((pub_dt - now).total_seconds() // 60)
                            
                            if minutes_left < 1:
                                notify_text = TEXTS[lang]['notify_message_less_min'].format(
                                    id=post['id'], 
                                    channel=chan_name
                                )
                            else:
                                notify_text = TEXTS[lang]['notify_message'].format(
                                    id=post['id'], 
                                    channel=chan_name, 
                                    minutes=minutes_left
                                )
                            
                            try:
                                await bot.send_message(user_id, notify_text)
                                supabase_db.db.update_post(post["id"], {"notified": True})
                                print(f"🔔 Отправлено уведомление пользователю {user_id} о посте #{post['id']}")
                            except Exception as e:
                                print(f"Failed to send notification to user {user_id}: {e}")
                                
                    except Exception as e:
                        print(f"Notification check failed for post {post.get('id')}: {e}")
            
        except Exception as e:
            print(f"❌ Ошибка в планировщике: {e}")
        
        await asyncio.sleep(check_interval)
