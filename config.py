import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Telegram API limits
MAX_MEDIA_SIZE_MB = 20
ALLOWED_MEDIA_TYPES = ['photo', 'video', 'document'] # For validation
ALLOWED_MEDIA_EXTENSIONS = {
    'photo': ['jpg', 'jpeg', 'png', 'gif', 'webp'],
    'video': ['mp4', 'mov', 'avi', 'mkv'],
    'document': ['pdf', 'doc', 'docx', 'txt']
}