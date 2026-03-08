"""Seed database with test data for demo purposes."""
from database import init_db, get_db

init_db()

with get_db() as conn:
    # Users
    conn.execute("INSERT OR IGNORE INTO users (name, email, role) VALUES ('Jess Kristensen', 'jess@systemate.dk', 'admin')")
    conn.execute("INSERT OR IGNORE INTO users (name, email, role) VALUES ('Thomas Nielsen', 'thomas@systemate.dk', 'user')")

    # Companies
    companies = [
        ("Energi Fyn", "el", "Odense", "5000"),
        ("TREFOR Vand", "vand", "Vejle", "7100"),
        ("Fjernvarme Fyn", "varme", "Odense", "5000"),
        ("Verdo", "multiforsyning", "Randers", "8900"),
        ("EWII", "multiforsyning", "Kolding", "6000"),
        ("Aarhus Vand", "vand", "Aarhus", "8000"),
    ]
    for name, sector, city, zip_code in companies:
        conn.execute("INSERT OR IGNORE INTO companies (name, sector, city, zip_code) VALUES (?, ?, ?, ?)",
                     (name, sector, city, zip_code))

    # Contacts
    contacts = [
        (1, "Lars", "Hansen", "CEO", "lars@energifyn.dk", 1),
        (1, "Mette", "Andersen", "CFO", "mette@energifyn.dk", 0),
        (1, "Peter", "Skov", "Afregningschef", "peter@energifyn.dk", 1),
        (2, "Anne", "Mortensen", "CEO", "anne@trefor.dk", 0),
        (2, "Henrik", "Olsen", "COO", "henrik@trefor.dk", 1),
        (3, "Soeren", "Frederiksen", "CEO", "soren@fjernvarmefyn.dk", 0),
        (4, "Camilla", "Thomsen", "CEO", "camilla@verdo.dk", 1),
        (4, "Michael", "Nielsen", "Kundechef", "michael@verdo.dk", 0),
        (5, "Birgitte", "Jensen", "CCO", "birgitte@ewii.dk", 0),
        (6, "Kasper", "Holm", "CEO", "kasper@aarhusvand.dk", 0),
    ]
    for cid, fn, ln, title, email, li in contacts:
        conn.execute(
            "INSERT OR IGNORE INTO contacts (company_id, first_name, last_name, title, email, on_linkedin_list) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, fn, ln, title, email, li))

    # Interactions
    interactions = [
        (1, 1, "meeting", "2026-03-01", "Strategimoede om ny platform"),
        (1, 1, "email", "2026-03-03", "Opfoelgning paa moede"),
        (2, 1, "phone", "2026-02-25", "Budget-diskussion"),
        (3, 2, "linkedin", "2026-02-20", "LinkedIn besked om afregning"),
        (3, 2, "email", "2026-02-28", "Afregningssystem demo"),
        (4, 1, "meeting", "2026-02-15", "Praesentation af loesning"),
        (5, 2, "email", "2026-02-18", "Teknisk dokumentation"),
        (4, 1, "phone", "2026-02-20", "Opfoelgning"),
        (6, 1, "email", "2025-12-10", "Introduktion"),
        (6, 1, "phone", "2025-12-15", "Kort samtale om muligheder"),
        (7, 2, "meeting", "2026-02-01", "Foerste moede"),
        (7, 2, "email", "2026-02-05", "Opfoelgning paa moede"),
        (9, 1, "email", "2026-01-15", "Indledende kontakt"),
    ]
    for cid, uid, itype, date, subj in interactions:
        conn.execute(
            "INSERT INTO interactions (contact_id, user_id, type, date, subject) VALUES (?, ?, ?, ?, ?)",
            (cid, uid, itype, date, subj))

    # Tasks
    tasks = [
        (1, 1, 1, 1, "opfoelgning", "Ring Lars Hansen om kontrakt", "Afvent svar paa tilbud", "open", "high", "2026-03-07"),
        (1, 2, 1, 2, "tilbud", "Udarbejd tilbud til Energi Fyn", "Platform-loesning inkl. afregning", "done", "normal", "2026-02-28"),
        (2, 4, 2, 1, "moede", "Planlæg demo for TREFOR Vand", "Online demo af platform", "in_progress", "normal", "2026-03-10"),
        (1, None, 2, 1, "opkald", "Kvartals-opfoelgning Energi Fyn", "Tjek status paa samarbejde", "open", "normal", "2026-03-12"),
        (4, 7, 2, 2, "demo", "Demo af settl for Verdo", "Vis multiforsynings-modul", "open", "high", "2026-03-08"),
        (2, 5, 1, 1, "opfoelgning", "Send referencecase til TREFOR", "De vil se Energi Fyn case", "done", "normal", "2026-03-01"),
    ]
    for comp_id, contact_id, assigned_to, created_by, cat, title, desc, status, prio, due in tasks:
        conn.execute(
            """INSERT INTO tasks (company_id, contact_id, assigned_to, created_by, category, title, description, status, priority, due_date, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (comp_id, contact_id if contact_id else None, assigned_to, created_by, cat, title, desc, status, prio, due,
             "2026-03-01 10:00:00" if status == "done" else None))

    # LinkedIn Activities
    linkedin_activities = [
        (1, "post", "Lars Hansen delte artikel om groen omstilling i energisektoren", None, 1, "2026-03-02"),
        (4, "comment", "Anne Mortensen kommenterede paa branche-opslag", None, 2, "2026-02-28"),
        (7, "article", "Camilla Thomsen publicerede artikel om digitalisering", None, 1, "2026-02-25"),
        (5, "like", "Henrik Olsen likede Systemates opslag om ny platform", None, 2, "2026-03-04"),
    ]
    for contact_id, atype, summary, url, observed_by, adate in linkedin_activities:
        conn.execute(
            "INSERT INTO linkedin_activities (contact_id, activity_type, content_summary, linkedin_post_url, observed_by, activity_date) VALUES (?, ?, ?, ?, ?, ?)",
            (contact_id, atype, summary, url, observed_by, adate))

    # LinkedIn Engagements
    linkedin_engagements = [
        (1, "like", "systemate", None, 1, "2026-03-03", "Likede opslag om CRM loesning"),
        (5, "comment", "settl", None, 2, "2026-02-26", "Kommenterede paa settl demo-video"),
        (7, "follow", "systemate", None, 1, "2026-02-22", "Foelger nu Systemate paa LinkedIn"),
    ]
    for contact_id, etype, page, url, observed_by, odate, notes in linkedin_engagements:
        conn.execute(
            "INSERT INTO linkedin_engagements (contact_id, engagement_type, company_page, post_url, observed_by, observed_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (contact_id, etype, page, url, observed_by, odate, notes))

print("Database seeded successfully!")
