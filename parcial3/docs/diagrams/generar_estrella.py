"""Diagrama del modelo estrella del parcial 3 (.svg y .png).

Columnas tomadas de backend/app/star_sql.py: negro = contrato (A.3), gris con "+" = atributo
agregado por el equipo. Las lineas unen cada clave foranea con la clave de su dimension.
Uso:  ../.venv/bin/python generar_estrella.py
"""

import html
import pathlib

OUT = pathlib.Path(__file__).resolve().parent
NOMBRE = "08-modelo-estrella-parcial3"
W, H = 1280, 790
ROW, HEAD = 19, 52

# (id, titulo, subtitulo, x, y, w, color, [(columna, tipo, rol)])  rol: pk, fk, c (contrato), x (extra), p (particion)
TABLAS = [
    ("dim_date", "dim_date", "1 fila por día · 2023-01-01 a 2027-12-31 · conformada", 20, 30, 330, "#1864ab", [
        ("date_key", "int", "pk"), ("full_date", "date", "c"), ("year", "int", "c"), ("quarter", "int", "c"),
        ("month", "int", "c"), ("month_name", "string", "x"), ("year_month", "string", "x"),
        ("day_of_month", "int", "x"), ("weekday", "int", "c"), ("weekday_name", "string", "c"),
        ("is_weekend", "boolean", "c"), ("is_holiday", "boolean", "c"), ("holiday_name", "string", "c"),
        ("is_long_weekend", "boolean", "c"), ("is_business_day", "boolean", "x")]),
    ("fact_search", "fact_search", "grano: 1 fila por búsqueda distinta (event_id)", 475, 30, 330, "#c2255c", [
        ("event_id", "string", "c"), ("date_key", "int", "fk"), ("route_key", "int", "fk"),
        ("results_count", "int", "c"), ("searches", "int (=1)", "c"), ("session_id", "string", "x"),
        ("travel_date", "date", "x"), ("days_to_travel", "int", "x"), ("event_ts", "string", "x"),
        ("month", "string YYYY-MM", "p")]),
    ("fact_booking_event", "fact_booking_event", "grano: 1 fila por reserva o cancelación distinta", 475, 330, 330, "#c2255c", [
        ("event_id", "string", "c"), ("date_key", "int", "fk"), ("route_key", "int", "fk"),
        ("fare_class_key", "int", "fk"), ("reservation_id", "string", "c"), ("event_type", "string", "c"),
        ("bookings", "int (1/0)", "c"), ("cancellations", "int (0/1)", "c"), ("revenue_cents", "bigint (±precio)", "c"),
        ("flight_id", "string", "x"), ("flight_date", "date", "x"), ("event_ts", "string", "x"),
        ("month", "string YYYY-MM", "p")]),
    ("dim_route", "dim_route", "SCD tipo 2 · 1 fila por versión · conformada", 930, 30, 330, "#2b8a3e", [
        ("route_key", "int", "pk"), ("route", "string", "c"), ("origin", "string", "c"), ("destination", "string", "c"),
        ("region", "string", "c"), ("route_category", "string", "c"), ("valid_from", "date (incl.)", "c"),
        ("valid_to", "date (excl.)", "c"), ("is_current", "boolean", "c"), ("version", "int", "x")]),
    ("dim_fare_class", "dim_fare_class", "1 fila por clase tarifaria", 930, 330, 330, "#e67700", [
        ("fare_class_key", "int", "pk"), ("fare_class", "string", "c"), ("fare_class_name", "string", "x"),
        ("cabin_rank", "int", "x")]),
]
T = {t[0]: t for t in TABLAS}

# (tabla_hecho, columna_fk, dimension)
RELACIONES = [
    ("fact_search", "date_key", "dim_date"), ("fact_search", "route_key", "dim_route"),
    ("fact_booking_event", "date_key", "dim_date"), ("fact_booking_event", "route_key", "dim_route"),
    ("fact_booking_event", "fare_class_key", "dim_fare_class"),
]


def esc(s):
    return html.escape(s, quote=False)


def fila_y(tid, col):
    _, _, _, x, y, w, _, cols = T[tid]
    i = [c[0] for c in cols].index(col)
    return y + HEAD + i * ROW + ROW / 2


def alto(tid):
    return HEAD + len(T[tid][7]) * ROW + 8


def svg():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="Segoe UI, Arial, sans-serif">', f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    # relaciones (debajo de las tablas)
    for f, col, d in RELACIONES:
        _, _, _, fx, fy, fw, _, _ = T[f]
        _, _, _, dx, dy, dw, _, _ = T[d]
        y1, y2 = fila_y(f, col), fila_y(d, T[d][7][0][0])
        if dx < fx:   # dimension a la izquierda
            x1, x2 = fx, dx + dw
        else:
            x1, x2 = fx + fw, dx
        mx = (x1 + x2) / 2
        o.append(f'<path d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}" fill="none" stroke="#495057" stroke-width="1.6"/>')
        o.append(f'<circle cx="{x2}" cy="{y2}" r="4" fill="#495057"/>')
        o.append(f'<text x="{x1 + (8 if x2 > x1 else -8)}" y="{y1 - 4}" font-size="10" fill="#495057" '
                 f'text-anchor="{"start" if x2 > x1 else "end"}">N</text>')
        o.append(f'<text x="{x2 + (-8 if x2 > x1 else 8)}" y="{y2 - 6}" font-size="10" fill="#495057" '
                 f'text-anchor="{"end" if x2 > x1 else "start"}">1</text>')
    for tid, tit, sub, x, y, w, color, cols in TABLAS:
        h = alto(tid)
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#ffffff" stroke="{color}" stroke-width="2"/>')
        o.append(f'<path d="M{x},{y + 8} a8,8 0 0 1 8,-8 h{w - 16} a8,8 0 0 1 8,8 v{HEAD - 14} h-{w} z" fill="{color}"/>')
        o.append(f'<text x="{x + 12}" y="{y + 21}" font-size="15" font-weight="700" fill="#ffffff">{esc(tit)}</text>')
        o.append(f'<text x="{x + 12}" y="{y + 38}" font-size="10.5" fill="#ffffff">{esc(sub)}</text>')
        for i, (c, ty, rol) in enumerate(cols):
            yy = y + HEAD + i * ROW + 14
            if i % 2:
                o.append(f'<rect x="{x + 2}" y="{yy - 13}" width="{w - 4}" height="{ROW}" fill="#f8f9fa"/>')
            marca = {"pk": "PK", "fk": "FK", "p": "PART"}.get(rol, "+" if rol == "x" else "")
            gris = rol == "x"
            col_txt = "#868e96" if gris else "#212529"
            o.append(f'<text x="{x + 12}" y="{yy}" font-size="10" font-weight="700" fill="{color}">{marca}</text>')
            o.append(f'<text x="{x + 52}" y="{yy}" font-size="12.5" fill="{col_txt}" '
                     f'font-weight="{"700" if rol in ("pk", "fk") else "400"}"'
                     f'{" font-style=\"italic\"" if gris else ""}>{esc(c)}</text>')
            o.append(f'<text x="{x + w - 12}" y="{yy}" font-size="11" text-anchor="end" fill="#868e96">{esc(ty)}</text>')
    ly = 690
    o.append(f'<rect x="20" y="{ly}" width="{W - 40}" height="86" rx="8" fill="#f8f9fa" stroke="#ced4da"/>')
    notas = [
        "PK = clave de la dimensión · FK = clave foránea · PART = columna de partición (las tablas de hechos se particionan por mes) · "
        "+ en gris = atributo agregado por el equipo (no lo exige el contrato).",
        "Medidas: fact_search.searches; fact_booking_event.bookings, cancellations y revenue_cents (la cancelación es una fila propia con ingreso negativo).",
        "dim_date y dim_route son conformadas: las comparten los dos hechos (Q6 y Q7). route_key apunta a la versión vigente en la fecha del evento "
        "(valid_from ≤ fecha < valid_to).",
        "Miembros 'UNKNOWN' con clave 0 en dim_route y dim_fare_class: un evento con ruta o clase desconocida nunca queda huérfano (R6).",
    ]
    for i, t in enumerate(notas):
        o.append(f'<text x="34" y="{ly + 22 + i * 18}" font-size="11.5" fill="#343a40">{esc(t)}</text>')
    o.append("</svg>")
    return "\n".join(o)


def drawio():
    """Misma figura en formato draw.io (editable): cada tabla es un contenedor y cada columna una celda."""
    q = lambda s: html.escape(s, quote=True)
    c = ['<mxfile host="generar_estrella.py"><diagram name="Modelo estrella" id="estrella">',
         f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" page="1" pageWidth="{W}" pageHeight="{H}">',
         '<root><mxCell id="0"/><mxCell id="1" parent="0"/>']
    for tid, tit, sub, x, y, w, color, cols in TABLAS:
        c.append(f'<mxCell id="{tid}" value="&lt;b&gt;{q(tit)}&lt;/b&gt;&lt;br&gt;&lt;font style=&quot;font-size:10px&quot;&gt;{q(q(sub))}&lt;/font&gt;" '
                 f'style="swimlane;html=1;startSize={HEAD};rounded=1;arcSize=4;fillColor={color};fontColor=#ffffff;'
                 f'strokeColor={color};strokeWidth=2;align=left;spacingLeft=10;fontSize=14;collapsible=0;swimlaneFillColor=#ffffff;" '
                 f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{alto(tid)}" as="geometry"/></mxCell>')
        for i, (col, ty, rol) in enumerate(cols):
            marca = {"pk": "PK", "fk": "FK", "p": "PART"}.get(rol, "+" if rol == "x" else "")
            gris = rol == "x"
            nombre = q(col)
            if rol in ("pk", "fk"):
                nombre = f"&lt;b&gt;{nombre}&lt;/b&gt;"
            if gris:
                nombre = f"&lt;i&gt;&lt;font color=&quot;#868e96&quot;&gt;{nombre}&lt;/font&gt;&lt;/i&gt;"
            valor = (f"&lt;font color=&quot;{color}&quot;&gt;&lt;b&gt;{marca}&lt;/b&gt;&lt;/font&gt;&amp;nbsp;&amp;nbsp;{nombre}"
                     f"&lt;span style=&quot;float:right;color:#868e96&quot;&gt;{q(q(ty))}&lt;/span&gt;")
            fondo = "#f8f9fa" if i % 2 else "none"
            c.append(f'<mxCell id="{tid}.{col}" value="{valor}" style="text;html=1;align=left;verticalAlign=middle;'
                     f'spacingLeft=10;spacingRight=10;fontSize=12;fillColor={fondo};strokeColor=none;" vertex="1" parent="{tid}">'
                     f'<mxGeometry y="{HEAD + i * ROW}" width="{w}" height="{ROW}" as="geometry"/></mxCell>')
    for n, (f, col, d) in enumerate(RELACIONES):
        c.append(f'<mxCell id="rel{n}" style="edgeStyle=entityRelationEdgeStyle;html=1;endArrow=ERmandOne;startArrow=ERmany;'
                 f'endFill=0;startFill=0;strokeColor=#495057;strokeWidth=1.5;" edge="1" parent="1" '
                 f'source="{f}.{col}" target="{d}.{T[d][7][0][0]}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    ly = 690
    notas = "&lt;br&gt;".join([
        "PK = clave de la dimensión · FK = clave foránea · PART = partición por mes · + en gris = atributo agregado por el equipo.",
        "Medidas: fact_search.searches; fact_booking_event.bookings, cancellations y revenue_cents (la cancelación es una fila con ingreso negativo).",
        "dim_date y dim_route son conformadas (Q6 y Q7). route_key apunta a la versión vigente en la fecha del evento (valid_from ≤ fecha &amp;lt; valid_to).",
        "Miembros 'UNKNOWN' con clave 0 en dim_route y dim_fare_class: ningún evento queda huérfano (R6).",
    ])
    c.append(f'<mxCell id="notas" value="{notas}" style="rounded=1;arcSize=6;html=1;whiteSpace=wrap;align=left;spacingLeft=14;'
             f'fontSize=11;fillColor=#f8f9fa;strokeColor=#ced4da;fontColor=#343a40;" vertex="1" parent="1">'
             f'<mxGeometry x="20" y="{ly}" width="{W - 40}" height="86" as="geometry"/></mxCell>')
    c.append("</root></mxGraphModel></diagram></mxfile>")
    return "\n".join(c)


if __name__ == "__main__":
    (OUT / f"{NOMBRE}.drawio").write_text(drawio(), encoding="utf-8")
    p = OUT / f"{NOMBRE}.svg"
    p.write_text(svg(), encoding="utf-8")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        pg.goto(p.as_uri())
        pg.screenshot(path=str(OUT / f"{NOMBRE}.png"))
        b.close()
    print("generados:", f"{NOMBRE}.drawio", f"{NOMBRE}.svg", f"{NOMBRE}.png")
