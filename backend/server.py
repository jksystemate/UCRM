"""Standalone HTTP server using only Python stdlib - no pip packages required.
Serves both the API and static files for the Relations CRM.
"""
import json
import os
import sqlite3
import email as email_lib
from email import policy as email_policy
from email.utils import parsedate_to_datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from datetime import date, datetime
import io

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relations_crm.db")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# ─── Database ───
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sector TEXT,
            address TEXT, city TEXT, zip_code TEXT, website TEXT, notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            first_name TEXT NOT NULL, last_name TEXT NOT NULL,
            title TEXT, email TEXT, phone TEXT, linkedin_url TEXT,
            on_linkedin_list BOOLEAN DEFAULT 0, notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'user' CHECK(role IN ('admin', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            type TEXT NOT NULL,
            date DATE NOT NULL, subject TEXT, notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interaction_id INTEGER REFERENCES interactions(id) ON DELETE CASCADE,
            from_email TEXT, to_email TEXT, cc TEXT,
            subject TEXT, body_text TEXT, body_html TEXT,
            date_sent TIMESTAMP, eml_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(date);
        CREATE INDEX IF NOT EXISTS idx_emails_interaction ON emails(interaction_id);

        -- New tables for extended features
        CREATE TABLE IF NOT EXISTS score_settings (
            rating TEXT PRIMARY KEY CHECK(rating IN ('A', 'B', 'C')),
            threshold INTEGER NOT NULL DEFAULT 50
        );
        INSERT OR IGNORE INTO score_settings (rating, threshold) VALUES ('A', 70);
        INSERT OR IGNORE INTO score_settings (rating, threshold) VALUES ('B', 50);
        INSERT OR IGNORE INTO score_settings (rating, threshold) VALUES ('C', 30);

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            user_name TEXT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            entity_name TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
            assigned_to INTEGER REFERENCES users(id),
            created_by INTEGER REFERENCES users(id),
            category TEXT NOT NULL CHECK(category IN ('opkald', 'tilbud', 'moede', 'opfoelgning', 'demo', 'kontrakt', 'generelt')),
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'done')),
            priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low', 'normal', 'high', 'urgent')),
            due_date DATE,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_company ON tasks(company_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(is_read);
        CREATE INDEX IF NOT EXISTS idx_notif_company ON notifications(company_id);

        CREATE TABLE IF NOT EXISTS linkedin_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            activity_type TEXT NOT NULL CHECK(activity_type IN ('post', 'comment', 'like', 'share', 'article')),
            content_summary TEXT,
            linkedin_post_url TEXT,
            observed_by INTEGER REFERENCES users(id),
            activity_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_li_act_contact ON linkedin_activities(contact_id);

        CREATE TABLE IF NOT EXISTS linkedin_engagements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            engagement_type TEXT NOT NULL CHECK(engagement_type IN ('like', 'comment', 'share', 'follow')),
            company_page TEXT NOT NULL CHECK(company_page IN ('systemate', 'settl')),
            post_url TEXT,
            observed_by INTEGER REFERENCES users(id),
            observed_date DATE NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_li_eng_contact ON linkedin_engagements(contact_id);

        -- Tags (many-to-many for companies and contacts)
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            color TEXT DEFAULT '#6b7280',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS company_tags (
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (company_id, tag_id)
        );
        CREATE TABLE IF NOT EXISTS contact_tags (
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (contact_id, tag_id)
        );
        CREATE INDEX IF NOT EXISTS idx_company_tags_company ON company_tags(company_id);
        CREATE INDEX IF NOT EXISTS idx_company_tags_tag ON company_tags(tag_id);
        CREATE INDEX IF NOT EXISTS idx_contact_tags_contact ON contact_tags(contact_id);
        CREATE INDEX IF NOT EXISTS idx_contact_tags_tag ON contact_tags(tag_id);

        -- Tender/Udbud system
        CREATE TABLE IF NOT EXISTS tender_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            is_default BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tender_template_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL REFERENCES tender_templates(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            default_days_before_deadline INTEGER DEFAULT 7,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_tts_template ON tender_template_sections(template_id);

        CREATE TABLE IF NOT EXISTS tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            template_id INTEGER REFERENCES tender_templates(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','in_progress','submitted','won','lost','dropped')),
            deadline DATE,
            contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
            responsible_id INTEGER REFERENCES users(id),
            created_by INTEGER REFERENCES users(id),
            estimated_value TEXT,
            portal_link TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tenders_company ON tenders(company_id);
        CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status);

        CREATE TABLE IF NOT EXISTS tender_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_id INTEGER NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            content TEXT,
            responsible_id INTEGER REFERENCES users(id),
            reviewer_id INTEGER REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'not_started' CHECK(status IN ('not_started','in_progress','in_review','approved')),
            deadline DATE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tsections_tender ON tender_sections(tender_id);

        -- Tender section audit / revision trail
        CREATE TABLE IF NOT EXISTS tender_section_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL REFERENCES tender_sections(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            user_name TEXT,
            note_type TEXT NOT NULL DEFAULT 'note',
            content TEXT,
            old_value TEXT,
            new_value TEXT,
            field_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_section_audit ON tender_section_audit(section_id);

        -- Task notes (comments/notes on tasks)
        CREATE TABLE IF NOT EXISTS task_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            user_name TEXT,
            content TEXT NOT NULL,
            note_type TEXT NOT NULL DEFAULT 'note' CHECK(note_type IN ('note','email','status_change','field_change')),
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_task_notes_task ON task_notes(task_id);

        -- Tender notes (comments/notes on tenders)
        CREATE TABLE IF NOT EXISTS tender_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_id INTEGER NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id),
            user_name TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tender_notes_tender ON tender_notes(tender_id);

        -- Score decay rules (configurable inactivity penalties)
        CREATE TABLE IF NOT EXISTS score_decay_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inactivity_days INTEGER NOT NULL DEFAULT 21,
            penalty_points INTEGER NOT NULL DEFAULT 10,
            description TEXT,
            is_active BOOLEAN DEFAULT 1
        );
        INSERT OR IGNORE INTO score_decay_rules (id, inactivity_days, penalty_points, description)
            VALUES (1, 21, 10, 'Fald efter 3 ugers inaktivitet');
        INSERT OR IGNORE INTO score_decay_rules (id, inactivity_days, penalty_points, description)
            VALUES (2, 42, 20, 'Fald efter 6 ugers inaktivitet');
        INSERT OR IGNORE INTO score_decay_rules (id, inactivity_days, penalty_points, description)
            VALUES (3, 63, 30, 'Fald efter 9 ugers inaktivitet');

        -- Score historik
        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            score REAL NOT NULL,
            level TEXT,
            recorded_at DATE NOT NULL DEFAULT (date('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_score_history_company ON score_history(company_id);
        CREATE INDEX IF NOT EXISTS idx_score_history_date ON score_history(recorded_at);
    """)

    # Idempotent ALTER TABLE migrations
    migrations = [
        "ALTER TABLE companies ADD COLUMN rating TEXT DEFAULT 'C'",
        "ALTER TABLE companies ADD COLUMN account_manager_id INTEGER REFERENCES users(id)",
        "ALTER TABLE contacts ADD COLUMN linkedin_connected_systemate BOOLEAN DEFAULT 0",
        "ALTER TABLE contacts ADD COLUMN linkedin_connected_settl BOOLEAN DEFAULT 0",
        "ALTER TABLE contacts ADD COLUMN linkedin_last_checked DATE",
        "ALTER TABLE tender_sections ADD COLUMN start_date DATE",
        "ALTER TABLE tender_sections ADD COLUMN end_date DATE",
        # Kundematrix: vigtighed og salgsstadie
        "ALTER TABLE companies ADD COLUMN importance TEXT DEFAULT 'middel_vigtig'",
        "ALTER TABLE companies ADD COLUMN sales_stage TEXT DEFAULT 'tidlig_fase'",
        # Relationsscore-parametre (0-10 skala) — legacy, kept for migration
        "ALTER TABLE companies ADD COLUMN score_cxo INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN score_kontaktfrekvens INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN score_kontaktbredde INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN score_kendskab INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN score_historik INTEGER DEFAULT 0",
        # Nye manuelle relationsscore-parametre (0-10)
        "ALTER TABLE companies ADD COLUMN score_kendskab_behov INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN score_workshops INTEGER DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN score_marketing INTEGER DEFAULT 0",
        # Udvidet virksomhedsdata
        "ALTER TABLE companies ADD COLUMN tier TEXT",
        "ALTER TABLE companies ADD COLUMN ejerform TEXT",
        "ALTER TABLE companies ADD COLUMN has_el BOOLEAN DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN has_gas BOOLEAN DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN has_vand BOOLEAN DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN has_varme BOOLEAN DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN has_spildevand BOOLEAN DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN has_affald BOOLEAN DEFAULT 0",
        "ALTER TABLE companies ADD COLUMN est_kunder TEXT",
    ]
    for m in migrations:
        try:
            conn.execute(m)
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Migration: remove sector CHECK constraint on companies (allow any sector value)
    try:
        conn.execute("SAVEPOINT sector_check")
        conn.execute("INSERT INTO companies (name, sector) VALUES ('__migration_test__', 'e-mobilitet')")
        conn.execute("ROLLBACK TO sector_check")
        conn.execute("RELEASE sector_check")
    except sqlite3.IntegrityError:
        conn.executescript("""
            CREATE TABLE companies_new AS SELECT * FROM companies;
            DROP TABLE companies;
            CREATE TABLE companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, sector TEXT,
                address TEXT, city TEXT, zip_code TEXT, website TEXT, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rating TEXT DEFAULT 'C', account_manager_id INTEGER REFERENCES users(id),
                importance TEXT DEFAULT 'middel_vigtig', sales_stage TEXT DEFAULT 'tidlig_fase',
                score_cxo INTEGER DEFAULT 0, score_kontaktfrekvens INTEGER DEFAULT 0,
                score_kontaktbredde INTEGER DEFAULT 0, score_kendskab INTEGER DEFAULT 0, score_historik INTEGER DEFAULT 0,
                tier TEXT, ejerform TEXT, has_el BOOLEAN DEFAULT 0, has_gas BOOLEAN DEFAULT 0,
                has_vand BOOLEAN DEFAULT 0, has_varme BOOLEAN DEFAULT 0, has_spildevand BOOLEAN DEFAULT 0,
                has_affald BOOLEAN DEFAULT 0, est_kunder TEXT
            );
            INSERT INTO companies SELECT *, NULL, NULL, 0, 0, 0, 0, 0, 0, NULL FROM companies_new
                WHERE (SELECT COUNT(*) FROM pragma_table_info('companies_new') WHERE name='tier') = 0;
            INSERT INTO companies SELECT * FROM companies_new
                WHERE (SELECT COUNT(*) FROM pragma_table_info('companies_new') WHERE name='tier') > 0;
            DROP TABLE companies_new;
        """)

    # Migration: update tender_section_audit CHECK constraint to allow 'comment' type
    try:
        conn.execute("SAVEPOINT audit_check")
        conn.execute("INSERT INTO tender_section_audit (section_id, note_type, content) VALUES (0, 'comment', '__migration_test__')")
        conn.execute("ROLLBACK TO audit_check")
        conn.execute("RELEASE audit_check")
    except sqlite3.IntegrityError:
        # Old CHECK constraint present - recreate table without CHECK
        conn.executescript("""
            CREATE TABLE tender_section_audit_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section_id INTEGER NOT NULL REFERENCES tender_sections(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id),
                user_name TEXT,
                note_type TEXT NOT NULL DEFAULT 'note',
                content TEXT, old_value TEXT, new_value TEXT, field_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO tender_section_audit_new SELECT * FROM tender_section_audit;
            DROP TABLE tender_section_audit;
            ALTER TABLE tender_section_audit_new RENAME TO tender_section_audit;
            CREATE INDEX IF NOT EXISTS idx_section_audit ON tender_section_audit(section_id);
        """)

    # Migration: remove interaction type CHECK constraint (allow new types like meeting_task, campaign)
    # Skip if already migrated to v3 (company_id exists = new schema, no CHECK constraint)
    has_company_id = conn.execute("SELECT COUNT(*) FROM pragma_table_info('interactions') WHERE name='company_id'").fetchone()[0]
    if not has_company_id:
        try:
            conn.execute("SAVEPOINT interaction_check")
            conn.execute("INSERT INTO interactions (contact_id, type, date) VALUES (0, 'campaign', '2000-01-01')")
            conn.execute("ROLLBACK TO interaction_check")
            conn.execute("RELEASE interaction_check")
        except sqlite3.IntegrityError:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS interactions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id),
                    type TEXT NOT NULL,
                    date DATE NOT NULL, subject TEXT, notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT OR IGNORE INTO interactions_new SELECT * FROM interactions;
                DROP TABLE interactions;
                ALTER TABLE interactions_new RENAME TO interactions;
                CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
                CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(date);
            """)

    # Migration: make contact_id nullable + add company_id to interactions
    try:
        conn.execute("SELECT company_id FROM interactions LIMIT 1")
    except sqlite3.OperationalError:
        conn.executescript("""
            CREATE TABLE interactions_v3 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id),
                type TEXT NOT NULL,
                date DATE NOT NULL, subject TEXT, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO interactions_v3 (id, contact_id, company_id, user_id, type, date, subject, notes, created_at)
            SELECT i.id, i.contact_id, c.company_id, i.user_id, i.type, i.date, i.subject, i.notes, i.created_at
            FROM interactions i LEFT JOIN contacts c ON i.contact_id = c.id;
            DROP TABLE interactions;
            ALTER TABLE interactions_v3 RENAME TO interactions;
            CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_company ON interactions(company_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(date);
        """)
        conn.commit()

    # Migration: add 'dropped' to tender status CHECK constraint
    try:
        conn.execute("SAVEPOINT tender_status_check")
        conn.execute("INSERT INTO tenders (company_id, title, status) VALUES (1, '__migration_test__', 'dropped')")
        conn.execute("ROLLBACK TO tender_status_check")
        conn.execute("RELEASE tender_status_check")
    except sqlite3.IntegrityError:
        conn.executescript("""
            CREATE TABLE tenders_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                template_id INTEGER REFERENCES tender_templates(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','in_progress','submitted','won','lost','dropped')),
                deadline DATE,
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                responsible_id INTEGER REFERENCES users(id),
                created_by INTEGER REFERENCES users(id),
                estimated_value TEXT,
                portal_link TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO tenders_new SELECT * FROM tenders;
            DROP TABLE tenders;
            ALTER TABLE tenders_new RENAME TO tenders;
            CREATE INDEX IF NOT EXISTS idx_tenders_company ON tenders(company_id);
            CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status);
        """)

    # Migration: add deleted_at to users for soft delete
    try:
        conn.execute("SELECT deleted_at FROM users LIMIT 1")
    except:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP")
        except:
            pass

    conn.commit()
    conn.close()

# ─── Audit helper ───
def log_audit(conn, user_id, action, entity_type, entity_id, entity_name, details=None):
    user_name = None
    if user_id:
        row = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            user_name = row["name"]
    conn.execute(
        "INSERT INTO audit_log (user_id, user_name, action, entity_type, entity_id, entity_name, details) VALUES (?,?,?,?,?,?,?)",
        (user_id, user_name, action, entity_type, entity_id, entity_name,
         json.dumps(details, ensure_ascii=False) if details else None))

# ─── Notification check ───
def check_score_notifications(conn):
    """Check all companies and create notifications if score is below threshold for their rating."""
    thresholds = {}
    for row in conn.execute("SELECT rating, threshold FROM score_settings").fetchall():
        thresholds[row["rating"]] = row["threshold"]

    all_scores = calculate_all_scores(conn)
    for s in all_scores:
        rating = s.get("rating") or "C"
        threshold = thresholds.get(rating, 30)
        score = s["score"]

        if score < threshold:
            # Check if recent unread notification exists (within 7 days)
            existing = conn.execute(
                """SELECT id FROM notifications WHERE company_id = ? AND is_read = 0
                   AND created_at > datetime('now', '-7 days') AND type = 'score_drop'""",
                (s["company_id"],)).fetchone()
            if not existing:
                msg = "{} har score {} (under graense {} for {}-kunde)".format(
                    s["company_name"], round(score), threshold, rating)
                conn.execute(
                    "INSERT INTO notifications (company_id, type, message) VALUES (?, 'score_drop', ?)",
                    (s["company_id"], msg))
    conn.commit()

# ─── Combined Relationsscore (0-100) ───
# 7 sub-scores, each 0-10, with weights summing to 100%
SCORE_WEIGHTS = {
    "kontaktfrekvens": 0.20,       # auto: from interaction points
    "kontaktdaekning": 0.15,       # auto: from contact coverage
    "tidsforfald": 0.15,           # auto: from days since last interaction
    "linkedin": 0.10,              # auto: from contacts' LinkedIn connections
    "kendskab_behov": 0.15,        # manual: 0-10
    "workshops": 0.10,             # manual: 0-10
    "marketing": 0.15,             # manual: 0-10 (reagerer paa vores marketing)
}

def score_color_100(score):
    """Return color for 0-100 score."""
    if score >= 70:
        return "groen"
    elif score >= 40:
        return "gul"
    return "roed"

# ─── Score ───
INTERACTION_POINTS = {
    "meeting_task": 25, "meeting": 15, "meeting_event": 8,
    "phone": 10, "email": 5, "linkedin": 3, "campaign": 2,
}
DECAY_BRACKETS = [(14, 1.0), (30, 0.85), (60, 0.65), (90, 0.45), (180, 0.25)]
DIVERSITY_SCORES = {1: 5, 2: 10, 3: 15, 4: 20}
# Map meeting subtypes to base 'meeting' for diversity calculation
DIVERSITY_TYPE_MAP = {"meeting_task": "meeting", "meeting_event": "meeting"}

def get_decay_factor(days):
    if days is None:
        return 0.10
    for max_days, factor in DECAY_BRACKETS:
        if days <= max_days:
            return factor
    return 0.10

def _calc_sub_scores(company, contacts_data, interactions, total_contacts):
    """Calculate 7 sub-scores (each 0-10) for the combined relationsscore."""
    # 1. Kontaktfrekvens (auto): interaction points scaled to 0-10
    raw_points = sum(INTERACTION_POINTS.get(i["type"], 0) for i in interactions)
    interaction_points = min(raw_points, 60)
    s_kontaktfrekvens = round(min(interaction_points / 6, 10), 1)  # 60 → 10

    # 2. Kontaktdaekning (auto): coverage + diversity scaled to 0-10
    contacted_ids = set(i["contact_id"] for i in interactions)
    contacted_count = len(contacted_ids)
    coverage_pct = (contacted_count / total_contacts * 100) if total_contacts > 0 else 0
    channel_types = list(set(DIVERSITY_TYPE_MAP.get(i["type"], i["type"]) for i in interactions))
    diversity_bonus = min(len(channel_types), 4)  # 0-4 bonus points
    s_kontaktdaekning = round(min(coverage_pct / 10 + diversity_bonus * 0.5, 10), 1)

    # 3. Tidsforfald (auto): decay factor scaled to 0-10
    days_since_last = None
    if interactions:
        try:
            last_date = date.fromisoformat(interactions[0]["date"])
            days_since_last = (date.today() - last_date).days
        except (ValueError, TypeError):
            pass
    decay_factor = get_decay_factor(days_since_last)
    s_tidsforfald = round(decay_factor * 10, 1)

    # 4. LinkedIn (auto): % of contacts connected on LinkedIn (systemate OR settl)
    li_connected = 0
    for c in contacts_data:
        if c.get("linkedin_connected_systemate") or c.get("linkedin_connected_settl"):
            li_connected += 1
    s_linkedin = round(min((li_connected / total_contacts * 10) if total_contacts > 0 else 0, 10), 1)

    # 5-7. Manual scores (0-10)
    s_kendskab = min(company.get("score_kendskab_behov", 0) or 0, 10)
    s_workshops = min(company.get("score_workshops", 0) or 0, 10)
    s_marketing = min(company.get("score_marketing", 0) or 0, 10)

    sub_scores = {
        "kontaktfrekvens": s_kontaktfrekvens,
        "kontaktdaekning": s_kontaktdaekning,
        "tidsforfald": s_tidsforfald,
        "linkedin": s_linkedin,
        "kendskab_behov": s_kendskab,
        "workshops": s_workshops,
        "marketing": s_marketing,
    }

    # Combined score (0-100)
    combined = sum(sub_scores[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS) * 10
    combined = round(min(combined, 100), 1)

    return sub_scores, combined, {
        "interaction_points": interaction_points,
        "contacted_count": contacted_count,
        "total_interactions": len(interactions),
        "channel_types": channel_types,
        "days_since_last": days_since_last,
        "decay_factor": decay_factor,
        "coverage_pct": round(coverage_pct, 1),
        "li_connected": li_connected,
    }


def calculate_company_score(company_id):
    conn = get_db()
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        conn.close()
        return None
    company = dict(company)

    am_name = None
    if company.get("account_manager_id"):
        am_row = conn.execute("SELECT name FROM users WHERE id = ?", (company["account_manager_id"],)).fetchone()
        if am_row:
            am_name = am_row["name"]

    contacts_data = [dict(r) for r in conn.execute("SELECT * FROM contacts WHERE company_id = ?", (company_id,)).fetchall()]
    total_contacts = len(contacts_data)
    contact_ids = [c["id"] for c in contacts_data]

    mx = {"importance": company.get("importance", "middel_vigtig"), "sales_stage": company.get("sales_stage", "tidlig_fase"),
          "score_kendskab_behov": company.get("score_kendskab_behov", 0) or 0,
          "score_workshops": company.get("score_workshops", 0) or 0,
          "score_marketing": company.get("score_marketing", 0) or 0}

    empty_sub = {"kontaktfrekvens": 0, "kontaktdaekning": 0, "tidsforfald": 0,
                 "linkedin": 0, "kendskab_behov": 0, "workshops": 0, "marketing": 0}

    if not contact_ids:
        conn.close()
        return {"company_id": company["id"], "company_name": company["name"], "sector": company["sector"],
                "tier": company.get("tier"), "rating": company.get("rating", "C"), "account_manager_name": am_name,
                "score": 0, "sub_scores": empty_sub, "interaction_points": 0,
                "decay_factor": 0.10, "days_since_last": None, "total_contacts": 0, "contacted_count": 0,
                "total_interactions": 0, "channel_types": [], "level": "kold",
                "coverage_pct": 0, "li_connected": 0, "score_color": "roed", **mx}

    placeholders = ",".join("?" * len(contact_ids))
    interactions = [dict(r) for r in conn.execute(
        "SELECT type, date, contact_id FROM interactions WHERE contact_id IN ({}) ORDER BY date DESC".format(placeholders),
        contact_ids).fetchall()]

    decay_penalty_rules = [dict(r) for r in conn.execute(
        "SELECT * FROM score_decay_rules WHERE is_active = 1 ORDER BY inactivity_days").fetchall()]
    conn.close()

    sub_scores, score, details = _calc_sub_scores(company, contacts_data, interactions, total_contacts)

    # Apply same inactivity penalty as calculate_all_scores
    penalty = 0
    if details["days_since_last"] is not None:
        for rule in decay_penalty_rules:
            if details["days_since_last"] >= rule["inactivity_days"]:
                penalty = rule["penalty_points"]
    score = max(0, round(score - penalty, 1))

    level = "staerk" if score >= 80 else "god" if score >= 50 else "svag" if score >= 20 else "kold"

    return {"company_id": company["id"], "company_name": company["name"], "sector": company["sector"],
            "tier": company.get("tier"), "rating": company.get("rating", "C"), "account_manager_name": am_name,
            "score": score, "sub_scores": sub_scores,
            "interaction_points": details["interaction_points"],
            "decay_factor": details["decay_factor"], "days_since_last": details["days_since_last"],
            "total_contacts": total_contacts, "contacted_count": details["contacted_count"],
            "total_interactions": details["total_interactions"], "channel_types": details["channel_types"],
            "level": level, "penalty": penalty, "coverage_pct": details["coverage_pct"],
            "li_connected": details["li_connected"], "score_color": score_color_100(score), **mx}

def calculate_all_scores(conn):
    """Batch-calculate combined scores for ALL companies using a single DB connection."""
    decay_penalty_rules = [dict(r) for r in conn.execute(
        "SELECT * FROM score_decay_rules WHERE is_active = 1 ORDER BY inactivity_days").fetchall()]

    companies = [dict(r) for r in conn.execute(
        """SELECT c.*, u.name AS account_manager_name
           FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id
           ORDER BY c.name""").fetchall()]
    if not companies:
        return []

    # 1) Contacts per company (with linkedin fields)
    contacts_by_company = {}
    for r in conn.execute("SELECT id, company_id, linkedin_connected_systemate, linkedin_connected_settl FROM contacts").fetchall():
        cid = r["company_id"]
        if cid not in contacts_by_company:
            contacts_by_company[cid] = []
        contacts_by_company[cid].append(dict(r))

    # 2) Tags per company
    tags_by_company = {}
    for r in conn.execute(
            """SELECT ct.company_id, t.id, t.name, t.color
               FROM company_tags ct JOIN tags t ON ct.tag_id = t.id
               ORDER BY t.name""").fetchall():
        cid = r["company_id"]
        if cid not in tags_by_company:
            tags_by_company[cid] = []
        tags_by_company[cid].append({"id": r["id"], "name": r["name"], "color": r["color"]})

    # 3) All interactions grouped by company
    interactions_by_company = {}
    for r in conn.execute(
            """SELECT i.type, i.date, i.contact_id, c.company_id
               FROM interactions i JOIN contacts c ON i.contact_id = c.id
               ORDER BY i.date DESC""").fetchall():
        cid = r["company_id"]
        if cid not in interactions_by_company:
            interactions_by_company[cid] = []
        interactions_by_company[cid].append(dict(r))

    # 4) Calculate combined score per company
    empty_sub = {"kontaktfrekvens": 0, "kontaktdaekning": 0, "tidsforfald": 0,
                 "linkedin": 0, "kendskab_behov": 0, "workshops": 0, "marketing": 0}
    results = []
    for company in companies:
        cid = company["id"]
        contacts_data = contacts_by_company.get(cid, [])
        total_contacts = len(contacts_data)
        interactions = interactions_by_company.get(cid, [])

        mx = {"importance": company.get("importance", "middel_vigtig"),
              "sales_stage": company.get("sales_stage", "tidlig_fase"),
              "score_kendskab_behov": company.get("score_kendskab_behov", 0) or 0,
              "score_workshops": company.get("score_workshops", 0) or 0,
              "score_marketing": company.get("score_marketing", 0) or 0}

        if total_contacts == 0 or not interactions:
            results.append({
                "company_id": cid, "company_name": company["name"], "sector": company["sector"],
                "tier": company.get("tier"), "rating": company.get("rating", "C"),
                "account_manager_name": company.get("account_manager_name"),
                "score": 0, "sub_scores": empty_sub, "interaction_points": 0,
                "decay_factor": 0.10, "days_since_last": None, "total_contacts": total_contacts,
                "contacted_count": 0, "total_interactions": 0, "channel_types": [], "level": "kold",
                "score_color": "roed", "tags": tags_by_company.get(cid, []), **mx})
            continue

        sub_scores, score, details = _calc_sub_scores(company, contacts_data, interactions, total_contacts)

        # Apply configurable penalty points for inactivity
        penalty = 0
        if details["days_since_last"] is not None:
            for rule in decay_penalty_rules:
                if details["days_since_last"] >= rule["inactivity_days"]:
                    penalty = rule["penalty_points"]
        score = max(0, round(score - penalty, 1))

        level = "staerk" if score >= 80 else "god" if score >= 50 else "svag" if score >= 20 else "kold"

        results.append({
            "company_id": cid, "company_name": company["name"], "sector": company["sector"],
            "tier": company.get("tier"), "rating": company.get("rating", "C"),
            "account_manager_name": company.get("account_manager_name"),
            "score": score, "sub_scores": sub_scores,
            "interaction_points": details["interaction_points"],
            "decay_factor": details["decay_factor"], "days_since_last": details["days_since_last"],
            "total_contacts": total_contacts, "contacted_count": details["contacted_count"],
            "total_interactions": details["total_interactions"], "channel_types": details["channel_types"],
            "level": level, "penalty": penalty, "score_color": score_color_100(score),
            "tags": tags_by_company.get(cid, []), **mx})

    # Save score snapshot to history (max 1 per day per company)
    today = date.today().isoformat()
    existing_today = set()
    for r in conn.execute("SELECT company_id FROM score_history WHERE recorded_at = ?", (today,)).fetchall():
        existing_today.add(r["company_id"])
    for r in results:
        if r["company_id"] not in existing_today:
            conn.execute("INSERT INTO score_history (company_id, score, level, recorded_at) VALUES (?,?,?,?)",
                         (r["company_id"], r["score"], r["level"], today))
    conn.commit()

    return results

# ─── Email Parser ───
def parse_eml(content):
    msg = email_lib.message_from_bytes(content, policy=email_policy.default)
    from_addr = str(msg.get("From", ""))
    to_addr = str(msg.get("To", ""))
    cc_addr = str(msg.get("Cc", ""))
    subject = str(msg.get("Subject", ""))
    date_sent = None
    date_str = msg.get("Date")
    if date_str:
        try:
            date_sent = parsedate_to_datetime(str(date_str)).isoformat()
        except Exception:
            pass
    body_text, body_html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not body_text:
                body_text = part.get_content()
            elif ct == "text/html" and not body_html:
                body_html = part.get_content()
    else:
        ct = msg.get_content_type()
        if ct == "text/plain":
            body_text = msg.get_content()
        elif ct == "text/html":
            body_html = msg.get_content()
    return {"from_email": from_addr, "to_email": to_addr, "cc": cc_addr, "subject": subject,
            "body_text": body_text, "body_html": body_html, "date_sent": date_sent}

# ─── HTTP Handler ───
class CRMHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def _get_user_id(self):
        """Extract current user ID from X-User-Id header."""
        uid = self.headers.get("X-User-Id")
        if uid:
            try:
                return int(uid)
            except (ValueError, TypeError):
                pass
        return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path.startswith("/api/"):
            self._handle_api_get(path, params)
        elif path == "/":
            self._serve_file("index.html", "text/html")
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
            ext = rel.rsplit(".", 1)[-1] if "." in rel else ""
            ct_map = {"js": "application/javascript", "css": "text/css", "html": "text/html", "png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml", "ico": "image/x-icon", "json": "application/json"}
            self._serve_file(rel, ct_map.get(ext, "application/octet-stream"))
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_type = self.headers.get("Content-Type", "")

        if "multipart/form-data" in content_type:
            self._handle_file_upload(path)
        elif path.startswith("/api/"):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            self._handle_api_post(path, body)

    def do_PUT(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        self._handle_api_put(parsed.path, body)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        self._handle_api_delete(parsed.path)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-User-Id")

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _no_content(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _error(self, status, msg):
        self._json_response({"detail": msg}, status)

    def _serve_file(self, filename, content_type):
        filepath = os.path.join(STATIC_DIR, filename)
        if os.path.exists(filepath):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            with open(filepath, "rb") as f:
                self.wfile.write(f.read())
        else:
            self._error(404, "File not found")

    # ─── API GET routes ───
    def _handle_api_get(self, path, params):
        conn = get_db()
        try:
            # Companies
            if path == "/api/companies":
                q = """SELECT c.*, u.name AS account_manager_name
                       FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE 1=1"""
                p = []
                if "sector" in params:
                    q += " AND c.sector = ?"; p.append(params["sector"][0])
                if "tier" in params:
                    q += " AND c.tier = ?"; p.append(params["tier"][0])
                if "rating" in params:
                    q += " AND c.rating = ?"; p.append(params["rating"][0])
                if "account_manager_id" in params:
                    q += " AND c.account_manager_id = ?"; p.append(int(params["account_manager_id"][0]))
                if "search" in params:
                    q += " AND c.name LIKE ?"; p.append("%{}%".format(params["search"][0]))
                if "tag_id" in params:
                    q += " AND c.id IN (SELECT company_id FROM company_tags WHERE tag_id = ?)"
                    p.append(int(params["tag_id"][0]))
                q += " ORDER BY c.name"
                rows = [dict(r) for r in conn.execute(q, p).fetchall()]
                # Attach tags to each company
                tags_map = {}
                for r in conn.execute(
                        """SELECT ct.company_id, t.id, t.name, t.color
                           FROM company_tags ct JOIN tags t ON ct.tag_id = t.id ORDER BY t.name""").fetchall():
                    cid = r["company_id"]
                    if cid not in tags_map:
                        tags_map[cid] = []
                    tags_map[cid].append({"id": r["id"], "name": r["name"], "color": r["color"]})
                for row in rows:
                    row["tags"] = tags_map.get(row["id"], [])
                self._json_response(rows)

            elif path.startswith("/api/companies/") and path.endswith("/full") and path.count("/") == 4:
                # Combined company detail endpoint (1 request instead of 10)
                cid = int(path.split("/")[-2])
                company = conn.execute(
                    """SELECT c.*, u.name AS account_manager_name
                       FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = ?""", (cid,)).fetchone()
                if not company:
                    return self._error(404, "Virksomhed ikke fundet")
                contacts = [dict(r) for r in conn.execute("SELECT * FROM contacts WHERE company_id = ? ORDER BY last_name, first_name", (cid,)).fetchall()]
                score = calculate_company_score(cid)
                interactions = [dict(r) for r in conn.execute(
                    """SELECT i.*, ct.first_name || ' ' || ct.last_name AS contact_name, u.name AS user_name
                       FROM interactions i LEFT JOIN contacts ct ON i.contact_id = ct.id
                       LEFT JOIN users u ON i.user_id = u.id
                       WHERE (ct.company_id = ? OR i.company_id = ?) ORDER BY i.date DESC""", (cid, cid)).fetchall()]
                emails = [dict(r) for r in conn.execute(
                    """SELECT e.* FROM emails e LEFT JOIN interactions i ON e.interaction_id = i.id
                       LEFT JOIN contacts ct ON i.contact_id = ct.id WHERE ct.company_id = ? ORDER BY e.date_sent DESC""", (cid,)).fetchall()]
                users = [dict(r) for r in conn.execute("SELECT * FROM users WHERE deleted_at IS NULL ORDER BY name").fetchall()]
                tasks = [dict(r) for r in conn.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id
                       WHERE t.company_id = ?
                       ORDER BY CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, t.due_date ASC""", (cid,)).fetchall()]
                audit = [dict(r) for r in conn.execute(
                    "SELECT * FROM audit_log WHERE entity_type = 'company' AND entity_id = ? ORDER BY created_at DESC LIMIT 20", (cid,)).fetchall()]
                li_activities = [dict(r) for r in conn.execute(
                    """SELECT la.*, ct.first_name || ' ' || ct.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_activities la JOIN contacts ct ON la.contact_id = ct.id
                       JOIN companies co ON ct.company_id = co.id LEFT JOIN users u ON la.observed_by = u.id
                       WHERE co.id = ? ORDER BY la.activity_date DESC LIMIT 50""", (cid,)).fetchall()]
                li_engagements = [dict(r) for r in conn.execute(
                    """SELECT le.*, ct.first_name || ' ' || ct.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_engagements le JOIN contacts ct ON le.contact_id = ct.id
                       JOIN companies co ON ct.company_id = co.id LEFT JOIN users u ON le.observed_by = u.id
                       WHERE co.id = ? ORDER BY le.observed_date DESC LIMIT 50""", (cid,)).fetchall()]
                # Tags for company
                company_tags = [dict(r) for r in conn.execute(
                    "SELECT t.* FROM tags t JOIN company_tags ct ON t.id = ct.tag_id WHERE ct.company_id = ? ORDER BY t.name", (cid,)).fetchall()]
                # Tags for each contact
                for c in contacts:
                    c["tags"] = [dict(r) for r in conn.execute(
                        "SELECT t.* FROM tags t JOIN contact_tags ct ON t.id = ct.tag_id WHERE ct.contact_id = ? ORDER BY t.name", (c["id"],)).fetchall()]
                # All tags (for autocomplete)
                all_tags = [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY name").fetchall()]
                tenders = [dict(r) for r in conn.execute(
                    """SELECT t.*, u.name AS responsible_name
                       FROM tenders t LEFT JOIN users u ON t.responsible_id = u.id
                       WHERE t.company_id = ? ORDER BY t.created_at DESC""", (cid,)).fetchall()]
                self._json_response({
                    "company": dict(company), "contacts": contacts, "score": score,
                    "interactions": interactions, "emails": emails, "users": users,
                    "tasks": tasks, "audit_log": audit,
                    "linkedin_activities": li_activities, "linkedin_engagements": li_engagements,
                    "company_tags": company_tags, "all_tags": all_tags, "tenders": tenders
                })

            elif path.startswith("/api/companies/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = conn.execute(
                    """SELECT c.*, u.name AS account_manager_name
                       FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = ?""", (cid,)).fetchone()
                if not row:
                    return self._error(404, "Virksomhed ikke fundet")
                self._json_response(dict(row))

            # Contacts
            elif path == "/api/contacts":
                q = "SELECT * FROM contacts WHERE 1=1"
                p = []
                if "company_id" in params:
                    q += " AND company_id = ?"; p.append(int(params["company_id"][0]))
                if "search" in params:
                    s = "%{}%".format(params["search"][0])
                    q += " AND (first_name LIKE ? OR last_name LIKE ? OR email LIKE ?)"; p.extend([s]*3)
                q += " ORDER BY last_name, first_name"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])
            elif path.startswith("/api/contacts/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
                if not row:
                    return self._error(404, "Kontakt ikke fundet")
                self._json_response(dict(row))

            # Interactions
            elif path == "/api/interactions":
                q = """SELECT i.*, c.first_name || ' ' || c.last_name AS contact_name, u.name AS user_name
                       FROM interactions i LEFT JOIN contacts c ON i.contact_id = c.id
                       LEFT JOIN users u ON i.user_id = u.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND i.contact_id = ?"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND c.company_id = ?"; p.append(int(params["company_id"][0]))
                if "type" in params:
                    q += " AND i.type = ?"; p.append(params["type"][0])
                q += " ORDER BY i.date DESC"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])

            # Users
            elif path == "/api/users":
                self._json_response([dict(r) for r in conn.execute("SELECT * FROM users WHERE deleted_at IS NULL ORDER BY name").fetchall()])

            # Emails
            elif path == "/api/emails":
                q = """SELECT e.* FROM emails e LEFT JOIN interactions i ON e.interaction_id = i.id
                       LEFT JOIN contacts c ON i.contact_id = c.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND i.contact_id = ?"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND c.company_id = ?"; p.append(int(params["company_id"][0]))
                q += " ORDER BY e.date_sent DESC"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])
            elif path.startswith("/api/emails/") and path.count("/") == 3:
                eid = int(path.split("/")[-1])
                row = conn.execute("SELECT * FROM emails WHERE id = ?", (eid,)).fetchone()
                if not row:
                    return self._error(404, "Email ikke fundet")
                self._json_response(dict(row))

            # Search
            elif path == "/api/search":
                q = params.get("q", [""])[0]
                if not q or len(q) < 2:
                    return self._json_response({"companies": [], "contacts": []})
                term = "%{}%".format(q)
                # Search companies by name, city, OR tag
                companies = [dict(r) for r in conn.execute(
                    """SELECT DISTINCT co.id, co.name, co.sector, co.city, co.rating FROM companies co
                       LEFT JOIN company_tags ct ON co.id = ct.company_id
                       LEFT JOIN tags t ON ct.tag_id = t.id
                       WHERE co.name LIKE ? OR co.city LIKE ? OR t.name LIKE ?
                       ORDER BY co.name LIMIT 10""",
                    (term, term, term)).fetchall()]
                # Search contacts by name, email, OR tag
                contacts = [dict(r) for r in conn.execute(
                    """SELECT DISTINCT c.id, c.first_name, c.last_name, c.title, c.email, c.company_id, co.name AS company_name
                       FROM contacts c JOIN companies co ON c.company_id = co.id
                       LEFT JOIN contact_tags cta ON c.id = cta.contact_id
                       LEFT JOIN tags t ON cta.tag_id = t.id
                       WHERE c.first_name LIKE ? OR c.last_name LIKE ? OR c.email LIKE ?
                       OR (c.first_name || ' ' || c.last_name) LIKE ? OR t.name LIKE ?
                       ORDER BY c.last_name LIMIT 10""",
                    (term, term, term, term, term)).fetchall()]
                self._json_response({"companies": companies, "contacts": contacts})

            # Tasks
            elif path == "/api/tasks":
                q = """SELECT t.*, c.name AS company_name,
                       u1.name AS assigned_to_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tasks t
                       JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id
                       WHERE 1=1"""
                p = []
                if "company_id" in params:
                    q += " AND t.company_id = ?"; p.append(int(params["company_id"][0]))
                if "assigned_to" in params:
                    q += " AND t.assigned_to = ?"; p.append(int(params["assigned_to"][0]))
                if "status" in params:
                    q += " AND t.status = ?"; p.append(params["status"][0])
                if "category" in params:
                    q += " AND t.category = ?"; p.append(params["category"][0])
                if "overdue" in params:
                    q += " AND t.due_date < date('now') AND t.status != 'done'"
                q += " ORDER BY CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, t.due_date ASC NULLS LAST, t.created_at DESC"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])

            elif path == "/api/tasks/summary":
                rows = conn.execute("SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status").fetchall()
                summary = {"open": 0, "in_progress": 0, "done": 0}
                for r in rows:
                    summary[r["status"]] = r["cnt"]
                overdue = conn.execute("SELECT COUNT(*) FROM tasks WHERE due_date < date('now') AND status != 'done'").fetchone()[0]
                this_week = conn.execute("SELECT COUNT(*) FROM tasks WHERE due_date BETWEEN date('now') AND date('now', '+7 days') AND status != 'done'").fetchone()[0]
                summary["overdue"] = overdue
                summary["this_week"] = this_week
                self._json_response(summary)

            elif path.startswith("/api/tasks/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = conn.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       WHERE t.id = ?""", (tid,)).fetchone()
                if not row:
                    return self._error(404, "Sag ikke fundet")
                self._json_response(dict(row))

            # Task notes
            elif path.startswith("/api/tasks/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM task_notes WHERE task_id = ? ORDER BY created_at DESC", (tid,)).fetchall()]
                self._json_response(rows)

            # Task history (audit log for this task)
            elif path.startswith("/api/tasks/") and path.endswith("/history"):
                tid = int(path.split("/")[-2])
                rows = [dict(r) for r in conn.execute(
                    """SELECT * FROM audit_log WHERE entity_type = 'task' AND entity_id = ?
                       ORDER BY created_at DESC""", (tid,)).fetchall()]
                self._json_response(rows)

            # Tender notes
            elif path.startswith("/api/tenders/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM tender_notes WHERE tender_id = ? ORDER BY created_at DESC", (tid,)).fetchall()]
                self._json_response(rows)

            # Tender history (audit log for this tender)
            elif path.startswith("/api/tenders/") and path.endswith("/history"):
                tid = int(path.split("/")[-2])
                rows = [dict(r) for r in conn.execute(
                    """SELECT * FROM audit_log WHERE entity_type = 'tender' AND entity_id = ?
                       ORDER BY created_at DESC""", (tid,)).fetchall()]
                self._json_response(rows)

            # Audit log
            elif path == "/api/audit-log":
                q = "SELECT * FROM audit_log WHERE 1=1"
                p = []
                if "entity_type" in params:
                    q += " AND entity_type = ?"; p.append(params["entity_type"][0])
                if "entity_id" in params:
                    q += " AND entity_id = ?"; p.append(int(params["entity_id"][0]))
                if "user_id" in params:
                    q += " AND user_id = ?"; p.append(int(params["user_id"][0]))
                q += " ORDER BY created_at DESC"
                limit = int(params.get("limit", ["50"])[0])
                q += " LIMIT ?"; p.append(limit)
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])

            # Notifications
            elif path == "/api/notifications":
                q = "SELECT n.*, c.name AS company_name FROM notifications n JOIN companies c ON n.company_id = c.id WHERE 1=1"
                p = []
                if "is_read" in params:
                    q += " AND n.is_read = ?"; p.append(int(params["is_read"][0]))
                q += " ORDER BY n.created_at DESC LIMIT 50"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])

            elif path == "/api/notifications/count":
                cnt = conn.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0").fetchone()[0]
                self._json_response({"unread": cnt})

            elif path == "/api/notifications/check":
                check_score_notifications(conn)
                cnt = conn.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0").fetchone()[0]
                self._json_response({"checked": True, "unread": cnt})

            # Score settings
            elif path == "/api/settings/score-thresholds":
                rows = conn.execute("SELECT rating, threshold FROM score_settings ORDER BY rating").fetchall()
                self._json_response({r["rating"]: r["threshold"] for r in rows})

            # Decay rules
            elif path == "/api/settings/decay-rules":
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM score_decay_rules ORDER BY inactivity_days").fetchall()]
                self._json_response(rows)

            # LinkedIn activities
            elif path == "/api/linkedin-activities":
                q = """SELECT la.*, c.first_name || ' ' || c.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_activities la
                       JOIN contacts c ON la.contact_id = c.id
                       JOIN companies co ON c.company_id = co.id
                       LEFT JOIN users u ON la.observed_by = u.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND la.contact_id = ?"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND co.id = ?"; p.append(int(params["company_id"][0]))
                q += " ORDER BY la.activity_date DESC LIMIT 50"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])

            # LinkedIn engagements
            elif path == "/api/linkedin-engagements":
                q = """SELECT le.*, c.first_name || ' ' || c.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_engagements le
                       JOIN contacts c ON le.contact_id = c.id
                       JOIN companies co ON c.company_id = co.id
                       LEFT JOIN users u ON le.observed_by = u.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND le.contact_id = ?"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND co.id = ?"; p.append(int(params["company_id"][0]))
                if "company_page" in params:
                    q += " AND le.company_page = ?"; p.append(params["company_page"][0])
                q += " ORDER BY le.observed_date DESC LIMIT 50"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])

            # Score history aggregate (avg per day across all companies)
            elif path == "/api/score-history/aggregate":
                rows = conn.execute("""
                    SELECT recorded_at AS date,
                           ROUND(AVG(score), 1) AS avg_score,
                           COUNT(*) AS total_companies,
                           SUM(CASE WHEN level='staerk' THEN 1 ELSE 0 END) AS strong,
                           SUM(CASE WHEN level='god' THEN 1 ELSE 0 END) AS good,
                           SUM(CASE WHEN level='svag' THEN 1 ELSE 0 END) AS weak,
                           SUM(CASE WHEN level='kold' THEN 1 ELSE 0 END) AS cold
                    FROM score_history
                    GROUP BY recorded_at
                    ORDER BY recorded_at ASC
                    LIMIT 90
                """).fetchall()
                self._json_response([dict(r) for r in rows])

            # Dashboard - combined endpoint (1 request instead of 2)
            elif path == "/api/dashboard/all":
                scores = calculate_all_scores(conn)
                total = len(scores)
                stats = {"total": 0, "strong": 0, "good": 0, "weak": 0, "cold": 0, "avg_score": 0}
                if total > 0:
                    stats = {
                        "total": total,
                        "strong": sum(1 for s in scores if s["level"] == "staerk"),
                        "good": sum(1 for s in scores if s["level"] == "god"),
                        "weak": sum(1 for s in scores if s["level"] == "svag"),
                        "cold": sum(1 for s in scores if s["level"] == "kold"),
                        "avg_score": round(sum(s["score"] for s in scores) / total, 1),
                    }
                all_tags = [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY name").fetchall()]

                # Accept days or from_date param
                if "from_date" in params:
                    from_date = params["from_date"][0]
                    date_cutoff = f"'{from_date}'"
                else:
                    days = max(1, min(365, int(params.get("days", ["14"])[0])))
                    date_cutoff = f"date('now', '-{days} days')"

                # Recent activities - unified feed from multiple tables
                recent_activities = [dict(r) for r in conn.execute(f"""
                    SELECT 'interaction' AS source, i.id, i.id AS entity_id,
                           i.date AS activity_date, i.type AS sub_type,
                           i.subject, COALESCE(co.id, co2.id) AS company_id,
                           COALESCE(co.name, co2.name) AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM interactions i
                    LEFT JOIN contacts ct ON i.contact_id = ct.id
                    LEFT JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN companies co2 ON i.company_id = co2.id
                    LEFT JOIN users u ON i.user_id = u.id
                    WHERE i.date >= {date_cutoff}

                    UNION ALL

                    SELECT 'task' AS source, t.id, t.id AS entity_id,
                           COALESCE(t.completed_at, t.created_at) AS activity_date,
                           t.category AS sub_type, t.title AS subject,
                           co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM tasks t
                    JOIN companies co ON t.company_id = co.id
                    LEFT JOIN contacts ct ON t.contact_id = ct.id
                    LEFT JOIN users u ON t.assigned_to = u.id
                    WHERE t.created_at >= {date_cutoff} OR (t.completed_at IS NOT NULL AND t.completed_at >= {date_cutoff})

                    UNION ALL

                    SELECT 'task_note' AS source, tn.id, t.id AS entity_id,
                           tn.created_at AS activity_date, 'note' AS sub_type,
                           tn.content AS subject,
                           co.id AS company_id, co.name AS company_name,
                           NULL AS contact_name, tn.user_name AS user_name
                    FROM task_notes tn
                    JOIN tasks t ON tn.task_id = t.id
                    JOIN companies co ON t.company_id = co.id
                    WHERE tn.created_at >= {date_cutoff}

                    UNION ALL

                    SELECT 'tender_note' AS source, tn.id, t.id AS entity_id,
                           tn.created_at AS activity_date, 'note' AS sub_type,
                           tn.content AS subject,
                           co.id AS company_id, co.name AS company_name,
                           NULL AS contact_name, tn.user_name AS user_name
                    FROM tender_notes tn
                    JOIN tenders t ON tn.tender_id = t.id
                    JOIN companies co ON t.company_id = co.id
                    WHERE tn.created_at >= {date_cutoff}

                    UNION ALL

                    SELECT 'tender' AS source, al.id, t.id AS entity_id,
                           al.created_at AS activity_date, al.action AS sub_type,
                           CASE al.action
                               WHEN 'update' THEN t.title || ' → ' || COALESCE(json_extract(al.details, '$.status'), '')
                               ELSE t.title
                           END AS subject,
                           co.id AS company_id, co.name AS company_name,
                           NULL AS contact_name, al.user_name AS user_name
                    FROM audit_log al
                    JOIN tenders t ON al.entity_id = t.id
                    JOIN companies co ON t.company_id = co.id
                    WHERE al.entity_type = 'tender' AND al.action IN ('create', 'update')
                    AND al.created_at >= {date_cutoff}

                    UNION ALL

                    SELECT 'contact' AS source, al.id, ct.company_id AS entity_id,
                           al.created_at AS activity_date, 'create' AS sub_type,
                           al.entity_name AS subject,
                           co.id AS company_id, co.name AS company_name,
                           al.entity_name AS contact_name, al.user_name AS user_name
                    FROM audit_log al
                    JOIN contacts ct ON al.entity_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    WHERE al.entity_type = 'contact' AND al.action = 'create'
                    AND al.created_at >= {date_cutoff}

                    UNION ALL

                    SELECT 'linkedin_activity' AS source, la.id, la.id AS entity_id,
                           la.activity_date, la.activity_type AS sub_type,
                           la.content_summary AS subject, co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM linkedin_activities la
                    JOIN contacts ct ON la.contact_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN users u ON la.observed_by = u.id
                    WHERE la.activity_date >= {date_cutoff}

                    UNION ALL

                    SELECT 'linkedin_engagement' AS source, le.id, le.id AS entity_id,
                           le.observed_date AS activity_date,
                           le.engagement_type AS sub_type, le.notes AS subject,
                           co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM linkedin_engagements le
                    JOIN contacts ct ON le.contact_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN users u ON le.observed_by = u.id
                    WHERE le.observed_date >= {date_cutoff}

                    ORDER BY activity_date DESC
                    LIMIT 100
                """).fetchall()]

                # Previous scores for delta indicators
                prev_scores = {}
                for r in conn.execute("""
                    SELECT sh.company_id, sh.score FROM score_history sh
                    INNER JOIN (
                        SELECT company_id, MAX(recorded_at) AS max_date
                        FROM score_history WHERE recorded_at < date('now')
                        GROUP BY company_id
                    ) latest ON sh.company_id = latest.company_id AND sh.recorded_at = latest.max_date
                """).fetchall():
                    prev_scores[r["company_id"]] = r["score"]
                for s in scores:
                    ps = prev_scores.get(s["company_id"])
                    s["previous_score"] = ps

                # Active tenders (not won/lost/dropped)
                active_tenders = [dict(r) for r in conn.execute("""
                    SELECT t.id, t.title, t.status, t.deadline, t.estimated_value,
                           co.id AS company_id, co.name AS company_name,
                           u.name AS responsible_name,
                           (SELECT COUNT(*) FROM tender_sections ts WHERE ts.tender_id = t.id) AS total_sections,
                           (SELECT COUNT(*) FROM tender_sections ts WHERE ts.tender_id = t.id AND ts.status = 'approved') AS approved_sections
                    FROM tenders t
                    JOIN companies co ON t.company_id = co.id
                    LEFT JOIN users u ON t.responsible_id = u.id
                    WHERE t.status NOT IN ('won', 'lost', 'dropped')
                    ORDER BY t.deadline ASC
                """).fetchall()]

                self._json_response({"scores": scores, "stats": stats, "all_tags": all_tags, "recent_activities": recent_activities, "active_tenders": active_tenders})

            elif path == "/api/dashboard/scores":
                scores = calculate_all_scores(conn)
                sector = params.get("sector", [None])[0]
                if sector:
                    scores = [s for s in scores if s["sector"] == sector]
                rating = params.get("rating", [None])[0]
                if rating:
                    scores = [s for s in scores if s.get("rating") == rating]
                sort_by = params.get("sort_by", ["score"])[0]
                if sort_by == "score":
                    scores.sort(key=lambda s: s["score"], reverse=True)
                elif sort_by == "name":
                    scores.sort(key=lambda s: s["company_name"])
                self._json_response(scores)

            elif path.startswith("/api/dashboard/scores/"):
                cid = int(path.split("/")[-1])
                result = calculate_company_score(cid)
                if not result:
                    return self._error(404, "Virksomhed ikke fundet")
                self._json_response(result)

            elif path == "/api/dashboard/stats":
                scores = calculate_all_scores(conn)
                total = len(scores)
                if total == 0:
                    self._json_response({"total": 0, "strong": 0, "good": 0, "weak": 0, "cold": 0, "avg_score": 0})
                else:
                    self._json_response({
                        "total": total,
                        "strong": sum(1 for s in scores if s["level"] == "staerk"),
                        "good": sum(1 for s in scores if s["level"] == "god"),
                        "weak": sum(1 for s in scores if s["level"] == "svag"),
                        "cold": sum(1 for s in scores if s["level"] == "kold"),
                        "avg_score": round(sum(s["score"] for s in scores) / total, 1),
                    })
            # Tags
            elif path == "/api/tags":
                rows = conn.execute(
                    """SELECT t.*,
                       (SELECT COUNT(*) FROM company_tags WHERE tag_id = t.id) +
                       (SELECT COUNT(*) FROM contact_tags WHERE tag_id = t.id) AS usage_count
                       FROM tags t ORDER BY t.name""").fetchall()
                self._json_response([dict(r) for r in rows])

            # Tenders
            elif path == "/api/tenders":
                q = """SELECT t.*, c.name AS company_name,
                       u1.name AS responsible_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tenders t
                       JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.responsible_id = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id
                       WHERE 1=1"""
                p = []
                if "company_id" in params:
                    q += " AND t.company_id = ?"; p.append(int(params["company_id"][0]))
                if "status" in params:
                    q += " AND t.status = ?"; p.append(params["status"][0])
                q += " ORDER BY t.deadline ASC NULLS LAST, t.created_at DESC"
                tenders = [dict(r) for r in conn.execute(q, p).fetchall()]
                for tender in tenders:
                    sections = conn.execute(
                        "SELECT status FROM tender_sections WHERE tender_id = ?", (tender["id"],)).fetchall()
                    total = len(sections)
                    done = sum(1 for s in sections if s["status"] == "approved")
                    tender["section_count"] = total
                    tender["sections_approved"] = done
                    tender["progress"] = round((done / total * 100) if total > 0 else 0)
                self._json_response(tenders)

            elif path.startswith("/api/tenders/") and path.endswith("/full"):
                tid = int(path.split("/")[-2])
                tender = conn.execute(
                    """SELECT t.*, c.name AS company_name,
                       u1.name AS responsible_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tenders t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.responsible_id = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id
                       WHERE t.id = ?""", (tid,)).fetchone()
                if not tender:
                    return self._error(404, "Tilbud ikke fundet")
                sections = [dict(r) for r in conn.execute(
                    """SELECT ts.*, u1.name AS responsible_name, u2.name AS reviewer_name
                       FROM tender_sections ts
                       LEFT JOIN users u1 ON ts.responsible_id = u1.id
                       LEFT JOIN users u2 ON ts.reviewer_id = u2.id
                       WHERE ts.tender_id = ?
                       ORDER BY ts.sort_order, ts.id""", (tid,)).fetchall()]
                users = [dict(r) for r in conn.execute("SELECT * FROM users WHERE deleted_at IS NULL ORDER BY name").fetchall()]
                companies = [dict(r) for r in conn.execute("SELECT id, name FROM companies ORDER BY name").fetchall()]
                self._json_response({
                    "tender": dict(tender), "sections": sections,
                    "users": users, "companies": companies
                })

            elif path == "/api/tender-templates":
                templates = [dict(r) for r in conn.execute(
                    "SELECT * FROM tender_templates ORDER BY is_default DESC, name").fetchall()]
                for t in templates:
                    t["section_count"] = conn.execute(
                        "SELECT COUNT(*) FROM tender_template_sections WHERE template_id = ?", (t["id"],)).fetchone()[0]
                self._json_response(templates)

            elif path.startswith("/api/tender-templates/") and path.count("/") == 3:
                tmpl_id = int(path.split("/")[-1])
                tmpl = conn.execute("SELECT * FROM tender_templates WHERE id = ?", (tmpl_id,)).fetchone()
                if not tmpl:
                    return self._error(404, "Skabelon ikke fundet")
                sections = [dict(r) for r in conn.execute(
                    "SELECT * FROM tender_template_sections WHERE template_id = ? ORDER BY sort_order", (tmpl_id,)).fetchall()]
                self._json_response({"template": dict(tmpl), "sections": sections})

            # Tender section audit trail
            elif path.startswith("/api/tender-sections/") and path.endswith("/audit"):
                sid = int(path.split("/")[-2])
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM tender_section_audit WHERE section_id = ? ORDER BY created_at DESC",
                    (sid,)).fetchall()]
                self._json_response(rows)

            else:
                self._error(404, "Endpoint not found")
        finally:
            conn.close()

    # ─── API POST routes ───
    def _handle_api_post(self, path, body):
        conn = get_db()
        uid = self._get_user_id()
        try:
            if path == "/api/companies":
                cur = conn.execute(
                    """INSERT INTO companies (name, sector, address, city, zip_code, website, notes, rating, account_manager_id,
                       importance, sales_stage, score_cxo, score_kontaktfrekvens, score_kontaktbredde, score_kendskab, score_historik,
                       tier, ejerform, has_el, has_gas, has_vand, has_varme, has_spildevand, has_affald, est_kunder)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (body["name"], body.get("sector"), body.get("address"), body.get("city"),
                     body.get("zip_code"), body.get("website"), body.get("notes"),
                     body.get("rating", "C"), body.get("account_manager_id"),
                     body.get("importance", "middel_vigtig"), body.get("sales_stage", "tidlig_fase"),
                     body.get("score_cxo", 0), body.get("score_kontaktfrekvens", 0),
                     body.get("score_kontaktbredde", 0), body.get("score_kendskab", 0), body.get("score_historik", 0),
                     body.get("tier"), body.get("ejerform"),
                     body.get("has_el", 0), body.get("has_gas", 0), body.get("has_vand", 0),
                     body.get("has_varme", 0), body.get("has_spildevand", 0), body.get("has_affald", 0),
                     body.get("est_kunder")))
                conn.commit()
                row = conn.execute(
                    "SELECT c.*, u.name AS account_manager_name FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = ?",
                    (cur.lastrowid,)).fetchone()
                log_audit(conn, uid, "create", "company", cur.lastrowid, body["name"])
                conn.commit()
                self._json_response(dict(row), 201)

            elif path == "/api/contacts":
                cur = conn.execute(
                    """INSERT INTO contacts (company_id,first_name,last_name,title,email,phone,linkedin_url,
                       on_linkedin_list,notes,linkedin_connected_systemate,linkedin_connected_settl) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (body["company_id"], body["first_name"], body["last_name"], body.get("title"),
                     body.get("email"), body.get("phone"), body.get("linkedin_url"),
                     body.get("on_linkedin_list", False), body.get("notes"),
                     body.get("linkedin_connected_systemate", False), body.get("linkedin_connected_settl", False)))
                conn.commit()
                row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)).fetchone()
                name = "{} {}".format(body["first_name"], body["last_name"])
                log_audit(conn, uid, "create", "contact", cur.lastrowid, name)
                conn.commit()
                self._json_response(dict(row), 201)

            elif path == "/api/interactions":
                contact_id = body.get("contact_id") or None
                company_id = body.get("company_id") or None
                # Auto-derive company_id from contact if not provided
                if contact_id and not company_id:
                    row = conn.execute("SELECT company_id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
                    if row: company_id = row["company_id"]
                cur = conn.execute(
                    "INSERT INTO interactions (contact_id,company_id,user_id,type,date,subject,notes) VALUES (?,?,?,?,?,?,?)",
                    (contact_id, company_id, body.get("user_id"), body["type"], body["date"],
                     body.get("subject"), body.get("notes")))
                conn.commit()
                row = conn.execute(
                    """SELECT i.*, c.first_name||' '||c.last_name AS contact_name, u.name AS user_name
                       FROM interactions i LEFT JOIN contacts c ON i.contact_id=c.id LEFT JOIN users u ON i.user_id=u.id
                       WHERE i.id=?""", (cur.lastrowid,)).fetchone()
                log_audit(conn, uid, "create", "interaction", cur.lastrowid, body.get("subject", body["type"]),
                          {"type": body["type"], "contact_id": contact_id})
                conn.commit()
                self._json_response(dict(row), 201)

            elif path == "/api/users":
                existing = conn.execute("SELECT id FROM users WHERE email = ?", (body["email"],)).fetchone()
                if existing:
                    return self._error(409, "Email allerede i brug")
                cur = conn.execute("INSERT INTO users (name,email,role) VALUES (?,?,?)",
                                   (body["name"], body["email"], body.get("role", "user")))
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
                log_audit(conn, uid, "create", "user", cur.lastrowid, body["name"])
                conn.commit()
                self._json_response(dict(row), 201)

            elif path.startswith("/api/users/") and path.endswith("/restore"):
                uid_restore = int(path.split("/")[-2])
                conn.execute("UPDATE users SET deleted_at = NULL WHERE id = ?", (uid_restore,))
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE id = ?", (uid_restore,)).fetchone()
                if row:
                    log_audit(conn, uid, "restore", "user", uid_restore, row["name"])
                    conn.commit()
                self._json_response(dict(row) if row else {})

            elif path == "/api/tasks":
                cur = conn.execute(
                    """INSERT INTO tasks (company_id, contact_id, assigned_to, created_by, category,
                       title, description, status, priority, due_date) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (body["company_id"], body.get("contact_id"), body.get("assigned_to"),
                     uid, body["category"], body["title"], body.get("description"),
                     body.get("status", "open"), body.get("priority", "normal"), body.get("due_date")))
                conn.commit()
                row = conn.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id LEFT JOIN users u2 ON t.created_by = u2.id
                       WHERE t.id = ?""", (cur.lastrowid,)).fetchone()
                log_audit(conn, uid, "create", "task", cur.lastrowid, body["title"],
                          {"category": body["category"], "company_id": body["company_id"]})
                conn.commit()
                self._json_response(dict(row), 201)

            # Task notes
            elif path.startswith("/api/tasks/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                user_name = None
                if uid:
                    ur = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                cur = conn.execute(
                    """INSERT INTO task_notes (task_id, user_id, user_name, content, note_type, metadata)
                       VALUES (?,?,?,?,?,?)""",
                    (tid, uid, user_name, body.get("content", ""),
                     body.get("note_type", "note"), body.get("metadata")))
                conn.commit()
                log_audit(conn, uid, "add_note", "task", tid, body.get("content", "")[:80])
                conn.commit()
                row = conn.execute("SELECT * FROM task_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
                self._json_response(dict(row), 201)

            # Tender notes
            elif path.startswith("/api/tenders/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                user_name = None
                if uid:
                    ur = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                cur = conn.execute(
                    """INSERT INTO tender_notes (tender_id, user_id, user_name, content)
                       VALUES (?,?,?,?)""",
                    (tid, uid, user_name, body.get("content", "")))
                conn.commit()
                log_audit(conn, uid, "add_note", "tender", tid, body.get("content", "")[:80])
                conn.commit()
                row = conn.execute("SELECT * FROM tender_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
                self._json_response(dict(row), 201)

            elif path == "/api/linkedin-activities":
                cur = conn.execute(
                    """INSERT INTO linkedin_activities (contact_id, activity_type, content_summary,
                       linkedin_post_url, observed_by, activity_date) VALUES (?,?,?,?,?,?)""",
                    (body["contact_id"], body["activity_type"], body.get("content_summary"),
                     body.get("linkedin_post_url"), uid, body["activity_date"]))
                conn.commit()
                # Also create a linkedin interaction to feed the score
                if body.get("create_interaction", True):
                    conn.execute(
                        "INSERT INTO interactions (contact_id, user_id, type, date, subject, notes) VALUES (?,?,'linkedin',?,?,?)",
                        (body["contact_id"], uid, body["activity_date"],
                         "LinkedIn: {}".format(body["activity_type"]),
                         body.get("content_summary", "")))
                    conn.commit()
                log_audit(conn, uid, "create", "linkedin_activity", cur.lastrowid,
                          body["activity_type"], {"contact_id": body["contact_id"]})
                conn.commit()
                self._json_response({"id": cur.lastrowid}, 201)

            elif path == "/api/linkedin-engagements":
                cur = conn.execute(
                    """INSERT INTO linkedin_engagements (contact_id, engagement_type, company_page,
                       post_url, observed_by, observed_date, notes) VALUES (?,?,?,?,?,?,?)""",
                    (body["contact_id"], body["engagement_type"], body["company_page"],
                     body.get("post_url"), uid, body["observed_date"], body.get("notes")))
                conn.commit()
                log_audit(conn, uid, "create", "linkedin_engagement", cur.lastrowid,
                          "{} on {}".format(body["engagement_type"], body["company_page"]),
                          {"contact_id": body["contact_id"]})
                conn.commit()
                self._json_response({"id": cur.lastrowid}, 201)

            # Tags
            elif path == "/api/tags":
                name = body.get("name", "").strip()
                if not name:
                    return self._error(400, "Tag-navn er paakraevet")
                # Auto-prefix with # if missing
                if not name.startswith("#"):
                    name = "#" + name
                existing = conn.execute("SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
                if existing:
                    return self._json_response({"id": existing["id"], "name": name}, 200)
                cur = conn.execute("INSERT INTO tags (name, color) VALUES (?, ?)",
                                   (name, body.get("color", "#6b7280")))
                conn.commit()
                log_audit(conn, uid, "create", "tag", cur.lastrowid, name)
                conn.commit()
                self._json_response({"id": cur.lastrowid, "name": name, "color": body.get("color", "#6b7280")}, 201)

            elif path.startswith("/api/companies/") and path.endswith("/tags") and path.count("/") == 4:
                cid = int(path.split("/")[-2])
                tag_id = body.get("tag_id")
                if not tag_id:
                    return self._error(400, "tag_id er paakraevet")
                try:
                    conn.execute("INSERT INTO company_tags (company_id, tag_id) VALUES (?, ?)", (cid, int(tag_id)))
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass  # Already tagged
                tag = conn.execute("SELECT name FROM tags WHERE id = ?", (int(tag_id),)).fetchone()
                log_audit(conn, uid, "create", "company_tag", cid, tag["name"] if tag else str(tag_id))
                conn.commit()
                self._json_response({"ok": True}, 201)

            elif path.startswith("/api/contacts/") and path.endswith("/tags") and path.count("/") == 4:
                cid = int(path.split("/")[-2])
                tag_id = body.get("tag_id")
                if not tag_id:
                    return self._error(400, "tag_id er paakraevet")
                try:
                    conn.execute("INSERT INTO contact_tags (contact_id, tag_id) VALUES (?, ?)", (cid, int(tag_id)))
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass  # Already tagged
                self._json_response({"ok": True}, 201)

            # Tenders
            elif path == "/api/tenders":
                cur = conn.execute(
                    """INSERT INTO tenders (company_id, template_id, title, description, status,
                       deadline, contact_id, responsible_id, created_by, estimated_value, portal_link, notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (body["company_id"], body.get("template_id"), body["title"], body.get("description"),
                     body.get("status", "draft"), body.get("deadline"), body.get("contact_id"),
                     body.get("responsible_id"), uid, body.get("estimated_value"),
                     body.get("portal_link"), body.get("notes")))
                tender_id = cur.lastrowid
                template_id = body.get("template_id")
                if template_id:
                    tmpl_sections = conn.execute(
                        "SELECT * FROM tender_template_sections WHERE template_id = ? ORDER BY sort_order",
                        (int(template_id),)).fetchall()
                    prev_end = None
                    for ts in tmpl_sections:
                        section_deadline = None
                        section_start = None
                        section_end = None
                        if body.get("deadline") and ts["default_days_before_deadline"]:
                            try:
                                from datetime import timedelta
                                td = date.fromisoformat(body["deadline"])
                                section_end = (td - timedelta(days=ts["default_days_before_deadline"])).isoformat()
                                section_deadline = section_end
                                section_start = prev_end or date.today().isoformat()
                                prev_end = section_end
                            except (ValueError, TypeError):
                                pass
                        conn.execute(
                            """INSERT INTO tender_sections (tender_id, title, description, status, deadline, start_date, end_date, sort_order)
                               VALUES (?,?,?,'not_started',?,?,?,?)""",
                            (tender_id, ts["title"], ts["description"], section_deadline, section_start, section_end, ts["sort_order"]))
                conn.commit()
                log_audit(conn, uid, "create", "tender", tender_id, body["title"],
                          {"company_id": body["company_id"]})
                conn.commit()
                row = conn.execute(
                    """SELECT t.*, c.name AS company_name FROM tenders t
                       JOIN companies c ON t.company_id = c.id WHERE t.id = ?""", (tender_id,)).fetchone()
                self._json_response(dict(row), 201)

            # Tender section comments
            elif path.startswith("/api/tender-sections/") and path.endswith("/comments"):
                sid = int(path.split("/")[-2])
                user_name = None
                if uid:
                    ur = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                conn.execute(
                    """INSERT INTO tender_section_audit
                       (section_id, user_id, user_name, note_type, content)
                       VALUES (?,?,?,'comment',?)""",
                    (sid, uid, user_name, body.get("content", "")))
                conn.commit()
                self._json_response({"ok": True}, 201)

            elif path == "/api/tender-sections":
                cur = conn.execute(
                    """INSERT INTO tender_sections (tender_id, title, description, content,
                       responsible_id, reviewer_id, status, deadline, start_date, end_date, sort_order, notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (body["tender_id"], body["title"], body.get("description"),
                     body.get("content"), body.get("responsible_id"), body.get("reviewer_id"),
                     body.get("status", "not_started"), body.get("deadline"),
                     body.get("start_date"), body.get("end_date"),
                     body.get("sort_order", 0), body.get("notes")))
                section_id = cur.lastrowid
                conn.commit()
                log_audit(conn, uid, "create", "tender_section", section_id, body["title"],
                          json.dumps({"tender_id": body["tender_id"]}))
                # Audit trail entry for creation
                user_name = None
                if uid:
                    ur = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                conn.execute(
                    """INSERT INTO tender_section_audit
                       (section_id, user_id, user_name, note_type, content)
                       VALUES (?,?,?,'created','Sektion oprettet')""",
                    (section_id, uid, user_name))
                conn.commit()
                row = conn.execute(
                    """SELECT ts.*, u1.name AS responsible_name, u2.name AS reviewer_name
                       FROM tender_sections ts
                       LEFT JOIN users u1 ON ts.responsible_id = u1.id
                       LEFT JOIN users u2 ON ts.reviewer_id = u2.id
                       WHERE ts.id = ?""", (section_id,)).fetchone()
                self._json_response(dict(row), 201)

            elif path == "/api/tender-templates":
                cur = conn.execute(
                    "INSERT INTO tender_templates (name, description) VALUES (?,?)",
                    (body["name"], body.get("description")))
                conn.commit()
                log_audit(conn, uid, "create", "tender_template", cur.lastrowid, body["name"])
                conn.commit()
                self._json_response({"id": cur.lastrowid, "name": body["name"]}, 201)

            # Template sections
            elif path.startswith("/api/tender-templates/") and path.endswith("/sections"):
                tmpl_id = int(path.split("/")[-2])
                max_sort = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) FROM tender_template_sections WHERE template_id = ?",
                    (tmpl_id,)).fetchone()[0]
                cur = conn.execute(
                    """INSERT INTO tender_template_sections
                       (template_id, title, description, default_days_before_deadline, sort_order)
                       VALUES (?,?,?,?,?)""",
                    (tmpl_id, body["title"], body.get("description"),
                     body.get("default_days_before_deadline", 7),
                     body.get("sort_order", max_sort + 1)))
                conn.commit()
                self._json_response({"id": cur.lastrowid}, 201)

            else:
                self._error(404, "Endpoint not found")
        finally:
            conn.close()

    # ─── File upload ───
    def _handle_file_upload(self, path):
        if path not in ("/api/emails/upload", "/api/tasks/upload-email"):
            return self._error(404, "Endpoint not found")

        uid = self._get_user_id()
        content_type = self.headers["Content-Type"]
        content_length = int(self.headers["Content-Length"])
        body = self.rfile.read(content_length)

        boundary = content_type.split("boundary=")[1].encode()
        parts = body.split(b"--" + boundary)

        fields = {}
        file_content = None
        file_name = None

        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            header = part[:header_end].decode("utf-8", errors="replace")
            data = part[header_end + 4:]
            if data.endswith(b"\r\n"):
                data = data[:-2]

            if 'name="file"' in header or 'name="file";' in header:
                file_content = data
                fn_start = header.find('filename="')
                if fn_start != -1:
                    fn_start += 10
                    fn_end = header.find('"', fn_start)
                    file_name = header[fn_start:fn_end]
            else:
                name_start = header.find('name="') + 6
                name_end = header.find('"', name_start)
                field_name = header[name_start:name_end]
                fields[field_name] = data.decode("utf-8").strip()

        if not file_content or not file_name:
            return self._error(400, "Ingen fil modtaget")
        if not (file_name.lower().endswith(".eml") or file_name.lower().endswith(".msg")):
            return self._error(400, f"Filtypen '{file_name.rsplit('.', 1)[-1]}' er ikke understottet. Kun .eml filer er tilladt. Tip: Traek emailen fra Outlook til Skrivebordet foerst, saa dannes en .eml fil.")

        parsed = parse_eml(file_content)

        # Task email upload — save as a task note
        if path == "/api/tasks/upload-email":
            task_id = fields.get("task_id")
            if not task_id:
                return self._error(400, "task_id er paakraevet")
            user_name = None
            if uid:
                conn = get_db()
                ur = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
                if ur: user_name = ur["name"]
                conn.close()
            email_summary = "Fra: {}\nTil: {}\nDato: {}\nEmne: {}\n\n{}".format(
                parsed["from_email"] or "", parsed["to_email"] or "",
                parsed["date_sent"] or "", parsed["subject"] or "",
                (parsed["body_text"] or "")[:2000])
            metadata = json.dumps({"from": parsed["from_email"], "to": parsed["to_email"],
                                   "cc": parsed["cc"], "date_sent": parsed["date_sent"],
                                   "filename": file_name})
            conn = get_db()
            try:
                cur = conn.execute(
                    """INSERT INTO task_notes (task_id, user_id, user_name, content, note_type, metadata)
                       VALUES (?,?,?,?,?,?)""",
                    (int(task_id), uid, user_name, email_summary, "email", metadata))
                conn.commit()
                log_audit(conn, uid, "import_email", "task", int(task_id), file_name)
                conn.commit()
                row = conn.execute("SELECT * FROM task_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
                self._json_response(dict(row), 201)
            finally:
                conn.close()
            return

        contact_id = fields.get("contact_id")
        if not contact_id:
            return self._error(400, "contact_id er paakraevet")

        user_id = fields.get("user_id") or None

        conn = get_db()
        try:
            interaction_date = parsed["date_sent"][:10] if parsed["date_sent"] else None
            cur = conn.execute(
                "INSERT INTO interactions (contact_id,user_id,type,date,subject,notes) VALUES (?,?,'email',?,?,'Importeret fra .eml fil')",
                (int(contact_id), int(user_id) if user_id else None, interaction_date, parsed["subject"]))
            iid = cur.lastrowid
            cur2 = conn.execute(
                "INSERT INTO emails (interaction_id,from_email,to_email,cc,subject,body_text,body_html,date_sent,eml_filename) VALUES (?,?,?,?,?,?,?,?,?)",
                (iid, parsed["from_email"], parsed["to_email"], parsed["cc"], parsed["subject"],
                 parsed["body_text"], parsed["body_html"], parsed["date_sent"], file_name))
            conn.commit()
            log_audit(conn, uid, "import", "email", cur2.lastrowid, file_name,
                      {"contact_id": int(contact_id), "subject": parsed["subject"]})
            conn.commit()
            row = conn.execute("SELECT * FROM emails WHERE id = ?", (cur2.lastrowid,)).fetchone()
            self._json_response(dict(row), 201)
        finally:
            conn.close()

    # ─── API PUT routes ───
    def _handle_api_put(self, path, body):
        conn = get_db()
        uid = self._get_user_id()
        try:
            if path.startswith("/api/companies/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                existing = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
                if not existing:
                    return self._error(404, "Virksomhed ikke fundet")
                e = dict(existing)
                changes = {}
                for k, v in body.items():
                    if k in e and e[k] != v:
                        changes[k] = {"old": e[k], "new": v}
                    if k in e:
                        e[k] = v
                # Handle account_manager_id specially
                if "account_manager_id" in body:
                    e["account_manager_id"] = body["account_manager_id"]
                conn.execute(
                    """UPDATE companies SET name=?,sector=?,address=?,city=?,zip_code=?,website=?,notes=?,
                       rating=?,account_manager_id=?,importance=?,sales_stage=?,
                       score_cxo=?,score_kontaktfrekvens=?,score_kontaktbredde=?,score_kendskab=?,score_historik=?,
                       score_kendskab_behov=?,score_workshops=?,score_marketing=?,
                       tier=?,ejerform=?,has_el=?,has_gas=?,has_vand=?,has_varme=?,has_spildevand=?,has_affald=?,est_kunder=? WHERE id=?""",
                    (e["name"], e["sector"], e["address"], e["city"], e["zip_code"],
                     e["website"], e["notes"], e.get("rating", "C"), e.get("account_manager_id"),
                     e.get("importance", "middel_vigtig"), e.get("sales_stage", "tidlig_fase"),
                     e.get("score_cxo", 0), e.get("score_kontaktfrekvens", 0),
                     e.get("score_kontaktbredde", 0), e.get("score_kendskab", 0), e.get("score_historik", 0),
                     e.get("score_kendskab_behov", 0), e.get("score_workshops", 0), e.get("score_marketing", 0),
                     e.get("tier"), e.get("ejerform"),
                     e.get("has_el", 0), e.get("has_gas", 0), e.get("has_vand", 0),
                     e.get("has_varme", 0), e.get("has_spildevand", 0), e.get("has_affald", 0),
                     e.get("est_kunder"), cid))
                conn.commit()
                if changes:
                    log_audit(conn, uid, "update", "company", cid, e["name"], changes)
                    conn.commit()
                row = conn.execute(
                    "SELECT c.*, u.name AS account_manager_name FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = ?",
                    (cid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/contacts/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
                if not existing:
                    return self._error(404, "Kontakt ikke fundet")
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v
                conn.execute(
                    """UPDATE contacts SET first_name=?,last_name=?,title=?,email=?,phone=?,linkedin_url=?,
                       on_linkedin_list=?,notes=?,linkedin_connected_systemate=?,linkedin_connected_settl=?,
                       linkedin_last_checked=? WHERE id=?""",
                    (e["first_name"], e["last_name"], e["title"], e["email"], e["phone"],
                     e["linkedin_url"], e["on_linkedin_list"], e["notes"],
                     e.get("linkedin_connected_systemate", 0), e.get("linkedin_connected_settl", 0),
                     e.get("linkedin_last_checked"), cid))
                conn.commit()
                name = "{} {}".format(e["first_name"], e["last_name"])
                log_audit(conn, uid, "update", "contact", cid, name)
                conn.commit()
                row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/tasks/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
                if not existing:
                    return self._error(404, "Sag ikke fundet")
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v
                # Handle status change to done
                if body.get("status") == "done" and existing["status"] != "done":
                    e["completed_at"] = datetime.now().isoformat()
                elif body.get("status") != "done":
                    e["completed_at"] = None
                conn.execute(
                    """UPDATE tasks SET contact_id=?, assigned_to=?, category=?, title=?, description=?,
                       status=?, priority=?, due_date=?, completed_at=? WHERE id=?""",
                    (e.get("contact_id"), e.get("assigned_to"), e["category"], e["title"],
                     e.get("description"), e["status"], e["priority"], e.get("due_date"),
                     e.get("completed_at"), tid))
                conn.commit()
                log_audit(conn, uid, "update", "task", tid, e["title"],
                          {"status": e["status"]})
                conn.commit()
                row = conn.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id LEFT JOIN users u2 ON t.created_by = u2.id
                       WHERE t.id = ?""", (tid,)).fetchone()
                self._json_response(dict(row))

            # Rename tag
            elif path.startswith("/api/tags/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                conn.execute("UPDATE tags SET name=?, color=? WHERE id=?",
                             (body["name"], body.get("color", "#6b7280"), tid))
                conn.commit()
                row = conn.execute("SELECT * FROM tags WHERE id=?", (tid,)).fetchone()
                self._json_response(dict(row))

            # Notifications
            elif path.startswith("/api/notifications/") and path.endswith("/read"):
                nid = int(path.split("/")[-2])
                conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (nid,))
                conn.commit()
                self._json_response({"ok": True})

            elif path == "/api/notifications/read-all":
                conn.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
                conn.commit()
                self._json_response({"ok": True})

            # Edit task note
            elif path.startswith("/api/task-notes/") and path.count("/") == 3:
                nid = int(path.split("/")[-1])
                conn.execute("UPDATE task_notes SET content = ? WHERE id = ?",
                             (body.get("content", ""), nid))
                conn.commit()
                row = conn.execute("SELECT * FROM task_notes WHERE id = ?", (nid,)).fetchone()
                self._json_response(dict(row))

            # Edit tender note
            elif path.startswith("/api/tender-notes/") and path.count("/") == 3:
                nid = int(path.split("/")[-1])
                conn.execute("UPDATE tender_notes SET content = ? WHERE id = ?",
                             (body.get("content", ""), nid))
                conn.commit()
                row = conn.execute("SELECT * FROM tender_notes WHERE id = ?", (nid,)).fetchone()
                self._json_response(dict(row))

            # Score settings
            elif path == "/api/settings/score-thresholds":
                for rating, threshold in body.items():
                    if rating in ("A", "B", "C"):
                        conn.execute("UPDATE score_settings SET threshold = ? WHERE rating = ?",
                                     (int(threshold), rating))
                conn.commit()
                log_audit(conn, uid, "update", "settings", None, "score-thresholds", body)
                conn.commit()
                self._json_response({"ok": True})

            # Decay rules
            elif path == "/api/settings/decay-rules":
                rules = body.get("rules", [])
                # Delete all existing rules and re-insert
                conn.execute("DELETE FROM score_decay_rules")
                for rule in rules:
                    conn.execute(
                        """INSERT INTO score_decay_rules (inactivity_days, penalty_points, description, is_active)
                           VALUES (?,?,?,?)""",
                        (int(rule["inactivity_days"]), int(rule["penalty_points"]),
                         rule.get("description", ""), rule.get("is_active", True)))
                conn.commit()
                log_audit(conn, uid, "update", "settings", None, "decay-rules",
                          {"rules_count": len(rules)})
                conn.commit()
                self._json_response({"ok": True})

            # Tenders
            elif path.startswith("/api/tenders/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                existing = conn.execute("SELECT * FROM tenders WHERE id = ?", (tid,)).fetchone()
                if not existing:
                    return self._error(404, "Tilbud ikke fundet")
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v
                conn.execute(
                    """UPDATE tenders SET company_id=?, title=?, description=?, status=?,
                       deadline=?, contact_id=?, responsible_id=?, estimated_value=?,
                       portal_link=?, notes=? WHERE id=?""",
                    (e["company_id"], e["title"], e.get("description"), e["status"],
                     e.get("deadline"), e.get("contact_id"), e.get("responsible_id"),
                     e.get("estimated_value"), e.get("portal_link"), e.get("notes"), tid))
                conn.commit()
                log_audit(conn, uid, "update", "tender", tid, e["title"],
                          {"status": e["status"]})
                conn.commit()
                row = conn.execute(
                    """SELECT t.*, c.name AS company_name FROM tenders t
                       JOIN companies c ON t.company_id = c.id WHERE t.id = ?""", (tid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/tender-sections/") and path.count("/") == 3:
                sid = int(path.split("/")[-1])
                existing = conn.execute("SELECT * FROM tender_sections WHERE id = ?", (sid,)).fetchone()
                if not existing:
                    return self._error(404, "Sektion ikke fundet")
                old = dict(existing)
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v

                # Detect changes for audit trail
                user_name = None
                if uid:
                    ur = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                audit_entries = []
                # Status change
                if e["status"] != old["status"]:
                    audit_entries.append(("status_change", None, old["status"], e["status"], "status"))
                # Responsible change
                if str(e.get("responsible_id") or "") != str(old.get("responsible_id") or ""):
                    old_name = "-"
                    new_name = "-"
                    if old.get("responsible_id"):
                        r = conn.execute("SELECT name FROM users WHERE id=?", (old["responsible_id"],)).fetchone()
                        if r: old_name = r["name"]
                    if e.get("responsible_id"):
                        r = conn.execute("SELECT name FROM users WHERE id=?", (e["responsible_id"],)).fetchone()
                        if r: new_name = r["name"]
                    audit_entries.append(("field_change", None, old_name, new_name, "responsible"))
                # Reviewer change
                if str(e.get("reviewer_id") or "") != str(old.get("reviewer_id") or ""):
                    old_name = "-"
                    new_name = "-"
                    if old.get("reviewer_id"):
                        r = conn.execute("SELECT name FROM users WHERE id=?", (old["reviewer_id"],)).fetchone()
                        if r: old_name = r["name"]
                    if e.get("reviewer_id"):
                        r = conn.execute("SELECT name FROM users WHERE id=?", (e["reviewer_id"],)).fetchone()
                        if r: new_name = r["name"]
                    audit_entries.append(("field_change", None, old_name, new_name, "reviewer"))
                # Notes change
                if (e.get("notes") or "") != (old.get("notes") or ""):
                    audit_entries.append(("note", e.get("notes"), old.get("notes") or "", e.get("notes") or "", "notes"))

                conn.execute(
                    """UPDATE tender_sections SET title=?, description=?, content=?,
                       responsible_id=?, reviewer_id=?, status=?, deadline=?,
                       start_date=?, end_date=?,
                       sort_order=?, notes=? WHERE id=?""",
                    (e["title"], e.get("description"), e.get("content"),
                     e.get("responsible_id"), e.get("reviewer_id"), e["status"],
                     e.get("deadline"), e.get("start_date"), e.get("end_date"),
                     e["sort_order"], e.get("notes"), sid))

                # Write audit entries
                for note_type, content, old_val, new_val, field_name in audit_entries:
                    conn.execute(
                        """INSERT INTO tender_section_audit
                           (section_id, user_id, user_name, note_type, content, old_value, new_value, field_name)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (sid, uid, user_name, note_type, content, old_val, new_val, field_name))

                conn.commit()
                log_audit(conn, uid, "update", "tender_section", sid, e["title"],
                          json.dumps({"status": e["status"]}))
                conn.commit()
                row = conn.execute(
                    """SELECT ts.*, u1.name AS responsible_name, u2.name AS reviewer_name
                       FROM tender_sections ts
                       LEFT JOIN users u1 ON ts.responsible_id = u1.id
                       LEFT JOIN users u2 ON ts.reviewer_id = u2.id
                       WHERE ts.id = ?""", (sid,)).fetchone()
                self._json_response(dict(row))

            # PUT /api/tender-templates/{id}
            elif path.startswith("/api/tender-templates/") and path.count("/") == 3:
                tmpl_id = int(path.split("/")[-1])
                existing = conn.execute("SELECT * FROM tender_templates WHERE id = ?", (tmpl_id,)).fetchone()
                if not existing:
                    return self._error(404, "Skabelon ikke fundet")
                conn.execute(
                    "UPDATE tender_templates SET name=?, description=? WHERE id=?",
                    (body.get("name", existing["name"]), body.get("description", existing["description"]), tmpl_id))
                conn.commit()
                log_audit(conn, uid, "update", "tender_template", tmpl_id, body.get("name", existing["name"]))
                conn.commit()
                self._json_response({"id": tmpl_id, "name": body.get("name", existing["name"])})

            # PUT /api/tender-template-sections/{id}
            elif path.startswith("/api/tender-template-sections/") and path.count("/") == 3:
                sec_id = int(path.split("/")[-1])
                existing = conn.execute("SELECT * FROM tender_template_sections WHERE id = ?", (sec_id,)).fetchone()
                if not existing:
                    return self._error(404, "Skabelon-sektion ikke fundet")
                conn.execute(
                    """UPDATE tender_template_sections SET title=?, description=?,
                       default_days_before_deadline=?, sort_order=? WHERE id=?""",
                    (body.get("title", existing["title"]),
                     body.get("description", existing["description"]),
                     body.get("default_days_before_deadline", existing["default_days_before_deadline"]),
                     body.get("sort_order", existing["sort_order"]), sec_id))
                conn.commit()
                self._json_response({"id": sec_id})

            else:
                self._error(404, "Endpoint not found")
        finally:
            conn.close()

    # ─── API DELETE routes ───
    def _handle_api_delete(self, path):
        conn = get_db()
        uid = self._get_user_id()
        try:
            if path.startswith("/api/companies/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = conn.execute("SELECT name FROM companies WHERE id = ?", (cid,)).fetchone()
                conn.execute("DELETE FROM companies WHERE id = ?", (cid,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "company", cid, row["name"])
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/contacts/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = conn.execute("SELECT first_name, last_name FROM contacts WHERE id = ?", (cid,)).fetchone()
                conn.execute("DELETE FROM contacts WHERE id = ?", (cid,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "contact", cid, "{} {}".format(row["first_name"], row["last_name"]))
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/interactions/") and path.count("/") == 3:
                iid = int(path.split("/")[-1])
                row = conn.execute("SELECT subject, type FROM interactions WHERE id = ?", (iid,)).fetchone()
                conn.execute("DELETE FROM interactions WHERE id = ?", (iid,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "interaction", iid, row["subject"] or row["type"])
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/users/") and path.count("/") == 3:
                uid_del = int(path.split("/")[-1])
                row = conn.execute("SELECT name FROM users WHERE id = ?", (uid_del,)).fetchone()
                conn.execute("UPDATE users SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?", (uid_del,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "deactivate", "user", uid_del, row["name"])
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/tasks/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = conn.execute("SELECT title FROM tasks WHERE id = ?", (tid,)).fetchone()
                conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "task", tid, row["title"])
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/linkedin-activities/") and path.count("/") == 3:
                lid = int(path.split("/")[-1])
                conn.execute("DELETE FROM linkedin_activities WHERE id = ?", (lid,))
                conn.commit()
                self._no_content()

            elif path.startswith("/api/linkedin-engagements/") and path.count("/") == 3:
                lid = int(path.split("/")[-1])
                conn.execute("DELETE FROM linkedin_engagements WHERE id = ?", (lid,))
                conn.commit()
                self._no_content()

            # Tags
            elif path.startswith("/api/tags/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = conn.execute("SELECT name FROM tags WHERE id = ?", (tid,)).fetchone()
                conn.execute("DELETE FROM tags WHERE id = ?", (tid,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "tag", tid, row["name"])
                    conn.commit()
                self._no_content()

            # Remove tag from company: DELETE /api/companies/{id}/tags/{tag_id}
            elif path.startswith("/api/companies/") and "/tags/" in path and path.count("/") == 5:
                parts = path.split("/")
                cid = int(parts[3])
                tid = int(parts[5])
                conn.execute("DELETE FROM company_tags WHERE company_id = ? AND tag_id = ?", (cid, tid))
                conn.commit()
                self._no_content()

            # Remove tag from contact: DELETE /api/contacts/{id}/tags/{tag_id}
            elif path.startswith("/api/contacts/") and "/tags/" in path and path.count("/") == 5:
                parts = path.split("/")
                cid = int(parts[3])
                tid = int(parts[5])
                conn.execute("DELETE FROM contact_tags WHERE contact_id = ? AND tag_id = ?", (cid, tid))
                conn.commit()
                self._no_content()

            # Tenders
            elif path.startswith("/api/tenders/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = conn.execute("SELECT title FROM tenders WHERE id = ?", (tid,)).fetchone()
                conn.execute("DELETE FROM tenders WHERE id = ?", (tid,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "tender", tid, row["title"])
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/tender-sections/") and path.count("/") == 3:
                sid = int(path.split("/")[-1])
                row = conn.execute("SELECT title FROM tender_sections WHERE id = ?", (sid,)).fetchone()
                conn.execute("DELETE FROM tender_sections WHERE id = ?", (sid,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "tender_section", sid, row["title"])
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/tender-templates/") and path.count("/") == 3:
                tmpl_id = int(path.split("/")[-1])
                row = conn.execute("SELECT name FROM tender_templates WHERE id = ?", (tmpl_id,)).fetchone()
                conn.execute("DELETE FROM tender_templates WHERE id = ?", (tmpl_id,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "tender_template", tmpl_id, row["name"])
                    conn.commit()
                self._no_content()

            elif path.startswith("/api/tender-template-sections/") and path.count("/") == 3:
                sec_id = int(path.split("/")[-1])
                conn.execute("DELETE FROM tender_template_sections WHERE id = ?", (sec_id,))
                conn.commit()
                self._no_content()

            else:
                self._error(404, "Endpoint not found")
        finally:
            conn.close()

    def log_message(self, format, *args):
        pass  # Suppress access logs for cleaner output

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except BrokenPipeError:
            pass  # Browser closed connection early - harmless

if __name__ == "__main__":
    init_db()
    # Seed if empty
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
        conn.executescript("""
            INSERT INTO users (name, email, role) VALUES ('Jess Kristensen', 'jess@systemate.dk', 'admin');
            INSERT INTO users (name, email, role) VALUES ('Thomas Nielsen', 'thomas@systemate.dk', 'user');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Forsyning Helsingør','multiforsyning','Helsingør','T1','Kommunalt',1,0,1,1,1,1,'~61.000 borgere','Fuld 5-arts: Forsyning Elnet+Kronborg El + vand+varme+spildevand+affald. ~150 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Frederikshavn Forsyning','multiforsyning','Frederikshavn','T1','Kommunalt',1,0,1,1,1,1,'~62.000 borgere','Fuld 5-arts: Frh. Elhandel+Elnet + vand+varme+spildevand+affald. ~250 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('EWII (TREFOR)','multiforsyning','Kolding','T1','Selvejende',1,0,1,1,0,0,'~400.000 kunderelationer','El(net+handel), vand, fjernvarme, fiber. ~700 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Verdo','multiforsyning','Randers/Herning','T1','Andel',1,0,1,1,0,0,'~100.000 kunder','Fjernvarme(~75k), vand, el(Kongerslev elnet+elhandel).');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Bornholms Energi & Forsyning','multiforsyning','Rønne','T1','Forbrugerejet',1,0,1,1,1,0,'~28.000 borgere','El(handel), vand, varme, spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energi Viborg','multiforsyning','Viborg','T1','Kommunalt',1,0,1,0,1,0,'~45.000 borgere','El(net Kimbrer), vand, spildevand, gadelys. ~105 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Læsø Forsyning','multiforsyning','Læsø','T1','Kommunalt',1,0,1,1,1,1,'~1.800 husstande','Fuld multi: elnet+vand+varme+spildevand+renovation.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Struer Energi','multiforsyning','Struer','T1','Kommunalt',1,0,1,1,1,0,'~11.000 borgere','Multi: el(net), fjernvarme, vand, spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Tønder Forsyning','multiforsyning','Tønder','T1','Kommunalt',1,0,1,1,1,1,'~40.000 borgere','Multi: el(handel), vand, fjernvarme, spildevand, affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energi Ikast','multiforsyning','Ikast','T1','Andel',1,0,1,1,0,0,'~8.000-10.000 kunder','El(Ikast El Net+Samstrøm), varme, fiber. Afregner vand+spildevand. ~40 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('GEV (Grindsted)','multiforsyning','Grindsted','T1','Andel',1,0,1,1,0,0,'~7.000 hjem','Multi: el(GEV Elnet+Samstrøm), vand, varme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vildbjerg Tekniske Værker','multiforsyning','Vildbjerg','T1','Andel',1,0,1,1,0,0,'~3.000-4.000 kunder','Vildbjerg Elværk+Vandværk+Varmeværk. Samstrøm.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energi Hurup','multiforsyning','Hurup Thy','T1','Andel',1,0,1,1,0,0,'~2.600 vandkunder','Hurup Elværk+Fjernvarme+Vandværk. Samstrøm.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Sunds Forsyning','multiforsyning','Sunds','T1','Andel',1,0,1,1,0,0,'~2.500-3.000','Elnet+Samstrøm, vandværk, varme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Videbæk Energiforsyning','multiforsyning','Videbæk','T1','Andel',1,0,1,1,0,0,'~3.000-4.000','Elnet+Samstrøm, vandværk, fjernvarme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vest Forsyning (Holstebro)','multiforsyning','Holstebro','T1','Kommunalt',1,0,1,1,1,1,'~58.000 borgere','Multi: el(handel), vand, varme, spildevand, affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('SK Forsyning (Slagelse)','multiforsyning','Slagelse','T1','Kommunalt',1,0,1,1,1,0,'~80.000 borgere','Multi: el(SK Energi=elhandel), vand, varme, spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vesthimmerlands Elforsyning','multiforsyning','Aars','T1','Andel',1,0,0,1,0,0,'~15.000 elkunder','Elnet (Aars-Hornum Net)+elhandel. Tilknyttet lokal varme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Andel (Andel Energi+Cerius+Radius)','multiforsyning','Sjælland/hele DK','T2','Andel',1,1,0,0,0,0,'~1.200.000 elkunder
Elnet:1.400.000','DK''s største el. Elhandel+gas+elnet+fiber.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Norlys (N1, Stofa, Boxer)','el','Jylland/hele DK','T2','Andel',1,0,0,0,0,0,'~1.700.000 kunderelationer','El(net N1+handel), tele/fiber, TV. ~4.500 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('NRGi (Konstant/Dinel)','el','Østjylland/hele DK','T2','Andel',1,0,0,0,0,0,'~140.000 elkunder','Elhandel, elnet, fiber, energirådgivning. ~1.600 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energi Fyn','multiforsyning','Fyn/hele DK','T2','Andel',1,1,0,0,0,0,'~220.000 elkunder','Elnet+elhandel, naturgas, fiber. ~390 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Ørsted','el','Hele DK/globalt','T2','Børsnoteret',1,0,0,0,0,0,'Primært B2B/VE-produktion','VE-gigant. Vindmøller, solceller. Tidl. DONG. Ikke retail-el i stor stil.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('AURA Energi','el','Østjylland','T2','Andel',1,0,0,0,0,0,'~100.000+ kunder','Elhandel, elnet, fiber.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('SEF (Sydfyns Elforsyning)','multiforsyning','Sydfyn/hele DK','T2','Selvejende fond',1,1,0,0,0,0,'Sydfyn + landsdk.','El(FLOW Elnet+SEF Energi), naturgas, fiber, varmepumper. ~160 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Thy-Mors Energi','el','Thy/Mors','T2','Andel',1,0,0,0,0,0,'~44.000 andelshavere','Elnet(Elværk)+elhandel, fiber.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('OK','el','Hele DK','T2','Andel',1,0,0,0,0,0,'Stor kundebasis','Andelsselskab. Brændstof+el+ladning.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Nord Energi','el','Nordjylland','T2','Andel',1,0,0,0,0,0,'Nordjylland','Elnetselskab+elhandel.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Jysk Energi','el','Jylland','T2','Privat',1,0,0,0,0,0,'Voksende','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vindstød','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Voksende','Dansk vindenergi direkte.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Barry','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Voksende','App-baseret elselskab. Timepriser.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('True Energy','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Voksende','Smart-el-app med forbrugsstyring.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('b.energy','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('NettoPower','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Voksende','Lavpris-el, grøn profil.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Modstrøm','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Voksende','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Velkommen','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Go Energi','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Cheap Energy','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Edison','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Elektron','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Forskel','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('FRI Energy','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('GNP Energy','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab (norsk oprindelse).');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Grøn El-Forsyning','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('EnergiPlus','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Kärnfull Energi','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Svensk atomkraft-elselskab i DK.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Natur-Energi','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Nordisk Energy','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Norsk Elkraft Danmark','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Norsk elhandelsselskab i DK.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Ø-strøm','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Power4U','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Preasy','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Strømlinet','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('strømtid','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vets Energi','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Samstrøm','el','Jylland','T2','Fællesejet',1,0,0,0,0,0,'Partner for 8 værker','Fælles elhandelsselskab for GEV,Ikast,Sunds,Hjerting,Tarm,Videbæk,VTV,Hurup.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('SK Energi (SK Forsyning)','el','Slagelse','T2','Kommunalt',1,0,0,0,0,0,'Slagelse-omr.','Elhandel. Del af SK Forsyning-koncern (som er Tier 1).');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('nef Fonden (Nordvestjysk)','el','Nordvestjylland','T2','Fond',1,0,0,0,0,0,'Nordvestjylland','Elhandel/energi. Fond.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('E.ON Danmark','el','Hele DK','T2','Privat/koncern',1,0,0,0,0,0,'B2B','Tysk energikoncern. El til erhverv i DK.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energidrift','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energiselskabet Elg','el','Hele DK','T2','Privat',1,0,0,0,0,0,'Mindre','Elhandelsselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energi Danmark / Mind Energy','multiforsyning','Hele DK/Norden','T2','Privat/koncern',1,1,0,0,0,0,'Primært B2B','Energitrading. Del af Andel-koncern.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Danske Commodities','multiforsyning','Hele DK/Europa','T2','Privat/koncern',1,1,0,0,0,0,'Primært B2B','Energitrading. Ejet af Equinor.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('DCC Energi','el','Hele DK','T2','Privat',1,0,0,0,0,0,'B2B','Energihandel/trading.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Energy Nordic','el','Hele DK','T2','Privat',1,0,0,0,0,0,'B2B','Energihandel/erhverv.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Cerius (Andel)','el','Sjælland','T2','Andel',1,0,0,0,0,0,'~590.000 netkunder','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Radius Elnet (Andel)','el','Storkøbenhavn','T2','Andel',1,0,0,0,0,0,'~800.000 netkunder','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('N1 (Norlys)','el','Jylland','T2','Andel',1,0,0,0,0,0,'~600.000+ netkunder','Jyllands største net.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('TREFOR El-Net (EWII)','el','Trekantomr.','T2','Selvejende',1,0,0,0,0,0,'Trekantomr.','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('TREFOR El-Net Øst (EWII)','el','Bornholm','T2','Selvejende',1,0,0,0,0,0,'Bornholm','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Konstant Net (NRGi)','el','Aarhus','T2','Andel',1,0,0,0,0,0,'Aarhus','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Dinel (NRGi)','el','Djursland','T2','Andel',1,0,0,0,0,0,'Djursland','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('NOE Net','el','Midtjylland','T2','Andel',1,0,0,0,0,0,'Midtjylland','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('RAH Net','el','Ringkøbing','T2','Andel',1,0,0,0,0,0,'Ringk.-Skjern','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('FLOW Elnet (SEF)','el','Sydfyn','T2','Selvejende',1,0,0,0,0,0,'Sydfyn/Langeland','Netselskab. Del af SEF.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vores Elnet','el','Fredericia/Vejle','T2','Andel',1,0,0,0,0,0,'Fred./Vejle','Netselskab.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('+ ca. 25 øvrige små netselskaber','el','Hele DK','T2','Diverse',1,0,0,0,0,0,'Varierende','Ravdex,Veksel,Elinord,Elektrus,NKE,Zeanet,L-Net,Nakskov,Hammel,Midtfyns,Aal m.fl.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('HOFOR','multiforsyning','København (8 komm.)','T3','Kommunalt',0,1,1,1,1,0,'~1.000.000 vandkunder','DK''s største vand. Vand 8 komm., varme+gas+køling KBH. ~1.700 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Aalborg Forsyning','multiforsyning','Aalborg','T3','Kommunalt',0,1,1,1,1,0,'~100.000+ husstande','Multi: varme,gas,køling,vand,spildevand. ~500 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Frederiksberg Forsyning','multiforsyning','Frederiksberg','T3','Kommunalt',0,1,1,1,1,0,'~55.000 borgere','Gas(bygas),vand,fjernvarme,fjernkøling,spildevand,VE. IKKE el.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Silkeborg Forsyning','multiforsyning','Silkeborg','T3','Kommunalt',0,0,1,1,1,1,'~96.000 borgere','Vand,fjernvarme,spildevand,affald. ~140 ans.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('FORS A/S','multiforsyning','Holbæk/Lejre/Roskilde','T3','Kommunalt',0,0,1,1,1,1,'~100.000+ borgere','Multi 3 kommuner.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Din Forsyning','multiforsyning','Esbjerg/Varde','T3','Kommunalt',0,0,1,1,1,1,'~120.000 borgere','Multi: vand,varme,spildevand,affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Halsnæs Forsyning','multiforsyning','Frederiksværk','T3','Kommunalt',0,0,1,1,1,1,'~31.000 borgere','Fjernvarme,vand,spildevand,affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Provas','multiforsyning','Haderslev','T3','Kommunalt',0,0,1,1,1,1,'~55.000 borgere','Vand,varme,spildevand,affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Kalundborg Forsyning','multiforsyning','Kalundborg','T3','Kommunalt',0,0,1,1,1,1,'~49.000 borgere','Vand,varme,spildevand,affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('REFA','multiforsyning','Lolland-Falster','T3','Kommunalt',0,0,0,1,0,1,'~100.000 borgere','Kraftvarme(affald+halm),genbrugspladser.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Klar Forsyning','multiforsyning','Slagelse','T3','Kommunalt',0,0,1,1,1,0,'~80.000 borgere','Vand,fjernvarme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Sønderborg Forsyning','multiforsyning','Sønderborg','T3','Kommunalt',0,0,1,1,1,0,'~75.000 borgere','Vand,fjernvarme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Næstved Forsyning','multiforsyning','Næstved','T3','Kommunalt',0,0,1,1,1,0,'~83.000 borgere','Vand,fjernvarme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Skanderborg Forsyning','multiforsyning','Skanderborg','T3','Kommunalt',0,0,1,1,1,0,'~60.000 borgere','Vand,varme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Ringsted Forsyning','multiforsyning','Ringsted','T3','Kommunalt',0,0,1,1,1,0,'~35.000 borgere','Vand,fjernvarme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Sorø Forsyning','multiforsyning','Sorø','T3','Kommunalt',0,0,1,1,1,0,'~30.000 borgere','Vand,fjernvarme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Assens Forsyning','multiforsyning','Assens','T3','Kommunalt',0,0,1,1,1,0,'~41.000 borgere','Vand,fjernvarme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Kerteminde Forsyning','multiforsyning','Kerteminde','T3','Kommunalt',0,0,1,1,1,0,'~24.000 borgere','Vand,varme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Middelfart Forsyning','multiforsyning','Middelfart','T3','Kommunalt',0,0,1,1,1,0,'~38.000 borgere','Varme,vand,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Skive Vand/Fjernvarme','multiforsyning','Skive','T3','Kommunalt',0,0,1,1,1,0,'~47.000 borgere','Vand,fjernvarme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Horsens Vand/Samn Forsyning','multiforsyning','Horsens/Odder','T3','Kommunalt',0,0,1,0,1,0,'~90.000 borgere','Vand og spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Kolding Forsyning (BlueKolding)','multiforsyning','Kolding','T3','Kommunalt',0,0,1,0,1,0,'~92.000 borgere','Vand og spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Herning Vand','multiforsyning','Herning','T3','Kommunalt',0,0,1,0,1,0,'~50.000 borgere','Vand+spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Hjørring Vandselskab','multiforsyning','Hjørring','T3','Kommunalt',0,0,1,0,1,0,'~66.000 borgere','Vand+spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Favrskov Forsyning','multiforsyning','Hadsten','T3','Kommunalt',0,0,1,0,1,0,'~48.000 borgere','Vand og spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vejle Spildevand/Varme','multiforsyning','Vejle','T3','Kommunalt',0,0,0,1,1,0,'~55.000 borgere','Fjernvarme+spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Roskilde Forsyning','multiforsyning','Roskilde','T3','Kommunalt',0,0,1,1,1,0,'~88.000 borgere','Vand,varme,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Billund Vand','multiforsyning','Billund','T3','Kommunalt',0,0,1,0,1,0,'~26.000 borgere','Vand,spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Novafos','multiforsyning','Nordsjælland(9 komm.)','T4','Kommunalt',0,0,1,0,1,0,'~300.000+ borgere','DK''s 2. største vand/spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('VandCenter Syd','multiforsyning','Odense/Nordfyn','T4','Kommunalt',0,0,1,0,1,0,'~220.000 borgere','Drikkevand og spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Aarhus Vand','multiforsyning','Aarhus','T4','Kommunalt',0,0,1,0,1,0,'~350.000 borgere','Drikkevand og spildevand.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('BIOFOS','spildevand','Storkøbenhavn','T4','Kommunalt',0,0,0,0,1,0,'~1.200.000 borgere','DK''s største spildevandsrensning.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Kredsløb (Aarhus)','multiforsyning','Aarhus','T4','Kommunalt',0,0,0,1,0,1,'~350.000 borgere','Fjernvarme+affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Fjernvarme Fyn','varme','Odense','T4','Kommunalt',0,0,0,1,0,0,'~85.000 kunder','DK''s 3. største fjernvarme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Vestforbrænding','multiforsyning','Vestegnen','T4','Kommunalt',0,0,0,1,0,1,'~900.000 borgere','DK''s største affald.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('ARC','multiforsyning','København','T4','Kommunalt',0,0,0,1,0,1,'~600.000 borgere','Affaldsforbrænding+varme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('ARGO','multiforsyning','Roskilde','T4','Kommunalt',0,0,0,1,0,1,'~470.000 borgere','Affald,genbrug,fjernvarme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Evida','gas','Hele DK','T4','Statsligt',0,1,0,0,0,0,'~400.000 gasmålere','National gasdistributør.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('CTR','varme','Storkøbenhavn','T4','Kommunalt',0,0,0,1,0,0,'Transmission','Fjernvarmetransmission.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('VEKS','varme','Vestegnen','T4','Kommunalt',0,0,0,1,0,0,'13 kommuner','Fjernvarmetransmission.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Nordværk','multiforsyning','Aalborg','T4','Kommunalt',0,0,0,1,0,1,'Nordjylland','Affaldsforbrænding+fjernvarme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('AVV','multiforsyning','Hjørring','T4','Kommunalt',0,0,0,1,0,1,'~75.000 borgere','Affaldsbehandling+fjernvarme.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('~350+ fjernvarmeværker','varme','Hele DK','T4','Primært andel',0,0,0,1,0,0,'~1.800.000 husstande','Ca. 400 fjernvarmeselskaber i DK.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('~2.600 vandværker','vand','Hele DK','T4','Primært andel',0,0,1,0,0,0,'Varierende','Mange forbrugerejede.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Clever','e-mobilitet','Hele DK','EM','Privat (Andel)',1,0,0,0,0,0,'~200.000+ brugere
~3.000 ladepunkter','DK''s største ladeoperatør. Abonnements-model. Opladning af elbiler.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Looad','e-mobilitet','Hele DK','EM','Privat',1,0,0,0,0,0,'Voksende','Ladeoperatør. Ladebokse+abonnement.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Circle K / Ladning','e-mobilitet','Hele DK','EM','Privat',1,0,0,0,0,0,'Landsdækkende','Tankstationer + lynladere til elbiler.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Spirii','e-mobilitet','Hele DK','EM','Privat',1,0,0,0,0,0,'Platform','Ladeplatform/software til CPO''er.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('E.ON Drive','e-mobilitet','Hele DK','EM','Privat/koncern',1,0,0,0,0,0,'Voksende','Ladeinfrastruktur.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('EWII Lading','e-mobilitet','Hele DK','EM','Selvejende',1,0,0,0,0,0,'~4.000 ladepunkter','EWIIs ladenetværk.');
            INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder,notes) VALUES ('Tesla Supercharger','e-mobilitet','Hele DK','EM','Privat',1,0,0,0,0,0,'DK-stationer','Lukket→åbent netværk.');
        """)
        # Lookup helper for company IDs by name
        def cid(name):
            r = conn.execute("SELECT id FROM companies WHERE name LIKE ?", (name + '%',)).fetchone()
            return r[0] if r else None

        seed_contacts = [
            ("EWII", "Lars", "Hansen", "CEO", "lars@ewii.dk", 1),
            ("EWII", "Mette", "Andersen", "CFO", "mette@ewii.dk", 0),
            ("EWII", "Peter", "Skov", "Afregningschef", "peter@ewii.dk", 1),
            ("Verdo", "Camilla", "Thomsen", "CEO", "camilla@verdo.dk", 1),
            ("Verdo", "Michael", "Nielsen", "Kundechef", "michael@verdo.dk", 0),
            ("Forsyning Helsingør", "Anne", "Mortensen", "CEO", "anne@LFH.dk", 0),
            ("Forsyning Helsingør", "Henrik", "Olsen", "COO", "henrik@LFH.dk", 1),
            ("Frederikshavn", "Soeren", "Frederiksen", "CEO", "soren@LFF.dk", 0),
            ("Bornholms", "Birgitte", "Jensen", "CCO", "birgitte@bef.dk", 0),
            ("Energi Viborg", "Kasper", "Holm", "CEO", "kasper@LEvib.dk", 0),
            ("Norlys", "Thomas", "Larsen", "VP Sales", "thomas@norlys.dk", 1),
            ("Norlys", "Kirsten", "Berg", "CTO", "kirsten@norlys.dk", 0),
            ("Andel Energi", "Jens", "Petersen", "CEO", "jens@andel.dk", 1),
            ("Ørsted", "Maria", "Christensen", "Key Account Mgr", "maria@orsted.dk", 0),
            ("Radius", "Anders", "Johansen", "Driftschef", "anders@radius.dk", 1),
        ]
        for comp, fn, ln, title, em, li in seed_contacts:
            company_id = cid(comp)
            if company_id:
                conn.execute("INSERT INTO contacts (company_id,first_name,last_name,title,email,on_linkedin_list) VALUES (?,?,?,?,?,?)",
                             (company_id, fn, ln, title, em, li))

        # Interactions referencing contact IDs (first 13 contacts)
        interactions = [
            (1,1,"meeting","2026-03-01","Strategimoede"),(1,1,"email","2026-03-03","Opfoelgning"),
            (2,1,"phone","2026-02-25","Budget-diskussion"),(3,2,"linkedin","2026-02-20","LinkedIn besked"),
            (3,2,"email","2026-02-28","Afregningssystem demo"),(4,1,"meeting","2026-02-15","Praesentation"),
            (5,2,"email","2026-02-18","Teknisk dok"),(4,1,"phone","2026-02-20","Opfoelgning"),
            (6,1,"email","2025-12-10","Introduktion"),(6,1,"phone","2025-12-15","Kort samtale"),
            (7,2,"meeting","2026-02-01","Foerste moede"),(7,2,"email","2026-02-05","Opfoelgning"),
            (11,1,"email","2026-01-15","Indledende kontakt"),(13,1,"meeting","2026-03-05","Strategimoede"),
        ]
        for cid_i, uid_seed, t, d, s in interactions:
            conn.execute("INSERT INTO interactions (contact_id,user_id,type,date,subject) VALUES (?,?,?,?,?)", (cid_i,uid_seed,t,d,s))
        # Tender template + sample tender
        conn.execute("INSERT INTO tender_templates (name, description, is_default) VALUES ('Standard IT-udbud', 'Standardskabelon til IT-udbud for forsyningsselskaber', 1)")
        template_sections = [
            (1, 'Leverandoerbeskrivelse', 'Beskrivelse af virksomheden, organisation, omsaetning og erfaring', 14, 0),
            (1, 'Loesningsbeskrivelse', 'Teknisk og funktionel beskrivelse af den tilbudte loesning', 10, 1),
            (1, 'Tidsplan', 'Implementeringsplan med milepale og leverancer', 7, 2),
            (1, 'Prissaetning', 'Prismodel, licenser, drift og implementeringsomkostninger', 5, 3),
            (1, 'Sikkerhed & GDPR', 'IT-sikkerhed, databeskyttelse, GDPR-compliance og certificeringer', 10, 4),
            (1, 'Support & Drift', 'SLA, supportmodel, driftsaftale og beredskab', 7, 5),
            (1, 'Referencer', 'Relevante kundecases og referenceprojekter', 14, 6),
            (1, 'Kvalitetssikring', 'QA-processer, testmetodik og kvalitetsstyring', 7, 7),
        ]
        for tid, title, desc, days, sort in template_sections:
            conn.execute("INSERT INTO tender_template_sections (template_id, title, description, default_days_before_deadline, sort_order) VALUES (?,?,?,?,?)",
                         (tid, title, desc, days, sort))

        # Sample tender
        conn.execute("""INSERT INTO tenders (company_id, template_id, title, description, status, deadline, responsible_id, created_by, estimated_value)
            VALUES (1, 1, 'Energi Fyn - Afregningssystem 2026', 'Udbud paa nyt afregningssystem til Energi Fyn', 'in_progress', '2026-06-01', 1, 1, '2.5M DKK')""")
        sample_sections = [
            (1, 'Leverandoerbeskrivelse', 'Beskrivelse af Systemate', 1, 2, 'approved', '2026-04-15', 0),
            (1, 'Loesningsbeskrivelse', 'Teknisk loesningsbeskrivelse', 1, None, 'in_progress', '2026-05-01', 1),
            (1, 'Tidsplan', 'Implementeringsplan', 2, 1, 'not_started', '2026-05-10', 2),
            (1, 'Prissaetning', 'Prismodel og budget', 1, None, 'not_started', '2026-05-15', 3),
            (1, 'Sikkerhed & GDPR', 'Sikkerhed og compliance', 2, 1, 'in_review', '2026-05-01', 4),
            (1, 'Support & Drift', 'Driftsaftale', 1, None, 'not_started', '2026-05-10', 5),
            (1, 'Referencer', 'Kundecases', 2, 1, 'in_progress', '2026-04-20', 6),
            (1, 'Kvalitetssikring', 'QA processer', 1, None, 'not_started', '2026-05-15', 7),
        ]
        for tid, title, desc, resp, rev, status, deadline, sort in sample_sections:
            conn.execute("""INSERT INTO tender_sections (tender_id, title, description, responsible_id, reviewer_id, status, deadline, sort_order)
                VALUES (?,?,?,?,?,?,?,?)""", (tid, title, desc, resp, rev, status, deadline, sort))

        # Score history (for delta indicators) - simulate scores from 7 days ago
        conn.execute("INSERT INTO score_history (company_id, score, level, recorded_at) VALUES (1, 45, 'svag', date('now', '-7 days'))")
        conn.execute("INSERT INTO score_history (company_id, score, level, recorded_at) VALUES (2, 10, 'kold', date('now', '-7 days'))")
        conn.execute("INSERT INTO score_history (company_id, score, level, recorded_at) VALUES (3, 35, 'svag', date('now', '-7 days'))")
        conn.execute("INSERT INTO score_history (company_id, score, level, recorded_at) VALUES (4, 55, 'god', date('now', '-7 days'))")

        conn.commit()
        print("Database seeded with demo data.")
    conn.close()

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    port = int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer(("0.0.0.0", port), CRMHandler)
    print("Systemate Customer Care Center running on http://0.0.0.0:{}".format(port))
    server.serve_forever()
