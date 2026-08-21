import os
import re
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from auto_job_agent.config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, HEADLESS_BROWSER
from auto_job_agent.database import (
    init_db, save_vacancy, get_vacancy, get_pending_vacancies, update_status
)
from auto_job_agent.llm_engine import load_master_profile, analyze_and_adapt
from auto_job_agent.docx_generator import build_resume_docx
from auto_job_agent.vacancy_parser import get_all_live_vacancies, clean_title_and_company
from auto_job_agent.browser_applier import apply_to_yandex_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN or "DUMMY_TOKEN")
dp = Dispatcher()

def get_action_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Скачать DOCX", callback_data=f"get_cv:{vacancy_id}")
    builder.button(text="✉️ Письмо для копирования", callback_data=f"get_cl:{vacancy_id}")
    builder.button(text="🚀 Откликнуться (Playwright)", callback_data=f"apply:{vacancy_id}")
    builder.button(text="❌ Пропустить", callback_data=f"reject:{vacancy_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "👋 **Привет, Олег! Я твой персональный AI Job Agent.**\n\n"
        "Я умею:\n"
        "1. 🔍 **Искать реальные свежие вакансии** с официальных сайтов (Яндекс, Т-Банк, Cloud.ru, Авито, Ozon, VK) — команда `/scan`.\n"
        "2. 🎯 **Оценивать Match Score (0–100%)** под твой Master-профиль.\n"
        "3. 📝 **Генерировать адаптированное резюме (.docx)** и адресное сопроводительное письмо (в режиме копирования в 1 клик).\n"
        "4. 🚀 **Автоматически заполнять формы и отправлять отклики** через Playwright.\n\n"
        "💡 *Ты можешь отправить команду `/scan` или просто переслать мне ссылку/текст любой вакансии!*"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(Command("scan"))
async def cmd_scan(message: types.Message):
    status_msg = await message.answer("🔄 **Ищу свежие вакансии на карьерных сайтах компаний...**", parse_mode="Markdown")
    
    vacancies = get_all_live_vacancies()
    profile = load_master_profile()
    
    if not vacancies:
        await status_msg.edit_text("⚠️ Не удалось получить список вакансий. Попробуйте чуть позже.")
        return
        
    await status_msg.edit_text(f"🔍 Найдено **{len(vacancies)}** вакансий из разных компаний. Анализирую и генерирую материалы...", parse_mode="Markdown")
    
    # Analyze and sort by match score
    scored_vacs = []
    for v in vacancies:
        analysis = analyze_and_adapt(v['description'], v['title'], v['company'])
        scored_vacs.append((analysis['match_score'], v, analysis))
        
    scored_vacs.sort(key=lambda x: x[0], reverse=True)
    
    # Select diverse mix of companies (not just Yandex)
    selected_vacs = []
    seen_companies = {}
    
    for score, v, analysis in scored_vacs:
        comp = v['company']
        # Allow max 2 from Yandex, max 2 from others to keep diversity
        if seen_companies.get(comp, 0) < 2:
            seen_companies[comp] = seen_companies.get(comp, 0) + 1
            selected_vacs.append((score, v, analysis))
            if len(selected_vacs) >= 5:
                break
                
    for score, v, analysis in selected_vacs:
        # Generate tailored docx
        safe_comp = re.sub(r'[^\w]', '', v['company']) or 'Company'
        safe_title = re.sub(r'[^\w]', '_', v['title'])[:35].strip('_')
        docx_path = f"auto_job_agent/generated_resumes/CV_Oleg_{safe_comp}_{safe_title}.docx"
        
        build_resume_docx(docx_path, profile, {
            'role': analysis['adapted_role'],
            'summary': analysis['adapted_summary']
        })
        
        vac_id = save_vacancy(
            source=v['source'],
            external_id=v['external_id'],
            title=v['title'],
            company=v['company'],
            url=v['url'],
            description=v['description'],
            domain=analysis['domain'],
            match_score=analysis['match_score'],
            match_reasons=analysis['match_reasons'],
            adapted_role=analysis['adapted_role'],
            cover_letter=analysis['cover_letter'],
            docx_path=docx_path
        )
        
        card_text = (
            f"🎯 **{v['title']}**\n"
            f"🏢 **Компания:** {v['company']}\n"
            f"🌐 **Источник:** {v['source']}\n\n"
            f"📊 **Match Score:** **{analysis['match_score']}%**\n"
            f"🏷 **Домен:** {analysis['domain']}\n"
            f"💡 **Почему подходит:** {analysis['match_reasons']}\n\n"
            f"🔗 **[Перейти на сайт к вакансии]({v['url']})**\n\n"
            f"✉️ **Сопроводительное письмо (нажмите на текст ниже, чтобы скопировать):**\n"
            f"```\n{analysis['cover_letter']}\n```"
        )
        
        await message.answer(card_text, parse_mode="Markdown", reply_markup=get_action_keyboard(vac_id))
            
    await message.answer(f"✅ Показаны топ-**{len(selected_vacs)}** вакансий от разных компаний.", parse_mode="Markdown")

@dp.message(F.text)
async def handle_vacancy_text(message: types.Message):
    text = message.text
    if text.startswith("/"):
        return
        
    await message.answer("🧠 **Анализирую вакансию и готовлю кастомизированные материалы...**", parse_mode="Markdown")
    
    title, company = clean_title_and_company(text, default_company="IT Компания")
    profile = load_master_profile()
    analysis = analyze_and_adapt(text, title, company)
    
    safe_comp = re.sub(r'[^\w]', '', company) or 'Company'
    safe_title = re.sub(r'[^\w]', '_', title)[:35].strip('_')
    docx_path = f"auto_job_agent/generated_resumes/CV_Oleg_{safe_comp}_{safe_title}_{message.message_id}.docx"
    
    build_resume_docx(docx_path, profile, {
        'role': analysis['adapted_role'],
        'summary': analysis['adapted_summary']
    })
    
    vac_id = save_vacancy(
        source="Telegram Chat Input",
        external_id=f"chat_{message.message_id}_{hash(text)}",
        title=title,
        company=company,
        url="https://yandex.ru/jobs",
        description=text,
        domain=analysis['domain'],
        match_score=analysis['match_score'],
        match_reasons=analysis['match_reasons'],
        adapted_role=analysis['adapted_role'],
        cover_letter=analysis['cover_letter'],
        docx_path=docx_path
    )
    
    card_text = (
        f"🎯 **{title}**\n"
        f"🏢 **Компания:** {company}\n\n"
        f"📊 **Релевантность (Match Score):** **{analysis['match_score']}%**\n"
        f"🏷 **Целевой домен:** {analysis['domain']}\n"
        f"💡 **Фокус:** {analysis['match_reasons']}\n\n"
        f"✉️ **Сопроводительное письмо (нажмите на текст ниже, чтобы скопировать):**\n"
        f"```\n{analysis['cover_letter']}\n```"
    )
    
    await message.answer(card_text, parse_mode="Markdown", reply_markup=get_action_keyboard(vac_id))

@dp.callback_query(F.data.startswith("get_cv:"))
async def cb_get_cv(callback: types.CallbackQuery):
    vac_id = int(callback.data.split(":")[1])
    vac = get_vacancy(vac_id)
    if vac and os.path.exists(vac['docx_path']):
        doc_file = FSInputFile(vac['docx_path'], filename=os.path.basename(vac['docx_path']))
        await callback.message.answer_document(doc_file, caption=f"📄 Адаптированное резюме под: {vac['title']} ({vac['company']})")
        await callback.answer()
    else:
        await callback.answer("Файл не найден", show_alert=True)

@dp.callback_query(F.data.startswith("get_cl:"))
async def cb_get_cl(callback: types.CallbackQuery):
    vac_id = int(callback.data.split(":")[1])
    vac = get_vacancy(vac_id)
    if vac and vac.get('cover_letter'):
        msg = f"✉️ **Сопроводительное письмо под {vac['company']} (кликните для копирования):**\n\n```\n{vac['cover_letter']}\n```"
        await callback.message.answer(msg, parse_mode="Markdown")
        await callback.answer()
    else:
        await callback.answer("Письмо не найдено", show_alert=True)

@dp.callback_query(F.data.startswith("apply:"))
async def cb_apply(callback: types.CallbackQuery):
    vac_id = int(callback.data.split(":")[1])
    vac = get_vacancy(vac_id)
    if not vac:
        await callback.answer("Вакансия не найдена")
        return
        
    await callback.message.answer(f"🚀 **Запускаю Playwright для автоотклика на:**\n{vac['url']}...")
    profile = load_master_profile()
    
    result = await apply_to_yandex_job(
        url=vac['url'],
        personal_data=profile['personal'],
        cover_letter=vac['cover_letter'],
        docx_path=vac['docx_path'],
        headless=HEADLESS_BROWSER
    )
    
    if result['success']:
        update_status(vac_id, 'applied', result.get('message'))
        await callback.message.answer(f"✅ **Успешно!** {result['message']}")
    else:
        update_status(vac_id, 'failed', result.get('error'))
        await callback.message.answer(f"⚠️ **Статус:** {result.get('error') or result.get('message')}")
    await callback.answer()

@dp.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: types.CallbackQuery):
    vac_id = int(callback.data.split(":")[1])
    update_status(vac_id, 'rejected')
    await callback.message.edit_text("❌ Вакансия отклонена и скрыта.")
    await callback.answer()

async def main():
    init_db()
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        print("\n[!] TELEGRAM_BOT_TOKEN не задан.")
        return
        
    print("🤖 AI Job Agent Bot успешно запущен и слушает события...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
