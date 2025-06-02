from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from storage import supabase_db
from commands import TEXTS

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    # Determine default language from user's Telegram settings
    lang_code = message.from_user.language_code or ""
    default_lang = "ru"
    if lang_code.startswith("en"):
        default_lang = "en"
    elif lang_code.startswith("ru"):
        default_lang = "ru"
    # Ensure user exists with default settings (and default project)
    user = supabase_db.db.ensure_user(user_id, default_lang=default_lang)
    # Greet in user's language
    lang = user.get("language", default_lang) if user else default_lang
    await message.answer(TEXTS[lang]['start_welcome'])

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    user_id = message.from_user.id
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    if not current_state:
        await message.answer(TEXTS[lang]['confirm_post_cancel'])
    else:
        await state.clear()
        await message.answer(TEXTS[lang]['confirm_post_cancel'])
