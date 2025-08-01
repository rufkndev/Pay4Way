import os
import urllib.parse
import re
from scrapingbee import ScrapingBeeClient
from bs4 import BeautifulSoup

SCRAPINGBEE_API_KEY = "Q0XYGG0L76TOEDTE4GGJSU219JC6O8IM6IYFY0UATWAD7J002N758IUYQ2TLFSX8WF47QSNQBJNZYG9Q"

def search_idealo_products(query, limit=10):
    """
    Поиск товаров на Idealo через ScrapingBee. Возвращает список из 10 товаров: название, цена, картинка, ссылка, количество предложений.
    """
    try:
        url = f"https://www.idealo.de/preisvergleich/MainSearchProductCategory.html?q={urllib.parse.quote(query)}"
        client = ScrapingBeeClient(api_key=SCRAPINGBEE_API_KEY)
        params = {
            'premium_proxy': True,
            'country_code': 'de',
            'wait': 5000,
            'wait_for': '.sr-resultList__item_m6xdA',
            'wait_browser': 'networkidle2',
            'block_resources': False
        }
        
        response = client.get(url, params=params)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            products = soup.find_all('div', class_='sr-resultList__item_m6xdA')
            result_products = []
            for idx, item in enumerate(products[:limit]):
                # Ссылка на товар
                link_tag = item.find('a', href=True)
                link_url = link_tag['href'] if link_tag and link_tag.has_attr('href') else ''
                if link_url and not link_url.startswith('http'):
                    link_url = 'https://www.idealo.de' + link_url

                # Название товара
                title_div = item.find('div', class_='sr-productSummary__title_f5flP')
                if title_div:
                    title = title_div.get_text(strip=True)
                else:
                    # fallback: текст ссылки или alt картинки
                    title = link_tag.get_text(strip=True) if link_tag else ''
                    if not title:
                        img = item.find('img')
                        if img and img.has_attr('alt'):
                            title = img['alt']
                    title = title or 'Без названия'

                # Цена
                price_div = item.find('div', class_='sr-detailedPriceInfo__price_sYVmx')
                if price_div:
                    price_text = price_div.get_text(strip=True)
                    price = price_text.replace('ab', '').strip()
                else:
                    price = 'Цена не указана'

                # Картинка
                img = item.find('img')
                img_url = img['src'] if img and img.has_attr('src') else ''

                # Количество предложений
                offers_div = item.find('div', class_='sr-detailedPriceInfo__offerCount_PJByo')
                offers_count = offers_div.get_text(strip=True) if offers_div else 'Нет данных'
                # Убираем слово 'Angebote' из количества предложений
                if isinstance(offers_count, str):
                    offers_count = offers_count.replace('Angebote', '').strip()

                product = {
                    "title": title,
                    "link": link_url,
                    "img": img_url,
                    "image": img_url,
                    "price": price,
                    "offers_count": offers_count,
                    "source": "Idealo",
                    "rating": "⭐"
                }
                result_products.append(product)
            return result_products
        else:
            print(f"Ошибка ScrapingBee: {response.text}")
            return []
    except Exception as e:
        print(f"Ошибка при поиске товаров: {e}")
        return []

