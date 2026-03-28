import sqlite3

DB_PATH = "database/clients.db"

sql = """
CREATE TABLE IF NOT EXISTS email_login_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NULL,
    email VARCHAR(255) NOT NULL,
    code_hash VARCHAR(128) NOT NULL,
    expires_at DATETIME NOT NULL,
    consumed_at DATETIME NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE INDEX IF NOT EXISTS ix_email_login_codes_email
ON email_login_codes(email);

CREATE INDEX IF NOT EXISTS ix_email_login_codes_client_id
ON email_login_codes(client_id);
"""

conn = sqlite3.connect(DB_PATH)
try:
    conn.executescript(sql)
    conn.commit()
    print("email_login_codes table created")
finally:
    conn.close()