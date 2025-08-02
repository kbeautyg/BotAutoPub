#!/usr/bin/env python3
"""
Тест улучшенной функции подготовки текста для caption
"""

import sys
sys.path.append('/app')

from auto_post_fixed import prepare_media_text_smart, prepare_media_text

def test_caption_length_handling():
    """Тестирует обработку длинных caption с экранированием"""
    
    print("🧪 ТЕСТИРОВАНИЕ ОБРАБОТКИ ДЛИННЫХ CAPTION")
    print("=" * 60)
    
    # Тестовый текст пользователя с проблемными символами - длинный
    long_text = """🎉 НОВОСТЬ: Запуск партнёрской программы KBeautyGuide!

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

    print(f"📝 ИСХОДНЫЙ ТЕКСТ:")
    print(f"Длина: {len(long_text)} символов")
    print(f"Превью: {long_text[:150]}...")
    print("\n" + "-" * 50)
    
    # Тестируем разные режимы парсинга
    parse_modes = [
        ("MarkdownV2", "Markdown с экранированием"),
        ("HTML", "HTML форматирование"),
        (None, "Без форматирования")
    ]
    
    for parse_mode, description in parse_modes:
        print(f"\n🔄 ТЕСТИРОВАНИЕ: {description}")
        
        try:
            # Умная функция
            smart_caption, smart_additional = prepare_media_text_smart(
                long_text, 
                parse_mode, 
                max_caption_length=1024
            )
            
            print(f"✅ Умная функция:")
            print(f"   Caption длина: {len(smart_caption)} символов")
            print(f"   Дополнительный текст: {len(smart_additional)} символов")
            print(f"   Caption в пределах лимита: {len(smart_caption) <= 1024}")
            
            if len(smart_caption) > 100:
                print(f"   Caption превью: {smart_caption[:100]}...")
            else:
                print(f"   Caption: {smart_caption}")
            
            # Старая функция для сравнения
            old_caption, old_additional = prepare_media_text(long_text, max_caption_length=800)
            
            print(f"\n📊 Старая функция (для сравнения):")
            print(f"   Caption длина: {len(old_caption)} символов")
            print(f"   Дополнительный текст: {len(old_additional)} символов")
            
        except Exception as e:
            print(f"❌ ОШИБКА: {e}")
        
        print("-" * 40)
    
    # Дополнительные тесты с разными длинами
    print(f"\n🎯 ТЕСТЫ С РАЗНОЙ ДЛИНОЙ:")
    
    test_lengths = [
        ("Короткий", "Привет! Это короткое сообщение."),
        ("Средний", "Это текст средней длины с некоторыми символами: точки, дефисы - и скобки (тест)! " * 3),
        ("Длинный", long_text)
    ]
    
    for length_name, test_text in test_lengths:
        print(f"\n📋 {length_name} текст ({len(test_text)} символов):")
        
        try:
            caption, additional = prepare_media_text_smart(test_text, "MarkdownV2", max_caption_length=1024)
            
            print(f"   ✅ Caption: {len(caption)} символов")
            print(f"   ✅ Дополнительный: {len(additional)} символов")
            print(f"   ✅ В пределах лимита: {len(caption) <= 1024}")
            
            if len(caption) > 50:
                print(f"   Превью: {caption[:50]}...")
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    print(f"\n" + "=" * 60)
    print("🏁 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")

if __name__ == "__main__":
    test_caption_length_handling()