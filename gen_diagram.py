import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.lines as mlines

fig, ax = plt.subplots(figsize=(10, 14))
ax.set_xlim(0, 10)
ax.set_ylim(0, 14)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')

# ── Palette ───────────────────────────────────────────────────────────────────
COL = {
    1: ('#1A6FB5', '#E8F2FC'),   # albastru
    2: ('#1E8C5A', '#E6F6EF'),   # verde
    3: ('#C8680A', '#FDF0E2'),   # portocaliu
}
C_ARROW  = '#444444'
C_BADGE  = '#FFFFFF'

# ── Titlu ─────────────────────────────────────────────────────────────────────
ax.text(5, 13.5, 'Mecanism de cascadare – API-uri publice',
        ha='center', va='center', fontsize=16, fontweight='bold',
        color='#1A1A2E', fontfamily='DejaVu Sans')
ax.plot([0.6, 9.4], [13.15, 13.15], color='#CCCCCC', linewidth=1.5)

# ── Helper: API card ──────────────────────────────────────────────────────────
def api_card(num, title, domain, url, y_top):
    border, bg = COL[num]
    x, w, h = 0.7, 8.6, 1.8

    # corp card
    card = FancyBboxPatch((x, y_top - h), w, h,
                           boxstyle="round,pad=0.18",
                           facecolor=bg, edgecolor=border,
                           linewidth=2.2, zorder=3)
    ax.add_patch(card)

    # cerc numar
    circle = plt.Circle((x + 0.55, y_top - h/2), 0.34,
                          color=border, zorder=4)
    ax.add_patch(circle)
    ax.text(x + 0.55, y_top - h/2, str(num),
            ha='center', va='center', fontsize=14,
            fontweight='bold', color='white', zorder=5)

    # titlu API
    ax.text(x + 1.15, y_top - h*0.30,
            f'API {num}  –  {title}',
            ha='left', va='center', fontsize=13.5, fontweight='bold',
            color='#1A1A2E', zorder=4)

    # domeniu + url
    ax.text(x + 1.15, y_top - h*0.58,
            domain,
            ha='left', va='center', fontsize=11.5,
            color=border, fontweight='semibold', zorder=4)

    ax.text(x + 1.15, y_top - h*0.82,
            url,
            ha='left', va='center', fontsize=9,
            color='#777777', style='italic', zorder=4)

    return y_top - h   # returneaza y-ul de jos al cardului

# ── Helper: sageta + eticheta ─────────────────────────────────────────────────
def flow_arrow(y_from, y_to, label):
    xc = 5.0
    # linie verticala
    ax.annotate('', xy=(xc, y_to + 0.05), xytext=(xc, y_from - 0.05),
                arrowprops=dict(
                    arrowstyle='->', color=C_ARROW,
                    lw=2.2, mutation_scale=22,
                    connectionstyle='arc3,rad=0'),
                zorder=5)
    # eticheta pe sageta
    ymid = (y_from + y_to) / 2
    ax.text(xc + 0.25, ymid, label,
            ha='left', va='center', fontsize=11,
            color='#333355', zorder=6,
            bbox=dict(boxstyle='round,pad=0.4',
                      facecolor='#F0F0FF',
                      edgecolor='#9999CC',
                      linewidth=1.3))

# ── Carduri ───────────────────────────────────────────────────────────────────
gap   = 0.9
y_start = 12.8

y1b = api_card(1,
               'Detectie locatie geografica',
               'ipapi.co',
               'https://ipapi.co/json/',
               y_start)

flow_arrow(y1b, y1b - gap,
           'country_code = "RO"')

y2b = api_card(2,
               'Sarbatori legale',
               'date.nager.at',
               'https://date.nager.at/api/v3/NextPublicHolidays/{countryCode}',
               y1b - gap)

flow_arrow(y2b, y2b - gap,
           'RO  →  EUR  (mapare tara → moneda)')

y3b = api_card(3,
               'Curs valutar',
               'currency-api via jsDelivr',
               'https://cdn.jsdelivr.net/.../currencies/{moneda}.min.json',
               y2b - gap)

# ── Sageta finala ─────────────────────────────────────────────────────────────
y_res_top = y3b - 0.7
flow_arrow(y3b, y_res_top,
           '{ eur: { ron: 4.97 } }')

# ── Box rezultat ──────────────────────────────────────────────────────────────
res_h = 0.85
res_y = y_res_top - res_h

res_bg = FancyBboxPatch((0.7, res_y), 8.6, res_h,
                         boxstyle="round,pad=0.18",
                         facecolor='#EDE9FF', edgecolor='#6644CC',
                         linewidth=2.5, zorder=3)
ax.add_patch(res_bg)
ax.text(5.0, res_y + res_h / 2,
        'Rezultat:   1 EUR = 4.97 RON   (curs actualizat zilnic)',
        ha='center', va='center', fontsize=13, fontweight='bold',
        color='#4422AA', zorder=4)

# ── Nota API 4 ────────────────────────────────────────────────────────────────
note_y = 0.25
note_h = 0.80
note = FancyBboxPatch((0.7, note_y), 8.6, note_h,
                       boxstyle="round,pad=0.18",
                       facecolor='#FFFBF0', edgecolor='#DDAA44',
                       linewidth=1.8, linestyle='dashed', zorder=2)
ax.add_patch(note)
ax.text(5.0, note_y + note_h / 2,
        'API 4  –  qrserver.com  │  Generare cod QR (apel independent, la cerere)',
        ha='center', va='center', fontsize=11,
        color='#8B6500', zorder=4)

# ── Separator nainte de nota ──────────────────────────────────────────────────
ax.plot([0.7, 9.3], [note_y + note_h + 0.18, note_y + note_h + 0.18],
        color='#DDDDDD', linewidth=1.2, linestyle='--')

plt.tight_layout(pad=0.1)
out = r"C:\Users\Operator 1\OneDrive\Desktop\Diagrama_Cascadare_API.png"
plt.savefig(out, dpi=200, bbox_inches='tight', facecolor='white')
print(f"Salvat: {out}")
