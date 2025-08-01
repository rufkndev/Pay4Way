#!/usr/bin/env python3
"""
Утилиты для форматирования цен и итоговых сумм
"""

from services.currency_service import currency_service

def format_price_with_rub(price_eur: float) -> str:
    """
    Форматирует цену в евро с конвертацией в рубли
    """
    return currency_service.format_price_rub(price_eur)

def format_total_with_savings(total_cost: float, total_with_vat: float, savings: float) -> str:
    """
    Форматирует итоговую сумму с экономией в рублях
    """
    total_cost_rub = currency_service.convert_price(total_cost, "EUR", "RUB")
    total_with_vat_rub = currency_service.convert_price(total_with_vat, "EUR", "RUB")
    savings_rub = currency_service.convert_price(savings, "EUR", "RUB")
    
    if total_cost_rub and total_with_vat_rub and savings_rub:
        return f"€{total_cost:.2f} (≈ {total_cost_rub:.0f} ₽) (а могла бы быть €{total_with_vat:.2f} (≈ {total_with_vat_rub:.0f} ₽)). Экономия составляет €{savings:.2f} (≈ {savings_rub:.0f} ₽)"
    else:
        return f"€{total_cost:.2f} (а могла бы быть €{total_with_vat:.2f}).\n Экономия составила €{savings:.2f} за счет вычета нами суммы европейского НДС" 