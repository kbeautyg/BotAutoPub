import asyncio
from datetime import datetime, timedelta, timezone
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from storage import supabase_db
from commands import TEXTS
import json

async def start_scheduler(bot: Bot, check_interval: int = 5):
    """Background task to publish scheduled posts and send notifications."""
    while True:
        now_utc = datetime.now(timezone.utc)
        # 1. Publish due posts
        due_posts = supabase_db.db.get_due_posts(now_utc)
        for post in due_posts:
            post_id = post["id"]
            user_id = post.get("user_id")
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
            fmt = post.get("format") or ""
            buttons = []
            markup = None
            if post.get("buttons"):
                try:
                    buttons = json.loads(post["buttons"]) if isinstance(post["buttons"], str) else post["buttons"]
                except Exception:
                    buttons = post["buttons"] or []
            if buttons:
                kb = []
                for btn in buttons:
                    if isinstance(btn, dict):
                        btn_text = btn.get("text"); btn_url = btn.get("url")
                    elif isinstance(btn, (list, tuple)) and len(btn) >= 2:
                        btn_text, btn_url = btn[0], btn[1]
                    else:
                        continue
                    if btn_text and btn_url:
                        kb.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
                if kb:
                    markup = InlineKeyboardMarkup(inline_keyboard=kb)
            parse_mode = None
            if fmt.lower() == "markdown":
                parse_mode = "Markdown"
            elif fmt.lower() == "html":
                parse_mode = "HTML"
            try:
                if media_id and media_type:
                    if media_type.lower() == "photo":
                        await bot.send_photo(chat_id, photo=media_id, caption=text, parse_mode=parse_mode, reply_markup=markup)
                    elif media_type.lower() == "video":
                        await bot.send_video(chat_id, video=media_id, caption=text, parse_mode=parse_mode, reply_markup=markup)
                    else:
                        await bot.send_message(chat_id, text or TEXTS['en']['no_text'], parse_mode=parse_mode, reply_markup=markup)
                else:
                    await bot.send_message(chat_id, text or TEXTS['en']['no_text'], parse_mode=parse_mode, reply_markup=markup)
            except Exception as e:
                error_msg = str(e)
                if user_id:
                    chan_name = str(chat_id)
                    channel = supabase_db.db.get_channel_by_chat_id(chat_id)
                    if channel:
                        chan_name = channel.get("name") or str(chat_id)
                    lang = "ru"
                    user = supabase_db.db.get_user(user_id)
                    if user:
                        lang = user.get("language", "ru")
                    msg_text = TEXTS[lang]['error_post_failed'].format(id=post_id, channel=chan_name, error=error_msg)
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
                            current_dt = datetime.fromisoformat(pub_time_str)
                        except Exception:
                            current_dt = datetime.strptime(pub_time_str, "%Y-%m-%dT%H:%M:%S")
                    else:
                        current_dt = now_utc
                    next_time = current_dt + timedelta(seconds=repeat_int)
                    supabase_db.db.update_post(post_id, {
                        "publish_time": next_time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "published": False,
                        "notified": False
                    })
                    continue  # do not mark published
                except Exception as e:
                    print(f"Failed to schedule next repeat for post {post_id}: {e}")
            supabase_db.db.mark_post_published(post_id)
        # 2. Send notifications for upcoming posts
        upcoming_posts = supabase_db.db.list_posts(only_pending=True)
        for post in upcoming_posts:
            if post.get("published") or post.get("draft"):
                continue
            user_id = post.get("user_id")
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
                    try:
                        pub_dt = datetime.fromisoformat(pub_time_str)
                    except Exception:
                        pub_dt = datetime.strptime(pub_time_str, "%Y-%m-%dT%H:%M:%S")
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    threshold = pub_dt - timedelta(minutes=notify_before)
                    if threshold <= now < pub_dt and not post.get("notified"):
                        lang = user.get("language", "ru")
                        chan_name = ""
                        chan_id = post.get("channel_id"); chat_id = post.get("chat_id")
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
                            notify_text = TEXTS[lang]['notify_message_less_min'].format(id=post['id'], channel=chan_name)
                        else:
                            notify_text = TEXTS[lang]['notify_message'].format(id=post['id'], channel=chan_name, minutes=minutes_left)
                        try:
                            await bot.send_message(user_id, notify_text)
                            supabase_db.db.update_post(post["id"], {"notified": True})
                        except Exception as e:
                            print(f"Failed to send notification to user {user_id}: {e}")
                except Exception as e:
                    print(f"Notification check failed for post {post.get('id')}: {e}")
        await asyncio.sleep(check_interval)
