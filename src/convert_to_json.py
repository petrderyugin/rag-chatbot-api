import csv
import json
import os
import re
from typing import Dict, List

def count_words(text: str) -> int:
    """Подсчитывает количество слов в тексте"""
    if not text:
        return 0
    # Разделяем по всем пробельным символам
    words = re.findall(r'\b\w+\b', text)
    return len(words)

def count_lines(text: str) -> int:
    """Подсчитывает количество строк в тексте"""
    if not text:
        return 0
    # Считаем символы новой строки + 1 (последняя строка может не иметь \n)
    return text.count('\n') + (1 if text else 0)

def convert_csv_to_json(csv_path: str, json_path: str):
    """
    Конвертирует CSV файл в JSON с нужной структурой
    
    Args:
        csv_path: Путь к входному CSV файлу
        json_path: Путь к выходному JSON файлу
    """
    print(f"Конвертация {csv_path} в {json_path}")
    
    # Проверяем существование CSV файла
    if not os.path.exists(csv_path):
        print(f"Ошибка: файл {csv_path} не найден")
        return
    
    data: List[Dict] = []
    
    try:
        # Читаем CSV файл
        with open(csv_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for i, row in enumerate(reader):
                # Получаем текст
                text = row.get('text', '')
                
                # Считаем метаданные
                characters = len(text)
                words = count_words(text)
                lines = count_lines(text)
                
                # Создаем новую запись
                new_entry = {
                    'url': row.get('url', ''),
                    'state': row.get('state', ''),
                    'title': row.get('title', ''),
                    'content': text,
                    'metadata': {
                        'characters': characters,
                        'words': words,
                        'lines': lines
                    }
                }
                
                data.append(new_entry)
                
                # Выводим прогресс каждые 100 записей
                if (i + 1) % 100 == 0:
                    print(f"  Обработано {i + 1} записей")
        
        print(f"Прочитано {len(data)} записей из CSV")
        
    except Exception as e:
        print(f"Ошибка при чтении CSV файла: {e}")
        return
    
    # Создаем папку для JSON файла, если нужно
    json_dir = os.path.dirname(json_path)
    if json_dir and not os.path.exists(json_dir):
        os.makedirs(json_dir)
        print(f"Создана папка: {json_dir}")
    
    # Записываем JSON файл
    try:
        with open(json_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, ensure_ascii=False, indent=2)
        
        print(f"Успешно сохранено в {json_path}")
        print(f"Общая статистика:")
        print(f"  Всего записей: {len(data)}")
        
        if data:
            total_chars = sum(item['metadata']['characters'] for item in data)
            total_words = sum(item['metadata']['words'] for item in data)
            total_lines = sum(item['metadata']['lines'] for item in data)
            
            print(f"  Всего символов: {total_chars:,}")
            print(f"  Всего слов: {total_words:,}")
            print(f"  Всего строк: {total_lines:,}")
            
    except Exception as e:
        print(f"Ошибка при записи JSON файла: {e}")

def main():
    import os
    """Основная функция"""
    # Определяем пути относительно расположения скрипта
    script_dir = os.path.dirname(os.path.abspath(__file__))  # Папка src
    project_root = os.path.dirname(script_dir)               # Корень проекта
    data_dir = os.path.join(project_root, "data")            # Папка data
    
    # Пути по умолчанию
    default_csv = os.path.join(data_dir, "crawled_data.csv")
    default_json = os.path.join(data_dir, "crawled_data.json")
    
    print("Конвертер CSV в JSON")
    print(f"CSV файл по умолчанию: {default_csv}")
    print(f"JSON файл по умолчанию: {default_json}")
    print("-" * 50)
    
    # Можно указать свои пути
    use_default = input("Использовать пути по умолчанию? (y/n): ").strip().lower()
    
    if use_default == 'y' or use_default == '':
        csv_path = default_csv
        json_path = default_json
    else:
        csv_path = input("Введите путь к CSV файлу: ").strip()
        json_path = input("Введите путь для JSON файла: ").strip()
    
    # Конвертируем
    convert_csv_to_json(csv_path, json_path)

if __name__ == "__main__":
    main()