from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext   # <-- добавлен импорт
from datetime import datetime
from zoneinfo import ZoneInfo
from storage import supabase_db
from commands import TEXTS
from commands.create_post import parse_time, format_example

router = Router()

@router.message(Command("list"))
async def cmd_list(message: Message):
    user_id = message.from_user.id
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    project_id = user.get("current_project") if user else None
    if not project_id:
        await message.answer(TEXTS[lang]['no_posts'])
        return
    posts = supabase_db.db.list_posts(project_id=project_id, only_pending=True)
    if not posts:
        await message.answer(TEXTS[lang]['no_posts'])
    else:
        await message.answer(TEXTS[lang]['scheduled_posts_title'])
        for post in posts:
            pid = post.get("id")
            # Determine channel name
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
            # Determine time string
            if post.get("draft"):
                time_str = "(черновик)" if lang == "ru" else "(draft)"
            else:
                pub_time = post.get("publish_time")
                time_str = str(pub_time)
                try:
                    pub_dt = None
                    if isinstance(pub_time, str):
                        try:
                            pub_dt = datetime.fromisoformat(pub_time)
                        except:
                            pub_dt = datetime.strptime(pub_time, "%Y-%m-%dT%H:%M:%S")
                        pub_dt = pub_dt.replace(tzinfo=ZoneInfo("UTC"))
                    elif isinstance(pub_time, datetime):
                        pub_dt = pub_time
                    tz_name = user.get("timezone", "UTC") if user else "UTC"
                    tz = ZoneInfo(tz_name)
                    pub_local = pub_dt.astimezone(tz) if pub_dt else None
                    if pub_local:
                        date_fmt = user.get("date_format", "YYYY-MM-DD") if user else "YYYY-MM-DD"
                        time_fmt = user.get("time_format", "HH:MM") if user else "HH:MM"
                        fmt = date_fmt.replace("YYYY", "%Y").replace("YY", "%y")
                        fmt = fmt.replace("MM", "%m").replace("DD", "%d") + " " + time_fmt.replace("HH", "%H").replace("H", "%H").replace("MM", "%M").replace("M", "%M")
                        time_str = pub_local.strftime(fmt)
                    else:
                        time_str = str(pub_time)
                except Exception:
                    time_str = str(pub_time)
            repeat_flag = ""
            if post.get("repeat_interval") and post["repeat_interval"] > 0:
                repeat_flag = " 🔁"
            full_text = (post.get("text") or "").replace("\n", " ")
            preview = full_text[:30]
            if len(full_text) > 30:
                preview += "..."
            line = f"ID {pid}: {chan_name} | {time_str}{repeat_flag} | {preview}"
            # Inline keyboard for actions
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="👁️ View", callback_data=f"view_post:{pid}"),
                    InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit_post:{pid}"),
                    InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_post:{pid}")
                ]
            ])
            await message.answer(line, reply_markup=kb)

@router.message(Command("view"))
async def cmd_view(message: Message):
    user_id = message.from_user.id
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(TEXTS[lang]['view_usage'])
        return
    try:
        post_id = int(args[1])
    except:
        await message.answer(TEXTS[lang]['view_invalid_id'])
        return
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer(TEXTS[lang]['view_not_found'])
        return
    # Prepare content
    text = post.get("text") or TEXTS[lang]['no_text']
    media_id = post.get("media_id")
    media_type = post.get("media_type")
    fmt = post.get("format") or "none"
    buttons = post.get("buttons") or []
    parse_mode = None
    if fmt.lower() == "markdown":
        parse_mode = "Markdown"
    elif fmt.lower() == "html":
        parse_mode = "HTML"
    # Prepare inline markup for buttons if any
    btn_list = []
    if isinstance(buttons, str):
        try:
            btn_list = __import__("json").loads(buttons) if buttons else []
        except:
            btn_list = []
    elif isinstance(buttons, list):
        btn_list = buttons
    markup = None
    if btn_list:
        kb = []
        for btn in btn_list:
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
    # Send the post preview to user
    try:
        if media_id and media_type:
            if media_type.lower() == "photo":
                await message.answer_photo(media_id, caption=text, parse_mode=parse_mode, reply_markup=markup)
            elif media_type.lower() == "video":
                await message.answer_video(media_id, caption=text, parse_mode=parse_mode, reply_markup=markup)
            else:
                await message.answer(text, parse_mode=parse_mode, reply_markup=markup)
        else:
            await message.answer(text, parse_mode=parse_mode, reply_markup=markup)
    except Exception as e:
        err_msg = f"Не удалось показать пост: {e}" if lang == "ru" else f"Failed to display post: {e}"
        await message.answer(err_msg)

@router.message(Command("reschedule"))
async def cmd_reschedule(message: Message):
    user_id = message.from_user.id
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(TEXTS[lang]['reschedule_usage'])
        return
    try:
        post_id = int(args[1])
    except:
        await message.answer(TEXTS[lang]['reschedule_invalid_id'])
        return
    time_str = args[2]
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer(TEXTS[lang]['reschedule_not_found'])
        return
    if post.get("published"):
        await message.answer(TEXTS[lang]['reschedule_post_published'])
        return
    # Parse new time
    user_settings = supabase_db.db.get_user(user_id) or {}
    try:
        new_dt = parse_time(user_settings, time_str)
    except Exception:
        example = format_example(user_settings)
        await message.answer(TEXTS[lang]['create_time_error'].format(example=example))
        return
    now = datetime.now(ZoneInfo("UTC"))
    if new_dt <= now:
        await message.answer(TEXTS[lang]['time_past_error'])
        return
    # Update post time and mark not published
    updates = {}
    updates["publish_time"] = new_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    updates["published"] = False
    updates["repeat_interval"] = post.get("repeat_interval", 0)  # keep same repeat
    # If it was published (shouldn't be here), skip, otherwise set notified False
    updates["notified"] = False
    supabase_db.db.update_post(post_id, updates)
    await message.answer(TEXTS[lang]['reschedule_success'].format(id=post_id))

# Callback handlers for interactive post management

@router.callback_query(lambda c: c.data and c.data.startswith("view_post:"))
async def on_view_post(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        post_id = int(callback.data.split(":", 1)[1])
    except:
        await callback.answer()
        return
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer(TEXTS[lang]['view_not_found'], show_alert=True)
        return
    text = post.get("text") or TEXTS[lang]['no_text']
    media_id = post.get("media_id")
    media_type = post.get("media_type")
    fmt = post.get("format") or "none"
    buttons = post.get("buttons") or []
    parse_mode = None
    if fmt.lower() == "markdown":
        parse_mode = "Markdown"
    elif fmt.lower() == "html":
        parse_mode = "HTML"
    btn_list = []
    if isinstance(buttons, str):
        try:
            btn_list = json.loads(buttons) if buttons else []
        except:
            btn_list = []
    elif isinstance(buttons, list):
        btn_list = buttons
    markup = None
    if btn_list:
        kb = []
        for btn in btn_list:
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
    try:
        if media_id and media_type:
            if media_type.lower() == "photo":
                await callback.message.answer_photo(media_id, caption=text, parse_mode=parse_mode, reply_markup=markup)
            elif media_type.lower() == "video":
                await callback.message.answer_video(media_id, caption=text, parse_mode=parse_mode, reply_markup=markup)
            else:
                await callback.message.answer(text, parse_mode=parse_mode, reply_markup=markup)
        else:
            await callback.message.answer(text, parse_mode=parse_mode, reply_markup=markup)
    except Exception as e:
        await callback.message.answer(f"Failed to display post: {e}" if lang != "ru" else f"Не удалось показать пост: {e}")
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("edit_post:"))
async def on_edit_post(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        post_id = int(callback.data.split(":", 1)[1])
    except:
        await callback.answer()
        return
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer(TEXTS[lang]['edit_post_not_found'], show_alert=True)
        return
    if post.get("published"):
        await callback.answer(TEXTS[lang]['edit_post_published'], show_alert=True)
        return
    # Start edit FSM similar to /edit command
    await state.update_data(orig_post=post, user_settings=(user or supabase_db.db.ensure_user(user_id, default_lang=lang)))
    await state.set_state(EditPost.text)
    current_text = post.get("text") or ""
    await callback.message.answer(TEXTS[lang]['edit_begin'].format(id=post_id, text=current_text))
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("delete_post:"))
async def on_delete_post(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        post_id = int(callback.data.split(":", 1)[1])
    except:
        await callback.answer()
        return
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await callback.answer(TEXTS[lang]['delete_not_found'], show_alert=True)
        return
    if post.get("published"):
        await callback.answer(TEXTS[lang]['delete_already_published'], show_alert=True)
        return
    # Prompt confirmation for deletion
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=TEXTS[lang]['yes_btn'], callback_data=f"confirm_delete_post:{post_id}"),
            InlineKeyboardButton(text=TEXTS[lang]['no_btn'], callback_data=f"cancel_delete_post:{post_id}")
        ]
    ])
    await callback.message.edit_text(TEXTS[lang]['delete_confirm'].format(id=post_id), reply_markup=kb)
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("confirm_delete_post:"))
async def on_confirm_delete_post(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        post_id = int(callback.data.split(":", 1)[1])
    except:
        await callback.answer()
        return
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    post = supabase_db.db.get_post(post_id)
    if not post:
        # Already deleted or not found
        try:
            await callback.message.edit_text(TEXTS[lang]['delete_not_found'])
        except:
            pass
        await callback.answer()
        return
    if post.get("published"):
        try:
            await callback.message.edit_text(TEXTS[lang]['delete_already_published'])
        except:
            pass
        await callback.answer()
        return
    # Delete the post
    supabase_db.db.delete_post(post_id)
    try:
        await callback.message.edit_text(TEXTS[lang]['delete_success'].format(id=post_id))
    except:
        await callback.answer(TEXTS[lang]['delete_success'].format(id=post_id), show_alert=True)
    await callback.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("cancel_delete_post:"))
async def on_cancel_delete_post(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        post_id = int(callback.data.split(":", 1)[1])
    except:
        await callback.answer()
        return
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    post = supabase_db.db.get_post(post_id)
    if post:
        # Reconstruct original listing line and buttons
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
        # Format time string as in list
        if post.get("draft"):
            time_str = "(черновик)" if lang == "ru" else "(draft)"
        else:
            pub_time = post.get("publish_time")
            time_str = str(pub_time)
            try:
                pub_dt = None
                if isinstance(pub_time, str):
                    try:
                        pub_dt = datetime.fromisoformat(pub_time)
                    except:
                        pub_dt = datetime.strptime(pub_time, "%Y-%m-%dT%H:%M:%S")
                        pub_dt = pub_dt.replace(tzinfo=ZoneInfo("UTC"))
                elif isinstance(pub_time, datetime):
                    pub_dt = pub_time
                tz_name = user.get("timezone", "UTC") if user else "UTC"
                tz = ZoneInfo(tz_name)
                pub_local = pub_dt.astimezone(tz) if pub_dt else None
                if pub_local:
                    date_fmt = user.get("date_format", "YYYY-MM-DD") if user else "YYYY-MM-DD"
                    time_fmt = user.get("time_format", "HH:MM") if user else "HH:MM"
                    fmt = date_fmt.replace("YYYY", "%Y").replace("YY", "%y")
                    fmt = fmt.replace("MM", "%m").replace("DD", "%d") + " " + time_fmt.replace("HH", "%H").replace("H", "%H").replace("MM", "%M").replace("M", "%M")
                    time_str = pub_local.strftime(fmt)
                else:
                    time_str = str(pub_time)
            except:
                time_str = str(pub_time)
        repeat_flag = ""
        if post.get("repeat_interval") and post["repeat_interval"] > 0:
            repeat_flag = " 🔁"
        full_text = (post.get("text") or "").replace("\n", " ")
        preview = full_text[:30]
        if len(full_text) > 30:
            preview += "..."
        line = f"ID {post_id}: {chan_name} | {time_str}{repeat_flag} | {preview}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👁️ View", callback_data=f"view_post:{post_id}"),
                InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit_post:{post_id}"),
                InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_post:{post_id}")
            ]
        ])
        await callback.message.edit_text(line, reply_markup=kb)
    else:
        await callback.message.edit_text(TEXTS[lang]['confirm_post_cancel'])
    await callback.answer(TEXTS[lang]['confirm_post_cancel'])
