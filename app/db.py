import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config

class Database:
    def __init__(self):
        self.connection = None
    
    def get_connection(self):
        if self.connection is None or self.connection.closed:
            self.connection = psycopg2.connect(Config.DATABASE_URL)
        return self.connection
    
    def close(self):
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None
    
    def execute(self, query, params=None, fetch=False):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(query, params)
            if fetch:
                result = cursor.fetchall()
            else:
                conn.commit()
                result = None
            return result
        finally:
            cursor.close()
    
    def execute_one(self, query, params=None):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(query, params)
            conn.commit()
            result = cursor.fetchone()
            return result
        finally:
            cursor.close()

def init_db():
    """Initialize database tables"""
    db = Database()
    
    # Domain whitelist table
    db.execute("""
        CREATE TABLE IF NOT EXISTS domain_whitelist (
            id SERIAL PRIMARY KEY,
            domain VARCHAR(255) UNIQUE NOT NULL,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Sender blocklist table
    db.execute("""
        CREATE TABLE IF NOT EXISTS sender_blocklist (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255),
            domain VARCHAR(255),
            blocked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add unique constraints via partial indexes
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sender_blocklist_email 
        ON sender_blocklist(email) WHERE email IS NOT NULL
    """)
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sender_blocklist_domain 
        ON sender_blocklist(domain) WHERE email IS NULL AND domain IS NOT NULL
    """)
    
    # User preferences table
    db.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id SERIAL PRIMARY KEY,
            user_email VARCHAR(255) NOT NULL,
            setting_name VARCHAR(100) NOT NULL,
            setting_value TEXT,
            UNIQUE(user_email, setting_name)
        )
    """)
    
    db.close()
    print("Database initialized successfully")

def get_db():
    """Get database instance"""
    return Database()
