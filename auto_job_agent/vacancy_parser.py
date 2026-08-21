import os
import re
import json
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_title_and_company(text: str, default_company: str = "IT Компания") -> tuple:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return "Product Manager", default_company
        
    title = "Product Manager"
    company = default_company
    
    # 1. Try to find the exact role line
    for line in lines[:5]:
        cleaned = re.sub(r'^[^\w\s\(\)\-\/\+]+', '', line).strip()
        cleaned = re.sub(r'^[•\-\*\#\d\.\s]+', '', cleaned).strip()
        cleaned_low = cleaned.lower()
        if any(k in cleaned_low for k in ['менеджер продукта', 'product manager', 'продакт', 'product lead', 'cpo', 'head of product', 'product owner']):
            if 5 < len(cleaned) < 90:
                title = cleaned
                break
                
    # If no PM line found, take first non-empty clean line
    if title == "Product Manager" and lines:
        cleaned_first = re.sub(r'^[^\w\s\(\)\-\/\+]+', '', lines[0]).strip()
        if 5 < len(cleaned_first) < 70:
            title = cleaned_first

    # 2. Detect company
    text_low = text.lower()
    if any(k in text_low for k in ['яндекс', 'yandex', 'ya.ru']):
        company = 'Яндекс'
    elif any(k in text_low for k in ['авито', 'avito']):
        company = 'Авито'
    elif any(k in text_low for k in ['тинькофф', 'т-банк', 't-bank', 'tinkoff']):
        company = 'Т-Банк'
    elif any(k in text_low for k in ['ozon', 'озон']):
        company = 'Ozon'
    elif any(k in text_low for k in ['vk', 'вконтакте', 'вк ']):
        company = 'VK'
    elif any(k in text_low for k in ['сбер', 'sber', 'сбермаркет', 'купер']):
        company = 'Сбер'
    elif any(k in text_low for k in ['мегафон', 'megafon']):
        company = 'МегаФон'
    elif any(k in text_low for k in ['мтс', 'mts']):
        company = 'МТС'
    elif any(k in text_low for k in ['альфа', 'alfa']):
        company = 'Альфа-Банк'
    elif any(k in text_low for k in ['x5', 'пятерочка', 'перекресток']):
        company = 'X5 Group'
        
    return title, company

def fetch_live_yandex_vacancies() -> List[Dict[str, Any]]:
    """
    Fetches official live Product Manager vacancies directly from Yandex Jobs API.
    """
    vacancies = []
    url = "https://yandex.ru/jobs/api/publications?professions=product-manager&page_size=20"
    try:
        with httpx.Client(timeout=8.0, headers=HEADERS) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('results', []):
                    vac_id = item.get('id')
                    title = item.get('title', 'Product Manager')
                    slug = item.get('publication_slug_url') or item.get('slug') or str(vac_id)
                    job_url = f"https://yandex.ru/jobs/vacancies/{slug}"
                    
                    # Fetch detailed description if available, or build from summary
                    desc_parts = [item.get('short_summary', '')]
                    if item.get('duties'):
                        desc_parts.append("Обязанности: " + str(item.get('duties')))
                    if item.get('key_qualifications'):
                        desc_parts.append("Требования: " + str(item.get('key_qualifications')))
                        
                    full_desc = "\n".join(desc_parts).strip() or title
                    
                    vacancies.append({
                        'source': 'Yandex Jobs (Официальный сайт)',
                        'external_id': f"yandex_api_{vac_id}",
                        'title': title,
                        'company': 'Яндекс',
                        'url': job_url,
                        'description': full_desc
                    })
    except Exception as e:
        print(f"Error fetching Yandex API vacancies: {e}")
        
    return vacancies

def fetch_live_telegram_channel_vacancies() -> List[Dict[str, Any]]:
    """
    Fetches real-time vacancies from public Telegram channel web previews.
    """
    vacancies = []
    channels = [
        ('ya_jobs_pm', 'Яндекс Вакансии'),
        ('product_jobs', 'Product Jobs'),
        ('remote_it_jobs', 'Remote IT')
    ]
    
    with httpx.Client(timeout=8.0, headers=HEADERS) as client:
        for ch, ch_name in channels:
            try:
                resp = client.get(f"https://t.me/s/{ch}")
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    wraps = soup.find_all('div', class_='tgme_widget_message_wrap')
                    for wrap in wraps:
                        text_div = wrap.find('div', class_='tgme_widget_message_text')
                        if not text_div:
                            continue
                        text = text_div.get_text('\n', strip=True)
                        text_low = text.lower()
                        
                        if any(k in text_low for k in ['product manager', 'менеджер продукта', 'продакт', 'product owner', 'product lead']):
                            title, company = clean_title_and_company(text, default_company=ch_name)
                            
                            # Extract link if present in message
                            a_tag = text_div.find('a', href=True)
                            job_url = a_tag['href'] if a_tag and a_tag['href'].startswith('http') else f"https://t.me/{ch}"
                            
                            msg_id_match = wrap.get('data-post') or f"{ch}_{hash(text)}"
                            
                            vacancies.append({
                                'source': f"Telegram @{ch}",
                                'external_id': f"tg_{msg_id_match}",
                                'title': title,
                                'company': company,
                                'url': job_url,
                                'description': text
                            })
            except Exception as e:
                print(f"Error fetching TG @{ch}: {e}")
                
    return vacancies

def get_all_live_vacancies() -> List[Dict[str, Any]]:
    """
    Combines live vacancies from all sources: Yandex Jobs API, Career Portals, and Telegram feeds.
    """
    all_vacs = []
    
    # 1. Official Yandex Jobs API
    ya_vacs = fetch_live_yandex_vacancies()
    all_vacs.extend(ya_vacs)
    
    # 2. Real-time Telegram job channels
    tg_vacs = fetch_live_telegram_channel_vacancies()
    all_vacs.extend(tg_vacs)
    
    return all_vacs
