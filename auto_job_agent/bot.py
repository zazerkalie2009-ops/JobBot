import os
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
from auto_job_agent.llm_engine import load_master_profile, analyze_and_adapt, MASTER_PROFILE_PATH
from auto_job_agent.docx_generator import build_resume_docx
from auto_job_agent.vacancy_parser import parse_local_yandex_vacancies
from auto_job_agent.browser_applier import apply_to_yandex_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN or "DUMMY_TOKEN")
dp = Dispatcher()

def get_action_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Откликнуться (Playwright)", callback_data=f"apply:{vacancy_id}")
    builder.button(text="📄 Скачать DOCX", callback_data=f"get_cv:{vacancy_id}")
    builder.button(text="❌ Пропустить", callback_data=f"reject:{vacancy_id}")
    builder.adjust(1, 2)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "👋 **Привет, Олег! Я твой персональный AI Job Agent.**\n\n"
        "Я умею:\n"
        "1. 🔍 **Сканировать каналы и базы вакансий** (Яндекс, hh.ru, TG) — команда `/scan`.\n"
        "2. 🎯 **Анализировать релевантность (Match Score)** под твой Master-профиль.\n"
        "3. 📝 **Генерировать адаптированное резюме (.docx)** и адресное сопроводительное письмо на лету.\n"
        "4. 🚀 **Автоматически заполнять формы и отправлять отклики** через Playwright.\n\n"
        "💡 *Просто отправь мне ссылку на вакансию или её текст, и я подготовлю всё за 3 секунды!*"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(Command("scan"))
async def cmd_scan(message: types.Message):
    await message.answer("🔄 **Запускаю сканирование базы вакансий Яндекса...**", parse_mode="Markdown")
    
    vacancies = parse_local_yandex_vacancies()
    profile = load_master_profile()
    
    found_count = 0
    for v in vacancies:
        analysis = analyze_and_adapt(v['description'], v['title'], v['company'])
        if analysis['match_score'] >= 80:
            # Generate tailored docx
            file_safe_title = "".join(c for c in v['title'] if c.isalnum() or c in (' ', '_')).rstrip()[:30]
            docx_path = f"auto_job_agent/generated_resumes/CV_Oleg_Kokhtenko_{file_safe_title}.docx"
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
                f"🎯 **Найдена горячая вакансия!**\n\n"
                f"📌 **Позиция:** {v['title']}\n"
                f"🏢 **Компания:** {v['company']}\n"
                f"📊 **Match Score:** {analysis['match_score']}%\n"
                f"🏷 **Домен:** {analysis['domain']}\n"
                f"💡 **Почему подходит:** {analysis['match_reasons']}\n\n"
                f"🔗 [Ссылка на вакансию]({v['url']})\n\n"
                f"✉️ **Сопроводительное письмо:**\n_{analysis['cover_letter'][:300]}..._"
            )
            
            await message.answer(card_text, parse_mode="Markdown", reply_markup=get_action_keyboard(vac_id))
            found_count += 1
            if found_count >= 5:  # Send top 5
                break
                
    await message.answer(f"✅ Найдено и подготовлено **{found_count}** релевантных вакансий с высоким скором.", parse_mode="Markdown")

@dp.message(F.text)
async def handle_vacancy_text(message: types.Message):
    text = message.text
    if text.startswith("/"):
        return
        
    await message.answer("🧠 **Анализирую вакансию и генерирую кастомизированные материалы...**", parse_mode="Markdown")
    
    profile = load_master_profile()
    analysis = analyze_and_adapt(text, "Product Manager", "Яндекс / IT")
    
    docx_path = f"auto_job_agent/generated_resumes/CV_Oleg_Kokhtenko_Custom_{message.message_id}.docx"
    build_resume_docx(docx_path, profile, {
        'role': analysis['adapted_role'],
        'summary': analysis['adapted_summary']
    })
    
    vac_id = save_vacancy(
        source="Telegram Chat Input",
        external_id=f"custom_{message.message_id}",
        title=analysis['adapted_role'],
        company="IT Компания",
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
        f"🎯 **Анализ завершен!**\n\n"
        f"📊 **Релевантность (Match Score):** {analysis['match_score']}%\n"
        f"🏷 **Целевой домен:** {analysis['domain']}\n"
        f"💡 **Фокус адаптации:** {analysis['match_reasons']}\n\n"
        f"✉️ **Сгенерированное сопроводительное письмо:**\n\n"
        f"{analysis['cover_letter']}"
    )
    
    await message.answer(card_text, reply_markup=get_action_keyboard(vac_id))

@dp.callback_query(F.data.startswith("get_cv:"))
async def cb_get_cv(callback: types.CallbackQuery):
    vac_id = int(callback.data.split(":")[1])
    vac = get_vacancy(vac_id)
    if vac and os.path.exists(vac['docx_path']):
        doc_file = FSInputFile(vac['docx_path'], filename=os.path.basename(vac['docx_path']))
        await callback.message.answer_document(doc_file, caption=f"📄 Адаптированное резюме под вакансию: {vac['title']}")
        await callback.answer()
    else:
        await callback.answer("Файл не найден", show_alert=True)

@dp.callback_query(F.data.startswith("apply:"))
async def cb_apply(callback: types.CallbackQuery):
    vac_id = int(callback.data.split(":")[1])
    vac = get_vacancy(vac_id)
    if not vac:
        await callback.answer("Вакансия не найдена")
        return
        
    await callback.message.answer(f"🚀 **Запускаю Playwright для автоотклика на:** {vac['url']}...")
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
        await callback.message.answer(f"⚠️ **Ошибка автоотклика:** {result.get('error')}")
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
        print("\n[!] ВНИМАНИЕ: TELEGRAM_BOT_TOKEN не задан в auto_job_agent/.env")
        print("[!] Создайте бота в @BotFather, вставьте токен в auto_job_agent/.env и запустите снова.\n")
        return
        
    print("🤖 AI Job Agent Bot успешно запущен и слушает события...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
