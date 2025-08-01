import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json
import logging
from typing import Dict, Any

class GoogleSheetsService:
    def __init__(self):
        logging.info("Инициализация GoogleSheetsService...")
        
        # Настройка аутентификации
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Путь к JSON файлу с сервисным аккаунтом
        json_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pay4way.json')
        logging.info(f"Путь к JSON файлу: {json_file_path}")
        
        # Проверяем существование файла
        if not os.path.exists(json_file_path):
            raise FileNotFoundError(f"JSON файл не найден: {json_file_path}")
        
        # Загружаем JSON файл
        try:
            with open(json_file_path, 'r') as f:
                service_account_data = json.load(f)
            logging.info("JSON файл загружен успешно")
        except Exception as e:
            logging.error(f"Ошибка загрузки JSON файла: {e}")
            raise
        
        try:
            credentials = Credentials.from_service_account_file(json_file_path, scopes=scope)
            self.client = gspread.authorize(credentials)
            logging.info("Аутентификация в Google Sheets успешна")
        except Exception as e:
            logging.error(f"Ошибка аутентификации: {e}")
            raise
        
        # ID таблицы из JSON файла или переменной окружения
        self.spreadsheet_id = service_account_data.get('spreadsheet_id') or os.getenv('GOOGLE_SHEETS_ID', 'your_spreadsheet_id_here')
        logging.info(f"ID таблицы: {self.spreadsheet_id}")
        
        # Проверяем, есть ли ID таблицы
        if not self.spreadsheet_id or self.spreadsheet_id == 'your_spreadsheet_id_here':
            raise ValueError("Не найден ID таблицы Google Sheets. Добавьте 'spreadsheet_id' в JSON файл сервисного аккаунта или установите переменную GOOGLE_SHEETS_ID в .env")
        
        logging.info("GoogleSheetsService инициализирован успешно")
        
    def add_order(self, order_data: Dict[str, Any]) -> bool:
        """
        Добавляет заказ в Google таблицу
        
        Args:
            order_data: Словарь с данными заказа
            
        Returns:
            bool: True если успешно, False если ошибка
        """
        try:
            # Открываем таблицу
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.sheet1
            
            # Используем order_id из order_data, если он есть, иначе генерируем новый
            order_id = order_data.get('order_id', int(datetime.now().timestamp()))
            
            # Получаем текущую дату
            current_date = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            # Получаем товары из заказа
            cart_items = order_data.get('cart_items', [])
            
            # Формируем строку с товарами и ссылками
            items_info = []
            for i, item in enumerate(cart_items, 1):
                title = item.get('title', 'Название не указано')
                shipping = item.get('shipping', 'Доставка не указана')
                price = item.get('price', 'Цена не указана')
                link = item.get('link', 'Ссылка не указана')
                source = item.get('source', 'Магазин не указан')
                
                items_info.append(f"{i}. {title} - {price} ({source})")
            
            items_text = "\n".join(items_info) if items_info else "Товары не указаны"
            
            # Формируем строку со ссылками на товары
            links_info = []
            for i, item in enumerate(cart_items, 1):
                link = item.get('link', '')
                if link:
                    links_info.append(f"{i}. {link}")
            
            links_text = "\n".join(links_info) if links_info else "Ссылки не указаны"
            
            # Подготавливаем данные для записи
            row_data = [
                order_id,  # ID заказа
                current_date,  # Дата
                order_data.get('full_name', ''),  # Имя и Фамилия
                order_data.get('phone', ''),  # Телефон
                order_data.get('email', ''),  # Email
                order_data.get('address', ''),  # Адрес
                order_data.get('comment', ''),  # Комментарий
                order_data.get('total_amount', ''),  # Общая сумма
                order_data.get('items_count', ''),  # Количество товаров
                items_text,  # Список товаров
                links_text,  # Ссылки на товары
                order_data.get('telegram_id', ''),  # Telegram ID пользователя
                order_data.get('username', '')  # Username пользователя
            ]
            
            # Добавляем строку в таблицу
            worksheet.append_row(row_data)
            
            return True
            
        except Exception as e:
            print(f"Ошибка при записи в Google Sheets: {str(e)}")
            return False
    
    def get_orders_count(self) -> int:
        """
        Получает количество заказов в таблице
        
        Returns:
            int: Количество заказов
        """
        try:
            spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.sheet1
            
            # Получаем все значения
            all_values = worksheet.get_all_values()
            
            # Возвращаем количество строк (минус заголовок)
            return len(all_values) - 1 if len(all_values) > 1 else 0
            
        except Exception as e:
            print(f"Ошибка при получении количества заказов: {str(e)}")
            return 0 