import os
import asyncio
import logging
from typing import Tuple
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
from services.scrapingbee_service import search_idealo_products
from services.currency_service import currency_service, CurrencyService
from services.google_sheets_service import GoogleSheetsService
from price_calculator import calculate_cart_total, format_price_display, get_delivery_type_name, get_delivery_cost
from keyboards import (
    get_help_keyboard, 
    get_product_navigation_keyboard,
    get_cart_reply_keyboard, get_main_reply_keyboard,
    get_delivery_type_keyboard, get_delivery_type_keyboard_for_calculation, get_weight_keyboard, get_weight_keyboard_for_order, get_payment_method_keyboard, get_order_confirmation_keyboard,
    get_price_calculation_keyboard, get_cancel_price_calculation_keyboard, get_back_keyboard, get_add_to_cart_from_calculation_keyboard
)

# Импортируем обработчики заказов
from order_handlers import (
    OrderStates, 
    process_name, 
    process_phone_number, 
    process_email, 
    process_address, 
    restart_order,
    confirm_order_callback
)

# Импортируем роутер для расчета цены

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Инициализация бота
bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключаем роутеры

# Сервис поиска товаров теперь импортируется как функция

# Инициализация Google Sheets сервиса для логирования
try:
    sheets_service = GoogleSheetsService()
except Exception as e:
    logging.error(f"Ошибка инициализации Google Sheets сервиса: {e}")
    sheets_service = None

# Helper функция для логирования действий пользователя
async def log_user_action(user_id: int, username: str, action: str):
    """Логирует действие пользователя в Google Sheets асинхронно"""
    if sheets_service:
        try:
            # Запускаем логирование как фоновую задачу, чтобы не блокировать ответ
            asyncio.create_task(log_user_action_background(user_id, username, action))
        except Exception as e:
            logging.error(f"Ошибка создания задачи логирования: {e}")

async def log_user_action_background(user_id: int, username: str, action: str):
    """Фоновое логирование действий пользователя"""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, sheets_service.log_user_action, user_id, username, action)
    except Exception as e:
        logging.error(f"Ошибка фонового логирования: {e}")

from formatting_utils import format_price_with_rub, format_total_with_savings

def parse_weight_callback_data(callback_data: str) -> Tuple[str, float]:
    """
    Правильно разбирает callback_data для кнопок веса
    Возвращает кортеж (delivery_type, weight)
    """
    # Убираем префикс "weight_"
    data_part = callback_data.replace("weight_", "")
    
    # Находим последнее подчеркивание, которое отделяет delivery_type от weight
    last_underscore_index = data_part.rfind('_')
    if last_underscore_index == -1:
        raise ValueError("Неверный формат callback_data")
    
    delivery_type = data_part[:last_underscore_index]
    weight_str = data_part[last_underscore_index + 1:]
    
    try:
        weight = float(weight_str)
    except ValueError:
        raise ValueError(f"Не удалось преобразовать '{weight_str}' в число")
    
    return delivery_type, weight

# Состояния FSM
class SearchStates(StatesGroup):
    waiting_for_query = State()
    showing_results = State()

class ProductStates(StatesGroup):
    waiting_for_action = State()

class PriceCalculationStates(StatesGroup):
    """Состояния для диалога расчета цены"""
    waiting_for_original_price = State()
    waiting_for_delivery_type = State()
    waiting_for_weight = State()
    waiting_for_product_link = State()
    waiting_for_product_features = State()
    showing_result = State()

class CartStates(StatesGroup):
    """Состояния для добавления товаров в корзину"""
    waiting_for_quantity_search = State()    # Выбор количества для товара из поиска
    waiting_for_quantity_calculated = State()  # Выбор количества для рассчитанного товара
    waiting_for_custom_quantity_search = State()  # Ввод пользовательского количества для товара из поиска
    waiting_for_custom_quantity_calculated = State()  # Ввод пользовательского количества для рассчитанного товара

# Хранилище для результатов поиска пользователей
user_results = {}

# Хранилище для URL товаров (временное решение)
product_urls = {}


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await log_user_action(message.from_user.id, message.from_user.username, "Команда /start")
    welcome_text = """
💯 Pay4Way — сервис №1 в России для выгодных международных покупок!

Мы — первые и единственные, кто предоставляет возможность приобретать товары из Европы 🇪🇺 без уплаты европейского НДС. Это значит, что вы экономите 19% уже на этапе покупки! 

Покупайте практически любой товар из Европы ([перечень ограничений](https://pay4way.ru/ogranichenia)), а мы доставим 🚛✈️🚄его в Россию быстро, безопасно и с гарантией!

📆 Срок доставки до вашего отделения Почты РФ: 3-4 недели
    
💬 Начните и убедитесь, как это просто и удобно
"""

    # Инлайн-кнопка под сообщением
    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Поехали", callback_data="start_go")]
        ]
    )

    await message.answer(welcome_text, reply_markup=inline_kb, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "start_go")
async def on_go_clicked(callback: types.CallbackQuery):
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Поехали")
    await callback.message.edit_reply_markup()  # Удаляем кнопку
    await callback.message.answer("🚀", reply_markup=get_main_reply_keyboard())
    await callback.answer()
# Обработчики Reply-кнопок

@dp.message(lambda message: message.text == "🔍 Поиск товаров")
async def search_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки поиск товаров"""
    await log_user_action(message.from_user.id, message.from_user.username, "Кнопка: Поиск товаров")
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    await state.set_state(SearchStates.waiting_for_query)
    await message.answer("🔍 Введите марку и модель товара на английском (например, Nike zoom):")
    await message.answer("🔍")
    
@dp.callback_query(lambda c: c.data == "start_search")
async def start_search_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки начала поиска"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Начать поиск")
    await state.set_state(SearchStates.waiting_for_query)
    await callback.message.answer("🔍 Введите марку и модель товара на английском (например, Nike zoom):")
    await callback.message.answer("🔍")

@dp.message(lambda message: message.text == "❓ Кто мы")
async def about_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки информация о нас"""
    await log_user_action(message.from_user.id, message.from_user.username, "Кнопка: Кто мы")
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    text = """
Кто мы?

Мы – чешское юридическое лицо. 
Наши реквизиты:
KPSports s.r.o. 
IČO 22332294
Kotkova 50/16, Liberec XIV-Ruprechtice, 460 14 Liberec

Проверить нас можно в [реестре Министерства юстиции Чешской Республики](https://msp.gov.cz/), указав наш ИНН (IČO). 


"""
    await message.answer(text, parse_mode="Markdown")

@dp.message(lambda message: message.text == "🚨 Поддержка")
async def contacts_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки контакты"""
    await log_user_action(message.from_user.id, message.from_user.username, "Кнопка: Поддержка")
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    
    text = """🚨 Поддержка

Свяжитесь с нами любым удобным способом:

📧 Email:
support@pay4way.ru

📱Telegram:
@pay4way_support

🌐 Сайт:
https://pay4way.ru"""
    await message.answer(text)


@dp.message(lambda message: message.text == "🛍 Корзина")
async def cart_handler(message: types.Message, state: FSMContext):
    await log_user_action(message.from_user.id, message.from_user.username, "Кнопка: Корзина")
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    
    # Добавляем отладочную информацию
    logging.info(f"Просмотр корзины. Размер корзины: {len(cart)}")
    for i, item in enumerate(cart):
        logging.info(f"Товар {i+1}: {item.get('title', 'Без названия')[:50]}")
    
    cart_text = "🛒 Ваша корзина:\n\n"
    no_cart_text = "🛒 Корзина пуста!\n\n" 
    delivery_cost_to_warehouse = 5.00

    if not cart:
        await message.answer(no_cart_text)
        return

    # Переменные для подсчета общей суммы
    total_euro = 0
    total_rub = 0

    for i, product in enumerate(cart):
        # Получаем количество товара (по умолчанию 1 для совместимости)
        quantity = product.get('quantity', 1)
        
        # Добавляем номер товара и количество
        cart_text += f"Товар #{i+1} (Количество: {quantity} шт.)\n\n"
        
        # Используем сохранённые параметры или значения по умолчанию
        price_without_vat = product.get('original_price_without_vat', 0)
        if price_without_vat == 0:
            # Если нет сохранённого значения, рассчитываем из цены
            price = product.get('price', 0)
            if isinstance(price, str):
                price = price.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
            try:
                price_with_vat = float(price)
                price_without_vat = round(price_with_vat * 0.81, 2)
            except Exception:
                price_without_vat = 0.0
        
        # Рассчитываем стоимость с учетом количества
        total_price_without_vat = price_without_vat * quantity
        rub_price_without_vat = currency_service.convert_price(total_price_without_vat)
        
        # Вычисляем стоимость доставки до склада в рублях отдельно
        rub_delivery_to_warehouse_value = currency_service.convert_price(delivery_cost_to_warehouse)
        rub_delivery_to_warehouse = f"{rub_delivery_to_warehouse_value:,.0f}".replace(',', ' ')
        
        cart_text += (
            f"🪙 Стоимость товаров: €{total_price_without_vat:.2f} или {f'{rub_price_without_vat:,.0f}'.replace(',', ' ')}₽ (мы уже вычли НДС)\n"
            f"   ├ За единицу: €{price_without_vat:.2f} × {quantity} шт.\n\n"
        )
        cart_text += (
            f"🚚 Стоимость доставки от интернет-магазина до нашего склада в Германии: €{delivery_cost_to_warehouse:.2f} или {rub_delivery_to_warehouse}₽\n\n"
        )
        
        # Используем сохранённые параметры доставки
        delivery_type = product.get('delivery_type', 'Маленький пакет')
        weight = product.get('weight', 1.0)
        delivery_cost_from_germany = product.get('delivery_cost_from_germany', 12.94)
        
        # Вычисляем стоимость доставки из Германии в рублях отдельно
        rub_delivery_from_germany_value = currency_service.convert_price(delivery_cost_from_germany)
        rub_delivery_from_germany = f"{rub_delivery_from_germany_value:,.0f}".replace(',', ' ')
        cart_text += (
            f"📦 Доставка из Германии до РФ:\n\n"
            f"Тип: {delivery_type}\n"
            f"Вес: {weight} кг\n"
            f"Стоимость доставки: €{delivery_cost_from_germany:.2f} или {rub_delivery_from_germany}₽\n\n"
        )
        
        # Используем сохранённые расчёты или рассчитываем заново с учетом количества
        if product.get('service_commission') and product.get('total'):
            service_commission_per_unit = product.get('service_commission')
            total_per_unit = product.get('total')
            service_commission = service_commission_per_unit * quantity
            total = total_per_unit * quantity
        else:
            subtotal = total_price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
            service_commission = round(subtotal * 0.15, 2)
            total = round(subtotal + service_commission, 2)
        
        # Вычисляем комиссию сервиса в рублях отдельно
        rub_service_commission_value = currency_service.convert_price(service_commission)
        rub_service_commission = f"{rub_service_commission_value:,.0f}".replace(',', ' ')
        cart_text += (
            f"💼 Комиссия нашего сервиса (15%): €{service_commission:.2f} или {rub_service_commission}₽\n\n"
        )
        if product.get('link'):
            cart_text += f"🔗 Ссылка на товар: {product['link']}\n\n"
        
        rub_total = currency_service.convert_price(total)
        cart_text += (
            f"💶 ИТОГО за {quantity} шт.: €{total:.2f} или {f'{rub_total:,.0f}'.replace(',', ' ')}₽\n\n"
        )
        
        # Добавляем к общим суммам
        total_euro += total
        total_rub += rub_total
        
        # Добавляем разделитель между товарами
        if i < len(cart) - 1:
            cart_text += "─" * 30 + "\n\n"
    
    # Добавляем общую сумму, если товаров больше одного
    if len(cart) > 1:
        cart_text += "=" * 40 + "\n"
        cart_text += f"**ОБЩАЯ СУММА ЗАКАЗА:**\n"
        cart_text += f"💶 €{total_euro:.2f} или {f'{total_rub:,.0f}'.replace(',', ' ')}₽\n\n"
    
    # Создаем клавиатуру с кнопками удаления отдельных товаров
    keyboard_buttons = []
    
    # Добавляем кнопки удаления для каждого товара
    for i in range(len(cart)):
        keyboard_buttons.append([InlineKeyboardButton(text=f"🗑️ Удалить товар #{i+1}", callback_data=f"remove_item_{i}")])
    
    # Добавляем основные кнопки
    keyboard_buttons.append([
        InlineKeyboardButton(text="🗑️ Очистить корзину", callback_data="clear_cart"), 
        InlineKeyboardButton(text="💳 Оформить заказ", callback_data="order_from_cart")
    ])
    
    next_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(cart_text, reply_markup=next_keyboard, parse_mode=None)



@dp.message(lambda message: message.text == "🧮 Рассчитать доставку")
async def start_price_calculation(message: types.Message, state: FSMContext):
    await log_user_action(message.from_user.id, message.from_user.username, "Кнопка: Рассчитать доставку")
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    
    await state.set_state(PriceCalculationStates.waiting_for_original_price)
    await message.answer("💰Введите цену товара:")

@dp.message(PriceCalculationStates.waiting_for_original_price)
async def input_original_price(message: types.Message, state: FSMContext):
    await log_user_action(message.from_user.id, message.from_user.username, f"Ввод цены товара: {message.text}")
    try:
        original_price = float(message.text.replace('€', '').replace(',', '.').strip())
        await state.update_data(original_price=original_price)
        # Проверка на превышение порога 200 евро
        if original_price > 200:
            await message.answer(
                "‼️ В соответствии с действующим законодательством РФ, если стоимость вашей покупки более 200€ (без учета стоимости доставки и комиссии нашего сервиса), то вам будет необходимо уплатить таможенную пошлину в размере 15% на разницу суммы, которая рассчитывается по формуле:\n\n"
                "Стоимость товара * 15%\n\n"
                "Пример:\n"
                "300€ (стоимость товара) - 200€ (беспошлинный порог) = 100 * 0.15 = 15€\n\n"
                "Пошлина составит 15€.\n\n"
                "Уплатить ее будет возможно в рублях в отделении почты РФ при получении товара."
            )
        await state.set_state(PriceCalculationStates.waiting_for_delivery_type)
        await message.answer("✅ Средняя стоимость доставки товара от интернет-магазина до нашего склада в Германии €5.00, которые уже включены в тариф доставки\n\n"
                             "❗️ Если доставка интернет-магазина бесплатная, то мы уменьшим стоимость доставки на €5.00. Если стоимость более €5.00, то мы скорректируем стоимость доставки на эту сумму.\n\n"
                             "🚚 Теперь выберите тип отправления из Германии до России:", reply_markup=get_delivery_type_keyboard_for_calculation())
    except Exception:
        await message.answer("Пожалуйста, введите корректную цену!")

@dp.callback_query(lambda c: c.data.startswith("delivery_"), StateFilter(PriceCalculationStates.waiting_for_delivery_type))
async def choose_delivery_type(callback: types.CallbackQuery, state: FSMContext):
    await log_user_action(callback.from_user.id, callback.from_user.username, f"Кнопка: Выбор доставки {callback.data}")
    await callback.answer()
    delivery_type = callback.data.replace("delivery_", "")
    await state.update_data(delivery_type=delivery_type)
    await state.set_state(PriceCalculationStates.waiting_for_weight)
    await callback.message.edit_text("Выберите вес товара:", reply_markup=get_weight_keyboard(delivery_type))

@dp.callback_query(lambda c: c.data.startswith("weight_"), StateFilter(PriceCalculationStates.waiting_for_weight))
async def choose_weight(callback: types.CallbackQuery, state: FSMContext):
    await log_user_action(callback.from_user.id, callback.from_user.username, f"Кнопка: Выбор веса {callback.data}")
    await callback.answer()
    try:
        delivery_type, weight = parse_weight_callback_data(callback.data)
    except ValueError as e:
        await callback.message.answer(f"Ошибка в данных: {e}. Попробуйте еще раз.")
        return
    await state.update_data(weight=weight)
    data = await state.get_data()
    delivery_cost_to_warehouse = 5.00
    result = calculate_cart_total(
        original_price=data['original_price'],
        delivery_type=delivery_type,
        weight=weight,
    )
    delivery_cost = get_delivery_cost(delivery_type, weight)
    original_price_without_vat = data['original_price'] * 0.81
    original_price_with_vat = data['original_price']
    rub_total = currency_service.convert_price(result['total'])
    rub_original_price_without_vat = currency_service.convert_price(data['original_price'] * 0.81)
    service_commission_amount = (original_price_without_vat + delivery_cost_to_warehouse + delivery_cost) * 0.15
    insurance_fee_amount = (original_price_without_vat + service_commission_amount) * 0.03
    final_price_without_vat = original_price_without_vat + delivery_cost_to_warehouse + delivery_cost + service_commission_amount + insurance_fee_amount
    final_rub_total = currency_service.convert_price(final_price_without_vat)
    final_price_with_vat = final_price_without_vat * 1.19
    await state.set_state(PriceCalculationStates.waiting_for_product_link)
    # Вычисляем значения в рублях отдельно
    rub_delivery_cost_to_warehouse_value = currency_service.convert_price(delivery_cost_to_warehouse)
    rub_delivery_cost_to_warehouse = f"{rub_delivery_cost_to_warehouse_value:,.0f}".replace(',', ' ')
    
    rub_delivery_cost_value = currency_service.convert_price(delivery_cost)
    rub_delivery_cost = f"{rub_delivery_cost_value:,.0f}".replace(',', ' ')
    
    rub_service_commission_value = currency_service.convert_price(service_commission_amount)
    rub_service_commission = f"{rub_service_commission_value:,.0f}".replace(',', ' ')
    
    rub_insurance_fee_value = currency_service.convert_price(insurance_fee_amount)
    rub_insurance_fee = f"{rub_insurance_fee_value:,.0f}".replace(',', ' ')
    
    savings_amount = original_price_with_vat - original_price_without_vat
    rub_savings_value = currency_service.convert_price(savings_amount)
    rub_savings = f"{rub_savings_value:,.0f}".replace(',', ' ')
    await callback.message.answer(
        "*Расчёт стоимости доставки*\n\n"
        f"🪙 Стоимость товаров: €{original_price_without_vat:.2f} или {f'{rub_original_price_without_vat:,.0f}'.replace(',', ' ')}₽ (мы уже вычли НДС)\n\n"
        f"🚚 Стоимость доставки от интернет-магазина до нашего склада в Германии: €{delivery_cost_to_warehouse:.2f} или {rub_delivery_cost_to_warehouse}₽\n\n"
        f"📦 Доставка из Германии до РФ:\nТип: {get_delivery_type_name(delivery_type)}\nВес: {weight} кг\nСтоимость: €{delivery_cost:.2f} или {rub_delivery_cost}₽\n\n"
        f"💼 Комиссия сервиса (15%): €{service_commission_amount:.2f} или {rub_service_commission}₽\n\n"
        f"🛡️ Страховой сбор (3%): €{insurance_fee_amount:.2f} или {rub_insurance_fee}₽\n\n"
        f"💶 ИТОГО: €{final_price_without_vat:.2f} или {f'{final_rub_total:,.0f}'.replace(',', ' ')}₽\n\n" 
        f"*Экономия составила €{savings_amount:.2f} или {rub_savings}₽ за счёт вычета нами суммы европейского НДС*\n\n"
        f"🔗 Если Вас всё устраивает, укажите, пожалуйста, ссылку на товар:",
        parse_mode="Markdown"
    )
    

@dp.message(PriceCalculationStates.waiting_for_product_link)
async def input_product_link(message: types.Message, state: FSMContext):
    await log_user_action(message.from_user.id, message.from_user.username, f"Ввод ссылки на товар: {message.text[:100]}")
    product_link = message.text.strip()
    
    # Проверяем, что это корректная ссылка
    if not product_link.startswith(('http://', 'https://')):
        await message.answer(
            "❌ *Ошибка!* Пожалуйста, введите корректную ссылку на товар.\n"
            "Ссылка должна начинаться с http:// или https://\n\n"
            "Пример: https://www.amazon.de/product/123",
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(product_link=product_link)
    await state.set_state(PriceCalculationStates.waiting_for_product_features)
    await message.answer("Укажите отличительные особенности товара (как указано на сайте интернет-магазина): размер, цвет и количество")

@dp.message(PriceCalculationStates.waiting_for_product_features)
async def input_product_features(message: types.Message, state: FSMContext):
    await log_user_action(message.from_user.id, message.from_user.username, f"Ввод особенностей товара: {message.text}")
    features = message.text.strip()
    await state.update_data(product_features=features)
    await state.set_state(PriceCalculationStates.showing_result)
    await message.answer(
            "Для добавления товара в корзину нажмите \"Добавить в корзину\"",
        reply_markup=get_add_to_cart_from_calculation_keyboard()
    )

@dp.callback_query(lambda c: c.data == "calculate_price_again_product")
async def calculate_price_again_product(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    
    await state.set_state(PriceCalculationStates.waiting_for_original_price)
    await callback.message.answer("Введите цену товара :", reply_markup=get_cancel_price_calculation_keyboard())


@dp.message(lambda message: message.text == "⬅️ Назад")
async def back_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки назад"""
    await log_user_action(message.from_user.id, message.from_user.username, "Кнопка: Назад")
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    
    welcome_text = """
🎉 Главное меню
Добро пожаловать в Pay4Way!
🏠 Главное меню

Здесь вы можете:

— 🔍 Найти товары из Европы
— 🛍 Добавить товары в корзину
— 💰 Рассчитать стоимость товара
— 💸 Оформить заказ
— ℹ️ Получить помощь и ответы на вопросы
— 📞 Связаться с нашей поддержкой
— 🏢 Узнать больше о нашей компании 

Выберите нужную опцию с помощью кнопок ниже 👇
"""
    await message.answer(welcome_text, reply_markup=get_main_reply_keyboard())
    await message.answer("⬅️")





@dp.callback_query(lambda c: c.data == "cart_next")
async def cart_next_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    # Получаем данные корзины
    data = await state.get_data()
    cart = data.get('cart', [])
    if not cart:
        await callback.message.edit_text(
            "🛒 Корзина пуста\n\n"
            "Добавьте товары из поиска, чтобы начать покупки!",
            reply_markup=get_back_keyboard()
        )
        return
    cart_text = ""
    delivery_cost_to_warehouse = 5.00
    
    # Переменные для подсчета общей суммы
    total_euro = 0
    total_rub = 0
    
    for i, product in enumerate(cart):
        # Добавляем номер товара
        cart_text += f"Товар #{i+1}\n"
        
        # Используем сохранённые параметры или значения по умолчанию
        price_without_vat = product.get('original_price_without_vat', 0)
        if price_without_vat == 0:
            # Если нет сохранённого значения, рассчитываем из цены
            price = product.get('price', 0)
            if isinstance(price, str):
                price = price.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
            try:
                price_with_vat = float(price)
                price_without_vat = round(price_with_vat * 0.81, 2)
            except Exception:
                price_without_vat = 0.0
        
        rub_price_without_vat = currency_service.convert_price(price_without_vat)
        cart_text += (
            f"🪙 Стоимость товаров: €{price_without_vat} или {f'{rub_price_without_vat:,.0f}'.replace(',', ' ')}₽ (мы уже вычли НДС)\n\n"
        )
        # Вычисляем стоимость в рублях отдельно
        rub_delivery_to_warehouse_value = currency_service.convert_price(delivery_cost_to_warehouse)
        rub_delivery_to_warehouse_formatted = f"{rub_delivery_to_warehouse_value:,.0f}".replace(',', ' ')
        
        cart_text += (
            f"🚚 Стоимость доставки от интернет-магазина до нашего склада в Германии: €{delivery_cost_to_warehouse:.2f} или {rub_delivery_to_warehouse_formatted}₽\n\n"
        )
        
        # Используем сохранённые параметры доставки
        delivery_type = product.get('delivery_type', 'Маленький пакет')
        weight = product.get('weight', 1.0)
        delivery_cost_from_germany = product.get('delivery_cost_from_germany', 12.94)
        rub_delivery_from_germany = f"{currency_service.convert_price(delivery_cost_from_germany):,.0f}".replace(',', ' ')
        cart_text += (
            f"📦 Доставка из Германии до РФ:\n\n"
            f"Тип: {delivery_type}\n"
            f"Вес: {weight} кг\n"
            f"Стоимость доставки: €{delivery_cost_from_germany:.2f} или {rub_delivery_from_germany}₽\n\n"
        )
        
        # Используем сохранённые расчёты или рассчитываем заново
        if product.get('service_commission') and product.get('total'):
            service_commission = product.get('service_commission')
            total = product.get('total')
        else:
            subtotal = price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
            service_commission = round(subtotal * 0.15, 2)
            total = round(subtotal + service_commission, 2)
        
        rub_service_commission = f"{currency_service.convert_price(service_commission):,.0f}".replace(',', ' ')
        cart_text += (
            f"💼 Комиссия нашего сервиса (15%): €{service_commission:.2f} или {rub_service_commission}₽\n\n"
        )
        if product.get('link'):
            cart_text += f"🔗 Ссылка на товар: {product['link']}\n\n"
        
        rub_total = currency_service.convert_price(total)
        cart_text += (
            f"💶 ИТОГО: €{total} или {f'{rub_total:,.0f}'.replace(',', ' ')}₽\n\n"
        )
        
        # Добавляем к общим суммам
        total_euro += total
        total_rub += rub_total
        
        # Добавляем разделитель между товарами
        if i < len(cart) - 1:
            cart_text += "─" * 30 + "\n\n"
    
    # Добавляем общую сумму, если товаров больше одного
    if len(cart) > 1:
        cart_text += "=" * 40 + "\n"
        cart_text += f"**ОБЩАЯ СУММА ЗАКАЗА:**\n"
        cart_text += f"💶 €{total_euro:.2f} или {f'{total_rub:,.0f}'.replace(',', ' ')}₽\n\n"
    
    next_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[KeyboardButton(text="💳 Оформить заказ")],[KeyboardButton(text="🗑️ Очистить корзину")]])
    await callback.message.edit_text(cart_text, reply_markup=next_keyboard, parse_mode=None)

@dp.callback_query(lambda c: c.data.startswith("delivery_"), StateFilter(PriceCalculationStates.waiting_for_delivery_type))
async def handle_delivery_type_selection_for_calculation(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора типа доставки для расчета цены"""
    await log_user_action(callback.from_user.id, callback.from_user.username, f"Кнопка: Выбор доставки для расчета {callback.data}")
    await callback.answer()
    
    from price_calculator import get_delivery_type_name
    
    delivery_type = callback.data.replace("delivery_", "")
    
    if delivery_type in ["ems"]:
        delivery_type_name = get_delivery_type_name(delivery_type)
        
        await state.set_state(PriceCalculationStates.waiting_for_weight)
        
        await callback.message.edit_text(
            f"✅ **Тип доставки выбран:** {delivery_type_name}\n\n"
            "⚖️ **Шаг 4: Выберите вес товара**\n\n"
            "Выберите подходящий вес товара:",
            reply_markup=get_weight_keyboard(delivery_type),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "❌ **Ошибка!** Неизвестный тип доставки.\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=get_delivery_type_keyboard_for_calculation()
        )



@dp.callback_query(lambda c: c.data == "back_to_delivery_type", StateFilter(PriceCalculationStates.waiting_for_weight))
async def back_to_delivery_type_for_calculation(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору типа доставки в процессе расчета цены"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Назад к выбору доставки")
    await callback.answer()
    
    await state.set_state(PriceCalculationStates.waiting_for_delivery_type)
    
    await callback.message.edit_text(
        "📦 **Выберите тип доставки**\n\n"
        "Выберите подходящий тип доставки до России:",
        reply_markup=get_delivery_type_keyboard_for_calculation()
    )

@dp.callback_query(lambda c: c.data == "delivery_type_callback")
async def delivery_type_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора типа доставки для заказа"""
    await callback.answer()
    
    from price_calculator import get_delivery_type_name
    
    delivery_type = callback.data.replace("delivery_type_", "")
    
    if delivery_type in ["ems"]:
        delivery_type_name = get_delivery_type_name(delivery_type)
        
        # Сохраняем выбранный тип доставки
        await state.update_data(selected_delivery_type=delivery_type)
        
        await callback.message.edit_text(
            f"✅ **Тип доставки выбран:** {delivery_type_name}\n\n"
            "⚖️ **Выберите вес товара:**",
            reply_markup=get_weight_keyboard_for_order(delivery_type),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "❌ **Ошибка!** Неизвестный тип доставки.\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=get_delivery_type_keyboard()
        )

@dp.callback_query(lambda c: c.data == "start_order")
async def start_order_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Оформить заказ'"""
    await callback.answer()
    
    # Отправляем сообщение о способах оплаты
    payment_message = """
💳 Мы принимаем оплату в криптовалюте или картой иностранного банка
"""
    
    # Создаем клавиатуру с кнопками
    payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ок, меня все устраивает", callback_data="payment_ok")],
        [InlineKeyboardButton(
            text="❓ Помогите разобраться в криптовалюте",
            url="https://telegra.ph/Gajd-Kak-kupit-kriptovalyutu-na-Bybit-dlya-oplaty-uslug-ot-Pay4Way-06-27"
        )]
    ])
    
    await callback.message.answer(payment_message, reply_markup=payment_keyboard)

@dp.message(OrderStates.waiting_for_name)
async def order_name_handler(message: types.Message, state: FSMContext):
    await process_name(message, state)

@dp.message(OrderStates.waiting_for_phone)
async def order_phone_handler(message: types.Message, state: FSMContext):
    await process_phone_number(message, state)

@dp.message(OrderStates.waiting_for_email)
async def order_email_handler(message: types.Message, state: FSMContext):
    await process_email(message, state)

@dp.message(OrderStates.waiting_for_address)
async def order_address_handler(message: types.Message, state: FSMContext):
    await process_address(message, state)


# 6. Проверка данных и подтверждение
@dp.callback_query(lambda c: c.data == "confirm_order", StateFilter(OrderStates.waiting_for_confirmation))
async def confirm_order_handler(callback: types.CallbackQuery, state: FSMContext):
    await confirm_order_callback(callback, state)

@dp.callback_query(lambda c: c.data == "restart_order")
async def restart_order_handler(callback: types.CallbackQuery, state: FSMContext):
    await restart_order(callback, state)

@dp.callback_query(lambda c: c.data == "cancel_order")
async def cancel_order_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    from keyboards import get_main_reply_keyboard
    await callback.message.answer(
        "❌ Заказ отменен.\n\n🏠 Возвращаемся в главное меню:",
        reply_markup=get_main_reply_keyboard()
    )


@dp.message(lambda message: message.text == "🗑️ Очистить корзину")
async def clear_cart_reply_handler(message: types.Message, state: FSMContext):
    await log_user_action(message.from_user.id, message.from_user.username, "Кнопка: Очистить корзину (reply)")
    await state.update_data(cart=[])
    text = "🗑️ **Ваша корзина очищена!**"
    await message.answer(text, reply_markup=get_cart_reply_keyboard(), parse_mode="Markdown")
    await message.answer("🗑️")

# Обработчики Inline-кнопок
@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки назад в главное меню"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Назад в главное меню")
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})

    await callback.message.answer("Вы перешли в главное меню !", reply_markup=get_main_reply_keyboard())
    await callback.message.answer("🏠")
    await callback.answer()





# Обработчики помощи
@dp.callback_query(lambda c: c.data == "help")
async def help_callback(callback: types.CallbackQuery):
    """Обработчик кнопки помощи"""
    help_text = """
ℹ️ **Помощь по использованию бота**

🔍 **Поиск товаров:**
• Используйте кнопку "Начать поиск" или команду /search
• Введите название товара
• Просматривайте результаты с помощью кнопок навигации

🛒 **Корзина:**
• Добавляйте товары в корзину кнопкой "В корзину"
• Просматривайте корзину в главном меню
• Оформляйте заказы

📞 **Поддержка:**
• Используйте кнопку "Контакты" для связи
• Обращайтесь к нам с любыми вопросами
"""
    await callback.message.answer(help_text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "how_to_use")
async def how_to_use_callback(callback: types.CallbackQuery):
    """Обработчик как пользоваться"""
    text = """
📖 **Как пользоваться ботом:**

1️⃣ **Поиск товаров:**
   • Нажмите "Начать поиск"
   • Введите название товара
   • Ожидайте результатов поиска

2️⃣ **Просмотр результатов:**
   • Используйте кнопки "Назад" и "Вперед"
   • Нажмите на изображение товара для деталей
   • Нажмите "Открыть товар" для перехода на сайт
   • Добавьте товар в корзину

3️⃣ **Корзина:**
   • Просматривайте добавленные товары
   • Оформляйте заказы
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "payment")
async def payment_callback(callback: types.CallbackQuery):
    """Обработчик как оплатить"""
    text = """
💳 **Способы оплаты**

Мы принимаем следующие способы оплаты:

— ₿ **Криптовалюта:** Вы можете оплатить заказ с помощью популярных криптовалют. Это быстрый и безопасный способ.

— 💳 **Карты иностранных банков:** Мы принимаем к оплате карты Visa, MasterCard и другие, выпущенные зарубежными банками.

Выберите удобный для вас вариант при оформлении заказа.
"""
    
    # Создаем клавиатуру с кнопкой "Назад в помощь"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в помощь", callback_data="help")]
    ])
    
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "support")
async def support_callback(callback: types.CallbackQuery):
    """Обработчик поддержки"""
    text = """
📞 **Поддержка**

Если у вас есть вопросы или проблемы:

💬 **Написать в поддержку:**
@your_support_username

📧 **Email:**
support@yourcompany.com

🌐 **Сайт:**
https://yourcompany.com/support

⏰ **Время работы:**
Пн-Пт: 9:00-18:00 (МСК)

Мы ответим вам в течение 24 часов!
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# Обработчики контактов
@dp.callback_query(lambda c: c.data == "contacts")
async def contacts_callback(callback: types.CallbackQuery):
    """Обработчик контактов"""
    text = """
📞 **Контакты**

Свяжитесь с нами любым удобным способом:

📧 **Email:**
info@yourcompany.com

📱 **Telegram:**
@your_company_bot

🌐 **Сайт:**
https://yourcompany.com

💬 **Поддержка:**
@your_support_username

Выберите способ связи:
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "about")
async def about_callback(callback: types.CallbackQuery):
    """Обработчик информации о нас"""
    text = """
ℹ️ **Информация о нас**

🏢 **О компании:**
Мы специализируемся на поиске и доставке товаров из Европы. Наша миссия - сделать покупки в европейских магазинах доступными для всех.

👥 **Наша команда:**
• Опытные специалисты по поиску товаров
• Менеджеры по работе с клиентами
• Логистические партнеры в Европе

📈 **Статистика:**
• Более 1000 успешных доставок
• Партнерство с 50+ европейскими магазинами
• Среднее время доставки: 7-14 дней

🎯 **Наши цели:**
• Предоставить доступ к качественным европейским товарам
• Обеспечить прозрачность цен и условий
• Сделать процесс покупки максимально удобным

Выберите раздел для получения подробной информации:
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "contact_email")
async def contact_email_callback(callback: types.CallbackQuery):
    """Обработчик email контакта"""
    text = """
📧 **Email контакты:**

📧 **Общие вопросы:**
info@yourcompany.com

🛒 **Заказы:**
orders@yourcompany.com

📞 **Поддержка:**
support@yourcompany.com

💼 **Партнерство:**
partnership@yourcompany.com

⏰ **Время ответа:** 1-2 часа
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "contact_telegram")
async def contact_telegram_callback(callback: types.CallbackQuery):
    """Обработчик telegram контакта"""
    text = """
📱 **Telegram контакты:**

🤖 **Основной бот:**
@your_company_bot

👨‍💼 **Менеджер:**
@your_manager_username

📞 **Поддержка:**
@your_support_username

💬 **Чат сообщества:**
@your_community_chat

⏰ **Время ответа:** 5-15 минут
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "contact_website")
async def contact_website_callback(callback: types.CallbackQuery):
    """Обработчик сайта"""
    text = """
🌐 **Наш сайт:**

🏠 **Главная страница:**
https://yourcompany.com

🛒 **Каталог товаров:**
https://yourcompany.com/catalog

📞 **Контакты:**
https://yourcompany.com/contacts

📖 **О нас:**
https://yourcompany.com/about

💼 **Партнерам:**
https://yourcompany.com/partners

📱 **Мобильная версия:**
https://m.yourcompany.com
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "contact_support")
async def contact_support_callback(callback: types.CallbackQuery):
    """Обработчик связи с поддержкой"""
    text = """
💬 **Написать в поддержку:**

📱 **Telegram:**
@your_support_username

📧 **Email:**
support@yourcompany.com

🌐 **Форма на сайте:**
https://yourcompany.com/support

📞 **Телефон:**
+7 (999) 123-45-67

⏰ **Время работы:**
Пн-Пт: 9:00-18:00 (МСК)
Сб-Вс: 10:00-16:00 (МСК)

**Среднее время ответа:** 15 минут
"""
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "clear_cart")
async def clear_cart_callback(callback: types.CallbackQuery, state: FSMContext):
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Очистить корзину")
    await state.update_data(cart=[])
    text = "🗑️ **Ваша корзина очищена!**"
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer("Корзина очищена!")

@dp.callback_query(lambda c: c.data.startswith("remove_item_"))
async def remove_item_callback(callback: types.CallbackQuery, state: FSMContext):
    """Удаление отдельного товара из корзины с обновлением сообщения"""
    await log_user_action(callback.from_user.id, callback.from_user.username, f"Кнопка: Удалить товар {callback.data}")
    await callback.answer()
    try:
        item_index = int(callback.data.split("_")[2])
        data = await state.get_data()
        cart = data.get('cart', [])
        if 0 <= item_index < len(cart):
            cart.pop(item_index)
            await state.update_data(cart=cart)
            # Если корзина пуста — показать соответствующее сообщение
            if not cart:
                await callback.message.edit_text(
                    "🛒 Корзина пуста\n\nДобавьте товар в корзину, чтобы начать покупки!"
                )
            else:
                # Сформировать новый текст и клавиатуру (логика из cart_callback)
                cart_text = "🛒 Ваша корзина:\n\n"
                delivery_cost_to_warehouse = 5.00
                total_euro = 0
                total_rub = 0
                for i, product in enumerate(cart):
                    cart_text += f"Товар #{i+1}\n"
                    price_without_vat = product.get('original_price_without_vat', 0)
                    if price_without_vat == 0:
                        price = product.get('price', 0)
                        if isinstance(price, str):
                            price = price.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
                        try:
                            price_with_vat = float(price)
                            price_without_vat = round(price_with_vat * 0.81, 2)
                        except Exception:
                            price_without_vat = 0.0
                    rub_price_without_vat = currency_service.convert_price(price_without_vat)
                    cart_text += (
                        f"🪙 Стоимость товаров: €{price_without_vat} или {f'{rub_price_without_vat:,.0f}'.replace(',', ' ')}₽ (мы уже вычли НДС)\n\n"
                    )
                    cart_text += (
                        f"🚚 Стоимость доставки от интернет-магазина до нашего склада в Германии: €{delivery_cost_to_warehouse}\n\n"
                    )
                    delivery_type = product.get('delivery_type', 'Маленький пакет')
                    weight = product.get('weight', 1.0)
                    delivery_cost_from_germany = product.get('delivery_cost_from_germany', 12.94)
                    cart_text += (
                        f"📦 Доставка из Германии до РФ:\n\n"
                        f"Тип: {delivery_type}\n"
                        f"Вес: {weight} кг\n"
                        f"Стоимость доставки: €{delivery_cost_from_germany:.2f}\n\n"
                    )
                    if product.get('service_commission') and product.get('total'):
                        service_commission = product.get('service_commission')
                        total = product.get('total')
                    else:
                        subtotal = price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
                        service_commission = round(subtotal * 0.15, 2)
                        total = round(subtotal + service_commission, 2)
                    cart_text += (
                        f"💼 Комиссия нашего сервиса (15%): €{service_commission}\n\n"
                    )
                    if product.get('link'):
                        cart_text += f"🔗 Ссылка на товар: {product['link']}\n\n"
                    rub_total = currency_service.convert_price(total)
                    cart_text += (
                        f"💶 ИТОГО: €{total} или {f'{rub_total:,.0f}'.replace(',', ' ')}₽\n\n"
                    )
                    total_euro += total
                    total_rub += rub_total
                    if i < len(cart) - 1:
                        cart_text += "─" * 30 + "\n\n"
                if len(cart) > 1:
                    cart_text += "=" * 40 + "\n"
                    cart_text += f"**ОБЩАЯ СУММА ЗАКАЗА:**\n"
                    cart_text += f"💶 €{total_euro:.2f} или {f'{total_rub:,.0f}'.replace(',', ' ')}₽\n\n"
                keyboard_buttons = []
                for i in range(len(cart)):
                    keyboard_buttons.append([InlineKeyboardButton(text=f"🗑️ Удалить товар #{i+1}", callback_data=f"remove_item_{i}")])
                keyboard_buttons.append([
                    InlineKeyboardButton(text="🗑️ Очистить корзину", callback_data="clear_cart"), 
                    InlineKeyboardButton(text="💳 Оформить заказ", callback_data="order_from_cart")
                ])
                next_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                await callback.message.edit_text(cart_text, reply_markup=next_keyboard, parse_mode=None)
        else:
            await callback.message.answer("❌ Ошибка: товар не найден!")
    except (ValueError, IndexError) as e:
        await callback.message.answer("❌ Ошибка при удалении товара!")
        logging.error(f"Ошибка при удалении товара: {e}")


# Обработчики поиска
@dp.message(SearchStates.waiting_for_query)
async def process_search_query(message: types.Message, state: FSMContext):
    """Обработчик поискового запроса (с сохранением истории для листания)"""
    await log_user_action(message.from_user.id, message.from_user.username, f"Поиск товара: {message.text[:50]}")
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("❌ Слишком короткий запрос. Введите минимум 2 символа. Попробуйте еще раз.")
        return
    search_msg = await message.answer(f"🔍 Ищу товары по запросу: '{query}'...")
    try:
        # Запускаем синхронную функцию в executor
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, search_idealo_products, query, 10)
        
        # Проверяем специальный случай ошибки 503
        if results is None:
            await search_msg.edit_text(
                "⚠️ **Извините, функция поиска временно недоступна**\n\n"
                "Произошла техническая ошибка при поиске товаров. "
                "Пожалуйста, попробуйте позже или обратитесь в поддержку.\n\n"
                "🔧 Мы работаем над устранением проблемы.\n"
                "📞 Для получения помощи: @pay4way_admin",
                parse_mode="Markdown"
            )
            return
        
        if not results:
            await search_msg.edit_text(f"❌ По запросу '{query}' ничего не найдено. Пожалуйста, попробуйте еще раз.")
            return
            
        # Сохраняем только первые 10 результатов для пользователя
        user_id = message.from_user.id
        user_results[user_id] = {
            'results': results,
            'current_index': 0,
            'query': query
        }
        # Показываем первый результат
        await show_product_card(search_msg, user_id, 0)
        await state.set_state(SearchStates.showing_results)
    except Exception as e:
        logging.error(f"Ошибка при поиске: {e}")
        await search_msg.edit_text("❌ Данная функция временно недоступна, из за технических работ на сервере. Попробуйте позже.\n\n"
                                   "🔧 Мы работаем над устранением проблемы.\n"
                                   "📞 Для получения помощи: @pay4way_admin")

async def show_product_card(message: types.Message, user_id: int, index: int):
    """Показывает карточку товара с навигацией (использует user_results)"""
    if user_id not in user_results:
        return
    results = user_results[user_id]['results']
    if not results or index < 0 or index >= len(results):
        return
    product = results[index]
    
    # Формируем текст карточки с количеством предложений и ценой в рублях
    price = product['price']
    price_eur = 0.0
    offers_count = product.get('offers_count', 'Нет данных')
    
    # Извлекаем числовое значение цены
    if isinstance(price, str):
        price_clean = price.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
        try:
            price_eur = float(price_clean)
        except:
            price_eur = 0.0
    
    # Форматируем цену с конвертацией в рубли
    if price_eur > 0:
        rub_price = currency_service.convert_price(price_eur)
        rub_price_formatted = f"{rub_price:,.0f}".replace(',', ' ') if rub_price else "—"
        formatted_price = f"€{price_eur:.2f} или {rub_price_formatted}₽"
    else:
        formatted_price = price
    
    # Определяем формат цены в зависимости от количества предложений
    if isinstance(offers_count, str) and offers_count.isdigit():
        offers_num = int(offers_count)
        if offers_num > 1:
            price_display = f"Цена от {formatted_price}"
        else:
            price_display = formatted_price
    else:
        price_display = formatted_price
    
    card_text = f"""
🛍️ **{product['title']}**

💰 Цена от: {price_display}\n
📊 Всего найдено предложений: {offers_count} шт.

*Инструкция:*
1️⃣ Чтобы выбрать лучшее предложение, размер и цвет нажмите на кнопку «🛍️ Посмотреть товар»\n
2️⃣ После того, как вы нашли нужный товар, скопируйте ссылку на него из интернет-магазина и запомните его стоимость\n
3️⃣ Вернитесь в бота и нажмите «🧮 Рассчитать доставку». Далее следуйте указаниям бота.\n
"""
    
    keyboard = get_product_navigation_keyboard(
        current_index=index,
        total_results=len(results),
        product_index=index,
        product_link=product.get('link', '')
    )
    
    if product.get('image'):
        try:
            await message.answer_photo(
                photo=product['image'],
                caption=card_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            await message.delete()
        except Exception as e:
            logging.error(f"Ошибка при отправке фото: {e}")
            await message.edit_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.edit_text(card_text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data.startswith("nav_"))
async def navigation_callback(callback: types.CallbackQuery):
    """Обработчик навигации по товарам (вперёд/назад)"""
    await log_user_action(callback.from_user.id, callback.from_user.username, f"Кнопка: Навигация {callback.data}")
    user_id = callback.from_user.id
    index = int(callback.data.split("_")[1])
    if user_id in user_results:
        user_results[user_id]['current_index'] = index
        await show_product_card(callback.message, user_id, index)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("add_to_cart_"))
async def add_to_cart_callback(callback: types.CallbackQuery, state: FSMContext):
    """Переходит к выбору количества товара из результатов поиска"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Добавить в корзину (выбор количества)")
    user_id = callback.from_user.id
    index = int(callback.data.split("_")[3])
    if user_id in user_results:
        product = user_results[user_id]['results'][index]
        
        # Сохраняем информацию о выбранном товаре в состоянии
        await state.update_data(selected_product=product, selected_product_index=index)
        await state.set_state(CartStates.waiting_for_quantity_search)
        
        # Показываем клавиатуру выбора количества
        from keyboards import get_quantity_keyboard
        await callback.message.edit_text(
            f"🛒 **Выберите количество товара:**\n\n"
            f"📦 {product.get('title', 'Товар')[:100]}\n"
            f"💰 Цена: {product.get('price', 'Не указана')}\n\n"
            f"Сколько единиц товара добавить в корзину?",
            reply_markup=get_quantity_keyboard("search"),
            parse_mode="Markdown"
        )
        await callback.answer()
    else:
        await callback.answer("❌ Ошибка: товар не найден")

# Обработчики выбора количества товаров
@dp.callback_query(lambda c: c.data.startswith("quantity_search_"), StateFilter(CartStates.waiting_for_quantity_search))
async def handle_quantity_search(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора количества для товара из поиска"""
    await log_user_action(callback.from_user.id, callback.from_user.username, f"Кнопка: Выбор количества {callback.data}")
    await callback.answer()
    
    # Получаем количество из callback_data
    quantity_str = callback.data.split("_")[2]
    
    if quantity_str == "custom":
        # Пользователь хочет ввести свое количество
        await callback.message.edit_text(
            "✏️ **Введите количество товара:**\n\n"
            "Напишите число от 1 до 999:",
            parse_mode="Markdown"
        )
        await state.set_state(CartStates.waiting_for_custom_quantity_search)
        return
    
    try:
        quantity = int(quantity_str)
        if quantity < 1 or quantity > 999:
            await callback.answer("❌ Количество должно быть от 1 до 999")
            return
    except ValueError:
        await callback.answer("❌ Ошибка в количестве")
        return
    
    # Получаем данные о выбранном товаре
    data = await state.get_data()
    product = data.get('selected_product')
    
    if not product:
        await callback.answer("❌ Ошибка: товар не найден")
        return
    
    # Добавляем количество к товару
    product_with_quantity = product.copy()
    product_with_quantity['quantity'] = quantity
    
    # Добавляем в корзину
    cart = data.get('cart', [])
    cart.append(product_with_quantity)
    await state.update_data(cart=cart)
    
    # Очищаем временные данные о товаре
    await state.update_data(selected_product=None, selected_product_index=None)
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ **Товар добавлен в корзину!**\n\n"
        f"📦 {product.get('title', 'Товар')[:100]}\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"💰 Цена за единицу: {product.get('price', 'Не указана')}\n\n"
        f"Что делаем дальше?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Перейти в корзину", callback_data="cart")],
            [InlineKeyboardButton(text="🔍 Продолжить поиск", callback_data="start_search")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]),
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data.startswith("quantity_calculated_"), StateFilter(CartStates.waiting_for_quantity_calculated))
async def handle_quantity_calculated(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора количества для рассчитанного товара"""
    await log_user_action(callback.from_user.id, callback.from_user.username, f"Кнопка: Выбор количества рассчитанного {callback.data}")
    await callback.answer()
    
    # Получаем количество из callback_data
    quantity_str = callback.data.split("_")[2]
    
    if quantity_str == "custom":
        # Пользователь хочет ввести свое количество
        await callback.message.edit_text(
            "✏️ **Введите количество товара:**\n\n"
            "Напишите число от 1 до 999:",
            parse_mode="Markdown"
        )
        await state.set_state(CartStates.waiting_for_custom_quantity_calculated)
        return
    
    try:
        quantity = int(quantity_str)
        if quantity < 1 or quantity > 999:
            await callback.answer("❌ Количество должно быть от 1 до 999")
            return
    except ValueError:
        await callback.answer("❌ Ошибка в количестве")
        return
    
    # Получаем данные расчета и создаем товар (аналогично add_calculated_to_cart)
    data = await state.get_data()
    original_price = data.get('original_price', 0)
    final_price = data.get('final_price', 0)
    delivery_type = data.get('delivery_type', '')
    weight = data.get('weight', 0)
    product_link = data.get('product_link', '')
    product_features = data.get('product_features', '')
    
    # Рассчитываем все нужные параметры
    from price_calculator import get_delivery_cost, get_delivery_type_name, format_price_display
    delivery_cost_from_germany = get_delivery_cost(delivery_type, weight)
    original_price_without_vat = round(original_price * 0.81, 2)
    delivery_cost_to_warehouse = 5.00
    subtotal = original_price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
    service_commission = round(subtotal * 0.15, 2)
    total = round(subtotal + service_commission, 2)
    
    # Получаем красивое название типа доставки
    delivery_type_name = get_delivery_type_name(delivery_type)
    
    # Создаем товар для корзины с количеством
    calculated_product = {
        'title': f"Товар (цена: {format_price_display(original_price)})",
        'price': format_price_display(original_price),
        'source': 'Расчет пользователя',
        'link': product_link,
        'original_price': original_price,
        'original_price_without_vat': original_price_without_vat,
        'delivery_type': delivery_type_name,
        'delivery_type_code': delivery_type,
        'weight': weight,
        'delivery_cost_from_germany': delivery_cost_from_germany,
        'delivery_cost_to_warehouse': delivery_cost_to_warehouse,
        'service_commission': service_commission,
        'total': total,
        'calculated_price': data.get('calculated_price', 0),
        'product_features': product_features,
        'quantity': quantity  # Добавляем количество
    }
    
    # Добавляем в корзину
    cart_data = await state.get_data()
    cart = cart_data.get('cart', [])
    cart.append(calculated_product)
    await state.update_data(cart=cart)
    
    # Очищаем данные расчета, но оставляем корзину
    await state.clear()
    await state.update_data(cart=cart)
    
    await callback.message.edit_text(
        f"✅ **Рассчитанный товар добавлен в корзину!**\n\n"
        f"📦 Товар (цена: €{original_price})\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"💰 Общая стоимость: €{total * quantity:.2f}\n\n"
        f"Что делаем дальше?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Перейти в корзину", callback_data="cart")],
            [InlineKeyboardButton(text="🧮 Рассчитать еще товар", callback_data="calculate_price")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]),
        parse_mode="Markdown"
    )

# Обработчики ввода пользовательского количества
@dp.message(CartStates.waiting_for_custom_quantity_search)
async def handle_custom_quantity_search(message: types.Message, state: FSMContext):
    """Обработчик ввода пользовательского количества для товара из поиска"""
    await log_user_action(message.from_user.id, message.from_user.username, f"Ввод количества товара: {message.text}")
    
    try:
        quantity = int(message.text.strip())
        if quantity < 1 or quantity > 999:
            await message.answer(
                "❌ **Ошибка!**\n\n"
                "Количество должно быть от 1 до 999.\n"
                "Попробуйте еще раз:",
                parse_mode="Markdown"
            )
            return
    except ValueError:
        await message.answer(
            "❌ **Ошибка!**\n\n"
            "Введите корректное число от 1 до 999.\n"
            "Попробуйте еще раз:",
            parse_mode="Markdown"
        )
        return
    
    # Получаем данные о выбранном товаре
    data = await state.get_data()
    product = data.get('selected_product')
    
    if not product:
        await message.answer("❌ Ошибка: товар не найден")
        await state.clear()
        return
    
    # Добавляем количество к товару
    product_with_quantity = product.copy()
    product_with_quantity['quantity'] = quantity
    
    # Добавляем в корзину
    cart = data.get('cart', [])
    cart.append(product_with_quantity)
    await state.update_data(cart=cart)
    
    # Очищаем временные данные о товаре
    await state.update_data(selected_product=None, selected_product_index=None)
    await state.clear()
    
    await message.answer(
        f"✅ **Товар добавлен в корзину!**\n\n"
        f"📦 {product.get('title', 'Товар')[:100]}\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"💰 Цена за единицу: {product.get('price', 'Не указана')}\n\n"
        f"Что делаем дальше?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Перейти в корзину", callback_data="cart")],
            [InlineKeyboardButton(text="🔍 Продолжить поиск", callback_data="start_search")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]),
        parse_mode="Markdown"
    )

@dp.message(CartStates.waiting_for_custom_quantity_calculated)
async def handle_custom_quantity_calculated(message: types.Message, state: FSMContext):
    """Обработчик ввода пользовательского количества для рассчитанного товара"""
    await log_user_action(message.from_user.id, message.from_user.username, f"Ввод количества рассчитанного товара: {message.text}")
    
    try:
        quantity = int(message.text.strip())
        if quantity < 1 or quantity > 999:
            await message.answer(
                "❌ **Ошибка!**\n\n"
                "Количество должно быть от 1 до 999.\n"
                "Попробуйте еще раз:",
                parse_mode="Markdown"
            )
            return
    except ValueError:
        await message.answer(
            "❌ **Ошибка!**\n\n"
            "Введите корректное число от 1 до 999.\n"
            "Попробуйте еще раз:",
            parse_mode="Markdown"
        )
        return
    
    # Получаем данные расчета и создаем товар (аналогично handle_quantity_calculated)
    data = await state.get_data()
    original_price = data.get('original_price', 0)
    final_price = data.get('final_price', 0)
    delivery_type = data.get('delivery_type', '')
    weight = data.get('weight', 0)
    product_link = data.get('product_link', '')
    product_features = data.get('product_features', '')
    
    # Рассчитываем все нужные параметры
    from price_calculator import get_delivery_cost, get_delivery_type_name, format_price_display
    delivery_cost_from_germany = get_delivery_cost(delivery_type, weight)
    original_price_without_vat = round(original_price * 0.81, 2)
    delivery_cost_to_warehouse = 5.00
    subtotal = original_price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
    service_commission = round(subtotal * 0.15, 2)
    total = round(subtotal + service_commission, 2)
    
    # Получаем красивое название типа доставки
    delivery_type_name = get_delivery_type_name(delivery_type)
    
    # Создаем товар для корзины с количеством
    calculated_product = {
        'title': f"Товар (цена: {format_price_display(original_price)})",
        'price': format_price_display(original_price),
        'source': 'Расчет пользователя',
        'link': product_link,
        'original_price': original_price,
        'original_price_without_vat': original_price_without_vat,
        'delivery_type': delivery_type_name,
        'delivery_type_code': delivery_type,
        'weight': weight,
        'delivery_cost_from_germany': delivery_cost_from_germany,
        'delivery_cost_to_warehouse': delivery_cost_to_warehouse,
        'service_commission': service_commission,
        'total': total,
        'calculated_price': data.get('calculated_price', 0),
        'product_features': product_features,
        'quantity': quantity  # Добавляем количество
    }
    
    # Добавляем в корзину
    cart_data = await state.get_data()
    cart = cart_data.get('cart', [])
    cart.append(calculated_product)
    await state.update_data(cart=cart)
    
    # Очищаем данные расчета, но оставляем корзину
    await state.clear()
    await state.update_data(cart=cart)
    
    await message.answer(
        f"✅ **Рассчитанный товар добавлен в корзину!**\n\n"
        f"📦 Товар (цена: €{original_price})\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"💰 Общая стоимость: €{total * quantity:.2f}\n\n"
        f"Что делаем дальше?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Перейти в корзину", callback_data="cart")],
            [InlineKeyboardButton(text="🧮 Рассчитать еще товар", callback_data="calculate_price")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]),
        parse_mode="Markdown"
    )

# Обработчик кнопки "Назад" из выбора количества
@dp.callback_query(lambda c: c.data == "back_to_product")
async def back_to_product_callback(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к карточке товара из выбора количества"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Назад к товару")
    await callback.answer()
    
    # Получаем данные о товаре
    data = await state.get_data()
    user_id = callback.from_user.id
    selected_product_index = data.get('selected_product_index')
    
    # Очищаем состояние выбора количества
    await state.clear()
    
    # Если есть индекс товара, показываем карточку товара
    if selected_product_index is not None and user_id in user_results:
        await show_product_card(callback.message, user_id, selected_product_index)
    else:
        # Если нет данных о товаре, возвращаемся в главное меню
        await callback.message.edit_text(
            "🏠 Возврат в главное меню",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Начать поиск", callback_data="start_search")],
                [InlineKeyboardButton(text="🧮 Рассчитать доставку", callback_data="calculate_price")],
                [InlineKeyboardButton(text="🛍 Корзина", callback_data="cart")]
            ])
        )

@dp.callback_query(lambda c: c.data == "cart")
async def cart_callback(callback: types.CallbackQuery, state: FSMContext):
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Корзина (callback)")
    data = await state.get_data()
    cart = data.get('cart', [])
    
    # Добавляем отладочную информацию
    logging.info(f"Callback просмотр корзины. Размер корзины: {len(cart)}")
    logging.info(f"Все данные состояния: {data}")
    for i, item in enumerate(cart):
        logging.info(f"Товар {i+1}: {item.get('title', 'Без названия')[:50]}")
        logging.info(f"  - source: {item.get('source', 'Не указан')}")
        logging.info(f"  - price: {item.get('price', 'Не указана')}")
    
    cart_text = "🛒 Ваша корзина:\n\n"
    delivery_cost_to_warehouse = 5.00
    
    if not cart:
        await callback.message.edit_text(
            "🛒 Корзина пуста\n\n"
            "Добавьте товар в корзину, чтобы начать покупки!",
        )
    else:
        # Переменные для подсчета общей суммы
        total_euro = 0
        total_rub = 0
        
        for i, product in enumerate(cart):
            # Получаем количество товара (по умолчанию 1 для совместимости)
            quantity = product.get('quantity', 1)
            
            # Добавляем номер товара и количество
            cart_text += f"Товар #{i+1} (Количество: {quantity} шт.)\n"
            
            # Используем сохранённые параметры или значения по умолчанию
            price_without_vat = product.get('original_price_without_vat', 0)
            if price_without_vat == 0:
                # Если нет сохранённого значения, рассчитываем из цены
                price = product.get('price', 0)
                if isinstance(price, str):
                    price = price.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
                try:
                    price_with_vat = float(price)
                    price_without_vat = round(price_with_vat * 0.81, 2)
                except Exception:
                    price_without_vat = 0.0
            
            # Рассчитываем стоимость с учетом количества
            total_price_without_vat = price_without_vat * quantity
            rub_price_without_vat = currency_service.convert_price(total_price_without_vat)
            
            # Вычисляем стоимость доставки до склада в рублях отдельно
            rub_delivery_to_warehouse_value = currency_service.convert_price(delivery_cost_to_warehouse)
            rub_delivery_to_warehouse = f"{rub_delivery_to_warehouse_value:,.0f}".replace(',', ' ')
            
            cart_text += (
                f"🪙 Стоимость товаров: €{total_price_without_vat:.2f} или {f'{rub_price_without_vat:,.0f}'.replace(',', ' ')}₽ (мы уже вычли НДС)\n"
                f"   ├ За единицу: €{price_without_vat:.2f} × {quantity} шт.\n\n"
            )
            cart_text += (
                f"🚚 Стоимость доставки от интернет-магазина до нашего склада в Германии: €{delivery_cost_to_warehouse:.2f} или {rub_delivery_to_warehouse}₽\n\n"
            )
            
            # Используем сохранённые параметры доставки
            delivery_type = product.get('delivery_type', 'Маленький пакет')
            weight = product.get('weight', 1.0)
            delivery_cost_from_germany = product.get('delivery_cost_from_germany', 12.94)
            
            # Вычисляем стоимость доставки из Германии в рублях отдельно
            rub_delivery_from_germany_value = currency_service.convert_price(delivery_cost_from_germany)
            rub_delivery_from_germany = f"{rub_delivery_from_germany_value:,.0f}".replace(',', ' ')
            cart_text += (
                f"📦 Доставка из Германии до РФ:\n\n"
                f"Тип: {delivery_type}\n"
                f"Вес: {weight} кг\n"
                f"Стоимость доставки: €{delivery_cost_from_germany:.2f} или {rub_delivery_from_germany}₽\n\n"
            )
            
            # Используем сохранённые расчёты или рассчитываем заново с учетом количества
            if product.get('service_commission') and product.get('total'):
                service_commission_per_unit = product.get('service_commission')
                total_per_unit = product.get('total')
                service_commission = service_commission_per_unit * quantity
                total = total_per_unit * quantity
            else:
                subtotal = total_price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
                service_commission = round(subtotal * 0.15, 2)
                total = round(subtotal + service_commission, 2)
            
            # Вычисляем комиссию сервиса в рублях отдельно
            rub_service_commission_value = currency_service.convert_price(service_commission)
            rub_service_commission = f"{rub_service_commission_value:,.0f}".replace(',', ' ')
            cart_text += (
                f"💼 Комиссия нашего сервиса (15%): €{service_commission:.2f} или {rub_service_commission}₽\n\n"
            )
            if product.get('link'):
                cart_text += f"🔗 Ссылка на товар: {product['link']}\n\n"
            
            rub_total = currency_service.convert_price(total)
            cart_text += (
                f"💶 ИТОГО за {quantity} шт.: €{total:.2f} или {f'{rub_total:,.0f}'.replace(',', ' ')}₽\n\n"
            )
            
            # Добавляем к общим суммам
            total_euro += total
            total_rub += rub_total
            
            # Добавляем разделитель между товарами
            if i < len(cart) - 1:
                cart_text += "─" * 30 + "\n\n"
        
        # Добавляем общую сумму, если товаров больше одного
        if len(cart) > 1:
            cart_text += "=" * 40 + "\n"
            cart_text += f"**ОБЩАЯ СУММА ЗАКАЗА:**\n"
            cart_text += f"💶 €{total_euro:.2f} или {f'{total_rub:,.0f}'.replace(',', ' ')}₽\n\n"
        
        # Создаем клавиатуру с кнопками удаления отдельных товаров
        keyboard_buttons = []
        
        # Добавляем кнопки удаления для каждого товара
        for i in range(len(cart)):
            keyboard_buttons.append([InlineKeyboardButton(text=f"🗑️ Удалить товар #{i+1}", callback_data=f"remove_item_{i}")])
        
        # Добавляем основные кнопки
        keyboard_buttons.append([
            InlineKeyboardButton(text="🗑️ Очистить корзину", callback_data="clear_cart"), 
            InlineKeyboardButton(text="💳 Оформить заказ", callback_data="order_from_cart")
        ])
        
        next_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await callback.message.edit_text(cart_text, reply_markup=next_keyboard, parse_mode=None)

# Обработчики для расчета цены товара

@dp.callback_query(lambda c: c.data == "start_price_calculation")
async def start_price_calculation(callback: types.CallbackQuery, state: FSMContext):
    """Запуск процесса расчета цены товара"""
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.set_data({'cart': cart})
    await callback.answer()
    
    # Очищаем данные предыдущего расчета
    await state.update_data(calculation_data={})
    await state.set_state(PriceCalculationStates.waiting_for_original_price)
    
    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "💰Введите цену товара:",
        parse_mode="Markdown"
    )

@dp.message(PriceCalculationStates.waiting_for_original_price)
async def handle_original_price(message: types.Message, state: FSMContext):
    """Обработка ввода цены товара"""
    await log_user_action(message.from_user.id, message.from_user.username, f"Ввод цены товара (обработчик 2): {message.text}")
    from price_calculator import extract_price_value, format_price_display
    
    price_text = message.text.strip()
    
    # Извлекаем числовое значение цены
    original_price = extract_price_value(price_text)
    
  
    # Сохраняем итоговую цену
    await state.update_data(final_price=original_price)
    
    await state.set_state(PriceCalculationStates.waiting_for_delivery_type)
    
    await message.answer(
        f"✅ **Итоговая цена принята:** {format_price_display(original_price)}\n\n"
        "📦 Шаг 3 **Выбор типа доставки из Германии до России**\n\n"
        "🚚 Теперь выберите тип отправления из Германии до России:",
        reply_markup=get_delivery_type_keyboard_for_calculation(),
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "cancel_price_calculation")
async def cancel_price_calculation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена расчета цены"""
    await callback.answer()
    
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем состояние, но сохраняем корзину
    await state.clear()
    await state.update_data(cart=cart)
    
    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "❌ Расчет цены отменен.\n\n"
        "Вы можете начать новый расчет в любое время.",
        reply_markup=get_back_keyboard()
    )

@dp.callback_query(lambda c: c.data == "select_quantity_calculated")
async def select_quantity_calculated(callback: types.CallbackQuery, state: FSMContext):
    """Переход к выбору количества рассчитанного товара"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Выбор количества рассчитанного товара")
    
    # Получаем данные расчета для отображения
    data = await state.get_data()
    original_price = data.get('original_price', 0)
    product_link = data.get('product_link', '')
    product_features = data.get('product_features', '')
    
    await state.set_state(CartStates.waiting_for_quantity_calculated)
    
    # Показываем клавиатуру выбора количества
    from keyboards import get_quantity_keyboard
    await callback.message.edit_text(
        f"🛒 **Выберите количество товара:**\n\n"
        f"📦 Рассчитанный товар\n"
        f"💰 Цена: €{original_price}\n"
        f"🔗 Ссылка: {product_link[:50]}{'...' if len(product_link) > 50 else ''}\n"
        f"📝 Особенности: {product_features[:50]}{'...' if len(product_features) > 50 else ''}\n\n"
        f"Сколько единиц товара добавить в корзину?",
        reply_markup=get_quantity_keyboard("calculated"),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "add_calculated_to_cart")
async def add_calculated_to_cart(callback: types.CallbackQuery, state: FSMContext):
    """Добавление рассчитанного товара в корзину"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Добавить рассчитанный товар в корзину")
    
    # Получаем данные расчета
    data = await state.get_data()
    original_price = data.get('original_price', 0)
    final_price = data.get('final_price', 0)
    delivery_type = data.get('delivery_type', '')
    weight = data.get('weight', 0)
    product_link = data.get('product_link', '')
    product_features = data.get('product_features', '')  # Получаем комментарий пользователя
    
    # Добавляем отладочную информацию
    logging.info(f"Добавление рассчитанного товара в корзину:")
    logging.info(f"original_price: {original_price}")
    logging.info(f"final_price: {final_price}")
    logging.info(f"delivery_type: {delivery_type}")
    logging.info(f"weight: {weight}")
    logging.info(f"product_link: {product_link}")
    logging.info(f"product_features: {product_features}")
    
    # Рассчитываем все нужные параметры
    from price_calculator import get_delivery_cost, get_delivery_type_name, format_price_display
    delivery_cost_from_germany = get_delivery_cost(delivery_type, weight)
    original_price_without_vat = round(original_price * 0.81, 2)
    delivery_cost_to_warehouse = 5.00
    subtotal = original_price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
    service_commission = round(subtotal * 0.15, 2)
    total = round(subtotal + service_commission, 2)
    
    # Получаем красивое название типа доставки
    delivery_type_name = get_delivery_type_name(delivery_type)
    
    # Создаем товар для корзины с ВСЕМИ нужными параметрами
    calculated_product = {
        'title': f"Товар (цена: {format_price_display(original_price)})",
        'price': format_price_display(original_price),
        'source': 'Расчет пользователя',
        'link': product_link,
        'original_price': original_price,
        'original_price_without_vat': original_price_without_vat,
        'delivery_type': delivery_type_name,  # Сохраняем красивое название
        'delivery_type_code': delivery_type,  # Сохраняем технический код для расчетов
        'weight': weight,
        'delivery_cost_from_germany': delivery_cost_from_germany,
        'delivery_cost_to_warehouse': delivery_cost_to_warehouse,
        'service_commission': service_commission,
        'total': total,
        'calculated_price': data.get('calculated_price', 0),
        'product_features': product_features  # Сохраняем комментарий пользователя
    }
    
    # Добавляем в корзину
    cart_data = await state.get_data()
    cart = cart_data.get('cart', [])
    logging.info(f"Размер корзины до добавления: {len(cart)}")
    cart.append(calculated_product)
    await state.update_data(cart=cart)
    
    # Дополнительная проверка сохранения
    await asyncio.sleep(0.1)  # Небольшая задержка для гарантии сохранения
    verification_data = await state.get_data()
    verification_cart = verification_data.get('cart', [])
    logging.info(f"Проверка сохранения - размер корзины: {len(verification_cart)}")
    
    # Проверяем, что товар действительно добавился
    cart_after = await state.get_data()
    cart_final = cart_after.get('cart', [])
    logging.info(f"Размер корзины после добавления: {len(cart_final)}")
    logging.info(f"Последний добавленный товар: {calculated_product.get('title', 'Без названия')}")
    
    # Очищаем данные расчета, но оставляем корзину
    await state.update_data({
        'cart': cart_final,
        'original_price': None,
        'final_price': None,
        'delivery_type': None,
        'weight': None,
        'product_link': None,
        'product_features': None  # Очищаем комментарий из состояния
    })
    
    # Отправляем новое сообщение вместо редактирования
    await callback.answer(
        "✅ Ваш товар добавлен в корзину! \n\n"
        "Для оформления заказа перейдите в меню \"🛍 Корзина\"",
        parse_mode="Markdown"
    )


@dp.callback_query(lambda c: c.data == "back_to_delivery_type_order")
async def back_to_delivery_type_order_handler(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору типа доставки в процессе оформления заказа"""
    await callback.answer()
    
    # Получаем данные корзины
    data = await state.get_data()
    cart = data.get('cart', [])
    
    if not cart:
        await callback.message.edit_text(
            "🛒 Корзина пуста\n\n"
            "Добавьте товары из поиска, чтобы начать покупки!",
            reply_markup=get_back_keyboard()
        )
        return
    
    # Показываем товары в корзине с ссылками
    cart_text = "🛍 **Ваша корзина:**\n\n"
    
    for i, product in enumerate(cart, 1):
        cart_text += f"{i}. 🛍️ **{product['title']}**\n"
        cart_text += f"   💰 Цена: {product['price']}\n"
        cart_text += f"   🏪 Магазин: {product.get('source', 'Не указан')}\n"
        if product.get('link'):
            cart_text += f"   🔗 Ссылка: {product['link']}\n"
        cart_text += "\n"
    
    cart_text += f"📊 **Итого товаров:** {len(cart)} шт.\n\n"
    cart_text += "💡 Выберите тип доставки для расчета стоимости:"
    
    # Создаем клавиатуру для выбора типа доставки
    delivery_keyboard = get_delivery_type_keyboard()
    
    await callback.message.edit_text(cart_text, parse_mode="Markdown", reply_markup=delivery_keyboard)


@dp.callback_query(lambda c: c.data == "payment_ok")
async def payment_ok_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Ок, меня все устраивает'"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Ок, меня все устраивает")
    await callback.answer()
    
    # Начинаем процесс оформления заказа
    await state.set_state(OrderStates.waiting_for_name)
    await callback.message.answer("Пожалуйста, введите ФИО полностью как в паспорте (например Иванов Иван Иванович):")

@dp.callback_query(lambda c: c.data == "back_to_order")
async def back_to_order_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Назад' к заказу"""
    await callback.answer()
    
    # Возвращаемся к сообщению о способах оплаты
    payment_message = """
💳 Мы принимаем оплату в криптовалюте или картой иностранного банка
"""
    
    # Создаем клавиатуру с кнопками
    payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ок, меня все устраивает", callback_data="payment_ok")],
        [InlineKeyboardButton(text="❓ Помогите разобраться в криптовалюте", url="https://telegra.ph/Gajd-Kak-kupit-kriptovalyutu-na-Bybit-dlya-oplaty-uslug-ot-Pay4Way-06-27")]
    ])
    
    await callback.message.edit_text(payment_message, reply_markup=payment_keyboard)


@dp.callback_query(lambda c: c.data == "back_to_cart")
async def back_to_cart_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get('cart', [])
    rub_delivery_to_warehouse = f"{currency_service.convert_price(delivery_cost_to_warehouse):,.0f}".replace(',', ' ')
    if not cart:
        await callback.message.edit_text(
            "🛒 Корзина пуста\n\n"
            "Добавьте товар в корзину, чтобы начать покупки!"
        )
        await callback.answer()
        return
    cart_text = "🛒 Ваша корзина:\n\n"
    delivery_cost_to_warehouse = 5.00
    
    # Переменные для подсчета общей суммы
    total_euro = 0
    total_rub = 0
    
    for i, product in enumerate(cart):
        # Добавляем номер товара
        cart_text += f"Товар #{i+1}\n"
        
        # Используем сохранённые параметры или значения по умолчанию
        price_without_vat = product.get('original_price_without_vat', 0)
        if price_without_vat == 0:
            # Если нет сохранённого значения, рассчитываем из цены
            price = product.get('price', 0)
            if isinstance(price, str):
                price = price.replace('€', '').replace('$', '').replace('₽', '').replace(',', '.').strip()
            try:
                price_with_vat = float(price)
                price_without_vat = round(price_with_vat * 0.81, 2)
            except Exception:
                price_without_vat = 0.0
        
        rub_price_without_vat = currency_service.convert_price(price_without_vat)
        rub_delivery_to_warehouse = f"{currency_service.convert_price(delivery_cost_to_warehouse):,.0f}".replace(',', ' ')
        cart_text += (
            f"🪙 Стоимость товаров: €{price_without_vat} или {f'{rub_price_without_vat:,.0f}'.replace(',', ' ')}₽ (мы уже вычли НДС)\n\n"
        )
        cart_text += (
            f"🚚 Стоимость доставки от интернет-магазина до нашего склада в Германии: €{delivery_cost_to_warehouse:.2f} или {rub_delivery_to_warehouse}₽\n\n"
        )
        
        # Используем сохранённые параметры доставки
        delivery_type = product.get('delivery_type', 'Маленький пакет')
        weight = product.get('weight', 1.0)
        delivery_cost_from_germany = product.get('delivery_cost_from_germany', 12.94)
        rub_delivery_from_germany = f"{currency_service.convert_price(delivery_cost_from_germany):,.0f}".replace(',', ' ')
        rub_service_commission = f"{currency_service.convert_price(service_commission):,.0f}".replace(',', ' ')
        cart_text += (
            f"📦 Доставка из Германии до РФ:\n\n"
            f"Тип: {delivery_type}\n"
            f"Вес: {weight} кг\n"
            f"Стоимость доставки: €{delivery_cost_from_germany:.2f} или {rub_delivery_from_germany}₽\n\n"
        )
        
        # Используем сохранённые расчёты или рассчитываем заново
        if product.get('service_commission') and product.get('total'):
            service_commission = product.get('service_commission')
            total = product.get('total')
        else:
            subtotal = price_without_vat + delivery_cost_to_warehouse + delivery_cost_from_germany
            service_commission = round(subtotal * 0.15, 2)
            total = round(subtotal + service_commission, 2)
        
        cart_text += (
            f"💼 Комиссия нашего сервиса (15%): €{service_commission:.2f} или {rub_service_commission}₽\n\n"
        )
        if product.get('link'):
            cart_text += f"🔗 Ссылка на товар: {product['link']}\n\n"
        
        rub_total = currency_service.convert_price(total)
        cart_text += (
            f"💶 ИТОГО: €{total:.2f} или {f'{rub_total:,.0f}'.replace(',', ' ')}₽\n\n"
        )
        
        # Добавляем к общим суммам
        total_euro += total
        total_rub += rub_total
        
        # Добавляем разделитель между товарами
        if i < len(cart) - 1:
            cart_text += "─" * 30 + "\n\n"
    
    # Добавляем общую сумму, если товаров больше одного
    if len(cart) > 1:
        cart_text += "=" * 40 + "\n"
        cart_text += f"**ОБЩАЯ СУММА ЗАКАЗА:**\n"
        cart_text += f"💶 €{total_euro:.2f} или {f'{total_rub:,.0f}'.replace(',', ' ')}₽\n\n"
    
    # Создаем клавиатуру с кнопками удаления отдельных товаров
    keyboard_buttons = []
    
    # Добавляем кнопки удаления для каждого товара
    for i in range(len(cart)):
        keyboard_buttons.append([InlineKeyboardButton(text=f"🗑️ Удалить товар #{i+1}", callback_data=f"remove_item_{i}")])
    
    # Добавляем основные кнопки
    keyboard_buttons.append([
        InlineKeyboardButton(text="🗑️ Очистить корзину", callback_data="clear_cart"), 
        InlineKeyboardButton(text="💳 Оформить заказ", callback_data="order_from_cart")
    ])
    
    next_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(cart_text, reply_markup=next_keyboard, parse_mode=None)
    await callback.answer()

@dp.message(PriceCalculationStates.waiting_for_product_link)
async def handle_product_link(message: types.Message, state: FSMContext):
    """Обработка ввода ссылки на товар"""
    await log_user_action(message.from_user.id, message.from_user.username, f"Ввод ссылки на товар (обработчик 2): {message.text[:100]}")
    from price_calculator import format_price_display
    
    product_link = message.text.strip()
    
    # Простая проверка на ссылку
    if not (product_link.startswith('http://') or product_link.startswith('https://')):
        await message.answer(
            "❌ Ошибка!\n\n"
            "Пожалуйста, введите корректную ссылку на товар.\n"
            "Ссылка должна начинаться с http:// или https://\n\n"
            "Примеры:\n"
            "• https://www.amazon.de/product/...\n"
            "• https://www.ebay.de/itm/...\n"
            "• https://www.idealo.de/...",
            reply_markup=get_cancel_price_calculation_keyboard()
        )
        return
    
    # Получаем сохраненные данные расчета
    data = await state.get_data()
    original_price = data.get('original_price', 0)
    final_price = data.get('final_price', 0)
    delivery_type = data.get('delivery_type', '')
    weight = data.get('weight', 0)
    calculated_price = data.get('calculated_price', 0)
    calculated_price_without_vat = data.get('calculated_price_without_vat', 0)
    
    # Сохраняем ссылку на товар
    await state.update_data(product_link=product_link)
    
    await state.set_state(PriceCalculationStates.showing_result)
    
    # Формируем финальный результат с детальным расчетом
    from price_calculator import get_delivery_cost, get_delivery_type_name
    
    delivery_cost = get_delivery_cost(delivery_type, weight)
    delivery_type_name = get_delivery_type_name(delivery_type)
    
    # Формируем детальный расчет
    delivery_from_google = final_price - original_price
    price_without_vat_step = original_price - (original_price * 0.19)
    step3 = delivery_from_google + price_without_vat_step
    step4 = step3 + delivery_cost
    step5 = step4 * 0.15
    
    calculation_text = (
            f"💰 **ИТОГО:**\n\n"
            f"🪙 **Стоимость товара:** {format_price_with_rub(original_price)} (а могла бы быть {format_price_with_rub(original_price * 1.19)}, если бы мы не убрали НДС)\n\n"
            f"🚚 **Стоимость доставки до нашего склада в Германии:** {format_price_with_rub(delivery_from_google)}\n\n"
            f"📦 **Доставка из Германии до РФ:**\n"
            f"Тип: {delivery_type_name}\n"
            f"Вес: {weight} кг\n"
            f"Стоимость доставки: {format_price_with_rub(step4)}\n\n"
            f"💼 **Комиссия сервиса (15%):** {format_price_with_rub(step5)}\n\n"
            f"💶 **ИТОГО:** {format_price_with_rub(calculated_price)} (а могла бы быть {format_price_with_rub(calculated_price * 1.19)}). Экономия составляет {format_price_with_rub(calculated_price * 0.19)}"
        )
    
    await message.answer(
        calculation_text,
        reply_markup=get_add_to_cart_from_calculation_keyboard(),
        parse_mode="Markdown"
    )

async def main():
    """Главная функция запуска бота"""
    logging.info("Запуск бота...")
    
    # Удаляем webhook и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()


# Обработчик всех остальных сообщений (должен быть в самом конце)
@dp.message()
async def echo_message(message: types.Message):
    """Обработчик всех остальных сообщений"""
    await log_user_action(message.from_user.id, message.from_user.username, f"Неопознанное сообщение: {message.text[:50] if message.text else 'Не текст'}")
    await message.answer("Пожалуйста, используйте кнопки в меню или под сообщением !", parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "order_from_cart")
async def start_order_from_cart(callback: types.CallbackQuery, state: FSMContext):
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Оформить заказ")
    # Показываем сообщение о способах оплаты
    payment_message = (
        "💳 Мы принимаем оплату в криптовалюте или картой иностранного банка"
    )
    payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ок, меня все устраивает", callback_data="payment_ok")],
        [InlineKeyboardButton(
            text="❓ Помогите разобраться в криптовалюте",
            url="https://telegra.ph/Gajd-Kak-kupit-kriptovalyutu-na-Bybit-dlya-oplaty-uslug-ot-Pay4Way-06-27"
        )]
    ])
    await callback.message.answer(payment_message, reply_markup=payment_keyboard)

@dp.callback_query(lambda c: c.data == "no_link")
async def no_link_callback(callback: types.CallbackQuery):
    """Обработчик для случая отсутствия ссылки на товар"""
    await log_user_action(callback.from_user.id, callback.from_user.username, "Кнопка: Отсутствует ссылка")
    await callback.answer("⚠️ Попробуйте другой товар или новый поиск.")

if __name__ == "__main__":
    asyncio.run(main()) 