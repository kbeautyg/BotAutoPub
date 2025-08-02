#!/usr/bin/env python3
"""
Тест исправлений функции экранирования MarkdownV2
"""

import sys
sys.path.append('/app')

from view_post import clean_text_for_format

def test_markdown_escaping():
    """Тестирует исправленную функцию экранирования"""
    
    print("🧪 ТЕСТИРОВАНИЕ ИСПРАВЛЕНИЙ MARKDOWNV2")
    print("=" * 50)
    
    # Тестовый текст пользователя с проблемными символами
    test_text = """🎉 НОВОСТЬ: Запуск партнёрской программы KBeautyGuide!

Друзья, мы долго ждали этот день — теперь у тебя есть шанс не только экономить на любимой корейской косметике, но и зарабатывать вместе с нашим сообществом! 😍

💎 Для кого программа?
- Для постоянных клиентов и тех, кто любит делиться находками
- Если ты часто заказываешь для себя/друзей — тебе точно к нам!

✨ Преимущества партнёрства:
👥 Участие только для членов нашего сообщества — ощущай себя в клубе избранных  
💰 Бонусы за рекомендации и оптовые закупки  
🌏 100% оригинал из Кореи — лично проверяем в Сеуле  
🔥 Выгодно и надёжно — ноль переплат и рисков  
🚀 Самые свежие новинки и тренды до магазинов

📌 Условия участия простые, а возможности для роста — безграничные! Стань частью команды и развивай KBeautyGuide вместе с нами. Идеально для тех, кто уже закупается «на троих» или хочет сделать бьюти-увлечение источником дохода.

👉 Хочешь узнать детали? Пиши в личку — расскажу всё, подскажу и помогу стартовать!

#KGG_Партнеры #KGG_Сообщество #ПолезноеОтKBG"""

    print("📝 ИСХОДНЫЙ ТЕКСТ:")
    print(test_text[:200] + "..." if len(test_text) > 200 else test_text)
    print("\n" + "-" * 50)
    
    # Тестируем разные форматы
    formats = [
        ("HTML", "HTML"),
        ("Markdown", "MarkdownV2"),
        (None, "Обычный текст")
    ]
    
    for format_name, description in formats:
        print(f"\n🔄 ТЕСТИРОВАНИЕ ФОРМАТА: {description}")
        
        try:
            cleaned_text = clean_text_for_format(test_text, format_name)
            
            print(f"✅ Обработка успешна для {description}")
            print(f"📏 Длина результата: {len(cleaned_text)} символов")
            
            # Показываем первые 200 символов результата
            preview = cleaned_text[:200] + "..." if len(cleaned_text) > 200 else cleaned_text
            print(f"👀 Превью результата:")
            print(preview)
            
            # Проверяем проблемные символы для MarkdownV2
            if format_name == "Markdown":
                problem_chars = ['.', '-', '!', '(', ')', '_', '*']
                unescaped_found = []
                
                for char in problem_chars:
                    # Ищем неэкранированные символы (не предшествует \)
                    import re
                    unescaped = re.findall(f'[^\\\\]{re.escape(char)}', cleaned_text)
                    if unescaped:
                        unescaped_found.append(char)
                
                if unescaped_found:
                    print(f"⚠️  Найдены потенциально неэкранированные символы: {unescaped_found}")
                else:
                    print("✅ Все специальные символы корректно экранированы")
            
        except Exception as e:
            print(f"❌ ОШИБКА при обработке {description}: {e}")
        
        print("-" * 30)
    
    # Дополнительные тесты с конкретными проблемными случаями
    print(f"\n🎯 ДОПОЛНИТЕЛЬНЫЕ ТЕСТЫ:")
    
    problem_cases = [
        "Простой текст с точкой.",
        "Текст с дефисом - и скобками (тест)!",
        "Символы: _подчеркивание_ *жирный* [ссылка]",
        "Эмодзи 🎉 и спецсимволы: #хештег @упоминание",
        "[b]Жирный[/b] и [i]курсив[/i] с [url=https://example.com]ссылкой[/url]"
    ]
    
    for i, test_case in enumerate(problem_cases, 1):
        print(f"\n📋 Тест {i}: {test_case}")
        try:
            result = clean_text_for_format(test_case, "Markdown")
            print(f"✅ Результат: {result}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    print(f"\n" + "=" * 50)
    print("🏁 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")

if __name__ == "__main__":
    test_markdown_escaping()