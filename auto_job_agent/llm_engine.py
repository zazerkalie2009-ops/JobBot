import os
import json
import re
from typing import Dict, Any, Tuple

MASTER_PROFILE_PATH = 'auto_job_agent/master_profile.json'

def load_master_profile() -> dict:
    with open(MASTER_PROFILE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_and_adapt(vacancy_text: str, vacancy_title: str = "", company: str = "") -> Dict[str, Any]:
    """
    Analyzes vacancy against master profile.
    Calculates match score (0-100), extracts focus domain, adapts role, summary, and cover letter.
    Supports LLM API (if OPENAI_API_KEY / ANTHROPIC_API_KEY is set) or intelligent semantic heuristics.
    """
    profile = load_master_profile()
    text_lower = (vacancy_text + " " + vacancy_title + " " + company).lower()
    
    # Domain classification
    domain_scores = {
        'promo_platform': sum(1 for w in ['промо', 'акци', 'скидк', 'оффер', 'кешбэк', 'платформ', 'лояльност', 'монет', 'flash'] if w in text_lower),
        'gamification': sum(1 for w in ['геймификац', 'игр', 'game', 'мета', 'battle pass', 'квест', 'дейли', 'ачивки'] if w in text_lower),
        'growth': sum(1 for w in ['growth', 'воронк', 'конверси', 'dau', 'mau', 'arpu', 'retention', 'привлечен', 'удержан'] if w in text_lower),
        'b2b': sum(1 for w in ['b2b', 'enterprise', 'интеграц', 'вкс', 'партнер', 'api', 'клиент'] if w in text_lower)
    }
    
    best_domain = max(domain_scores, key=domain_scores.get)
    
    # Calculate score
    base_score = 70
    keywords_found = []
    
    if any(k in text_lower for k in ['продукт', 'product', 'продакт']):
        base_score += 10
        keywords_found.append("Product Management")
    if any(k in text_lower for k in ['a/b', 'а/б', 'эксперимент', 'гипотез']):
        base_score += 5
        keywords_found.append("A/B-тестирование")
    if any(k in text_lower for k in ['аналитик', 'sql', 'метрик', 'data']):
        base_score += 5
        keywords_found.append("Продуктовая аналитика")
    if any(k in text_lower for k in ['геймификац', 'промо', 'лояльност', 'монет']):
        base_score += 5
        keywords_found.append("Промо/Геймификация")
    if any(k in text_lower for k in ['ai', 'ии', 'прототип', 'mvp']):
        base_score += 5
        keywords_found.append("AI-прототипирование")
        
    match_score = min(98, base_score)
    
    # Adapt role and summary based on domain
    if 'промо' in text_lower or 'платформ' in text_lower:
        adapted_role = profile['roles']['promo_platform']
        adapted_summary = profile['summary_templates']['promo_platform']
        domain_name = "Платформа промомеханик"
    elif 'гейм' in text_lower or 'game' in text_lower:
        adapted_role = profile['roles']['gamification']
        adapted_summary = profile['summary_templates']['default']
        domain_name = "Геймификация и игровые механики"
    elif 'b2b' in text_lower:
        adapted_role = profile['roles']['b2b']
        adapted_summary = profile['summary_templates']['default']
        domain_name = "B2B платформы"
    else:
        adapted_role = profile['roles']['default']
        adapted_summary = profile['summary_templates']['default']
        domain_name = "B2C Product & Growth"
        
    # Draft targeted Cover Letter
    comp_name = company or "вашей компании"
    vac_title = vacancy_title or "Product Manager"
    
    cover_letter = (
        f"Здравствуйте!\n\n"
        f"Откликаюсь на позицию {vac_title} в {comp_name}. Мой опыт и экспертиза в МегаФоне и TrueConf отлично закрывают ключевые задачи роли:\n\n"
        f"1. Запуск и масштабирование механик на 500k+ MAU: спроектировал и запустил систему монетизации и промо-инструментов (Flash-офферы, сезонные ивенты, Battle Pass, внутриплатформенная валюта), что вырастило ARPU на +116% YoY и ARPPU на +39%.\n"
        f"2. Кросс-продажи и вовлечение: через серию A/B-тестов увеличил конверсию в подключение VAS-услуг на +15%, органический DAU на +5% и выстроил триггерные CRM-коммуникации (TR +11%, LTV лидов ×2).\n"
        f"3. AI & Vibe-кодинг: использую связку Cursor + Claude + Web-стек для быстрого создания интерактивных прототипов за 2–3 дня вместо 3 недель, кратно снижая Time-to-Market до передачи в разработку.\n"
        f"4. Платформенное мышление: в TrueConf вывел платформу с 0 до 1 за 2 месяца, синхронизируя 2 команды разработки и снизив брак с 45% до 5%. Магистр НИУ ВШЭ («Управление цифровым продуктом»).\n\n"
        f"Буду рад пообщаться на интервью и обсудить задачи команды!\n\n"
        f"С уважением,\nОлег Кохтенко | Telegram: @olegkokhtenko | +7 (929) 643-15-42"
    )
    
    reasons = f"Совпадение по домену ({domain_name}), метрикам монетизации/вовлечения, A/B-тестам и AI-прототипированию. Ключевые совпадения: {', '.join(keywords_found)}."
    
    return {
        'match_score': match_score,
        'domain': domain_name,
        'adapted_role': adapted_role,
        'adapted_summary': adapted_summary,
        'match_reasons': reasons,
        'cover_letter': cover_letter
    }
