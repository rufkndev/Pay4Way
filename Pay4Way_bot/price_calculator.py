"""
Модуль для расчета цен товаров в корзине
"""

# Константы для типов доставки и их цен
DELIVERY_TYPES = {
    # "small_package": {
    #     "name": "Маленький пакет",
    #     "weights": {
    #         1: 12.94,
    #         2: 18.5
    #     }
    # },
    # "standard_package": {
    #     "name": "Стандартный пакет", 
    #     "weights": {
    #         1: 19.04, 2: 22.69, 3: 24.23, 4: 26.16, 5: 27.7, 6: 29.24, 7: 30.78, 8: 32.78,
    #         9: 34.32, 10: 35.86, 11: 31.45, 12: 32.99, 13: 34.53, 14: 36.07, 15: 37.61,
    #         16: 39.15, 17: 40.69, 18: 42.23, 19: 43.77, 20: 45.31
    #     }
    # },
    "ems": {
        "name": "EMS",
        "weights": {
            0.5: 15.69, 1: 17.39, 1.5: 21.65, 2: 23.35, 2.5: 25.5, 3: 27.2, 3.5: 29.74,
            4: 31.44, 4.5: 33.59, 5: 35.29, 5.5: 37.44, 6: 39.14, 6.5: 41.29, 7: 42.99,
            7.5: 45.14, 8: 46.84
        }
    }
}

def calculate_item_price(original_price: float, delivery_type: str, weight: float, with_vat: bool = True) -> float:
    """
    Рассчитывает цену товара по формуле:
    (Шаг 4 + Шаг 5 + Шаг 6) = (сумма после добавления доставки) + (сумма после добавления доставки * 0,15) + (цена товара без НДС + комиссия сервиса) * 0.03
    
    Args:
        original_price (float): Цена товара из Google Shopping
        delivery_type (str): Тип доставки ('ems')
        weight (float): Вес товара в кг
        with_vat (bool): С НДС или без НДС
        
    Returns:
        float: Рассчитанная цена товара
    """
    try:
        # Извлекаем числовое значение цены
        original_price_clean = extract_price_value(original_price)
        if original_price_clean is None:
            return 0.0
        # Получаем стоимость доставки для выбранного типа и веса
        delivery_cost = get_delivery_cost(delivery_type, weight)
        if delivery_cost is None:
            return 0.0
        # Цена без НДС (19%)
        price_without_vat = original_price_clean - (original_price_clean * 0.19)
        # Складываем доставку и цену без НДС
        step3 = price_without_vat
        # Добавляем стоимость доставки до РФ
        step4 = step3 + delivery_cost
        # Комиссия сервиса (15%)
        step5 = step4 * 0.15
        # Страховой сбор (3% от цены товара без НДС + комиссии сервиса, но НЕ от доставки)
        step6 = (price_without_vat + step5) * 0.03
        # Финальный расчет: Шаг 4 + Шаг 5 + Шаг 6
        calculated_price = step4 + step5 + step6
        # Если нужно без НДС, убираем НДС (20%)
        if not with_vat:
            calculated_price = calculated_price / 1.20
        return round(calculated_price, 2)
    except Exception as e:
        print(f"Ошибка при расчете цены: {e}")
        return 0.0


def extract_price_value(price_input) -> float:
    """
    Извлекает числовое значение из строки цены
    
    Args:
        price_input: Цена в любом формате (строка, число, с символами валют)
        
    Returns:
        float: Числовое значение цены или None если не удалось извлечь
    """
    try:
        if isinstance(price_input, (int, float)):
            return float(price_input)
        
        price_str = str(price_input)
        # Убираем символы валют и пробелы
        price_str = price_str.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
        # Убираем все нечисловые символы кроме точки
        price_clean = ''.join(c for c in price_str if c.isdigit() or c == '.')
        
        if price_clean:
            return float(price_clean)
        return None
        
    except (ValueError, TypeError):
        return None


def get_delivery_cost(delivery_type: str, weight: float) -> float:
    """
    Получает стоимость доставки для указанного типа и веса
    
    Args:
        delivery_type (str): Тип доставки
        weight (float): Вес в кг
        
    Returns:
        float: Стоимость доставки или None если не найдено
    """
    if delivery_type not in DELIVERY_TYPES:
        return None
    
    weights = DELIVERY_TYPES[delivery_type]["weights"]
    return weights.get(weight, None)


def get_available_weights(delivery_type: str) -> list:
    """
    Получает список доступных весов для указанного типа доставки
    
    Args:
        delivery_type (str): Тип доставки
        
    Returns:
        list: Список доступных весов
    """
    if delivery_type not in DELIVERY_TYPES:
        return []
    
    return list(DELIVERY_TYPES[delivery_type]["weights"].keys())


def get_delivery_type_name(delivery_type: str) -> str:
    """
    Получает название типа доставки
    
    Args:
        delivery_type (str): Тип доставки
        
    Returns:
        str: Название типа доставки
    """
    if delivery_type not in DELIVERY_TYPES:
        return "Неизвестный тип"
    
    return DELIVERY_TYPES[delivery_type]["name"]


def calculate_cart_total(original_price: float, delivery_type: str, weight: float, with_vat: bool = True) -> dict:
    """
    Рассчитывает общую сумму корзины для одного товара (или для одной цены)
    Args:
        original_price (float): Цена товара
        delivery_type (str): Тип доставки
        weight (float): Вес товара в кг
        with_vat (bool): С НДС или без НДС
    Returns:
        dict: Словарь с результатами расчета включая страховой сбор
    """
    price_with_vat = calculate_item_price(original_price, delivery_type, weight, True)
    price_without_vat = calculate_item_price(original_price, delivery_type, weight, False)
    delivery_cost = get_delivery_cost(delivery_type, weight)
    
    # Рассчитываем отдельно каждую составляющую
    original_price_clean = extract_price_value(original_price)
    item_price_without_vat = original_price_clean - (original_price_clean * 0.19)
    service_fee = (item_price_without_vat + delivery_cost) * 0.15
    insurance_fee = (item_price_without_vat + service_fee) * 0.03
    
    savings = price_with_vat - price_without_vat
    return {
        'total': price_with_vat,
        'service_fee': service_fee,
        'insurance_fee': insurance_fee,
        'savings': savings,
        'delivery_cost': delivery_cost
    }


def format_price_display(price: float, currency: str = "€") -> str:
    """
    Форматирует цену для отображения
    
    Args:
        price (float): Цена
        currency (str): Символ валюты
        
    Returns:
        str: Отформатированная цена
    """
    return f"{currency}{price:.2f}"


def get_detailed_price_breakdown(cart_items: list, delivery_type: str, weight: float) -> str:
    """
    Возвращает детальную разбивку цен для пользователя
    
    Args:
        cart_items (list): Товары в корзине
        delivery_type (str): Тип доставки
        weight (float): Вес товара в кг
        
    Returns:
        str: Детальная разбивка цен
    """
    if not cart_items:
        return "🛒 Корзина пуста"
    
    calculation_result = calculate_cart_total(cart_items[0]['price'], delivery_type, weight)
    delivery_type_name = get_delivery_type_name(delivery_type)
    delivery_cost = calculation_result['delivery_cost']
    service_commission = calculation_result['service_fee']
    insurance_fee = calculation_result['insurance_fee']
    
    # Рассчитываем общую стоимость товаров без НДС
    total_original_price = sum(extract_price_value(item.get('price', 0)) or 0 for item in cart_items)
    total_price_without_vat = total_original_price - (total_original_price * 0.19)
    
    breakdown = f"""
📊 **Ваш заказ:**

🛍️ **Товары в корзине ({len(cart_items)} шт.):**
   💰 Общая стоимость: €{total_original_price:.2f} за вычетом НДС (А могла быть €{total_original_price:.2f} с НДС)

🚚 **Доставка из Германии до РФ:**
   📦 Тип: {delivery_type_name}
   ⚖️ Вес: {weight} кг
   💶 Стоимость доставки: €{delivery_cost:.2f}

💼 **Комиссия сервиса (15%):** €{service_commission:.2f}

🛡️ **Страховой сбор (3%):** €{insurance_fee:.2f}

💰 **ИТОГО: {format_price_display(calculation_result['total'])}**
"""
    
    return breakdown 