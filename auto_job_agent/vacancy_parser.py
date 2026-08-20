import os
import re
import json
from html.parser import HTMLParser
from typing import List, Dict, Any

class YandexHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_text = False
        self.current = []
        self.texts = []
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if 'class' in attrs_dict and 'text' in attrs_dict['class'].split():
            self.in_text = True
            self.current = []
            
    def handle_endtag(self, tag):
        if self.in_text and tag in ['div', 'p']:
            text = ' '.join(self.current).strip()
            if text:
                self.texts.append(text)
            self.current = []
            self.in_text = False
            
    def handle_data(self, data):
        if self.in_text:
            self.current.append(data.strip())

def parse_local_yandex_vacancies(yandex_dir: str = 'Яндекс вакансии') -> List[Dict[str, Any]]:
    vacancies = []
    for fname in ['messages.html', 'messages2.html', 'messages3.html']:
        fpath = os.path.join(yandex_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                parser = YandexHTMLParser()
                parser.feed(f.read())
                for idx, t in enumerate(parser.texts):
                    t_low = t.lower()
                    if any(k in t_low for k in ['менеджер продукта', 'product manager', 'продакт']):
                        # Extract title
                        lines = [l.strip() for l in t.split('\n') if l.strip()]
                        first_line = lines[0] if lines else "Product Manager"
                        # Clean title
                        title = re.sub(r'^[^\w\s]+', '', first_line).strip()
                        if len(title) > 60:
                            title = title[:60] + '...'
                            
                        # Extract URL if present
                        url_match = re.search(r'https://yandex\.ru/jobs/vacancies/[^\s"\'<>]+', t)
                        url = url_match.group(0) if url_match else f"local_yandex_{fname}_{idx}"
                        
                        vacancies.append({
                            'source': 'Yandex Telegram Export',
                            'external_id': f"ya_{fname}_{idx}",
                            'title': title,
                            'company': 'Яндекс',
                            'url': url,
                            'description': t
                        })
    return vacancies
