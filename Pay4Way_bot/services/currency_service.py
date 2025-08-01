import requests
import json
import time
from typing import Optional, Dict
import logging

class CurrencyService:
    """Сервис для получения актуального курса валют"""
    
    def __init__(self):
        self.cache = {}
        self.cache_timeout = 3600  # 1 час
        self.last_update = 0
        
    def get_exchange_rate(self, from_currency: str = "EUR", to_currency: str = "RUB") -> Optional[float]:
        """
        Получает актуальный курс валют
        
        Args:
            from_currency: Исходная валюта (по умолчанию EUR)
            to_currency: Целевая валюта (по умолчанию RUB)
            
        Returns:
            Курс валют или None в случае ошибки
        """
        cache_key = f"{from_currency}_{to_currency}"
        current_time = time.time()
        
        # Проверяем кэш
        if cache_key in self.cache and (current_time - self.last_update) < self.cache_timeout:
            return self.cache[cache_key] * 1.035
        
        try:
            # Используем бесплi.exchangerate-apатный API exchangerate-api.com
            url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                rate = data['rates'].get(to_currency)
                
                if rate:
                    # Обновляем кэш
                    self.cache[cache_key] = rate
                    self.last_update = current_time
                    return rate * 1.035
                else:
                    logging.error(f"Курс {from_currency}/{to_currency} не найден в ответе API")
                    return None
            else:
                logging.error(f"Ошибка API: {response.status_code}")
                return None
                
        except Exception as e:
            logging.error(f"Ошибка при получении курса валют: {e}")
            return None
    

    
    def convert_price(self, price: float, from_currency: str = "EUR", to_currency: str = "RUB") -> Optional[float]:
        """
        Конвертирует цену из одной валюты в другую
        
        Args:
            price: Цена для конвертации
            from_currency: Исходная валюта
            to_currency: Целевая валюта
            
        Returns:
            Конвертированная цена или None в случае ошибки
        """
        rate = self.get_exchange_rate(from_currency, to_currency)
        if rate:
            return price * rate
        return None
    
    def format_price_rub(self, price_eur: float) -> str:
        """
        Форматирует цену в рублях с курсом
        
        Args:
            price_eur: Цена в евро
            
        Returns:
            Отформатированная строка с ценой в рублях или только в евро, если курс недоступен
        """
        price_rub = self.convert_price(price_eur, "EUR", "RUB")
        if price_rub:
            return f"€{price_eur:.2f} (≈ {price_rub:.0f} ₽)"
        else:
            return f"€{price_eur:.2f}"
    
    def get_currency_info(self) -> Dict:
        """
        Возвращает информацию о курсах валют
        
        Returns:
            Словарь с информацией о курсах
        """
        eur_rub = self.get_exchange_rate("EUR", "RUB")
        usd_rub = self.get_exchange_rate("USD", "RUB")
        
        return {
            "EUR_RUB": eur_rub,
            "USD_RUB": usd_rub,
            "last_update": self.last_update,
            "cache_valid": (time.time() - self.last_update) < self.cache_timeout
        }

# Глобальный экземпляр сервиса
currency_service = CurrencyService() 