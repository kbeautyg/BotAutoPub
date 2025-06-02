#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации бота
"""

import os
from config import Config

def test_config():
    """Проверка конфигурации"""
    print("🔍 Проверка конфигурации бота...\n")
    
    # Проверяем переменные окружения
    env_vars = {
        'TELEGRAM_BOT_TOKEN': Config.TELEGRAM_BOT_TOKEN,
        'SUPABASE_URL': Config.SUPABASE_URL,
        'SUPABASE_KEY': Config.SUPABASE_KEY,
        'ADMIN_TELEGRAM_ID': Config.ADMIN_TELEGRAM_ID,
        'BOT_USERNAME': Config.BOT_USERNAME,
        'DEBUG': Config.DEBUG
    }
    
    missing_vars = []
    
    for var_name, var_value in env_vars.items():
        if var_value:
            if var_name in ['SUPABASE_KEY', 'TELEGRAM_BOT_TOKEN']:
                # Скрываем чувствительные данные
                masked_value = var_value[:10] + "..." + var_value[-5:] if len(var_value) > 15 else "***"
                print(f"✅ {var_name}: {masked_value}")
            else:
                print(f"✅ {var_name}: {var_value}")
        else:
            print(f"❌ {var_name}: НЕ УСТАНОВЛЕНА")
            missing_vars.append(var_name)
    
    print()
    
    if missing_vars:
        print(f"❌ Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
        print("\n📝 Создайте .env файл с следующими переменными:")
        print("TELEGRAM_BOT_TOKEN=your_bot_token_here")
        print("SUPABASE_URL=your_supabase_url_here")
        print("SUPABASE_KEY=your_supabase_anon_key_here")
        print("ADMIN_TELEGRAM_ID=your_telegram_id_here")
        print("BOT_USERNAME=your_bot_username_here")
        print("DEBUG=False")
        return False
    else:
        print("✅ Все переменные окружения настроены!")
        
        # Проверяем валидацию
        try:
            Config.validate()
            print("✅ Конфигурация валидна!")
            return True
        except ValueError as e:
            print(f"❌ Ошибка валидации: {e}")
            return False

if __name__ == "__main__":
    success = test_config()
    if success:
        print("\n🚀 Бот готов к запуску!")
    else:
        print("\n⚠️ Исправьте ошибки конфигурации перед запуском бота.")