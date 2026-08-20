import os
import asyncio
from typing import Dict, Any

async def apply_to_yandex_job(
    url: str,
    personal_data: dict,
    cover_letter: str,
    docx_path: str,
    headless: bool = False
) -> Dict[str, Any]:
    """
    Automates the job application on Yandex Jobs using Playwright.
    Fills in: Name, Phone, Email, Telegram, Cover letter, and uploads the generated DOCX CV.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {'success': False, 'error': 'Playwright is not installed yet.'}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        try:
            print(f"Navigating to {url}...")
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state('networkidle')
            
            # Find and click "Откликнуться" button if present
            apply_btn = page.locator('button:has-text("Откликнуться"), a:has-text("Откликнуться")').first
            if await apply_btn.is_visible():
                await apply_btn.click()
                await page.wait_for_timeout(1000)
                
            # Fill form fields
            name_input = page.locator('input[name="name"], input[placeholder*="Имя"], input[aria-label*="Имя"]').first
            if await name_input.is_visible():
                await name_input.fill(personal_data.get('name', 'Олег Кохтенко'))
                
            email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="Email"]').first
            if await email_input.is_visible():
                await email_input.fill(personal_data.get('email', 'olegkokhtenko@gmail.com'))
                
            phone_input = page.locator('input[type="tel"], input[name="phone"], input[placeholder*="Телефон"]').first
            if await phone_input.is_visible():
                await phone_input.fill(personal_data.get('phone', '+79296431542'))
                
            tg_input = page.locator('input[name*="telegram"], input[placeholder*="Telegram"], input[placeholder*="@"]').first
            if await tg_input.is_visible():
                await tg_input.fill(personal_data.get('telegram', '@olegkokhtenko'))
                
            # Fill cover letter
            cover_input = page.locator('textarea[name*="cover"], textarea[placeholder*="сопроводительн"], textarea').first
            if await cover_input.is_visible():
                await cover_input.fill(cover_letter)
                
            # Upload DOCX file
            file_input = page.locator('input[type="file"]').first
            if await file_input.is_visible() and os.path.exists(docx_path):
                await file_input.set_input_files(os.path.abspath(docx_path))
                print(f"Uploaded CV: {docx_path}")
                
            await page.wait_for_timeout(2000)
            
            # If not headless, let user inspect or click submit
            # submit_btn = page.locator('button[type="submit"]:has-text("Отправить")').first
            # await submit_btn.click()
            
            return {
                'success': True,
                'message': f'Форма на {url} успешно заполнена и резюме прикреплено!'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            if headless:
                await browser.close()
