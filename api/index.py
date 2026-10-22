"""Relations CRM – Vercel serverless API handler (PostgreSQL / Neon)."""
import json
import os
import email as email_lib
from email import policy as email_policy
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.extras
from decimal import Decimal

# ─── DB wrapper ───
class DB:
    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

def get_db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    return DB(conn)

def _json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

DEFAULT_SALES_PROCESS = """Vi sælger software til forsynings- og energiselskaber. Vi har typisk to forløb:

Direkte salg: indledende møder → produktdemo → besvarelse af spørgsmål (nogle gange ud fra kundens kravspec) → tilbud med pris og tidsplan → forhandling → kontrakt.

Udbud: samme forløb, men med en meget formel kravbesvarelse, faste frister og en evaluering.

Når jeg følger op, vil jeg altid vide: hvor i forløbet er kunden, hvad er næste skridt og hvornår, hvem beslutter, hvem konkurrerer vi mod, og hvad skal der til for at komme videre."""

# Faste spørgsmål pr. område ud over kunder og mål (formuleret som CEO'en ville stille dem)
REPORT_QUESTIONS = {
    "salg": [
        ("marketing", "Marketing de sidste 14 dage",
         {"hint": "Hvilke aktiviteter har vi haft, hvad kom der ud af dem, og hvad er planen for de næste 14 dage?"}),
        ("question", "Andet jeg bør vide?",
         {"hint": "Fx nye muligheder, konkurrenter, eller hvor du har brug for hjælp."}),
    ],
    "leverance": [
        ("question", "Leverancer de sidste 14 dage",
         {"hint": "Hvad er leveret, hvad er forsinket, og hvorfor?"}),
        ("question", "Kapacitet og ressourcer",
         {"hint": "Har vi folk nok til det, der er lovet de næste 4–8 uger? Hvor er flaskehalsen?"}),
        ("question", "Kvalitet og kundetilfredshed",
         {"hint": "Fejl, klager eller ros siden sidst. Er der kunder, der er utilfredse?"}),
        ("question", "Andet jeg bør vide?", {"hint": "Risici eller beslutninger du har brug for."}),
    ],
    "oekonomi": [
        ("question", "Likviditet",
         {"hint": "Hvordan ser likviditeten ud nu og de næste 3 måneder? Noget, der skal handles på?"}),
        ("question", "Fakturering og debitorer",
         {"hint": "Er alt faktureret, der kan faktureres? Hvilke kunder skylder over forfald?"}),
        ("question", "Resultat mod budget",
         {"hint": "Hvor ligger vi i forhold til budget for måneden og året til dato? Største afvigelser og hvorfor."}),
        ("question", "Andet jeg bør vide?", {"hint": "Risici, kontrakter eller beslutninger du har brug for."}),
    ],
}

import re as _re
UNKNOWN_RE = _re.compile(r"\b(ved (det |jeg |vi |han |hun )?ikke|ved (jeg|vi) (det )?ikke|aner (det )?ikke|ingen anelse|ikke afklaret|uvist|tbd)\b|^\s*[?\-–]+\s*$", _re.I)

SALES_TYPES = [["direkte", "Direkte salg"], ["udbud", "Udbud"], ["ved_ikke", "Ved ikke"]]
SALES_PHASES = [["indledende", "Indledende møder"], ["demo", "Demo"], ["afklaring", "Spørgsmål / kravspec / kravbesvarelse"],
                ["tilbud", "Tilbud"], ["forhandling", "Forhandling"], ["kontrakt", "Kontrakt"],
                ["vundet", "Vundet"], ["tabt", "Tabt"], ["ikke_i_proces", "Ikke i proces"], ["ved_ikke", "Ved ikke"]]
# Fase → det grove salgsstadie, som kundematrixen bruger
PHASE_TO_STAGE = {"indledende": "tidlig_fase", "demo": "aktiv_dialog", "afklaring": "aktiv_dialog",
                  "tilbud": "fremskreden", "forhandling": "fremskreden", "kontrakt": "fremskreden"}
MAX_DETAILED_CUSTOMERS = 12
AREA_NAMES = [("salg", "salg & marketing"), ("leverance", "leverance"), ("oekonomi", "økonomi"), ("tvaers", "tværgående")]

# Svarform: det skal være så let som muligt at svare
ANSWER_FORMAT_RULES = (
    "Vælg den svarform, der er hurtigst for lederen, for hvert spørgsmål:\n"
    "- choice: når svaret er et af få kendte udfald. Giv 2–5 korte options og tag 'Ved ikke' med, når det er relevant. "
    "Fx 'Er tilbuddet afleveret?' → ['Afleveret', 'Udskudt', 'Tabt', 'Ved ikke'].\n"
    "- date: når der spørges om hvornår. number: når der spørges om et tal eller beløb.\n"
    "- text: kun når der skal forklares noget, fx hvad der skal til, eller hvad der er sket.\n"
    "Brug options = [] for andet end choice. Spørg IKKE om salgsform (direkte salg/udbud) eller fase. "
    "Kunder har altid faste felter til næste skridt, dato og sandsynlighed, så spørg heller ikke om dem. "
    "Det afklares i en fælles klik-liste. Max 3 spørgsmål pr. emne, og hellere 2.")


def goal_quality(g):
    """Hvor konkret er målet? Returnerer (score 0–100, liste over det der mangler)."""
    checks = [
        (g.get("target_value") is not None or (g.get("milestones_total") or 0) >= 2, "måltal eller milepæle"),
        (bool(g.get("due_date")), "deadline"),
        (bool(g.get("owner_role")), "ansvarlig"),
        (bool((g.get("description") or "").strip()), "beskrivelse af hvordan det måles"),
        (g.get("target_value") is None or bool(g.get("unit")), "enhed"),
        (g.get("kind") != "strategisk" or (g.get("milestones_total") or 0) >= 2, "milepæle (strategisk)"),
        (bool(g.get("last_checkin")) and (date.today() - date.fromisoformat(str(g["last_checkin"])[:10])).days <= 30, "statusopdatering inden for 30 dage"),
    ]
    missing = [label for ok, label in checks if not ok]
    return round((len(checks) - len(missing)) / len(checks) * 100), missing


def _goal_expected(g):
    """Forventet fremdrift 0–1 ved lineær plan fra start til deadline (samme logik som i frontend)."""
    due = str(g.get("due_date") or "")[:10]
    if not due:
        return None
    start = str(g.get("start_date") or g.get("created_at") or date.today().isoformat())[:10]
    total = (date.fromisoformat(due) - date.fromisoformat(start)).days
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, (date.today() - date.fromisoformat(start)).days / total))


SEED_GOALS = [
    ("salg", "drift", "Sælge 150.000 målepunkter i 2027",
     "Samlet antal solgte målepunkter i kontrakter underskrevet i 2027.",
     "CCO", "målepunkter", 0, 150000, 0, "2027-01-01", "2027-12-31"),
    ("salg", "strategisk", "Kendt af alle i forsynings- og energibranchen",
     "Måles som andel af branchens selskaber, hvor vi har en god eller stærk relation.",
     "CCO", "%", 0, 100, 0, None, "2027-12-31"),
    ("leverance", "strategisk", "100 % AI-understøttet udvikling",
     "Andel af udviklingsarbejdet, der foregår AI-understøttet.",
     "COO", "%", 0, 100, 0, None, "2027-12-31"),
]

# ─── Database init ───
def init_db():
    db = get_db()
    try:
        stmts = [
            """CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                sector TEXT,
                address TEXT, city TEXT, zip_code TEXT, website TEXT, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rating TEXT DEFAULT 'C',
                account_manager_id INTEGER,
                importance TEXT DEFAULT 'middel_vigtig',
                sales_stage TEXT DEFAULT 'tidlig_fase',
                score_cxo INTEGER DEFAULT 0,
                score_kontaktfrekvens INTEGER DEFAULT 0,
                score_kontaktbredde INTEGER DEFAULT 0,
                score_kendskab INTEGER DEFAULT 0,
                score_historik INTEGER DEFAULT 0,
                score_kendskab_behov INTEGER DEFAULT 0,
                score_workshops INTEGER DEFAULT 0,
                score_marketing INTEGER DEFAULT 0,
                tier TEXT,
                ejerform TEXT,
                has_el BOOLEAN DEFAULT FALSE,
                has_gas BOOLEAN DEFAULT FALSE,
                has_vand BOOLEAN DEFAULT FALSE,
                has_varme BOOLEAN DEFAULT FALSE,
                has_spildevand BOOLEAN DEFAULT FALSE,
                has_affald BOOLEAN DEFAULT FALSE,
                est_kunder TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS contacts (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                first_name TEXT NOT NULL, last_name TEXT NOT NULL,
                title TEXT, email TEXT, phone TEXT, linkedin_url TEXT,
                on_linkedin_list BOOLEAN DEFAULT FALSE, notes TEXT,
                linkedin_connected_systemate BOOLEAN DEFAULT FALSE,
                linkedin_connected_settl BOOLEAN DEFAULT FALSE,
                linkedin_last_checked DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS interactions (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id),
                type TEXT NOT NULL,
                date DATE NOT NULL, subject TEXT, notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS emails (
                id SERIAL PRIMARY KEY,
                interaction_id INTEGER REFERENCES interactions(id) ON DELETE CASCADE,
                from_email TEXT, to_email TEXT, cc TEXT,
                subject TEXT, body_text TEXT, body_html TEXT,
                date_sent TIMESTAMP, eml_filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id)",
            "CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id)",
            "CREATE INDEX IF NOT EXISTS idx_interactions_company ON interactions(company_id)",
            "CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(date)",
            "CREATE INDEX IF NOT EXISTS idx_emails_interaction ON emails(interaction_id)",
            """CREATE TABLE IF NOT EXISTS score_settings (
                rating TEXT PRIMARY KEY,
                threshold INTEGER NOT NULL DEFAULT 50
            )""",
            "INSERT INTO score_settings (rating, threshold) VALUES ('A', 70) ON CONFLICT DO NOTHING",
            "INSERT INTO score_settings (rating, threshold) VALUES ('B', 50) ON CONFLICT DO NOTHING",
            "INSERT INTO score_settings (rating, threshold) VALUES ('C', 30) ON CONFLICT DO NOTHING",
            """CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                user_name TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                entity_name TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)",
            """CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                assigned_to INTEGER REFERENCES users(id),
                created_by INTEGER REFERENCES users(id),
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'normal',
                due_date DATE,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_tasks_company ON tasks(company_id)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date)",
            """CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(is_read)",
            "CREATE INDEX IF NOT EXISTS idx_notif_company ON notifications(company_id)",
            """CREATE TABLE IF NOT EXISTS linkedin_activities (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                activity_type TEXT NOT NULL,
                content_summary TEXT,
                linkedin_post_url TEXT,
                observed_by INTEGER REFERENCES users(id),
                activity_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_li_act_contact ON linkedin_activities(contact_id)",
            """CREATE TABLE IF NOT EXISTS linkedin_engagements (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                engagement_type TEXT NOT NULL,
                company_page TEXT NOT NULL,
                post_url TEXT,
                observed_by INTEGER REFERENCES users(id),
                observed_date DATE NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_li_eng_contact ON linkedin_engagements(contact_id)",
            """CREATE TABLE IF NOT EXISTS tags (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#6b7280',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS company_tags (
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (company_id, tag_id)
            )""",
            """CREATE TABLE IF NOT EXISTS contact_tags (
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (contact_id, tag_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_company_tags_company ON company_tags(company_id)",
            "CREATE INDEX IF NOT EXISTS idx_company_tags_tag ON company_tags(tag_id)",
            "CREATE INDEX IF NOT EXISTS idx_contact_tags_contact ON contact_tags(contact_id)",
            "CREATE INDEX IF NOT EXISTS idx_contact_tags_tag ON contact_tags(tag_id)",
            """CREATE TABLE IF NOT EXISTS tender_templates (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS tender_template_sections (
                id SERIAL PRIMARY KEY,
                template_id INTEGER NOT NULL REFERENCES tender_templates(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                default_days_before_deadline INTEGER DEFAULT 7,
                sort_order INTEGER NOT NULL DEFAULT 0
            )""",
            "CREATE INDEX IF NOT EXISTS idx_tts_template ON tender_template_sections(template_id)",
            """CREATE TABLE IF NOT EXISTS tenders (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                template_id INTEGER REFERENCES tender_templates(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                deadline DATE,
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                responsible_id INTEGER REFERENCES users(id),
                created_by INTEGER REFERENCES users(id),
                estimated_value TEXT,
                portal_link TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_tenders_company ON tenders(company_id)",
            "CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status)",
            """CREATE TABLE IF NOT EXISTS tender_sections (
                id SERIAL PRIMARY KEY,
                tender_id INTEGER NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                content TEXT,
                responsible_id INTEGER REFERENCES users(id),
                reviewer_id INTEGER REFERENCES users(id),
                status TEXT NOT NULL DEFAULT 'not_started',
                deadline DATE,
                start_date DATE,
                end_date DATE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_tsections_tender ON tender_sections(tender_id)",
            """CREATE TABLE IF NOT EXISTS tender_section_audit (
                id SERIAL PRIMARY KEY,
                section_id INTEGER NOT NULL REFERENCES tender_sections(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id),
                user_name TEXT,
                note_type TEXT NOT NULL DEFAULT 'note',
                content TEXT,
                old_value TEXT,
                new_value TEXT,
                field_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_section_audit ON tender_section_audit(section_id)",
            """CREATE TABLE IF NOT EXISTS company_notes (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id),
                user_name TEXT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_company_notes_company ON company_notes(company_id)",
            """CREATE TABLE IF NOT EXISTS task_notes (
                id SERIAL PRIMARY KEY,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id),
                user_name TEXT,
                content TEXT NOT NULL,
                note_type TEXT NOT NULL DEFAULT 'note',
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_task_notes_task ON task_notes(task_id)",
            """CREATE TABLE IF NOT EXISTS tender_notes (
                id SERIAL PRIMARY KEY,
                tender_id INTEGER NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id),
                user_name TEXT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_tender_notes_tender ON tender_notes(tender_id)",
            """CREATE TABLE IF NOT EXISTS score_decay_rules (
                id SERIAL PRIMARY KEY,
                inactivity_days INTEGER NOT NULL DEFAULT 21,
                penalty_points INTEGER NOT NULL DEFAULT 10,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE
            )""",
            "INSERT INTO score_decay_rules (id, inactivity_days, penalty_points, description) VALUES (1, 21, 10, 'Fald efter 3 ugers inaktivitet') ON CONFLICT DO NOTHING",
            "INSERT INTO score_decay_rules (id, inactivity_days, penalty_points, description) VALUES (2, 42, 20, 'Fald efter 6 ugers inaktivitet') ON CONFLICT DO NOTHING",
            "INSERT INTO score_decay_rules (id, inactivity_days, penalty_points, description) VALUES (3, 63, 30, 'Fald efter 9 ugers inaktivitet') ON CONFLICT DO NOTHING",
            """CREATE TABLE IF NOT EXISTS score_history (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                score REAL NOT NULL,
                level TEXT,
                recorded_at DATE NOT NULL DEFAULT CURRENT_DATE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_score_history_company ON score_history(company_id)",
            "CREATE INDEX IF NOT EXISTS idx_score_history_date ON score_history(recorded_at)",
        ]
        for stmt in stmts:
            db.execute(stmt)
        db.commit()

        # Idempotent migrations
        migrations = [
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS rating TEXT DEFAULT 'C'",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS account_manager_id INTEGER REFERENCES users(id)",
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS linkedin_connected_systemate BOOLEAN DEFAULT FALSE",
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS linkedin_connected_settl BOOLEAN DEFAULT FALSE",
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS linkedin_last_checked DATE",
            "ALTER TABLE tender_sections ADD COLUMN IF NOT EXISTS start_date DATE",
            "ALTER TABLE tender_sections ADD COLUMN IF NOT EXISTS end_date DATE",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS importance TEXT DEFAULT 'middel_vigtig'",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sales_stage TEXT DEFAULT 'tidlig_fase'",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_cxo INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_kontaktfrekvens INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_kontaktbredde INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_kendskab INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_historik INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_kendskab_behov INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_workshops INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS score_marketing INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS tier TEXT",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS ejerform TEXT",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_el BOOLEAN DEFAULT FALSE",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_gas BOOLEAN DEFAULT FALSE",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_vand BOOLEAN DEFAULT FALSE",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_varme BOOLEAN DEFAULT FALSE",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_spildevand BOOLEAN DEFAULT FALSE",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_affald BOOLEAN DEFAULT FALSE",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS est_kunder TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
            "ALTER TABLE interactions ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE",
            "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS area TEXT DEFAULT 'salg'",
            # SystemateCEO: mål, statusopdateringer, milepæle, ledermøder og aktioner
            """CREATE TABLE IF NOT EXISTS goals (
                id SERIAL PRIMARY KEY,
                area TEXT NOT NULL DEFAULT 'salg',
                kind TEXT NOT NULL DEFAULT 'drift',
                title TEXT NOT NULL,
                description TEXT,
                owner_role TEXT,
                company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                unit TEXT,
                start_value NUMERIC DEFAULT 0,
                target_value NUMERIC,
                current_value NUMERIC,
                start_date DATE DEFAULT CURRENT_DATE,
                due_date DATE,
                status TEXT NOT NULL DEFAULT 'not_started',
                last_checkin DATE,
                archived BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS meetings (
                id SERIAL PRIMARY KEY,
                area TEXT NOT NULL,
                title TEXT NOT NULL,
                meeting_date DATE NOT NULL DEFAULT CURRENT_DATE,
                participants TEXT,
                status TEXT NOT NULL DEFAULT 'planned',
                notes JSONB DEFAULT '{}'::jsonb,
                summary TEXT,
                next_meeting_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS goal_checkins (
                id SERIAL PRIMARY KEY,
                goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
                checkin_date DATE NOT NULL DEFAULT CURRENT_DATE,
                value NUMERIC,
                status TEXT NOT NULL,
                comment TEXT,
                user_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS goal_milestones (
                id SERIAL PRIMARY KEY,
                goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                due_date DATE,
                done BOOLEAN DEFAULT FALSE,
                done_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS meeting_actions (
                id SERIAL PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
                area TEXT NOT NULL,
                goal_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
                company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                kind TEXT NOT NULL DEFAULT 'aktion',
                title TEXT NOT NULL,
                owner TEXT,
                due_date DATE,
                status TEXT NOT NULL DEFAULT 'open',
                done_at TIMESTAMP,
                closed_in_meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_goal_checkins_goal ON goal_checkins(goal_id)",
            "CREATE INDEX IF NOT EXISTS idx_goal_milestones_goal ON goal_milestones(goal_id)",
            "CREATE INDEX IF NOT EXISTS idx_meeting_actions_area ON meeting_actions(area, status)",
            # Indrapportering: runder med spørgsmål til CCO/COO/CFO før ledermøder
            """CREATE TABLE IF NOT EXISTS report_rounds (
                id SERIAL PRIMARY KEY,
                area TEXT NOT NULL,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
                respondent_user_id INTEGER REFERENCES users(id),
                respondent_name TEXT,
                token TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                due_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP,
                submitted_at TIMESTAMP,
                ai_assessment TEXT,
                ai_model TEXT,
                ai_generated_at TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS report_items (
                id SERIAL PRIMARY KEY,
                round_id INTEGER NOT NULL REFERENCES report_rounds(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                ref_type TEXT,
                ref_id INTEGER,
                company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                context JSONB DEFAULT '{}'::jsonb,
                answer JSONB,
                answered_at TIMESTAMP,
                sort_order INTEGER DEFAULT 0
            )""",
            "CREATE INDEX IF NOT EXISTS idx_report_items_round ON report_items(round_id)",
            "ALTER TABLE report_rounds ADD COLUMN IF NOT EXISTS practice BOOLEAN DEFAULT FALSE",
            "ALTER TABLE report_rounds ADD COLUMN IF NOT EXISTS ai_questions BOOLEAN DEFAULT FALSE",
            "ALTER TABLE report_rounds ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP",
            "ALTER TABLE report_rounds ADD COLUMN IF NOT EXISTS message TEXT",
            "ALTER TABLE report_rounds ADD COLUMN IF NOT EXISTS followup_of INTEGER REFERENCES report_rounds(id) ON DELETE CASCADE",
            # Notifikationer kan også pege på andet end en virksomhed (fx en indsendt indrapportering)
            "ALTER TABLE notifications ALTER COLUMN company_id DROP NOT NULL",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title TEXT",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS link TEXT",
            # Husker om en kunde allerede står under scoregrænsen, så der kun notificeres ved ændringer
            """CREATE TABLE IF NOT EXISTS score_alert_state (
                company_id INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                below BOOLEAN NOT NULL,
                last_score NUMERIC,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            # Indkøbsfællesskaber (fx Servia): en virksomhed kan være et fællesskab, kunder kan være medlemmer,
            # og et tilbud kan gå direkte til kunden eller via fællesskabet
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_purchasing_group BOOLEAN DEFAULT FALSE",
            """CREATE TABLE IF NOT EXISTS company_memberships (
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                group_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (company_id, group_id)
            )""",
            "ALTER TABLE tenders ADD COLUMN IF NOT EXISTS purchase_route TEXT DEFAULT 'selv'",
            # Salgsform og fase efter CEO'ens salgsproces (opdateres fx fra indrapporteringens hurtige lister)
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sales_type TEXT",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sales_phase TEXT",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sales_phase_updated DATE",
            # Opgaver (fx lønsamtaler): aktioner kan stå alene, have beskrivelse, tjekliste og en log med noter
            "ALTER TABLE meeting_actions ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE meeting_actions ADD COLUMN IF NOT EXISTS checklist JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE meeting_actions ADD COLUMN IF NOT EXISTS notes TEXT",
            "ALTER TABLE tenders ADD COLUMN IF NOT EXISTS via_group_id INTEGER REFERENCES companies(id) ON DELETE SET NULL",
            """CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
        ]
        for m in migrations:
            try:
                db.execute(m)
                db.commit()
            except Exception:
                db.rollback()

        # Seed: Jess user, kun i en helt tom database (ellers kommer brugeren igen, hvis e-mailen er rettet)
        db.execute("""INSERT INTO users (name, email, role) SELECT 'Jess Kristensen', 'jess@systemate.dk', 'admin'
                      WHERE NOT EXISTS (SELECT 1 FROM users)""")
        db.commit()

        # Seed companies if empty
        cnt = db.execute("SELECT COUNT(*) AS cnt FROM companies").fetchone()["cnt"]
        if cnt == 0:
            _seed_companies(db)

        # Seed: AI-kontekst om salgsprocessen (CEO'en kan rette den under Ledermøder)
        db.execute("INSERT INTO app_settings (key, value) VALUES ('sales_process', %s) ON CONFLICT (key) DO NOTHING",
                   (DEFAULT_SALES_PROCESS,))
        db.commit()

        # Seed: CEO-mål fra brugerens egne eksempler, kun første gang (flaget gør, at slettede mål ikke kommer igen)
        if not db.execute("SELECT 1 FROM app_settings WHERE key = 'goals_seeded'").fetchone():
            if db.execute("SELECT COUNT(*) AS cnt FROM goals").fetchone()["cnt"] == 0:
                for g in SEED_GOALS:
                    db.execute(
                        """INSERT INTO goals (area,kind,title,description,owner_role,unit,start_value,target_value,
                           current_value,start_date,due_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", g)
            db.execute("INSERT INTO app_settings (key, value) VALUES ('goals_seeded', 'true') ON CONFLICT (key) DO NOTHING")
            db.commit()

    finally:
        db.close()

def _seed_companies(db):
    companies = [
        ('Forsyning Helsingør','multiforsyning','Helsingør','T1','Kommunalt',True,False,True,True,True,True,'~61.000 borgere','Fuld 5-arts: Forsyning Elnet+Kronborg El + vand+varme+spildevand+affald. ~150 ans.'),
        ('Frederikshavn Forsyning','multiforsyning','Frederikshavn','T1','Kommunalt',True,False,True,True,True,True,'~62.000 borgere','Fuld 5-arts: Frh. Elhandel+Elnet + vand+varme+spildevand+affald. ~250 ans.'),
        ('EWII (TREFOR)','multiforsyning','Kolding','T1','Selvejende',True,False,True,True,False,False,'~400.000 kunderelationer','El(net+handel), vand, fjernvarme, fiber. ~700 ans.'),
        ('Verdo','multiforsyning','Randers/Herning','T1','Andel',True,False,True,True,False,False,'~100.000 kunder','Fjernvarme(~75k), vand, el(Kongerslev elnet+elhandel).'),
        ('Bornholms Energi & Forsyning','multiforsyning','Rønne','T1','Forbrugerejet',True,False,True,True,True,False,'~28.000 borgere','El(handel), vand, varme, spildevand.'),
        ('Energi Viborg','multiforsyning','Viborg','T1','Kommunalt',True,False,True,False,True,False,'~45.000 borgere','El(net Kimbrer), vand, spildevand, gadelys. ~105 ans.'),
        ('Læsø Forsyning','multiforsyning','Læsø','T1','Kommunalt',True,False,True,True,True,True,'~1.800 husstande','Fuld multi: elnet+vand+varme+spildevand+renovation.'),
        ('Struer Energi','multiforsyning','Struer','T1','Kommunalt',True,False,True,True,True,False,'~11.000 borgere','Multi: el(net), fjernvarme, vand, spildevand.'),
        ('Tønder Forsyning','multiforsyning','Tønder','T1','Kommunalt',True,False,True,True,True,True,'~40.000 borgere','Multi: el(handel), vand, fjernvarme, spildevand, affald.'),
        ('Energi Ikast','multiforsyning','Ikast','T1','Andel',True,False,True,True,False,False,'~8.000-10.000 kunder','El(Ikast El Net+Samstrøm), varme, fiber. Afregner vand+spildevand. ~40 ans.'),
        ('GEV (Grindsted)','multiforsyning','Grindsted','T1','Andel',True,False,True,True,False,False,'~7.000 hjem','Multi: el(GEV Elnet+Samstrøm), vand, varme.'),
        ('Vildbjerg Tekniske Værker','multiforsyning','Vildbjerg','T1','Andel',True,False,True,True,False,False,'~3.000-4.000 kunder','Vildbjerg Elværk+Vandværk+Varmeværk. Samstrøm.'),
        ('Energi Hurup','multiforsyning','Hurup Thy','T1','Andel',True,False,True,True,False,False,'~2.600 vandkunder','Hurup Elværk+Fjernvarme+Vandværk. Samstrøm.'),
        ('Sunds Forsyning','multiforsyning','Sunds','T1','Andel',True,False,True,True,False,False,'~2.500-3.000','Elnet+Samstrøm, vandværk, varme.'),
        ('Videbæk Energiforsyning','multiforsyning','Videbæk','T1','Andel',True,False,True,True,False,False,'~3.000-4.000','Elnet+Samstrøm, vandværk, fjernvarme.'),
        ('Vest Forsyning (Holstebro)','multiforsyning','Holstebro','T1','Kommunalt',True,False,True,True,True,True,'~58.000 borgere','Multi: el(handel), vand, varme, spildevand, affald.'),
        ('SK Forsyning (Slagelse)','multiforsyning','Slagelse','T1','Kommunalt',True,False,True,True,True,False,'~80.000 borgere','Multi: el(SK Energi=elhandel), vand, varme, spildevand.'),
        ('Vesthimmerlands Elforsyning','multiforsyning','Aars','T1','Andel',True,False,False,True,False,False,'~15.000 elkunder','Elnet (Aars-Hornum Net)+elhandel. Tilknyttet lokal varme.'),
        ('Andel (Andel Energi+Cerius+Radius)','multiforsyning','Sjælland/hele DK','T2','Andel',True,True,False,False,False,False,'~1.200.000 elkunder\nElnet:1.400.000',"DK's største el. Elhandel+gas+elnet+fiber."),
        ('Norlys (N1, Stofa, Boxer)','el','Jylland/hele DK','T2','Andel',True,False,False,False,False,False,'~1.700.000 kunderelationer','El(net N1+handel), tele/fiber, TV. ~4.500 ans.'),
        ('NRGi (Konstant/Dinel)','el','Østjylland/hele DK','T2','Andel',True,False,False,False,False,False,'~140.000 elkunder','Elhandel, elnet, fiber, energirådgivning. ~1.600 ans.'),
        ('Energi Fyn','multiforsyning','Fyn/hele DK','T2','Andel',True,True,False,False,False,False,'~220.000 elkunder','Elnet+elhandel, naturgas, fiber. ~390 ans.'),
        ('Ørsted','el','Hele DK/globalt','T2','Børsnoteret',True,False,False,False,False,False,'Primært B2B/VE-produktion','VE-gigant. Vindmøller, solceller. Tidl. DONG. Ikke retail-el i stor stil.'),
        ('AURA Energi','el','Østjylland','T2','Andel',True,False,False,False,False,False,'~100.000+ kunder','Elhandel, elnet, fiber.'),
        ('SEF (Sydfyns Elforsyning)','multiforsyning','Sydfyn/hele DK','T2','Selvejende fond',True,True,False,False,False,False,'Sydfyn + landsdk.','El(FLOW Elnet+SEF Energi), naturgas, fiber, varmepumper. ~160 ans.'),
        ('Thy-Mors Energi','el','Thy/Mors','T2','Andel',True,False,False,False,False,False,'~44.000 andelshavere','Elnet(Elværk)+elhandel, fiber.'),
        ('OK','el','Hele DK','T2','Andel',True,False,False,False,False,False,'Stor kundebasis','Andelsselskab. Brændstof+el+ladning.'),
        ('Nord Energi','el','Nordjylland','T2','Andel',True,False,False,False,False,False,'Nordjylland','Elnetselskab+elhandel.'),
        ('Jysk Energi','el','Jylland','T2','Privat',True,False,False,False,False,False,'Voksende','Elhandelsselskab.'),
        ('Vindstød','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Voksende','Dansk vindenergi direkte.'),
        ('Barry','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Voksende','App-baseret elselskab. Timepriser.'),
        ('True Energy','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Voksende','Smart-el-app med forbrugsstyring.'),
        ('b.energy','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('NettoPower','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Voksende','Lavpris-el, grøn profil.'),
        ('Modstrøm','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Voksende','Elhandelsselskab.'),
        ('Velkommen','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Go Energi','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Cheap Energy','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Edison','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Elektron','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Forskel','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('FRI Energy','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('GNP Energy','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab (norsk oprindelse).'),
        ('Grøn El-Forsyning','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('EnergiPlus','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Kärnfull Energi','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Svensk atomkraft-elselskab i DK.'),
        ('Natur-Energi','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Nordisk Energy','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Norsk Elkraft Danmark','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Norsk elhandelsselskab i DK.'),
        ('Ø-strøm','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Power4U','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Preasy','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Strømlinet','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('strømtid','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Vets Energi','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Samstrøm','el','Jylland','T2','Fællesejet',True,False,False,False,False,False,'Partner for 8 værker','Fælles elhandelsselskab for GEV,Ikast,Sunds,Hjerting,Tarm,Videbæk,VTV,Hurup.'),
        ('SK Energi (SK Forsyning)','el','Slagelse','T2','Kommunalt',True,False,False,False,False,False,'Slagelse-omr.','Elhandel. Del af SK Forsyning-koncern (som er Tier 1).'),
        ('nef Fonden (Nordvestjysk)','el','Nordvestjylland','T2','Fond',True,False,False,False,False,False,'Nordvestjylland','Elhandel/energi. Fond.'),
        ('E.ON Danmark','el','Hele DK','T2','Privat/koncern',True,False,False,False,False,False,'B2B','Tysk energikoncern. El til erhverv i DK.'),
        ('Energidrift','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Energiselskabet Elg','el','Hele DK','T2','Privat',True,False,False,False,False,False,'Mindre','Elhandelsselskab.'),
        ('Energi Danmark / Mind Energy','multiforsyning','Hele DK/Norden','T2','Privat/koncern',True,True,False,False,False,False,'Primært B2B','Energitrading. Del af Andel-koncern.'),
        ('Danske Commodities','multiforsyning','Hele DK/Europa','T2','Privat/koncern',True,True,False,False,False,False,'Primært B2B','Energitrading. Ejet af Equinor.'),
        ('DCC Energi','el','Hele DK','T2','Privat',True,False,False,False,False,False,'B2B','Energihandel/trading.'),
        ('Energy Nordic','el','Hele DK','T2','Privat',True,False,False,False,False,False,'B2B','Energihandel/erhverv.'),
        ('Cerius (Andel)','el','Sjælland','T2','Andel',True,False,False,False,False,False,'~590.000 netkunder','Netselskab.'),
        ('Radius Elnet (Andel)','el','Storkøbenhavn','T2','Andel',True,False,False,False,False,False,'~800.000 netkunder','Netselskab.'),
        ('N1 (Norlys)','el','Jylland','T2','Andel',True,False,False,False,False,False,'~600.000+ netkunder','Jyllands største net.'),
        ('TREFOR El-Net (EWII)','el','Trekantomr.','T2','Selvejende',True,False,False,False,False,False,'Trekantomr.','Netselskab.'),
        ('TREFOR El-Net Øst (EWII)','el','Bornholm','T2','Selvejende',True,False,False,False,False,False,'Bornholm','Netselskab.'),
        ('Konstant Net (NRGi)','el','Aarhus','T2','Andel',True,False,False,False,False,False,'Aarhus','Netselskab.'),
        ('Dinel (NRGi)','el','Djursland','T2','Andel',True,False,False,False,False,False,'Djursland','Netselskab.'),
        ('NOE Net','el','Midtjylland','T2','Andel',True,False,False,False,False,False,'Midtjylland','Netselskab.'),
        ('RAH Net','el','Ringkøbing','T2','Andel',True,False,False,False,False,False,'Ringk.-Skjern','Netselskab.'),
        ('FLOW Elnet (SEF)','el','Sydfyn','T2','Selvejende',True,False,False,False,False,False,'Sydfyn/Langeland','Netselskab. Del af SEF.'),
        ('Vores Elnet','el','Fredericia/Vejle','T2','Andel',True,False,False,False,False,False,'Fred./Vejle','Netselskab.'),
        ('+ ca. 25 øvrige små netselskaber','el','Hele DK','T2','Diverse',True,False,False,False,False,False,'Varierende','Ravdex,Veksel,Elinord,Elektrus,NKE,Zeanet,L-Net,Nakskov,Hammel,Midtfyns,Aal m.fl.'),
        ('HOFOR','multiforsyning','København (8 komm.)','T3','Kommunalt',False,True,True,True,True,False,'~1.000.000 vandkunder',"DK's største vand. Vand 8 komm., varme+gas+køling KBH. ~1.700 ans."),
        ('Aalborg Forsyning','multiforsyning','Aalborg','T3','Kommunalt',False,True,True,True,True,False,'~100.000+ husstande','Multi: varme,gas,køling,vand,spildevand. ~500 ans.'),
        ('Frederiksberg Forsyning','multiforsyning','Frederiksberg','T3','Kommunalt',False,True,True,True,True,False,'~55.000 borgere','Gas(bygas),vand,fjernvarme,fjernkøling,spildevand,VE. IKKE el.'),
        ('Silkeborg Forsyning','multiforsyning','Silkeborg','T3','Kommunalt',False,False,True,True,True,True,'~96.000 borgere','Vand,fjernvarme,spildevand,affald. ~140 ans.'),
        ('FORS A/S','multiforsyning','Holbæk/Lejre/Roskilde','T3','Kommunalt',False,False,True,True,True,True,'~100.000+ borgere','Multi 3 kommuner.'),
        ('Din Forsyning','multiforsyning','Esbjerg/Varde','T3','Kommunalt',False,False,True,True,True,True,'~120.000 borgere','Multi: vand,varme,spildevand,affald.'),
        ('Halsnæs Forsyning','multiforsyning','Frederiksværk','T3','Kommunalt',False,False,True,True,True,True,'~31.000 borgere','Fjernvarme,vand,spildevand,affald.'),
        ('Provas','multiforsyning','Haderslev','T3','Kommunalt',False,False,True,True,True,True,'~55.000 borgere','Vand,varme,spildevand,affald.'),
        ('Kalundborg Forsyning','multiforsyning','Kalundborg','T3','Kommunalt',False,False,True,True,True,True,'~49.000 borgere','Vand,varme,spildevand,affald.'),
        ('REFA','multiforsyning','Lolland-Falster','T3','Kommunalt',False,False,False,True,False,True,'~100.000 borgere','Kraftvarme(affald+halm),genbrugspladser.'),
        ('Klar Forsyning','multiforsyning','Slagelse','T3','Kommunalt',False,False,True,True,True,False,'~80.000 borgere','Vand,fjernvarme,spildevand.'),
        ('Sønderborg Forsyning','multiforsyning','Sønderborg','T3','Kommunalt',False,False,True,True,True,False,'~75.000 borgere','Vand,fjernvarme,spildevand.'),
        ('Næstved Forsyning','multiforsyning','Næstved','T3','Kommunalt',False,False,True,True,True,False,'~83.000 borgere','Vand,fjernvarme,spildevand.'),
        ('Skanderborg Forsyning','multiforsyning','Skanderborg','T3','Kommunalt',False,False,True,True,True,False,'~60.000 borgere','Vand,varme,spildevand.'),
        ('Ringsted Forsyning','multiforsyning','Ringsted','T3','Kommunalt',False,False,True,True,True,False,'~35.000 borgere','Vand,fjernvarme,spildevand.'),
        ('Sorø Forsyning','multiforsyning','Sorø','T3','Kommunalt',False,False,True,True,True,False,'~30.000 borgere','Vand,fjernvarme,spildevand.'),
        ('Assens Forsyning','multiforsyning','Assens','T3','Kommunalt',False,False,True,True,True,False,'~41.000 borgere','Vand,fjernvarme,spildevand.'),
        ('Kerteminde Forsyning','multiforsyning','Kerteminde','T3','Kommunalt',False,False,True,True,True,False,'~24.000 borgere','Vand,varme,spildevand.'),
        ('Middelfart Forsyning','multiforsyning','Middelfart','T3','Kommunalt',False,False,True,True,True,False,'~38.000 borgere','Varme,vand,spildevand.'),
        ('Skive Vand/Fjernvarme','multiforsyning','Skive','T3','Kommunalt',False,False,True,True,True,False,'~47.000 borgere','Vand,fjernvarme,spildevand.'),
        ('Horsens Vand/Samn Forsyning','multiforsyning','Horsens/Odder','T3','Kommunalt',False,False,True,False,True,False,'~90.000 borgere','Vand og spildevand.'),
        ('Kolding Forsyning (BlueKolding)','multiforsyning','Kolding','T3','Kommunalt',False,False,True,False,True,False,'~92.000 borgere','Vand og spildevand.'),
        ('Herning Vand','multiforsyning','Herning','T3','Kommunalt',False,False,True,False,True,False,'~50.000 borgere','Vand+spildevand.'),
        ('Hjørring Vandselskab','multiforsyning','Hjørring','T3','Kommunalt',False,False,True,False,True,False,'~66.000 borgere','Vand+spildevand.'),
        ('Favrskov Forsyning','multiforsyning','Hadsten','T3','Kommunalt',False,False,True,False,True,False,'~48.000 borgere','Vand og spildevand.'),
        ('Vejle Spildevand/Varme','multiforsyning','Vejle','T3','Kommunalt',False,False,False,True,True,False,'~55.000 borgere','Fjernvarme+spildevand.'),
        ('Roskilde Forsyning','multiforsyning','Roskilde','T3','Kommunalt',False,False,True,True,True,False,'~88.000 borgere','Vand,varme,spildevand.'),
        ('Billund Vand','multiforsyning','Billund','T3','Kommunalt',False,False,True,False,True,False,'~26.000 borgere','Vand,spildevand.'),
        ('Novafos','multiforsyning','Nordsjælland(9 komm.)','T4','Kommunalt',False,False,True,False,True,False,'~300.000+ borgere',"DK's 2. største vand/spildevand."),
        ('VandCenter Syd','multiforsyning','Odense/Nordfyn','T4','Kommunalt',False,False,True,False,True,False,'~220.000 borgere','Drikkevand og spildevand.'),
        ('Aarhus Vand','multiforsyning','Aarhus','T4','Kommunalt',False,False,True,False,True,False,'~350.000 borgere','Drikkevand og spildevand.'),
        ('BIOFOS','spildevand','Storkøbenhavn','T4','Kommunalt',False,False,False,False,True,False,'~1.200.000 borgere',"DK's største spildevandsrensning."),
        ('Kredsløb (Aarhus)','multiforsyning','Aarhus','T4','Kommunalt',False,False,False,True,False,True,'~350.000 borgere','Fjernvarme+affald.'),
        ('Fjernvarme Fyn','varme','Odense','T4','Kommunalt',False,False,False,True,False,False,'~85.000 kunder',"DK's 3. største fjernvarme."),
        ('Vestforbrænding','multiforsyning','Vestegnen','T4','Kommunalt',False,False,False,True,False,True,'~900.000 borgere',"DK's største affald."),
        ('ARC','multiforsyning','København','T4','Kommunalt',False,False,False,True,False,True,'~600.000 borgere','Affaldsforbrænding+varme.'),
        ('ARGO','multiforsyning','Roskilde','T4','Kommunalt',False,False,False,True,False,True,'~470.000 borgere','Affald,genbrug,fjernvarme.'),
        ('Evida','gas','Hele DK','T4','Statsligt',False,True,False,False,False,False,'~400.000 gasmålere','National gasdistributør.'),
        ('CTR','varme','Storkøbenhavn','T4','Kommunalt',False,False,False,True,False,False,'Transmission','Fjernvarmetransmission.'),
        ('VEKS','varme','Vestegnen','T4','Kommunalt',False,False,False,True,False,False,'13 kommuner','Fjernvarmetransmission.'),
        ('Nordværk','multiforsyning','Aalborg','T4','Kommunalt',False,False,False,True,False,True,'Nordjylland','Affaldsforbrænding+fjernvarme.'),
        ('AVV','multiforsyning','Hjørring','T4','Kommunalt',False,False,False,True,False,True,'~75.000 borgere','Affaldsbehandling+fjernvarme.'),
        ('~350+ fjernvarmeværker','varme','Hele DK','T4','Primært andel',False,False,False,True,False,False,'~1.800.000 husstande','Ca. 400 fjernvarmeselskaber i DK.'),
        ('~2.600 vandværker','vand','Hele DK','T4','Primært andel',False,False,True,False,False,False,'Varierende','Mange forbrugerejede.'),
        ('Clever','e-mobilitet','Hele DK','EM','Privat (Andel)',True,False,False,False,False,False,'~200.000+ brugere\n~3.000 ladepunkter',"DK's største ladeoperatør. Abonnements-model. Opladning af elbiler."),
        ('Looad','e-mobilitet','Hele DK','EM','Privat',True,False,False,False,False,False,'Voksende','Ladeoperatør. Ladebokse+abonnement.'),
        ('Circle K / Ladning','e-mobilitet','Hele DK','EM','Privat',True,False,False,False,False,False,'Landsdækkende','Tankstationer + lynladere til elbiler.'),
        ('Spirii','e-mobilitet','Hele DK','EM','Privat',True,False,False,False,False,False,'Platform','Ladeplatform/software til CPOer.'),
        ('E.ON Drive','e-mobilitet','Hele DK','EM','Privat/koncern',True,False,False,False,False,False,'Voksende','Ladeinfrastruktur.'),
        ('EWII Lading','e-mobilitet','Hele DK','EM','Selvejende',True,False,False,False,False,False,'~4.000 ladepunkter','EWIIs ladenetværk.'),
        ('Tesla Supercharger','e-mobilitet','Hele DK','EM','Privat',True,False,False,False,False,False,'DK-stationer','Lukket→åbent netværk.'),
    ]
    for row in companies:
        db.execute(
            """INSERT INTO companies (name,sector,city,tier,ejerform,has_el,has_gas,has_vand,has_varme,
               has_spildevand,has_affald,est_kunder,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            row)
    db.commit()


# ─── Audit helper ───
def log_audit(db, user_id, action, entity_type, entity_id, entity_name, details=None):
    user_name = None
    if user_id:
        row = db.execute("SELECT name FROM users WHERE id = %s", (user_id,)).fetchone()
        if row:
            user_name = row["name"]
    db.execute(
        "INSERT INTO audit_log (user_id, user_name, action, entity_type, entity_id, entity_name, details) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (user_id, user_name, action, entity_type, entity_id, entity_name,
         json.dumps(details, ensure_ascii=False, default=_json_default) if details else None))


# ─── Notification check ───
SCORE_DROP_POINTS = 15  # så meget skal scoren falde, før der notificeres igen for en kunde under grænsen


def check_score_notifications(db):
    """Notificerer kun ved ændringer: når en kunde falder under sin scoregrænse, eller scoren falder markant.
    Kunder der allerede står under grænsen giver ikke nye notifikationer, heller ikke efter de er læst."""
    thresholds = {row["rating"]: row["threshold"] for row in db.execute("SELECT rating, threshold FROM score_settings").fetchall()}
    state = {r["company_id"]: r for r in db.execute("SELECT * FROM score_alert_state").fetchall()}
    first_run = not state
    # Engangsoprydning efter den gamle logik, der lavede en notifikation pr. kunde under grænsen igen og igen.
    # Styres af et flag (ikke af first_run), så den også virker, hvis den gamle version nåede at lave dem igen.
    done = db.execute("SELECT value FROM app_settings WHERE key = 'score_notif_cleanup_v2'").fetchone()
    if not done:
        db.execute("UPDATE notifications SET is_read = TRUE WHERE type = 'score_drop' AND is_read = FALSE AND title IS NULL")
        db.execute("INSERT INTO app_settings (key, value) VALUES ('score_notif_cleanup_v2', %s) ON CONFLICT (key) DO NOTHING",
                   (date.today().isoformat(),))
    changed = []
    for s in calculate_all_scores(db):
        cid = s["company_id"]
        threshold = thresholds.get(s.get("rating") or "C", 30)
        below = s["score"] < threshold
        prev = state.get(cid)
        if prev is not None and not first_run:
            if below and not prev["below"]:
                changed.append((s, threshold, "under"))
            elif below and prev["last_score"] is not None and float(prev["last_score"]) - s["score"] >= SCORE_DROP_POINTS:
                changed.append((s, threshold, "fald"))
        if prev is None or prev["below"] != below or (prev["last_score"] is None) or abs(float(prev["last_score"]) - s["score"]) >= 1:
            db.execute("""INSERT INTO score_alert_state (company_id, below, last_score, updated_at) VALUES (%s,%s,%s,CURRENT_TIMESTAMP)
                          ON CONFLICT (company_id) DO UPDATE SET below = EXCLUDED.below, last_score = EXCLUDED.last_score,
                          updated_at = CURRENT_TIMESTAMP""", (cid, below, s["score"]))
    if len(changed) > 5:
        names = ", ".join(c[0]["company_name"] for c in changed[:6])
        db.execute("""INSERT INTO notifications (company_id, type, title, message, link) VALUES (NULL, 'score_drop', %s, %s, '#/companies')""",
                   (f"{len(changed)} kunder er faldet i relationsscore", f"Bl.a. {names}. Se virksomhederne og planlæg kontakt."))
    else:
        for s, threshold, why in changed:
            rating = s.get("rating") or "C"
            msg = (f"Scoren er faldet til {round(s['score'])}, under grænsen {threshold} for {rating}-kunder." if why == "under"
                   else f"Scoren er faldet med mere end {SCORE_DROP_POINTS} point til {round(s['score'])}.")
            db.execute("INSERT INTO notifications (company_id, type, message) VALUES (%s, 'score_drop', %s)", (s["company_id"], msg))
    db.commit()


# ─── Score ───
SCORE_WEIGHTS = {
    "kontaktfrekvens": 0.20,
    "kontaktdaekning": 0.15,
    "tidsforfald": 0.15,
    "linkedin": 0.10,
    "kendskab_behov": 0.15,
    "workshops": 0.10,
    "marketing": 0.15,
}

def score_color_100(score):
    if score >= 70:
        return "groen"
    elif score >= 40:
        return "gul"
    return "roed"

INTERACTION_POINTS = {
    "meeting_task": 25, "meeting": 15, "meeting_event": 8,
    "phone": 10, "email": 5, "linkedin": 3, "campaign": 2,
}
DECAY_BRACKETS = [(14, 1.0), (30, 0.85), (60, 0.65), (90, 0.45), (180, 0.25)]
DIVERSITY_TYPE_MAP = {"meeting_task": "meeting", "meeting_event": "meeting"}

def get_decay_factor(days):
    if days is None:
        return 0.10
    for max_days, factor in DECAY_BRACKETS:
        if days <= max_days:
            return factor
    return 0.10

def _calc_sub_scores(company, contacts_data, interactions, total_contacts):
    raw_points = sum(INTERACTION_POINTS.get(i["type"], 0) for i in interactions)
    interaction_points = min(raw_points, 60)
    s_kontaktfrekvens = round(min(interaction_points / 6, 10), 1)

    contacted_ids = set(i["contact_id"] for i in interactions if i["contact_id"])
    contacted_count = len(contacted_ids)
    coverage_pct = (contacted_count / total_contacts * 100) if total_contacts > 0 else 0
    channel_types = list(set(DIVERSITY_TYPE_MAP.get(i["type"], i["type"]) for i in interactions))
    diversity_bonus = min(len(channel_types), 4)
    s_kontaktdaekning = round(min(coverage_pct / 10 + diversity_bonus * 0.5, 10), 1)

    days_since_last = None
    if interactions:
        try:
            last_date = interactions[0]["date"]
            if isinstance(last_date, str):
                last_date = date.fromisoformat(last_date)
            days_since_last = (date.today() - last_date).days
        except (ValueError, TypeError):
            pass
    decay_factor = get_decay_factor(days_since_last)
    s_tidsforfald = round(decay_factor * 10, 1)

    li_connected = sum(1 for c in contacts_data
                       if c.get("linkedin_connected_systemate") or c.get("linkedin_connected_settl"))
    s_linkedin = round(min((li_connected / total_contacts * 10) if total_contacts > 0 else 0, 10), 1)

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
    db = get_db()
    try:
        company = db.execute(
            "SELECT * FROM companies WHERE id = %s", (company_id,)).fetchone()
        if not company:
            return None
        company = dict(company)

        am_name = None
        if company.get("account_manager_id"):
            am_row = db.execute("SELECT name FROM users WHERE id = %s",
                                (company["account_manager_id"],)).fetchone()
            if am_row:
                am_name = am_row["name"]

        contacts_data = [dict(r) for r in db.execute(
            "SELECT * FROM contacts WHERE company_id = %s", (company_id,)).fetchall()]
        total_contacts = len(contacts_data)
        contact_ids = [c["id"] for c in contacts_data]

        mx = {
            "importance": company.get("importance", "middel_vigtig"),
            "sales_stage": company.get("sales_stage", "tidlig_fase"),
            "score_kendskab_behov": company.get("score_kendskab_behov", 0) or 0,
            "score_workshops": company.get("score_workshops", 0) or 0,
            "score_marketing": company.get("score_marketing", 0) or 0,
        }
        empty_sub = {"kontaktfrekvens": 0, "kontaktdaekning": 0, "tidsforfald": 0,
                     "linkedin": 0, "kendskab_behov": 0, "workshops": 0, "marketing": 0}

        TASK_TYPE_MAP = {
            'moede': 'meeting', 'opkald': 'phone', 'demo': 'meeting',
            'kontrakt': 'meeting_task', 'opfølgning': 'phone',
            'tilbud': 'email', 'generelt': 'email',
        }

        interactions = [dict(r) for r in db.execute("""
            SELECT type, date, contact_id FROM interactions
            WHERE contact_id = ANY(%s) OR company_id = %s
            UNION ALL
            SELECT
                CASE category
                    WHEN 'moede' THEN 'meeting' WHEN 'opkald' THEN 'phone'
                    WHEN 'demo' THEN 'meeting' WHEN 'kontrakt' THEN 'meeting_task'
                    WHEN 'opfølgning' THEN 'phone' ELSE 'email'
                END AS type,
                COALESCE(due_date, created_at::date) AS date,
                contact_id
            FROM tasks WHERE company_id = %s
            ORDER BY date DESC""",
            (contact_ids, company_id, company_id)).fetchall()]

        if not interactions:
            return {"company_id": company["id"], "company_name": company["name"],
                    "sector": company["sector"], "tier": company.get("tier"),
                    "rating": company.get("rating", "C"), "account_manager_name": am_name,
                    "score": 0, "sub_scores": empty_sub, "interaction_points": 0,
                    "decay_factor": 0.10, "days_since_last": None, "total_contacts": total_contacts,
                    "contacted_count": 0, "total_interactions": 0, "channel_types": [],
                    "level": "kold", "coverage_pct": 0, "li_connected": 0,
                    "score_color": "roed", **mx}

        decay_penalty_rules = [dict(r) for r in db.execute(
            "SELECT * FROM score_decay_rules WHERE is_active = TRUE ORDER BY inactivity_days").fetchall()]

        sub_scores, score, details = _calc_sub_scores(company, contacts_data, interactions, total_contacts)

        penalty = 0
        if details["days_since_last"] is not None:
            for rule in decay_penalty_rules:
                if details["days_since_last"] >= rule["inactivity_days"]:
                    penalty = rule["penalty_points"]
        score = max(0, round(score - penalty, 1))
        level = "staerk" if score >= 80 else "god" if score >= 50 else "svag" if score >= 20 else "kold"

        return {"company_id": company["id"], "company_name": company["name"],
                "sector": company["sector"], "tier": company.get("tier"),
                "rating": company.get("rating", "C"), "account_manager_name": am_name,
                "score": score, "sub_scores": sub_scores,
                "interaction_points": details["interaction_points"],
                "decay_factor": details["decay_factor"], "days_since_last": details["days_since_last"],
                "total_contacts": total_contacts, "contacted_count": details["contacted_count"],
                "total_interactions": details["total_interactions"],
                "channel_types": details["channel_types"],
                "level": level, "penalty": penalty, "coverage_pct": details["coverage_pct"],
                "li_connected": details["li_connected"], "score_color": score_color_100(score), **mx}
    finally:
        db.close()


def calculate_all_scores(db):
    decay_penalty_rules = [dict(r) for r in db.execute(
        "SELECT * FROM score_decay_rules WHERE is_active = TRUE ORDER BY inactivity_days").fetchall()]

    companies = [dict(r) for r in db.execute(
        """SELECT c.*, u.name AS account_manager_name
           FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id
           ORDER BY c.name""").fetchall()]
    if not companies:
        return []

    contacts_by_company = {}
    for r in db.execute(
            "SELECT id, company_id, linkedin_connected_systemate, linkedin_connected_settl FROM contacts").fetchall():
        cid = r["company_id"]
        if cid not in contacts_by_company:
            contacts_by_company[cid] = []
        contacts_by_company[cid].append(dict(r))

    tags_by_company = {}
    for r in db.execute(
            """SELECT ct.company_id, t.id, t.name, t.color
               FROM company_tags ct JOIN tags t ON ct.tag_id = t.id ORDER BY t.name""").fetchall():
        cid = r["company_id"]
        if cid not in tags_by_company:
            tags_by_company[cid] = []
        tags_by_company[cid].append({"id": r["id"], "name": r["name"], "color": r["color"]})

    interactions_by_company = {}
    for r in db.execute("""
            SELECT i.type, i.date, i.contact_id, COALESCE(c.company_id, i.company_id) AS company_id
            FROM interactions i
            LEFT JOIN contacts c ON i.contact_id = c.id
            WHERE COALESCE(c.company_id, i.company_id) IS NOT NULL
            UNION ALL
            SELECT
                CASE t.category
                    WHEN 'moede' THEN 'meeting' WHEN 'opkald' THEN 'phone'
                    WHEN 'demo' THEN 'meeting' WHEN 'kontrakt' THEN 'meeting_task'
                    WHEN 'opfølgning' THEN 'phone' ELSE 'email'
                END AS type,
                COALESCE(t.due_date, t.created_at::date) AS date,
                t.contact_id, t.company_id
            FROM tasks t WHERE t.company_id IS NOT NULL
            ORDER BY date DESC""").fetchall():
        cid = r["company_id"]
        if cid not in interactions_by_company:
            interactions_by_company[cid] = []
        interactions_by_company[cid].append(dict(r))

    empty_sub = {"kontaktfrekvens": 0, "kontaktdaekning": 0, "tidsforfald": 0,
                 "linkedin": 0, "kendskab_behov": 0, "workshops": 0, "marketing": 0}
    results = []
    for company in companies:
        cid = company["id"]
        contacts_data = contacts_by_company.get(cid, [])
        total_contacts = len(contacts_data)
        interactions = interactions_by_company.get(cid, [])
        mx = {
            "importance": company.get("importance", "middel_vigtig"),
            "sales_stage": company.get("sales_stage", "tidlig_fase"),
            "score_kendskab_behov": company.get("score_kendskab_behov", 0) or 0,
            "score_workshops": company.get("score_workshops", 0) or 0,
            "score_marketing": company.get("score_marketing", 0) or 0,
        }
        if not interactions:
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

    today = date.today()
    existing_today = set()
    for r in db.execute("SELECT company_id FROM score_history WHERE recorded_at = %s", (today,)).fetchall():
        existing_today.add(r["company_id"])
    for r in results:
        if r["company_id"] not in existing_today:
            db.execute(
                "INSERT INTO score_history (company_id, score, level, recorded_at) VALUES (%s,%s,%s,%s)",
                (r["company_id"], r["score"], r["level"], today))
    db.commit()
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


# ─── Vercel handler ───
class handler(BaseHTTPRequestHandler):

    def _get_user_id(self):
        uid = self.headers.get("X-User-Id")
        if uid:
            try:
                return int(uid)
            except (ValueError, TypeError):
                pass
        return None

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)
            if path.startswith("/api/"):
                self._handle_api_get(path, params)
            else:
                self._error(404, "Not found")
        except Exception as e:
            self._error(500, str(e))

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                self._handle_file_upload(path)
            elif path.startswith("/api/"):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                self._handle_api_post(path, body)
        except Exception as e:
            self._error(500, str(e))

    def do_PUT(self):
        try:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            self._handle_api_put(parsed.path, body)
        except Exception as e:
            self._error(500, str(e))

    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            self._handle_api_delete(parsed.path)
        except Exception as e:
            self._error(500, str(e))

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-User-Id")

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=_json_default).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _no_content(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _error(self, status, msg):
        self._json_response({"detail": msg}, status)

    # ─── GET ───
    def _handle_api_get(self, path, params):
        db = get_db()
        try:
            if self._handle_ceo(db, 'GET', path, params, None, None):
                return
            if path == "/api/companies":
                q = """SELECT c.*, u.name AS account_manager_name
                       FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE 1=1"""
                p = []
                if "sector" in params:
                    q += " AND c.sector = %s"; p.append(params["sector"][0])
                if "tier" in params:
                    q += " AND c.tier = %s"; p.append(params["tier"][0])
                if "rating" in params:
                    q += " AND c.rating = %s"; p.append(params["rating"][0])
                if "account_manager_id" in params:
                    q += " AND c.account_manager_id = %s"; p.append(int(params["account_manager_id"][0]))
                if "search" in params:
                    q += " AND c.name ILIKE %s"; p.append("%{}%".format(params["search"][0]))
                if "tag_id" in params:
                    q += " AND c.id IN (SELECT company_id FROM company_tags WHERE tag_id = %s)"
                    p.append(int(params["tag_id"][0]))
                q += " ORDER BY c.name"
                rows = [dict(r) for r in db.execute(q, p or None).fetchall()]
                tags_map = {}
                for r in db.execute(
                        """SELECT ct.company_id, t.id, t.name, t.color
                           FROM company_tags ct JOIN tags t ON ct.tag_id = t.id ORDER BY t.name""").fetchall():
                    cid = r["company_id"]
                    if cid not in tags_map:
                        tags_map[cid] = []
                    tags_map[cid].append({"id": r["id"], "name": r["name"], "color": r["color"]})
                groups_map = {}
                for r in db.execute("""SELECT m.company_id, g.id, g.name FROM company_memberships m
                                       JOIN companies g ON m.group_id = g.id ORDER BY g.name""").fetchall():
                    groups_map.setdefault(r["company_id"], []).append({"id": r["id"], "name": r["name"]})
                for row in rows:
                    row["tags"] = tags_map.get(row["id"], [])
                    row["memberships"] = groups_map.get(row["id"], [])
                self._json_response(rows)

            elif path.startswith("/api/companies/") and path.endswith("/full") and path.count("/") == 4:
                cid = int(path.split("/")[-2])
                company = db.execute(
                    """SELECT c.*, u.name AS account_manager_name
                       FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = %s""",
                    (cid,)).fetchone()
                if not company:
                    return self._error(404, "Virksomhed ikke fundet")
                contacts = [dict(r) for r in db.execute(
                    "SELECT * FROM contacts WHERE company_id = %s ORDER BY last_name, first_name", (cid,)).fetchall()]
                score = calculate_company_score(cid)
                interactions = [dict(r) for r in db.execute(
                    """SELECT i.*, ct.first_name || ' ' || ct.last_name AS contact_name, u.name AS user_name
                       FROM interactions i LEFT JOIN contacts ct ON i.contact_id = ct.id
                       LEFT JOIN users u ON i.user_id = u.id
                       WHERE (ct.company_id = %s OR i.company_id = %s) ORDER BY i.date DESC""",
                    (cid, cid)).fetchall()]
                emails = [dict(r) for r in db.execute(
                    """SELECT e.* FROM emails e LEFT JOIN interactions i ON e.interaction_id = i.id
                       LEFT JOIN contacts ct ON i.contact_id = ct.id WHERE ct.company_id = %s ORDER BY e.date_sent DESC""",
                    (cid,)).fetchall()]
                users = [dict(r) for r in db.execute(
                    "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY name").fetchall()]
                tasks = [dict(r) for r in db.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id
                       WHERE t.company_id = %s
                       ORDER BY CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                       t.due_date ASC""", (cid,)).fetchall()]
                audit = [dict(r) for r in db.execute(
                    "SELECT * FROM audit_log WHERE entity_type = 'company' AND entity_id = %s ORDER BY created_at DESC LIMIT 20",
                    (cid,)).fetchall()]
                li_activities = [dict(r) for r in db.execute(
                    """SELECT la.*, ct.first_name || ' ' || ct.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_activities la JOIN contacts ct ON la.contact_id = ct.id
                       JOIN companies co ON ct.company_id = co.id LEFT JOIN users u ON la.observed_by = u.id
                       WHERE co.id = %s ORDER BY la.activity_date DESC LIMIT 50""", (cid,)).fetchall()]
                li_engagements = [dict(r) for r in db.execute(
                    """SELECT le.*, ct.first_name || ' ' || ct.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_engagements le JOIN contacts ct ON le.contact_id = ct.id
                       JOIN companies co ON ct.company_id = co.id LEFT JOIN users u ON le.observed_by = u.id
                       WHERE co.id = %s ORDER BY le.observed_date DESC LIMIT 50""", (cid,)).fetchall()]
                company_tags = [dict(r) for r in db.execute(
                    "SELECT t.* FROM tags t JOIN company_tags ct ON t.id = ct.tag_id WHERE ct.company_id = %s ORDER BY t.name",
                    (cid,)).fetchall()]
                for c in contacts:
                    c["tags"] = [dict(r) for r in db.execute(
                        "SELECT t.* FROM tags t JOIN contact_tags ct ON t.id = ct.tag_id WHERE ct.contact_id = %s ORDER BY t.name",
                        (c["id"],)).fetchall()]
                all_tags = [dict(r) for r in db.execute("SELECT * FROM tags ORDER BY name").fetchall()]
                tenders = [dict(r) for r in db.execute(
                    """SELECT t.*, u.name AS responsible_name, g.name AS via_group_name
                       FROM tenders t LEFT JOIN users u ON t.responsible_id = u.id
                       LEFT JOIN companies g ON t.via_group_id = g.id
                       WHERE t.company_id = %s ORDER BY t.created_at DESC""", (cid,)).fetchall()]
                memberships = [dict(r) for r in db.execute(
                    """SELECT g.id, g.name FROM company_memberships m JOIN companies g ON m.group_id = g.id
                       WHERE m.company_id = %s ORDER BY g.name""", (cid,)).fetchall()]
                members = [dict(r) for r in db.execute(
                    """SELECT c.id, c.name, c.city,
                              (SELECT COUNT(*) FROM tenders t WHERE t.company_id = c.id AND t.status NOT IN ('won','lost','dropped')) AS active_tenders,
                              (SELECT COUNT(*) FROM tenders t WHERE t.company_id = c.id AND t.via_group_id = %s AND t.status NOT IN ('won','lost','dropped')) AS via_group_tenders
                       FROM company_memberships m JOIN companies c ON m.company_id = c.id
                       WHERE m.group_id = %s ORDER BY c.name""", (cid, cid)).fetchall()]
                company_notes = [dict(r) for r in db.execute(
                    "SELECT * FROM company_notes WHERE company_id = %s ORDER BY created_at DESC", (cid,)).fetchall()]
                self._json_response({
                    "company": dict(company), "contacts": contacts, "score": score,
                    "interactions": interactions, "emails": emails, "users": users,
                    "tasks": tasks, "audit_log": audit,
                    "linkedin_activities": li_activities, "linkedin_engagements": li_engagements,
                    "company_tags": company_tags, "all_tags": all_tags, "tenders": tenders,
                    "company_notes": company_notes, "memberships": memberships, "members": members
                })

            elif path.startswith("/api/companies/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = db.execute(
                    """SELECT c.*, u.name AS account_manager_name
                       FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = %s""",
                    (cid,)).fetchone()
                if not row:
                    return self._error(404, "Virksomhed ikke fundet")
                self._json_response(dict(row))

            elif path == "/api/contacts":
                q = "SELECT * FROM contacts WHERE 1=1"
                p = []
                if "company_id" in params:
                    q += " AND company_id = %s"; p.append(int(params["company_id"][0]))
                if "search" in params:
                    s = "%{}%".format(params["search"][0])
                    q += " AND (first_name ILIKE %s OR last_name ILIKE %s OR email ILIKE %s)"; p.extend([s]*3)
                q += " ORDER BY last_name, first_name"
                self._json_response([dict(r) for r in db.execute(q, p or None).fetchall()])

            elif path.startswith("/api/contacts/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = db.execute("SELECT * FROM contacts WHERE id = %s", (cid,)).fetchone()
                if not row:
                    return self._error(404, "Kontakt ikke fundet")
                self._json_response(dict(row))

            elif path == "/api/interactions":
                q = """SELECT i.*, c.first_name || ' ' || c.last_name AS contact_name, u.name AS user_name
                       FROM interactions i LEFT JOIN contacts c ON i.contact_id = c.id
                       LEFT JOIN users u ON i.user_id = u.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND i.contact_id = %s"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND c.company_id = %s"; p.append(int(params["company_id"][0]))
                if "type" in params:
                    q += " AND i.type = %s"; p.append(params["type"][0])
                q += " ORDER BY i.date DESC"
                self._json_response([dict(r) for r in db.execute(q, p or None).fetchall()])

            elif path == "/api/users":
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY name").fetchall()])

            elif path == "/api/emails":
                q = """SELECT e.* FROM emails e LEFT JOIN interactions i ON e.interaction_id = i.id
                       LEFT JOIN contacts c ON i.contact_id = c.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND i.contact_id = %s"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND c.company_id = %s"; p.append(int(params["company_id"][0]))
                q += " ORDER BY e.date_sent DESC"
                self._json_response([dict(r) for r in db.execute(q, p or None).fetchall()])

            elif path.startswith("/api/emails/") and path.count("/") == 3:
                eid = int(path.split("/")[-1])
                row = db.execute("SELECT * FROM emails WHERE id = %s", (eid,)).fetchone()
                if not row:
                    return self._error(404, "Email ikke fundet")
                self._json_response(dict(row))

            elif path == "/api/search":
                q = params.get("q", [""])[0]
                if not q or len(q) < 2:
                    return self._json_response({"companies": [], "contacts": []})
                term = "%{}%".format(q)
                companies = [dict(r) for r in db.execute(
                    """SELECT DISTINCT co.id, co.name, co.sector, co.city, co.rating FROM companies co
                       LEFT JOIN company_tags ct ON co.id = ct.company_id
                       LEFT JOIN tags t ON ct.tag_id = t.id
                       WHERE co.name ILIKE %s OR co.city ILIKE %s OR t.name ILIKE %s
                       ORDER BY co.name LIMIT 10""", (term, term, term)).fetchall()]
                contacts = [dict(r) for r in db.execute(
                    """SELECT DISTINCT c.id, c.first_name, c.last_name, c.title, c.email, c.company_id, co.name AS company_name
                       FROM contacts c JOIN companies co ON c.company_id = co.id
                       LEFT JOIN contact_tags cta ON c.id = cta.contact_id
                       LEFT JOIN tags t ON cta.tag_id = t.id
                       WHERE c.first_name ILIKE %s OR c.last_name ILIKE %s OR c.email ILIKE %s
                       OR (c.first_name || ' ' || c.last_name) ILIKE %s OR t.name ILIKE %s
                       ORDER BY c.last_name LIMIT 10""", (term, term, term, term, term)).fetchall()]
                self._json_response({"companies": companies, "contacts": contacts})

            elif path == "/api/tasks":
                q = """SELECT t.*, c.name AS company_name,
                       u1.name AS assigned_to_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id WHERE 1=1"""
                p = []
                if "company_id" in params:
                    q += " AND t.company_id = %s"; p.append(int(params["company_id"][0]))
                if "assigned_to" in params:
                    q += " AND t.assigned_to = %s"; p.append(int(params["assigned_to"][0]))
                if "status" in params:
                    q += " AND t.status = %s"; p.append(params["status"][0])
                if "category" in params:
                    q += " AND t.category = %s"; p.append(params["category"][0])
                if "area" in params:
                    q += " AND COALESCE(t.area, 'salg') = %s"; p.append(params["area"][0])
                if "overdue" in params:
                    q += " AND t.due_date < CURRENT_DATE AND t.status != 'done'"
                q += " ORDER BY CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, t.due_date ASC NULLS LAST, t.created_at DESC"
                self._json_response([dict(r) for r in db.execute(q, p or None).fetchall()])

            elif path == "/api/tasks/summary":
                rows = db.execute("SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status").fetchall()
                summary = {"open": 0, "in_progress": 0, "done": 0}
                for r in rows:
                    summary[r["status"]] = r["cnt"]
                overdue = db.execute(
                    "SELECT COUNT(*) AS cnt FROM tasks WHERE due_date < CURRENT_DATE AND status != 'done'").fetchone()["cnt"]
                this_week = db.execute(
                    "SELECT COUNT(*) AS cnt FROM tasks WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days' AND status != 'done'").fetchone()["cnt"]
                summary["overdue"] = overdue
                summary["this_week"] = this_week
                self._json_response(summary)

            elif path.startswith("/api/tasks/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM task_notes WHERE task_id = %s ORDER BY created_at DESC", (tid,)).fetchall()])

            elif path.startswith("/api/companies/") and path.endswith("/notes") and path.count("/") == 4:
                cid = int(path.split("/")[-2])
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM company_notes WHERE company_id = %s ORDER BY created_at DESC", (cid,)).fetchall()])

            elif path.startswith("/api/tasks/") and path.endswith("/history"):
                tid = int(path.split("/")[-2])
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM audit_log WHERE entity_type = 'task' AND entity_id = %s ORDER BY created_at DESC",
                    (tid,)).fetchall()])

            elif path.startswith("/api/tasks/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = db.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       WHERE t.id = %s""", (tid,)).fetchone()
                if not row:
                    return self._error(404, "Sag ikke fundet")
                self._json_response(dict(row))

            elif path.startswith("/api/tenders/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM tender_notes WHERE tender_id = %s ORDER BY created_at DESC", (tid,)).fetchall()])

            elif path.startswith("/api/tenders/") and path.endswith("/history"):
                tid = int(path.split("/")[-2])
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM audit_log WHERE entity_type = 'tender' AND entity_id = %s ORDER BY created_at DESC",
                    (tid,)).fetchall()])

            elif path == "/api/audit-log":
                q = "SELECT * FROM audit_log WHERE 1=1"
                p = []
                if "entity_type" in params:
                    q += " AND entity_type = %s"; p.append(params["entity_type"][0])
                if "entity_id" in params:
                    q += " AND entity_id = %s"; p.append(int(params["entity_id"][0]))
                if "user_id" in params:
                    q += " AND user_id = %s"; p.append(int(params["user_id"][0]))
                q += " ORDER BY created_at DESC"
                limit = int(params.get("limit", ["50"])[0])
                q += " LIMIT %s"; p.append(limit)
                self._json_response([dict(r) for r in db.execute(q, p).fetchall()])

            elif path == "/api/notifications":
                q = "SELECT n.*, COALESCE(n.title, c.name) AS company_name FROM notifications n LEFT JOIN companies c ON n.company_id = c.id WHERE 1=1"
                p = []
                if "is_read" in params:
                    val = params["is_read"][0]
                    q += " AND n.is_read = %s"; p.append(val == "1" or val == "true")
                # Ulæste svar fra ledere står altid øverst, så de ikke drukner i score-notifikationer
                q += " ORDER BY n.is_read ASC, (n.type = 'report') DESC, n.created_at DESC LIMIT 50"
                self._json_response([dict(r) for r in db.execute(q, p or None).fetchall()])

            elif path == "/api/notifications/count":
                cnt = db.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE is_read = FALSE").fetchone()["cnt"]
                self._json_response({"unread": cnt})

            elif path == "/api/notifications/check":
                check_score_notifications(db)
                cnt = db.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE is_read = FALSE").fetchone()["cnt"]
                self._json_response({"checked": True, "unread": cnt})

            elif path == "/api/settings/score-thresholds":
                rows = db.execute("SELECT rating, threshold FROM score_settings ORDER BY rating").fetchall()
                self._json_response({r["rating"]: r["threshold"] for r in rows})

            elif path == "/api/settings/decay-rules":
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM score_decay_rules ORDER BY inactivity_days").fetchall()])

            elif path == "/api/linkedin-activities":
                q = """SELECT la.*, c.first_name || ' ' || c.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_activities la JOIN contacts c ON la.contact_id = c.id
                       JOIN companies co ON c.company_id = co.id
                       LEFT JOIN users u ON la.observed_by = u.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND la.contact_id = %s"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND co.id = %s"; p.append(int(params["company_id"][0]))
                q += " ORDER BY la.activity_date DESC LIMIT 50"
                self._json_response([dict(r) for r in db.execute(q, p or None).fetchall()])

            elif path == "/api/linkedin-engagements":
                q = """SELECT le.*, c.first_name || ' ' || c.last_name AS contact_name, u.name AS observed_by_name,
                       co.id AS company_id, co.name AS company_name
                       FROM linkedin_engagements le JOIN contacts c ON le.contact_id = c.id
                       JOIN companies co ON c.company_id = co.id
                       LEFT JOIN users u ON le.observed_by = u.id WHERE 1=1"""
                p = []
                if "contact_id" in params:
                    q += " AND le.contact_id = %s"; p.append(int(params["contact_id"][0]))
                if "company_id" in params:
                    q += " AND co.id = %s"; p.append(int(params["company_id"][0]))
                if "company_page" in params:
                    q += " AND le.company_page = %s"; p.append(params["company_page"][0])
                q += " ORDER BY le.observed_date DESC LIMIT 50"
                self._json_response([dict(r) for r in db.execute(q, p or None).fetchall()])

            elif path == "/api/score-history/aggregate":
                rows = db.execute("""
                    SELECT recorded_at AS date,
                           ROUND(AVG(score)::numeric, 1) AS avg_score,
                           COUNT(*) AS total_companies,
                           SUM(CASE WHEN level='staerk' THEN 1 ELSE 0 END) AS strong,
                           SUM(CASE WHEN level='god' THEN 1 ELSE 0 END) AS good,
                           SUM(CASE WHEN level='svag' THEN 1 ELSE 0 END) AS weak,
                           SUM(CASE WHEN level='kold' THEN 1 ELSE 0 END) AS cold
                    FROM score_history GROUP BY recorded_at ORDER BY recorded_at ASC LIMIT 90
                """).fetchall()
                self._json_response([dict(r) for r in rows])

            elif path == "/api/dashboard/all":
                scores = calculate_all_scores(db)
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
                all_tags = [dict(r) for r in db.execute("SELECT * FROM tags ORDER BY name").fetchall()]

                if "from_date" in params:
                    from_date = params["from_date"][0]
                    date_cutoff = f"'{from_date}'"
                else:
                    days = max(1, min(365, int(params.get("days", ["14"])[0])))
                    date_cutoff = f"CURRENT_DATE - INTERVAL '{days} days'"

                recent_activities = [dict(r) for r in db.execute(f"""
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
                    FROM tasks t JOIN companies co ON t.company_id = co.id
                    LEFT JOIN contacts ct ON t.contact_id = ct.id
                    LEFT JOIN users u ON t.assigned_to = u.id
                    WHERE t.created_at >= {date_cutoff} OR (t.completed_at IS NOT NULL AND t.completed_at >= {date_cutoff})
                    UNION ALL
                    SELECT 'task_note' AS source, tn.id, t.id AS entity_id,
                           tn.created_at AS activity_date, 'note' AS sub_type,
                           tn.content AS subject,
                           co.id AS company_id, co.name AS company_name,
                           NULL AS contact_name, tn.user_name AS user_name
                    FROM task_notes tn JOIN tasks t ON tn.task_id = t.id
                    JOIN companies co ON t.company_id = co.id
                    WHERE tn.created_at >= {date_cutoff}
                    UNION ALL
                    SELECT 'tender_note' AS source, tn.id, t.id AS entity_id,
                           tn.created_at AS activity_date, 'note' AS sub_type,
                           tn.content AS subject,
                           co.id AS company_id, co.name AS company_name,
                           NULL AS contact_name, tn.user_name AS user_name
                    FROM tender_notes tn JOIN tenders t ON tn.tender_id = t.id
                    JOIN companies co ON t.company_id = co.id
                    WHERE tn.created_at >= {date_cutoff}
                    UNION ALL
                    SELECT 'tender' AS source, al.id, t.id AS entity_id,
                           al.created_at AS activity_date, al.action AS sub_type,
                           CASE al.action
                               WHEN 'update' THEN t.title || ' → ' || COALESCE((al.details::json)->>'status', '')
                               ELSE t.title
                           END AS subject,
                           co.id AS company_id, co.name AS company_name,
                           NULL AS contact_name, al.user_name AS user_name
                    FROM audit_log al JOIN tenders t ON al.entity_id = t.id
                    JOIN companies co ON t.company_id = co.id
                    WHERE al.entity_type = 'tender' AND al.action IN ('create', 'update')
                    AND al.created_at >= {date_cutoff}
                    UNION ALL
                    SELECT 'contact' AS source, al.id, ct.company_id AS entity_id,
                           al.created_at AS activity_date, 'create' AS sub_type,
                           al.entity_name AS subject,
                           co.id AS company_id, co.name AS company_name,
                           al.entity_name AS contact_name, al.user_name AS user_name
                    FROM audit_log al JOIN contacts ct ON al.entity_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    WHERE al.entity_type = 'contact' AND al.action = 'create'
                    AND al.created_at >= {date_cutoff}
                    UNION ALL
                    SELECT 'linkedin_activity' AS source, la.id, la.id AS entity_id,
                           la.activity_date, la.activity_type AS sub_type,
                           la.content_summary AS subject, co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM linkedin_activities la JOIN contacts ct ON la.contact_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN users u ON la.observed_by = u.id
                    WHERE la.activity_date >= {date_cutoff}
                    UNION ALL
                    SELECT 'linkedin_engagement' AS source, le.id, le.id AS entity_id,
                           le.observed_date AS activity_date,
                           le.engagement_type AS sub_type, le.notes AS subject,
                           co.id AS company_id, co.name AS company_name,
                           ct.first_name||' '||ct.last_name AS contact_name, u.name AS user_name
                    FROM linkedin_engagements le JOIN contacts ct ON le.contact_id = ct.id
                    JOIN companies co ON ct.company_id = co.id
                    LEFT JOIN users u ON le.observed_by = u.id
                    WHERE le.observed_date >= {date_cutoff}
                    ORDER BY activity_date DESC LIMIT 100
                """).fetchall()]

                prev_scores = {}
                for r in db.execute("""
                    SELECT sh.company_id, sh.score FROM score_history sh
                    INNER JOIN (
                        SELECT company_id, MAX(recorded_at) AS max_date
                        FROM score_history WHERE recorded_at < CURRENT_DATE GROUP BY company_id
                    ) latest ON sh.company_id = latest.company_id AND sh.recorded_at = latest.max_date
                """).fetchall():
                    prev_scores[r["company_id"]] = r["score"]
                for s in scores:
                    s["previous_score"] = prev_scores.get(s["company_id"])

                active_tenders = [dict(r) for r in db.execute("""
                    SELECT t.id, t.title, t.status, t.deadline, t.estimated_value, t.purchase_route,
                           co.id AS company_id, co.name AS company_name, g.name AS via_group_name,
                           u.name AS responsible_name,
                           (SELECT COUNT(*) FROM tender_sections ts WHERE ts.tender_id = t.id) AS total_sections,
                           (SELECT COUNT(*) FROM tender_sections ts WHERE ts.tender_id = t.id AND ts.status = 'approved') AS approved_sections
                    FROM tenders t JOIN companies co ON t.company_id = co.id
                    LEFT JOIN companies g ON t.via_group_id = g.id
                    LEFT JOIN users u ON t.responsible_id = u.id
                    WHERE t.status NOT IN ('won', 'lost', 'dropped')
                    ORDER BY t.deadline ASC NULLS LAST
                """).fetchall()]

                active_tasks = [dict(r) for r in db.execute("""
                    SELECT t.id, t.title, t.category, t.status, t.priority, t.due_date,
                           COALESCE(t.area, 'salg') AS area,
                           co.id AS company_id, co.name AS company_name,
                           u.name AS assigned_to_name
                    FROM tasks t JOIN companies co ON t.company_id = co.id
                    LEFT JOIN users u ON t.assigned_to = u.id
                    WHERE t.status != 'done'
                    ORDER BY
                        CASE t.priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                        t.due_date ASC NULLS LAST,
                        t.id DESC
                """).fetchall()]

                tender_summary = [dict(r) for r in db.execute(
                    "SELECT status, estimated_value, deadline FROM tenders").fetchall()]

                tasks_done_30d = [dict(r) for r in db.execute("""
                    SELECT COALESCE(area, 'salg') AS area, COUNT(*) AS cnt FROM tasks
                    WHERE status = 'done' AND completed_at >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY COALESCE(area, 'salg')
                """).fetchall()]

                self._json_response({"scores": scores, "stats": stats, "all_tags": all_tags,
                                     "recent_activities": recent_activities, "active_tenders": active_tenders,
                                     "active_tasks": active_tasks, "tender_summary": tender_summary,
                                     "tasks_done_30d": tasks_done_30d})

            elif path == "/api/dashboard/scores":
                scores = calculate_all_scores(db)
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
                scores = calculate_all_scores(db)
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

            elif path == "/api/tags":
                rows = db.execute(
                    """SELECT t.*,
                       (SELECT COUNT(*) FROM company_tags WHERE tag_id = t.id) +
                       (SELECT COUNT(*) FROM contact_tags WHERE tag_id = t.id) AS usage_count
                       FROM tags t ORDER BY t.name""").fetchall()
                self._json_response([dict(r) for r in rows])

            elif path == "/api/tenders":
                q = """SELECT t.*, c.name AS company_name, g.name AS via_group_name,
                       u1.name AS responsible_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tenders t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN companies g ON t.via_group_id = g.id
                       LEFT JOIN users u1 ON t.responsible_id = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id WHERE 1=1"""
                p = []
                if "company_id" in params:
                    q += " AND t.company_id = %s"; p.append(int(params["company_id"][0]))
                if "status" in params:
                    q += " AND t.status = %s"; p.append(params["status"][0])
                q += " ORDER BY t.deadline ASC NULLS LAST, t.created_at DESC"
                tenders = [dict(r) for r in db.execute(q, p or None).fetchall()]
                for tender in tenders:
                    sections = db.execute(
                        "SELECT status FROM tender_sections WHERE tender_id = %s", (tender["id"],)).fetchall()
                    total = len(sections)
                    done = sum(1 for s in sections if s["status"] == "approved")
                    tender["section_count"] = total
                    tender["sections_approved"] = done
                    tender["progress"] = round((done / total * 100) if total > 0 else 0)
                self._json_response(tenders)

            elif path.startswith("/api/tenders/") and path.endswith("/full"):
                tid = int(path.split("/")[-2])
                tender = db.execute(
                    """SELECT t.*, c.name AS company_name, g.name AS via_group_name,
                       u1.name AS responsible_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tenders t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN companies g ON t.via_group_id = g.id
                       LEFT JOIN users u1 ON t.responsible_id = u1.id
                       LEFT JOIN users u2 ON t.created_by = u2.id
                       LEFT JOIN contacts ct ON t.contact_id = ct.id
                       WHERE t.id = %s""", (tid,)).fetchone()
                if not tender:
                    return self._error(404, "Tilbud ikke fundet")
                sections = [dict(r) for r in db.execute(
                    """SELECT ts.*, u1.name AS responsible_name, u2.name AS reviewer_name
                       FROM tender_sections ts
                       LEFT JOIN users u1 ON ts.responsible_id = u1.id
                       LEFT JOIN users u2 ON ts.reviewer_id = u2.id
                       WHERE ts.tender_id = %s ORDER BY ts.sort_order, ts.id""", (tid,)).fetchall()]
                users = [dict(r) for r in db.execute(
                    "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY name").fetchall()]
                companies = [dict(r) for r in db.execute(
                    "SELECT id, name FROM companies ORDER BY name").fetchall()]
                self._json_response({"tender": dict(tender), "sections": sections,
                                     "users": users, "companies": companies})

            elif path == "/api/tender-templates":
                templates = [dict(r) for r in db.execute(
                    "SELECT * FROM tender_templates ORDER BY is_default DESC, name").fetchall()]
                for t in templates:
                    t["section_count"] = db.execute(
                        "SELECT COUNT(*) AS cnt FROM tender_template_sections WHERE template_id = %s",
                        (t["id"],)).fetchone()["cnt"]
                self._json_response(templates)

            elif path.startswith("/api/tender-templates/") and path.count("/") == 3:
                tmpl_id = int(path.split("/")[-1])
                tmpl = db.execute("SELECT * FROM tender_templates WHERE id = %s", (tmpl_id,)).fetchone()
                if not tmpl:
                    return self._error(404, "Skabelon ikke fundet")
                sections = [dict(r) for r in db.execute(
                    "SELECT * FROM tender_template_sections WHERE template_id = %s ORDER BY sort_order",
                    (tmpl_id,)).fetchall()]
                self._json_response({"template": dict(tmpl), "sections": sections})

            elif path.startswith("/api/tender-sections/") and path.endswith("/audit"):
                sid = int(path.split("/")[-2])
                self._json_response([dict(r) for r in db.execute(
                    "SELECT * FROM tender_section_audit WHERE section_id = %s ORDER BY created_at DESC",
                    (sid,)).fetchall()])

            else:
                self._error(404, "Endpoint not found")
        finally:
            db.close()

    # ─── POST ───
    def _handle_api_post(self, path, body):
        db = get_db()
        uid = self._get_user_id()
        try:
            if self._handle_ceo(db, 'POST', path, {}, body, uid):
                return
            if path == "/api/companies":
                cur = db.execute(
                    """INSERT INTO companies (name,sector,address,city,zip_code,website,notes,rating,account_manager_id,
                       importance,sales_stage,score_cxo,score_kontaktfrekvens,score_kontaktbredde,score_kendskab,score_historik,
                       tier,ejerform,has_el,has_gas,has_vand,has_varme,has_spildevand,has_affald,est_kunder)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    (body["name"], body.get("sector"), body.get("address"), body.get("city"),
                     body.get("zip_code"), body.get("website"), body.get("notes"),
                     body.get("rating","C"), body.get("account_manager_id"),
                     body.get("importance","middel_vigtig"), body.get("sales_stage","tidlig_fase"),
                     body.get("score_cxo",0), body.get("score_kontaktfrekvens",0),
                     body.get("score_kontaktbredde",0), body.get("score_kendskab",0), body.get("score_historik",0),
                     body.get("tier"), body.get("ejerform"),
                     bool(body.get("has_el",False)), bool(body.get("has_gas",False)), bool(body.get("has_vand",False)),
                     bool(body.get("has_varme",False)), bool(body.get("has_spildevand",False)), bool(body.get("has_affald",False)),
                     body.get("est_kunder")))
                new_id = cur.fetchone()["id"]
                db.commit()
                row = db.execute(
                    "SELECT c.*, u.name AS account_manager_name FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = %s",
                    (new_id,)).fetchone()
                log_audit(db, uid, "create", "company", new_id, body["name"])
                db.commit()
                self._json_response(dict(row), 201)

            elif path == "/api/contacts":
                cur = db.execute(
                    """INSERT INTO contacts (company_id,first_name,last_name,title,email,phone,linkedin_url,
                       on_linkedin_list,notes,linkedin_connected_systemate,linkedin_connected_settl)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["company_id"], body["first_name"], body["last_name"], body.get("title"),
                     body.get("email"), body.get("phone"), body.get("linkedin_url"),
                     bool(body.get("on_linkedin_list",False)), body.get("notes"),
                     bool(body.get("linkedin_connected_systemate",False)), bool(body.get("linkedin_connected_settl",False))))
                new_id = cur.fetchone()["id"]
                db.commit()
                row = db.execute("SELECT * FROM contacts WHERE id = %s", (new_id,)).fetchone()
                log_audit(db, uid, "create", "contact", new_id, "{} {}".format(body["first_name"], body["last_name"]))
                db.commit()
                self._json_response(dict(row), 201)

            elif path == "/api/interactions":
                contact_id = body.get("contact_id") or None
                company_id = body.get("company_id") or None
                if contact_id and not company_id:
                    row = db.execute("SELECT company_id FROM contacts WHERE id = %s", (contact_id,)).fetchone()
                    if row: company_id = row["company_id"]
                cur = db.execute(
                    "INSERT INTO interactions (contact_id,company_id,user_id,type,date,subject,notes) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (contact_id, company_id, body.get("user_id"), body["type"], body["date"],
                     body.get("subject"), body.get("notes")))
                new_id = cur.fetchone()["id"]
                db.commit()
                row = db.execute(
                    """SELECT i.*, c.first_name||' '||c.last_name AS contact_name, u.name AS user_name
                       FROM interactions i LEFT JOIN contacts c ON i.contact_id=c.id LEFT JOIN users u ON i.user_id=u.id
                       WHERE i.id=%s""", (new_id,)).fetchone()
                log_audit(db, uid, "create", "interaction", new_id, body.get("subject", body["type"]),
                          {"type": body["type"], "contact_id": contact_id})
                db.commit()
                self._json_response(dict(row), 201)

            elif path == "/api/users":
                existing = db.execute("SELECT id FROM users WHERE email = %s", (body["email"],)).fetchone()
                if existing:
                    return self._error(409, "Email allerede i brug")
                cur = db.execute(
                    "INSERT INTO users (name,email,role) VALUES (%s,%s,%s) RETURNING id",
                    (body["name"], body["email"], body.get("role","user")))
                new_id = cur.fetchone()["id"]
                db.commit()
                row = db.execute("SELECT * FROM users WHERE id = %s", (new_id,)).fetchone()
                log_audit(db, uid, "create", "user", new_id, body["name"])
                db.commit()
                self._json_response(dict(row), 201)

            elif path.startswith("/api/users/") and path.endswith("/restore"):
                uid_restore = int(path.split("/")[-2])
                db.execute("UPDATE users SET deleted_at = NULL WHERE id = %s", (uid_restore,))
                db.commit()
                row = db.execute("SELECT * FROM users WHERE id = %s", (uid_restore,)).fetchone()
                if row:
                    log_audit(db, uid, "restore", "user", uid_restore, row["name"])
                    db.commit()
                self._json_response(dict(row) if row else {})

            elif path == "/api/tasks":
                cur = db.execute(
                    """INSERT INTO tasks (company_id,contact_id,assigned_to,created_by,category,
                       title,description,status,priority,due_date,area) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["company_id"], body.get("contact_id"), body.get("assigned_to"),
                     uid, body["category"], body["title"], body.get("description"),
                     body.get("status","open"), body.get("priority","normal"), body.get("due_date"),
                     body.get("area") or "salg"))
                new_id = cur.fetchone()["id"]
                db.commit()
                row = db.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id LEFT JOIN users u2 ON t.created_by = u2.id
                       WHERE t.id = %s""", (new_id,)).fetchone()
                log_audit(db, uid, "create", "task", new_id, body["title"],
                          {"category": body["category"], "company_id": body["company_id"]})
                db.commit()
                self._json_response(dict(row), 201)

            elif path.startswith("/api/companies/") and path.endswith("/notes") and path.count("/") == 4:
                cid = int(path.split("/")[-2])
                user_name = None
                if uid:
                    ur = db.execute("SELECT name FROM users WHERE id=%s", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                cur = db.execute(
                    "INSERT INTO company_notes (company_id,user_id,user_name,content) VALUES (%s,%s,%s,%s) RETURNING id",
                    (cid, uid, user_name, body.get("content","")))
                new_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "add_note", "company", cid, body.get("content","")[:80])
                db.commit()
                row = db.execute("SELECT * FROM company_notes WHERE id = %s", (new_id,)).fetchone()
                self._json_response(dict(row), 201)

            elif path.startswith("/api/tasks/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                user_name = None
                if uid:
                    ur = db.execute("SELECT name FROM users WHERE id=%s", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                cur = db.execute(
                    "INSERT INTO task_notes (task_id,user_id,user_name,content,note_type,metadata) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tid, uid, user_name, body.get("content",""), body.get("note_type","note"), body.get("metadata")))
                new_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "add_note", "task", tid, body.get("content","")[:80])
                db.commit()
                row = db.execute("SELECT * FROM task_notes WHERE id = %s", (new_id,)).fetchone()
                self._json_response(dict(row), 201)

            elif path.startswith("/api/tenders/") and path.endswith("/notes"):
                tid = int(path.split("/")[-2])
                user_name = None
                if uid:
                    ur = db.execute("SELECT name FROM users WHERE id=%s", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                cur = db.execute(
                    "INSERT INTO tender_notes (tender_id,user_id,user_name,content) VALUES (%s,%s,%s,%s) RETURNING id",
                    (tid, uid, user_name, body.get("content","")))
                new_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "add_note", "tender", tid, body.get("content","")[:80])
                db.commit()
                row = db.execute("SELECT * FROM tender_notes WHERE id = %s", (new_id,)).fetchone()
                self._json_response(dict(row), 201)

            elif path == "/api/linkedin-activities":
                cur = db.execute(
                    """INSERT INTO linkedin_activities (contact_id,activity_type,content_summary,
                       linkedin_post_url,observed_by,activity_date) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["contact_id"], body["activity_type"], body.get("content_summary"),
                     body.get("linkedin_post_url"), uid, body["activity_date"]))
                new_id = cur.fetchone()["id"]
                db.commit()
                if body.get("create_interaction", True):
                    db.execute(
                        "INSERT INTO interactions (contact_id,user_id,type,date,subject,notes) VALUES (%s,%s,'linkedin',%s,%s,%s)",
                        (body["contact_id"], uid, body["activity_date"],
                         "LinkedIn: {}".format(body["activity_type"]), body.get("content_summary","")))
                    db.commit()
                log_audit(db, uid, "create", "linkedin_activity", new_id,
                          body["activity_type"], {"contact_id": body["contact_id"]})
                db.commit()
                self._json_response({"id": new_id}, 201)

            elif path == "/api/linkedin-engagements":
                cur = db.execute(
                    """INSERT INTO linkedin_engagements (contact_id,engagement_type,company_page,
                       post_url,observed_by,observed_date,notes) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["contact_id"], body["engagement_type"], body["company_page"],
                     body.get("post_url"), uid, body["observed_date"], body.get("notes")))
                new_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "create", "linkedin_engagement", new_id,
                          "{} on {}".format(body["engagement_type"], body["company_page"]),
                          {"contact_id": body["contact_id"]})
                db.commit()
                self._json_response({"id": new_id}, 201)

            elif path == "/api/tags":
                name = body.get("name","").strip()
                if not name:
                    return self._error(400, "Tag-navn er paakraevet")
                if not name.startswith("#"):
                    name = "#" + name
                existing = db.execute("SELECT id FROM tags WHERE LOWER(name) = LOWER(%s)", (name,)).fetchone()
                if existing:
                    return self._json_response({"id": existing["id"], "name": name}, 200)
                cur = db.execute("INSERT INTO tags (name,color) VALUES (%s,%s) RETURNING id",
                                 (name, body.get("color","#6b7280")))
                new_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "create", "tag", new_id, name)
                db.commit()
                self._json_response({"id": new_id, "name": name, "color": body.get("color","#6b7280")}, 201)

            elif path.startswith("/api/companies/") and path.endswith("/tags") and path.count("/") == 4:
                cid = int(path.split("/")[-2])
                tag_id = body.get("tag_id")
                if not tag_id:
                    return self._error(400, "tag_id er paakraevet")
                try:
                    db.execute("INSERT INTO company_tags (company_id,tag_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                               (cid, int(tag_id)))
                    db.commit()
                except Exception:
                    db.rollback()
                tag = db.execute("SELECT name FROM tags WHERE id = %s", (int(tag_id),)).fetchone()
                log_audit(db, uid, "create", "company_tag", cid, tag["name"] if tag else str(tag_id))
                db.commit()
                self._json_response({"ok": True}, 201)

            elif path.startswith("/api/contacts/") and path.endswith("/tags") and path.count("/") == 4:
                cid = int(path.split("/")[-2])
                tag_id = body.get("tag_id")
                if not tag_id:
                    return self._error(400, "tag_id er paakraevet")
                db.execute("INSERT INTO contact_tags (contact_id,tag_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                           (cid, int(tag_id)))
                db.commit()
                self._json_response({"ok": True}, 201)

            elif path == "/api/tenders":
                cur = db.execute(
                    """INSERT INTO tenders (company_id,template_id,title,description,status,
                       deadline,contact_id,responsible_id,created_by,estimated_value,portal_link,notes,purchase_route,via_group_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["company_id"], body.get("template_id"), body["title"], body.get("description"),
                     body.get("status","draft"), body.get("deadline"), body.get("contact_id"),
                     body.get("responsible_id"), uid, body.get("estimated_value"),
                     body.get("portal_link"), body.get("notes"), body.get("purchase_route") or "selv",
                     body.get("via_group_id") if body.get("purchase_route") == "faellesskab" else None))
                tender_id = cur.fetchone()["id"]
                template_id = body.get("template_id")
                if template_id:
                    tmpl_sections = db.execute(
                        "SELECT * FROM tender_template_sections WHERE template_id = %s ORDER BY sort_order",
                        (int(template_id),)).fetchall()
                    prev_end = None
                    for ts in tmpl_sections:
                        section_deadline = section_start = section_end = None
                        if body.get("deadline") and ts["default_days_before_deadline"]:
                            try:
                                td = date.fromisoformat(body["deadline"])
                                section_end = (td - timedelta(days=ts["default_days_before_deadline"])).isoformat()
                                section_deadline = section_end
                                section_start = prev_end or date.today().isoformat()
                                prev_end = section_end
                            except (ValueError, TypeError):
                                pass
                        db.execute(
                            """INSERT INTO tender_sections (tender_id,title,description,status,deadline,start_date,end_date,sort_order)
                               VALUES (%s,%s,%s,'not_started',%s,%s,%s,%s)""",
                            (tender_id, ts["title"], ts["description"], section_deadline, section_start, section_end, ts["sort_order"]))
                db.commit()
                log_audit(db, uid, "create", "tender", tender_id, body["title"], {"company_id": body["company_id"]})
                db.commit()
                row = db.execute(
                    "SELECT t.*, c.name AS company_name FROM tenders t JOIN companies c ON t.company_id = c.id WHERE t.id = %s",
                    (tender_id,)).fetchone()
                self._json_response(dict(row), 201)

            elif path.startswith("/api/tender-sections/") and path.endswith("/comments"):
                sid = int(path.split("/")[-2])
                user_name = None
                if uid:
                    ur = db.execute("SELECT name FROM users WHERE id=%s", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                db.execute(
                    "INSERT INTO tender_section_audit (section_id,user_id,user_name,note_type,content) VALUES (%s,%s,%s,'comment',%s)",
                    (sid, uid, user_name, body.get("content","")))
                db.commit()
                self._json_response({"ok": True}, 201)

            elif path == "/api/tender-sections":
                cur = db.execute(
                    """INSERT INTO tender_sections (tender_id,title,description,content,
                       responsible_id,reviewer_id,status,deadline,start_date,end_date,sort_order,notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["tender_id"], body["title"], body.get("description"), body.get("content"),
                     body.get("responsible_id"), body.get("reviewer_id"),
                     body.get("status","not_started"), body.get("deadline"),
                     body.get("start_date"), body.get("end_date"),
                     body.get("sort_order",0), body.get("notes")))
                section_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "create", "tender_section", section_id, body["title"],
                          {"tender_id": body["tender_id"]})
                user_name = None
                if uid:
                    ur = db.execute("SELECT name FROM users WHERE id=%s", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                db.execute(
                    "INSERT INTO tender_section_audit (section_id,user_id,user_name,note_type,content) VALUES (%s,%s,%s,'created','Sektion oprettet')",
                    (section_id, uid, user_name))
                db.commit()
                row = db.execute(
                    """SELECT ts.*, u1.name AS responsible_name, u2.name AS reviewer_name
                       FROM tender_sections ts
                       LEFT JOIN users u1 ON ts.responsible_id = u1.id
                       LEFT JOIN users u2 ON ts.reviewer_id = u2.id
                       WHERE ts.id = %s""", (section_id,)).fetchone()
                self._json_response(dict(row), 201)

            elif path == "/api/tender-templates":
                cur = db.execute(
                    "INSERT INTO tender_templates (name,description) VALUES (%s,%s) RETURNING id",
                    (body["name"], body.get("description")))
                new_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "create", "tender_template", new_id, body["name"])
                db.commit()
                self._json_response({"id": new_id, "name": body["name"]}, 201)

            elif path.startswith("/api/tender-templates/") and path.endswith("/sections"):
                tmpl_id = int(path.split("/")[-2])
                max_sort = db.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) AS m FROM tender_template_sections WHERE template_id = %s",
                    (tmpl_id,)).fetchone()["m"]
                cur = db.execute(
                    """INSERT INTO tender_template_sections
                       (template_id,title,description,default_days_before_deadline,sort_order)
                       VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                    (tmpl_id, body["title"], body.get("description"),
                     body.get("default_days_before_deadline",7),
                     body.get("sort_order", max_sort + 1)))
                new_id = cur.fetchone()["id"]
                db.commit()
                self._json_response({"id": new_id}, 201)

            else:
                self._error(404, "Endpoint not found")
        finally:
            db.close()

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
        file_content = file_name = None
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
                    file_name = header[fn_start:header.find('"', fn_start)]
            else:
                name_start = header.find('name="') + 6
                name_end = header.find('"', name_start)
                fields[header[name_start:name_end]] = data.decode("utf-8").strip()
        if not file_content or not file_name:
            return self._error(400, "Ingen fil modtaget")
        if not (file_name.lower().endswith(".eml") or file_name.lower().endswith(".msg")):
            return self._error(400, f"Filtypen er ikke understottet. Kun .eml filer er tilladt.")
        parsed = parse_eml(file_content)
        if path == "/api/tasks/upload-email":
            task_id = fields.get("task_id")
            if not task_id:
                return self._error(400, "task_id er paakraevet")
            user_name = None
            db = get_db()
            try:
                if uid:
                    ur = db.execute("SELECT name FROM users WHERE id=%s", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                email_summary = "Fra: {}\nTil: {}\nDato: {}\nEmne: {}\n\n{}".format(
                    parsed["from_email"] or "", parsed["to_email"] or "",
                    parsed["date_sent"] or "", parsed["subject"] or "",
                    (parsed["body_text"] or "")[:2000])
                metadata = json.dumps({"from": parsed["from_email"], "to": parsed["to_email"],
                                       "cc": parsed["cc"], "date_sent": parsed["date_sent"],
                                       "filename": file_name})
                cur = db.execute(
                    "INSERT INTO task_notes (task_id,user_id,user_name,content,note_type,metadata) VALUES (%s,%s,%s,%s,'email',%s) RETURNING id",
                    (int(task_id), uid, user_name, email_summary, metadata))
                new_id = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "import_email", "task", int(task_id), file_name)
                db.commit()
                row = db.execute("SELECT * FROM task_notes WHERE id = %s", (new_id,)).fetchone()
                self._json_response(dict(row), 201)
            finally:
                db.close()
            return
        contact_id = fields.get("contact_id")
        if not contact_id:
            return self._error(400, "contact_id er paakraevet")
        user_id = fields.get("user_id") or None
        db = get_db()
        try:
            interaction_date = parsed["date_sent"][:10] if parsed["date_sent"] else None
            cur = db.execute(
                "INSERT INTO interactions (contact_id,user_id,type,date,subject,notes) VALUES (%s,%s,'email',%s,%s,'Importeret fra .eml fil') RETURNING id",
                (int(contact_id), int(user_id) if user_id else None, interaction_date, parsed["subject"]))
            iid = cur.fetchone()["id"]
            cur2 = db.execute(
                "INSERT INTO emails (interaction_id,from_email,to_email,cc,subject,body_text,body_html,date_sent,eml_filename) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (iid, parsed["from_email"], parsed["to_email"], parsed["cc"], parsed["subject"],
                 parsed["body_text"], parsed["body_html"], parsed["date_sent"], file_name))
            new_id = cur2.fetchone()["id"]
            db.commit()
            log_audit(db, uid, "import", "email", new_id, file_name,
                      {"contact_id": int(contact_id), "subject": parsed["subject"]})
            db.commit()
            row = db.execute("SELECT * FROM emails WHERE id = %s", (new_id,)).fetchone()
            self._json_response(dict(row), 201)
        finally:
            db.close()

    # ─── PUT ───
    def _handle_api_put(self, path, body):
        db = get_db()
        uid = self._get_user_id()
        try:
            if self._handle_ceo(db, 'PUT', path, {}, body, uid):
                return
            if path.startswith("/api/users/") and path.count("/") == 3:
                # Ret navn, e-mail og rolle (e-mailen bruges fx til at finde personen i Slack)
                user_id = int(path.split("/")[-1])
                vals = {k: (body[k].strip() if isinstance(body.get(k), str) else body.get(k)) for k in ("name", "email", "role") if body.get(k)}
                if vals:
                    try:
                        db.execute(f"UPDATE users SET {', '.join(f'{k} = %s' for k in vals)} WHERE id = %s", list(vals.values()) + [user_id])
                        db.commit()
                    except psycopg2.errors.UniqueViolation:
                        db.rollback()
                        return self._error(400, "E-mailen bruges allerede af en anden bruger")
                    log_audit(db, uid, "update", "user", user_id, vals.get("name") or vals.get("email"))
                    db.commit()
                row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
                return self._json_response(dict(row)) if row else self._error(404, "Bruger ikke fundet")
            if path.startswith("/api/companies/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                existing = db.execute("SELECT * FROM companies WHERE id = %s", (cid,)).fetchone()
                if not existing:
                    return self._error(404, "Virksomhed ikke fundet")
                e = dict(existing)
                changes = {}
                for k, v in body.items():
                    if k in e and e[k] != v:
                        changes[k] = {"old": e[k], "new": v}
                    if k in e:
                        e[k] = v
                if "account_manager_id" in body:
                    e["account_manager_id"] = body["account_manager_id"]
                db.execute(
                    """UPDATE companies SET name=%s,sector=%s,address=%s,city=%s,zip_code=%s,website=%s,notes=%s,
                       rating=%s,account_manager_id=%s,importance=%s,sales_stage=%s,
                       score_cxo=%s,score_kontaktfrekvens=%s,score_kontaktbredde=%s,score_kendskab=%s,score_historik=%s,
                       score_kendskab_behov=%s,score_workshops=%s,score_marketing=%s,
                       tier=%s,ejerform=%s,has_el=%s,has_gas=%s,has_vand=%s,has_varme=%s,has_spildevand=%s,has_affald=%s,est_kunder=%s WHERE id=%s""",
                    (e["name"], e["sector"], e["address"], e["city"], e["zip_code"],
                     e["website"], e["notes"], e.get("rating","C"), e.get("account_manager_id"),
                     e.get("importance","middel_vigtig"), e.get("sales_stage","tidlig_fase"),
                     e.get("score_cxo",0), e.get("score_kontaktfrekvens",0),
                     e.get("score_kontaktbredde",0), e.get("score_kendskab",0), e.get("score_historik",0),
                     e.get("score_kendskab_behov",0), e.get("score_workshops",0), e.get("score_marketing",0),
                     e.get("tier"), e.get("ejerform"),
                     bool(e.get("has_el",False)), bool(e.get("has_gas",False)), bool(e.get("has_vand",False)),
                     bool(e.get("has_varme",False)), bool(e.get("has_spildevand",False)), bool(e.get("has_affald",False)),
                     e.get("est_kunder"), cid))
                db.commit()
                if changes:
                    log_audit(db, uid, "update", "company", cid, e["name"], changes)
                    db.commit()
                row = db.execute(
                    "SELECT c.*, u.name AS account_manager_name FROM companies c LEFT JOIN users u ON c.account_manager_id = u.id WHERE c.id = %s",
                    (cid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/contacts/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                existing = db.execute("SELECT * FROM contacts WHERE id = %s", (cid,)).fetchone()
                if not existing:
                    return self._error(404, "Kontakt ikke fundet")
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v
                db.execute(
                    """UPDATE contacts SET first_name=%s,last_name=%s,title=%s,email=%s,phone=%s,linkedin_url=%s,
                       on_linkedin_list=%s,notes=%s,linkedin_connected_systemate=%s,linkedin_connected_settl=%s,
                       linkedin_last_checked=%s WHERE id=%s""",
                    (e["first_name"], e["last_name"], e["title"], e["email"], e["phone"],
                     e["linkedin_url"], bool(e["on_linkedin_list"]), e["notes"],
                     bool(e.get("linkedin_connected_systemate",False)), bool(e.get("linkedin_connected_settl",False)),
                     e.get("linkedin_last_checked"), cid))
                db.commit()
                log_audit(db, uid, "update", "contact", cid, "{} {}".format(e["first_name"], e["last_name"]))
                db.commit()
                row = db.execute("SELECT * FROM contacts WHERE id = %s", (cid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/tasks/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                existing = db.execute("SELECT * FROM tasks WHERE id = %s", (tid,)).fetchone()
                if not existing:
                    return self._error(404, "Sag ikke fundet")
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v
                if body.get("status") == "done" and existing["status"] != "done":
                    e["completed_at"] = datetime.now().isoformat()
                elif "status" in body and body["status"] != "done":
                    e["completed_at"] = None
                db.execute(
                    """UPDATE tasks SET contact_id=%s,assigned_to=%s,category=%s,title=%s,description=%s,
                       status=%s,priority=%s,due_date=%s,completed_at=%s,area=%s WHERE id=%s""",
                    (e.get("contact_id"), e.get("assigned_to"), e["category"], e["title"],
                     e.get("description"), e["status"], e["priority"], e.get("due_date"),
                     e.get("completed_at"), e.get("area") or "salg", tid))
                db.commit()
                log_audit(db, uid, "update", "task", tid, e["title"], {"status": e["status"]})
                db.commit()
                row = db.execute(
                    """SELECT t.*, c.name AS company_name, u1.name AS assigned_to_name, u2.name AS created_by_name
                       FROM tasks t JOIN companies c ON t.company_id = c.id
                       LEFT JOIN users u1 ON t.assigned_to = u1.id LEFT JOIN users u2 ON t.created_by = u2.id
                       WHERE t.id = %s""", (tid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/tags/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                db.execute("UPDATE tags SET name=%s,color=%s WHERE id=%s",
                           (body["name"], body.get("color","#6b7280"), tid))
                db.commit()
                row = db.execute("SELECT * FROM tags WHERE id=%s", (tid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/notifications/") and path.endswith("/read"):
                nid = int(path.split("/")[-2])
                db.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (nid,))
                db.commit()
                self._json_response({"ok": True})

            elif path == "/api/notifications/read-all":
                db.execute("UPDATE notifications SET is_read = TRUE WHERE is_read = FALSE")
                db.commit()
                self._json_response({"ok": True})

            elif path.startswith("/api/company-notes/") and path.count("/") == 3:
                nid = int(path.split("/")[-1])
                db.execute("UPDATE company_notes SET content = %s WHERE id = %s", (body.get("content",""), nid))
                db.commit()
                row = db.execute("SELECT * FROM company_notes WHERE id = %s", (nid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/task-notes/") and path.count("/") == 3:
                nid = int(path.split("/")[-1])
                db.execute("UPDATE task_notes SET content = %s WHERE id = %s", (body.get("content",""), nid))
                db.commit()
                row = db.execute("SELECT * FROM task_notes WHERE id = %s", (nid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/tender-notes/") and path.count("/") == 3:
                nid = int(path.split("/")[-1])
                db.execute("UPDATE tender_notes SET content = %s WHERE id = %s", (body.get("content",""), nid))
                db.commit()
                row = db.execute("SELECT * FROM tender_notes WHERE id = %s", (nid,)).fetchone()
                self._json_response(dict(row))

            elif path == "/api/settings/score-thresholds":
                for rating, threshold in body.items():
                    if rating in ("A","B","C"):
                        db.execute("UPDATE score_settings SET threshold = %s WHERE rating = %s",
                                   (int(threshold), rating))
                db.commit()
                log_audit(db, uid, "update", "settings", None, "score-thresholds", body)
                db.commit()
                self._json_response({"ok": True})

            elif path == "/api/settings/decay-rules":
                rules = body.get("rules", [])
                db.execute("DELETE FROM score_decay_rules")
                for rule in rules:
                    db.execute(
                        "INSERT INTO score_decay_rules (inactivity_days,penalty_points,description,is_active) VALUES (%s,%s,%s,%s)",
                        (int(rule["inactivity_days"]), int(rule["penalty_points"]),
                         rule.get("description",""), bool(rule.get("is_active",True))))
                db.commit()
                log_audit(db, uid, "update", "settings", None, "decay-rules", {"rules_count": len(rules)})
                db.commit()
                self._json_response({"ok": True})

            elif path.startswith("/api/tenders/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                existing = db.execute("SELECT * FROM tenders WHERE id = %s", (tid,)).fetchone()
                if not existing:
                    return self._error(404, "Tilbud ikke fundet")
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v
                route = e.get("purchase_route") or "selv"
                db.execute(
                    """UPDATE tenders SET company_id=%s,title=%s,description=%s,status=%s,
                       deadline=%s,contact_id=%s,responsible_id=%s,estimated_value=%s,portal_link=%s,notes=%s,
                       purchase_route=%s,via_group_id=%s WHERE id=%s""",
                    (e["company_id"], e["title"], e.get("description"), e["status"],
                     e.get("deadline"), e.get("contact_id"), e.get("responsible_id"),
                     e.get("estimated_value"), e.get("portal_link"), e.get("notes"),
                     route, e.get("via_group_id") if route == "faellesskab" else None, tid))
                db.commit()
                log_audit(db, uid, "update", "tender", tid, e["title"], {"status": e["status"]})
                db.commit()
                row = db.execute(
                    "SELECT t.*, c.name AS company_name FROM tenders t JOIN companies c ON t.company_id = c.id WHERE t.id = %s",
                    (tid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/tender-sections/") and path.count("/") == 3:
                sid = int(path.split("/")[-1])
                existing = db.execute("SELECT * FROM tender_sections WHERE id = %s", (sid,)).fetchone()
                if not existing:
                    return self._error(404, "Sektion ikke fundet")
                old = dict(existing)
                e = dict(existing)
                for k, v in body.items():
                    if k in e:
                        e[k] = v
                user_name = None
                if uid:
                    ur = db.execute("SELECT name FROM users WHERE id=%s", (uid,)).fetchone()
                    if ur: user_name = ur["name"]
                audit_entries = []
                if e["status"] != old["status"]:
                    audit_entries.append(("status_change", None, old["status"], e["status"], "status"))
                if str(e.get("responsible_id") or "") != str(old.get("responsible_id") or ""):
                    old_n, new_n = "-", "-"
                    if old.get("responsible_id"):
                        r = db.execute("SELECT name FROM users WHERE id=%s", (old["responsible_id"],)).fetchone()
                        if r: old_n = r["name"]
                    if e.get("responsible_id"):
                        r = db.execute("SELECT name FROM users WHERE id=%s", (e["responsible_id"],)).fetchone()
                        if r: new_n = r["name"]
                    audit_entries.append(("field_change", None, old_n, new_n, "responsible"))
                if str(e.get("reviewer_id") or "") != str(old.get("reviewer_id") or ""):
                    old_n, new_n = "-", "-"
                    if old.get("reviewer_id"):
                        r = db.execute("SELECT name FROM users WHERE id=%s", (old["reviewer_id"],)).fetchone()
                        if r: old_n = r["name"]
                    if e.get("reviewer_id"):
                        r = db.execute("SELECT name FROM users WHERE id=%s", (e["reviewer_id"],)).fetchone()
                        if r: new_n = r["name"]
                    audit_entries.append(("field_change", None, old_n, new_n, "reviewer"))
                if (e.get("notes") or "") != (old.get("notes") or ""):
                    audit_entries.append(("note", e.get("notes"), old.get("notes") or "", e.get("notes") or "", "notes"))
                db.execute(
                    """UPDATE tender_sections SET title=%s,description=%s,content=%s,
                       responsible_id=%s,reviewer_id=%s,status=%s,deadline=%s,
                       start_date=%s,end_date=%s,sort_order=%s,notes=%s WHERE id=%s""",
                    (e["title"], e.get("description"), e.get("content"),
                     e.get("responsible_id"), e.get("reviewer_id"), e["status"],
                     e.get("deadline"), e.get("start_date"), e.get("end_date"),
                     e["sort_order"], e.get("notes"), sid))
                for note_type, content, old_val, new_val, field_name in audit_entries:
                    db.execute(
                        """INSERT INTO tender_section_audit
                           (section_id,user_id,user_name,note_type,content,old_value,new_value,field_name)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (sid, uid, user_name, note_type, content, old_val, new_val, field_name))
                db.commit()
                log_audit(db, uid, "update", "tender_section", sid, e["title"], {"status": e["status"]})
                db.commit()
                row = db.execute(
                    """SELECT ts.*, u1.name AS responsible_name, u2.name AS reviewer_name
                       FROM tender_sections ts
                       LEFT JOIN users u1 ON ts.responsible_id = u1.id
                       LEFT JOIN users u2 ON ts.reviewer_id = u2.id
                       WHERE ts.id = %s""", (sid,)).fetchone()
                self._json_response(dict(row))

            elif path.startswith("/api/tender-templates/") and path.count("/") == 3:
                tmpl_id = int(path.split("/")[-1])
                existing = db.execute("SELECT * FROM tender_templates WHERE id = %s", (tmpl_id,)).fetchone()
                if not existing:
                    return self._error(404, "Skabelon ikke fundet")
                db.execute("UPDATE tender_templates SET name=%s,description=%s WHERE id=%s",
                           (body.get("name", existing["name"]), body.get("description", existing["description"]), tmpl_id))
                db.commit()
                log_audit(db, uid, "update", "tender_template", tmpl_id, body.get("name", existing["name"]))
                db.commit()
                self._json_response({"id": tmpl_id, "name": body.get("name", existing["name"])})

            elif path.startswith("/api/tender-template-sections/") and path.count("/") == 3:
                sec_id = int(path.split("/")[-1])
                existing = db.execute("SELECT * FROM tender_template_sections WHERE id = %s", (sec_id,)).fetchone()
                if not existing:
                    return self._error(404, "Skabelon-sektion ikke fundet")
                db.execute(
                    "UPDATE tender_template_sections SET title=%s,description=%s,default_days_before_deadline=%s,sort_order=%s WHERE id=%s",
                    (body.get("title", existing["title"]), body.get("description", existing["description"]),
                     body.get("default_days_before_deadline", existing["default_days_before_deadline"]),
                     body.get("sort_order", existing["sort_order"]), sec_id))
                db.commit()
                self._json_response({"id": sec_id})

            else:
                self._error(404, "Endpoint not found")
        finally:
            db.close()

    # ─── DELETE ───
    def _handle_api_delete(self, path):
        db = get_db()
        uid = self._get_user_id()
        try:
            if self._handle_ceo(db, 'DELETE', path, {}, None, uid):
                return
            if path == "/api/notifications/read":
                # "Ryd læste" i klokken: fjerner notifikationer, brugeren allerede har læst
                db.execute("DELETE FROM notifications WHERE is_read = TRUE")
                db.commit()
                return self._no_content()
            if path.startswith("/api/companies/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = db.execute("SELECT name FROM companies WHERE id = %s", (cid,)).fetchone()
                db.execute("DELETE FROM companies WHERE id = %s", (cid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "company", cid, row["name"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/contacts/") and path.count("/") == 3:
                cid = int(path.split("/")[-1])
                row = db.execute("SELECT first_name, last_name FROM contacts WHERE id = %s", (cid,)).fetchone()
                db.execute("DELETE FROM contacts WHERE id = %s", (cid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "contact", cid, "{} {}".format(row["first_name"], row["last_name"]))
                    db.commit()
                self._no_content()

            elif path.startswith("/api/interactions/") and path.count("/") == 3:
                iid = int(path.split("/")[-1])
                row = db.execute("SELECT subject, type FROM interactions WHERE id = %s", (iid,)).fetchone()
                db.execute("DELETE FROM interactions WHERE id = %s", (iid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "interaction", iid, row["subject"] or row["type"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/users/") and path.count("/") == 3:
                uid_del = int(path.split("/")[-1])
                row = db.execute("SELECT name FROM users WHERE id = %s", (uid_del,)).fetchone()
                db.execute("UPDATE users SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s", (uid_del,))
                db.commit()
                if row:
                    log_audit(db, uid, "deactivate", "user", uid_del, row["name"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/tasks/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = db.execute("SELECT title FROM tasks WHERE id = %s", (tid,)).fetchone()
                db.execute("DELETE FROM tasks WHERE id = %s", (tid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "task", tid, row["title"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/linkedin-activities/") and path.count("/") == 3:
                lid = int(path.split("/")[-1])
                db.execute("DELETE FROM linkedin_activities WHERE id = %s", (lid,))
                db.commit()
                self._no_content()

            elif path.startswith("/api/linkedin-engagements/") and path.count("/") == 3:
                lid = int(path.split("/")[-1])
                db.execute("DELETE FROM linkedin_engagements WHERE id = %s", (lid,))
                db.commit()
                self._no_content()

            elif path.startswith("/api/tags/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = db.execute("SELECT name FROM tags WHERE id = %s", (tid,)).fetchone()
                db.execute("DELETE FROM tags WHERE id = %s", (tid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "tag", tid, row["name"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/companies/") and "/tags/" in path and path.count("/") == 5:
                parts = path.split("/")
                db.execute("DELETE FROM company_tags WHERE company_id = %s AND tag_id = %s",
                           (int(parts[3]), int(parts[5])))
                db.commit()
                self._no_content()

            elif path.startswith("/api/contacts/") and "/tags/" in path and path.count("/") == 5:
                parts = path.split("/")
                db.execute("DELETE FROM contact_tags WHERE contact_id = %s AND tag_id = %s",
                           (int(parts[3]), int(parts[5])))
                db.commit()
                self._no_content()

            elif path.startswith("/api/tenders/") and path.count("/") == 3:
                tid = int(path.split("/")[-1])
                row = db.execute("SELECT title FROM tenders WHERE id = %s", (tid,)).fetchone()
                db.execute("DELETE FROM tenders WHERE id = %s", (tid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "tender", tid, row["title"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/tender-sections/") and path.count("/") == 3:
                sid = int(path.split("/")[-1])
                row = db.execute("SELECT title FROM tender_sections WHERE id = %s", (sid,)).fetchone()
                db.execute("DELETE FROM tender_sections WHERE id = %s", (sid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "tender_section", sid, row["title"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/tender-templates/") and path.count("/") == 3:
                tmpl_id = int(path.split("/")[-1])
                row = db.execute("SELECT name FROM tender_templates WHERE id = %s", (tmpl_id,)).fetchone()
                db.execute("DELETE FROM tender_templates WHERE id = %s", (tmpl_id,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "tender_template", tmpl_id, row["name"])
                    db.commit()
                self._no_content()

            elif path.startswith("/api/tender-template-sections/") and path.count("/") == 3:
                sec_id = int(path.split("/")[-1])
                db.execute("DELETE FROM tender_template_sections WHERE id = %s", (sec_id,))
                db.commit()
                self._no_content()

            else:
                self._error(404, "Endpoint not found")
        finally:
            db.close()

    # ─── SystemateCEO: mål, ledermøder og aktioner ───
    def _user_name(self, db, uid):
        if not uid:
            return None
        row = db.execute("SELECT name FROM users WHERE id = %s", (uid,)).fetchone()
        return row["name"] if row else None

    def _goal_rows(self, db, where="", params=None):
        rows = [dict(r) for r in db.execute(f"""
            SELECT g.*, co.name AS company_name,
                   (SELECT COUNT(*) FROM goal_milestones m WHERE m.goal_id = g.id) AS milestones_total,
                   (SELECT COUNT(*) FROM goal_milestones m WHERE m.goal_id = g.id AND m.done) AS milestones_done,
                   (SELECT c.comment FROM goal_checkins c WHERE c.goal_id = g.id ORDER BY c.checkin_date DESC, c.id DESC LIMIT 1) AS last_comment,
                   (SELECT COUNT(*) FROM meeting_actions a WHERE a.goal_id = g.id AND a.status = 'open') AS open_actions
            FROM goals g LEFT JOIN companies co ON g.company_id = co.id
            WHERE 1=1 {where}
            ORDER BY CASE g.kind WHEN 'drift' THEN 0 ELSE 1 END, g.due_date ASC NULLS LAST, g.id
        """, params).fetchall()]
        for g in rows:
            g["quality"], g["quality_missing"] = goal_quality(g)
        return rows

    def _action_rows(self, db, where="", params=None):
        return [dict(r) for r in db.execute(f"""
            SELECT a.*, g.title AS goal_title, co.name AS company_name, m.meeting_date AS meeting_date
            FROM meeting_actions a
            LEFT JOIN goals g ON a.goal_id = g.id
            LEFT JOIN companies co ON a.company_id = co.id
            LEFT JOIN meetings m ON a.meeting_id = m.id
            WHERE 1=1 {where}
            ORDER BY CASE a.status WHEN 'open' THEN 0 ELSE 1 END, a.due_date ASC NULLS LAST, a.id
        """, params).fetchall()]

    def _handle_ceo(self, db, method, path, params, body, uid):
        """Returns True when the request was a SystemateCEO route and has been answered."""
        if path.startswith("/api/report-rounds") or path.startswith("/api/r/") or path == "/api/report-config":
            return self._handle_reports(db, method, path, body, uid)
        if path == "/api/purchasing-groups" or (path.startswith("/api/companies/") and ("/memberships" in path or path.endswith("/group"))):
            return self._handle_groups(db, method, path, body, uid)
        if not (path.startswith("/api/goals") or path.startswith("/api/meetings") or path.startswith("/api/actions")
                or path.startswith("/api/milestones") or path.startswith("/api/ceo/") or path.startswith("/api/cron/")):
            return False
        parts = path.strip("/").split("/")  # e.g. ['api', 'goals', '3', 'checkins']
        res = parts[1]
        rid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        sub = parts[3] if len(parts) > 3 else None

        GOAL_FIELDS = ["area", "kind", "title", "description", "owner_role", "company_id", "unit", "start_value",
                       "target_value", "current_value", "start_date", "due_date", "status", "archived"]
        MEETING_FIELDS = ["area", "title", "meeting_date", "participants", "status", "summary", "next_meeting_date"]
        ACTION_FIELDS = ["meeting_id", "area", "goal_id", "company_id", "kind", "title", "owner", "due_date", "status",
                         "description", "checklist", "notes"]
        def action_vals(src):
            vals = {k: blank_to_none(src.get(k)) for k in ACTION_FIELDS if k in src}
            if "checklist" in vals:
                vals["checklist"] = json.dumps(vals["checklist"] or [])
            return vals

        def blank_to_none(v):
            return None if v == "" else v

        # ── Overview for Overblik ──
        if path.startswith("/api/ceo/assistant"):
            return self._handle_assistant(db, method, path, body)
        if path in ("/api/ceo/followup-settings", "/api/ceo/followup") or path.startswith("/api/cron/"):
            return self._handle_task_followup(db, method, path, body)
        if res == "ceo" and method == "GET":
            goals = self._goal_rows(db, "AND NOT g.archived")
            actions = self._action_rows(db, "AND a.status = 'open'")
            last_meetings = [dict(r) for r in db.execute("""
                SELECT DISTINCT ON (area) id, area, title, meeting_date, status, next_meeting_date
                FROM meetings WHERE status = 'done' ORDER BY area, meeting_date DESC, id DESC""").fetchall()]
            planned = [dict(r) for r in db.execute("""
                SELECT id, area, title, meeting_date, status FROM meetings
                WHERE status != 'done' ORDER BY meeting_date ASC""").fetchall()]
            self._json_response({"goals": goals, "open_actions": actions,
                                 "last_meetings": last_meetings, "planned_meetings": planned})
            return True

        # ── Goals ──
        if res == "goals":
            if method == "GET" and rid is None:
                where, p = "", []
                if params.get("area"):
                    where += " AND g.area = %s"; p.append(params["area"][0])
                if params.get("kind"):
                    where += " AND g.kind = %s"; p.append(params["kind"][0])
                if not params.get("include_archived"):
                    where += " AND NOT g.archived"
                self._json_response(self._goal_rows(db, where, p or None))
            elif method == "GET":
                rows = self._goal_rows(db, "AND g.id = %s", (rid,))
                if not rows:
                    self._error(404, "Mål ikke fundet"); return True
                goal = rows[0]
                goal["checkins"] = [dict(r) for r in db.execute(
                    """SELECT c.*, m.title AS meeting_title FROM goal_checkins c LEFT JOIN meetings m ON c.meeting_id = m.id
                       WHERE c.goal_id = %s ORDER BY c.checkin_date DESC, c.id DESC""", (rid,)).fetchall()]
                goal["milestones"] = [dict(r) for r in db.execute(
                    "SELECT * FROM goal_milestones WHERE goal_id = %s ORDER BY due_date ASC NULLS LAST, id", (rid,)).fetchall()]
                goal["actions"] = self._action_rows(db, "AND a.goal_id = %s", (rid,))
                self._json_response(goal)
            elif method == "POST" and rid is None:
                vals = {k: blank_to_none(body.get(k)) for k in GOAL_FIELDS if k in body}
                if not vals.get("title"):
                    self._error(400, "Titel mangler"); return True
                cols = list(vals.keys())
                cur = db.execute(f"INSERT INTO goals ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
                                 [vals[c] for c in cols])
                gid = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "create", "goal", gid, vals["title"])
                db.commit()
                self._json_response(self._goal_rows(db, "AND g.id = %s", (gid,))[0], 201)
            elif method == "POST" and sub == "checkins":
                status = body.get("status") or "on_track"
                value = blank_to_none(body.get("value"))
                db.execute(
                    """INSERT INTO goal_checkins (goal_id, meeting_id, checkin_date, value, status, comment, user_name)
                       VALUES (%s,%s,COALESCE(%s, CURRENT_DATE),%s,%s,%s,%s)""",
                    (rid, body.get("meeting_id"), blank_to_none(body.get("checkin_date")), value, status,
                     blank_to_none(body.get("comment")), self._user_name(db, uid)))
                db.execute(
                    """UPDATE goals SET status = %s, current_value = COALESCE(%s, current_value),
                       last_checkin = COALESCE(%s, CURRENT_DATE), updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
                    (status, value, blank_to_none(body.get("checkin_date")), rid))
                db.commit()
                self._json_response(self._goal_rows(db, "AND g.id = %s", (rid,))[0], 201)
            elif method == "POST" and sub == "milestones":
                cur = db.execute("INSERT INTO goal_milestones (goal_id, title, due_date) VALUES (%s,%s,%s) RETURNING *",
                                 (rid, body["title"], blank_to_none(body.get("due_date"))))
                row = dict(cur.fetchone())
                db.commit()
                self._json_response(row, 201)
            elif method == "PUT" and rid is not None:
                vals = {k: blank_to_none(body.get(k)) for k in GOAL_FIELDS if k in body}
                if vals:
                    sets = ", ".join(f"{k} = %s" for k in vals)
                    db.execute(f"UPDATE goals SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                               list(vals.values()) + [rid])
                    db.commit()
                rows = self._goal_rows(db, "AND g.id = %s", (rid,))
                if not rows:
                    self._error(404, "Mål ikke fundet"); return True
                self._json_response(rows[0])
            elif method == "DELETE" and rid is not None:
                row = db.execute("SELECT title FROM goals WHERE id = %s", (rid,)).fetchone()
                db.execute("DELETE FROM goals WHERE id = %s", (rid,))
                db.commit()
                if row:
                    log_audit(db, uid, "delete", "goal", rid, row["title"])
                    db.commit()
                self._no_content()
            else:
                self._error(404, "Endpoint not found")
            return True

        # ── Milestones ──
        if res == "milestones" and rid is not None:
            if method == "PUT":
                row = db.execute("SELECT * FROM goal_milestones WHERE id = %s", (rid,)).fetchone()
                if not row:
                    self._error(404, "Milepæl ikke fundet"); return True
                m = dict(row)
                for k in ("title", "due_date", "done"):
                    if k in body:
                        m[k] = blank_to_none(body[k])
                done_at = (m.get("done_at") or datetime.now()) if m["done"] else None
                db.execute("UPDATE goal_milestones SET title=%s, due_date=%s, done=%s, done_at=%s WHERE id=%s",
                           (m["title"], m["due_date"], bool(m["done"]), done_at, rid))
                db.commit()
                self._json_response(dict(db.execute("SELECT * FROM goal_milestones WHERE id = %s", (rid,)).fetchone()))
            elif method == "DELETE":
                db.execute("DELETE FROM goal_milestones WHERE id = %s", (rid,))
                db.commit()
                self._no_content()
            else:
                self._error(404, "Endpoint not found")
            return True

        # ── Meetings ──
        if res == "meetings":
            if method == "GET" and rid is None:
                where, p = "", []
                if params.get("area"):
                    where = " WHERE m.area = %s"; p.append(params["area"][0])
                rows = [dict(r) for r in db.execute(f"""
                    SELECT m.*,
                           (SELECT COUNT(*) FROM meeting_actions a WHERE a.meeting_id = m.id AND a.kind = 'aktion') AS actions_count,
                           (SELECT COUNT(*) FROM meeting_actions a WHERE a.meeting_id = m.id AND a.kind = 'beslutning') AS decisions_count,
                           (SELECT COUNT(*) FROM goal_checkins c WHERE c.meeting_id = m.id) AS checkins_count
                    FROM meetings m {where} ORDER BY m.meeting_date DESC, m.id DESC""", p or None).fetchall()]
                self._json_response(rows)
            elif method == "GET":
                row = db.execute("SELECT * FROM meetings WHERE id = %s", (rid,)).fetchone()
                if not row:
                    self._error(404, "Møde ikke fundet"); return True
                mtg = dict(row)
                area = mtg["area"]
                # Ledelsesmødet (tværgående) gennemgår tværgående mål og alle strategiske mål
                if area == "tvaers":
                    goal_where, gp = "AND NOT g.archived AND (g.area = 'tvaers' OR g.kind = 'strategisk')", None
                    act_where, ap = "", None
                else:
                    goal_where, gp = "AND NOT g.archived AND g.area = %s", (area,)
                    act_where, ap = "AND a.area = %s", (area,)
                mtg["goals"] = self._goal_rows(db, goal_where, gp)
                checked = {r["goal_id"]: dict(r) for r in db.execute(
                    "SELECT * FROM goal_checkins WHERE meeting_id = %s ORDER BY id", (rid,)).fetchall()}
                for g in mtg["goals"]:
                    g["meeting_checkin"] = checked.get(g["id"])
                # Aktioner til opfølgning: åbne fra tidligere møder + dem der blev lukket på dette møde
                mtg["followup_actions"] = self._action_rows(
                    db, f"{act_where} AND (a.meeting_id IS DISTINCT FROM %s) AND (a.status = 'open' OR a.closed_in_meeting_id = %s)",
                    (list(ap) if ap else []) + [rid, rid])
                mtg["new_items"] = self._action_rows(db, "AND a.meeting_id = %s", (rid,))
                task_area = "" if area == "tvaers" else "AND COALESCE(t.area, 'salg') = %s"
                mtg["risk_tasks"] = [dict(r) for r in db.execute(f"""
                    SELECT t.id, t.title, t.priority, t.due_date, t.status, COALESCE(t.area, 'salg') AS area,
                           co.id AS company_id, co.name AS company_name, u.name AS assigned_to_name
                    FROM tasks t JOIN companies co ON t.company_id = co.id LEFT JOIN users u ON t.assigned_to = u.id
                    WHERE t.status != 'done' {task_area}
                      AND (t.due_date < CURRENT_DATE OR t.priority IN ('high', 'urgent'))
                    ORDER BY t.due_date ASC NULLS LAST LIMIT 25""", (area,) if task_area else None).fetchall()]
                mtg["risk_tenders"] = [dict(r) for r in db.execute("""
                    SELECT t.id, t.title, t.deadline, t.status, t.estimated_value, co.id AS company_id, co.name AS company_name
                    FROM tenders t JOIN companies co ON t.company_id = co.id
                    WHERE t.status NOT IN ('won','lost','dropped','submitted') AND t.deadline < CURRENT_DATE + INTERVAL '14 days'
                    ORDER BY t.deadline ASC""").fetchall()] if area in ("salg", "tvaers") else []
                prev = db.execute("""SELECT id, title, meeting_date, summary FROM meetings
                    WHERE area = %s AND id != %s AND status = 'done' AND meeting_date <= %s
                    ORDER BY meeting_date DESC, id DESC LIMIT 1""", (area, rid, mtg["meeting_date"])).fetchone()
                mtg["previous"] = dict(prev) if prev else None
                self._json_response(mtg)
            elif method == "POST":
                vals = {k: blank_to_none(body.get(k)) for k in MEETING_FIELDS if k in body}
                vals.setdefault("status", "planned")
                cols = list(vals.keys())
                cur = db.execute(f"INSERT INTO meetings ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
                                 [vals[c] for c in cols])
                mid = cur.fetchone()["id"]
                db.commit()
                log_audit(db, uid, "create", "meeting", mid, vals.get("title"))
                db.commit()
                self._json_response(dict(db.execute("SELECT * FROM meetings WHERE id = %s", (mid,)).fetchone()), 201)
            elif method == "PUT" and rid is not None:
                vals = {k: blank_to_none(body.get(k)) for k in MEETING_FIELDS if k in body}
                if "notes" in body:
                    vals["notes"] = json.dumps(body["notes"] or {})
                if vals.get("status") == "done":
                    vals["completed_at"] = datetime.now()
                if vals:
                    sets = ", ".join(f"{k} = %s" for k in vals)
                    db.execute(f"UPDATE meetings SET {sets} WHERE id = %s", list(vals.values()) + [rid])
                    db.commit()
                row = db.execute("SELECT * FROM meetings WHERE id = %s", (rid,)).fetchone()
                if not row:
                    self._error(404, "Møde ikke fundet"); return True
                self._json_response(dict(row))
            elif method == "DELETE" and rid is not None:
                db.execute("DELETE FROM meetings WHERE id = %s", (rid,))
                db.commit()
                self._no_content()
            else:
                self._error(404, "Endpoint not found")
            return True

        # ── Actions & decisions ──
        if res == "actions":
            if method == "POST" and len(parts) > 2 and parts[2] == "breakdown":
                # AI foreslår delopgaver til en opgave (fx "Lønsamtaler" → forberedelse, samtaler, opfølgning)
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    self._error(400, "AI er ikke slået til endnu"); return True
                system = ("Du hjælper CEO'en i Systemate med at bryde en ledelsesopgave ned i 3–8 konkrete, afkrydsbare delopgaver "
                          "i den rækkefølge de skal gøres. Skriv på dansk, korte linjer. Tilføj ikke navne, der ikke står i opgaven.")
                schema = {"type": "object", "additionalProperties": False, "required": ["items"],
                          "properties": {"items": {"type": "array", "items": {"type": "string"}}}}
                try:
                    data, _ = self._claude(system, json.dumps({"opgave": body.get("title"), "beskrivelse": body.get("description"),
                                                               "ansvarlig": body.get("owner"), "frist": body.get("due_date")}, ensure_ascii=False),
                                           schema, effort="low", max_tokens=1500)
                except Exception as e:
                    self._error(502, f"AI kunne ikke bryde opgaven ned: {e}"); return True
                self._json_response({"items": data["items"][:10]})
                return True
            if method == "GET" and rid is None:
                where, p = "", []
                if params.get("area"):
                    where += " AND a.area = %s"; p.append(params["area"][0])
                if params.get("status"):
                    where += " AND a.status = %s"; p.append(params["status"][0])
                if params.get("owner"):
                    where += " AND a.owner ILIKE %s"; p.append(params["owner"][0] + "%")
                if params.get("kind"):
                    where += " AND a.kind = %s"; p.append(params["kind"][0])
                self._json_response(self._action_rows(db, where, p or None))
            elif method == "POST":
                vals = action_vals(body)
                if not vals.get("title") or not vals.get("area"):
                    self._error(400, "Titel og område mangler"); return True
                cols = list(vals.keys())
                cur = db.execute(f"INSERT INTO meeting_actions ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
                                 [vals[c] for c in cols])
                aid = cur.fetchone()["id"]
                db.commit()
                self._json_response(self._action_rows(db, "AND a.id = %s", (aid,))[0], 201)
            elif method == "PUT" and rid is not None:
                vals = action_vals(body)
                if "status" in body:
                    vals["done_at"] = datetime.now() if body["status"] == "done" else None
                    vals["closed_in_meeting_id"] = body.get("closed_in_meeting_id") if body["status"] == "done" else None
                if vals:
                    sets = ", ".join(f"{k} = %s" for k in vals)
                    db.execute(f"UPDATE meeting_actions SET {sets} WHERE id = %s", list(vals.values()) + [rid])
                    db.commit()
                rows = self._action_rows(db, "AND a.id = %s", (rid,))
                if not rows:
                    self._error(404, "Aktion ikke fundet"); return True
                self._json_response(rows[0])
            elif method == "DELETE" and rid is not None:
                db.execute("DELETE FROM meeting_actions WHERE id = %s", (rid,))
                db.commit()
                self._no_content()
            else:
                self._error(404, "Endpoint not found")
            return True

        return False

    # ─── CEO-assistent: hvad mangler, hvad er over frist, og hvad bør CEO'en gøre ───
    def _assistant_checks(self, db):
        today = date.today()
        iso = today.isoformat()
        out = []
        area_label = {"salg": "Salg & marketing", "leverance": "Leverance", "oekonomi": "Økonomi", "tvaers": "Tværgående"}
        role = {"salg": "CCO", "leverance": "COO", "oekonomi": "CFO", "tvaers": "CEO"}

        def add(id, severity, area, title, detail, action, href, why=""):
            out.append({"id": id, "severity": severity, "area": area, "title": title, "detail": detail,
                        "why": why, "action": action, "href": href})

        # Mål
        goals = self._goal_rows(db, "AND NOT g.archived")
        for g in goals:
            gl = f"#/goals/{g['id']}"
            if g["status"] == "done":
                continue
            due = str(g.get("due_date") or "")[:10]
            if not due:
                add(f"goal-nodue-{g['id']}", "vigtig", g["area"], f"Målet \u201d{g['title']}\u201d har ingen deadline",
                    "Uden deadline kan systemet ikke vurdere, om I er bagud.", "Sæt en deadline", gl,
                    "Et mål uden tidsramme bliver sjældent fulgt op.")
            elif due < iso:
                add(f"goal-overdue-{g['id']}", "kritisk", g["area"], f"Målet \u201d{g['title']}\u201d er over deadline",
                    f"Deadline var {due}. Status: {g['status']}.", "Afslut, forlæng eller justér målet", gl,
                    "Beslut om målet er nået, skal forlænges med en ny plan, eller skal opgives.")
            if g.get("target_value") is None and not g.get("milestones_total"):
                add(f"goal-unmeasurable-{g['id']}", "vigtig", g["area"], f"Målet \u201d{g['title']}\u201d kan ikke måles",
                    "Der er hverken måltal eller milepæle.", "Tilføj måltal eller milepæle", gl,
                    "Uden noget at måle på bliver statusmøderne en vurdering af stemning.")
            if not g.get("owner_role"):
                add(f"goal-noowner-{g['id']}", "vigtig", g["area"], f"Målet \u201d{g['title']}\u201d har ingen ansvarlig",
                    "", "Vælg ansvarlig (CCO, COO, CFO eller CEO)", gl)
            if g.get("kind") == "strategisk" and not g.get("milestones_total"):
                add(f"goal-nomilestones-{g['id']}", "tips", g["area"], f"Det strategiske mål \u201d{g['title']}\u201d har ingen milepæle",
                    "Strategiske mål flytter sig bedst i konkrete skridt.", "Tilføj 2–3 milepæle", gl)
            ref = g.get("last_checkin") or str(g.get("created_at") or "")[:10]
            if ref and (today - date.fromisoformat(str(ref)[:10])).days > 30:
                add(f"goal-stale-{g['id']}", "vigtig", g["area"], f"\u201d{g['title']}\u201d er ikke fulgt op i over 30 dage",
                    f"Sidst opdateret {g.get('last_checkin') or 'aldrig'}.", f"Opdatér status, eller tag det op med {g.get('owner_role') or role.get(g['area'])}", gl)
            if g["status"] in ("off_track", "at_risk") and not g.get("open_actions"):
                add(f"goal-noaction-{g['id']}", "kritisk", g["area"], f"\u201d{g['title']}\u201d er {'bagud' if g['status'] == 'off_track' else 'i risiko'} uden en aktion",
                    "Der er ingen åbne aktioner, der skal bringe målet på sporet.", "Aftal en aktion med ansvarlig og frist", gl)
        # Hver leder skal have både kortsigtede og langsigtede mål
        for a, rl in (("salg", "CCO"), ("leverance", "COO"), ("oekonomi", "CFO")):
            kinds = {g["kind"] for g in goals if g["area"] == a}
            for kind, label in (("drift", "ingen kortsigtede mål"), ("strategisk", "intet langsigtet mål")):
                if kind not in kinds:
                    add(f"goal-missingkind-{a}-{kind}", "vigtig", a, f"{rl} har {label}",
                        "Indrapporteringen beder automatisk lederen om et forslag.",
                        f"Aftal {label.split(' ', 1)[1]} med {rl}", "#/goals")
        # Milepæle over frist
        for m in db.execute("""SELECT m.id, m.title, m.due_date, g.id AS goal_id, g.title AS goal_title, g.area
                               FROM goal_milestones m JOIN goals g ON m.goal_id = g.id
                               WHERE NOT m.done AND m.due_date < CURRENT_DATE AND NOT g.archived""").fetchall():
            add(f"ms-overdue-{m['id']}", "vigtig", m["area"], f"Milepælen \u201d{m['title']}\u201d er over frist",
                f"Del af målet \u201d{m['goal_title']}\u201d. Frist var {m['due_date']}.", "Afslut eller sæt ny frist", f"#/goals/{m['goal_id']}")
        # Lederenes opgaver: frist snart med lidt fremdrift, ingen status, meldt ikke startet, skubbet
        for t in self._task_followups(db):
            for sev, text in t["signals"]:
                if "over frist" in text or text == "ingen frist":
                    continue  # dækkes af tjekkene nedenfor
                who = t["role"] or t["owner"] or "ingen ansvarlig"
                add(f"task-{t['id']}-{text.split(' ')[0]}", sev, t["area"] or "tvaers", f"{t['title']} ({who}): {text}",
                    (f"Sidst: {t['last_note']}" if t.get("last_note") else "Der er ikke meldt status endnu."),
                    f"Bed {who} om status" if t["role"] in ("CCO", "COO", "CFO") else "Følg op på opgaven", "#/todo")
        # Aktioner
        for a in self._action_rows(db, "AND a.status = 'open' AND a.kind = 'aktion'"):
            href = f"#/goals/{a['goal_id']}" if a.get("goal_id") else (f"#/meetings/{a['meeting_id']}" if a.get("meeting_id") else "#/meetings")
            if a.get("due_date") and str(a["due_date"])[:10] < iso:
                add(f"action-overdue-{a['id']}", "kritisk", a["area"], f"Aktionen \u201d{a['title']}\u201d er over frist",
                    f"Ansvarlig: {a.get('owner') or 'ingen'}. Frist var {a['due_date']}.", "Følg op med den ansvarlige, eller sæt ny frist", href)
            elif not a.get("owner") or not a.get("due_date"):
                add(f"action-incomplete-{a['id']}", "vigtig", a["area"], f"Aktionen \u201d{a['title']}\u201d mangler " + ("ansvarlig" if not a.get("owner") else "frist"),
                    "", "Giv aktionen en ansvarlig og en frist", href)
        # Møder pr. område
        for area in ("salg", "leverance", "oekonomi", "tvaers"):
            last = db.execute("SELECT MAX(meeting_date) AS d FROM meetings WHERE area = %s AND status = 'done'", (area,)).fetchone()["d"]
            planned = db.execute("SELECT id, meeting_date, status FROM meetings WHERE area = %s AND status != 'done' ORDER BY meeting_date LIMIT 1", (area,)).fetchone()
            if planned and str(planned["meeting_date"])[:10] < iso:
                add(f"meeting-missed-{planned['id']}", "vigtig", area, f"Mødet med {role[area]} ({area_label[area]}) blev ikke afsluttet",
                    f"Det var planlagt {planned['meeting_date']}" + (" og er stadig i gang." if planned["status"] == "in_progress" else "."),
                    "Afhold og afslut mødet, eller flyt det", f"#/meetings/{planned['id']}")
            elif not planned and (not last or (today - last).days > 30):
                add(f"meeting-none-{area}", "kritisk" if area != "tvaers" else "vigtig", area,
                    f"Intet møde planlagt med {role[area]} ({area_label[area]})",
                    "Sidste møde: " + (str(last) if last else "aldrig") + ".", "Planlæg næste møde", "#/meetings",
                    "Faste møder er det, der gør opfølgningen konsekvent.")
        # Indrapporteringer
        for r in db.execute("""SELECT id, area, respondent_name, due_date, status, practice FROM report_rounds
                               WHERE status = 'open' AND NOT practice""").fetchall():
            if r["due_date"] and str(r["due_date"])[:10] < iso:
                add(f"report-late-{r['id']}", "vigtig", r["area"], f"{r['respondent_name']} har ikke indsendt indrapporteringen",
                    f"Svarfristen var {r['due_date']}.", "Send en påmindelse", f"#/reports/{r['id']}")
        for r in db.execute("""SELECT id, area, respondent_name, practice, followup_of FROM report_rounds
                               WHERE status = 'answered' AND reviewed_at IS NULL ORDER BY submitted_at DESC""").fetchall():
            add(f"report-new-{r['id']}", "vigtig", r["area"],
                f"{r['respondent_name']} har svaret" + (" på dine opfølgende spørgsmål" if r["followup_of"] else "") + (" (øvelse)" if r["practice"] else ""),
                "Svarene er klar til gennemsyn.", "Gennemse svarene", f"#/reports/{r['followup_of'] or r['id']}")
        for r in db.execute("SELECT id FROM report_rounds WHERE status = 'answered' AND NOT practice AND followup_of IS NULL ORDER BY submitted_at DESC LIMIT 5").fetchall():
            rnd = self._round_full(db, r["id"])
            sug = self._cleanup_suggestions(db, rnd)
            if sug:
                add(f"report-cleanup-{r['id']}", "vigtig", rnd["area"], f"{len(sug)} forslag til oprydning fra {rnd['respondent_name']}s indrapportering",
                    ", ".join(x["company_name"] for x in sug[:4]), "Gennemse og udfør", f"#/reports/{r['id']}")
            if not rnd.get("ai_assessment") and os.environ.get("ANTHROPIC_API_KEY"):
                add(f"report-noassess-{r['id']}", "tips", rnd["area"], f"Indrapporteringen fra {rnd['respondent_name']} er ikke vurderet",
                    "", "Lav AI-vurdering før mødet", f"#/reports/{r['id']}")
        # Tilbud og sager
        for t in db.execute("""SELECT t.id, t.title, t.deadline, t.status, co.name FROM tenders t JOIN companies co ON t.company_id = co.id
                               WHERE t.status IN ('draft','in_progress') AND t.deadline < CURRENT_DATE ORDER BY t.deadline""").fetchall():
            add(f"tender-overdue-{t['id']}", "vigtig", "salg", f"Tilbuddet til {t['name']} er over deadline",
                f"\u201d{t['title']}\u201d, deadline {t['deadline']}, status stadig {t['status']}.", "Opdatér status: indsendt, udskudt, tabt eller droppet", f"#/tenders/{t['id']}")
        late = db.execute("""SELECT COALESCE(area,'salg') AS area, COUNT(*) AS n FROM tasks
                             WHERE status != 'done' AND due_date < CURRENT_DATE GROUP BY COALESCE(area,'salg')""").fetchall()
        for r in late:
            add(f"tasks-late-{r['area']}", "vigtig" if r["n"] < 5 else "kritisk", r["area"], f"{r['n']} sager over frist inden for {area_label[r['area']].lower()}",
                "", f"Gennemgå dem med {role[r['area']]}, eller luk dem der er afklaret", f"#/area/{r['area']}")
        dup = db.execute("""SELECT co.name, t.title, COUNT(*) AS n, MIN(t.id) AS id FROM tenders t JOIN companies co ON t.company_id = co.id
                            WHERE t.status NOT IN ('won','lost','dropped') GROUP BY co.name, t.title HAVING COUNT(*) > 1""").fetchall()
        for d in dup:
            add(f"tender-dup-{d['id']}", "tips", "salg", f"{d['n']} ens tilbud til {d['name']}", f"\u201d{d['title']}\u201d. Er det dubletter?",
                "Slå dem sammen til ét", f"#/tenders/{d['id']}")
        missing_type = db.execute("""SELECT COUNT(DISTINCT co.id) AS n FROM companies co
                                     WHERE NOT COALESCE(co.is_purchasing_group, FALSE) AND co.sales_type IS NULL
                                       AND co.id IN (SELECT company_id FROM tenders WHERE status NOT IN ('won','lost','dropped'))""").fetchone()["n"]
        if missing_type:
            add("customers-notype", "tips", "salg", f"{missing_type} kunder med åbne tilbud mangler salgsform",
                "Systemet ved ikke, om det er direkte salg eller udbud.", "Bed CCO om indrapportering. Det klares i én klik-liste", "#/meetings")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            add("setup-ai", "tips", "tvaers", "AI er ikke slået til", "AI-spørgsmål, opfølgning, vurderinger og assistentens råd kræver en API-nøgle.",
                "Tilføj ANTHROPIC_API_KEY i Vercel", "#/meetings")

        snoozed = json.loads(self._setting(db, "assistant_snoozed", "{}") or "{}")
        active = [x for x in out if not (snoozed.get(x["id"]) and snoozed[x["id"]] >= iso)]
        order = {"kritisk": 0, "vigtig": 1, "tips": 2}
        active.sort(key=lambda x: order[x["severity"]])
        return active, len(out) - len(active)

    ROLE_AREA = {"CCO": "salg", "COO": "leverance", "CFO": "oekonomi", "CEO": "tvaers"}

    def _task_followups(self, db):
        """Signaler for lederenes åbne opgaver: over frist, frist snart med lidt fremdrift, ingen status længe,
        meldt 'ikke startet' / 'ved ikke' i seneste indrapportering, og skubbet videre."""
        today = date.today()
        # Seneste status fra indrapporteringernes opgaveliste pr. opgave
        reported = {}
        for r in db.execute("""SELECT ri.context, ri.answer, rr.submitted_at FROM report_items ri JOIN report_rounds rr ON ri.round_id = rr.id
                               WHERE ri.kind = 'matrix' AND ri.context->>'target' = 'tasks' AND rr.submitted_at IS NOT NULL AND NOT rr.practice
                               ORDER BY rr.submitted_at""").fetchall():
            for k, v in ((r["answer"] or {}).get("rows") or {}).items():
                if v:
                    reported[int(k)] = {"status": v, "date": r["submitted_at"].date().isoformat(), "note": ((r["answer"] or {}).get("notes") or {}).get(k)}
        carried = {}
        for mt in db.execute("SELECT notes FROM meetings").fetchall():
            for aid in (mt["notes"] or {}).get("carried") or []:
                carried[aid] = carried.get(aid, 0) + 1
        out = []
        for a in self._action_rows(db, "AND a.status = 'open' AND a.kind = 'aktion'"):
            owner = (a.get("owner") or "").strip()
            role = next((r for r in ("CCO", "COO", "CFO", "CEO") if owner.upper().startswith(r)), None)
            cl = a.get("checklist") or []
            done_n = sum(1 for c in cl if c.get("done"))
            due = str(a["due_date"])[:10] if a.get("due_date") else None
            days_left = (date.fromisoformat(due) - today).days if due else None
            notes = (a.get("notes") or "").strip().split("\n")
            last_note_date = notes[-1][:10] if notes and notes[-1][:4].isdigit() else None
            rep_ = reported.get(a["id"])
            last_status = max([d for d in (last_note_date, rep_["date"] if rep_ else None) if d], default=None)
            created = a["created_at"].date() if a.get("created_at") else today
            days_silent = (today - (date.fromisoformat(last_status) if last_status else created)).days
            signals = []
            if days_left is not None and days_left < 0:
                signals.append(("kritisk", f"{-days_left} dage over frist"))
            elif days_left is not None and days_left <= 7 and (not cl or done_n / len(cl) < 0.5) and not (rep_ and rep_["status"] == "i_gang" and rep_["date"] >= (today - timedelta(days=7)).isoformat()):
                signals.append(("vigtig", f"frist om {days_left} dage" + (f", {done_n} af {len(cl)} punkter" if cl else ", ingen status på fremdrift")))
            if rep_ and rep_["status"] in ("ikke_startet", "ved_ikke") and (days_left is None or days_left <= 14):
                signals.append(("vigtig", f"meldt '{'ikke startet' if rep_['status'] == 'ikke_startet' else 'ved ikke'}' {rep_['date']}"))
            if days_silent >= 14:
                signals.append(("tips" if days_left is None or days_left > 14 else "vigtig", f"ingen status i {days_silent} dage"))
            if carried.get(a["id"], 0) >= 2:
                signals.append(("vigtig", f"skubbet videre {carried[a['id']]} gange"))
            if not due:
                signals.append(("tips", "ingen frist"))
            out.append({"id": a["id"], "title": a["title"], "owner": owner or None, "role": role, "area": a.get("area"),
                        "due_date": due, "days_left": days_left, "checklist": f"{done_n}/{len(cl)}" if cl else None,
                        "last_report": rep_, "days_silent": days_silent, "signals": signals,
                        "goal_title": a.get("goal_title"), "last_note": notes[-1] if notes and notes[-1] else None})
        return out

    def _followup_settings(self, db):
        cfg = json.loads(self._setting(db, "task_followup", "{}") or "{}")
        cfg.setdefault("role_users", {})
        cfg.setdefault("auto", {})
        return cfg

    def _draft_followup_message(self, db, role, name, tasks, link):
        """Kort, venlig og konkret besked til lederen om de opgaver, der halter (AI når den er slået til)."""
        first = (name or role).split(" ")[0]
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                system = ("Du skriver på vegne af CEO'en i Systemate en kort, venlig og direkte besked (Slack-stil, 2–5 linjer, ingen emojis ud over evt. én) "
                          "til en leder om status på deres opgaver. Nævn de konkrete opgaver og hvorfor du spørger (frist, manglende fremdrift, "
                          "ingen status). Ingen bebrejdelser. Slut med at bede dem melde status via linket, som tilføjes automatisk bagefter. "
                          "Skriv kun selve beskeden, uden linket.")
                text, _ = self._claude(system, json.dumps({"leder": first, "rolle": role, "opgaver": [
                    {"titel": t["title"], "frist": t["due_date"], "tjekliste": t["checklist"], "signaler": [x[1] for x in t["signals"]],
                     "seneste": t["last_note"]} for t in tasks]}, ensure_ascii=False), effort="low", max_tokens=800)
                return f"{text.strip()}\n{link}"
            except Exception as e:
                print(f"followup draft failed: {e}")
        lines = [f"Hej {first}", "Jeg vil gerne høre, hvordan det går med:"]
        for t in tasks[:6]:
            why = ", ".join(x[1] for x in t["signals"] if x[0] in ("kritisk", "vigtig")) or (f"frist {t['due_date']}" if t["due_date"] else "")
            lines.append(f"• {t['title']}" + (f" ({why})" if why else ""))
        lines.append(f"Meld gerne status her, det tager et minut: {link}")
        return "\n".join(lines)

    def _create_task_status_request(self, db, role, base_url, send_slack=False, auto=False):
        """Opretter en statusforespørgsel kun om lederens opgaver og en besked til lederen."""
        import secrets
        cfg = self._followup_settings(db)
        uid = cfg["role_users"].get(role)
        user = db.execute("SELECT id, name, email FROM users WHERE id = %s", (uid,)).fetchone() if uid else None
        if not user:
            raise ValueError(f"Vælg hvem der er {role} under Opgaver")
        area = self.ROLE_AREA[role]
        tasks = [t for t in self._task_followups(db) if t["role"] == role or (t["owner"] or "").lower().startswith(user["name"].split(" ")[0].lower())]
        if not tasks:
            raise ValueError(f"{role} har ingen åbne opgaver")
        cur = db.execute("""INSERT INTO report_rounds (area, respondent_user_id, respondent_name, token, due_date, status)
                            VALUES (%s,%s,%s,%s,%s,'open') RETURNING id, token""",
                         (area, user["id"], user["name"], secrets.token_urlsafe(24), (date.today() + timedelta(days=2)).isoformat()))
        row = cur.fetchone()
        self._build_report_items(db, row["id"], area, user["id"], tasks_only=True)
        link = f"{base_url.rstrip('/')}/r/{row['token']}"
        flagged = [t for t in tasks if any(sv in ("kritisk", "vigtig") for sv, _ in t["signals"])] or tasks
        message = self._draft_followup_message(db, role, user["name"], flagged, link)
        db.execute("UPDATE report_rounds SET message = %s WHERE id = %s", (message, row["id"]))
        sent = False
        if send_slack and os.environ.get("SLACK_BOT_TOKEN") and user["email"]:
            try:
                self._slack_dm(user["email"], message)
                db.execute("UPDATE report_rounds SET sent_at = CURRENT_TIMESTAMP WHERE id = %s", (row["id"],))
                sent = True
            except Exception as e:
                print(f"slack failed: {e}")
        if auto:
            db.execute("""INSERT INTO notifications (company_id, type, title, message, link) VALUES (NULL, 'report', %s, %s, %s)""",
                       (f"AI har fulgt op på {role}s opgaver" if sent else f"Statusforespørgsel til {role} er klar",
                        (f"Sendt i Slack til {user['name']} om {len(flagged)} opgave{'' if len(flagged) == 1 else 'r'}." if sent
                         else f"{len(flagged)} opgave{' halter' if len(flagged) == 1 else 'r halter'}. Beskeden er klar under Opgaver: kopiér den og send den til {user['name']}."),
                        "#/todo"))
        db.commit()
        return {"round_id": row["id"], "token": row["token"], "link": link, "message": message, "sent": sent,
                "respondent": user["name"], "tasks": [t["title"] for t in flagged]}

    def _handle_task_followup(self, db, method, path, body):
        base = f"https://{self.headers.get('X-Forwarded-Host') or self.headers.get('Host')}"
        if path == "/api/ceo/followup-settings":
            cfg = self._followup_settings(db)
            if method == "PUT":
                for key in ("role_users", "auto", "base_url"):
                    if key in body:
                        cfg[key] = body[key]
                db.execute("""INSERT INTO app_settings (key, value, updated_at) VALUES ('task_followup', %s, CURRENT_TIMESTAMP)
                              ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP""", (json.dumps(cfg),))
                db.commit()
            tf = self._task_followups(db)
            summary = {r: {"open": sum(1 for t in tf if t["role"] == r),
                           "flagged": sum(1 for t in tf if t["role"] == r and any(sv in ("kritisk", "vigtig") for sv, _ in t["signals"])),
                           "last_request": (lambda x: x["created_at"].date().isoformat() if x else None)(db.execute(
                               """SELECT created_at FROM report_rounds WHERE respondent_user_id = %s AND area = %s
                                  ORDER BY created_at DESC LIMIT 1""", (cfg["role_users"].get(r), self.ROLE_AREA[r])).fetchone()),
                           # Forespørgsel der er lavet (fx automatisk) men ikke sendt endnu
                           "pending": (lambda x: dict(x) if x else None)(db.execute(
                               """SELECT id AS round_id, token, message, respondent_name AS respondent FROM report_rounds
                                  WHERE respondent_user_id = %s AND area = %s AND status = 'open' AND sent_at IS NULL AND message IS NOT NULL
                                  ORDER BY created_at DESC LIMIT 1""", (cfg["role_users"].get(r), self.ROLE_AREA[r])).fetchone())}
                       for r in ("CCO", "COO", "CFO")}
            self._json_response({**cfg, "summary": summary, "signals": {t["id"]: t["signals"] for t in tf},
                                 "slack": bool(os.environ.get("SLACK_BOT_TOKEN")),
                                 "ai": bool(os.environ.get("ANTHROPIC_API_KEY"))})
        elif path == "/api/ceo/followup" and method == "POST":
            try:
                res = self._create_task_status_request(db, body.get("role"), body.get("origin") or base, send_slack=bool(body.get("send_slack")))
            except ValueError as e:
                db.rollback(); self._error(400, str(e)); return True
            self._json_response(res, 201)
        elif path == "/api/cron/task-followup":
            # Køres af Vercel Cron hver hverdagsmorgen. Følger kun op for roller, hvor CEO'en har slået automatisk opfølgning til.
            secret = os.environ.get("CRON_SECRET")
            if secret and self.headers.get("Authorization") != f"Bearer {secret}":
                self._error(401, "Ikke tilladt"); return True
            cfg = self._followup_settings(db)
            # Linket skal pege på den adresse, CEO'en selv bruger (gemt fra browseren), ikke på cron-kaldets interne adresse
            base_url = os.environ.get("PUBLIC_BASE_URL") or cfg.get("base_url") or base
            done = []
            for role, on in cfg["auto"].items():
                if not on or not cfg["role_users"].get(role):
                    continue
                recent = db.execute("""SELECT 1 FROM report_rounds WHERE respondent_user_id = %s AND area = %s
                                       AND created_at >= NOW() - INTERVAL '3 days'""", (cfg["role_users"][role], self.ROLE_AREA[role])).fetchone()
                flagged = [t for t in self._task_followups(db) if t["role"] == role and any(sv in ("kritisk", "vigtig") for sv, _ in t["signals"])]
                if recent or not flagged:
                    continue
                try:
                    r = self._create_task_status_request(db, role, base_url, send_slack=True, auto=True)
                    done.append({"role": role, "sent": r["sent"], "tasks": len(r["tasks"])})
                except ValueError:
                    db.rollback()
            self._json_response({"followed_up": done})
        else:
            self._error(404, "Endpoint not found")
        return True

    def _leadership_mirror(self, db):
        """Lederspejl: hvordan CEO'en faktisk leder ud fra møder, aktioner, mål og indrapporteringer."""
        today = date.today()
        d30, d90 = (today - timedelta(days=30)).isoformat(), (today - timedelta(days=90)).isoformat()
        areas = {"salg": "Salg & marketing", "leverance": "Leverance", "oekonomi": "Økonomi"}
        role = {"salg": "CCO", "leverance": "COO", "oekonomi": "CFO"}
        m = {}
        # Møder
        held = {a: db.execute("SELECT COUNT(*) AS n, MAX(meeting_date) AS last FROM meetings WHERE area = %s AND status = 'done' AND meeting_date >= %s",
                              (a, d90)).fetchone() for a in list(areas) + ["tvaers"]}
        m["meetings_90"] = {a: held[a]["n"] for a in held}
        m["last_meeting"] = {a: (str(held[a]["last"]) if held[a]["last"] else None) for a in held}
        done_meetings = [dict(r) for r in db.execute("SELECT id, area, notes FROM meetings WHERE status = 'done' AND meeting_date >= %s", (d90,)).fetchall()]
        incomplete = 0
        for mt in done_meetings:
            goals_n = db.execute("SELECT COUNT(*) AS n FROM goals WHERE NOT archived AND (area = %s OR (%s = 'tvaers' AND kind = 'strategisk'))",
                                 (mt["area"], mt["area"])).fetchone()["n"]
            checked = db.execute("SELECT COUNT(DISTINCT goal_id) AS n FROM goal_checkins WHERE meeting_id = %s", (mt["id"],)).fetchone()["n"]
            if goals_n and checked < goals_n:
                incomplete += 1
        m["meetings_done_90"] = len(done_meetings)
        m["meetings_incomplete"] = incomplete
        m["decisions_90"] = db.execute("""SELECT COUNT(*) AS n FROM meeting_actions a JOIN meetings mt ON a.meeting_id = mt.id
                                          WHERE a.kind = 'beslutning' AND mt.meeting_date >= %s""", (d90,)).fetchone()["n"]
        # Aktioner
        acts = [dict(r) for r in db.execute("""SELECT id, owner, due_date, status, done_at, created_at FROM meeting_actions
                                               WHERE kind = 'aktion' AND created_at >= %s""", (d90,)).fetchall()]
        due_passed = [a for a in acts if a["due_date"] and str(a["due_date"]) < today.isoformat()]
        on_time = [a for a in due_passed if a["status"] == "done" and a["done_at"] and a["done_at"].date() <= a["due_date"]]
        m["actions_90"] = len(acts)
        m["actions_due_passed"] = len(due_passed)
        m["actions_on_time_pct"] = round(len(on_time) / len(due_passed) * 100) if due_passed else None
        carried = {}
        for mt in done_meetings + [dict(r) for r in db.execute("SELECT id, area, notes FROM meetings WHERE status != 'done'").fetchall()]:
            for aid in (mt.get("notes") or {}).get("carried") or []:
                carried[aid] = carried.get(aid, 0) + 1
        m["actions_pushed_twice"] = sum(1 for v in carried.values() if v >= 2)
        ceo_open = [a for a in self._action_rows(db, "AND a.status = 'open' AND a.kind = 'aktion' AND a.owner ILIKE 'CEO%%'")]
        m["ceo_actions_open"] = len(ceo_open)
        m["ceo_actions_overdue"] = sum(1 for a in ceo_open if a.get("due_date") and str(a["due_date"])[:10] < today.isoformat())
        m["ceo_actions_overdue_titles"] = [a["title"] for a in ceo_open if a.get("due_date") and str(a["due_date"])[:10] < today.isoformat()][:5]
        # Mål
        goals = self._goal_rows(db, "AND NOT g.archived AND g.status != 'done'")
        m["goals"] = len(goals)
        m["goals_updated_30"] = sum(1 for g in goals if g.get("last_checkin") and str(g["last_checkin"]) >= d30)
        m["strategic_unmoved"] = [g["title"] for g in goals if g["kind"] == "strategisk" and not g.get("last_checkin")
                                  and (g.get("current_value") in (None, g.get("start_value")))]
        # Mål pr. leder: kortsigtede og langsigtede, hvor konkrete, og om de bliver fulgt op
        leaders = {}
        for a in areas:
            gl = [g for g in goals if g["area"] == a]
            last = max((str(g["last_checkin"]) for g in gl if g.get("last_checkin")), default=None)
            leaders[a] = {"role": role[a], "drift": sum(1 for g in gl if g["kind"] == "drift"),
                          "strategisk": sum(1 for g in gl if g["kind"] == "strategisk"),
                          "quality": round(sum(g["quality"] for g in gl) / len(gl)) if gl else None,
                          "unclear": [{"title": g["title"], "missing": g["quality_missing"]} for g in gl if g["quality"] < 60],
                          "last_update": last,
                          "stale": sum(1 for g in gl if not g.get("last_checkin") or str(g["last_checkin"]) < d30)}
        tf = self._task_followups(db)
        for a, L in leaders.items():
            mine = [t for t in tf if t["role"] == L["role"]]
            L["tasks_open"] = len(mine)
            L["tasks_overdue"] = sum(1 for t in mine if t["days_left"] is not None and t["days_left"] < 0)
            L["tasks_flagged"] = sum(1 for t in mine if any(sv in ("kritisk", "vigtig") for sv, _ in t["signals"]))
        m["leaders"] = leaders

        # Opmærksomhed pr. område (møder, statusopdateringer og aktioner de sidste 30 dage)
        att = {}
        for a in areas:
            att[a] = (db.execute("SELECT COUNT(*) AS n FROM meetings WHERE area = %s AND meeting_date >= %s AND status != 'planned'", (a, d30)).fetchone()["n"] * 3
                      + db.execute("""SELECT COUNT(*) AS n FROM goal_checkins c JOIN goals g ON c.goal_id = g.id
                                      WHERE g.area = %s AND c.checkin_date >= %s""", (a, d30)).fetchone()["n"]
                      + db.execute("SELECT COUNT(*) AS n FROM meeting_actions WHERE area = %s AND created_at >= %s", (a, d30)).fetchone()["n"]
                      + db.execute("SELECT COUNT(*) AS n FROM report_rounds WHERE area = %s AND created_at >= %s", (a, d30)).fetchone()["n"] * 2)
        total = sum(att.values())
        m["attention_pct"] = {a: (round(v / total * 100) if total else 0) for a, v in att.items()}
        # Indrapporteringer
        m["reports_30"] = db.execute("SELECT COUNT(*) AS n FROM report_rounds WHERE created_at >= %s AND followup_of IS NULL AND NOT practice", (d30,)).fetchone()["n"]
        m["reports_unreviewed_3d"] = db.execute("""SELECT COUNT(*) AS n FROM report_rounds WHERE status = 'answered' AND reviewed_at IS NULL
                                                   AND submitted_at < NOW() - INTERVAL '3 days'""").fetchone()["n"]
        m["followups_30"] = db.execute("SELECT COUNT(*) AS n FROM report_rounds WHERE followup_of IS NOT NULL AND created_at >= %s", (d30,)).fetchone()["n"]
        snoozed = json.loads(self._setting(db, "assistant_snoozed", "{}") or "{}")
        m["snoozed_now"] = sum(1 for v in snoozed.values() if v >= today.isoformat())

        # Observationer: det gode og det, der kan blive bedre
        obs = []
        def o(kind, title, detail, href=None):
            obs.append({"kind": kind, "title": title, "detail": detail, "href": href})
        for a in areas:
            last = m["last_meeting"][a]
            if not last or last < d30:
                o("udfordring", f"Du har ikke holdt møde med {role[a]} om {areas[a].lower()} i over 30 dage",
                  "Uden faste møder er opfølgningen afhængig af, hvad der tilfældigvis kommer op." + (f" Sidste møde: {last}." if last else " Der er aldrig holdt et."), "#/meetings")
        if total and max(m["attention_pct"].values()) >= 60:
            top = max(m["attention_pct"], key=m["attention_pct"].get)
            low = [areas[a] for a, v in m["attention_pct"].items() if v <= 15]
            if low:
                o("udfordring", f"Din opmærksomhed er skæv: {m['attention_pct'][top]} % går til {areas[top].lower()}",
                  f"{', '.join(low)} får næsten ingen opfølgning. Er det et bevidst valg?")
        if m["actions_on_time_pct"] is not None and m["actions_due_passed"] >= 4:
            if m["actions_on_time_pct"] < 60:
                o("udfordring", f"Kun {m['actions_on_time_pct']} % af aktionerne lukkes til tiden",
                  "Overvej færre og skarpere aktioner med realistiske frister, og følg op på dem på hvert møde.")
            elif m["actions_on_time_pct"] >= 80:
                o("styrke", f"{m['actions_on_time_pct']} % af aktionerne lukkes til tiden", "Opfølgningen virker. Hold fast i rytmen.")
        if m["actions_pushed_twice"]:
            o("udfordring", f"{m['actions_pushed_twice']} aktioner er skubbet videre mindst to gange",
              "Når en aktion bliver ved med at 'fortsætte', er den enten for stor, uklar eller ikke vigtig. Beslut hvilken.", "#/meetings")
        if m["ceo_actions_overdue"]:
            o("udfordring", f"Du er selv bagud på {m['ceo_actions_overdue']} aktion" + ("er" if m["ceo_actions_overdue"] > 1 else ""),
              "Du sætter standarden for, hvordan der følges op. " + "; ".join(m["ceo_actions_overdue_titles"]))
        elif m["actions_90"] >= 5 and not m["ceo_actions_open"] and not any((a.get("owner") or "").upper().startswith("CEO") for a in acts):
            o("refleksion", "Du har ingen aktioner selv", "Alt er uddelegeret. Hvad er det, kun du kan gøre for at flytte målene?")
        for a, L in m["leaders"].items():
            if not L["drift"] and not L["strategisk"]:
                o("udfordring", f"{L['role']} har ingen mål", f"Uden mål for {areas[a].lower()} kan du ikke holde {L['role']} op på noget konkret. Aftal 2–3 kortsigtede og ét langsigtet mål.", "#/goals")
                continue
            if not L["drift"]:
                o("udfordring", f"{L['role']} har ingen kortsigtede mål", "Kortsigtede driftsmål (de næste 3–12 måneder) gør det muligt at se, om I er på sporet nu.", "#/goals")
            if not L["strategisk"]:
                o("udfordring", f"{L['role']} har intet langsigtet mål", f"Hvor skal {areas[a].lower()} være om 2–3 år? Uden et strategisk mål handler møderne kun om drift.", "#/goals")
            if L["quality"] is not None and L["quality"] < 60:
                mangler = sorted({x for u in L["unclear"] for x in u["missing"]})
                o("udfordring", f"{L['role']}'s mål er ikke konkrete nok ({L['quality']} %)",
                  "Der mangler bl.a. " + ", ".join(mangler[:4]) + ". Uklare mål giver uklar opfølgning.", "#/goals")
            if L["stale"] and L["stale"] * 2 >= L["drift"] + L["strategisk"]:  # mindst halvdelen er ikke fulgt op
                o("refleksion", f"{L['role']}'s mål bliver ikke fulgt op", f"{L['stale']} af {L['drift'] + L['strategisk']} mål er ikke opdateret de sidste 30 dage." + (f" Sidst opdateret {L['last_update']}." if L["last_update"] else ""), "#/goals")
            if L.get("tasks_overdue"):
                o("udfordring", f"{L['role']} har {L['tasks_overdue']} opgave{'r' if L['tasks_overdue'] > 1 else ''} over frist",
                  "Bed om status, og aftal en ny realistisk frist eller hjælp, så opgaven ikke bliver ved med at glide.", "#/todo")
            if L["quality"] is not None and L["quality"] >= 80 and not L["stale"]:
                o("styrke", f"{L['role']}'s mål er konkrete og fulgt op", f"Gennemsnitlig målkvalitet {L['quality']} %.")
        if m["goals"] and m["goals_updated_30"] / m["goals"] < 0.5:
            o("udfordring", f"Kun {m['goals_updated_30']} af {m['goals']} mål er opdateret de sidste 30 dage",
              "Mål, der ikke bliver fulgt op, bliver til ønsker. Brug ledermøderne til at opdatere dem.", "#/goals")
        if m["strategic_unmoved"]:
            o("udfordring", "Strategien flytter sig ikke", "Disse strategiske mål har ikke haft nogen statusopdatering: " + ", ".join(m["strategic_unmoved"][:3]) + ".", "#/goals")
        if m["meetings_done_90"] and not m["decisions_90"]:
            o("refleksion", "Dine møder registrerer ingen beslutninger", "Bliver der truffet beslutninger, som ikke bliver skrevet ned, eller bliver der ikke besluttet noget?")
        if m["meetings_incomplete"]:
            n = m['meetings_incomplete']
            o("refleksion", f"{n} møde{'' if n == 1 else 'r'} er afsluttet, uden at alle mål blev opdateret", "Er dagsordenen for lang, eller springes målene over, når tiden er knap?")
        if m["snoozed_now"] >= 5:
            o("refleksion", f"Du har udsat {m['snoozed_now']} punkter hos assistenten", "Udsættelse er fint, men mange udsatte punkter kan være et tegn på, at noget skal uddelegeres eller droppes.")
        if m["reports_unreviewed_3d"]:
            o("udfordring", f"{m['reports_unreviewed_3d']} indrapporteringer har ligget ulæst i over 3 dage",
              "Når svarene ikke bliver læst, mister lederne motivationen til at svare grundigt.")
        if m["followups_30"]:
            o("styrke", f"Du har stillet opfølgende spørgsmål {m['followups_30']} gang" + ("e" if m["followups_30"] > 1 else "") + " den sidste måned",
              "Du går i dybden med svarene. Det skaber bedre indrapporteringer.")
        if all(m["last_meeting"][a] and m["last_meeting"][a] >= d30 for a in areas):
            o("styrke", "Du har holdt møde med alle tre ledere den sidste måned", "Rytmen er på plads.")
        order = {"udfordring": 0, "refleksion": 1, "styrke": 2}
        obs.sort(key=lambda x: order[x["kind"]])
        return {"metrics": m, "observations": obs}

    def _assistant_snapshot(self, db, checks):
        """Kompakt billede af virksomheden til AI-rådgivning."""
        goals = [{"titel": g["title"], "område": g["area"], "type": g["kind"], "ansvarlig": g.get("owner_role"), "status": g["status"],
                  "nu": g.get("current_value"), "mål": g.get("target_value"), "enhed": g.get("unit"), "deadline": g.get("due_date"),
                  "sidst_opdateret": g.get("last_checkin"), "milepæle": f"{g.get('milestones_done')}/{g.get('milestones_total')}"}
                 for g in self._goal_rows(db, "AND NOT g.archived")]
        actions = [{"titel": t["title"], "område": t["area"], "ansvarlig": t["owner"], "frist": t["due_date"],
                    "dage_til_frist": t["days_left"], "tjekliste": t["checklist"], "dage_uden_status": t["days_silent"],
                    "seneste_melding": t["last_report"], "seneste_note": t["last_note"], "signaler": [x[1] for x in t["signals"]]}
                   for t in self._task_followups(db)]
        meetings = [dict(r) for r in db.execute("""SELECT area, title, meeting_date, status FROM meetings
                                                   ORDER BY meeting_date DESC LIMIT 12""").fetchall()]
        tenders = [dict(r) for r in db.execute("""SELECT co.name AS kunde, t.title, t.status, t.deadline, t.estimated_value, t.purchase_route
                                                  FROM tenders t JOIN companies co ON t.company_id = co.id
                                                  WHERE t.status NOT IN ('lost','dropped') ORDER BY t.deadline NULLS LAST""").fetchall()]
        return {"dato": date.today().isoformat(), "mål": goals, "åbne_aktioner": actions, "møder": meetings,
                "tilbud": tenders, "assistentens_tjek": [{k: c[k] for k in ("severity", "area", "title", "detail", "action")} for c in checks]}

    def _handle_assistant(self, db, method, path, body):
        if path == "/api/ceo/assistant" and method == "GET":
            checks, snoozed = self._assistant_checks(db)
            counts = {s: sum(1 for c in checks if c["severity"] == s) for s in ("kritisk", "vigtig", "tips")}
            self._json_response({"items": checks, "counts": counts, "snoozed": snoozed,
                                 "ai": bool(os.environ.get("ANTHROPIC_API_KEY"))})
        elif path == "/api/ceo/assistant/mirror" and method == "GET":
            self._json_response(self._leadership_mirror(db))
        elif path == "/api/ceo/assistant/snooze" and method == "POST":
            snoozed = json.loads(self._setting(db, "assistant_snoozed", "{}") or "{}")
            snoozed = {k: v for k, v in snoozed.items() if v >= date.today().isoformat()}
            if body.get("id"):
                snoozed[body["id"]] = (date.today() + timedelta(days=int(body.get("days") or 7))).isoformat()
            if body.get("clear"):
                snoozed = {}
            db.execute("""INSERT INTO app_settings (key, value, updated_at) VALUES ('assistant_snoozed', %s, CURRENT_TIMESTAMP)
                          ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP""", (json.dumps(snoozed),))
            db.commit()
            self._json_response({"ok": True})
        elif path == "/api/ceo/assistant/ask" and method == "POST":
            if not os.environ.get("ANTHROPIC_API_KEY"):
                self._error(400, "AI er ikke slået til endnu (ANTHROPIC_API_KEY mangler i Vercel)"); return True
            checks, _ = self._assistant_checks(db)
            snapshot = self._assistant_snapshot(db, checks)
            if body.get("mode") == "coach":
                snapshot["lederspejl"] = self._leadership_mirror(db)
            coach = (
                "\n\nDU ER LIGE NU I SPARRINGSTILSTAND: Udfordr CEO'en som en erfaren, direkte sparringspartner eller mentor. "
                "Fokus er CEO'ens egen ledelse: rytme og konsekvens i opfølgningen, prioritering og fokus, delegering, "
                "beslutningskraft, om de svære samtaler bliver taget, og hvad der er tabt af syne. Brug lederspejlet og data som belæg. "
                "Vær ærlig og konkret, men respektfuld. Ingen floskler. Anerkend kort det, der virker. "
                "Slut altid med '## Én ting til denne uge' med én konkret handling, og '## Spørgsmål til dig selv' med 2–3 skarpe spørgsmål."
            ) if body.get("mode") == "coach" else ""
            system = (
                "Du er CEO-assistent i SystemateCEO for CEO'en i Systemate (software til forsynings- og energiselskaber). "
                "CEO'en følger op på tre områder med faste ledermøder: salg & marketing (CCO), leverance (COO) og økonomi (CFO), "
                "plus tværgående strategiske mål. Du vejleder om, hvad der mangler, hvad der er over frist, og hvad CEO'en konkret bør gøre.\n\n"
                f"CEO'ens salgsproces og fokus:\n{self._setting(db, 'sales_process', DEFAULT_SALES_PROCESS)}\n{self._setting(db, 'ceo_focus', '')}\n\n"
                "Regler: Svar på dansk, kort og handlingsorienteret. Nævn mål, kunder, aktioner og personer ved navn. "
                "Prioritér: hvad er vigtigst først, og hvorfor. Foreslå konkrete næste skridt med hvem og hvornår. "
                "Byg kun på data herunder. Gæt ikke, og sig det, hvis data mangler. Brug overskrifter (##) og punktlister.\n\n"
                "Data (JSON):\n" + json.dumps(snapshot, ensure_ascii=False, default=_json_default) + coach)
            history = [m for m in (body.get("history") or []) if m.get("role") in ("user", "assistant") and m.get("content")][-8:]
            question = (body.get("question") or "").strip() or "Hvad bør jeg fokusere på nu?"
            messages = history + [{"role": "user", "content": question}]
            try:
                text, model = self._claude_messages(system, messages)
            except Exception as e:
                self._error(502, f"Assistenten kunne ikke svare: {e}"); return True
            self._json_response({"answer": text, "model": model})
        else:
            self._error(404, "Endpoint not found")
        return True

    # ─── Indkøbsfællesskaber ───
    def _handle_groups(self, db, method, path, body, uid):
        parts = path.strip("/").split("/")  # ['api','companies','12','memberships','5']
        if path == "/api/purchasing-groups" and method == "GET":
            self._json_response([dict(r) for r in db.execute("""
                SELECT g.id, g.name, (SELECT COUNT(*) FROM company_memberships m WHERE m.group_id = g.id) AS member_count
                FROM companies g WHERE g.is_purchasing_group ORDER BY g.name""").fetchall()])
            return True
        cid = int(parts[2])
        if parts[3] == "group" and method == "PUT":
            db.execute("UPDATE companies SET is_purchasing_group = %s WHERE id = %s", (bool(body.get("is_purchasing_group")), cid))
            db.commit()
            self._json_response({"ok": True})
        elif parts[3] == "memberships" and method == "POST":
            group_id = int(body["group_id"])
            if group_id == cid:
                self._error(400, "En virksomhed kan ikke være medlem af sig selv"); return True
            db.execute("UPDATE companies SET is_purchasing_group = TRUE WHERE id = %s", (group_id,))
            db.execute("INSERT INTO company_memberships (company_id, group_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (cid, group_id))
            db.commit()
            log_audit(db, uid, "update", "company", cid, f"medlem af fællesskab {group_id}")
            db.commit()
            self._json_response({"ok": True}, 201)
        elif parts[3] == "memberships" and method == "DELETE" and len(parts) > 4:
            db.execute("DELETE FROM company_memberships WHERE company_id = %s AND group_id = %s", (cid, int(parts[4])))
            db.commit()
            self._no_content()
        else:
            self._error(404, "Endpoint not found")
        return True

    # ─── Indrapportering til ledermøder ───
    def _customer_priority(self, ctx):
        """Hvor vigtigt er det at spørge grundigt ind til kunden nu? Beløb, overskredne frister og tidligere problemer."""
        today = date.today().isoformat()
        score = 0
        for t in ctx["tenders"]:
            score += 3 if t.get("deadline") and str(t["deadline"])[:10] < today else 0
            score += 2 if t.get("deadline") and str(t["deadline"])[:10] <= (date.today() + timedelta(days=30)).isoformat() else 0
            v = int(_re.sub(r"\D", "", str(t.get("estimated_value") or "")) or 0)
            score += 3 if v >= 1_000_000 else 1 if v > 0 else 0
        score += sum(2 for t in ctx["tasks"] if t.get("due_date") and str(t["due_date"])[:10] < today)
        prev = ctx.get("previous_answer") or {}
        score += 2 if prev.get("status") in ("risiko", "kritisk", "udfordret") else 0
        score += 1 if not ctx.get("last_contact") else 0
        return score

    def _build_report_items(self, db, round_id, area, respondent_user_id=None, company_ids=None, only_customers=False, tasks_only=False):
        """Laver indrapporteringen ud fra data. Bedste svarform først: hurtige klik-lister til det, alle kunder skal svare på,
        grundige spørgsmål kun til de vigtigste kunder, og emner der blev udskudt sidst kommer med igen."""
        items = []
        # Emner der blev markeret "svarer senere" i forrige runde
        prev_round = db.execute("""SELECT id FROM report_rounds WHERE area = %s AND respondent_user_id = %s AND status != 'draft'
                                   AND submitted_at IS NOT NULL AND id != %s ORDER BY submitted_at DESC LIMIT 1""",
                                (area, respondent_user_id, round_id)).fetchone() if respondent_user_id else None
        if prev_round:
            for it in db.execute("SELECT * FROM report_items WHERE round_id = %s ORDER BY sort_order", (prev_round["id"],)).fetchall():
                if (it["answer"] or {}).get("later"):
                    ctx = dict(it["context"] or {})
                    ctx["carried"] = True
                    items.append((it["kind"], it["ref_type"], it["ref_id"], it["company_id"], it["title"], ctx))
        carried_companies = {i[3] for i in items if i[3]}

        customers = []
        if tasks_only:
            area = area  # kun opgavelisten nedenfor
        if area in ("salg", "leverance") and not tasks_only:
            if area == "salg":
                companies = db.execute("""
                    SELECT DISTINCT co.id, co.name, co.sales_stage, co.sales_type, co.sales_phase FROM companies co
                    WHERE NOT COALESCE(co.is_purchasing_group, FALSE) AND (
                          co.id IN (SELECT company_id FROM tenders WHERE status NOT IN ('won','lost','dropped'))
                       OR co.id IN (SELECT company_id FROM tasks WHERE status != 'done' AND COALESCE(area,'salg') = 'salg'))
                    ORDER BY co.name LIMIT 60""").fetchall()
            else:
                companies = db.execute("""
                    SELECT DISTINCT co.id, co.name, co.sales_stage, co.sales_type, co.sales_phase FROM companies co
                    WHERE co.id IN (SELECT company_id FROM tasks WHERE status != 'done' AND area = 'leverance')
                       OR co.id IN (SELECT company_id FROM goals WHERE NOT archived AND area = 'leverance' AND company_id IS NOT NULL)
                    ORDER BY co.name LIMIT 40""").fetchall()
            if company_ids:
                # CEO'en har valgt bestemte kunder (fx til en kort runde eller en test)
                wanted = {int(x) for x in company_ids}
                companies = [c for c in companies if c["id"] in wanted] + [
                    dict(r) for r in db.execute("""SELECT id, name, sales_stage, sales_type, sales_phase FROM companies
                                                   WHERE id = ANY(%s)""", (list(wanted),)).fetchall()
                    if r["id"] not in {c["id"] for c in companies}]
            for co in companies:
                cid = co["id"]
                tenders = [dict(r) for r in db.execute("""
                    SELECT t.id, t.title, t.status, t.deadline, t.estimated_value, t.purchase_route, g.name AS via_group
                    FROM tenders t LEFT JOIN companies g ON t.via_group_id = g.id
                    WHERE t.company_id = %s AND t.status NOT IN ('won','lost','dropped') ORDER BY t.deadline NULLS LAST""", (cid,)).fetchall()]
                groups = [r["name"] for r in db.execute(
                    """SELECT g.name FROM company_memberships m JOIN companies g ON m.group_id = g.id WHERE m.company_id = %s""", (cid,)).fetchall()]
                tasks = [dict(r) for r in db.execute("""
                    SELECT id, title, due_date, priority FROM tasks
                    WHERE company_id = %s AND status != 'done' AND COALESCE(area,'salg') = %s ORDER BY due_date NULLS LAST""",
                    (cid, area)).fetchall()]
                last = db.execute("""
                    SELECT MAX(d) AS d FROM (
                        SELECT i.date AS d FROM interactions i LEFT JOIN contacts ct ON i.contact_id = ct.id
                        WHERE COALESCE(i.company_id, ct.company_id) = %s
                        UNION ALL SELECT created_at::date FROM company_notes
                        WHERE company_id = %s AND content NOT LIKE 'Indrapporteret%%') x""", (cid, cid)).fetchone()
                prev = db.execute("""
                    SELECT ri.answer, rr.submitted_at FROM report_items ri JOIN report_rounds rr ON ri.round_id = rr.id
                    WHERE ri.company_id = %s AND ri.kind IN ('customer','topic') AND rr.area = %s AND ri.answer IS NOT NULL
                          AND rr.submitted_at IS NOT NULL
                    ORDER BY rr.submitted_at DESC NULLS LAST, ri.id DESC LIMIT 1""", (cid, area)).fetchone()
                ctx = {"tenders": tenders, "tasks": tasks, "sales_stage": co["sales_stage"], "member_of": groups,
                       "sales_type": co["sales_type"], "sales_phase": co["sales_phase"],
                       "last_contact": last["d"] if last else None,
                       "previous_answer": prev["answer"] if prev else None,
                       "previous_date": prev["submitted_at"] if prev else None}
                ctx["priority"] = self._customer_priority(ctx)
                customers.append((co, ctx))

        if area == "salg" and customers and not tasks_only:
            def hint(ctx):
                parts = []
                for t in ctx["tenders"][:1]:
                    parts.append(t["title"] + (f" · deadline {str(t['deadline'])[:10]}" if t.get("deadline") else ""))
                if not parts and ctx["tasks"]:
                    parts.append(ctx["tasks"][0]["title"])
                if ctx["member_of"]:
                    parts.append("medlem af " + ", ".join(ctx["member_of"]))
                return " · ".join(parts)
            rows = lambda lst, field: [{"company_id": co["id"], "name": co["name"], "hint": hint(ctx), "current": ctx.get(field)} for co, ctx in lst]
            unknown_type = [(co, ctx) for co, ctx in customers if not ctx["sales_type"] or ctx["sales_type"] == "ved_ikke"]
            if unknown_type:
                items.append(("matrix", None, None, None, "Direkte salg eller udbud?",
                              {"target": "sales_type", "input": "choice", "options": SALES_TYPES,
                               "hint": "Ét klik pr. kunde. Svaret gemmes på kunden, så du ikke bliver spurgt igen.",
                               "rows": rows(unknown_type, "sales_type")}))
            items.append(("matrix", None, None, None, "Hvor i forløbet er kunderne nu?",
                          {"target": "sales_phase", "input": "select", "options": SALES_PHASES,
                           "hint": "Vælg fasen for hver kunde. Står den rigtigt fra sidst, så tryk ”Alle uændrede”.",
                           "rows": rows(customers, "sales_phase")}))
            ranked = sorted(customers, key=lambda x: -x[1]["priority"])
            detailed = [c for c in ranked[:MAX_DETAILED_CUSTOMERS] if c[0]["id"] not in carried_companies]
            rest = [c for c in ranked[MAX_DETAILED_CUSTOMERS:] if c[0]["id"] not in carried_companies]
            if rest:
                items.append(("matrix", None, None, None, "Noget nyt hos disse kunder?",
                              {"target": "news", "input": "choice", "options": [["nej", "Nej"], ["ja", "Ja"]],
                               "hint": "De mindre presserende kunder. Svar ”Ja” for at skrive kort, hvad der er sket.",
                               "rows": rows(rest, "news")}))
            for co, ctx in sorted(detailed, key=lambda x: x[0]["name"]):
                items.append(("customer", "company", co["id"], co["id"], co["name"], ctx))
        else:
            for co, ctx in customers:
                if co["id"] not in carried_companies:
                    items.append(("customer", "company", co["id"], co["id"], co["name"], ctx))
        role = {"salg": "CCO", "leverance": "COO", "oekonomi": "CFO"}.get(area, "CEO")
        if not only_customers:
            # Lederens egne åbne opgaver som klik-liste (fx lønsamtaler), så CEO'en ved om de bliver gjort
            resp = db.execute("SELECT name FROM users WHERE id = %s", (respondent_user_id,)).fetchone() if respondent_user_id else None
            first = (resp["name"].split(" ")[0] if resp else None)
            tasks_open = self._action_rows(db, "AND a.status = 'open' AND a.kind = 'aktion' AND (a.owner ILIKE %s OR a.owner ILIKE %s)",
                                           (role + "%", (first or "§") + "%"))
            if tasks_open:
                items.append(("matrix", None, None, None, "Dine opgaver: hvordan står det til?",
                              {"target": "tasks", "input": "choice",
                               "options": [["done", "Udført"], ["i_gang", "I gang"], ["ikke_startet", "Ikke startet"], ["ved_ikke", "Ved ikke"]],
                               "hint": "Udførte opgaver bliver lukket. Er en opgave ikke udført, så skriv kort hvad der mangler.",
                               "rows": [{"company_id": t["id"], "name": t["title"],
                                         "hint": " · ".join(x for x in [f"frist {str(t['due_date'])[:10]}" if t.get("due_date") else "",
                                                                         "over frist" if t.get("due_date") and str(t["due_date"])[:10] < date.today().isoformat() else "",
                                                                         (f"{sum(1 for c in (t.get('checklist') or []) if c.get('done'))}/{len(t.get('checklist') or [])} punkter" if t.get("checklist") else "")] if x),
                                         "current": None} for t in tasks_open]}))
        area_goals = [] if (only_customers or tasks_only) else self._goal_rows(db, "AND NOT g.archived AND g.area = %s AND g.status != 'done'", (area,))
        for g in sorted(area_goals, key=lambda g: 0 if g["kind"] == "drift" else 1):
            ctx = {k: g.get(k) for k in ("kind", "unit", "start_value", "target_value", "current_value", "due_date",
                                          "status", "last_checkin", "last_comment", "milestones_total", "milestones_done", "start_date",
                                          "description", "quality_missing")}
            items.append(("goal", "goal", g["id"], g.get("company_id"), g["title"], ctx))
        if not only_customers and not tasks_only and area in ("salg", "leverance", "oekonomi"):
            kinds = {g["kind"] for g in area_goals}
            if "drift" not in kinds:
                items.append(("question", None, None, None, "Dine kortsigtede mål",
                              {"hint": "Du har ingen kortsigtede mål registreret. Hvad er dine 2–3 vigtigste mål for de næste 3–12 måneder, og hvordan måler vi dem (tal og dato)?"}))
            if "strategisk" not in kinds:
                items.append(("question", None, None, None, "Dit langsigtede mål",
                              {"hint": "Du har intet langsigtet mål registreret. Hvor skal dit område være om 2–3 år, og hvad er de første milepæle?"}))
            # Tværgående strategiske mål: hvad bidrager lederen med?
            for g in self._goal_rows(db, "AND NOT g.archived AND g.area = 'tvaers' AND g.status != 'done'"):
                items.append(("question", "goal", g["id"], None, f"Tværgående mål: {g['title']}",
                              {"hint": f"Hvad har du gjort for at flytte \u201d{g['title']}\u201d siden sidst, og hvad er dit næste bidrag?", "cross_goal": True}))
        for kind, title, ctx in ([] if (only_customers or tasks_only) else REPORT_QUESTIONS.get(area, [])):
            items.append((kind, None, None, None, title, ctx))
        for i, (kind, ref_type, ref_id, company_id, title, ctx) in enumerate(items):
            db.execute("""INSERT INTO report_items (round_id, kind, ref_type, ref_id, company_id, title, context, sort_order)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                       (round_id, kind, ref_type, ref_id, company_id, title, json.dumps(ctx, default=_json_default), i))

    @staticmethod
    def _answer_texts(a):
        texts = [v for k, v in a.items() if isinstance(v, str) and k not in ("status", "goal_status", "probability", "next_date")]
        fu = a.get("followup") or {}
        if fu.get("answer"):
            texts.append(fu["answer"])
        return texts

    def _report_flags(self, item):
        """Regelbaserede advarsler, så CEO'en ser uoverensstemmelser også uden AI-vurdering."""
        import re
        flags = []
        a = item.get("answer") or {}
        ctx = item.get("context") or {}
        today = date.today().isoformat()
        if not a:
            return ["Ikke besvaret"]
        if a.get("later"):
            return ["Svarer senere. Kommer med i næste indrapportering."]
        if item["kind"] == "matrix":
            rows = ctx.get("rows") or []
            vals = a.get("rows") or {}
            missing = [r["name"] for r in rows if not vals.get(str(r["company_id"]))]
            if missing:
                flags.append(f"{len(missing)} af {len(rows)} kunder ikke besvaret")
            unk = [r["name"] for r in rows if vals.get(str(r["company_id"])) == "ved_ikke"]
            if unk:
                flags.append("'Ved ikke' for: " + ", ".join(unk[:6]) + (" …" if len(unk) > 6 else ""))
            if ctx.get("target") == "sales_phase":
                for key, label in (("tabt", "tabt"), ("vundet", "vundet"), ("ikke_i_proces", "ikke i proces")):
                    names = [r["name"] for r in rows if vals.get(str(r["company_id"])) == key]
                    if names:
                        flags.append(f"Meldt {label}: " + ", ".join(names) + ". Se forslag til oprydning.")
            if ctx.get("target") == "tasks":
                notdone = [r["name"] for r in rows if vals.get(str(r["company_id"])) in ("ikke_startet", "ved_ikke")]
                if notdone:
                    flags.append("Ikke startet eller uklart: " + ", ".join(notdone[:5]))
                over = [r["name"] for r in rows if "over frist" in (r.get("hint") or "") and vals.get(str(r["company_id"])) != "done"]
                if over:
                    flags.append("Over frist og ikke udført: " + ", ".join(over[:5]))
            if ctx.get("target") == "news":
                yes = [r["name"] for r in rows if vals.get(str(r["company_id"])) == "ja" and not (a.get("notes") or {}).get(str(r["company_id"]))]
                if yes:
                    flags.append("Svarer 'ja' uden at skrive hvad: " + ", ".join(yes))
            return flags
        texts = self._answer_texts(a)
        unknown = [t for t in texts if UNKNOWN_RE.search(t)]
        if unknown:
            flags.append(f"Svarer 'ved ikke' {len(unknown)} gang" + ("e" if len(unknown) > 1 else ""))
        positive = a.get("status") in ("paa_sporet", "som_planlagt", "on_track") or a.get("goal_status") == "on_track"
        if positive and unknown:
            flags.append("Modstrid: vurderet som på sporet, men svarer 'ved ikke' på centrale spørgsmål")
        for t in texts:
            for m in re.finditer(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b|\b(20\d{2})-(\d{2})-(\d{2})\b", t):
                try:
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m.group(3) else date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
                except ValueError:
                    continue
                if (d - date.today()).days > 270:
                    flags.append(f"Nævner datoen {m.group(0)}, mere end 9 måneder ude. Tjek at den er rigtig.")
        fu = a.get("followup") or {}
        if fu.get("question") and not fu.get("answer"):
            flags.append("Opfølgende spørgsmål ikke besvaret" + (" (sprunget over)" if fu.get("skipped") else ""))
        if item["kind"] == "customer":
            if a.get("not_relevant"):
                return ["Markeret som ikke længere i proces. Overvej at lukke tilbud og sager."]
            prob = int(a.get("probability") or 0)
            last = str(ctx.get("last_contact") or "")[:10]
            days = (date.today() - date.fromisoformat(last)).days if last else None
            if a.get("status") in ("udfordret", "forsinket"):
                flags.append("Rapporteret som " + a["status"])
            if prob >= 75 and (days is None or days > 30):
                flags.append(f"Høj sandsynlighed ({prob}%), men ingen registreret kontakt " + ("nogensinde" if days is None else f"i {days} dage"))
            if not a.get("next_step"):
                flags.append("Intet næste skridt angivet")
            elif not a.get("next_date"):
                flags.append("Næste skridt uden dato")
            elif a.get("next_date") < today:
                flags.append("Datoen for næste skridt er allerede passeret")
            for t in ctx.get("tenders") or []:
                if t.get("deadline") and str(t["deadline"])[:10] < today and a.get("status") not in ("vundet", "tabt"):  # tilbud findes kun i salg
                    flags.append(f"Tilbuddet ”{t['title']}” er over deadline")
            prev = ctx.get("previous_answer") or {}
            if prev and prev.get("next_step") and prev.get("next_step") == a.get("next_step"):
                flags.append("Samme næste skridt som sidst. Står det stille?")
        elif item["kind"] == "marketing":
            if a.get("activities") and int(a.get("leads") or 0) == 0:
                flags.append("Aktiviteter, men ingen nye leads")
            if not a.get("next"):
                flags.append("Ingen plan for de næste 14 dage")
        elif item["kind"] == "topic":
            qs = (ctx.get("questions") or [])
            missing = [i for i in range(len(qs)) if not (a.get(f"q{i}") or "").strip()]
            if missing:
                flags.append(f"{len(missing)} af {len(qs)} spørgsmål ikke besvaret")
            if a.get("status") in ("risiko", "kritisk"):
                flags.append("Vurderet som " + a["status"])
            is_text = lambda q: not isinstance(q, dict) or q.get("answer_type", "text") == "text"
            short = [i for i in range(len(qs)) if is_text(qs[i]) and 0 < len((a.get(f"q{i}") or "").strip()) < 25 and not UNKNOWN_RE.search(a.get(f"q{i}") or "")]
            if short:
                flags.append("Meget korte svar på spørgsmål " + ", ".join(chr(97 + i) for i in short) + ". Spørg ind til dem på mødet.")
            src = ctx.get("source") or {}
            if ctx.get("source_kind") == "customer":
                prob = int(a.get("probability") or 0)
                last = str(src.get("last_contact") or "")[:10]
                days = (date.today() - date.fromisoformat(last)).days if last else None
                if prob >= 75 and (days is None or days > 30):
                    flags.append(f"Høj sandsynlighed ({prob}%), men ingen registreret kontakt " + ("nogensinde" if days is None else f"i {days} dage"))
                if prob >= 75 and a.get("status") == "kritisk":
                    flags.append("Modstrid: høj sandsynlighed, men vurderet som kritisk")
                if a.get("next_step") and not a.get("next_date"):
                    flags.append("Næste skridt uden dato")
                elif a.get("next_date") and a["next_date"] < today:
                    flags.append("Datoen for næste skridt er allerede passeret")
            if ctx.get("source_kind") == "goal" and a.get("goal_status") == "on_track" and src.get("target_value") is not None:
                exp = _goal_expected(src)
                start, target = float(src.get("start_value") or 0), float(src["target_value"])
                cur = float(a.get("value") or src.get("current_value") or start)
                prog = (cur - start) / (target - start) if target != start else 1
                if exp is not None and prog < exp - 0.2:
                    flags.append(f"Modstrid: 'På sporet', men fremdriften er {round(prog * 100)}% mod forventet {round(exp * 100)}%")
        elif item["kind"] == "goal":
            if a.get("status") in ("at_risk", "off_track"):
                flags.append("Målet er " + ("bagud" if a["status"] == "off_track" else "i risiko"))
            if ctx.get("current_value") is not None and a.get("value") not in (None, "") and \
                    float(a["value"]) == float(ctx["current_value"]) and ctx.get("last_checkin"):
                flags.append("Uændret værdi siden sidste opdatering")
        return flags

    def _round_full(self, db, rid, include_token=True):
        row = db.execute("""SELECT rr.*, u.email AS respondent_email, m.title AS meeting_title, m.meeting_date
                            FROM report_rounds rr LEFT JOIN users u ON rr.respondent_user_id = u.id
                            LEFT JOIN meetings m ON rr.meeting_id = m.id WHERE rr.id = %s""", (rid,)).fetchone()
        if not row:
            return None
        rnd = dict(row)
        if not include_token:
            rnd.pop("token", None)
        rnd["items"] = [dict(r) for r in db.execute(
            "SELECT * FROM report_items WHERE round_id = %s ORDER BY sort_order, id", (rid,)).fetchall()]
        for it in rnd["items"]:
            it["flags"] = self._report_flags(it)
        return rnd

    OUTCOME_RE = _re.compile(r"\b(tabt|vundet|afleveret|indsendt)\b", _re.I)

    def _cleanup_suggestions(self, db, rnd):
        """Forslag til oprydning ud fra svarene: tabt/vundet/ikke i proces/afleveret → konkrete ændringer på tilbud og sager."""
        outcomes = {}  # company_id -> (outcome, kilde)
        for it in rnd["items"]:
            a = it.get("answer") or {}
            if a.get("later"):
                continue
            if it["kind"] == "matrix" and (it.get("context") or {}).get("target") == "sales_phase":
                for cid, val in (a.get("rows") or {}).items():
                    if val in ("tabt", "vundet", "ikke_i_proces"):
                        outcomes[int(cid)] = (val, f"Fase: {dict(SALES_PHASES).get(val)}")
            elif it.get("company_id") and it["kind"] in ("topic", "customer"):
                for k, v in a.items():
                    if k.startswith("q") and isinstance(v, str):
                        m = self.OUTCOME_RE.search(v)
                        if m and it["company_id"] not in outcomes:
                            word = m.group(1).lower()
                            outcomes[it["company_id"]] = ({"indsendt": "afleveret"}.get(word, word), f"Svar: \u201d{v[:80]}\u201d")
        suggestions = []
        for cid, (outcome, source) in outcomes.items():
            co = db.execute("SELECT name FROM companies WHERE id = %s", (cid,)).fetchone()
            if not co:
                continue
            tenders = [dict(r) for r in db.execute("SELECT id, title, status FROM tenders WHERE company_id = %s AND status NOT IN ('won','lost','dropped')", (cid,)).fetchall()]
            tasks = [dict(r) for r in db.execute("SELECT id, title FROM tasks WHERE company_id = %s AND status != 'done' AND COALESCE(area,'salg') = 'salg'", (cid,)).fetchall()]
            actions = []
            if outcome == "tabt":
                actions += [{"type": "tender_status", "id": t["id"], "status": "lost", "label": f"Sæt tilbuddet \u201d{t['title']}\u201d til Tabt"} for t in tenders]
                actions += [{"type": "close_task", "id": t["id"], "label": f"Luk sagen \u201d{t['title']}\u201d"} for t in tasks]
            elif outcome == "vundet":
                actions += [{"type": "tender_status", "id": t["id"], "status": "won", "label": f"Sæt tilbuddet \u201d{t['title']}\u201d til Vundet"} for t in tenders]
            elif outcome == "ikke_i_proces":
                actions += [{"type": "tender_status", "id": t["id"], "status": "dropped", "label": f"Sæt tilbuddet \u201d{t['title']}\u201d til Droppet"} for t in tenders]
                actions += [{"type": "close_task", "id": t["id"], "label": f"Luk sagen \u201d{t['title']}\u201d"} for t in tasks]
            elif outcome == "afleveret":
                actions += [{"type": "tender_status", "id": t["id"], "status": "submitted", "label": f"Sæt tilbuddet \u201d{t['title']}\u201d til Indsendt"}
                            for t in tenders if t["status"] in ("draft", "in_progress")]
            if actions:
                suggestions.append({"id": f"{cid}:{outcome}", "company_id": cid, "company_name": co["name"],
                                    "outcome": outcome, "source": source, "actions": actions})
        return suggestions

    @staticmethod
    def _answer_summary(item):
        a = item.get("answer") or {}
        if a.get("later"):
            return "svarer senere"
        ctx = item.get("context") or {}
        parts = []
        if item["kind"] == "matrix":
            opt = dict(ctx.get("options") or [])
            parts = [f"{r['name']}: {opt.get((a.get('rows') or {}).get(str(r['company_id'])), '-')}" for r in ctx.get("rows") or []][:6]
        else:
            for i, q in enumerate(ctx.get("questions") or []):
                if a.get(f"q{i}"):
                    parts.append(f"{(q.get('text') if isinstance(q, dict) else q)[:60]} → {a[f'q{i}']}")
            for k, label in (("status", "vurdering"), ("next_step", "næste skridt"), ("next_date", "dato"), ("probability", "sandsynlighed")):
                if a.get(k):
                    parts.append(f"{label}: {a[k]}")
            if (a.get("followup") or {}).get("answer"):
                parts.append(f"opfølgning: {a['followup']['answer']}")
        return "; ".join(parts)[:400] or "(intet)"

    def _suggest_followup_questions(self, db, rnd):
        """Forslag til opfølgende spørgsmål fra CEO'en ud fra svarene (AI når den er slået til, ellers regler)."""
        items = [it for it in rnd["items"] if it["kind"] != "matrix" and it.get("answer")]
        if os.environ.get("ANTHROPIC_API_KEY"):
            payload = [{"item_id": it["id"], "emne": it["title"], "fakta": (it.get("context") or {}).get("facts"),
                        "svar": self._answer_summary(it), "advarsler": it.get("flags")} for it in items]
            system = self._ai_preamble(db, rnd["area"]) + (
                "\nOpgave: CEO'en har læst lederens svar og vil stille opfølgende spørgsmål tilbage, før mødet. "
                "Foreslå 3–6 skarpe opfølgende spørgsmål, hvor svarene er vage, modstridende, mangler ejer/dato/tal, "
                "eller hvor der er en risiko eller mulighed, CEO'en bør forstå bedre. Hvert spørgsmål knyttes til et emne (item_id). "
                "reason: én kort sætning til CEO'en om hvorfor.\n\n" + ANSWER_FORMAT_RULES)
            schema = {"type": "object", "additionalProperties": False, "required": ["suggestions"], "properties": {"suggestions": {
                "type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": ["item_id", "text", "answer_type", "options", "reason"],
                    "properties": {"item_id": {"type": "integer"}, "text": {"type": "string"},
                                   "answer_type": {"type": "string", "enum": ["text", "choice", "date", "number"]},
                                   "options": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}}}}}}
            data, _ = self._claude(system, "Svar (JSON):\n" + json.dumps(payload, ensure_ascii=False, default=_json_default), schema)
            titles = {it["id"]: it["title"] for it in items}
            return [{**sgg, "about": titles.get(sgg["item_id"], "Generelt"), "source": "ai"} for sgg in data["suggestions"] if sgg["item_id"] in titles]
        out = []
        for it in items:
            a = it.get("answer") or {}
            ctx = it.get("context") or {}
            for i, q in enumerate(ctx.get("questions") or []):
                v = a.get(f"q{i}") or ""
                qt = q.get("text") if isinstance(q, dict) else q
                if UNKNOWN_RE.search(v):
                    out.append({"item_id": it["id"], "about": it["title"], "text": f"Du svarede '{v}' til \u201d{qt}\u201d. Hvem finder ud af det, og hvornår?",
                                "answer_type": "text", "options": [], "reason": "Svaret var 'ved ikke'.", "source": "regel"})
            for f in it.get("flags") or []:
                if f.startswith("Næste skridt uden dato"):
                    out.append({"item_id": it["id"], "about": it["title"], "text": "Hvornår sker næste skridt?", "answer_type": "date",
                                "options": [], "reason": f, "source": "regel"})
                elif f.startswith("Modstrid") or f.startswith("Høj sandsynlighed"):
                    out.append({"item_id": it["id"], "about": it["title"], "text": "Hvad konkret gør, at du vurderer det sådan?",
                                "answer_type": "text", "options": [], "reason": f, "source": "regel"})
        return out[:8]

    def _apply_report(self, db, rnd):
        """Overfører indsendte svar: målstatus til målets historik og kundestatus som note på virksomheden."""
        who = rnd.get("respondent_name") or "ukendt"
        for it in rnd["items"]:
            a = it.get("answer") or {}
            if not a or a.get("later"):
                continue
            if it["kind"] == "matrix":
                ctx = it.get("context") or {}
                for cid, val in (a.get("rows") or {}).items():
                    if not val:
                        continue
                    if ctx.get("target") == "sales_type" and val != "ved_ikke":
                        db.execute("UPDATE companies SET sales_type = %s WHERE id = %s", (val, int(cid)))
                    elif ctx.get("target") == "sales_phase" and val != "ved_ikke":
                        db.execute("""UPDATE companies SET sales_phase = %s, sales_phase_updated = CURRENT_DATE,
                                      sales_stage = COALESCE(%s, sales_stage) WHERE id = %s""", (val, PHASE_TO_STAGE.get(val), int(cid)))
                    elif ctx.get("target") == "tasks":
                        note = (a.get("notes") or {}).get(cid)
                        label = dict(ctx.get("options") or []).get(val, val)
                        line = f"{date.today().isoformat()} {who}: {label}" + (f". {note}" if note else "")
                        if val == "done":
                            db.execute("""UPDATE meeting_actions SET status = 'done', done_at = CURRENT_TIMESTAMP,
                                          notes = COALESCE(notes || E'\n', '') || %s WHERE id = %s AND status = 'open'""", (line, int(cid)))
                        else:
                            db.execute("UPDATE meeting_actions SET notes = COALESCE(notes || E'\n', '') || %s WHERE id = %s", (line, int(cid)))
                    elif ctx.get("target") == "news" and val == "ja" and (a.get("notes") or {}).get(cid):
                        db.execute("INSERT INTO company_notes (company_id, user_name, content) VALUES (%s,%s,%s)",
                                   (int(cid), who, "Indrapporteret: " + a["notes"][cid]))
                continue
            if it["kind"] == "goal" and it.get("ref_id") and a.get("status"):
                value = a.get("value")
                value = None if value in (None, "") else float(value)
                comment = a.get("comment") or ""
                db.execute("""INSERT INTO goal_checkins (goal_id, meeting_id, value, status, comment, user_name)
                              VALUES (%s,%s,%s,%s,%s,%s)""",
                           (it["ref_id"], rnd.get("meeting_id"), value, a["status"], f"Indrapporteret: {comment}" if comment else "Indrapporteret", who))
                db.execute("""UPDATE goals SET status = %s, current_value = COALESCE(%s, current_value),
                              last_checkin = CURRENT_DATE, updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
                           (a["status"], value, it["ref_id"]))
            elif it["kind"] == "topic":
                ctx = it.get("context") or {}
                qa = "\n".join(f"{q.get('text') if isinstance(q, dict) else q}\n→ {a.get(f'q{i}') or '(ikke besvaret)'}" for i, q in enumerate(ctx.get("questions") or []))
                fu = a.get("followup") or {}
                if fu.get("question"):
                    qa += f"\n{fu['question']}\n→ {fu.get('answer') or '(ikke besvaret)'}"
                if ctx.get("source_kind") == "goal" and it.get("ref_id"):
                    status = a.get("goal_status") or {"paa_sporet": "on_track", "risiko": "at_risk", "kritisk": "off_track"}.get(a.get("status"))
                    if status:
                        value = a.get("value")
                        value = None if value in (None, "") else float(value)
                        db.execute("""INSERT INTO goal_checkins (goal_id, meeting_id, value, status, comment, user_name)
                                      VALUES (%s,%s,%s,%s,%s,%s)""",
                                   (it["ref_id"], rnd.get("meeting_id"), value, status, "Indrapporteret:\n" + qa, who))
                        db.execute("""UPDATE goals SET status = %s, current_value = COALESCE(%s, current_value),
                                      last_checkin = CURRENT_DATE, updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
                                   (status, value, it["ref_id"]))
                elif it.get("company_id"):
                    extra = []
                    if a.get("next_step"): extra.append(f"Næste skridt: {a['next_step']}" + (f" ({a['next_date']})" if a.get("next_date") else ""))
                    if a.get("probability"): extra.append(f"Sandsynlighed: {a['probability']}%")
                    db.execute("INSERT INTO company_notes (company_id, user_name, content) VALUES (%s,%s,%s)",
                               (it["company_id"], who, f"Indrapporteret ({it['title']}):\n" + qa + ("\n" + "\n".join(extra) if extra else "")))
            elif it["kind"] == "customer" and it.get("company_id"):
                labels = {"som_planlagt": "Fremdrift som planlagt", "venter": "Venter på kunden", "udfordret": "Udfordret",
                          "vundet": "Vundet", "tabt": "Tabt / droppet", "forsinket": "Forsinket", "leveret": "Leveret"}
                if a.get("not_relevant"):
                    text = "Indrapporteret: ikke længere i proces."
                else:
                    parts = [f"Status: {labels.get(a.get('status'), a.get('status') or '-')}"]
                    if a.get("since_last"): parts.append(f"Siden sidst: {a['since_last']}")
                    if a.get("next_step"): parts.append(f"Næste skridt: {a['next_step']}" + (f" ({a['next_date']})" if a.get("next_date") else ""))
                    if a.get("probability"): parts.append(f"Sandsynlighed: {a['probability']}%")
                    if a.get("help"): parts.append(f"Brug for hjælp: {a['help']}")
                    text = "Indrapporteret: " + "\n".join(parts)
                db.execute("INSERT INTO company_notes (company_id, user_name, content) VALUES (%s,%s,%s)",
                           (it["company_id"], who, text))

    def _setting(self, db, key, default=""):
        row = db.execute("SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
        return (row["value"] if row else None) or default

    def _claude(self, system, user, schema=None, effort="medium", max_tokens=8000):
        """Ét kald til Claude. Med schema returneres valideret JSON (structured outputs), ellers tekst."""
        import anthropic
        client = anthropic.Anthropic()
        output_config = {"effort": effort}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        response = client.beta.messages.create(
            model="claude-opus-5-5",
            max_tokens=max_tokens,
            output_config=output_config,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Modellen afviste opgaven.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Svaret blev for langt. Prøv med færre emner ad gangen.")
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        return (json.loads(text) if schema else text), response.model

    def _claude_messages(self, system, messages, effort="medium"):
        """Samtale med Claude (flere beskeder), fx CEO-assistentens spørg-funktion."""
        import anthropic
        client = anthropic.Anthropic()
        response = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=4000, output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=system, messages=messages)
        if response.stop_reason == "refusal":
            raise RuntimeError("Modellen afviste spørgsmålet.")
        return "\n".join(b.text for b in response.content if b.type == "text").strip(), response.model

    def _ai_preamble(self, db, area):
        role = {"salg": "CCO (salg & marketing)", "leverance": "COO (leverance)", "oekonomi": "CFO (økonomi)"}.get(area, area)
        return (f"Du hjælper CEO'en i Systemate med at følge op på {role}. Skriv på dansk, direkte og konkret, "
                f"som en erfaren CEO der kender forretningen. I dag er {date.today().isoformat()}.\n\n"
                f"CEO'ens beskrivelse af salgsprocessen og hvad CEO'en altid vil vide:\n{self._setting(db, 'sales_process', DEFAULT_SALES_PROCESS)}\n\n"
                f"Andet CEO'en lægger vægt på:\n{self._setting(db, 'ceo_focus', '(intet angivet)')}\n")

    def _generate_topics(self, db, rnd, items):
        """Omskriver skabelon-emner (kunde, mål, faste spørgsmål) til skarpe spørgsmål ud fra data."""
        subjects = [{"index": i, "type": it["kind"], "titel": it["title"], "data": it.get("context")} for i, it in enumerate(items)]
        system = self._ai_preamble(db, rnd["area"]) + (
            "\nOpgave: Lav spørgsmålene til en indrapportering, som lederen besvarer skriftligt før mødet. For hvert emne:\n"
            "- Placér kunden i salgsforløbet (direkte salg eller udbud, og fase), hvis det kan udledes. Gæt ikke, spørg hellere.\n"
            "- Er kunden medlem af et indkøbsfællesskab (member_of, fx Servia), så afklar om de køber selv eller via fællesskabet, "
            "og hvad det betyder for beslutning, tidsplan og hvem vi skal påvirke. purchase_route på tilbud viser, hvad vi ved i dag.\n"
            "- Brug de konkrete fakta: deadlines der er overskredet, sager over frist, manglende kontakt, beløb, svar fra sidst.\n"
            "- Stil 2–3 spørgsmål der kun kan besvares med konkret viden: næste skridt og dato, beslutningstager, konkurrent, "
            "risiko, hvad der skal til. Undgå ja/nej-spørgsmål og generiske 'hvordan går det'.\n"
            "- facts: 1–3 korte linjer med de fakta fra data, som lederen skal se ved spørgsmålene.\n"
            "- why: én sætning om hvorfor emnet er vigtigt nu (eller tom streng).\n"
            "- ask_status: true hvis en samlet vurdering (på sporet / risiko / kritisk) giver mening.\n"
            "- title: kort, fx 'EWII · Flow til EWII (3 mio. kr.)'.\n"
            "For mål: driftsmål (kortsigtede) handler om tal, fremdrift mod plan og hvad der skal til for at nå dem; "
            "strategiske mål (langsigtede) handler om næste milepæl, hvad der konkret er gjort siden sidst, og hvad der blokerer. "
            "Er målet uklart (se quality_missing), så spørg ind til det, der mangler (fx måltal eller dato).\n"
            "Lav præcis ét emne pr. input-emne med samme subject_index.\n\n"
            + ANSWER_FORMAT_RULES)
        schema = {"type": "object", "additionalProperties": False, "required": ["topics"], "properties": {"topics": {
            "type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["subject_index", "title", "facts", "why", "ask_status", "questions"],
                "properties": {"subject_index": {"type": "integer"}, "title": {"type": "string"},
                               "facts": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"},
                               "ask_status": {"type": "boolean"}, "questions": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                        "required": ["text", "answer_type", "options"],
                        "properties": {"text": {"type": "string"},
                                       "answer_type": {"type": "string", "enum": ["text", "choice", "date", "number"]},
                                       "options": {"type": "array", "items": {"type": "string"}}}}}}}}}}
        data, model = self._claude(system, "Emner (JSON):\n" + json.dumps(subjects, ensure_ascii=False, default=_json_default), schema)
        return data["topics"], model

    def _generate_patterns(self, db, rnd, items):
        """Finder mønstre på tværs af emner (dubletter, klynger, partnere) og laver 0–3 ekstra emner."""
        overview = [{"index": i, "type": (it.get("context") or {}).get("source_kind", it["kind"]), "titel": it["title"],
                     "fakta": (it.get("context") or {}).get("facts") or [],
                     "data": (it.get("context") or {}).get("source") or it.get("context")} for i, it in enumerate(items) if it["kind"] != "matrix"]
        system = self._ai_preamble(db, rnd["area"]) + (
            "\nOpgave: Se på alle emner samlet og find mønstre, som enkelte emner ikke viser: dubletter (fx flere ens tilbud), "
            "klynger (fx mange møder via samme partner med samme frist), mange sager over frist hos én person, "
            "eller sammenhæng til målene (fx hvor meget pipelinen dækker af salgsmålet). Lav 0–3 ekstra emner med 2–3 spørgsmål hver. "
            "Lav kun et emne, hvis mønsteret er tydeligt i data. related_subject_indexes angiver de emner mønsteret bygger på.\n\n"
            + ANSWER_FORMAT_RULES)
        schema = {"type": "object", "additionalProperties": False, "required": ["topics"], "properties": {"topics": {
            "type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["title", "facts", "why", "ask_status", "questions", "related_subject_indexes"],
                "properties": {"title": {"type": "string"}, "facts": {"type": "array", "items": {"type": "string"}},
                               "why": {"type": "string"}, "ask_status": {"type": "boolean"},
                               "questions": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                        "required": ["text", "answer_type", "options"],
                        "properties": {"text": {"type": "string"},
                                       "answer_type": {"type": "string", "enum": ["text", "choice", "date", "number"]},
                                       "options": {"type": "array", "items": {"type": "string"}}}}},
                               "related_subject_indexes": {"type": "array", "items": {"type": "integer"}}}}}}}
        data, model = self._claude(system, "Alle emner (JSON):\n" + json.dumps(overview, ensure_ascii=False, default=_json_default), schema)
        return data["topics"][:3], model

    def _followup_question(self, db, rnd, item):
        """Vurderer ét besvaret emne og returnerer evt. ét opfølgende spørgsmål (ved ikke, vagt, modstrid, mangler tal/dato)."""
        ctx = item.get("context") or {}
        a = item.get("answer") or {}
        if a.get("later") or item["kind"] == "matrix":
            return None
        qtext = lambda q: q.get("text") if isinstance(q, dict) else q
        qa = [{"spørgsmål": qtext(q), "svarform": (q.get("answer_type") if isinstance(q, dict) else "text"), "svar": a.get(f"q{i}")}
              for i, q in enumerate(ctx.get("questions") or [])]
        if not qa:
            qa = [{"felt": k, "svar": v} for k, v in a.items() if k not in ("followup", "checked")]
        if os.environ.get("ANTHROPIC_API_KEY"):
            system = self._ai_preamble(db, rnd["area"]) + (
                "\nOpgave: Lederen har netop besvaret ét emne. Afgør om ét opfølgende spørgsmål er nødvendigt, før CEO'en kan bruge svaret. "
                "Stil et opfølgende spørgsmål hvis: der svares 'ved ikke' (spørg hvem der ved det og hvornår), svaret er vagt eller generelt, "
                "den samlede vurdering strider mod svarene eller mod fakta (fx 'på sporet' men ingen kender risici, høj sandsynlighed uden kontakt), "
                "en dato eller et tal virker forkert eller mangler. Ét kort, venligt og konkret spørgsmål, der henviser til det lederen skrev. "
                "Hvis svaret er godt nok: needs_followup=false og tomme strenge.")
            schema = {"type": "object", "additionalProperties": False, "required": ["needs_followup", "kind", "question", "note_for_ceo"],
                      "properties": {"needs_followup": {"type": "boolean"},
                                     "kind": {"type": "string", "enum": ["ved_ikke", "vagt", "modstrid", "mangler_tal_eller_dato", "ok"]},
                                     "question": {"type": "string"}, "note_for_ceo": {"type": "string"}}}
            user = json.dumps({"emne": item["title"], "fakta": ctx.get("facts"), "data": ctx.get("source"),
                               "samlet_vurdering": a.get("status") or a.get("goal_status"), "svar": qa,
                               "næste_skridt": a.get("next_step"), "dato": a.get("next_date"), "sandsynlighed": a.get("probability")},
                              ensure_ascii=False, default=_json_default)
            data, _ = self._claude(system, user, schema, effort="low", max_tokens=2000)
            return data if data.get("needs_followup") else None
        # Uden AI: fang i det mindste 'ved ikke'
        for x in qa:
            if isinstance(x.get("svar"), str) and UNKNOWN_RE.search(x["svar"]):
                q = x.get("spørgsmål") or x.get("felt")
                return {"needs_followup": True, "kind": "ved_ikke",
                        "question": f"Du svarer 'ved ikke' til: ”{q}”. Hvem ved det, og hvornår kan du give et svar?", "note_for_ceo": ""}
        return None

    def _assess_report(self, db, rnd):
        """AI-vurdering til CEO'en via Claude. Returnerer (tekst, model)."""
        payload = [{"type": (it.get("context") or {}).get("source_kind", it["kind"]), "titel": it["title"],
                    "fakta_og_data": it.get("context"), "svar": it.get("answer"), "automatiske_advarsler": it.get("flags")}
                   for it in rnd["items"]]
        system = self._ai_preamble(db, rnd["area"]) + (
            "\nOpgave: Vurdér lederens indrapportering holdt op mod data, så CEO'en er klar til mødet. "
            "Vurdér forretningen, ikke personen. Nævn kunder og mål ved navn. Gæt ikke på fakta, der ikke står i materialet.\n"
            "Vær særligt opmærksom på: svar med 'ved ikke' (hvad betyder det for styringen), modstrid mellem samlet vurdering og svarene "
            "(fx 'på sporet' men ukendte risici), datoer eller tal der virker forkerte, opfølgende spørgsmål der ikke er besvaret, "
            "og mål hvor fremdriften ikke passer med vurderingen.\n\n"
            "Format (kort, max ca. 400 ord):\n## Samlet billede\n2–4 sætninger.\n## Kræver opmærksomhed\nPunktliste, vigtigste først.\n"
            "## Går godt\nPunktliste (kort).\n## Spørgsmål til mødet\n3–5 konkrete spørgsmål.\n## Forslag til aktioner\n2–5 aktioner med ansvarlig (rolle) og frist.")
        user = (f"Indrapporteret af: {rnd.get('respondent_name')}\n\nMateriale (JSON):\n"
                + json.dumps(payload, ensure_ascii=False, default=_json_default))
        return self._claude(system, user, effort="medium", max_tokens=6000)

    def _slack_dm(self, email, text):
        """Sender en direkte besked i Slack via bot-token. Kræver scopes chat:write og users:read.email."""
        import urllib.request, urllib.parse
        token = os.environ.get("SLACK_BOT_TOKEN")
        def call(method, data):
            req = urllib.request.Request(f"https://slack.com/api/{method}", data=json.dumps(data).encode(),
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})
            return json.loads(urllib.request.urlopen(req, timeout=10).read())
        req = urllib.request.Request("https://slack.com/api/users.lookupByEmail?" + urllib.parse.urlencode({"email": email}),
                                     headers={"Authorization": f"Bearer {token}"})
        user = json.loads(urllib.request.urlopen(req, timeout=10).read())
        if not user.get("ok"):
            raise RuntimeError(f"Slack kunne ikke finde {email}: {user.get('error')}")
        res = call("chat.postMessage", {"channel": user["user"]["id"], "text": text})
        if not res.get("ok"):
            raise RuntimeError(f"Slack-fejl: {res.get('error')}")

    def _handle_reports(self, db, method, path, body, uid):
        parts = path.strip("/").split("/")

        if path == "/api/report-config":
            if method == "PUT":
                for key in ("sales_process", "ceo_focus"):
                    if key in body:
                        db.execute("""INSERT INTO app_settings (key, value, updated_at) VALUES (%s,%s,CURRENT_TIMESTAMP)
                                      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP""",
                                   (key, body[key]))
                db.commit()
            self._json_response({"ai": bool(os.environ.get("ANTHROPIC_API_KEY")), "slack": bool(os.environ.get("SLACK_BOT_TOKEN")),
                                 "sales_process": self._setting(db, "sales_process", DEFAULT_SALES_PROCESS),
                                 "ceo_focus": self._setting(db, "ceo_focus", "")})
            return True

        # ── Modtagerens side: kun adgang via det personlige link ──
        if parts[1] == "r":
            token = parts[2] if len(parts) > 2 else ""
            row = db.execute("SELECT id, status FROM report_rounds WHERE token = %s", (token,)).fetchone()
            if not row or len(token) < 20:
                self._error(404, "Linket er ikke gyldigt"); return True
            rid = row["id"]
            if method == "GET" and len(parts) == 3:
                rnd = self._round_full(db, rid, include_token=False)
                if rnd["status"] == "draft":
                    rnd["items"] = []
                for it in rnd["items"]:
                    it.pop("flags", None)
                rnd.pop("ai_assessment", None)
                rnd.pop("respondent_email", None)
                self._json_response(rnd)
            elif method == "PUT" and len(parts) == 5 and parts[3] == "items":
                if row["status"] != "open":
                    self._error(409, "Indrapporteringen er allerede indsendt"); return True
                db.execute("UPDATE report_items SET answer = %s, answered_at = CURRENT_TIMESTAMP WHERE id = %s AND round_id = %s",
                           (json.dumps(body.get("answer") or {}), int(parts[4]), rid))
                db.commit()
                self._json_response({"ok": True})
            elif method == "POST" and len(parts) == 6 and parts[3] == "items" and parts[5] == "followup":
                if row["status"] != "open":
                    self._error(409, "Indrapporteringen er ikke åben"); return True
                rnd = self._round_full(db, rid)
                item = next((i for i in rnd["items"] if i["id"] == int(parts[4])), None)
                if not item or not item.get("answer"):
                    self._json_response({"followup": None}); return True
                a = dict(item["answer"])
                if (a.get("followup") or {}).get("question") or a.get("checked"):
                    self._json_response({"followup": a.get("followup")}); return True
                try:
                    fu = self._followup_question(db, rnd, item)
                except Exception as e:
                    print(f"followup failed: {e}")
                    fu = None
                a["checked"] = True
                if fu:
                    a["followup"] = {"question": fu["question"], "kind": fu.get("kind"), "note_for_ceo": fu.get("note_for_ceo", ""), "answer": ""}
                db.execute("UPDATE report_items SET answer = %s WHERE id = %s", (json.dumps(a), item["id"]))
                db.commit()
                self._json_response({"followup": a.get("followup")})
            elif method == "POST" and len(parts) == 4 and parts[3] == "submit":
                if row["status"] != "open":
                    self._error(409, "Indrapporteringen er allerede indsendt"); return True
                rnd = self._round_full(db, rid)
                if not rnd.get("practice"):
                    self._apply_report(db, rnd)
                db.execute("UPDATE report_rounds SET status = 'answered', submitted_at = CURRENT_TIMESTAMP WHERE id = %s", (rid,))
                n_flags = sum(1 for it in rnd["items"] for f in it.get("flags") or [] if f != "Ikke besvaret")
                kind = "opfølgende spørgsmål" if rnd.get("followup_of") else "indrapportering"
                db.execute("""INSERT INTO notifications (company_id, type, title, message, link) VALUES (NULL, 'report', %s, %s, %s)""",
                           (f"{rnd.get('respondent_name')} har svaret" + (" (øvelse)" if rnd.get("practice") else ""),
                            f"Svar på {kind} om {dict(AREA_NAMES).get(rnd['area'], rnd['area'])}. {n_flags} advarsler. Klik for at gennemse.",
                            f"#/reports/{rnd.get('followup_of') or rid}"))
                db.commit()
                self._json_response({"ok": True})
            else:
                self._error(404, "Endpoint not found")
            return True

        # ── CEO'ens side ──
        rid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        sub = parts[3] if len(parts) > 3 else None
        if method == "GET" and rid is None:
            q = parse_qs(urlparse(self.path).query)
            where, p = "", []
            if q.get("meeting_id"):
                where += " AND rr.meeting_id = %s"; p.append(int(q["meeting_id"][0]))
            if q.get("area"):
                where += " AND rr.area = %s"; p.append(q["area"][0])
            rows = [dict(r) for r in db.execute(f"""
                SELECT rr.id, rr.area, rr.meeting_id, rr.respondent_name, rr.status, rr.due_date, rr.created_at,
                       rr.sent_at, rr.submitted_at, rr.ai_generated_at, rr.token, rr.practice, rr.reviewed_at, rr.followup_of,
                       (SELECT COUNT(*) FROM report_items ri WHERE ri.round_id = rr.id) AS items_total,
                       (SELECT COUNT(*) FROM report_items ri WHERE ri.round_id = rr.id AND ri.answer IS NOT NULL) AS items_answered
                FROM report_rounds rr WHERE 1=1 {where} ORDER BY rr.created_at DESC""", p or None).fetchall()]
            self._json_response(rows)
        elif method == "GET":
            rnd = self._round_full(db, rid)
            if not rnd:
                self._error(404, "Indrapportering ikke fundet"); return True
            rnd["suggestions"] = self._cleanup_suggestions(db, rnd) if rnd["status"] != "draft" else []
            rnd["is_new"] = rnd["status"] == "answered" and not rnd.get("reviewed_at")
            if rnd["is_new"]:
                db.execute("UPDATE report_rounds SET reviewed_at = CURRENT_TIMESTAMP WHERE id = %s", (rid,))
                db.execute("UPDATE notifications SET is_read = TRUE WHERE link = %s AND type = 'report'", (f"#/reports/{rid}",))
                db.commit()
            rnd["followups"] = []
            for f in db.execute("SELECT id FROM report_rounds WHERE followup_of = %s ORDER BY created_at", (rid,)).fetchall():
                fr = self._round_full(db, f["id"])
                if fr["status"] == "answered" and not fr.get("reviewed_at"):
                    fr["is_new"] = True
                    db.execute("UPDATE report_rounds SET reviewed_at = CURRENT_TIMESTAMP WHERE id = %s", (f["id"],))
                    db.commit()
                rnd["followups"].append(fr)
            self._json_response(rnd)
        elif method == "POST" and sub == "suggest-questions":
            rnd = self._round_full(db, rid)
            try:
                self._json_response({"suggestions": self._suggest_followup_questions(db, rnd)})
            except Exception as e:
                self._error(502, f"Kunne ikke foreslå spørgsmål: {e}")
        elif method == "POST" and sub == "followup-round":
            import secrets
            rnd = self._round_full(db, rid)
            qs = [q for q in (body.get("questions") or []) if (q.get("text") or "").strip()]
            if not qs:
                self._error(400, "Vælg eller skriv mindst ét spørgsmål"); return True
            cur = db.execute("""INSERT INTO report_rounds (area, meeting_id, respondent_user_id, respondent_name, token, due_date,
                                practice, status, followup_of) VALUES (%s,%s,%s,%s,%s,%s,%s,'open',%s) RETURNING id""",
                             (rnd["area"], rnd.get("meeting_id"), rnd.get("respondent_user_id"), rnd.get("respondent_name"),
                              secrets.token_urlsafe(24), body.get("due_date") or (date.today() + timedelta(days=3)).isoformat(),
                              bool(rnd.get("practice")), rid))
            new_id = cur.fetchone()["id"]
            groups = {}
            for q in qs:
                groups.setdefault((q.get("about") or "Generelt", q.get("item_id")), []).append(q)
            by_id = {it["id"]: it for it in rnd["items"]}
            for i, ((about, item_id), questions) in enumerate(groups.items()):
                src = by_id.get(item_id) or {}
                facts = [f"Du svarede: {self._answer_summary(src)}"] if src.get("answer") else []
                ctx = {"facts": facts, "why": "", "ask_status": False, "source_kind": "followup",
                       "questions": [{"text": q["text"], "answer_type": q.get("answer_type") or "text", "options": q.get("options") or []} for q in questions]}
                db.execute("""INSERT INTO report_items (round_id, kind, company_id, title, context, sort_order)
                              VALUES (%s,'topic',%s,%s,%s,%s)""", (new_id, src.get("company_id"), about, json.dumps(ctx), i))
            db.commit()
            log_audit(db, uid, "create", "report_round", new_id, f"opfølgning på {rid}")
            db.commit()
            self._json_response(self._round_full(db, new_id), 201)
        elif method == "POST" and sub == "apply-suggestion":
            rnd = self._round_full(db, rid)
            if rnd.get("practice"):
                self._error(409, "Øvelse: forslag bliver ikke udført på rigtige data"); return True
            sug = next((x for x in self._cleanup_suggestions(db, rnd) if x["id"] == body.get("id")), None)
            if not sug:
                self._error(404, "Forslaget findes ikke længere"); return True
            for act in sug["actions"]:
                if act["type"] == "tender_status":
                    db.execute("UPDATE tenders SET status = %s WHERE id = %s", (act["status"], act["id"]))
                    log_audit(db, uid, "update", "tender", act["id"], act["label"], {"status": act["status"]})
                elif act["type"] == "close_task":
                    db.execute("UPDATE tasks SET status = 'done', completed_at = CURRENT_TIMESTAMP WHERE id = %s", (act["id"],))
            db.commit()
            rnd = self._round_full(db, rid)
            rnd["suggestions"] = self._cleanup_suggestions(db, rnd)
            self._json_response(rnd)
        elif method == "POST" and rid is None:
            import secrets
            user = db.execute("SELECT id, name FROM users WHERE id = %s", (body.get("respondent_user_id"),)).fetchone()
            if not user:
                self._error(400, "Vælg hvem der skal indrapportere"); return True
            ai_q = bool(body.get("ai_questions"))
            cur = db.execute("""INSERT INTO report_rounds (area, meeting_id, respondent_user_id, respondent_name, token, due_date,
                                practice, ai_questions, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                             (body["area"], body.get("meeting_id"), user["id"], user["name"], secrets.token_urlsafe(24),
                              body.get("due_date") or None, bool(body.get("practice")), ai_q, "draft" if ai_q else "open"))
            new_id = cur.fetchone()["id"]
            if body.get("items"):
                # Spørgsmål givet på forhånd (fx formuleret af AI eller CEO'en) i stedet for skabelonen
                for i, it in enumerate(body["items"]):
                    db.execute("""INSERT INTO report_items (round_id, kind, ref_type, ref_id, company_id, title, context, sort_order)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                               (new_id, it.get("kind", "topic"), it.get("ref_type"), it.get("ref_id"), it.get("company_id"),
                                it["title"], json.dumps(it.get("context") or {}), i))
            else:
                self._build_report_items(db, new_id, body["area"], user["id"],
                                         company_ids=body.get("company_ids") or None, only_customers=bool(body.get("only_customers")),
                                         tasks_only=bool(body.get("tasks_only")))
                if body.get("tasks_only") and not db.execute("SELECT 1 FROM report_items WHERE round_id = %s", (new_id,)).fetchone():
                    db.rollback()
                    self._error(400, "Der er ingen åbne opgaver til denne leder"); return True
            db.commit()
            log_audit(db, uid, "create", "report_round", new_id, f"{body['area']} · {user['name']}")
            db.commit()
            self._json_response(self._round_full(db, new_id), 201)
        elif method == "POST" and sub == "ai-generate":
            # Laver spørgsmål til de næste emner, der stadig er skabelon. Frontend kalder igen, til remaining = 0.
            rnd = self._round_full(db, rid)
            pending = [it for it in rnd["items"] if it["kind"] not in ("topic", "matrix")]
            batch = pending[: max(1, min(int(body.get("limit") or 4), 6))]
            if not batch:
                self._json_response({"remaining": 0, "done": len(rnd["items"])}); return True
            try:
                topics, model = self._generate_topics(db, rnd, batch)
            except Exception as e:
                self._error(502, f"AI kunne ikke lave spørgsmål: {e}"); return True
            for t in topics:
                if not (0 <= t["subject_index"] < len(batch)):
                    continue
                src = batch[t["subject_index"]]
                ctx = {"facts": t["facts"], "why": t["why"], "ask_status": t["ask_status"], "questions": t["questions"][:4],
                       "source_kind": src["kind"], "source": src.get("context"), "original_title": src["title"], "ai_model": model}
                db.execute("UPDATE report_items SET kind = 'topic', title = %s, context = %s WHERE id = %s",
                           (t["title"], json.dumps(ctx, default=_json_default), src["id"]))
            # Emner AI'en sprang over beholder skabelonen, men markeres, så løkken ikke kører i ring
            handled = {batch[t["subject_index"]]["id"] for t in topics if 0 <= t["subject_index"] < len(batch)}
            for it in batch:
                if it["id"] not in handled:
                    db.execute("""UPDATE report_items SET kind = 'topic', context = %s WHERE id = %s""",
                               (json.dumps({"facts": [], "why": "", "ask_status": True, "questions": [f"Hvad er status på {it['title']}?"],
                                            "source_kind": it["kind"], "source": it.get("context")}, default=_json_default), it["id"]))
            db.commit()
            self._json_response({"remaining": len(pending) - len(batch), "done": len(rnd["items"]) - len(pending) + len(batch)})
        elif method == "POST" and sub == "ai-patterns":
            rnd = self._round_full(db, rid)
            try:
                topics, model = self._generate_patterns(db, rnd, rnd["items"])
            except Exception as e:
                self._error(502, f"AI kunne ikke finde mønstre: {e}"); return True
            for i, t in enumerate(topics):
                related = [rnd["items"][k]["title"] for k in t.get("related_subject_indexes", []) if 0 <= k < len(rnd["items"])]
                db.execute("""INSERT INTO report_items (round_id, kind, title, context, sort_order) VALUES (%s,'topic',%s,%s,%s)""",
                           (rid, t["title"], json.dumps({"facts": t["facts"], "why": t["why"], "ask_status": t["ask_status"],
                                                         "questions": t["questions"][:4], "source_kind": "pattern",
                                                         "related": related, "ai_model": model}), -10 + i))
            db.commit()
            self._json_response({"added": len(topics)})
        elif sub == "items" and rid is not None:
            item_id = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None
            if method == "POST":
                db.execute("""INSERT INTO report_items (round_id, kind, title, context, sort_order)
                              VALUES (%s,'topic',%s,%s,(SELECT COALESCE(MAX(sort_order),0)+1 FROM report_items WHERE round_id = %s))""",
                           (rid, body.get("title") or "Nyt emne", json.dumps(body.get("context") or {"questions": [], "facts": [], "ask_status": False, "source_kind": "manual"}), rid))
            elif method == "PUT" and item_id:
                db.execute("UPDATE report_items SET title = COALESCE(%s, title), context = COALESCE(%s, context) WHERE id = %s AND round_id = %s",
                           (body.get("title"), json.dumps(body["context"]) if "context" in body else None, item_id, rid))
            elif method == "DELETE" and item_id:
                db.execute("DELETE FROM report_items WHERE id = %s AND round_id = %s", (item_id, rid))
            db.commit()
            self._json_response(self._round_full(db, rid))
        elif method == "POST" and sub == "sent":
            db.execute("UPDATE report_rounds SET sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP) WHERE id = %s", (rid,))
            db.commit()
            self._json_response(self._round_full(db, rid))
        elif method == "POST" and sub == "slack":
            if not os.environ.get("SLACK_BOT_TOKEN"):
                self._error(400, "Slack er ikke sat op endnu"); return True
            rnd = self._round_full(db, rid)
            if not rnd.get("respondent_email"):
                self._error(400, "Modtageren har ingen e-mail i Brugere"); return True
            due = f" senest {rnd['due_date']}" if rnd.get("due_date") else ""
            text = body.get("text") or (f"Hej {rnd['respondent_name'].split(' ')[0]} \U0001F44B\nDer er indrapportering til næste opfølgningsmøde{due}. "
                    f"Det tager ca. 10 minutter, og dine sidste svar er udfyldt på forhånd:\n{body.get('link')}")
            try:
                self._slack_dm(rnd["respondent_email"], text)
            except Exception as e:
                self._error(502, str(e)); return True
            db.execute("UPDATE report_rounds SET sent_at = CURRENT_TIMESTAMP WHERE id = %s", (rid,))
            db.commit()
            self._json_response(self._round_full(db, rid))
        elif method == "POST" and sub == "assess":
            if not os.environ.get("ANTHROPIC_API_KEY"):
                self._error(400, "AI-vurdering er ikke sat op endnu (ANTHROPIC_API_KEY mangler)"); return True
            rnd = self._round_full(db, rid)
            try:
                text, model = self._assess_report(db, rnd)
            except Exception as e:
                self._error(502, f"AI-vurderingen fejlede: {e}"); return True
            db.execute("UPDATE report_rounds SET ai_assessment = %s, ai_model = %s, ai_generated_at = CURRENT_TIMESTAMP WHERE id = %s",
                       (text, model, rid))
            db.commit()
            self._json_response(self._round_full(db, rid))
        elif method == "PUT" and rid is not None:
            if body.get("status") in ("draft", "open", "answered", "closed"):
                db.execute("UPDATE report_rounds SET status = %s WHERE id = %s", (body["status"], rid))
            if "due_date" in body:
                db.execute("UPDATE report_rounds SET due_date = %s WHERE id = %s", (body["due_date"] or None, rid))
            db.commit()
            self._json_response(self._round_full(db, rid))
        elif method == "DELETE" and rid is not None:
            db.execute("DELETE FROM report_rounds WHERE id = %s", (rid,))
            db.commit()
            self._no_content()
        else:
            self._error(404, "Endpoint not found")
        return True

    def log_message(self, format, *args):
        pass  # Suppress access logs


# ─── Initialize DB on cold start ───
try:
    init_db()
except Exception as e:
    print(f"init_db warning: {e}")
