from aiogram import Router, Bot
from aiogram import F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from states import NewProject
import supabase_db
from __init__ import TEXTS

router = Router()

@router.message(Command(commands=["project", "projects"]))
async def cmd_project(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=2)
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    
    # If no subcommand, list projects and provide inline switch/create
    if len(args) == 1:
        if not user:
            await message.answer(TEXTS[lang]['projects_not_found'])
            return
        projects = supabase_db.db.list_projects(user_id)
        if not projects:
            # Нет проектов - предлагаем создать
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📁 Создать проект", callback_data="proj_new")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await message.answer(
                "📁 **Управление проектами**\n\n"
                "У вас пока нет проектов. Создайте первый проект для начала работы!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        lines = [TEXTS[lang]['projects_list_title']]
        current_proj = user.get("current_project")
        for proj in projects:
            name = proj.get("name", "Unnamed")
            if current_proj and proj["id"] == current_proj:
                lines.append(TEXTS[lang]['projects_item_current'].format(name=name))
            else:
                lines.append(TEXTS[lang]['projects_item'].format(name=name))
        
        # Build inline keyboard with each project and a New Project button
        buttons = []
        for proj in projects:
            name = proj.get("name", "Unnamed")
            buttons.append([InlineKeyboardButton(text=name + (" ✅" if current_proj and proj["id"] == current_proj else ""),
                                                callback_data=f"proj_switch:{proj['id']}")])
        buttons.append([InlineKeyboardButton(text="➕ " + ("Новый проект" if lang == "ru" else "New Project"),
                                            callback_data="proj_new")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("\n".join(lines), reply_markup=kb)
        return

    sub = args[1].lower()
    if sub in ("new", "create"):
        # Create a new project with given name
        if len(args) < 3:
            # No name provided, start FSM
            await state.set_state(NewProject.name)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="proj_new_cancel")]
            ])
            await message.answer(
                "📁 **Создание нового проекта**\n\n"
                "Введите название нового проекта:",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        proj_name = args[2].strip()
        if not proj_name:
            await message.answer("Название проекта не может быть пустым." if lang == "ru" else "Project name cannot be empty.")
            return
        project = supabase_db.db.create_project(user_id, proj_name)
        if not project:
            await message.answer("Ошибка: не удалось создать проект." if lang == "ru" else "Error: Failed to create project.")
            return
        # Set as current project
        supabase_db.db.update_user(user_id, {"current_project": project["id"]})
        await message.answer(TEXTS[lang]['projects_created'].format(name=proj_name))
    elif sub == "switch":
        if len(args) < 3:
            await message.answer("Использование:\n/project switch <project_id>" if lang == "ru" else "Usage:\n/project switch <project_id>")
            return
        try:
            pid = int(args[2])
        except:
            await message.answer(TEXTS[lang]['projects_not_found'])
            return
        # Verify membership
        if not supabase_db.db.is_user_in_project(user_id, pid):
            await message.answer(TEXTS[lang]['projects_not_found'])
            return
        project = supabase_db.db.get_project(pid)
        if not project:
            await message.answer(TEXTS[lang]['projects_not_found'])
            return
        supabase_db.db.update_user(user_id, {"current_project": pid})
        await message.answer(TEXTS[lang]['projects_switched'].format(name=project.get("name", "")))
    elif sub == "invite":
        if len(args) < 3:
            await message.answer(TEXTS[lang]['projects_invite_usage'])
            return
        target = args[2].strip()
        try:
            invitee_id = int(target)
        except:
            invitee_id = None
        if not invitee_id:
            await message.answer(TEXTS[lang]['projects_invite_usage'])
            return
        # Ensure current project exists
        if not user or not user.get("current_project"):
            await message.answer(TEXTS[lang]['projects_not_found'])
            return
        proj_id = user["current_project"]
        # Check if invitee has started bot
        invitee_user = supabase_db.db.get_user(invitee_id)
        if not invitee_user:
            await message.answer(TEXTS[lang]['projects_invite_not_found'])
            return
        # Add user to project
        added = supabase_db.db.add_user_to_project(invitee_id, proj_id, role="admin")
        if not added:
            await message.answer("Пользователь уже в проекте." if lang == "ru" else "User is already a member of the project.")
            return
        await message.answer(TEXTS[lang]['projects_invite_success'].format(user_id=invitee_id))
        # Notify invited user
        proj = supabase_db.db.get_project(proj_id)
        inviter_name = message.from_user.full_name or f"user {user_id}"
        invitee_lang = invitee_user.get("language", "ru")
        notify_text = TEXTS[invitee_lang]['projects_invited_notify'].format(project=proj.get("name", ""), user=inviter_name)
        # Include a button to switch immediately
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Переключиться" if invitee_lang == "ru" else "🔄 Switch to project", callback_data=f"proj_switch:{proj_id}")]
        ])
        try:
            await bot.send_message(invitee_id, notify_text, reply_markup=kb)
        except Exception:
            # If bot can't send message (user hasn't started chat), ignore
            pass
    else:
        # Unknown subcommand
        await message.answer(TEXTS[lang]['projects_not_found'])

@router.callback_query(lambda c: c.data and c.data.startswith("proj_switch:"))
async def on_switch_project(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        proj_id = int(callback.data.split(":", 1)[1])
    except:
        await callback.answer()
        return
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    if not supabase_db.db.is_user_in_project(user_id, proj_id):
        await callback.answer(TEXTS[lang]['projects_not_found'], show_alert=True)
        return
    project = supabase_db.db.get_project(proj_id)
    if not project:
        await callback.answer(TEXTS[lang]['projects_not_found'], show_alert=True)
        return
    # Update current project
    supabase_db.db.update_user(user_id, {"current_project": proj_id})
    
    # Возвращаем обновленное меню проектов
    try:
        projects = supabase_db.db.list_projects(user_id)
        text = "📁 **Ваши проекты:**\n\n"
        current_proj = proj_id  # Только что переключились
        
        buttons = []
        for proj in projects:
            name = proj.get("name", "Unnamed")
            is_current = proj["id"] == current_proj
            
            if is_current:
                text += f"• **{name}** ✅ (текущий)\n"
            else:
                text += f"• {name}\n"
            
            button_text = f"{name}" + (" ✅" if is_current else "")
            buttons.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"proj_switch:{proj['id']}"
            )])
        
        buttons.append([InlineKeyboardButton(text="➕ Новый проект", callback_data="proj_new")])
        buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer(f"✅ Переключен на проект '{project.get('name', '')}'")
    except Exception as e:
        print(f"Error updating project menu: {e}")
        await callback.answer(TEXTS[lang]['projects_switched'].format(name=project.get("name", "")), show_alert=True)

@router.callback_query(F.data == "proj_new")
async def on_new_project(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    if not user:
        user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Устанавливаем состояние для создания проекта
    await state.set_state(NewProject.name)
    
    # Клавиатура для отмены
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="proj_new_cancel")]
    ])
    
    await callback.message.edit_text(
        "📁 **Создание нового проекта**\n\n"
        "Введите название нового проекта:\n\n"
        "💡 Примеры: \"Мой блог\", \"Компания ABC\", \"Личные проекты\"",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "proj_new_cancel")
async def on_new_project_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена создания проекта"""
    await state.clear()
    
    # Возвращаемся к меню проектов
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    try:
        projects = supabase_db.db.list_projects(user_id)
        
        if not projects:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📁 Создать проект", callback_data="proj_new")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
            ])
            await callback.message.edit_text(
                "📁 **Управление проектами**\n\n"
                "У вас пока нет проектов. Создайте первый проект для начала работы!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            # Показываем существующие проекты
            text = "📁 **Ваши проекты:**\n\n"
            current_proj = user.get("current_project")
            
            buttons = []
            for proj in projects:
                name = proj.get("name", "Unnamed")
                is_current = current_proj and proj["id"] == current_proj
                
                if is_current:
                    text += f"• **{name}** ✅ (текущий)\n"
                else:
                    text += f"• {name}\n"
                
                button_text = f"{name}" + (" ✅" if is_current else "")
                buttons.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"proj_switch:{proj['id']}"
                )])
            
            buttons.append([InlineKeyboardButton(text="➕ Новый проект", callback_data="proj_new")])
            buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    except Exception as e:
        print(f"Error in project cancel: {e}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            "❌ Создание проекта отменено",
            reply_markup=keyboard
        )
    
    await callback.answer("Создание проекта отменено")

@router.message(NewProject.name, F.text)
async def create_new_project_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    project_name = message.text.strip()
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Проверка на команды отмены
    if project_name.lower() in ['/cancel', 'отмена', 'cancel']:
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Создание проекта отменено", reply_markup=keyboard)
        return
    
    if not project_name:
        await message.answer(
            "❌ Название проекта не может быть пустым.\n\n"
            "Введите название проекта или отправьте /cancel для отмены:",
            parse_mode="Markdown"
        )
        return
    
    # Проверка длины названия
    if len(project_name) > 50:
        await message.answer(
            "❌ Название проекта слишком длинное (максимум 50 символов).\n\n"
            "Введите более короткое название:",
            parse_mode="Markdown"
        )
        return
    
    # Создаем проект
    try:
        project = supabase_db.db.create_project(user_id, project_name)
        if not project:
            await message.answer("❌ Ошибка при создании проекта. Попробуйте еще раз.")
            await state.clear()
            return
        
        # Set new project as current
        supabase_db.db.update_user(user_id, {"current_project": project["id"]})
        
        # Показываем успешное создание с меню действий
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📺 Добавить канал", callback_data="channels_add")],
            [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post")],
            [InlineKeyboardButton(text="📁 Управление проектами", callback_data="menu_projects")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await message.answer(
            f"✅ **Проект создан!**\n\n"
            f"Проект **'{project_name}'** успешно создан и активирован.\n\n"
            f"**Следующие шаги:**\n"
            f"• Добавьте каналы для публикации\n"
            f"• Создайте первый пост\n"
            f"• Настройте автоматизацию\n\n"
            f"Что хотите сделать дальше?",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await state.clear()
        
    except Exception as e:
        print(f"Error creating project: {e}")
        await message.answer(
            "❌ **Ошибка при создании проекта**\n\n"
            "Попробуйте еще раз или обратитесь к администратору.",
            parse_mode="Markdown"
        )
        await state.clear()

# Дополнительные обработчики для совместимости с другими модулями
@router.message(NewProject.name)
async def handle_non_text_project_name(message: Message, state: FSMContext):
    """Обработка нетекстовых сообщений при создании проекта"""
    await message.answer(
        "❌ **Некорректный ввод**\n\n"
        "Пожалуйста, введите название проекта текстом.\n\n"
        "Или отправьте /cancel для отмены.",
        parse_mode="Markdown"
    )
