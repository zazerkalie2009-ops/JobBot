import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = 'auto_job_agent/jobs.db'

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vacancies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                external_id TEXT UNIQUE,
                title TEXT,
                company TEXT,
                url TEXT,
                description TEXT,
                domain TEXT,
                match_score INTEGER,
                match_reasons TEXT,
                adapted_role TEXT,
                cover_letter TEXT,
                docx_path TEXT,
                status TEXT DEFAULT 'new', -- 'new', 'approved', 'applied', 'rejected', 'failed'
                applied_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS application_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vacancy_id INTEGER,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vacancy_id) REFERENCES vacancies (id)
            )
        ''')
        conn.commit()

def save_vacancy(
    source: str,
    external_id: str,
    title: str,
    company: str,
    url: str,
    description: str,
    domain: str,
    match_score: int,
    match_reasons: str,
    adapted_role: str,
    cover_letter: str,
    docx_path: str
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO vacancies (
                source, external_id, title, company, url, description,
                domain, match_score, match_reasons, adapted_role,
                cover_letter, docx_path, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
            ON CONFLICT(external_id) DO UPDATE SET
                title=excluded.title,
                match_score=excluded.match_score,
                match_reasons=excluded.match_reasons,
                cover_letter=excluded.cover_letter,
                docx_path=excluded.docx_path,
                updated_at=CURRENT_TIMESTAMP
        ''', (
            source, external_id, title, company, url, description,
            domain, match_score, match_reasons, adapted_role,
            cover_letter, docx_path
        ))
        conn.commit()
        return cursor.lastrowid

def get_vacancy(vacancy_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM vacancies WHERE id = ?', (vacancy_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_pending_vacancies(limit: int = 10) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM vacancies 
            WHERE status = 'new' AND match_score >= 70
            ORDER BY match_score DESC, created_at DESC
            LIMIT ?
        ''', (limit,))
        return [dict(r) for r in cursor.fetchall()]

def update_status(vacancy_id: int, status: str, details: str = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now() if status == 'applied' else None
        cursor.execute('''
            UPDATE vacancies 
            SET status = ?, applied_at = COALESCE(?, applied_at), updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, now, vacancy_id))
        cursor.execute('''
            INSERT INTO application_logs (vacancy_id, action, details)
            VALUES (?, ?, ?)
        ''', (vacancy_id, status, details or ''))
        conn.commit()

init_db()
