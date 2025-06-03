from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
import supabase_db
from __init__ import TEXTS

router = Router()

@router.message(Command("help"))
async def cmd_help(message: Message):
    user_id = message.from_user.id
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    
    # Расширенная справка с всеми командами
    help_text = """
📖 **Справка по боту**

**Основные команды:**
• `/start` - начать работу с ботом
• `/menu` - главное меню
• `/help` - эта справка

**Управление постами:**
• `/create` - создать новый пост (пошагово)
• `/quickpost <канал> <время> <текст>` - быстрое создание
  Примеры:
  - `/quickpost @channel now Текст поста`
  - `/quickpost 1 draft Черновик`
  - `/quickpost 2 2024-12-25_15:30 Пост`

• `/list` - список всех постов
• `/view <ID>` - просмотр поста
• `/edit <ID>` - редактировать пост
• `/delete <ID>` - удалить пост
• `/publish <ID>` - опубликовать немедленно
• `/reschedule <ID> <дата> <время>` - перенести публикацию

**Управление каналами:**
• `/channels` - меню управления каналами
• `/channels add <@канал или ID>` - добавить канал
• `/channels remove <ID>` - удалить канал
• `/channels list` - список каналов

**Проекты:**
• `/project` - управление проектами
• `/project new <название>` - создать проект
• `/project switch <ID>` - переключить проект
• `/project invite <user_id>` - пригласить пользователя

**Настройки:**
• `/settings` - настройки профиля

**Текстовые команды для ИИ-агента:**
При создании/редактировании поста можно использовать:
• `skip` или `пропустить` - пропустить шаг
• `back` или `назад` - вернуться назад
• `cancel` или `отмена` - отменить операцию
• `now` или `сейчас` - опубликовать сейчас
• `draft` или `черновик` - сохранить как черновик

**Форматы времени:**
• `YYYY-MM-DD HH:MM` (2024-12-25 15:30)
• `DD.MM.YYYY HH:MM` (25.12.2024 15:30)
• `DD/MM/YYYY HH:MM` (25/12/2024 15:30)

💡 **Совет:** Бот оптимизирован для работы с ИИ-агентами и поддерживает текстовые команды на каждом шаге!
"""
    
    await message.answer(help_text, parse_mode="Markdown")
