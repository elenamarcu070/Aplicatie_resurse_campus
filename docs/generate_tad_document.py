"""Genereaza documentul Word pentru proiectul TAD."""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "TAD_Proiect_WashTUIasi.docx"

VIEWS = (ROOT / "booking/api/views.py").read_text(encoding="utf-8")
URLS = (ROOT / "booking/api/urls.py").read_text(encoding="utf-8")
UTILS = (ROOT / "booking/api/utils.py").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "booking/templates/api/dashboard.html").read_text(encoding="utf-8")
JS_START = DASHBOARD.index("// ——— API-uri publice ———")
JS_END = DASHBOARD.index("// ——— Init ———")
JS_PUBLIC = DASHBOARD[JS_START:JS_END].strip()


def set_margins(doc):
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)


def set_default_font(doc, name="Times New Roman", size=12):
    style = doc.styles["Normal"]
    style.font.name = name
    style.font.size = Pt(size)
    rfonts = style.element.rPr.rFonts
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:cs"), name)


def configure_headings(doc):
    for level, size in [(1, 16), (2, 14)]:
        h = doc.styles[f"Heading {level}"]
        h.font.name = "Times New Roman"
        h.font.size = Pt(size)
        h.font.bold = True
        h.font.color.rgb = RGBColor(0, 0, 0)


def add_page_number_footer(doc):
    for section in doc.sections:
        footer = section.footer
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = " PAGE "
        fld_sep = OxmlElement("w:fldChar")
        fld_sep.set(qn("w:fldCharType"), "separate")
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        run._r.append(fld_begin)
        run._r.append(instr)
        run._r.append(fld_sep)
        run._r.append(fld_end)
        run.font.name = "Times New Roman"
        run.font.size = Pt(11)


def add_toc(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = r'TOC \o "1-2" \h \z \u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(fld_end)
    note = doc.add_paragraph(
        "(Deschideți documentul în Microsoft Word și apăsați Ctrl+A, apoi F9 "
        "pentru a actualiza cuprinsul și numerele de pagină.)"
    )
    note.runs[0].italic = True
    note.runs[0].font.size = Pt(10)


def add_body(doc, text):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    for run in p.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)


def add_bullet(doc, text):
    p = doc.add_paragraph(text, style="List Bullet")
    for run in p.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)


def add_code_block(doc, title, code):
    h = doc.add_heading(title, level=2)
    for run in h.runs:
        run.font.name = "Times New Roman"
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(12)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), "F2F2F2")
    p._p.get_or_add_pPr().append(shading)
    run = p.add_run(code)
    run.font.name = "Courier New"
    run.font.size = Pt(10)


def build():
    doc = Document()
    set_margins(doc)
    set_default_font(doc)
    configure_headings(doc)

    # --- COPERTA ---
    for _ in range(6):
        doc.add_paragraph()
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("WashTUIasi — Sistem de rezervări\nresurse campus studențesc")
    r.bold = True
    r.font.size = Pt(22)
    r.font.name = "Times New Roman"

    for text, size, bold in [
        ("Proiect TAD 2026", 16, True),
        ("Universitatea Tehnica Gheorghe Asachi din Iași", 14, False),
        ("", 12, False),
        ("Student: Elena Marcu", 14, False),
        ("An universitar: 2025-2026", 14, False),
        ("", 12, False),
        ("URL: https://washtuiasi.ro", 12, False),
        ("Dashboard TAD: https://washtuiasi.ro/api-dashboard/", 12, False),
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.font.name = "Times New Roman"
        run.font.size = Pt(size)
        run.bold = bold

    doc.add_page_break()

    # --- CUPRINS ---
    doc.add_heading("CUPRINS", level=1)
    add_toc(doc)
    doc.add_page_break()

    # --- 3. PREZENTAREA TEMEI ---
    doc.add_heading("3. PREZENTAREA TEMEI (CE?)", level=1)
    add_body(
        doc,
        "Aplicația WashTUIasi este un sistem web de rezervări pentru mașinile de spălat "
        "din căminele studențești ale Universității Tehnice Gheorghe Asachi din Iași. "
        "Studenții se autentifică cu contul Google și pot rezerva intervale orare la "
        "mașinile de spălat din căminul în care sunt repartizați. Administratorii de cămin "
        "gestionează mașinile, studenții, programul și pot importa liste de studenți.",
    )
    add_body(
        doc,
        "Aplicația este disponibilă public la adresa washtuiasi.ro și este folosită în "
        "căminele universității. Backend-ul este implementat în Django (Python), iar datele "
        "sunt persistate într-o bază de date PostgreSQL găzduită pe platformă cloud.",
    )
    add_body(doc, "Proiectul TAD extinde aplicația existentă cu următoarele componente:")
    for item in [
        "Un REST API complet (GET, POST, PUT, DELETE) pentru resursa mașini, "
        "implementat conform modelului RESTful prezentat la curs;",
        "Integrarea a patru API-uri publice externe, cu cascadare între servicii "
        "(ipapi.co → date.nager.at → currency-api);",
        "Un dashboard web interactiv la /api-dashboard/ care demonstrează toate "
        "funcționalitățile API-ului propriu și ale serviciilor externe;",
        "Statistici avansate asupra rezervărilor reale, cu grafice Chart.js și "
        "navigare temporală (săptămână/lună).",
    ]:
        add_bullet(doc, item)

    # --- 4. JUSTIFICAREA ---
    doc.add_heading("4. JUSTIFICAREA TEMEI (DE CE?)", level=1)
    add_body(
        doc,
        "Problema reală: în căminele studențești, resursele partajate (mașini de spălat) "
        "sunt limitate. Studenții nu știu în mod intuitiv când sunt libere mașinile, ceea ce "
        "duce la cozi, suprapuneri și timp pierdut. O aplicație centralizată de rezervări "
        "rezolvă această problemă prin alocare transparentă a intervalelor orare.",
    )
    add_body(
        doc,
        "Relevanța domeniului: proiectul combină dezvoltarea web, servicii REST, integrarea "
        "API-urilor externe și persistența în baza de date — competențe centrale pentru "
        "specializările tehnice (IoT, informatică, electronică aplicată). Administrarea "
        "resurselor partajate din cămine reprezintă un caz de utilizare concret și verificabil.",
    )
    add_body(
        doc,
        "Valoarea adăugată a API-ului REST: expunerea datelor structurate JSON permite "
        "integrarea cu alte sisteme — aplicații mobile, panouri de monitorizare, sisteme "
        "de notificare (SMS, WhatsApp, push) sau roboți de raportare. API-ul respectă "
        "verbele HTTP standard și codurile de stare, fiind testabil cu REST Client sau Postman.",
    )
    add_body(
        doc,
        "Izolarea mediului de test: toate operațiunile CRUD pe resursa mașini din API "
        "se execută exclusiv pe căminul API_TEST, creat automat la migrare. Datele reale "
        "ale aplicației (cămine, studenți, rezervări efective) nu sunt modificate prin "
        "demonstrațiile TAD, ceea ce permite testarea liberă în producție.",
    )

    # --- 5. DESCRIEREA ---
    doc.add_heading("5. DESCRIEREA FUNCȚIONALITĂȚII (CUM?)", level=1)

    doc.add_heading("5.1 Arhitectura aplicației", level=2)
    add_body(
        doc,
        "Arhitectura generală urmează modelul client-server clasic. Clientul (browser web) "
        "comunică cu serverul Django prin HTTP/HTTPS. Serverul procesează cererile, "
        "interoghează baza de date PostgreSQL prin Django ORM și returnează răspunsuri "
        "HTML (interfață) sau JSON (API REST).",
    )
    for item in [
        "Backend: Django 5 (Python), autentificare Google via django-allauth, "
        "notificări Twilio/WhatsApp, Firebase push;",
        "Frontend: template-uri Django, HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js, Font Awesome;",
        "Bază de date: PostgreSQL pe server cloud (Railway), accesată prin DATABASE_URL;",
        "Hosting: washtuiasi.ro — server public accesibil din internet, cu SSL;",
        "Static files: WhiteNoise + Gunicorn pentru servirea în producție.",
    ]:
        add_bullet(doc, item)

    doc.add_heading("5.2 REST API — Resursa mașini", level=2)
    add_body(
        doc,
        "Resursa principală expusă pentru Tema 2 și Tema 3 este colecția de mașini de spălat "
        "din mediul de test. API-ul este montat sub prefixul /api/ și returnează exclusiv JSON.",
    )
    add_body(doc, "COLLECTION: /api/masini/")
    for item in [
        "GET → returnează lista tuturor mașinilor din API_TEST (JSON array, status 200);",
        'POST → creează o mașină nouă; body: {"nume": "...", "activa": true}; status 201;',
        'PUT → înlocuiește întreaga listă; body: [{"nume": "..."}, ...]; status 200;',
        "DELETE → șterge toate mașinile din mediul test; status 200;",
        "PATCH / alte metode → status 405 (Method Not Allowed).",
    ]:
        add_bullet(doc, item)

    add_body(doc, "ITEM: /api/masini/<id>/")
    for item in [
        "GET → returnează o mașină specifică; status 200 sau 404;",
        'POST → creează mașină cu ID fix dacă nu există; status 201 sau 409;',
        'PUT → actualizează mașina existentă (200) sau o creează dacă nu există (201);',
        "DELETE → șterge mașina; status 200 sau 404.",
    ]:
        add_bullet(doc, item)

    add_body(doc, "Alte endpoint-uri auxiliare:")
    for item in [
        "GET /api/ → documentație JSON cu lista resurselor disponibile;",
        "GET /api/camine/ → lista căminelor (id, nume);",
        "GET /api/masini-camin/?camin_id=X → mașinile unui cămin;",
        "GET /api/statistici/avansate/?camin_id=&period=saptamana|luna&referinta=YYYY-MM-DD"
        "&masina_id=&zi= → statistici agregate; returnează total, prioritati, per_zi, perioada.",
    ]:
        add_bullet(doc, item)

    add_body(
        doc,
        "Codurile de stare HTTP implementate: 200 (OK), 201 (Created), 400 (Bad Request), "
        "404 (Not Found), 405 (Method Not Allowed), 409 (Conflict). Răspunsurile de eroare "
        "conțin câmpul error cu mesaj descriptiv în limba română.",
    )

    doc.add_heading("5.3 API-uri publice integrate (cascadare)", level=2)
    add_body(
        doc,
        "Modulul 1 TAD cere utilizarea a cel puțin două API-uri publice, preferabil cu "
        "cascadare (output-ul unui API devine input pentru altul). Dashboard-ul integrează "
        "patru servicii externe, apelate din browser cu fetch().",
    )

    add_body(doc, "API 1 — ipapi.co (detecție locație)")
    for item in [
        "Apelat automat la încărcarea paginii /api-dashboard/;",
        "URL: https://ipapi.co/json/;",
        "Returnează codul țării utilizatorului (ex: RO);",
        "Output-ul (country_code) este folosit ca input pentru API 2 și pentru selectarea monedei.",
    ]:
        add_bullet(doc, item)

    add_body(doc, "API 2 — date.nager.at (sărbători legale)")
    for item in [
        "Primește codul țării de la API 1 sau din dropdown-ul utilizatorului;",
        "URL: https://date.nager.at/api/v3/NextPublicHolidays/{countryCode};",
        "Returnează următoarele sărbători legale pentru țara selectată;",
        "Utilizatorul poate schimba țara → lista se actualizează live.",
    ]:
        add_bullet(doc, item)

    add_body(doc, "API 3 — currency-api via jsDelivr (curs valutar)")
    for item in [
        "Apelat simultan cu API 2, folosind moneda corespunzătoare țării;",
        "URL: https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{moneda}.min.json;",
        "Afișează: 1 EUR = X RON și o spălare (5 RON) ≈ Y EUR;",
        "Mapare țară → monedă definită în JavaScript (RO→EUR, GB→GBP, US→USD etc.).",
    ]:
        add_bullet(doc, item)

    add_body(doc, "API 4 — qrserver.com (generare QR Code)")
    for item in [
        "Generat pentru fiecare mașină din lista API_TEST;",
        "URL: https://api.qrserver.com/v1/create-qr-code/?size=110x110&data=...;",
        "QR-ul conține: numele mașinii, ID-ul și domeniul washtuiasi.ro.",
    ]:
        add_bullet(doc, item)

    add_body(doc, "CASCADARE (cerința de punctaj maxim):")
    add_body(
        doc,
        "ipapi.co → detectează țara → date.nager.at primește codul țării → "
        "currency-api primește moneda corespunzătoare → afișare simultană în dashboard.",
    )

    doc.add_heading("5.4 Dashboard-ul web (/api-dashboard/)", level=2)
    for item in [
        "Statistici rezervări reale cu grafice Chart.js: bar chart pe zile, doughnut pe priorități;",
        "Navigare temporală: selector săptămână/lună, butoane ← →, buton Azi;",
        "Filtrare pe cămin, mașină și zi specifică;",
        "Gestionare mașini API_TEST: adaugă, editează (modal Bootstrap), șterge, înlocuiește lista;",
        "Secțiunea Informații utile (sărbători + curs valutar) la finalul paginii;",
        "Toast notifications pentru feedback la acțiuni CRUD;",
        "Design consistent cu aplicația principală (fundal, culori, Bootstrap 5).",
    ]:
        add_bullet(doc, item)

    doc.add_heading("5.5 Baza de date", level=2)
    add_body(
        doc,
        "Modelul principal pentru statistici este Rezervare, cu câmpurile: data_rezervare, "
        "ora_start, ora_end, masina (cheie străină către Masina), utilizator (cheie străină "
        "către User), nivel_prioritate (1–4, calculat automat în funcție de ordinea "
        "rezervărilor din săptămână), anulata (boolean), created_at.",
    )
    add_body(
        doc,
        "Toate operațiunile REST API pe resursa mașini se execută pe baza de date reală "
        "prin Django ORM (PostgreSQL). Statisticile avansează interogări agregate "
        "(Count, filter pe interval) asupra tabelei Rezervare. Migrarea 0012_camin_api_test "
        "creează automat căminul API_TEST la deploy.",
    )
    add_body(
        doc,
        "Testarea API-ului se poate realiza cu REST Client (extensie browser), Postman "
        "(colectia docs/tad_api.postman_collection.json) sau direct din dashboard-ul web.",
    )

    # --- 6. BIBLIOGRAFIE ---
    doc.add_heading("6. BIBLIOGRAFIE", level=1)
    refs = [
        "Django Documentation — https://docs.djangoproject.com/",
        "Bootstrap 5 — https://getbootstrap.com/",
        "Chart.js — https://www.chartjs.org/",
        "ipapi.co — https://ipapi.co/",
        "Nager.Date API — https://date.nager.at/",
        "Fawazahmed0 Currency API — https://github.com/fawazahmed0/exchange-api",
        "QR Server API — https://goqr.me/api/",
        "MDN Web Docs — REST — https://developer.mozilla.org/",
        "Roy Fielding — REST — https://ics.uci.edu/~fielding/pubs/dissertation/top.htm",
        "Damian Cătălin — Materiale curs TAD 2026, Universitatea Tehnică Gheorghe Asachi din Iași.",
    ]
    for ref in refs:
        add_bullet(doc, ref)

    doc.add_page_break()

    # --- 7. ANEXA ---
    doc.add_heading("7. ANEXĂ — COD SURSĂ", level=1)
    add_body(
        doc,
        "Anexa conține fragmentele de cod sursă relevante pentru componenta TAD a proiectului. "
        "Codul complet al aplicației este disponibil în repository-ul GitHub al proiectului.",
    )
    add_code_block(doc, "Anexa A — booking/api/views.py", VIEWS)
    doc.add_page_break()
    add_code_block(doc, "Anexa B — booking/api/urls.py", URLS)
    add_code_block(doc, "Anexa C — booking/api/utils.py", UTILS)
    doc.add_page_break()
    add_code_block(
        doc,
        "Anexa D — dashboard.html (secțiunea JavaScript — API-uri publice)",
        JS_PUBLIC,
    )

    add_page_number_footer(doc)
    doc.save(OUT)
    print(f"Document generat: {OUT}")


if __name__ == "__main__":
    build()
