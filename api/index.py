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
    raise TypeError(f"Type {type(obj)} not serializable")

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
        ]
        for m in migrations:
            try:
                db.execute(m)
                db.commit()
            except Exception:
                db.rollback()

        # Seed: Jess user
        db.execute("INSERT INTO users (name, email, role) VALUES ('Jess Kristensen', 'jess@systemate.dk', 'admin') ON CONFLICT (email) DO NOTHING")
        db.commit()

        # Seed companies if empty
        cnt = db.execute("SELECT COUNT(*) AS cnt FROM companies").fetchone()["cnt"]
        if cnt == 0:
            _seed_companies(db)

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
def check_score_notifications(db):
    thresholds = {}
    for row in db.execute("SELECT rating, threshold FROM score_settings").fetchall():
        thresholds[row["rating"]] = row["threshold"]
    all_scores = calculate_all_scores(db)
    for s in all_scores:
        rating = s.get("rating") or "C"
        threshold = thresholds.get(rating, 30)
        if s["score"] < threshold:
            existing = db.execute(
                """SELECT id FROM notifications WHERE company_id = %s AND is_read = FALSE
                   AND created_at > NOW() - INTERVAL '7 days' AND type = 'score_drop'""",
                (s["company_id"],)).fetchone()
            if not existing:
                msg = "{} har score {} (under graense {} for {}-kunde)".format(
                    s["company_name"], round(s["score"]), threshold, rating)
                db.execute(
                    "INSERT INTO notifications (company_id, type, message) VALUES (%s, 'score_drop', %s)",
                    (s["company_id"], msg))
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

        if not contact_ids:
            return {"company_id": company["id"], "company_name": company["name"],
                    "sector": company["sector"], "tier": company.get("tier"),
                    "rating": company.get("rating", "C"), "account_manager_name": am_name,
                    "score": 0, "sub_scores": empty_sub, "interaction_points": 0,
                    "decay_factor": 0.10, "days_since_last": None, "total_contacts": 0,
                    "contacted_count": 0, "total_interactions": 0, "channel_types": [],
                    "level": "kold", "coverage_pct": 0, "li_connected": 0,
                    "score_color": "roed", **mx}

        interactions = [dict(r) for r in db.execute(
            "SELECT type, date, contact_id FROM interactions WHERE contact_id = ANY(%s) ORDER BY date DESC",
            (contact_ids,)).fetchall()]

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
    for r in db.execute(
            """SELECT i.type, i.date, i.contact_id, c.company_id
               FROM interactions i JOIN contacts c ON i.contact_id = c.id
               ORDER BY i.date DESC""").fetchall():
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
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        if path.startswith("/api/"):
            self._handle_api_get(path, params)
        else:
            self._error(404, "Not found")

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
                for row in rows:
                    row["tags"] = tags_map.get(row["id"], [])
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
                    """SELECT t.*, u.name AS responsible_name
                       FROM tenders t LEFT JOIN users u ON t.responsible_id = u.id
                       WHERE t.company_id = %s ORDER BY t.created_at DESC""", (cid,)).fetchall()]
                self._json_response({
                    "company": dict(company), "contacts": contacts, "score": score,
                    "interactions": interactions, "emails": emails, "users": users,
                    "tasks": tasks, "audit_log": audit,
                    "linkedin_activities": li_activities, "linkedin_engagements": li_engagements,
                    "company_tags": company_tags, "all_tags": all_tags, "tenders": tenders
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
                q = "SELECT n.*, c.name AS company_name FROM notifications n JOIN companies c ON n.company_id = c.id WHERE 1=1"
                p = []
                if "is_read" in params:
                    val = params["is_read"][0]
                    q += " AND n.is_read = %s"; p.append(val == "1" or val == "true")
                q += " ORDER BY n.created_at DESC LIMIT 50"
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
                    SELECT t.id, t.title, t.status, t.deadline, t.estimated_value,
                           co.id AS company_id, co.name AS company_name,
                           u.name AS responsible_name,
                           (SELECT COUNT(*) FROM tender_sections ts WHERE ts.tender_id = t.id) AS total_sections,
                           (SELECT COUNT(*) FROM tender_sections ts WHERE ts.tender_id = t.id AND ts.status = 'approved') AS approved_sections
                    FROM tenders t JOIN companies co ON t.company_id = co.id
                    LEFT JOIN users u ON t.responsible_id = u.id
                    WHERE t.status NOT IN ('won', 'lost', 'dropped')
                    ORDER BY t.deadline ASC NULLS LAST
                """).fetchall()]

                self._json_response({"scores": scores, "stats": stats, "all_tags": all_tags,
                                     "recent_activities": recent_activities, "active_tenders": active_tenders})

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
                q = """SELECT t.*, c.name AS company_name,
                       u1.name AS responsible_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tenders t JOIN companies c ON t.company_id = c.id
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
                    """SELECT t.*, c.name AS company_name,
                       u1.name AS responsible_name, u2.name AS created_by_name,
                       ct.first_name || ' ' || ct.last_name AS contact_name
                       FROM tenders t JOIN companies c ON t.company_id = c.id
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
                     body.get("has_el",False), body.get("has_gas",False), body.get("has_vand",False),
                     body.get("has_varme",False), body.get("has_spildevand",False), body.get("has_affald",False),
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
                     body.get("on_linkedin_list",False), body.get("notes"),
                     body.get("linkedin_connected_systemate",False), body.get("linkedin_connected_settl",False)))
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
                       title,description,status,priority,due_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["company_id"], body.get("contact_id"), body.get("assigned_to"),
                     uid, body["category"], body["title"], body.get("description"),
                     body.get("status","open"), body.get("priority","normal"), body.get("due_date")))
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
                       deadline,contact_id,responsible_id,created_by,estimated_value,portal_link,notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (body["company_id"], body.get("template_id"), body["title"], body.get("description"),
                     body.get("status","draft"), body.get("deadline"), body.get("contact_id"),
                     body.get("responsible_id"), uid, body.get("estimated_value"),
                     body.get("portal_link"), body.get("notes")))
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
                     e.get("has_el",False), e.get("has_gas",False), e.get("has_vand",False),
                     e.get("has_varme",False), e.get("has_spildevand",False), e.get("has_affald",False),
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
                     e["linkedin_url"], e["on_linkedin_list"], e["notes"],
                     e.get("linkedin_connected_systemate",False), e.get("linkedin_connected_settl",False),
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
                elif body.get("status") != "done":
                    e["completed_at"] = None
                db.execute(
                    """UPDATE tasks SET contact_id=%s,assigned_to=%s,category=%s,title=%s,description=%s,
                       status=%s,priority=%s,due_date=%s,completed_at=%s WHERE id=%s""",
                    (e.get("contact_id"), e.get("assigned_to"), e["category"], e["title"],
                     e.get("description"), e["status"], e["priority"], e.get("due_date"),
                     e.get("completed_at"), tid))
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
                         rule.get("description",""), rule.get("is_active",True)))
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
                db.execute(
                    """UPDATE tenders SET company_id=%s,title=%s,description=%s,status=%s,
                       deadline=%s,contact_id=%s,responsible_id=%s,estimated_value=%s,portal_link=%s,notes=%s WHERE id=%s""",
                    (e["company_id"], e["title"], e.get("description"), e["status"],
                     e.get("deadline"), e.get("contact_id"), e.get("responsible_id"),
                     e.get("estimated_value"), e.get("portal_link"), e.get("notes"), tid))
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

    def log_message(self, format, *args):
        pass  # Suppress access logs


# ─── Initialize DB on cold start ───
try:
    init_db()
except Exception as e:
    print(f"init_db warning: {e}")
