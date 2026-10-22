"""Convierte documento-final.html en PARCIAL2-ENTREGA.pdf con Chromium (Playwright).

Uso:  python generar_pdf.py
"""
import pathlib

from playwright.sync_api import sync_playwright

AQUI = pathlib.Path(__file__).resolve().parent

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto((AQUI / "documento-final.html").as_uri())
    pg.wait_for_load_state("networkidle")
    pg.pdf(
        path=str(AQUI / "PARCIAL2-ENTREGA.pdf"),
        format="A4",
        print_background=True,
        display_header_footer=True,
        header_template="<span></span>",
        footer_template=(
            '<div style="font-size:8px;width:100%;text-align:center;color:#000;">'
            'Parcial 2 · Panel gerencial de ocupación · página <span class="pageNumber"></span> de '
            '<span class="totalPages"></span></div>'
        ),
        margin={"top": "20mm", "bottom": "18mm", "left": "18mm", "right": "18mm"},
    )
    b.close()
print("generado PARCIAL2-ENTREGA.pdf")
