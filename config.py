import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    BOT_USERNAME = os.getenv('BOT_USERNAME')
    
    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    # Admin
    ADMIN_TELEGRAM_ID = int(os.getenv('ADMIN_TELEGRAM_ID', 0))
    
    # Bot settings
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Timezone
    DEFAULT_TIMEZONE = 'UTC'
    
    # Post settings
    MAX_TEXT_LENGTH = 4096
    MAX_CAPTION_LENGTH = 1024
    
    # Scheduler settings
    SCHEDULER_INTERVAL = 60  # seconds
    
    @classmethod
    def validate(cls):
        """Проверка обязательных настроек"""
        required_vars = [
            'TELEGRAM_BOT_TOKEN',
            'SUPABASE_URL', 
            'SUPABASE_KEY',
            'ADMIN_TELEGRAM_ID'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
        
        return True