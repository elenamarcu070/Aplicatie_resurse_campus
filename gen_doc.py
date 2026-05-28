from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

for sec in doc.sections:
    sec.top_margin    = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    sec.left_margin   = Cm(3.0)
    sec.right_margin  = Cm(2.0)

# =============================================================================
# HELPERS
# =============================================================================

def set_font(run, name="Times New Roman", size=12, bold=False, italic=False, color=None):
    run.font.name   = name
    run.font.size   = Pt(size)
    run.font.bold   = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)

def para(text="", align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=12, bold=False,
         italic=False, space_before=0, space_after=8, left_indent=0):
    p = doc.add_paragraph()
    p.paragraph_format.alignment    = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    p.paragraph_format.left_indent  = Cm(left_indent)
    p.paragraph_format.first_line_indent = Cm(1.25) if align == WD_ALIGN_PARAGRAPH.JUSTIFY else Cm(0)
    if text:
        r = p.add_run(text)
        set_font(r, size=size, bold=bold, italic=italic)
    return p

def para_no_indent(text="", align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=12, bold=False,
                   italic=False, space_before=0, space_after=8):
    p = doc.add_paragraph()
    p.paragraph_format.alignment    = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    if text:
        r = p.add_run(text)
        set_font(r, size=size, bold=bold, italic=italic)
    return p

def heading(text, level=1):
    sizes   = {1: 14, 2: 13, 3: 12}
    spacing = {1: 24, 2: 18, 3: 14}
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(spacing.get(level, 14))
    p.paragraph_format.space_after  = Pt(6)
    r = p.add_run(text)
    set_font(r, size=sizes.get(level, 12), bold=True)
    pPr = p._p.get_or_add_pPr()
    kwn = OxmlElement('w:keepNext')
    pPr.append(kwn)
    return p

def bullet(text, indent=1.25):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.left_indent  = Cm(indent)
    p.paragraph_format.space_after  = Pt(3)
    r = p.add_run(text)
    set_font(r, size=12)
    return p

def code_block(lines):
    if isinstance(lines, str):
        lines = lines.split('\n')
    for line in lines:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.left_indent  = Cm(0.5)
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'),   'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'),  'F4F4F4')
        pPr.append(shd)
        r = p.add_run(line if line else ' ')
        set_font(r, name='Courier New', size=9)

def page_break():
    doc.add_page_break()

def tbl_row(tbl, cells, header=False):
    row = tbl.add_row()
    for i, txt in enumerate(cells):
        cell = row.cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        r = p.add_run(txt)
        set_font(r, size=11, bold=header)
        p.paragraph_format.space_after  = Pt(2)
        p.paragraph_format.space_before = Pt(2)
    return row

def image_placeholder(text):
    """Rand italic centrat pentru locul imaginii – de inlocuit cu Insert > Picture."""
    p = doc.add_paragraph()
    p.paragraph_format.alignment   = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(4)
    r = p.add_run(text)
    set_font(r, size=10, italic=True, color=(120, 120, 120))
    return p

def caption(text):
    p = doc.add_paragraph()
    p.paragraph_format.alignment   = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(12)
    r = p.add_run(text)
    set_font(r, size=10, italic=True)
    return p

def add_footer_page_numbers():
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        fp.clear()
        fp.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_prefix = fp.add_run("- ")
        set_font(r_prefix, size=10)
        fldChar1  = OxmlElement('w:fldChar'); fldChar1.set(qn('w:fldCharType'), 'begin')
        instrText = OxmlElement('w:instrText'); instrText.text = 'PAGE'
        fldChar2  = OxmlElement('w:fldChar'); fldChar2.set(qn('w:fldCharType'), 'end')
        run_el = OxmlElement('w:r')
        run_el.append(fldChar1); run_el.append(instrText); run_el.append(fldChar2)
        fp._p.append(run_el)
        r_suffix = fp.add_run(" -")
        set_font(r_suffix, size=10)

# =============================================================================
# COPERTĂ
# =============================================================================

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(40)
p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('UNIVERSITATEA TEHNICA "GHEORGHE ASACHI" DIN IASI')
set_font(r, size=12, bold=True)

para_no_indent("Facultatea de Automatica si Calculatoare",
               align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_after=6)
para_no_indent("Master – Calculatoare si Tehnologia Informatiei",
               align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_after=60)

p2 = doc.add_paragraph()
p2.paragraph_format.alignment    = WD_ALIGN_PARAGRAPH.CENTER
p2.paragraph_format.space_before = Pt(40)
r2 = p2.add_run("Integrare API-uri si REST API")
set_font(r2, size=20, bold=True)

para_no_indent("Dashboard interactiv pentru aplicatia de rezervari spalatorie",
               align=WD_ALIGN_PARAGRAPH.CENTER, size=14, italic=True,
               space_before=8, space_after=60)

para_no_indent("Documentatie de proiect",
               align=WD_ALIGN_PARAGRAPH.CENTER, size=12, space_after=4)
para_no_indent("Tehnologii si Arhitecturi pentru Dezvoltare",
               align=WD_ALIGN_PARAGRAPH.CENTER, size=12, space_after=80)

p3 = doc.add_paragraph()
p3.paragraph_format.alignment    = WD_ALIGN_PARAGRAPH.CENTER
p3.paragraph_format.space_before = Pt(60)
r3 = p3.add_run("Masterand: Marcu Elena")
set_font(r3, size=12)

para_no_indent("Specializarea: Calculatoare si Tehnologia Informatiei",
               align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_after=4)
para_no_indent("An universitar: 2025 – 2026",
               align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_before=30)

page_break()

# =============================================================================
# CUPRINS
# =============================================================================

heading("CUPRINS", level=1)

toc = [
    ("1. Introducere", "3"),
    ("2. Arhitectura sistemului", "4"),
    ("3. Integrarea API-urilor publice", "5"),
    ("   3.1 Detectia locatiei geografice (ipapi.co)", "5"),
    ("   3.2 Sarbatori legale (date.nager.at)", "6"),
    ("   3.3 Curs valutar (currency-api)", "6"),
    ("   3.4 Generare cod QR (qrserver.com)", "7"),
    ("   3.5 Mecanismul de cascadare", "7"),
    ("4. Proiectarea si implementarea REST API", "8"),
    ("   4.1 Resursa masini – colectie si item", "8"),
    ("   4.2 Endpoint-uri auxiliare", "10"),
    ("5. Baza de date", "11"),
    ("6. Interfata dashboard", "12"),
    ("7. Concluzii", "13"),
    ("8. Bibliografie", "14"),
    ("9. Anexa – Cod sursa", "15"),
]

for label, pg in toc:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    rl = p.add_run(label)
    set_font(rl, size=12)
    rd = p.add_run(" " + "." * max(2, 62 - len(label)) + " ")
    set_font(rd, size=12)
    rp = p.add_run(pg)
    set_font(rp, size=12)

page_break()

# =============================================================================
# 1. INTRODUCERE
# =============================================================================

heading("1. Introducere", level=1)

para(
    "Lucrarea de fata documenteaza componenta de integrare API dezvoltata in cadrul "
    "aplicatiei web washtuiasi.ro – un sistem de rezervari pentru masinile de spalat "
    "din caminele studentesti ale Universitatii Tehnice \"Gheorghe Asachi\" din Iasi. "
    "Aplicatia de baza permite studentilor autentificati cu cont institutional Google "
    "sa rezerve intervale orare la masinile de spalat din caminul in care sunt cazati, "
    "iar administratorilor sa gestioneze masinile si programul de functionare."
)

para(
    "In contextul disciplinei Tehnologii si Arhitecturi pentru Dezvoltare, aplicatia "
    "a fost extinsa cu o pagina dedicata – accesibila la adresa washtuiasi.ro/api-dashboard/ – "
    "care grupeaza doua componente tehnice distincte: un REST API propriu pentru "
    "gestionarea inventarului de masini si un set de integrari cu API-uri publice externe, "
    "orchestrate printr-un mecanism de cascadare."
)

para(
    "Serverul ruleaza pe un VPS public, baza de date utilizata este PostgreSQL, iar "
    "backend-ul este implementat in Python cu framework-ul Django. Interfata dashboard "
    "foloseste HTML5, Bootstrap 5, JavaScript cu Fetch API si Chart.js pentru vizualizarea datelor."
)

image_placeholder("[ Figura 1 – Screenshot pagina /api-dashboard/ in browser ]")
caption("Figura 1. Pagina de dashboard cu toate sectiunile vizibile.")

page_break()

# =============================================================================
# 2. ARHITECTURA SISTEMULUI
# =============================================================================

heading("2. Arhitectura sistemului", level=1)

para(
    "Sistemul urmeaza o arhitectura client-server clasica, in care backend-ul Django "
    "expune endpoint-uri HTTP, iar frontend-ul JavaScript le consuma prin Fetch API. "
    "Componenta REST API si cea de integrare cu servicii externe sunt izolate in "
    "subdirectorul booking/api/ si nu interfereaza cu logica aplicatiei principale."
)

tbl = doc.add_table(rows=1, cols=2)
tbl.style = 'Table Grid'
tbl.columns[0].width = Cm(4)
tbl.columns[1].width = Cm(11)
tbl_row(tbl, ["Componenta", "Detalii tehnice"], header=True)
for cells in [
    ("Backend",      "Django 4.x (Python) – routing, ORM, autentificare Google OAuth2"),
    ("Baza de date", "PostgreSQL – gazduita pe VPS-ul aplicatiei"),
    ("REST API",     "Modul booking/api/ – views.py, urls.py, utils.py"),
    ("Frontend",     "HTML5, CSS3, Bootstrap 5, JavaScript ES2017 (async/await), Chart.js"),
    ("Hosting",      "Server VPS public – domeniu washtuiasi.ro"),
]:
    tbl_row(tbl, cells)

para_no_indent()

para(
    "Modulul REST API este inregistrat in rutarea principala Django sub prefixul /api/ "
    "si contine trei fisiere: views.py cu logica endpoint-urilor, urls.py cu definitia "
    "rutelor si utils.py cu functii ajutatoare reutilizabile (serializare, parsare JSON, "
    "gestionarea erorilor HTTP)."
)

para(
    "Mediul de test al API-ului este izolat printr-un camin virtual denumit API_TEST, "
    "creat automat la primul apel REST prin functia ensure_camin_test() din utils.py. "
    "Toate operatiunile CRUD se executa exclusiv asupra acestui camin, lasand neafectate "
    "datele de productie ale aplicatiei."
)

page_break()

# =============================================================================
# 3. INTEGRAREA API-URILOR PUBLICE
# =============================================================================

heading("3. Integrarea API-urilor publice", level=1)

para(
    "Sectiunea de informatii din dashboard integreaza patru API-uri publice externe, "
    "toate accesibile fara autentificare. Primele trei formeaza un lant de cascadare "
    "in care raspunsul unui apel constituie parametrul de intrare pentru urmatorul."
)

# 3.1
heading("3.1 Detectia locatiei geografice – ipapi.co", level=2)

para(
    "La incarcarea paginii se efectueaza un apel GET catre https://ipapi.co/json/. "
    "Serviciul returneaza un obiect JSON cu informatii despre adresa IP a clientului, "
    "printre care si campul country_code (ISO 3166-1 alpha-2, ex: RO, DE, GB). "
    "Codul tarii este extras si folosit simultan ca parametru pentru apelurile "
    "catre API 2 si API 3, constituind primul nod al lantului de cascadare."
)

para(
    "Utilizatorul poate suprascrie tara detectata automat prin intermediul unui dropdown "
    "de selectie. La orice schimbare a valorii din dropdown se redeclaseaza intregul "
    "lant de cascadare, actualizand in timp real toate datele derivate."
)

# 3.2
heading("3.2 Sarbatori legale – date.nager.at", level=2)

para(
    "Al doilea apel din lant tinteste endpoint-ul "
    "https://date.nager.at/api/v3/NextPublicHolidays/{countryCode}, unde countryCode "
    "este valoarea obtinuta de la API 1. Raspunsul este un array JSON cu urmatoarele "
    "sarbatori legale pentru tara respectiva, fiecare continand data calendaristica "
    "si denumirea locala a sarbatorii. Pagina afiseaza primele patru intrari din lista."
)

# 3.3
heading("3.3 Curs valutar – currency-api via jsDelivr", level=2)

para(
    "La finalul procesarii raspunsului de la API 2 se efectueaza automat un al treilea "
    "apel, catre serviciul @fawazahmed0/currency-api distribuit prin CDN-ul jsDelivr: "
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{moneda}.min.json."
)

para(
    "Codul tarii este mai intai transformat in codul monedei locale printr-un dictionar "
    "de mapare definit in JavaScript (RO -> EUR, GB -> GBP, HU -> HUF, BG -> BGN etc.). "
    "Raspunsul contine cursurile de schimb ale monedei respective fata de toate celelalte "
    "valute; pagina extrage valoarea corespunzatoare RON si o afiseaza impreuna cu data "
    "la care a fost calculat cursul."
)

# 3.4
heading("3.4 Generare cod QR – qrserver.com", level=2)

para(
    "Independent de lantul de cascadare, fiecare masina din lista API_TEST dispune de "
    "un buton care genereaza un cod QR la cerere. La apasarea butonului, browser-ul "
    "incarca imaginea de la https://api.qrserver.com/v1/create-qr-code/?size=110x110&data={encoded_data}, "
    "unde parametrul data contine identificatorul masinii si domeniul aplicatiei, "
    "codificat URL. Imaginea este afisata inline, sub randul respectiv din tabel."
)

# 3.5
heading("3.5 Mecanismul de cascadare", level=2)

para(
    "Cascadarea este implementata prin functii JavaScript asincrone legate in serie "
    "cu async/await. Functia loadSarbatori() initiaza lantul apeland ipapi.co, "
    "dupa care apeleaza fetchSarbatoriPentruTara() cu codul tarii obtinut. "
    "Aceasta din urma actualizeaza lista de sarbatori si apeleaza la randul ei "
    "updateCursValutar() cu acelasi cod de tara. Erori le de retea sunt prinse "
    "cu try/catch si semnalate utilizatorului prin notificari toast."
)

code_block([
    "ipapi.co/json/",
    "   |",
    '   | country_code = "RO"  (valoare preluata si folosita ca parametru)',
    "   v",
    "date.nager.at/api/v3/NextPublicHolidays/RO",
    "   |",
    "   | RO  ->  EUR  (mapare tara -> moneda)",
    "   v",
    "currency-api/v1/currencies/eur.min.json",
    "   |",
    "   | { eur: { ron: 4.97 } }",
    "   v",
    "   Afisare curs: 1 EUR = 4.97 RON",
])

para_no_indent()

image_placeholder("[ Figura 2 – Sectiunea \"Informatii\" cu tara setata pe DE: sarbatori germane + curs EUR/RON ]")
caption("Figura 2. Cascadare demonstrata prin schimbarea tarii in dropdown.")

page_break()

# =============================================================================
# 4. REST API
# =============================================================================

heading("4. Proiectarea si implementarea REST API", level=1)

para(
    "REST API-ul este implementat in modulul booking/api/ si expune resursa masini "
    "conform principiilor arhitecturii REST: identificare prin URI, operatiuni exprimate "
    "prin verbe HTTP, raspunsuri in format JSON si coduri de stare HTTP semantice. "
    "Resursa este accesibila atat la nivel de colectie cat si la nivel de item individual."
)

# 4.1
heading("4.1 Resursa masini – colectie si item", level=2)

para_no_indent("Colectia este expusa la endpoint-ul /api/masini/ si suporta patru verbe HTTP:",
               space_after=6)

tbl2 = doc.add_table(rows=1, cols=4)
tbl2.style = 'Table Grid'
tbl2.columns[0].width = Cm(2.5)
tbl2.columns[1].width = Cm(5)
tbl2.columns[2].width = Cm(5)
tbl2.columns[3].width = Cm(3)
tbl_row(tbl2, ["Verb HTTP", "Actiune", "Body cerere", "Cod raspuns"], header=True)
for r in [
    ("GET",    "Listeaza toate masinile din API_TEST",
     "–",                                 "200 OK"),
    ("POST",   "Adauga o masina noua",
     '{"nume": "...", "activa": true}',   "201 Created"),
    ("PUT",    "Inlocuieste intreaga colectie",
     '[{"nume": "..."}, ...]',             "200 OK"),
    ("DELETE", "Sterge toate masinile din API_TEST",
     "–",                                 "200 OK"),
]:
    tbl_row(tbl2, r)

para_no_indent()

para_no_indent("Itemul individual este accesibil la /api/masini/<id>/ si suporta:",
               space_after=6)

tbl3 = doc.add_table(rows=1, cols=4)
tbl3.style = 'Table Grid'
tbl3.columns[0].width = Cm(2.5)
tbl3.columns[1].width = Cm(5)
tbl3.columns[2].width = Cm(5)
tbl3.columns[3].width = Cm(3)
tbl_row(tbl3, ["Verb HTTP", "Actiune", "Body cerere", "Cod raspuns"], header=True)
for r in [
    ("GET",    "Returneaza masina cu ID-ul dat",
     "–",                                "200 / 404"),
    ("POST",   "Creeaza masina cu ID explicit",
     '{"nume": "..."}',                  "201 / 409"),
    ("PUT",    "Actualizeaza sau creeaza masina (upsert)",
     '{"nume": "...", "activa": true}',  "200 / 201"),
    ("DELETE", "Sterge masina specificata",
     "–",                                "200 / 404"),
]:
    tbl_row(tbl3, r)

para_no_indent()

para(
    "Implementarea foloseste decoratorul @csrf_exempt pentru endpoint-urile care accepta "
    "scriere, permitand testarea din clienti externi (Postman, curl) fara token CSRF. "
    "Logica fiecarui verb este separata prin ramuri if pe request.method, iar "
    "raspunsurile de eroare urmeaza un format JSON uniform, cu campul \"error\" "
    "si codul de stare HTTP corespunzator (400, 404, 405, 409)."
)

para(
    "Verbul PUT pe colectie implementeaza un inlocuitor complet (replace): stergere "
    "urmata de recreare. Verbul PUT pe item implementeaza upsert prin Django ORM "
    "(update_or_create), returnand 201 daca resursa a fost creata sau 200 daca a "
    "fost actualizata."
)

image_placeholder("[ Figura 3 – Raspuns JSON al GET /api/masini/ in browser sau Postman ]")
caption("Figura 3. Raspuns JSON al endpoint-ului de colectie.")

# 4.2
heading("4.2 Endpoint-uri auxiliare", level=2)

tbl4 = doc.add_table(rows=1, cols=3)
tbl4.style = 'Table Grid'
tbl4.columns[0].width = Cm(5.5)
tbl4.columns[1].width = Cm(2)
tbl4.columns[2].width = Cm(8)
tbl_row(tbl4, ["Endpoint", "Verb", "Descriere"], header=True)
for r in [
    ("/api/",                          "GET",
     "Documentatie API – resurse disponibile si URL-urile aferente"),
    ("/api/camine/",                   "GET",
     "Lista tuturor caminelor din baza de date"),
    ("/api/masini-camin/?camin_id=X",  "GET",
     "Masinile unui camin specific, filtrate dupa ID"),
    ("/api/statistici/avansate/",      "GET",
     "Statistici agregate: total rezervari, distributie prioritati, date zilnice"),
]:
    tbl_row(tbl4, r)

para_no_indent()

para(
    "Endpoint-ul de statistici accepta parametrii: period (saptamana sau luna), "
    "referinta (data de referinta in format YYYY-MM-DD), camin_id si masina_id "
    "pentru filtrare. Raspunsul include campul per_zi – un array cu numarul de "
    "rezervari pentru fiecare zi din intervalul selectat – folosit pentru generarea "
    "graficului bar din dashboard."
)

page_break()

# =============================================================================
# 5. BAZA DE DATE
# =============================================================================

heading("5. Baza de date", level=1)

para(
    "Baza de date utilizata este PostgreSQL, gazduita pe acelasi VPS cu aplicatia. "
    "Accesul se realizeaza exclusiv prin Django ORM; nu exista interogari SQL scrise "
    "manual in codul API-ului. Operatiunile REST se traduc direct in apeluri ORM: "
    "objects.filter() pentru GET, objects.create() pentru POST, "
    "objects.update_or_create() pentru PUT si objects.delete() pentru DELETE."
)

tbl5 = doc.add_table(rows=1, cols=3)
tbl5.style = 'Table Grid'
tbl5.columns[0].width = Cm(3)
tbl5.columns[1].width = Cm(8)
tbl5.columns[2].width = Cm(4.5)
tbl_row(tbl5, ["Model Django", "Campuri relevante", "Relatii"], header=True)
for r in [
    ("Camin",     "id, nume, durata_interval",
     "One-to-Many catre Masina"),
    ("Masina",    "id, nume, activa, camin (FK)",
     "Many-to-One catre Camin"),
    ("Rezervare", "data_rezervare, ora_start, ora_final, nivel_prioritate (1–4), anulata",
     "FK catre Masina si User"),
]:
    tbl_row(tbl5, r)

para_no_indent()

para(
    "Nivelul de prioritate al unei rezervari (1 = maxima, 4 = scazuta) este atribuit "
    "automat de aplicatie in functie de numarul de rezervari efectuate de student in "
    "saptamana curenta. Endpoint-ul de statistici agrega aceste valori prin "
    "annotate(count=Count(\"id\")) si le returneaza grupate, permitand vizualizarea "
    "distributiei in graficul doughnut din dashboard."
)

page_break()

# =============================================================================
# 6. INTERFATA DASHBOARD
# =============================================================================

heading("6. Interfata dashboard", level=1)

para(
    "Pagina /api-dashboard/ reuneste intr-o singura interfata web toate componentele "
    "descrise in capitolele anterioare. Aceasta nu face parte din fluxul aplicatiei "
    "principale si nu este accesibila studentilor; reprezinta o pagina dedicata "
    "demonstrarii si testarii functionalitatilor implementate."
)

para(
    "Interfata este organizata in trei sectiuni. Prima sectiune afiseaza statisticile "
    "de rezervari: un selector de camin, butoane de navigare inapoi si inainte pentru "
    "saptamana sau luna si doua grafice generate cu Chart.js – unul de tip bara pentru "
    "distributia pe zile si unul de tip doughnut pentru distributia pe niveluri de "
    "prioritate."
)

image_placeholder("[ Figura 4 – Sectiunea statistici: grafic bar si doughnut ]")
caption("Figura 4. Grafice generate din datele returnate de /api/statistici/avansate/.")

para(
    "A doua sectiune permite testarea interactiva a REST API-ului: adaugare masina "
    "noua (POST colectie), editare prin modal Bootstrap 5 (PUT item), stergere "
    "individuala (DELETE item) si stergere in masa a intregii colectii. Fiecare "
    "operatiune este confirmata printr-o notificare toast afisata in coltul ecranului."
)

image_placeholder("[ Figura 5 – Lista masini API_TEST cu modalul de editare deschis ]")
caption("Figura 5. Modal Bootstrap 5 pentru actualizarea unei masini prin PUT.")

para(
    "A treia sectiune prezinta datele obtinute de la API-urile externe: dropdown-ul "
    "de selectie a tarii, lista de sarbatori legale si cursul valutar al zilei, "
    "actualizate in timp real la orice schimbare a tarii selectate."
)

page_break()

# =============================================================================
# 7. CONCLUZII
# =============================================================================

heading("7. Concluzii", level=1)

para(
    "Lucrarea prezinta implementarea unui modul API integrat intr-o aplicatie web Django "
    "existenta, aflata in productie. Au fost dezvoltate doua componente tehnice "
    "complementare: un REST API complet cu suport pentru verbele GET, POST, PUT si "
    "DELETE atat pe colectie cat si pe item, si un set de integrari cu patru API-uri "
    "publice externe, orchestrate printr-un mecanism de cascadare implementat in JavaScript."
)

para(
    "Izolarea mediului de test prin caminul virtual API_TEST permite demonstrarea "
    "tuturor operatiunilor CRUD fara riscul afectarii datelor reale. "
    "Arhitectura modulara a codului – separarea in views.py, urls.py si utils.py – "
    "faciliteaza extinderea ulterioara a API-ului cu noi resurse."
)

para(
    "O posibila directie de dezvoltare ulterioara consta in securizarea endpoint-urilor "
    "REST prin autentificare bazata pe token (JWT sau Django REST Framework TokenAuth), "
    "precum si extinderea API-ului pentru a expune si resursa rezervarilor, nu doar "
    "pe cea a masinilor."
)

page_break()

# =============================================================================
# 8. BIBLIOGRAFIE
# =============================================================================

heading("8. Bibliografie", level=1)

refs = [
    ("Django Software Foundation. Django Documentation, 2024.",
     "https://docs.djangoproject.com/"),
    ("Mozilla Developer Network. HTTP request methods.",
     "https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods"),
    ("Mozilla Developer Network. Fetch API.",
     "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API"),
    ("Fielding, R. T. Architectural Styles and the Design of Network-based Software Architectures. "
     "Doctoral dissertation, University of California, Irvine, 2000.",
     "https://ics.uci.edu/~fielding/pubs/dissertation/top.htm"),
    ("Internet Engineering Task Force. RFC 9110: HTTP Semantics, 2022.",
     "https://www.rfc-editor.org/rfc/rfc9110"),
    ("Bootstrap Team. Bootstrap 5 Documentation.",
     "https://getbootstrap.com/docs/5.0/"),
    ("Chart.js Contributors. Chart.js Documentation.",
     "https://www.chartjs.org/docs/"),
    ("ipapi.co. IP Address Location API.",
     "https://ipapi.co/"),
    ("Nager.Date. Public Holiday API.",
     "https://date.nager.at/"),
    ("Fawazahmed0. Exchange-API – Currency Exchange Rates.",
     "https://github.com/fawazahmed0/exchange-api"),
    ("GoQR.me. QR Code API.",
     "https://goqr.me/api/"),
]

for i, (label, url) in enumerate(refs, 1):
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(5)
    p.paragraph_format.left_indent  = Cm(0.6)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    r1 = p.add_run(f"[{i}] {label} ")
    set_font(r1, size=11)
    r2 = p.add_run(url)
    set_font(r2, size=11, italic=True)

page_break()

# =============================================================================
# 9. ANEXA – COD SURSA
# =============================================================================

heading("9. Anexa – Cod sursa", level=1)

heading("9.1 booking/api/urls.py", level=2)
code_block("""from django.urls import path
from . import views

urlpatterns = [
    path("", views.api_root),
    path("masini/", views.masini_list),
    path("masini/<int:id>/", views.masina_detail),
    path("camine/", views.get_camine),
    path("masini-camin/", views.get_masini),
    path("statistici/avansate/", views.statistici_avansate),
]""")

para_no_indent()

heading("9.2 booking/api/utils.py", level=2)
code_block("""import json
from django.http import JsonResponse
from booking.models import Camin

API_TEST_CAMIN_NAME = "API_TEST"

def ensure_camin_test():
    camin, _ = Camin.objects.get_or_create(
        nume=API_TEST_CAMIN_NAME,
        defaults={"durata_interval": 2},
    )
    return camin

def parse_json_body(request):
    if not request.body:
        return {}, None
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, JsonResponse(
            {"error": "JSON invalid in corpul cererii"}, status=400)

def method_not_allowed(allowed_methods):
    return JsonResponse(
        {"error": "Metoda HTTP nepermisa", "allowed": allowed_methods},
        status=405)

def masina_to_dict(masina):
    return {"id": masina.id, "nume": masina.nume,
            "activa": masina.activa, "camin_id": masina.camin_id}""")

para_no_indent()

heading("9.3 booking/api/views.py (fragmente reprezentative)", level=2)
code_block("""from datetime import date, timedelta
import calendar
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from booking.models import Camin, Masina, Rezervare
from .utils import ensure_camin_test, masina_to_dict, method_not_allowed, parse_json_body

ZI_SAPTAMANA = ["Luni", "Marti", "Miercuri", "Joi", "Vineri", "Sambata", "Duminica"]
PRIORITATE_LABELS = {1: "Maxima", 2: "Inalta", 3: "Medie", 4: "Scazuta"}

@csrf_exempt
def masini_list(request):
    camin_test = ensure_camin_test()
    if request.method == "GET":
        return JsonResponse(
            list(Masina.objects.filter(camin=camin_test).values()),
            safe=False, status=200)
    if request.method == "POST":
        data, err = parse_json_body(request)
        if err: return err
        masina = Masina.objects.create(
            nume=data.get("nume", "").strip(),
            camin=camin_test,
            activa=data.get("activa", True))
        return JsonResponse(
            {"message": "Masina creata", "masina": masina_to_dict(masina)},
            status=201)
    if request.method == "PUT":
        data, err = parse_json_body(request)
        if err: return err
        Masina.objects.filter(camin=camin_test).delete()
        created = [
            masina_to_dict(Masina.objects.create(
                nume=item.get("nume", "").strip(),
                camin=camin_test,
                activa=item.get("activa", True)))
            for item in data if item.get("nume")]
        return JsonResponse({"message": "Lista inlocuita", "masini": created}, status=200)
    if request.method == "DELETE":
        deleted, _ = Masina.objects.filter(camin=camin_test).delete()
        return JsonResponse({"message": "Sterse", "deleted": deleted}, status=200)
    return method_not_allowed(["GET", "POST", "PUT", "DELETE"])

@csrf_exempt
def masina_detail(request, id):
    camin_test = ensure_camin_test()
    if request.method == "GET":
        try:
            m = Masina.objects.get(id=id, camin=camin_test)
        except Masina.DoesNotExist:
            return JsonResponse({"error": "Masina nu exista"}, status=404)
        return JsonResponse(masina_to_dict(m), status=200)
    if request.method == "PUT":
        data, err = parse_json_body(request)
        if err: return err
        m, created = Masina.objects.update_or_create(
            id=id,
            defaults={"nume": data.get("nume", "").strip(),
                      "camin": camin_test,
                      "activa": data.get("activa", True)})
        return JsonResponse(
            {"message": "Creata" if created else "Actualizata",
             "masina": masina_to_dict(m)},
            status=201 if created else 200)
    if request.method == "DELETE":
        try:
            Masina.objects.get(id=id, camin=camin_test).delete()
        except Masina.DoesNotExist:
            return JsonResponse({"error": "Masina nu exista"}, status=404)
        return JsonResponse({"message": "Masina stearsa"}, status=200)
    return method_not_allowed(["GET", "POST", "PUT", "DELETE"])""")

para_no_indent()

heading("9.4 dashboard.html – JavaScript cascadare API-uri publice", level=2)
code_block("""async function loadSarbatori() {
    try {
        const ipRes  = await fetch('https://ipapi.co/json/');
        const ipData = await ipRes.json();
        const countryCode = ipData.country_code || 'RO';
        const select = document.getElementById('tara_select');
        if ([...select.options].some(o => o.value === countryCode))
            select.value = countryCode;
        await fetchSarbatoriPentruTara(countryCode);
    } catch (e) {
        await fetchSarbatoriPentruTara('RO');
    }
}

async function fetchSarbatoriPentruTara(countryCode) {
    const res  = await fetch(
        `https://date.nager.at/api/v3/NextPublicHolidays/${countryCode}`);
    const data = await res.json();
    let html = '';
    data.slice(0, 4).forEach(s => {
        const d   = new Date(s.date);
        const fmt = d.toLocaleDateString('ro-RO',
            { day: 'numeric', month: 'long', year: 'numeric' });
        html += `<div class="holiday-item"><b>${fmt}</b> - ${s.localName}</div>`;
    });
    document.getElementById('sarbatori').innerHTML = html;
    await updateCursValutar(countryCode);
}

const MONEDE = {
    RO: 'EUR', DE: 'EUR', FR: 'EUR', GB: 'GBP',
    HU: 'HUF', BG: 'BGN', MD: 'MDL', US: 'USD'
};

async function updateCursValutar(countryCode) {
    const moneda = MONEDE[countryCode] || 'EUR';
    document.getElementById('curs_titlu').textContent = `Curs ${moneda} / RON`;
    const res  = await fetch(
        `https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest` +
        `/v1/currencies/${moneda.toLowerCase()}.min.json`);
    const data = await res.json();
    const ron  = data[moneda.toLowerCase()].ron;
    document.getElementById('curs').innerHTML =
        `<div class="rate-number">1 ${moneda} = ${ron.toFixed(4)} RON</div>
         <small>${data.date}</small>`;
}""")

# =============================================================================
# FOOTER SI SALVARE
# =============================================================================

add_footer_page_numbers()

out = r"C:\Users\Operator 1\OneDrive\Desktop\Documentatie_TAD_2026_v3.docx"
doc.save(out)
print(f"Salvat: {out}")
