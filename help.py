from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from storage import supabase_db
from commands import TEXTS

router = Router()

@router.message(Command("help"))
async def cmd_help(message: Message):
    user_id = message.from_user.id
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    await message.answer(TEXTS[lang]['help'])
