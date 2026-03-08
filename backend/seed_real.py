"""
Seed database with real companies from 'Den danske energibranche 2024' map.
Extracted from the Forsynings- og energiselskaber section and city listings on the map.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relations_crm.db")

def run():
    # First init the database tables
    from database import init_db
    init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF")

    # Clear existing data
    conn.execute("DELETE FROM emails")
    conn.execute("DELETE FROM interactions")
    conn.execute("DELETE FROM contacts")
    conn.execute("DELETE FROM companies")
    conn.execute("DELETE FROM users")
    conn.execute("PRAGMA foreign_keys=ON")

    # Insert default users (Systemate sales team)
    conn.execute("INSERT INTO users (name, email, role) VALUES ('Jess Kristensen', 'jess@systemate.dk', 'admin')")
    conn.execute("INSERT INTO users (name, email, role) VALUES ('Thomas Nielsen', 'thomas@systemate.dk', 'user')")

    # ────────────────────────────────────────────────────────
    # Companies from "Forsynings- og energiselskaber" section
    # and city listings on the map
    # ────────────────────────────────────────────────────────
    companies = [
        # (name, sector, city, zip_code, notes)

        # === Fra "Forsynings- og energiselskaber" listen (øverst til venstre) ===
        ("Ø. Himmerlands Forsyning", "multiforsyning", "Aars", "9600", "Region Nordjylland"),
        ("ARC I/S Amager Ressourcecenter", "varme", "København S", "2300", "Region Hovedstaden. Affaldsforbrænding og fjernvarme"),
        ("Andel Energi", "el", "Svinninge", "4520", "Region Sjælland. Tidl. SEAS-NVE"),
        ("Bjerringbro Elværk", "el", "Bjerringbro", "8850", "Region Midtjylland"),
        ("Blue Energy Holding A/S", "multiforsyning", "Kolding", "6000", "Region Syddanmark. Moderselskab for EWII"),
        ("Cerius A/S", "el", "Sorø", "4180", "Region Sjælland. Eldistribution"),
        ("DIN Forsyning", "multiforsyning", "Esbjerg", "6700", "Region Syddanmark. El, vand, varme, spildevand"),
        ("Energi Fyn", "el", "Odense", "5000", "Region Syddanmark. Eldistribution og salg"),
        ("EWII", "multiforsyning", "Kolding", "6000", "Region Syddanmark. El, vand, varme, fiber"),
        ("Faxe Forsyning", "multiforsyning", "Faxe", "4640", "Region Sjælland"),
        ("Fjernvarme Fyn", "varme", "Odense", "5000", "Region Syddanmark. Fjernvarme"),
        ("Fors A/S", "multiforsyning", "Holbæk", "4300", "Region Sjælland. Vand, varme, affald"),
        ("Forsyning Helsingør", "multiforsyning", "Helsingør", "3000", "Region Hovedstaden"),
        ("Frederikshavn Forsyning", "multiforsyning", "Frederikshavn", "9900", "Region Nordjylland"),
        ("Hillerød Forsyning", "multiforsyning", "Hillerød", "3400", "Region Hovedstaden"),
        ("Hofor", "multiforsyning", "København", "2100", "Region Hovedstaden. Hovedstadens Forsyning"),
        ("Jysk Energi Holding A/S", "el", "Haderslev", "6100", "Region Syddanmark"),
        ("Klar Forsyning", "multiforsyning", "Kalundborg", "4400", "Region Sjælland"),
        ("N1 A/S", "el", "Ballerup", "2750", "Region Hovedstaden. Tidl. Radius Elnet"),
        ("Nordenergi A/S", "el", "Aalborg", "9000", "Region Nordjylland"),
        ("Norlys", "el", "Silkeborg", "8600", "Region Midtjylland. El, fiber, opladning"),
        ("NRGi", "el", "Aarhus", "8000", "Region Midtjylland. Nu del af Norlys/Andel"),
        ("SE (Syd Energi)", "el", "Vejen", "6600", "Region Syddanmark. Nu del af Andel"),
        ("SE Forsyning A/S", "multiforsyning", "Stege", "4780", "Region Sjælland"),
        ("SK Forsyning", "multiforsyning", "Slagelse", "4200", "Region Sjælland"),
        ("Skanderborg Forsyning", "multiforsyning", "Skanderborg", "8660", "Region Midtjylland"),
        ("Sønderborg Forsyning", "multiforsyning", "Sønderborg", "6400", "Region Syddanmark"),
        ("Thy-Mors Energi", "el", "Thisted", "7700", "Region Nordjylland"),
        ("TREFOR", "multiforsyning", "Vejle", "7100", "Region Syddanmark. Del af Norlys"),
        ("Verdo", "multiforsyning", "Randers", "8900", "Region Midtjylland. El, vand, varme"),
        ("Vestforsyning", "multiforsyning", "Holstebro", "7500", "Region Midtjylland"),
        ("Aalborg Forsyning", "multiforsyning", "Aalborg", "9000", "Region Nordjylland. Vand, varme, kloak, renovation"),
        ("Aarhus Forsyning", "multiforsyning", "Aarhus", "8000", "Region Midtjylland. Tidl. AffaldVarme Aarhus"),

        # === Fra kortet: Byer med forsyningsselskaber ===
        ("Aarhus Vand", "vand", "Aarhus", "8000", "Region Midtjylland"),
        ("VandCenter Syd", "vand", "Odense", "5000", "Region Syddanmark"),
        ("Aalborg Varme A/S", "varme", "Aalborg", "9000", "Region Nordjylland"),
        ("Kredsløb", "varme", "Aarhus", "8000", "Region Midtjylland. Tidl. AffaldVarme Aarhus"),
        ("Energi Viborg", "multiforsyning", "Viborg", "8800", "Region Midtjylland. El, vand, varme"),
        ("Herning Vand", "vand", "Herning", "7400", "Region Midtjylland"),
        ("Horsens Vand", "vand", "Horsens", "8700", "Region Midtjylland"),
        ("Provas", "multiforsyning", "Haderslev", "6100", "Region Syddanmark. Vand, varme, affald"),
        ("NK-Forsyning", "multiforsyning", "Næstved", "4700", "Region Sjælland"),
        ("Fredericia Fjernvarme", "varme", "Fredericia", "7000", "Region Syddanmark"),
        ("Middelfart Fjernvarme", "varme", "Middelfart", "5500", "Region Syddanmark"),
        ("Ringkøbing-Skjern Forsyning", "multiforsyning", "Ringkøbing", "6950", "Region Midtjylland"),
        ("Lemvig Vand", "vand", "Lemvig", "7620", "Region Midtjylland"),
        ("Skive Vand", "vand", "Skive", "7800", "Region Midtjylland"),
        ("Ikast-Brande Forsyning", "multiforsyning", "Ikast", "7430", "Region Midtjylland"),
        ("Brønderslev Forsyning", "multiforsyning", "Brønderslev", "9700", "Region Nordjylland"),
        ("Hjørring Vandselskab", "vand", "Hjørring", "9800", "Region Nordjylland"),
        ("Mariagerfjord Vand", "vand", "Hobro", "9500", "Region Nordjylland"),
        ("Randers Forsyning", "multiforsyning", "Randers", "8900", "Region Midtjylland"),
        ("Silkeborg Forsyning", "multiforsyning", "Silkeborg", "8600", "Region Midtjylland"),
        ("Vejle Spildevand", "vand", "Vejle", "7100", "Region Syddanmark"),

        # === Fra kortet: Storkøbenhavn / Sjælland ===
        ("Vestforbrænding", "varme", "Glostrup", "2600", "Region Hovedstaden. Affaldsforbrænding og fjernvarme"),
        ("CTR", "varme", "Frederiksberg", "1799", "Region Hovedstaden. Centralkommunernes Transmissionsselskab"),
        ("VEKS", "varme", "Albertslund", "2620", "Region Hovedstaden. Vestegnens Kraftvarmeselskab"),
        ("Køge Forsyning", "multiforsyning", "Køge", "4600", "Region Sjælland"),
        ("Roskilde Forsyning", "multiforsyning", "Roskilde", "4000", "Region Sjælland"),
        ("Lyngby-Taarbæk Forsyning", "multiforsyning", "Kgs. Lyngby", "2800", "Region Hovedstaden"),

        # === Yderligere fra kortet: Syddanmark ===
        ("Aabenraa Fjernvarme", "varme", "Aabenraa", "6200", "Region Syddanmark"),
        ("Svendborg Fjernvarme", "varme", "Svendborg", "5700", "Region Syddanmark"),
        ("Nyborg Forsyning", "multiforsyning", "Nyborg", "5800", "Region Syddanmark"),
        ("Assens Forsyning", "multiforsyning", "Assens", "5610", "Region Syddanmark"),
        ("Tønder Forsyning", "multiforsyning", "Tønder", "6270", "Region Syddanmark"),

        # === Fra kortet: Øvrige ===
        ("Lolland Forsyning", "multiforsyning", "Nakskov", "4900", "Region Sjælland"),
        ("Guldborgsund Forsyning", "multiforsyning", "Nykøbing F", "4800", "Region Sjælland"),
        ("Kalundborg Forsyning", "multiforsyning", "Kalundborg", "4400", "Region Sjælland"),
        ("Odsherred Forsyning", "multiforsyning", "Nykøbing Sj", "4500", "Region Sjælland"),
        ("Sorø Forsyning", "multiforsyning", "Sorø", "4180", "Region Sjælland"),
    ]

    for name, sector, city, zip_code, notes in companies:
        conn.execute(
            "INSERT INTO companies (name, sector, city, zip_code, notes) VALUES (?, ?, ?, ?, ?)",
            (name, sector, city, zip_code, notes)
        )

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    by_sector = conn.execute(
        "SELECT sector, COUNT(*) FROM companies GROUP BY sector ORDER BY sector"
    ).fetchall()

    print(f"Database opdateret med {total} virksomheder:")
    for sector, count in by_sector:
        print(f"  {sector}: {count}")

    conn.close()

if __name__ == "__main__":
    run()
