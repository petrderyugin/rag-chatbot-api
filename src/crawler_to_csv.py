import time
import csv
import re
from urllib.parse import urljoin, urlparse
from collections import deque
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from bs4 import BeautifulSoup
import requests
from typing import List, Dict, Set, Optional
import os

class SmartWebCrawler:
    def __init__(self, start_url: str, max_depth: int = 3, output_file: str = 'crawled_data.csv'):
        """
        Инициализация краулера
        
        Args:
            start_url: Начальный URL для обхода
            max_depth: Максимальная глубина обхода (1 = главная, 2 = с главная, 3 = со второго уровня)
            output_file: Файл для сохранения результатов
        """
        self.start_url = start_url
        self.max_depth = max_depth
        self.output_file = output_file
        self.domain = urlparse(start_url).netloc
        
        # Паттерны для определения страниц ошибок по заголовку
        self.error_patterns = [
            r'404',
            r'страница не найдена',
            r'page not found',
            r'ошибка',
            r'error',
            r'not found',
            r'не найдено'
        ]
        
        # Инициализация Selenium WebDriver
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')  # Фоновый режим
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Структуры для хранения данных
        self.visited_urls: Set[str] = set()
        self.visited_states: Set[str] = set()  # Для отслеживания уникальных состояний
        self.data: List[Dict] = []
        
        # Статистика
        self.stats = {
            'total_pages': 0,
            'total_states': 0,
            'dynamic_interactions': 0,
            'skipped_errors': 0
        }
    
    def is_error_page(self, title: str, text: str) -> bool:
        """Проверяет, является ли страница страницей ошибки (проверяем только заголовок)"""
        title_lower = title.lower()
        
        for pattern in self.error_patterns:
            if re.search(pattern, title_lower):
                return True
        
        # Дополнительная проверка: очень короткие страницы с подозрительными заголовками
        if len(text) < 50 and any(word in title_lower for word in ['error', 'ошибка', '404']):
            return True
            
        return False
    
    def close_cookie_notice(self):
        """Закрывает cookie-уведомления, если они есть"""
        try:
            # Селекторы для cookie-уведомлений
            cookie_selectors = [
                '.cookie-notice',
                '.cookie-banner',
                '.cookie-consent',
                '.cookies',
                '#cookie-notice',
                '#cookie-banner',
                '.cc-banner',
                '.cc-cookies',
                '[class*="cookie"]',
                '[id*="cookie"]'
            ]
            
            for selector in cookie_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            # Ищем кнопки закрыть/принять внутри уведомления
                            close_buttons = element.find_elements(By.CSS_SELECTOR, 
                                "button, a, [role='button'], .close, .btn-close, [class*='close'], [class*='accept'], [class*='agree']")
                            
                            for btn in close_buttons:
                                if btn.is_displayed() and btn.is_enabled():
                                    try:
                                        btn_text = btn.text.lower() if btn.text else ""
                                        if any(word in btn_text for word in ['принять', 'согласен', 'ok', 'ок', 'закрыть', 'close', 'accept', 'agree']):
                                            self.driver.execute_script("arguments[0].click();", btn)
                                            time.sleep(0.5)
                                            print(f"    Закрыто cookie-уведомление")
                                            return True
                                    except:
                                        pass
                            
                            # Если не нашли кнопку, пробуем кликнуть на сам элемент
                            try:
                                self.driver.execute_script("arguments[0].click();", element)
                                time.sleep(0.5)
                                print(f"    Закрыто cookie-уведомление (клик на элемент)")
                                return True
                            except:
                                pass
                except:
                    pass
        except Exception as e:
            # Не критично, если не удалось закрыть
            pass
        
        return False
    
    def safe_click_element(self, element):
        """Безопасный клик на элемент с обработкой cookie-уведомлений"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                # Прокручиваем к элементу
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)
                
                # Проверяем видимость
                if not element.is_displayed() or not element.is_enabled():
                    return False
                
                # Пробуем кликнуть
                element.click()
                time.sleep(0.5)
                return True
                
            except ElementClickInterceptedException:
                # Если элемент перекрыт, пробуем закрыть cookie-уведомление
                if attempt < max_attempts - 1:
                    print(f"      Элемент перекрыт, попытка {attempt + 1} из {max_attempts}: закрываю cookie-уведомление")
                    self.close_cookie_notice()
                    time.sleep(0.5)
                else:
                    # Последняя попытка - используем JavaScript
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        time.sleep(0.5)
                        return True
                    except:
                        return False
                        
            except Exception as e:
                if attempt < max_attempts - 1:
                    # Пробуем еще раз
                    time.sleep(0.5)
                else:
                    # Последняя попытка - используем JavaScript
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        time.sleep(0.5)
                        return True
                    except:
                        return False
        
        return False
    
    def save_to_csv(self):
        """Сохраняет собранные данные в CSV файл"""
        if not self.data:
            print("Нет данных для сохранения")
            return
            
        output_dir = os.path.dirname(self.output_file)
        with open(self.output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['url', 'state', 'title', 'text']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.data)
        
        print(f"Данные сохранены в {self.output_file}")
        print(f"Статистика: {self.stats['total_pages']} страниц, {self.stats['total_states']} состояний")
        print(f"Пропущено страниц с ошибками: {self.stats['skipped_errors']}")
    
    def get_page_title(self) -> str:
        """Получает заголовок страницы"""
        try:
            return self.driver.title
        except:
            return ""
    
    def get_page_text(self) -> str:
        """Получает весь видимый текст страницы"""
        try:
            body = self.driver.find_element(By.TAG_NAME, 'body')
            return body.text.strip()
        except:
            return ""
    
    def save_page_state(self, url: str, state_name: str = "initial"):
        """Сохраняет текущее состояние страницы"""
        state_key = f"{url}||{state_name}"
        
        if state_key in self.visited_states:
            return False
            
        title = self.get_page_title()
        text = self.get_page_text()
        
        # Не сохраняем пустые страницы (менее 10 символов)
        if not text or len(text) < 10:
            return False
        
        # Проверяем, не является ли страница страницей ошибки (только по заголовку)
        if self.is_error_page(title, text):
            print(f"  Пропуск страницы с ошибкой: {title}")
            self.stats['skipped_errors'] += 1
            return False
        
        self.data.append({
            'url': url,
            'state': state_name,
            'title': title,
            'text': text
        })
        
        self.visited_states.add(state_key)
        self.stats['total_states'] += 1
        
        print(f"  Сохранено состояние: {state_name} (символов: {len(text)})")
        return True
    
    def extract_links_statically(self, html_content: str, base_url: str) -> List[str]:
        """
        Извлекает все ссылки из HTML контента (статический анализ)
        
        Args:
            html_content: HTML код страницы
            base_url: Базовый URL для преобразования относительных ссылок
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Пропускаем якоря и javascript ссылки
            if href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Преобразуем относительные ссылки в абсолютные
            full_url = urljoin(base_url, href)
            
            # Проверяем, что ссылка ведет на тот же домен
            if urlparse(full_url).netloc == self.domain:
                links.append(full_url)
        
        return list(set(links))  # Убираем дубликаты
    
    def click_hash_links(self, url: str):
        """Обрабатываем ссылки с href='#' (hash-ссылки)"""
        try:
            # Закрываем cookie-уведомление перед началом обработки
            self.close_cookie_notice()
            
            # Сначала сохраняем информацию о всех hash-ссылках на странице
            initial_hash_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href='#']")
            
            if not initial_hash_links:
                print("  Hash-ссылки (href='#') не найдены")
                return 0
            
            print(f"  Найдено hash-ссылок: {len(initial_hash_links)}")
            
            clicked_count = 0
            max_links_to_click = min(10, len(initial_hash_links))
            
            # Создаем список уникальных идентификаторов для каждой ссылки
            link_identifiers = []
            for i, link in enumerate(initial_hash_links):
                try:
                    # Собираем уникальный идентификатор для ссылки
                    link_text = link.text.strip()[:50] if link.text.strip() else f"link_{i}"
                    link_class = link.get_attribute('class') or ''
                    link_id = link.get_attribute('id') or ''
                    
                    identifier = {
                        'index': i,
                        'text': link_text,
                        'class': link_class,
                        'id': link_id
                    }
                    link_identifiers.append(identifier)
                    print(f"    Ссылка {i}: текст='{link_text}'")
                    
                except Exception as e:
                    print(f"    Ошибка при получении информации о ссылке {i}: {e}")
                    link_identifiers.append({'index': i, 'text': f"link_{i}"})
            
            # Теперь обрабатываем каждую ссылку
            for i, identifier in enumerate(link_identifiers[:max_links_to_click]):
                try:
                    # Для каждой ссылки (кроме первой) перезагружаем страницу
                    if i > 0:
                        self.driver.get(url)
                        time.sleep(3)
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )
                        # Закрываем cookie-уведомление после перезагрузки
                        self.close_cookie_notice()
                    
                    # Находим все hash-ссылки на текущей странице
                    current_hash_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href='#']")
                    
                    if i >= len(current_hash_links):
                        print(f"    Ссылка с индексом {i} не найдена после перезагрузки")
                        continue
                    
                    # Пытаемся найти ссылку с похожими характеристиками
                    target_link = None
                    
                    # Сначала попробуем найти по индексу
                    if i < len(current_hash_links):
                        target_link = current_hash_links[i]
                    
                    # Если не нашли по индексу, ищем по тексту
                    if not target_link and identifier['text']:
                        for link in current_hash_links:
                            try:
                                current_text = link.text.strip()[:50] if link.text.strip() else ''
                                if current_text and identifier['text'].lower() == current_text.lower():
                                    target_link = link
                                    break
                            except:
                                continue
                    
                    if not target_link:
                        print(f"    Не удалось найти ссылку {i} после перезагрузки")
                        continue
                    
                    # Теперь кликаем на найденную ссылку
                    try:
                        # Сохраняем текст до клика
                        text_before = self.driver.find_element(By.TAG_NAME, 'body').text
                        
                        # Используем безопасный клик с обработкой cookie-уведомлений
                        click_success = self.safe_click_element(target_link)
                        
                        if not click_success:
                            print(f"    Не удалось кликнуть на hash-ссылку '{identifier['text']}'")
                            continue
                        
                        # Даем время на изменение контента
                        time.sleep(1.5)
                        
                        # Проверяем изменения
                        text_after = self.driver.find_element(By.TAG_NAME, 'body').text
                        
                        # Сохраняем состояние, если текст изменился
                        if text_after != text_before:
                            # Используем текст ссылки в имени состояния
                            safe_link_text = re.sub(r'[^\w\s-]', '', identifier['text']).strip().replace(' ', '_')[:30]
                            state_name = f"hash_link_{safe_link_text}_{clicked_count}" if safe_link_text else f"hash_link_{clicked_count}"
                            
                            if self.save_page_state(url, state_name):
                                self.stats['dynamic_interactions'] += 1
                                clicked_count += 1
                                print(f"    Успешно нажата hash-ссылка: '{identifier['text']}'")
                            else:
                                print(f"    Состояние после hash-ссылки '{identifier['text']}' не сохранено")
                        else:
                            print(f"    Контент не изменился после клика на hash-ссылку '{identifier['text']}'")
                        
                    except Exception as e:
                        print(f"    Ошибка при клике на hash-ссылку: {e}")
                
                except Exception as e:
                    print(f"    Ошибка при обработке hash-ссылки {i}: {e}")
            
            print(f"  Всего нажато hash-ссылок: {clicked_count}")
            return clicked_count
        
        except Exception as e:
            print(f"  Ошибка при обработке hash-ссылок: {e}")
            return 0
    
    def click_show_more_buttons(self, url: str, state_prefix: str = ""):
        """Кликаем на все кнопки 'Подробнее' на текущей странице"""
        try:
            # Закрываем cookie-уведомление перед началом
            self.close_cookie_notice()
            
            # Ищем по разным вариантам текста
            show_more_xpaths = [
                "//button[contains(translate(., 'ПОДРОБНЕЕ', 'подробнее'), 'подробнее')]",
                "//a[contains(translate(., 'ПОДРОБНЕЕ', 'подробнее'), 'подробнее')]",
                "//span[contains(translate(., 'ПОДРОБНЕЕ', 'подробнее'), 'подробнее')]",
                "//div[contains(translate(., 'ПОДРОБНЕЕ', 'подробнее'), 'подробнее')]",
                "//*[contains(@class, 'more') and contains(translate(., 'ПОДРОБНЕЕ', 'подробнее'), 'подробнее')]",
                # Добавляем английские варианты
                "//button[contains(translate(., 'MORE', 'more'), 'more')]",
                "//a[contains(translate(., 'READ MORE', 'read more'), 'read more')]",
                "//*[contains(translate(., 'SHOW MORE', 'show more'), 'show more')]",
                # Добавляем другие русские варианты
                "//*[contains(translate(., 'РАЗВЕРНУТЬ', 'развернуть'), 'развернуть')]",
                "//*[contains(translate(., 'РАСКРЫТЬ', 'раскрыть'), 'раскрыть')]",
                "//*[contains(translate(., 'ЧИТАТЬ ДАЛЕЕ', 'читать далее'), 'читать далее')]"
            ]
            
            all_buttons = []
            for xpath in show_more_xpaths:
                try:
                    buttons = self.driver.find_elements(By.XPATH, xpath)
                    all_buttons.extend(buttons)
                except:
                    pass
            
            # Убираем дубликаты
            unique_buttons = []
            seen_elements = set()
            for btn in all_buttons:
                try:
                    element_id = btn.get_attribute('id') or ''
                    element_class = btn.get_attribute('class') or ''
                    element_text = btn.text[:30] if btn.text else ''
                    element_key = f"{element_id}_{element_class}_{element_text}"
                    
                    if element_key not in seen_elements:
                        seen_elements.add(element_key)
                        unique_buttons.append(btn)
                except:
                    pass
            
            if not unique_buttons:
                return 0
            
            print(f"    Найдено кнопок 'Подробнее': {len(unique_buttons)}")
            
            clicked_count = 0
            max_buttons_to_click = 8
            
            for i, button in enumerate(unique_buttons[:max_buttons_to_click]):
                try:
                    # Сохраняем состояние до клика
                    text_before = self.driver.find_element(By.TAG_NAME, 'body').text
                    
                    # Используем безопасный клик
                    click_success = self.safe_click_element(button)
                    
                    if not click_success:
                        print(f"      Не удалось кликнуть на кнопку 'Подробнее' {i}")
                        continue
                    
                    # Даем время на раскрытие контента
                    time.sleep(1.5)
                    
                    # Проверяем изменения
                    text_after = self.driver.find_element(By.TAG_NAME, 'body').text
                    if text_after != text_before:
                        state_name = f"{state_prefix}show_more_{clicked_count}" if state_prefix else f"show_more_{clicked_count}"
                        if self.save_page_state(url, state_name):
                            self.stats['dynamic_interactions'] += 1
                            clicked_count += 1
                            print(f"      Успешно нажата кнопка 'Подробнее' #{clicked_count}")
                    
                except Exception as e:
                    print(f"      Ошибка при клике на 'Подробнее': {e}")
            
            return clicked_count
        
        except Exception as e:
            print(f"    Ошибка при обработке кнопок 'Подробнее': {e}")
            return 0
    
    def click_prev_arrows(self, url: str):
        """Обрабатываем стрелки навигации назад (prev-arrow) и кнопки 'Подробнее' в каждом состоянии"""
        try:
            # Закрываем cookie-уведомление перед началом
            self.close_cookie_notice()
            
            # Ищем стрелки "назад" по разным возможным классам
            prev_arrow_selectors = [
                ".prev-arrow",
                ".slick-prev", 
                ".swiper-button-prev",
                ".carousel-prev", 
                ".arrow-prev",
                ".prev-button",
                ".button-prev",
                "[class*='prev']:not([class*='previous']):not([class*='preview'])",
                # Ищем по атрибутам aria-label
                "[aria-label*='prev']",
                "[aria-label*='previous']",
                "[aria-label*='назад']",
                "[aria-label*='предыдущ']",
                # Общие селекторы для навигации
                ".navigation-prev",
                ".nav-prev",
                ".control-prev"
            ]
            
            arrows = []
            for selector in prev_arrow_selectors:
                try:
                    found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if found:
                        arrows.extend(found)
                except:
                    pass
            
            # Убираем дубликаты
            unique_arrows = []
            seen_elements = set()
            for arrow in arrows:
                try:
                    element_id = f"{arrow.id}_{arrow.get_attribute('class')}"
                    if element_id not in seen_elements:
                        seen_elements.add(element_id)
                        unique_arrows.append(arrow)
                except:
                    pass
            
            if not unique_arrows:
                print("  Стрелки 'назад' не найдены")
                return 0
            
            print(f"  Найдено стрелок 'назад': {len(unique_arrows)}")
            
            # Ограничиваем количество кликов по стрелкам
            max_clicks = 20
            clicks_made = 0
            
            for click_num in range(max_clicks):
                try:
                    # Находим стрелки снова (DOM может измениться после предыдущих кликов)
                    current_arrows = []
                    for selector in prev_arrow_selectors:
                        try:
                            found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            current_arrows.extend(found)
                        except:
                            pass
                    
                    if not current_arrows:
                        print("    Больше нет стрелок для клика")
                        break
                    
                    # Берем первую доступную стрелку
                    arrow_to_click = None
                    for arrow in current_arrows:
                        try:
                            if arrow.is_displayed() and arrow.is_enabled():
                                arrow_to_click = arrow
                                break
                        except:
                            continue
                    
                    if not arrow_to_click:
                        print("    Нет видимых и активных стрелок")
                        break
                    
                    # Сохраняем состояние до клика
                    text_before = self.driver.find_element(By.TAG_NAME, 'body').text
                    
                    # Используем безопасный клик
                    click_success = self.safe_click_element(arrow_to_click)
                    
                    if not click_success:
                        print(f"    Не удалось кликнуть на стрелку")
                        break
                    
                    # Ждем загрузки нового контента
                    time.sleep(2.0)
                    
                    # Проверяем изменения
                    text_after = self.driver.find_element(By.TAG_NAME, 'body').text
                    if text_after != text_before:
                        # Сохраняем состояние после клика на стрелку
                        state_name = f"prev_arrow_{clicks_made}"
                        
                        if self.save_page_state(url, state_name):
                            print(f"    Сохранено состояние после стрелки #{clicks_made + 1}")
                            
                            # Ищем и нажимаем кнопки "Подробнее" в этом новом состоянии
                            more_prefix = f"prev_arrow_{clicks_made}_"
                            show_more_clicks = self.click_show_more_buttons(url, more_prefix)
                            if show_more_clicks > 0:
                                print(f"    Нажато {show_more_clicks} кнопок 'Подробнее' в этом состоянии")
                            
                            self.stats['dynamic_interactions'] += 1
                            clicks_made += 1
                            print(f"    Успешный клик на стрелку назад #{clicks_made}")
                        else:
                            print(f"    Состояние уже было сохранено ранее или не прошло проверку")
                            break
                    else:
                        print("    Контент не изменился после клика, прекращаем")
                        break
                        
                except Exception as e:
                    print(f"    Ошибка при клике на стрелку назад: {e}")
                    break
            
            print(f"  Всего выполнено кликов назад: {clicks_made}")
            return clicks_made
        
        except Exception as e:
            print(f"  Ошибка при обработке стрелок назад: {e}")
            return 0
    
    def click_common_dynamic_elements(self, url: str):
        """Кликаем на другие распространенные динамические элементы"""
        common_selectors = [
            '[role="tab"]:not([aria-selected="true"])',
            '[data-toggle="tab"]',
            '.accordion-header:not(.active)',
            '.collapse-trigger',
            '.tab-link:not(.active)',
            '[data-target*="collapse"]',
            '.expand-button',
            '.toggle-content',
            '.spoiler-title',
            '.spoiler-head',
            '[onclick*="show"]',
            '[onclick*="toggle"]'
        ]
        
        clicked_count = 0
        max_clicks = 10
        
        for selector in common_selectors:
            if clicked_count >= max_clicks:
                break
                
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for i, element in enumerate(elements):
                    if clicked_count >= max_clicks:
                        break
                        
                    try:
                        # Сохраняем состояние до клика
                        text_before = self.driver.find_element(By.TAG_NAME, 'body').text
                        
                        # Используем безопасный клик
                        click_success = self.safe_click_element(element)
                        
                        if not click_success:
                            continue
                        
                        # Ждем изменения
                        time.sleep(1.0)
                        
                        # Проверяем изменения
                        text_after = self.driver.find_element(By.TAG_NAME, 'body').text
                        if text_after != text_before:
                            selector_name = selector.replace('[', '').replace(']', '').replace('.', '').replace(':', '')
                            state_name = f"dynamic_{selector_name}_{i}"
                            
                            if self.save_page_state(url, state_name):
                                # После клика на динамический элемент тоже проверяем кнопки "Подробнее"
                                more_prefix = f"{state_name}_"
                                self.click_show_more_buttons(url, more_prefix)
                                self.stats['dynamic_interactions'] += 1
                                clicked_count += 1
                            
                    except:
                        pass
                        
            except:
                pass
        
        if clicked_count > 0:
            print(f"  Нажато других динамических элементов: {clicked_count}")
    
    def process_page_dynamic(self, url: str):
        """Обрабатывает страницу с динамическим контентом"""
        print(f"\nОбработка страницы: {url}")
        
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Даем время на загрузку динамического контента
            time.sleep(3)
            
            # Закрываем cookie-уведомление если есть
            self.close_cookie_notice()
            
            # Проверяем, не страница ли ошибки
            title = self.get_page_title()
            text = self.get_page_text()
            
            if self.is_error_page(title, text):
                print(f"  Страница с ошибкой, пропускаем: {title}")
                self.stats['skipped_errors'] += 1
                return None
            
            # Сохраняем исходное состояние
            if not self.save_page_state(url, "initial"):
                print("  Исходное состояние не сохранено (пустая или дубликат)")
            
            # 0. Обрабатываем hash-ссылки (href="#")
            print("  Обработка hash-ссылок (href='#'):")
            hash_clicks = self.click_hash_links(url)
            if hash_clicks > 0:
                print(f"  Нажато hash-ссылок: {hash_clicks}")
            
            # 1. В исходном состоянии ищем и нажимаем кнопки "Подробнее"
            print("  Обработка кнопок 'Подробнее' в исходном состоянии:")
            show_more_clicks = self.click_show_more_buttons(url, "initial_")
            if show_more_clicks > 0:
                print(f"  Нажато кнопок 'Подробнее' в исходном состоянии: {show_more_clicks}")
            
            # 2. Обрабатываем стрелки навигации назад
            print("  Обработка стрелок навигации назад:")
            arrow_clicks = self.click_prev_arrows(url)
            
            # 3. Обрабатываем другие динамические элементы
            print("  Обработка других динамических элементов:")
            self.click_common_dynamic_elements(url)
            
            # Получаем HTML для извлечения ссылок
            html_content = self.driver.page_source
            
            self.stats['total_pages'] += 1
            print(f"  Обработка страницы завершена. Всего взаимодействий: {self.stats['dynamic_interactions']}")
            return html_content
            
        except TimeoutException:
            print(f"  Таймаут при загрузке страницы: {url}")
            return None
        except Exception as e:
            print(f"  Ошибка при обработке страницы {url}: {e}")
            return None
    
    def crawl(self):
        """Основной метод обхода сайта"""
        print(f"Начало обхода сайта: {self.start_url}")
        print(f"Максимальная глубина: {self.max_depth}")
        print(f"Домен: {self.domain}")
        print("-" * 60)
        
        # Очередь для BFS обхода: (url, depth)
        queue = deque([(self.start_url, 1)])
        self.visited_urls.add(self.start_url)
        
        while queue:
            current_url, depth = queue.popleft()
            
            print(f"\n{'='*40}")
            print(f"Уровень {depth}: {current_url}")
            print(f"{'='*40}")
            
            # Обрабатываем страницу с динамическим контентом
            html_content = self.process_page_dynamic(current_url)
            
            # Если достигли максимальной глубины, не извлекаем ссылки
            if depth >= self.max_depth or not html_content:
                continue
            
            # Извлекаем ссылки для следующего уровня
            links = self.extract_links_statically(html_content, current_url)
            
            new_links_count = 0
            for link in links:
                if link not in self.visited_urls:
                    self.visited_urls.add(link)
                    queue.append((link, depth + 1))
                    new_links_count += 1
            
            if new_links_count > 0:
                print(f"  Добавлено {new_links_count} новых ссылок для следующего уровня")
        
        print("\n" + "=" * 60)
        print("Обход завершен!")
        
        # Сохраняем данные
        self.save_to_csv()
        
        # Закрываем драйвер
        self.driver.quit()
        
        return self.data


# Основная функция для запуска
def main():
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))  # Папка src
    project_root = os.path.dirname(script_dir)               # Корень проекта
    data_dir = os.path.join(project_root, "data")            # Папка data
    
    START_URL = "https://www.neoflex.ru"
    MAX_DEPTH = 3
    OUTPUT_FILE = os.path.join(data_dir, "crawled_data.csv")
    
    print("Выберите метод обхода:")
    print("1. SmartWebCrawler (для сайтов с JavaScript - РЕКОМЕНДУЕТСЯ)")
    print("2. Тестовый режим (только главная страница)")
    
    choice = input("Введите 1 или 2: ").strip()
    
    if choice == "1":
        # Используем SmartWebCrawler для динамических сайтов
        crawler = SmartWebCrawler(
            start_url=START_URL,
            max_depth=MAX_DEPTH,
            output_file=OUTPUT_FILE
        )
        
        try:
            data = crawler.crawl()
            print(f"\nСобрано {len(data)} уникальных состояний страниц")
            print(f"Статистика взаимодействий: {crawler.stats['dynamic_interactions']}")
        except KeyboardInterrupt:
            print("\nОбход прерван пользователем")
            if 'crawler' in locals():
                crawler.save_to_csv()
                crawler.driver.quit()
        except Exception as e:
            print(f"\nКритическая ошибка: {e}")
            if 'crawler' in locals():
                crawler.save_to_csv()
                crawler.driver.quit()
    
    elif choice == "2":
        # Тестовый режим - только главная страница
        test_output_file = os.path.join(data_dir, "test_output.csv")
        print(f"Тестовый режим: обработка только главной страницы {START_URL}")
        crawler = SmartWebCrawler(
            start_url=START_URL,
            max_depth=1,  # Только первая страница
            output_file=test_output_file
        )
        try:
            data = crawler.crawl()
            print(f"\nСобрано {len(data)} состояний главной страницы")
            
            # Показать первые 5 состояний
            print("\nПервые 5 состояний:")
            for i, item in enumerate(data[:5]):
                print(f"\n{i+1}. URL: {item['url']}")
                print(f"   Состояние: {item['state']}")
                print(f"   Заголовок: {item['title']}")
                print(f"   Длина текста: {len(item['text'])} символов")
                print(f"   Начало текста: {item['text'][:150]}...")
        except Exception as e:
            print(f"Ошибка: {e}")
    
    else:
        print("Неверный выбор. Завершение работы.")

if __name__ == "__main__":
    main()