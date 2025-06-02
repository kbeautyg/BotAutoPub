from aiogram.fsm.state import State, StatesGroup

class CreatePost(StatesGroup):
    text = State()
    media = State()
    format = State()
    buttons = State()
    time = State()
    repeat = State()
    channel = State()
    confirm = State()

class EditPost(StatesGroup):
    text = State()
    media = State()
    format = State()
    buttons = State()
    time = State()
    repeat = State()
    channel = State()
    confirm = State()

class NewProject(StatesGroup):
    name = State()

class AddChannel(StatesGroup):
    waiting_input = State()

class PostCreationFlow(StatesGroup):
    """Улучшенный процесс создания поста с навигацией"""
    step_text = State()
    step_media = State()
    step_format = State()
    step_buttons = State()
    step_time = State()
    step_repeat = State()
    step_channel = State()
    step_preview = State()
    step_confirm = State()
