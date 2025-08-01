"""
Обработчики для расчета цены товара
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command

from keyboards import (
    get_price_calculation_keyboard,
    get_cancel_price_calculation_keyboard,
    get_add_to_cart_from_calculation_keyboard,
    get_delivery_type_keyboard,
    get_delivery_type_keyboard_for_calculation,
    get_weight_keyboard,
    get_back_keyboard
)
from price_calculator import (
    calculate_item_price,
    extract_price_value,
    get_delivery_type_name,
    get_delivery_cost,
    format_price_display
)

router = Router()

class PriceCalculationStates(StatesGroup):
    """Состояния для диалога расчета цены"""
    waiting_for_original_price = State()
    waiting_for_final_price = State()
    waiting_for_delivery_type = State()
    waiting_for_weight = State()
    showing_result = State()

# Словарь для хранения данных расчета
calculation_data = {}



@router.callback_query(F.data == "start_price_calculation")
async def start_price_calculation(callback: CallbackQuery, state: FSMContext):
    """Начало диалога расчета цены"""
    await callback.answer()
    
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    # Очищаем данные предыдущего расчета
    calculation_data.clear()
    await state.clear()
    
    # Восстанавливаем корзину
    await state.update_data(cart=cart)
    
    await state.set_state(PriceCalculationStates.waiting_for_original_price)
    
    await callback.message.edit_text(
        "💰 **Цена товара**\n\n"
        "Введите цену товара (только стоимость самого товара).\n\n"
      
        "❌ Для отмены нажмите кнопку ниже:",
        reply_markup=get_cancel_price_calculation_keyboard()
    )

@router.message(PriceCalculationStates.waiting_for_original_price)
async def handle_original_price(message: Message, state: FSMContext):
    """Обработка ввода цены товара"""
    price_text = message.text.strip()
    
    # Извлекаем числовое значение цены
    original_price = extract_price_value(price_text)
    
    if original_price is None or original_price <= 0:
        await message.answer(
            "❌ **Ошибка!**\n\n"
            "Пожалуйста, введите корректную цену товара.\n"
            "Примеры: 29.99, €29.99, $29.99",
            reply_markup=get_cancel_price_calculation_keyboard()
        )
        return
    
    # Сохраняем цену товара
    calculation_data['original_price'] = original_price
    
    await state.set_state(PriceCalculationStates.waiting_for_final_price)
    
    await message.answer(
        f"✅ **Цена товара принята:** {format_price_display(original_price)}\n\n"
        "💰 **Цена товара вместе с доставкой**\n\n"
        "✅Средняя стоимость доставки товара от интернет-магазина до нашего склада в Германии: €5.00, которые уже включены в тариф доставки.\n\n"
        "❗️ Если доставка интернет-магазина бесплатная, то мы уменьшим стоимость доставки на €5.00. Если стоимость более €5.00, то мы скорректируем стоимость доставки на эту сумму.\n\n"
        "Теперь введите **цену товара вместе с доставкой** из магазина.\n\n"
        "Примеры:\n"
        "• 39.99\n"
        "• €39.99\n"
        "• $39.99\n\n"
        "❌ Для отмены нажмите кнопку ниже:",
        reply_markup=get_cancel_price_calculation_keyboard()
    )

@router.message(PriceCalculationStates.waiting_for_final_price)
async def handle_final_price(message: Message, state: FSMContext):
    """Обработка ввода итоговой цены"""
    price_text = message.text.strip()
    
    # Извлекаем числовое значение цены
    final_price = extract_price_value(price_text)
    
    if final_price is None or final_price <= 0:
        await message.answer(
            "❌ **Ошибка!**\n\n"
            "Пожалуйста, введите корректную итоговую цену.\n"
            "Примеры: 39.99, €39.99, $39.99",
            reply_markup=get_cancel_price_calculation_keyboard()
        )
        return
    
    # Проверяем, что итоговая цена больше или равна цене товара
    original_price = calculation_data.get('original_price', 0)
    if final_price < original_price:
        await message.answer(
            "❌ **Ошибка!**\n\n"
            f"Итоговая цена ({format_price_display(final_price)}) не может быть меньше цены товара ({format_price_display(original_price)}).\n"
            "Пожалуйста, проверьте данные и введите корректную итоговую цену.",
            reply_markup=get_cancel_price_calculation_keyboard()
        )
        return
    
    # Сохраняем итоговую цену
    calculation_data['final_price'] = final_price
    
    await state.set_state(PriceCalculationStates.waiting_for_delivery_type)
    
    await message.answer(
        f"✅ **Итоговая цена принята:** {format_price_display(final_price)}\n\n"
        "📦 **Выбор типа доставки из Германии до России**\n\n"
        "🚚 Теперь выберите тип отправления из Германии до России:",
        reply_markup=get_delivery_type_keyboard_for_calculation()
    )

@router.callback_query(F.data == "cancel_price_calculation")
async def cancel_price_calculation(callback: CallbackQuery, state: FSMContext):
    """Отмена расчета цены"""
    await callback.answer()
    
    # Сохраняем корзину перед очисткой состояния
    current_data = await state.get_data()
    cart = current_data.get('cart', [])
    
    calculation_data.clear()
    await state.clear()
    
    # Восстанавливаем корзину
    await state.update_data(cart=cart)
    
    await callback.message.edit_text(
        "❌ Расчет цены отменен.\n\n"
        "Вы можете начать новый расчет в любое время.",
        reply_markup=get_back_keyboard()
    )



@router.callback_query(F.data == "back_to_delivery_type")
async def back_to_delivery_type(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору типа доставки"""
    await callback.answer()
    
    await state.set_state(PriceCalculationStates.waiting_for_delivery_type)
    
    await callback.message.edit_text(
        "📦 Выберите тип доставки\n\n"
        "Выберите подходящий тип доставки до России:",
        reply_markup=get_delivery_type_keyboard_for_calculation()
    )