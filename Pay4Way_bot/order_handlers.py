# order_handlers.py

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards import get_cart_reply_keyboard, get_main_reply_keyboard
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import urllib.parse
from price_calculator import calculate_cart_total, format_price_display
from formatting_utils import format_total_with_savings, format_price_with_rub
from services.currency_service import currency_service

# Загружаем переменные окружения
load_dotenv()

# Состояния для оформления заказа
class OrderStates(StatesGroup):
    waiting_for_name = State()      # Ожидание ввода ФИО
    waiting_for_phone = State()     # Ожидание ввода телефона
    waiting_for_email = State()     # Ожидание ввода email
    waiting_for_address = State()   # Ожидание ввода адреса
    waiting_for_confirmation = State()  # Ожидание подтверждения данных

# Функции-обработчики (будут зарегистрированы в основном файле)

async def process_name(message: types.Message, state: FSMContext):
    """Обработчик ввода ФИО"""
    name = message.text
    await state.update_data(name=name)
    await message.answer("📱 Пожалуйста, введите номер телефона в формате 79998887766:")
    await state.set_state(OrderStates.waiting_for_phone)

async def process_phone_number(message: types.Message, state: FSMContext):
    """Обработчик ввода телефона"""
    phone_number = message.text
    await state.update_data(phone_number=phone_number)
    await message.answer("📧 Пожалуйста, введите ваш email:")
    await state.set_state(OrderStates.waiting_for_email)

async def process_email(message: types.Message, state: FSMContext):
    """Обработчик ввода email"""
    email = message.text
    await state.update_data(email=email)
    await message.answer("📍 Пожалуйста, введите ваш адрес для доставки в Россию в следующем формате: индекс, город, улица, дом, квартира")
    await state.set_state(OrderStates.waiting_for_address)

async def process_address(message: types.Message, state: FSMContext):
    """Обработчик ввода адреса"""
    address = message.text
    await state.update_data(address=address)
    # После адреса сразу показываем сводку и подтверждение
    order_data = await state.get_data()
    cart_items = order_data.get('cart', [])
    if not cart_items:
        await message.answer("❌ Ошибка: корзина пуста!")
        return
    # Получаем данные из первого товара в корзине (они должны быть одинаковыми для всех товаров)
    first_product = cart_items[0]
    delivery_type_code = first_product.get('delivery_type_code', 'small_package')  # Используем код для расчетов
    delivery_type_name = first_product.get('delivery_type', 'Маленький пакет')  # Используем название для отображения
    weight = first_product.get('weight', 1.0)
    from price_calculator import get_delivery_type_name, format_price_display, get_delivery_cost
    from formatting_utils import format_price_with_rub, format_total_with_savings
    delivery_cost_to_warehouse = 5.00  # Фиксированная стоимость
    delivery_cost_from_germany = get_delivery_cost(delivery_type_code, weight)
    order_summary = f"""
**Проверьте данные заказа:**

👤 **ФИО:** {order_data.get('name', 'Не указано')}
📱 **Телефон:** {order_data.get('phone_number', 'Не указано')}
📧 **Email:** {order_data.get('email', 'Не указано')}
📍 **Адрес:** {order_data.get('address', 'Не указано')}
━━━━━
🛍 **Товары в корзине ({len(cart_items)} шт.):**
"""
    total_products_without_vat = 0
    total_products_with_vat = 0
    for i, product in enumerate(cart_items, 1):
        price_without_vat = product.get('original_price_without_vat', 0)
        price_with_vat = product.get('original_price', 0)
        if price_without_vat == 0 or price_with_vat == 0:
            price = product.get('price', 0)
            if isinstance(price, str):
                price = price.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
            try:
                price_with_vat = float(price)
                price_without_vat = round(price_with_vat * 0.81, 2)
            except Exception:
                price_with_vat = 0.0
                price_without_vat = 0.0
        total_products_without_vat += price_without_vat
        total_products_with_vat += price_with_vat
        order_summary += f"{i}. **{product['title']}**\n"
        order_summary += f"   💶 Цена: {format_price_with_rub(price_without_vat)} без НДС \n"
        if product.get('link'):
            order_summary += f"   🔗 Ссылка: {product['link']}"
        # Добавляем перевод строки только если это не последний товар
        if i < len(cart_items):
            order_summary += "\n"
    subtotal = total_products_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
    service_commission = round(subtotal * 0.15, 2)
    total_cost = round(subtotal + service_commission, 2)
    savings = total_products_with_vat - total_products_without_vat
    
    # Вычисляем конвертации валют заранее
    rub_total_products = currency_service.convert_price(total_products_without_vat)
    rub_delivery_to_warehouse = currency_service.convert_price(delivery_cost_to_warehouse)
    rub_delivery_from_germany = currency_service.convert_price(delivery_cost_from_germany)
    rub_service_commission = currency_service.convert_price(service_commission)
    rub_total_cost = currency_service.convert_price(total_cost)
    rub_savings = currency_service.convert_price(savings)
    
    order_summary += f"""
━━━━━
**ИТОГО:**

🪙 **Стоимость товаров:** {total_products_without_vat} € или {f'{rub_total_products:,.0f}'.replace(',', ' ')} ₽

🚚 **Стоимость доставки от интернет-магазина до нашего склада в германии:** {delivery_cost_to_warehouse} € или {f'{rub_delivery_to_warehouse:,.0f}'.replace(',', ' ')} ₽

📦 **Доставка из Германии до РФ:**
   Тип: {delivery_type_name}
   Вес: {weight} кг
   Стоимость доставки: {delivery_cost_from_germany} € или {f'{rub_delivery_from_germany:,.0f}'.replace(',', ' ')} ₽

💼 **Комиссия сервиса (15%):** {service_commission} € или {f'{rub_service_commission:,.0f}'.replace(',', ' ')} ₽

💶 **ИТОГО:** {total_cost} или {f'{rub_total_cost:,.0f}'.replace(',', ' ')} ₽

*Экономия состовляет {savings:.2f} € или {f'{rub_savings:,.0f}'.replace(',', ' ')} ₽*

Всё верно?
"""
    from keyboards import get_order_confirmation_keyboard
    confirmation_keyboard = get_order_confirmation_keyboard()
    await message.answer(order_summary, parse_mode="Markdown", reply_markup=confirmation_keyboard)
    await state.set_state(OrderStates.waiting_for_confirmation)

async def confirm_order_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик подтверждения заказа"""
    await callback.answer()
    
    logging.info(f"Начало обработки подтверждения заказа для пользователя {callback.from_user.id}")
    
    # Получаем данные заказа
    order_data = await state.get_data()
    logging.info(f"Получены данные заказа: {list(order_data.keys())}")
    
    # Получаем информацию о пользователе
    user_info = {
        'user_id': callback.from_user.id,
        'username': callback.from_user.username,
        'first_name': callback.from_user.first_name,
        'last_name': callback.from_user.last_name
    }
    logging.info(f"Информация о пользователе: {user_info}")
    
    # Получаем товары из корзины
    cart_items = order_data.get('cart', [])
    logging.info(f"Товаров в корзине: {len(cart_items)}")
    
    # Логируем комментарии из товаров
    for i, product in enumerate(cart_items):
        logging.info(f"Товар {i+1}: {product.get('title', 'Без названия')}")
        logging.info(f"  - product_features: {product.get('product_features', 'НЕТ')}")
    
    if not cart_items:
        logging.error("Корзина пуста при подтверждении заказа")
        await callback.message.answer("❌ Ошибка: корзина пуста!")
        return
    
    # Генерируем order_id
    order_id = int(datetime.now().timestamp())
    
    # Собираем комментарии из товаров корзины
    product_comments = []
    for product in cart_items:
        if product.get('product_features'):
            product_comments.append(product['product_features'])
    
    # Объединяем комментарии
    combined_comment = '; '.join(product_comments) if product_comments else ''
    logging.info(f"Собранные комментарии: {combined_comment}")
    
    # Сохраняем заказ
    logging.info("Начинаем процесс сохранения заказа")
    success = await process_order_completion(order_data, user_info, cart_items, order_id, combined_comment)
    logging.info(f"Результат сохранения заказа: {success}")
    
    if success:
        logging.info("Заказ успешно обработан, отправляем финальное сообщение")
        final_message = f"""
✅ Заказ успешно оформлен! ✅

Ваш ID заказа: {order_id}

Нам потребуется немного времени, чтобы проверить указанные данные.

🧑‍💻 Наш менеджер напишет Вам в ближайшее время для уточнения деталей и подтверждения заказа.

Если у вас есть срочные вопросы, можете связаться с нами:
• Telegram: @pay4way_admin
• Email: support@pay4way.com

Спасибо за доверие, ваш Pay4Way! 🚀
"""

        
        await callback.message.answer(final_message)
        # Очищаем корзину и состояние после успешного заказа
        await state.update_data(cart=[])
        await state.clear()
        # Показываем главное меню
        from keyboards import get_main_reply_keyboard
        await callback.message.answer("🏠 Главное меню:", reply_markup=get_main_reply_keyboard())
        logging.info("Заказ полностью завершен успешно")
    else:
        logging.error("Ошибка при обработке заказа, отправляем сообщение об ошибке")
        await callback.message.answer(
            "❌ Произошла ошибка при оформлении заказа. Попробуйте позже или обратитесь в поддержку."
        )

async def restart_order(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик нажатия кнопки 'Нет, заполнить заново'"""
    await callback.answer()  # Убираем "часики" у кнопки
    
    await callback.message.answer("Хорошо, давайте заполним заказ заново!")
    await callback.message.answer("Пожалуйста, введите ФИО полностью как в паспорте (например Иванов Иван Иванович):")
    
    # Очищаем только данные заказа, но сохраняем корзину
    await state.update_data(name=None, phone_number=None, email=None, address=None)
    await state.set_state(OrderStates.waiting_for_name)

async def save_order_to_sheets(order_data: dict, user_info: dict, order_id: int = None, calculation_comment: str = '') -> bool:
    """
    Сохраняет заказ в Google Sheets
    
    Args:
        order_data: Данные заказа
        user_info: Информация о пользователе
        order_id: ID заказа (timestamp)
        calculation_comment: комментарий пользователя из расчёта
        
    Returns:
        bool: True если успешно сохранено
    """
    try:
        from services.google_sheets_service import GoogleSheetsService
        
        # Создаем экземпляр сервиса
        sheets_service = GoogleSheetsService()
        
        # Получаем товары из корзины для подсчета общей суммы
        cart_items = order_data.get('cart', [])
        
        if not cart_items:
            logging.error("Корзина пуста при сохранении в Google Sheets")
            return False
        
        # Собираем комментарии из всех товаров в корзине
        product_comments = []
        for product in cart_items:
            if product.get('product_features'):
                product_comments.append(product['product_features'])
        
        # Объединяем все комментарии в одну строку
        combined_comment = '; '.join(product_comments) if product_comments else calculation_comment
        
        logging.info(f"Обработка комментариев в save_order_to_sheets:")
        logging.info(f"  - product_comments: {product_comments}")
        logging.info(f"  - calculation_comment: {calculation_comment}")
        logging.info(f"  - combined_comment: {combined_comment}")
        
        # Получаем данные из первого товара в корзине
        first_product = cart_items[0]
        delivery_type_code = first_product.get('delivery_type_code', 'small_package')
        weight = first_product.get('weight', 1.0)
        payment_method = order_data.get('payment_method', 'card')
        
        # Рассчитываем цены по нашей формуле
        from price_calculator import calculate_cart_total, get_delivery_type_name, get_delivery_cost
        calculation_result = calculate_cart_total(cart_items, delivery_type_code, weight)
        delivery_type_name = first_product.get('delivery_type', 'Маленький пакет')  # Используем название из корзины
        payment_method_name = "Карта иностранного банка" if payment_method == "card" else "Криптовалюта"
        
        # Рассчитываем итоговые суммы
        total_products_without_vat = sum(product.get('original_price_without_vat', 0) for product in cart_items)
        total_products_with_vat = sum(product.get('original_price', 0) for product in cart_items)
        delivery_cost_to_warehouse = 5.00
        delivery_cost_from_germany = get_delivery_cost(delivery_type_code, weight)
        subtotal = total_products_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
        service_commission = round(subtotal * 0.15, 2)
        total_cost = round(subtotal + service_commission, 2)
        
        # Формируем строку с общей суммой
        total_amount_str = f"С НДС: €{total_products_with_vat:.2f}, Без НДС: €{total_products_without_vat:.2f} (Тип: {delivery_type_name}, Вес: {weight} кг)"
        
        # Подготавливаем данные для Google Sheets
        sheets_order_data = {
            'order_id': order_id if order_id else '',
            'full_name': order_data.get('name', ''),
            'phone': order_data.get('phone_number', ''),
            'email': order_data.get('email', ''),
            'address': order_data.get('address', ''),
            'comment': combined_comment,  # Используем объединённый комментарий
            'total_amount': total_amount_str,
            'items_count': len(cart_items),
            'cart_items': cart_items,  # Передаем оригинальные товары из корзины
            'telegram_id': user_info.get('user_id', ''),
            'username': user_info.get('username', ''),
            'delivery_type': delivery_type_name,
            'weight': f"{weight} кг",
            'payment_method': payment_method_name,
            'delivery_cost': f"€{delivery_cost_from_germany:.2f}",
            'service_commission': f"€{service_commission:.2f}",
            'total_cost': f"€{total_cost:.2f}"
        }
        
        # Сохраняем в Google Sheets
        success = sheets_service.add_order(sheets_order_data)
        
        if success:
            logging.info(f"Заказ успешно сохранен в Google Sheets для пользователя {user_info.get('user_id')}")
        else:
            logging.error(f"Не удалось сохранить заказ в Google Sheets для пользователя {user_info.get('user_id')}")
        
        return success
        
    except Exception as e:
        logging.error(f"Ошибка сохранения в Google Sheets: {e}")
        return False

async def send_order_to_manager(order_data: dict, user_info: dict, cart_items: list) -> bool:
    """
    Отправляет уведомление о заказе менеджеру
    
    Args:
        order_data: Данные заказа
        user_info: Информация о пользователе
        cart_items: Товары в корзине
        
    Returns:
        bool: True если успешно отправлено
    """
    try:
        # Захардкоженный ID менеджера
        manager_id = "7197183698"
        
        if not cart_items:
            logging.error("Корзина пуста при отправке уведомления менеджеру")
            return False
        
        # Собираем комментарии из всех товаров в корзине
        product_comments = []
        for product in cart_items:
            if product.get('product_features'):
                product_comments.append(product['product_features'])
        
        # Объединяем все комментарии в одну строку
        combined_comment = '; '.join(product_comments) if product_comments else 'Не указано'
        
        # Получаем данные из первого товара в корзине
        first_product = cart_items[0]
        delivery_type_code = first_product.get('delivery_type_code', 'small_package')
        weight = first_product.get('weight', 1.0)
        payment_method = order_data.get('payment_method', 'card')
        
        # Рассчитываем цены
        from price_calculator import get_delivery_type_name, get_delivery_cost, format_price_display
        from formatting_utils import format_price_with_rub
        
        delivery_type_name = first_product.get('delivery_type', 'Маленький пакет')  # Используем название из корзины
        delivery_cost_to_warehouse = 5.00
        delivery_cost_from_germany = get_delivery_cost(delivery_type_code, weight)
        payment_method_name = "Карта иностранного банка" if payment_method == "card" else "Криптовалюта"
        
        # Рассчитываем итоговые суммы
        total_products_without_vat = sum(product.get('original_price_without_vat', 0) for product in cart_items)
        total_products_with_vat = sum(product.get('original_price', 0) for product in cart_items)
        subtotal = total_products_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
        service_commission = round(subtotal * 0.15, 2)
        total_cost = round(subtotal + service_commission, 2)
        
        # Формируем сообщение для менеджера
        manager_message = f"""
🆕 **НОВЫЙ ЗАКАЗ!**

👤 **Клиент:**
• ФИО: {order_data.get('name', 'Не указано')}
• Телефон: {order_data.get('phone_number', 'Не указано')}
• Email: {order_data.get('email', 'Не указано')}
• Адрес: {order_data.get('address', 'Не указано')}
• Комментарий: {combined_comment}

📦 **Доставка:**
• Тип: {delivery_type_name}
• Вес: {weight} кг
• Стоимость доставки до склада: €{delivery_cost_to_warehouse:.2f}
• Стоимость доставки из Германии: €{delivery_cost_from_germany:.2f}

💳 **Способ оплаты:** {payment_method_name}

👤 **Информация о пользователе:**
• ID: {user_info.get('user_id', 'Не указано')}
• Username: @{user_info.get('username', 'Не указано')}
• Имя: {user_info.get('first_name', 'Не указано')}
• Фамилия: {user_info.get('last_name', 'Не указано')}

🛒 **Товары в заказе ({len(cart_items)} шт.):**
"""
        
        # Добавляем товары с сохраненными ценами
        for i, product in enumerate(cart_items, 1):
            price_without_vat = product.get('original_price_without_vat', 0)
            price_with_vat = product.get('original_price', 0)
            
            manager_message += f"""
{i}. **{product.get('title', 'Название не указано')}**
   💰 Исходная цена: {product.get('price', 'Не указана')}
   💵 Без НДС: €{price_without_vat:.2f}
   💶 С НДС: €{price_with_vat:.2f}
   🔗 Ссылка: {product.get('link', 'Не указана')}
"""
            # Добавляем комментарий к товару, если он есть
            if product.get('product_features'):
                manager_message += f"   💬 Комментарий: {product['product_features']}\n"
        
        # Добавляем общую сумму
        manager_message += f"""
💰 **Итоговая стоимость:**
💵 **Товары без НДС:** €{total_products_without_vat:.2f}
💶 **Товары с НДС:** €{total_products_with_vat:.2f}
🚚 **Доставка до склада:** €{delivery_cost_to_warehouse:.2f}
📦 **Доставка из Германии:** €{delivery_cost_from_germany:.2f}
💼 **Комиссия сервиса (15%):** €{service_commission:.2f}
💶 **ИТОГО:** €{total_cost:.2f}

📅 **Дата заказа:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

💬 **Связаться с клиентом:** https://t.me/{user_info.get('username', '')}
        """
        
        # Пытаемся отправить через aiogram бота
        try:
            from bot import bot
            await bot.send_message(
                chat_id=manager_id,
                text=manager_message,
                parse_mode="Markdown"
            )
            logging.info(f"Уведомление о заказе отправлено менеджеру {manager_id}")
            return True
        except Exception as e:
            logging.warning(f"Не удалось отправить через aiogram: {e}")
            
            # Fallback: отправляем через requests
            try:
                import requests
                bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                if bot_token:
                    response = requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": manager_id,
                            "text": manager_message,
                            "parse_mode": "Markdown"
                        },
                        timeout=10
                    )
                    if response.status_code == 200:
                        logging.info(f"Уведомление отправлено через requests менеджеру {manager_id}")
                        return True
                    else:
                        logging.error(f"Ошибка requests API: {response.status_code} - {response.text}")
                        return False
                else:
                    logging.error("TELEGRAM_BOT_TOKEN не найден")
                    return False
            except Exception as e2:
                logging.error(f"Ошибка отправки через requests: {e2}")
                return False
                
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления менеджеру: {e}")
        return False

async def save_order_to_local_file(order_data: dict, user_info: dict, cart_items: list) -> bool:
    """
    Сохраняет заказ в локальный файл (fallback если Google Sheets недоступен)
    
    Args:
        order_data: Данные заказа
        user_info: Информация о пользователе
        cart_items: Товары в корзине
        
    Returns:
        bool: True если успешно сохранено
    """
    try:
        import json
        from datetime import datetime
        
        logging.info("Начало сохранения заказа в локальный файл")
        
        if not cart_items:
            logging.error("Корзина пуста при сохранении в локальный файл")
            return False
        
        # Получаем данные из первого товара в корзине
        first_product = cart_items[0]
        delivery_type_code = first_product.get('delivery_type_code', 'small_package')
        weight = first_product.get('weight', 1.0)
        payment_method = order_data.get('payment_method', 'card')
        
        logging.info(f"Параметры доставки: тип={delivery_type_code}, вес={weight}, способ оплаты={payment_method}")
        
        # Рассчитываем цены
        from price_calculator import get_delivery_type_name, get_delivery_cost
        
        delivery_type_name = first_product.get('delivery_type', 'Маленький пакет')  # Используем название из корзины
        delivery_cost_to_warehouse = 5.00
        delivery_cost_from_germany = get_delivery_cost(delivery_type_code, weight)
        payment_method_name = "Карта иностранного банка" if payment_method == "card" else "Криптовалюта"
        
        # Рассчитываем итоговые суммы
        total_products_without_vat = sum(product.get('original_price_without_vat', 0) for product in cart_items)
        total_products_with_vat = sum(product.get('original_price', 0) for product in cart_items)
        subtotal = total_products_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
        service_commission = round(subtotal * 0.15, 2)
        total_cost = round(subtotal + service_commission, 2)
        
        logging.info(f"Рассчитанные суммы: товары без НДС={total_products_without_vat}, с НДС={total_products_with_vat}, итого={total_cost}")
        
        # Создаем данные для сохранения
        order_record = {
            'order_id': int(datetime.now().timestamp()),
            'date': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            'customer': {
                'name': order_data.get('name', ''),
                'phone': order_data.get('phone_number', ''),
                'email': order_data.get('email', ''),
                'address': order_data.get('address', ''),
                'comment': order_data.get('comment', ''),
                'delivery_type': delivery_type_name,
                'weight': f"{weight} кг",
                'payment_method': payment_method_name,
                'delivery_cost_to_warehouse': f"€{delivery_cost_to_warehouse:.2f}",
                'delivery_cost_from_germany': f"€{delivery_cost_from_germany:.2f}"
            },
            'user_info': {
                'telegram_id': user_info.get('user_id', ''),
                'username': user_info.get('username', ''),
                'first_name': user_info.get('first_name', ''),
                'last_name': user_info.get('last_name', '')
            },
            'order_summary': {
                'items_count': len(cart_items),
                'total_products_with_vat': total_products_with_vat,
                'total_products_without_vat': total_products_without_vat,
                'delivery_type': delivery_type_name,
                'weight': f"{weight} кг",
                'delivery_cost_to_warehouse': delivery_cost_to_warehouse,
                'delivery_cost_from_germany': delivery_cost_from_germany,
                'service_commission': service_commission,
                'total_cost': total_cost
            },
            'cart_items': cart_items  # Оригинальные товары из корзины
        }
        
        # Создаем папку orders если её нет
        os.makedirs('orders', exist_ok=True)
        
        # Сохраняем в файл
        filename = f"orders/order_{order_record['order_id']}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(order_record, f, ensure_ascii=False, indent=2)
        
        logging.info(f"Заказ сохранен в локальный файл: {filename}")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка сохранения в локальный файл: {e}")
        return False

async def process_order_completion(order_data: dict, user_info: dict, cart_items: list, order_id: int = None, calculation_comment: str = '') -> bool:
    """
    Обрабатывает завершение заказа (сохранение данных)
    
    Args:
        order_data: Данные заказа
        user_info: Информация о пользователе
        cart_items: Товары в корзине
        order_id: ID заказа (timestamp)
        calculation_comment: комментарий пользователя из расчёта
        
    Returns:
        bool: True если все операции выполнены успешно
    """
    success = True
    errors = []
    
    # Сохраняем в локальный файл (основной способ)
    try:
        local_success = await save_order_to_local_file(order_data, user_info, cart_items)
        if not local_success:
            errors.append("Не удалось сохранить заказ в локальный файл")
            success = False
        else:
            logging.info("Заказ успешно сохранен в локальный файл")
    except Exception as e:
        errors.append(f"Ошибка сохранения в локальный файл: {e}")
        success = False
        logging.error(f"Ошибка сохранения в локальный файл: {e}")
        
    # Пытаемся сохранить в Google Sheets (опционально)
    try:
        sheets_success = await save_order_to_sheets(order_data, user_info, order_id, calculation_comment)
        if sheets_success:
            logging.info("Заказ также сохранен в Google Sheets")
        else:
            logging.warning("Не удалось сохранить в Google Sheets, но это не критично")
    except Exception as e:
        logging.warning(f"Ошибка Google Sheets (не критично): {e}")
    
    # Отправляем уведомление менеджеру (опционально)
    try:
        manager_success = await send_order_to_manager(order_data, user_info, cart_items)
        if not manager_success:
            logging.warning("Не удалось отправить уведомление менеджеру, но это не критично")
        else:
            logging.info("Уведомление менеджеру отправлено успешно")
    except Exception as e:
        logging.warning(f"Ошибка отправки уведомления менеджеру (не критично): {e}")
    
    # Логируем все ошибки
    if errors:
        logging.error(f"Ошибки при обработке заказа: {', '.join(errors)}")
    
    # Возвращаем True если хотя бы локальное сохранение прошло успешно
    return success



