"""Genera el diagrama de arquitectura del parcial 3 en .drawio (editable), .svg y .png.

Una sola descripcion (NODOS / ARISTAS) alimenta los tres formatos, asi nunca se desfasan.
Mismo motor que el diagrama del parcial 2.
Uso:  ../.venv/bin/python generar_diagrama.py   (el .png usa playwright con el Chrome del sistema)
"""

import html
import pathlib

OUT = pathlib.Path(__file__).resolve().parent
NOMBRE = "07-arquitectura-aws-parcial3"
W, H = 1280, 1045

# Paleta por tipo de recurso
EST = {
    "user": ("#f1f3f5", "#495057"),
    "compute": ("#ffe8cc", "#d9480f"),
    "stream": ("#ffdeeb", "#c2255c"),
    "store": ("#d3f9d8", "#2b8a3e"),
    "analytics": ("#e5dbff", "#5f3dc4"),
    "note": ("#fff9db", "#e67700"),
}

# Contenedores: (id, x, y, w, h, titulo, stroke)
ZONAS = [
    ("aws", 250, 15, 1015, 690, "AWS Academy Learner Lab · us-east-1 · VPC por defecto · una sola AZ", "#232f3e"),
    ("rapido", 270, 50, 975, 225, "Ruta transaccional y camino rápido (segundos)", "#c2255c"),
    ("anal", 270, 295, 975, 395, "Camino analítico (minutos): landing zone y modelo estrella", "#5f3dc4"),
]

# Nodos: (id, tipo, x, y, w, h, lineas)
NODOS = [
    ("cli", "user", 15, 75, 185, 70, ["Cliente", "buscar · reservar · cancelar"]),
    ("ger", "user", 15, 180, 185, 70, ["Gerente", "panel en vivo"]),
    ("ec2", "compute", 300, 90, 250, 130, ["EC2 t3.small", "FastAPI + React + PostgreSQL 16", "hilo consumidor (vista en vivo)",
                                            "job refresh-star"]),
    ("kds", "stream", 720, 95, 200, 120, ["Kinesis Data Stream", "provisionado · 1 shard · 24 h", "sin enhanced fan-out",
                                           "solo mientras se prueba"]),
    ("fh", "stream", 720, 355, 200, 90, ["Kinesis Data Firehose", "búfer 60 s · gzip", "un evento por línea"]),
    ("raw", "store", 1000, 355, 220, 90, ["S3 raw/events/", "landing zone (append-only)", "JSON por línea, con duplicados"]),
    ("ath", "analytics", 720, 545, 200, 90, ["Athena", "workgroup airline-p3", "CTAS · tope 1 GB por consulta"]),
    ("glue", "analytics", 300, 545, 250, 90, ["Glue Data Catalog", "base airline_star", "3 dimensiones + 2 hechos"]),
    ("star", "store", 1000, 545, 220, 90, ["S3 star/", "Parquet · hechos por month", "reconstruido cada 10 min"]),
    ("n1", "note", 285, 345, 285, 130,
     ["Datos del equipo (semilla 963)", "9 rutas · 3 cambian de categoría",
      "replay: 20.509 → 19.912 eventos", "Costo proyectado ≈ US$ 18,2 / mes"]),
    ("n2", "note", 960, 85, 280, 140,
     ["Publicar sin frenar la API (R2)", "búsquedas: cola + PutRecords por lote", "reservas: PutRecord tras el commit",
      "p95 = 0,335 s con 50 clientes", "200 / 200 eventos en el stream"]),
]

# Aristas: (origen, lado, destino, lado, etiqueta, dx_etiqueta, dy_etiqueta)
ARISTAS = [
    ("cli", "r", "ec2", "l:0.3", "HTTP", 0, -10),
    ("ger", "r", "ec2", "l:0.7", "/manager", 0, 14),
    ("ec2", "r:0.3", "kds", "l:0.3", "eventos", 0, -10),
    ("kds", "l:0.75", "ec2", "r:0.75", "GetRecords c/1 s", 0, 14),
    ("kds", "b", "fh", "t", "lee el shard", 0, 0),
    ("fh", "r", "raw", "l", "cada 60 s", 0, -10),
    ("raw", "b:0.3", "ath", "t:0.7", "lee todo", 0, -6),
    ("ec2", "b:0.6", "ath", "t:0.3", "lanza CTAS (refresh-star)", 0, -62),
    ("ath", "r", "star", "l", "Parquet", 0, -10),
    ("ath", "l", "glue", "r", "registra tablas", 0, -10),
]

LEYENDA = [
    (1, "cli", "Cliente", ["Persona que busca, reserva o cancela desde el navegador (página /).",
                           "Cada acción produce exactamente un evento."]),
    (2, "ger", "Gerente", ["Ve en /manager las búsquedas, reservas y conversión de los últimos",
                           "minutos, y puede pedir que se reconstruya el modelo estrella."]),
    (3, "ec2", "EC2 t3.small", ["Una sola máquina: API, frontend, PostgreSQL y un hilo que lee el stream",
                                "y cuenta eventos por la hora en que ocurrieron (vista en vivo)."]),
    (4, "kds", "Kinesis Data Stream", ["Cola de eventos con 1 shard. Se crea con un script al empezar a probar",
                                       "y se borra al terminar, porque se cobra por cada hora que existe."]),
    (5, "fh", "Kinesis Data Firehose", ["Servicio gestionado que lee el stream y cada 60 s escribe un archivo",
                                        "comprimido en S3, con un evento por línea."]),
    (6, "raw", "S3 raw/events/", ["La landing zone: todos los eventos tal como llegaron, incluidos",
                                  "duplicados, tardíos y desordenados. Nunca se modifica."]),
    (7, "ath", "Athena", ["Ejecuta SQL sobre S3 sin servidores. Reconstruye la estrella (CTAS) y",
                          "responde las preguntas de negocio; cobra solo por los datos que lee."]),
    (8, "glue", "Glue Data Catalog", ["Guarda cómo son las tablas (columnas, tipos, particiones por mes) para",
                                      "que Athena las entienda. Las crea el propio refresco."]),
    (9, "star", "S3 star/", ["El modelo estrella en Parquet: dim_date, dim_route (SCD tipo 2),",
                             "dim_fare_class, fact_search y fact_booking_event."]),
]
NUM = {nid: n for n, nid, _, _ in LEYENDA}
LEY_X, LEY_Y, LEY_W, LEY_H = 15, 725, 1250, 305

DIM = {n[0]: n for n in NODOS}


def frac(lado: str) -> tuple[str, float]:
    base, _, f = lado.partition(":")
    return base, float(f) if f else 0.5


def ancla(nid: str, lado: str) -> tuple[float, float]:
    _, _, x, y, w, h, _ = DIM[nid]
    base, f = frac(lado)
    return {"l": (x, y + h * f), "r": (x + w, y + h * f), "t": (x + w * f, y), "b": (x + w * f, y + h)}[base]


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ---------------------------------------------------------------- SVG
def svg() -> str:
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="Segoe UI, Arial, sans-serif">',
         '<defs><marker id="f" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
         'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#343a40"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    for _, x, y, w, h, t, c in ZONAS:
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{c}" '
                 f'stroke-width="2" stroke-dasharray="7 5"/>')
        o.append(f'<text x="{x + w - 14}" y="{y + 24}" font-size="14" font-weight="600" text-anchor="end" fill="{c}">{esc(t)}</text>')
    for a, la, b, lb, et, dx, dy in ARISTAS:
        (x1, y1), (x2, y2) = ancla(a, la), ancla(b, lb)
        o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#343a40" stroke-width="2" marker-end="url(#f)"/>')
        mx, my = (x1 + x2) / 2 + dx, (y1 + y2) / 2 + dy
        ancho = 7.0 * len(et) + 12
        o.append(f'<rect x="{mx - ancho / 2}" y="{my - 11}" width="{ancho}" height="18" rx="4" fill="#ffffff" fill-opacity="0.92"/>')
        o.append(f'<text x="{mx}" y="{my + 3}" font-size="12" text-anchor="middle" fill="#212529">{esc(et)}</text>')
    for nid, tipo, x, y, w, h, lineas in NODOS:
        fill, stroke = EST[tipo]
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        n = len(lineas)
        y0 = y + h / 2 - (n - 1) * 9 + 4
        for i, t in enumerate(lineas):
            peso = "700" if i == 0 else "400"
            tam = 14 if i == 0 else 12
            ali, px = ("start", x + 14) if tipo == "note" else ("middle", x + w / 2)
            o.append(f'<text x="{px}" y="{y0 + i * 18}" font-size="{tam}" font-weight="{peso}" '
                     f'text-anchor="{ali}" fill="#212529">{esc(t)}</text>')
    for nid, n in NUM.items():
        _, _, x, y, w, h, _ = DIM[nid]
        o.append(f'<circle cx="{x}" cy="{y}" r="12" fill="#212529"/>')
        o.append(f'<text x="{x}" y="{y + 4.5}" font-size="13" font-weight="700" text-anchor="middle" fill="#ffffff">{n}</text>')
    o.append(f'<rect x="{LEY_X}" y="{LEY_Y}" width="{LEY_W}" height="{LEY_H}" rx="10" fill="#f8f9fa" stroke="#868e96" stroke-width="1.5"/>')
    o.append(f'<text x="{LEY_X + 20}" y="{LEY_Y + 28}" font-size="15" font-weight="700" fill="#212529">¿Qué es cada cosa?  '
             f'<tspan font-weight="400" font-size="12" fill="#495057">(los números marcan cada elemento del diagrama; las flechas indican hacia dónde viajan los datos)</tspan></text>')
    for i, (n, nid, tit, lin) in enumerate(LEYENDA):
        col, fila = (0, i) if i < 5 else (1, i - 5)
        x0, y0 = LEY_X + 20 + col * 620, LEY_Y + 62 + fila * 47
        o.append(f'<circle cx="{x0 + 10}" cy="{y0 - 4}" r="10" fill="#212529"/>')
        o.append(f'<text x="{x0 + 10}" y="{y0}" font-size="12" font-weight="700" text-anchor="middle" fill="#ffffff">{n}</text>')
        o.append(f'<text x="{x0 + 28}" y="{y0}" font-size="13" font-weight="700" fill="#212529">{esc(tit)}</text>')
        for j, t in enumerate(lin):
            o.append(f'<text x="{x0 + 28}" y="{y0 + 15 + j * 14}" font-size="11.5" fill="#343a40">{esc(t)}</text>')
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------- draw.io
def drawio() -> str:
    celdas = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for zid, x, y, w, h, t, c in ZONAS:
        celdas.append(
            f'<mxCell id="z_{zid}" value="{html.escape(t)}" style="rounded=1;whiteSpace=wrap;html=1;fillColor=none;'
            f'strokeColor={c};strokeWidth=2;dashed=1;verticalAlign=top;align=right;spacingRight=12;fontStyle=1;'
            f'fontColor={c};" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for nid, tipo, x, y, w, h, lineas in NODOS:
        fill, stroke = EST[tipo]
        valor = f"<b>{html.escape(lineas[0])}</b><br>" + "<br>".join(html.escape(l) for l in lineas[1:])
        align = "left;spacingLeft=10" if tipo == "note" else "center"
        celdas.append(
            f'<mxCell id="{nid}" value="{html.escape(valor)}" style="rounded=1;whiteSpace=wrap;html=1;fillColor={fill};'
            f'strokeColor={stroke};strokeWidth=2;align={align};" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for i, (a, la, b, lb, et, _, _) in enumerate(ARISTAS):
        def pos(lado):
            base, f = frac(lado)
            return {"l": (0, f), "r": (1, f), "t": (f, 0), "b": (f, 1)}[base]
        sx, sy = pos(la)
        tx, ty = pos(lb)
        celdas.append(
            f'<mxCell id="e{i}" value="{html.escape(et)}" style="endArrow=classic;html=1;strokeWidth=2;'
            f'exitX={sx};exitY={sy};entryX={tx};entryY={ty};labelBackgroundColor=#ffffff;" edge="1" parent="1" '
            f'source="{a}" target="{b}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    for nid, n in NUM.items():
        _, _, x, y, w, h, _ = DIM[nid]
        celdas.append(
            f'<mxCell id="b{n}" value="{n}" style="ellipse;whiteSpace=wrap;html=1;fillColor=#212529;fontColor=#ffffff;'
            f'strokeColor=#212529;fontStyle=1;aspect=fixed;" vertex="1" parent="1">'
            f'<mxGeometry x="{x - 12}" y="{y - 12}" width="24" height="24" as="geometry"/></mxCell>')
    cuerpo = "<br>".join(
        f"<b>{n}. {html.escape(tit)}</b>: " + " ".join(html.escape(t) for t in lin) for n, _, tit, lin in LEYENDA)
    celdas.append(
        f'<mxCell id="leyenda" value="{html.escape("<b>¿Qué es cada cosa?</b><br>" + cuerpo)}" '
        f'style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f8f9fa;strokeColor=#868e96;align=left;verticalAlign=top;'
        f'spacingLeft=14;spacingTop=8;fontSize=11;" vertex="1" parent="1">'
        f'<mxGeometry x="{LEY_X}" y="{LEY_Y}" width="{LEY_W}" height="{LEY_H}" as="geometry"/></mxCell>')
    return (f'<mxfile host="app.diagrams.net"><diagram name="Arquitectura parcial 3" id="p3">'
            f'<mxGraphModel dx="1280" dy="720" grid="1" gridSize="10" page="1" pageWidth="{W}" pageHeight="{H}">'
            f'<root>{"".join(celdas)}</root></mxGraphModel></diagram></mxfile>')


def png(svg_path: pathlib.Path, png_path: pathlib.Path, solo_diagrama: pathlib.Path | None = None) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        pg.goto(svg_path.as_uri())
        pg.screenshot(path=str(png_path))
        if solo_diagrama:  # recorte sin el panel de leyenda, para el documento (la leyenda va como texto)
            pg.screenshot(path=str(solo_diagrama), clip={"x": 0, "y": 0, "width": W, "height": LEY_Y - 10})
        b.close()


if __name__ == "__main__":
    (OUT / f"{NOMBRE}.svg").write_text(svg(), encoding="utf-8")
    (OUT / f"{NOMBRE}.drawio").write_text(drawio(), encoding="utf-8")
    png(OUT / f"{NOMBRE}.svg", OUT / f"{NOMBRE}.png", OUT / f"{NOMBRE}-sin-leyenda.png")
    print("generados:", ", ".join(f"{NOMBRE}.{e}" for e in ("drawio", "svg", "png")))
