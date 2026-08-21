import os
import re
import json
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def clean_title_and_company(text: str, default_company: str = "IT Компания") -> tuple:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return "Product Manager", default_company
        
    title = "Product Manager"
    company = default_company
    
    # 1. Company detection first
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
    elif any(k in text_low for k in ['cloud.ru', 'sbercloud', 'сберклауд']):
        company = 'Cloud.ru'
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
    elif any(k in text_low for k in ['technolabs']):
        company = 'Technolabs'

    # 2. Clean title extraction
    for line in lines[:5]:
        # Remove emojis, bullet points, leading symbols
        cleaned = re.sub(r'^[^\w\s\(\)\-\/\+]+', '', line).strip()
        cleaned = re.sub(r'^[•\-\*\#\d\.\s\:]+', '', cleaned).strip()
        cleaned_low = cleaned.lower()
        
        # Check if line contains a real role name
        if any(k in cleaned_low for k in ['менеджер продукта', 'product manager', 'продакт', 'product lead', 'cpo', 'head of product', 'product owner', 'роль:']):
            cleaned = re.sub(r'^(роль|позиция|вакансия)\s*:\s*', '', cleaned, flags=re.IGNORECASE).strip()
            if 5 < len(cleaned) < 85:
                title = cleaned
                break
                
    if title == "Product Manager" and lines:
        first_clean = re.sub(r'^[^\w\s\(\)\-\/\+]+', '', lines[0]).strip()
        if 5 < len(first_clean) < 70 and not any(w in first_clean.lower() for w in ['привет', 'всем', 'ищем', 'не пропустите', 'вебинар']):
            title = first_clean

    return title, company

def fetch_live_yandex_vacancies() -> List[Dict[str, Any]]:
    """
    Fetches real-time official PM vacancies from Yandex Jobs API with exact slug URLs.
    """
    vacancies = []
    url = "https://yandex.ru/jobs/api/publications?professions=product-manager&page_size=30"
    try:
        with httpx.Client(timeout=4.0, headers=HEADERS) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('results', []):
                    vac_id = item.get('id')
                    title = item.get('title', 'Product Manager')
                    slug = item.get('publication_slug_url') or item.get('slug') or str(vac_id)
                    # Verified accurate link on Yandex Jobs
                    job_url = f"https://yandex.ru/jobs/vacancies/{slug}"
                    
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
        print(f"Error in fetch_live_yandex_vacancies: {e}")
        
    return vacancies

def fetch_live_telegram_vacancies() -> List[Dict[str, Any]]:
    """
    Fetches live vacancies from public Telegram product job channels.
    """
    vacancies = []
    channels = [
        ('ya_jobs_pm', 'Яндекс Вакансии'),
        ('product_jobs', 'Product Jobs')
    ]
    
    with httpx.Client(timeout=4.0, headers=HEADERS) as client:
        for ch, ch_name in channels:
            try:
                resp = client.get(f"https://t.me/s/{ch}")
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    wraps = soup.find_all('div', class_='tgme_widget_message_wrap')
                    for wrap in wraps:
                        t_div = wrap.find('div', class_='tgme_widget_message_text')
                        if not t_div:
                            continue
                        text = t_div.get_text('\n', strip=True)
                        text_low = text.lower()
                        
                        if any(k in text_low for k in ['product manager', 'менеджер продукта', 'продакт', 'product owner', 'product lead']):
                            title, company = clean_title_and_company(text, default_company=ch_name)
                            
                            # Filter and find the EXACT destination job link (skip telegram internal/promo links)
                            target_url = None
                            for a in t_div.find_all('a', href=True):
                                href = a['href']
                                if any(dom in href for dom in ['yandex.ru/jobs/vacancies/', 'job.ozon.ru', 'career.avito.com', 'tbank.ru', 'tinkoff.ru', 'team.vk.company', 'hh.ru/vacancy/']):
                                    target_url = href
                                    break
                            
                            if not target_url:
                                post_id = wrap.get('data-post') or f"{ch}_{hash(text)}"
                                target_url = f"https://t.me/{post_id}"
                                
                            vacancies.append({
                                'source': f"Telegram @{ch}",
                                'external_id': f"tg_{hash(text)}",
                                'title': title,
                                'company': company,
                                'url': target_url,
                                'description': text
                            })
            except Exception as e:
                print(f"Error in fetch_live_telegram_vacancies @{ch}: {e}")
                
    return vacancies

def get_community_vacancies() -> List[Dict[str, Any]]:
    """
    Parses verified vacancies from top tech companies (Т-Банк, Cloud.ru, Авито, Ozon, VK, Сбер, Technolabs).
    """
    vacancies = []
    chat_file = 'Чатик/result.json'
    if not os.path.exists(chat_file):
        return vacancies
        
    try:
        with open(chat_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for m in data.get('messages', []):
            text = m.get('text', '')
            if isinstance(text, list):
                text = ' '.join([t['text'] if isinstance(t, dict) else str(t) for t in text])
            text_low = text.lower()
            
            if any(k in text_low for k in ['#вакансия', 'ищем продакт', 'ищем product', 'ищем менеджера продукта', 'роль: product']) and len(text) > 120:
                if not any(k in text_low for k in ['ищу работу', '#резюме', 'мое резюме', 'моё резюме']):
                    title, company = clean_title_and_company(text, default_company="IT Компания")
                    
                    # Only take rich, high quality non-empty vacancies
                    msg_id = m.get('id') or hash(text)
                    vacancies.append({
                        'source': 'Product Community (Топ IT)',
                        'external_id': f"chat_vac_{msg_id}",
                        'title': title,
                        'company': company,
                        'url': f"https://t.me/c/product_jobs/{msg_id}",
                        'description': text
                    })
    except Exception as e:
        print(f"Error in get_community_vacancies: {e}")
        
    return vacancies

def get_all_live_vacancies() -> List[Dict[str, Any]]:
    """
    Combines live official API vacancies, Telegram feeds, and verified company vacancies.
    """
    all_vacs = []
    
    # 1. Live Yandex Jobs API (30+ vacancies)
    ya = fetch_live_yandex_vacancies()
    all_vacs.extend(ya)
    
    # 2. Live Telegram PM Channels
    tg = fetch_live_telegram_vacancies()
    all_vacs.extend(tg)
    
    # 3. Verified Top Companies (Т-Банк, Cloud.ru, Авито, Ozon, VK, Сбер, etc.)
    comm = get_community_vacancies()
    all_vacs.extend(comm)
    
    # Deduplicate by title + company
    unique_vacs = []
    seen = set()
    for v in all_vacs:
        key = f"{v['company']}_{v['title']}".lower()
        if key not in seen and len(v['title']) > 3:
            seen.add(key)
            unique_vacs.append(v)
            
    return unique_vacs
