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
            sector TEXT CHECK(sector IN ('el', 'vand', 'varme', 'multiforsyning')),
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
            type TEXT NOT NULL CHECK(type IN ('email', 'phone', 'meeting', 'linkedin')),
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
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','in_progress','submitted','won','lost')),
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
    ]
    for m in migrations:
        try:
            conn.execute(m)
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Migration: update tender_section_audit CHECK constraint to allow 'comment' type
    try:
        conn.execute("INSERT INTO tender_section_audit (section_id, note_type, content) VALUES (0, 'comment', '__migration_test__')")
        conn.execute("DELETE FROM tender_section_audit WHERE content = '__migration_test__'")
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

# ─── Score ───
INTERACTION_POINTS = {"meeting": 20, "phone": 10, "email": 5, "linkedin": 3}
DECAY_BRACKETS = [(14, 1.0), (30, 0.85), (60, 0.65), (90, 0.45), (180, 0.25)]
DIVERSITY_SCORES = {1: 5, 2: 10, 3: 15, 4: 20}

def get_decay_factor(days):
    if days is None:
        return 0.10
    for max_days, factor in DECAY_BRACKETS:
        if days <= max_days:
            return factor
    return 0.10

def calculate_company_score(company_id):
    conn = get_db()
    company = conn.execute("SELECT id, name, sector, rating, account_manager_id FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        conn.close()
        return None
    company = dict(company)

    # Get account manager name
    am_name = None
    if company.get("account_manager_id"):
        am_row = conn.execute("SELECT name FROM users WHERE id = ?", (company["account_manager_id"],)).fetchone()
        if am_row:
            am_name = am_row["name"]

    contacts = conn.execute("SELECT id FROM contacts WHERE company_id = ?", (company_id,)).fetchall()
    total_contacts = len(contacts)
    contact_ids = [c["id"] for c in contacts]

    if not contact_ids:
        conn.close()
        return {"company_id": company["id"], "company_name": company["name"], "sector": company["sector"],
                "rating": company.get("rating", "C"), "account_manager_name": am_name,
                "score": 0, "interaction_points": 0, "coverage_points": 0, "diversity_points": 0,
                "decay_factor": 0.10, "days_since_last": None, "total_contacts": 0, "contacted_count": 0,
                "total_interactions": 0, "channel_types": [], "level": "kold"}

    placeholders = ",".join("?" * len(contact_ids))
    interactions = [dict(r) for r in conn.execute(
        "SELECT type, date, contact_id FROM interactions WHERE contact_id IN ({}) ORDER BY date DESC".format(placeholders),
        contact_ids).fetchall()]
    conn.close()

    total_interactions = len(interactions)
    raw_points = sum(INTERACTION_POINTS.get(i["type"], 0) for i in interactions)
    interaction_points = min(raw_points, 60)

    contacted_ids = set(i["contact_id"] for i in interactions)
    contacted_count = len(contacted_ids)
    coverage_points = round((contacted_count / total_contacts * 20) if total_contacts > 0 else 0, 1)

    channel_types = list(set(i["type"] for i in interactions))
    diversity_points = DIVERSITY_SCORES.get(len(channel_types), 20) if channel_types else 0

    days_since_last = None
    if interactions:
        try:
            last_date = date.fromisoformat(interactions[0]["date"])
            days_since_last = (date.today() - last_date).days
        except (ValueError, TypeError):
            pass

    decay_factor = get_decay_factor(days_since_last)
    score = round((interaction_points + coverage_points + diversity_points) * decay_factor, 1)
    level = "staerk" if score >= 80 else "god" if score >= 50 else "svag" if score >= 20 else "kold"

    return {"company_id": company["id"], "company_name": company["name"], "sector": company["sector"],
            "rating": company.get("rating", "C"), "account_manager_name": am_name,
            "score": score, "interaction_points": interaction_points, "coverage_points": coverage_points,
            "diversity_points": diversity_points, "decay_factor": decay_factor, "days_since_last": days_since_last,
            "total_contacts": total_contacts, "contacted_count": contacted_count,
            "total_interactions": total_interactions, "channel_types": channel_types, "level": level}

def calculate_all_scores(conn):
    """Batch-calculate scores for ALL companies using a single DB connection."""
    # Load configurable decay penalty rules
    decay_penalty_rules = [dict(r) for r in conn.execute(
        "SELECT * FROM score_decay_rules WHERE is_active = 1 ORDER BY inactivity_days").fetchall()]

    companies = [dict(r) for r in conn.execute(
        """SELECT c.*, u.name AS account_manager_name
           FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id
           ORDER BY c.name""").fetchall()]
    if not companies:
        return []

    # 1) Contact counts per company
    contact_counts = {}
    for r in conn.execute("SELECT company_id, COUNT(*) AS cnt FROM contacts GROUP BY company_id").fetchall():
        contact_counts[r["company_id"]] = r["cnt"]

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

    # 3) Calculate score per company in Python
    results = []
    for company in companies:
        cid = company["id"]
        total_contacts = contact_counts.get(cid, 0)
        interactions = interactions_by_company.get(cid, [])

        if total_contacts == 0 or not interactions:
            results.append({
                "company_id": cid, "company_name": company["name"], "sector": company["sector"],
                "rating": company.get("rating", "C"), "account_manager_name": company.get("account_manager_name"),
                "score": 0, "interaction_points": 0, "coverage_points": 0, "diversity_points": 0,
                "decay_factor": 0.10, "days_since_last": None, "total_contacts": total_contacts,
                "contacted_count": 0, "total_interactions": 0, "channel_types": [], "level": "kold",
                "tags": tags_by_company.get(cid, [])})
            continue

        total_interactions = len(interactions)
        raw_points = sum(INTERACTION_POINTS.get(i["type"], 0) for i in interactions)
        interaction_points = min(raw_points, 60)

        contacted_ids = set(i["contact_id"] for i in interactions)
        contacted_count = len(contacted_ids)
        coverage_points = round((contacted_count / total_contacts * 20) if total_contacts > 0 else 0, 1)

        channel_types = list(set(i["type"] for i in interactions))
        diversity_points = DIVERSITY_SCORES.get(len(channel_types), 20) if channel_types else 0

        days_since_last = None
        if interactions:
            try:
                last_date = date.fromisoformat(interactions[0]["date"])
                days_since_last = (date.today() - last_date).days
            except (ValueError, TypeError):
                pass

        decay_factor = get_decay_factor(days_since_last)
        score = round((interaction_points + coverage_points + diversity_points) * decay_factor, 1)

        # Apply configurable penalty points for inactivity
        penalty = 0
        if days_since_last is not None:
            for rule in decay_penalty_rules:
                if days_since_last >= rule["inactivity_days"]:
                    penalty = rule["penalty_points"]  # Use highest matching penalty
        score = max(0, round(score - penalty, 1))

        level = "staerk" if score >= 80 else "god" if score >= 50 else "svag" if score >= 20 else "kold"

        results.append({
            "company_id": cid, "company_name": company["name"], "sector": company["sector"],
            "rating": company.get("rating", "C"), "account_manager_name": company.get("account_manager_name"),
            "score": score, "interaction_points": interaction_points, "coverage_points": coverage_points,
            "diversity_points": diversity_points, "decay_factor": decay_factor, "days_since_last": days_since_last,
            "total_contacts": total_contacts, "contacted_count": contacted_count,
            "total_interactions": total_interactions, "channel_types": channel_types, "level": level,
            "penalty": penalty, "tags": tags_by_company.get(cid, [])})

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
                if "rating" in params:
                    q += " AND c.rating = ?"; p.append(params["rating"][0])
                if "account_manager_id" in params:
                    q += " AND c.account_manager_id = ?"; p.append(int(params["account_manager_id"][0]))
                if "search" in params:
                    q += " AND c.name LIKE ?"; p.append("%{}%".format(params["search"][0]))
                q += " ORDER BY c.name"
                self._json_response([dict(r) for r in conn.execute(q, p).fetchall()])

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
                       FROM interactions i JOIN contacts ct ON i.contact_id = ct.id
                       LEFT JOIN users u ON i.user_id = u.id
                       WHERE ct.company_id = ? ORDER BY i.date DESC""", (cid,)).fetchall()]
                emails = [dict(r) for r in conn.execute(
                    """SELECT e.* FROM emails e LEFT JOIN interactions i ON e.interaction_id = i.id
                       LEFT JOIN contacts ct ON i.contact_id = ct.id WHERE ct.company_id = ? ORDER BY e.date_sent DESC""", (cid,)).fetchall()]
                users = [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY name").fetchall()]
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
                self._json_response({
                    "company": dict(company), "contacts": contacts, "score": score,
                    "interactions": interactions, "emails": emails, "users": users,
                    "tasks": tasks, "audit_log": audit,
                    "linkedin_activities": li_activities, "linkedin_engagements": li_engagements,
                    "company_tags": company_tags, "all_tags": all_tags
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
                       FROM interactions i JOIN contacts c ON i.contact_id = c.id
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
                self._json_response([dict(r) for r in conn.execute("SELECT * FROM users ORDER BY name").fetchall()])

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

                # Recent activities (last 14 days) - unified feed from multiple tables
                recent_activities = [dict(r) for r in conn.execute("""
                    SELECT 'interaction' AS source, i.id, i.date AS activity_date, i.type AS sub_type,
                           i.subject, co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM interactions i
                    JOIN contacts ct ON i.contact_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN users u ON i.user_id = u.id
                    WHERE i.date >= date('now', '-14 days')

                    UNION ALL

                    SELECT 'task' AS source, t.id, COALESCE(t.completed_at, t.created_at) AS activity_date,
                           t.category AS sub_type, t.title AS subject,
                           co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM tasks t
                    JOIN companies co ON t.company_id = co.id
                    LEFT JOIN contacts ct ON t.contact_id = ct.id
                    LEFT JOIN users u ON t.assigned_to = u.id
                    WHERE t.created_at >= date('now', '-14 days') OR t.completed_at >= date('now', '-14 days')

                    UNION ALL

                    SELECT 'linkedin_activity' AS source, la.id, la.activity_date, la.activity_type AS sub_type,
                           la.content_summary AS subject, co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM linkedin_activities la
                    JOIN contacts ct ON la.contact_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN users u ON la.observed_by = u.id
                    WHERE la.activity_date >= date('now', '-14 days')

                    UNION ALL

                    SELECT 'linkedin_engagement' AS source, le.id, le.observed_date AS activity_date,
                           le.engagement_type AS sub_type, le.notes AS subject,
                           co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM linkedin_engagements le
                    JOIN contacts ct ON le.contact_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN users u ON le.observed_by = u.id
                    WHERE le.observed_date >= date('now', '-14 days')

                    ORDER BY activity_date DESC
                    LIMIT 50
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

                self._json_response({"scores": scores, "stats": stats, "all_tags": all_tags, "recent_activities": recent_activities})

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
                users = [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY name").fetchall()]
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
                    "INSERT INTO companies (name, sector, address, city, zip_code, website, notes, rating, account_manager_id) VALUES (?,?,?,?,?,?,?,?,?)",
                    (body["name"], body.get("sector"), body.get("address"), body.get("city"),
                     body.get("zip_code"), body.get("website"), body.get("notes"),
                     body.get("rating", "C"), body.get("account_manager_id")))
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
                cur = conn.execute(
                    "INSERT INTO interactions (contact_id,user_id,type,date,subject,notes) VALUES (?,?,?,?,?,?)",
                    (body["contact_id"], body.get("user_id"), body["type"], body["date"],
                     body.get("subject"), body.get("notes")))
                conn.commit()
                row = conn.execute(
                    """SELECT i.*, c.first_name||' '||c.last_name AS contact_name, u.name AS user_name
                       FROM interactions i JOIN contacts c ON i.contact_id=c.id LEFT JOIN users u ON i.user_id=u.id
                       WHERE i.id=?""", (cur.lastrowid,)).fetchone()
                log_audit(conn, uid, "create", "interaction", cur.lastrowid, body.get("subject", body["type"]),
                          {"type": body["type"], "contact_id": body["contact_id"]})
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
                          json.dumps({"company_id": body["company_id"]}))
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
        if path != "/api/emails/upload":
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

        contact_id = fields.get("contact_id")
        if not contact_id:
            return self._error(400, "contact_id er paakraevet")

        user_id = fields.get("user_id") or None

        parsed = parse_eml(file_content)
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
                       rating=?,account_manager_id=? WHERE id=?""",
                    (e["name"], e["sector"], e["address"], e["city"], e["zip_code"],
                     e["website"], e["notes"], e.get("rating", "C"), e.get("account_manager_id"), cid))
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
                          json.dumps({"status": e["status"]}))
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
                conn.execute("DELETE FROM users WHERE id = ?", (uid_del,))
                conn.commit()
                if row:
                    log_audit(conn, uid, "delete", "user", uid_del, row["name"])
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
            INSERT INTO companies (name, sector, city, zip_code, rating) VALUES ('Energi Fyn', 'el', 'Odense', '5000', 'A');
            INSERT INTO companies (name, sector, city, zip_code, rating) VALUES ('TREFOR Vand', 'vand', 'Vejle', '7100', 'B');
            INSERT INTO companies (name, sector, city, zip_code, rating) VALUES ('Fjernvarme Fyn', 'varme', 'Odense', '5000', 'B');
            INSERT INTO companies (name, sector, city, zip_code, rating) VALUES ('Verdo', 'multiforsyning', 'Randers', '8900', 'A');
            INSERT INTO companies (name, sector, city, zip_code, rating) VALUES ('EWII', 'multiforsyning', 'Kolding', '6000', 'C');
            INSERT INTO companies (name, sector, city, zip_code, rating) VALUES ('Aarhus Vand', 'vand', 'Aarhus', '8000', 'B');
        """)
        contacts = [
            (1,"Lars","Hansen","CEO","lars@energifyn.dk",1),(1,"Mette","Andersen","CFO","mette@energifyn.dk",0),
            (1,"Peter","Skov","Afregningschef","peter@energifyn.dk",1),(2,"Anne","Mortensen","CEO","anne@trefor.dk",0),
            (2,"Henrik","Olsen","COO","henrik@trefor.dk",1),(3,"Soeren","Frederiksen","CEO","soren@fjernvarmefyn.dk",0),
            (4,"Camilla","Thomsen","CEO","camilla@verdo.dk",1),(4,"Michael","Nielsen","Kundechef","michael@verdo.dk",0),
            (5,"Birgitte","Jensen","CCO","birgitte@ewii.dk",0),(6,"Kasper","Holm","CEO","kasper@aarhusvand.dk",0),
        ]
        for cid, fn, ln, title, em, li in contacts:
            conn.execute("INSERT INTO contacts (company_id,first_name,last_name,title,email,on_linkedin_list) VALUES (?,?,?,?,?,?)",
                         (cid, fn, ln, title, em, li))
        interactions = [
            (1,1,"meeting","2026-03-01","Strategimoede"),(1,1,"email","2026-03-03","Opfoelgning"),
            (2,1,"phone","2026-02-25","Budget-diskussion"),(3,2,"linkedin","2026-02-20","LinkedIn besked"),
            (3,2,"email","2026-02-28","Afregningssystem demo"),(4,1,"meeting","2026-02-15","Praesentation"),
            (5,2,"email","2026-02-18","Teknisk dok"),(4,1,"phone","2026-02-20","Opfoelgning"),
            (6,1,"email","2025-12-10","Introduktion"),(6,1,"phone","2025-12-15","Kort samtale"),
            (7,2,"meeting","2026-02-01","Foerste moede"),(7,2,"email","2026-02-05","Opfoelgning"),
            (9,1,"email","2026-01-15","Indledende kontakt"),
        ]
        for cid, uid_seed, t, d, s in interactions:
            conn.execute("INSERT INTO interactions (contact_id,user_id,type,date,subject) VALUES (?,?,?,?,?)", (cid,uid_seed,t,d,s))
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
