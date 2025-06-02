from aiogram import Router, Bot
from aiogram import F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from states import NewProject
from storage import supabase_db
from commands import TEXTS

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
            await message.answer(TEXTS[lang]['projects_not_found'])
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
            # No name provided, prompt usage or start FSM
            await message.answer(TEXTS[lang]['projects_invite_usage'] if sub == "invite" else "Please provide a project name.")
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
    # Edit any message (if listing) to reflect switch
    try:
        await callback.message.edit_text(TEXTS[lang]['projects_switched'].format(name=project.get("name", "")))
    except:
        await callback.answer(TEXTS[lang]['projects_switched'].format(name=project.get("name", "")), show_alert=True)
    await callback.answer()

@router.callback_query(F.data == "proj_new")
async def on_new_project(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    await callback.message.answer("Введите название нового проекта:" if lang == "ru" else "Please send the new project name:")
    await state.set_state(NewProject.name)
    await callback.answer()

@router.message(NewProject.name)
async def create_new_project_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    project_name = message.text.strip()
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    if not project_name:
        await message.answer("Название проекта не может быть пустым." if lang == "ru" else "Project name cannot be empty.")
        return
    project = supabase_db.db.create_project(user_id, project_name)
    if not project:
        await message.answer("Ошибка при создании проекта." if lang == "ru" else "Failed to create project.")
        await state.clear()
        return
    # Set new project as current
    supabase_db.db.update_user(user_id, {"current_project": project["id"]})
    await message.answer(TEXTS[lang]['projects_created'].format(name=project_name))
    await state.clear()
