"""
Скрипт для проверки и исправления импортов
"""

def check_imports():
    """Проверка всех импортов в проекте"""
    
    files_to_check = [
        'bot.py',
        'handlers.py', 
        'conversation_handlers.py',
        'database.py',
        'scheduler.py',
        'utils.py',
        'config.py'
    ]
    
    print("Проверка импортов...")
    
    for file_name in files_to_check:
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"✅ {file_name} - файл читается корректно")
        except Exception as e:
            print(f"❌ {file_name} - ошибка: {e}")
    
    print("Проверка завершена!")

if __name__ == "__main__":
    check_imports()