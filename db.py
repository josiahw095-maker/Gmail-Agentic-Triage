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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_id TEXT,
            subject TEXT,
            original_category TEXT,
            corrected_category TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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


def log_correction(gmail_id, subject, original_category, corrected_category):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO corrections (gmail_id, subject, original_category, corrected_category)
        VALUES (?, ?, ?, ?)
    ''', (gmail_id, subject, original_category, corrected_category))

    conn.commit()
    conn.close()


def load_corrections(limit=20):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT subject, original_category, corrected_category
        FROM corrections
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()

    conn.close()
    return rows


def load_escalated_emails():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT gmail_id, subject, sender, category
        FROM emails
        WHERE escalated = 1
        ORDER BY timestamp DESC
    ''')
    rows = cursor.fetchall()

    conn.close()
    return rows


def load_recent_emails(limit=100):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT gmail_id, subject, sender, category
        FROM emails
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()

    conn.close()
    return rows
