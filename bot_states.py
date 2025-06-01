from aiogram.fsm.state import State, StatesGroup

class CreatePost(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    waiting_for_channels = State()
    waiting_for_buttons = State()
    waiting_for_send_mode = State()
    waiting_for_one_time_schedule = State()
    waiting_for_cyclic_schedule_type = State()
    waiting_for_cyclic_schedule_details = State()
    waiting_for_cyclic_schedule_dates = State()
    waiting_for_deletion_rule = State()
    waiting_for_confirmation = State()

class ManageChannels(StatesGroup):
    waiting_for_channel_to_add = State()
    waiting_for_channel_to_delete = State()

class EditPost(StatesGroup):
    waiting_for_post_id = State()
    waiting_for_edit_choice = State()
    editing_text = State()
    editing_media = State()
    editing_buttons = State()
    editing_channels = State()
    editing_schedule_mode = State()
    editing_one_time_schedule = State()
    editing_cyclic_schedule_type = State()
    editing_cyclic_schedule_details = State()
    editing_cyclic_schedule_dates = State()
    editing_deletion_rule = State()
    waiting_for_edit_confirmation = State()

class DeletePost(StatesGroup):
    waiting_for_post_id = State()

class ChangeTimezone(StatesGroup):
    waiting_for_timezone = State()