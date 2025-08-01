from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Inline клавиатуры
def get_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура бота"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Начать поиск", callback_data="start_search")],
        [InlineKeyboardButton(text="🧮 Рассчитать доставку", callback_data="calculate_price")],
        [InlineKeyboardButton(text="🛍 Корзина", callback_data="cart")],
        [InlineKeyboardButton(text="🚨 Поддержка", callback_data="contacts"), InlineKeyboardButton(text="❓ Кто мы", callback_data="about")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
    return keyboard

def get_help_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура помощи с кнопками 'Как пользоваться' и 'Как оплатить'"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Как пользоваться", callback_data="how_to_use")],
        [InlineKeyboardButton(text="💳 Как оплатить", callback_data="payment")]
    ])
    return keyboard


def get_about_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура о нас"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 О компании", callback_data="about_company")],
        [InlineKeyboardButton(text="👥 Наша команда", callback_data="about_team")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="about_stats")],
        [InlineKeyboardButton(text="🎯 Наши цели", callback_data="about_goals")],
    ])
    return keyboard

def get_product_navigation_keyboard(current_index: int, total_results: int, product_index: int, product_link: str) -> InlineKeyboardMarkup:
    """Клавиатура навигации по товарам с новыми кнопками"""
    keyboard_buttons = []
    
    # Кнопки навигации
    nav_row = []
    if current_index > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"nav_{current_index-1}"))
    if current_index < total_results - 1:
        nav_row.append(InlineKeyboardButton(text="Еще товары ➡️", callback_data=f"nav_{current_index+1}"))
    
    if nav_row:
        keyboard_buttons.append(nav_row)
    
    # Основные кнопки действий
    keyboard_buttons.append([
        InlineKeyboardButton(text="🛍️ Посмотреть товар", url=product_link) if product_link else InlineKeyboardButton(text="🛍️ Посмотреть товар", callback_data="no_link")
    ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="🧮 Рассчитать доставку", callback_data="start_price_calculation")
    ])
    
    
    # Кнопка нового поиска
    keyboard_buttons.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="start_search")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура с кнопкой назад"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_action")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

def get_cart_reply_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗑️ Очистить корзину"), KeyboardButton(text="💳 Оформить заказ")],
        ],
        resize_keyboard=True,
    )
    return keyboard

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Поиск товаров")],
            [KeyboardButton(text="🧮 Рассчитать доставку")],
            [KeyboardButton(text="🛍 Корзина")],
            [KeyboardButton(text="🚨 Поддержка"), KeyboardButton(text="❓ Кто мы")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Для поиска товара и расчета стоимости доставки нажмите кнопку справа в строке ввода текста"
    )
    return keyboard

# Закомментировано - теперь автоматически выбирается EMS
# def get_delivery_type_keyboard() -> InlineKeyboardMarkup:
#     """Клавиатура для выбора типа доставки"""
#     keyboard = InlineKeyboardMarkup(inline_keyboard=[
#         # [InlineKeyboardButton(text="🛍 До 2 кг и длиной до 600 мм", callback_data="delivery_small_package")],
#         # [InlineKeyboardButton(text="📦 Стандарт - длина до 1 005 мм", callback_data="delivery_standard_package")],
#         [InlineKeyboardButton(text="🚪🔜🚪 EMS – длина до 1 500 мм", callback_data="delivery_ems")],
#     ])
#     return keyboard

# def get_delivery_type_keyboard_for_calculation() -> InlineKeyboardMarkup:
#     """Клавиатура для выбора типа доставки в процессе расчета цены"""
#     keyboard = InlineKeyboardMarkup(inline_keyboard=[
#         # [InlineKeyboardButton(text="🛍 До 2 кг и длиной до 600 мм", callback_data="delivery_small_package")],
#         # [InlineKeyboardButton(text="📦 Стандарт - длина до 1 005 мм", callback_data="delivery_standard_package")],
#         [InlineKeyboardButton(text="🚪🔜🚪 EMS – длина до 1 500 мм", callback_data="delivery_ems")],
#     ])
#     return keyboard

def get_weight_keyboard(delivery_type: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора веса товара"""
    from price_calculator import get_available_weights, get_delivery_cost
    
    weights = get_available_weights(delivery_type)
    keyboard_buttons = []
    
    # Создаем кнопки для каждого доступного веса
    for weight in weights:
        delivery_cost = get_delivery_cost(delivery_type, weight)
        button_text = f"⚖️ {weight} кг (€{delivery_cost:.2f})"
        callback_data = f"weight_{delivery_type}_{weight}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    
    # Добавляем кнопку назад к вводу цены
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад к цене", callback_data="back_to_price_input")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def get_weight_keyboard_for_order(delivery_type: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора веса товара при оформлении заказа"""
    from price_calculator import get_available_weights, get_delivery_cost
    
    weights = get_available_weights(delivery_type)
    keyboard_buttons = []
    
    # Создаем кнопки для каждого доступного веса
    for weight in weights:
        delivery_cost = get_delivery_cost(delivery_type, weight)
        button_text = f"⚖️ {weight} кг (€{delivery_cost:.2f})"
        callback_data = f"weight_{delivery_type}_{weight}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    
    # Добавляем кнопку назад к выбору типа доставки
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад к выбору типа доставки", callback_data="back_to_delivery_type_order")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def get_payment_method_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора способа оплаты"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта иностранного банка", callback_data="payment_card")],
        [InlineKeyboardButton(text="₿ Криптовалюта", callback_data="payment_crypto")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_price_calculation")]
    ])
    return keyboard

def get_order_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения заказа"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data="confirm_order"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")
        ],
        [InlineKeyboardButton(text="🔄 Заполнить заново", callback_data="restart_order")]
    ])
    return keyboard

def get_price_calculation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для начала расчета цены товара"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Рассчитать цену", callback_data="start_price_calculation")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

def get_cancel_price_calculation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для отмены расчета цены"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти в главное меню 🏠", callback_data="back_to_main")]
    ])
    return keyboard

def get_add_to_cart_from_calculation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для добавления товара в корзину после расчета"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Добавить в корзину", callback_data="select_quantity_calculated")],
        [InlineKeyboardButton(text="🛍 Перейти в корзину", callback_data="cart")],
        [InlineKeyboardButton(text="🧮 Рассчитать доставку еще одного товара", callback_data="calculate_price_again_product")],
    ])
    return keyboard

def get_quantity_keyboard(product_type: str = "search") -> InlineKeyboardMarkup:
    """Клавиатура только с кнопкой Назад - количество вводится вручную"""
    keyboard_buttons = []
    
    # Добавляем только кнопку "Назад"
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_product")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
