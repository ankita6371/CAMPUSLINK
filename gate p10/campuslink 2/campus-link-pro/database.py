import sqlite3
import os
from config import Config


def get_db_connection():
    os.makedirs(
        os.path.dirname(Config.DATABASE),
        exist_ok=True
    )

    connection = sqlite3.connect(Config.DATABASE)

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def create_tables():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'placement_officer',
            student_id INTEGER REFERENCES students(id),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            registration_no TEXT UNIQUE NOT NULL,
            email TEXT,
            phone TEXT,
            branch TEXT NOT NULL,
            cgpa REAL NOT NULL,
            backlogs INTEGER DEFAULT 0,
            attendance REAL DEFAULT 0,
            skills TEXT,
            placement_status TEXT DEFAULT 'Unplaced',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    user_column_info = connection.execute("PRAGMA table_info(users)").fetchall()
    user_columns = {column["name"] for column in user_column_info}
    email_is_required = any(
        column["name"] == "email" and column["notnull"]
        for column in user_column_info
    )
    if "username" not in user_columns or email_is_required:
        connection.commit()
        connection.execute("PRAGMA foreign_keys = OFF")
        username_expression = (
            "COALESCE(NULLIF(username, ''), NULLIF(email, ''), name || id)"
            if "username" in user_columns
            else "COALESCE(NULLIF(email, ''), name || id)"
        )
        student_id_expression = "student_id" if "student_id" in user_columns else "NULL"
        active_expression = "is_active" if "is_active" in user_columns else "1"
        connection.execute("""
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'placement_officer',
                student_id INTEGER REFERENCES students(id),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute(f"""
            INSERT INTO users_new
                (id, username, name, email, password, role, student_id,
                 is_active, created_at)
            SELECT id, {username_expression}, name, email, password, role,
                   {student_id_expression}, {active_expression}, created_at
            FROM users
        """)
        connection.execute("DROP TABLE users")
        connection.execute("ALTER TABLE users_new RENAME TO users")
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")

    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student
        ON users(student_id)
        WHERE student_id IS NOT NULL
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS student_certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            certificate_name TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            file_data BLOB NOT NULL,
            file_size INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS student_resumes (
            student_id INTEGER PRIMARY KEY,
            professional_summary TEXT NOT NULL DEFAULT '',
            education TEXT NOT NULL DEFAULT '',
            skills TEXT NOT NULL DEFAULT '',
            projects TEXT NOT NULL DEFAULT '',
            experience TEXT NOT NULL DEFAULT '',
            certifications TEXT NOT NULL DEFAULT '',
            linkedin_url TEXT NOT NULL DEFAULT '',
            portfolio_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Needs generation',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS student_resume_files (
            student_id INTEGER PRIMARY KEY,
            original_filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            file_data BLOB NOT NULL,
            file_size INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS mock_test_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            question TEXT NOT NULL,
            options_json TEXT NOT NULL,
            correct_option TEXT NOT NULL,
            explanation TEXT NOT NULL,
            UNIQUE(category, question)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS mock_test_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            question_ids TEXT NOT NULL,
            answers_json TEXT NOT NULL DEFAULT '{}',
            score INTEGER,
            total_questions INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'In Progress',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            industry TEXT,
            location TEXT,
            website TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            package REAL,
            min_cgpa REAL DEFAULT 0,
            max_backlogs INTEGER DEFAULT 0,
            min_attendance REAL DEFAULT 0,
            eligible_branches TEXT,
            required_skills TEXT,
            application_deadline TEXT,
            drive_date TEXT,
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (company_id)
            REFERENCES companies(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            match_score REAL DEFAULT 0,
            status TEXT DEFAULT 'Applied',
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE,

            FOREIGN KEY (job_id)
            REFERENCES jobs(id)
            ON DELETE CASCADE,

            UNIQUE(student_id, job_id)
        )
    """)

    connection.execute("""
        UPDATE applications
        SET status = 'In Progress'
        WHERE status IN ('Shortlisted', 'Interview')
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            round TEXT DEFAULT 'Technical',
            interview_date TEXT NOT NULL,
            interview_time TEXT NOT NULL,
            venue TEXT,
            status TEXT DEFAULT 'Scheduled',

            FOREIGN KEY (application_id)
            REFERENCES applications(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            package REAL,
            offer_date TEXT,
            joining_date TEXT,
            status TEXT DEFAULT 'Pending',

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE,

            FOREIGN KEY (company_id)
            REFERENCES companies(id)
            ON DELETE CASCADE,

            FOREIGN KEY (job_id)
            REFERENCES jobs(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS communications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Announcement',
            audience_type TEXT NOT NULL
                CHECK (audience_type IN ('all', 'branch', 'student')),
            target_branch TEXT,
            target_student_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (target_student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS communication_reads (
            communication_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (communication_id, student_id),

            FOREIGN KEY (communication_id)
            REFERENCES communications(id)
            ON DELETE CASCADE,

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS communication_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            communication_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL
                CHECK (sender_type IN ('student', 'officer')),
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (communication_id)
            REFERENCES communications(id)
            ON DELETE CASCADE,

            FOREIGN KEY (student_id)
            REFERENCES students(id)
            ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS admin_notification_receipts (
            notification_signature TEXT PRIMARY KEY,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_communications_created
        ON communications(created_at DESC)
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_communication_reads_student
        ON communication_reads(student_id, read_at)
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_communication_replies_thread
        ON communication_replies(communication_id, student_id, created_at, id)
    """)

    from mock_test_data import QUESTION_BANK

    connection.executemany(
        """
        INSERT OR IGNORE INTO mock_test_questions
            (category, question, options_json, correct_option, explanation)
        VALUES (?, ?, ?, ?, ?)
        """,
        QUESTION_BANK,
    )

    connection.commit()
    connection.close()


if __name__ == "__main__":
    create_tables()
    print("CAMPUSLINK database created successfully.")