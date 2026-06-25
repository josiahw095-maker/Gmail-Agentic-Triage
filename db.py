import sqlite3

DB_FILE = 'triage.db'


def get_connection():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_id TEXT UNIQUE,
            subject TEXT,
            sender TEXT,
            category TEXT,
            confidence INTEGER,
            escalated BOOLEAN,
            reason TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT
        )
    ''')

    conn.commit()
    conn.close()


def log_email(gmail_id, subject, sender, category, confidence, escalated, reason):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR IGNORE INTO emails (gmail_id, subject, sender, category, confidence, escalated, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (gmail_id, subject, sender, category, confidence, escalated, reason))

    conn.commit()
    conn.close()


def save_category(name, description):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR IGNORE INTO categories (name, description)
        VALUES (?, ?)
    ''', (name, description))

    conn.commit()
    conn.close()


def load_categories():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT name, description FROM categories')
    rows = cursor.fetchall()

    conn.close()
    return [f'{name}: {description}' for name, description in rows]
