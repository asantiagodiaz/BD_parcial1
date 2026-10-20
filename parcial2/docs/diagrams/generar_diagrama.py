"""Genera el diagrama de arquitectura del parcial 2 en .drawio (editable), .svg y .png.

Una sola descripcion (NODOS / ARISTAS) alimenta los tres formatos, asi nunca se desfasan.
Uso:  python generar_diagrama.py        (el .png requiere playwright + chromium)
"""

import html
import pathlib

OUT = pathlib.Path(__file__).resolve().parent
NOMBRE = "06-arquitectura-aws-parcial2"
W, H = 1280, 720

# Paleta por tipo de recurso
EST = {
    "user": ("#f1f3f5", "#495057"),
    "compute": ("#ffe8cc", "#d9480f"),
    "db": ("#d0ebff", "#1864ab"),
    "store": ("#d3f9d8", "#2b8a3e"),
    "analytics": ("#e5dbff", "#5f3dc4"),
    "note": ("#fff9db", "#e67700"),
}

# Contenedores: (id, x, y, w, h, titulo, stroke)
ZONAS = [
    ("aws", 250, 15, 1015, 690, "AWS Academy Learner Lab · us-east-1 · VPC por defecto · una sola AZ", "#232f3e"),
    ("trans", 270, 50, 975, 225, "Ruta transaccional (reservas) · nunca se mezcla con la analítica", "#1864ab"),
    ("anal", 270, 295, 975, 395, "Ruta analítica (limpieza por lotes + consultas del panel)", "#5f3dc4"),
]

# Nodos: (id, tipo, x, y, w, h, lineas)
NODOS = [
    ("cli", "user", 15, 75, 150, 70, ["Cliente", "buscar y reservar"]),
    ("ger", "user", 15, 180, 150, 70, ["Gerente", "panel de ocupación"]),
    ("ec2", "compute", 330, 95, 235, 110, ["EC2 t3.small", "FastAPI + frontend estático", "(un solo proceso, puerto 8000)"]),
    ("rds", "db", 690, 95, 190, 110, ["RDS PostgreSQL", "db.t3.micro · 1 AZ", "privada (solo la EC2)"]),
    ("ath", "analytics", 330, 355, 200, 90, ["Athena", "workgroup airline-wg", "tope 1 GB por consulta"]),
    ("glue", "analytics", 330, 545, 200, 90, ["Glue Data Catalog", "2 tablas · partition", "projection (sin crawlers)"]),
    ("cur", "store", 630, 355, 220, 90, ["S3 curated/", "Parquet por month=YYYY-MM", "24 particiones"]),
    ("emr", "compute", 630, 545, 220, 90, ["EMR · 1 × m4.large", "PySpark: reglas C1–C5", "efímero (--auto-terminate)"]),
    ("raw", "store", 940, 545, 200, 90, ["S3 raw/", "CSV crudo y sucio", "2,0 M de reservas"]),
    ("n1", "note", 900, 345, 330, 130,
     ["Datos del equipo (semilla 963)", "9 rutas · 150 asientos por vuelo · K = 8",
      "24 meses (2023-01 a 2024-12)", "Costo proyectado ≈ US$ 31,9 / mes"]),
    ("n2", "note", 910, 90, 320, 120,
     ["R2: sin sobreventa", "UPDATE ... WHERE seats_sold < capacity", "afecta 1 fila → 201; 0 filas → 409", "probado con 50 clientes simultáneos"]),
]

# Aristas: (origen, lado, destino, lado, etiqueta, dx_etiqueta, dy_etiqueta)
ARISTAS = [
    ("cli", "r", "ec2", "l:0.3", "buscar / reservar", 0, -10),
    ("ger", "r", "ec2", "l:0.7", "panel /manager", 0, 16),
    ("ec2", "r", "rds", "l", "UPDATE atómico", 0, -10),
    ("ec2", "b", "ath", "t", "consulta SQL a Athena", 0, 18),
    ("ath", "b", "glue", "t", "esquema de las 2 tablas", 0, 0),
    ("ath", "r", "cur", "l", "lee 1 mes", 0, -8),
    ("emr", "t", "cur", "b", "escribe Parquet", 0, 0),
    ("raw", "l", "emr", "r", "lee CSV", 0, -8),
]

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
    return (f'<mxfile host="app.diagrams.net"><diagram name="Arquitectura parcial 2" id="p2">'
            f'<mxGraphModel dx="1280" dy="720" grid="1" gridSize="10" page="1" pageWidth="{W}" pageHeight="{H}">'
            f'<root>{"".join(celdas)}</root></mxGraphModel></diagram></mxfile>')


def png(svg_path: pathlib.Path, png_path: pathlib.Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        pg.goto(svg_path.as_uri())
        pg.screenshot(path=str(png_path))
        b.close()


if __name__ == "__main__":
    (OUT / f"{NOMBRE}.svg").write_text(svg(), encoding="utf-8")
    (OUT / f"{NOMBRE}.drawio").write_text(drawio(), encoding="utf-8")
    png(OUT / f"{NOMBRE}.svg", OUT / f"{NOMBRE}.png")
    print("generados:", ", ".join(f"{NOMBRE}.{e}" for e in ("drawio", "svg", "png")))
