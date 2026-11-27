import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
import datetime
from zoneinfo import ZoneInfo
import io
import json
import os
import re
import smtplib
import unicodedata
from email.message import EmailMessage

try:
    from pypdf import PdfReader, PdfWriter
    PYPDF_OK = True
except Exception:
    try:
        from PyPDF2 import PdfReader, PdfWriter
        PYPDF_OK = True
    except Exception:
        PYPDF_OK = False

# --- REGLAS COMERCIALES INTERNAS (OCULTAS EN PANTALLA PARA TODOS) ---
MIN_PZAS_NIVEL_2 = 50
MIN_PZAS_NIVEL_3 = 60
MAX_DESC_PCT = 10.0  # Límite máximo permitido de descuento (10%)
PRECIOS_INCLUYEN_IVA = False  # False = Precios más 16% IVA | True = Precios con IVA incluido
CARPETA_FICHAS = "fichas_tecnicas"  # También busca en la raíz como respaldo

def ahora_mx():
    """Devuelve fecha y hora local de Veracruz/México (corrige desfase +6h UTC)."""
    try:
        return datetime.datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-6)))

# --- PERFILES FISCALES Y BANCARIOS REALES (6 SUCURSALES / 3 RAZONES SOCIALES) ---
CONFIG_SUCURSALES = {
    "IMAC": {
        "nombre_oficial": "IMAC DE VERACRUZ S.A. DE C.V.",
        "sucursal_corta": "Sucursal Matriz",
        "razon_social": "IMAC DE VERACRUZ S.A. DE C.V.",
        "rfc": "IVE840928BS5",
        "direccion": "Boulevard Miguel Alemán 759, Col. Centro, Veracruz, Ver. C.P. 91700",
        "telefono": "(229) 9 35 39 40",
        "correo": "ventas@grupo-imac.com",
        "banco": "BBVA",
        "cuenta": "0134508394",
        "clabe": "012905001345083942",
        "leyenda_entrega": "Precios de contado Libre Abordo Veracruz, Ver.",
        "leyenda_extra": "",
        "prefijo_folio": "IVR"
    },
    "IMACRIL CENTRO": {
        "nombre_oficial": "IMACRIL S.A. DE C.V.",
        "sucursal_corta": "Sucursal Veracruz Centro",
        "razon_social": "IMACRIL S.A. DE C.V.",
        "rfc": "IMA770713FP6",
        "direccion": "Av. 5 de Mayo no. 1334, Col. Centro, Veracruz, Ver. C.P. 91700",
        "telefono": "(229) 9 32 14 24",
        "correo": "imacril@grupo-imac.com",
        "banco": "BBVA",
        "cuenta": "0447608314",
        "clabe": "012905004476083148",
        "leyenda_entrega": "Precios de contado Libre Abordo Veracruz, Ver.",
        "leyenda_extra": "",
        "prefijo_folio": "IMC"
    },
    "EJÉRCITO": {
        "nombre_oficial": "TARC S.A. DE C.V.",
        "sucursal_corta": "Sucursal Ejército Mexicano",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "TAR9803175MA",
        "direccion": "López Ruiz no. 30 esquina Ejército Mexicano, Col. Ylang Ylang, Boca del Río, Ver. C.P. 94298",
        "telefono": "(229) 130 08 01",
        "correo": "ejercito@grupo-imac.com",
        "banco": "BBVA",
        "cuenta": "0153947750",
        "clabe": "012905001539477500",
        "leyenda_entrega": "Precios de contado Libre Abordo Boca del Río, Ver.",
        "leyenda_extra": "",
        "prefijo_folio": "EJE"
    },
    "BOCA DEL RÍO": {
        "nombre_oficial": "TARC S.A. DE C.V.",
        "sucursal_corta": "Sucursal Boca del Río",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "TAR9803175MA",
        "direccion": "Boulevard Miguel Alemán 306, Col. Centro, Boca del Río, Ver. C.P. 94290",
        "telefono": "(229) 9 86 35 72",
        "correo": "bocadelrio@grupo-imac.com",
        "banco": "BBVA",
        "cuenta": "0131349694",
        "clabe": "012905001313496943",
        "leyenda_entrega": "Precios de contado Libre Abordo Boca del Río, Ver.",
        "leyenda_extra": "",
        "prefijo_folio": "FRB"
    },
    "FRAMBOYANES": {
        "nombre_oficial": "TARC S.A. DE C.V.",
        "sucursal_corta": "Sucursal Framboyanes",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "TAR9803175MA",
        "direccion": "Carretera libre Xalapa, Manuel de Jesús Clouthier No. 9339, Col. Zona Industrial Bruno Pagliai, Tejería, Veracruz. C.P. 91697",
        "telefono": "(229) 165 11 17",
        "correo": "framboyanes@grupo-imac.com",
        "banco": "BBVA",
        "cuenta": "0160290548",
        "clabe": "012905001602905488",
        "leyenda_entrega": "Precios de contado Libre Abordo Destino",
        "leyenda_extra": "",
        "prefijo_folio": "FFB"
    },
    "RIVIERA": {
        "nombre_oficial": "TARC S.A. DE C.V.",
        "sucursal_corta": "Sucursal Riviera",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "TAR9803175MA",
        "direccion": "Blvd. Playa Dorada Mz. 21 Lt. 1, Fracc. Playa Dorada, Alvarado, Ver. C.P. 95264",
        "telefono": "(229) 448 18 65",
        "correo": "riviera@grupo-imac.com",
        "banco": "BBVA",
        "cuenta": "0124562488",
        "clabe": "012905001245624883",
        "leyenda_entrega": "Precios de contado Libre Abordo Destino",
        "leyenda_extra": "",
        "prefijo_folio": "RIV"
    }
}

# --- CATÁLOGO AUDITADO: 74 PRODUCTOS MXN (SIN IVA) ---
_CATS = {
    "PAN": "Paneles (Tablaroca / Durock)",
    "PAS": "Pastas, Basecoat y Yesos",
    "PLA": "Plafones y Suspensión",
    "PCO": "Perfiles Comerciales",
    "PUS": "Perfiles USG",
    "IMP": "Impermeabilizantes y Recubrimientos",
    "TOR": "Tornillería, Cintas y Fijación",
}

_CAT_ITEMS = [
    ("US010604", "TABLAROCA ULTRALIGHT 12.7mm x 1.22 US010604", "PAN", "PZA", 206.24, 199.85, 189.00),
    ("US010301", "BASECOAT DUROCK FORTE 20 KG. US010301", "PAS", "PZA", 515.09, 499.64, 489.34),
    ("US010305", "REDIMIX 25 KGS. US010305", "PAS", "PZA", 461.41, 447.57, 438.34),
    ("US010306", "REDIMIX 28 KGS. US010306", "PAS", "PZA", 597.00, 585.06, 573.12),
    ("US010307", "PASTA TABLAROCA 21.8 KG US010307", "PAS", "PZA", 367.00, 363.33, 355.99),
    ("US010605", "TABLAROCA ANTI-MOHO 12.7MM US010605", "PAN", "PZA", 302.00, 292.94, 286.90),
    ("US010601", "TABLAROCA DUROCK ( TABLACEMENTO) US010601", "PAN", "PZA", 874.00, 847.78, 799.00),
    ("US010610-11-12", "TABLAROCA TEXT ASTRAL, POLAR, SOLAR", "PAN", "PZA", 118.12, 114.58, 112.21),
    ("US101131", "PLAFON RADAR LS 0.61x 0.61 ITEM:2220 US101131", "PLA", "CJA", 2280.50, 2212.09, 2166.48),
    ("US101132", "PLAFON RADAR OC 61x 1.22 Item: 2410", "PLA", "CJA", 1893.00, 1836.41, 1798.89),
    ("GN010101", "ANGULO COMERCIAL 3.05 CAL. 26 GN010101", "PCO", "PZA", 21.89, 21.23, 20.58),
    ("GN010102", "CANAL COMERCIAL 4.10x 3.05 CAL. 26 GN010102", "PCO", "PZA", 36.96, 35.85, 34.37),
    ("GN010103", "CANAL COMERCIAL 6.35x 3.05 CAL. 26 GN010103", "PCO", "PZA", 47.57, 46.14, 44.72),
    ("GN010104", "CANAL LISTON COMERCIAL DE 3.05 CAL. 26 GN010104", "PCO", "PZA", 38.14, 37.00, 35.85),
    ("GN010105", "CANALETA DE CARGA COMERCIAL 3.05 CAL. 22 GN010105", "PCO", "PZA", 36.57, 35.47, 34.38),
    ("GN010107", "POSTE COMERCIAL 4.10x 3.05 CAL.26 GN010107", "PCO", "PZA", 47.28, 45.86, 44.44),
    ("GN010109", "POSTE COMERCIAL 6.35x 3.05 CAL. 26 GN010109", "PCO", "PZA", 55.88, 54.20, 52.53),
    ("GN010110", "ESQUINERO COMERCIAL 3.05 CAL. 28 GN010110", "PCO", "PZA", 20.38, 19.97, 19.36),
    ("GN010112", "CANAL COMERCIAL 9.20x 3.05 CAL. 26 GN010112", "PCO", "PZA", 60.18, 58.37, 56.57),
    ("GN010114", "POSTE COMERCIAL 9.20x 3.05 CAL. 26 GN010114", "PCO", "PZA", 70.34, 68.23, 66.12),
    ("GN010116", "POSTE COMERCIAL 6.35x 3.05 CAL.20 GN010116", "PCO", "PZA", 109.41, 106.13, 102.85),
    ("GN010121", "CANAL COMERCIAL 6.35x 3.05 CAL. 22 GN010121", "PCO", "PZA", 84.86, 83.16, 81.47),
    ("GN010123", "CANAL AMARRE COMERCIAL 4.10x 3.05 CAL. 22 GN010123", "PCO", "PZA", 57.83, 56.10, 54.36),
    ("GN010124", "POSTE COMERCIAL 4.10x 3.05 CAL. 20 GN010124", "PCO", "PZA", 92.21, 89.44, 86.68),
    ("GN010126", "CANAL COMERCIAL 9.20x 3.05 CAL. 22 GN010126", "PCO", "PZA", 95.34, 92.48, 89.62),
    ("GN010127", "POSTE COMERCIAL 9.20x 3.05 CAL. 20 GN010127", "PCO", "PZA", 137.71, 133.58, 128.07),
    ("US010201", "ANGULO PERIMETRAL USG 3.05 MTS CAL 26 US010201", "PUS", "PZA", 24.74, 24.00, 23.50),
    ("US010202", "CANAL DE AMARRE USG 4.10x 3.05 CAL. 26 US010202", "PUS", "PZA", 41.05, 40.23, 39.00),
    ("US010203", "CANAL DE AMARRE USG 6.35x 3.05 CAL. 26 US010203", "PUS", "PZA", 49.81, 48.81, 47.32),
    ("US010204", "CANAL GALV. USG 9.20x 3.05 MTS CAL. 26 US010204", "PUS", "PZA", 64.83, 63.53, 61.59),
    ("US010205", "CANAL LISTON USG DE 3.05 CAL. 26 US010205", "PUS", "PZA", 40.61, 39.80, 38.58),
    ("US010206", "CANALETA DE CARGA USG 1.5x 3.05 CAL. 22 US010206", "PUS", "PZA", 45.16, 44.71, 44.26),
    ("US010208", "ESQUINERO METALICO USG 3.05 MTS CAL 28 US010208", "PUS", "PZA", 28.77, 27.91, 27.33),
    ("US010209", "REBORDE TIPO J USG 3.05 MTS CAL 28 US010209", "PUS", "PZA", 31.70, 30.75, 30.12),
    ("US010210", "ANGULO USG DUROCK DE 3.05 CAL. 20 US010210", "PUS", "PZA", 50.20, 48.69, 46.69),
    ("US010211", "CANAL USG DUROCK 4.10x 3.05 CAL.22 US010211", "PUS", "PZA", 70.14, 68.04, 66.63),
    ("US010212", "CANAL USG DUROCK 6.35x 3.05 CAL.22 US010212", "PUS", "PZA", 87.37, 85.62, 83.00),
    ("US010213", "CANAL USG DUROCK 9.20x 3.05 CAL.22 US010213", "PUS", "PZA", 113.10, 109.71, 106.31),
    ("US010214", "CANAL USG DUROCK 1524x 3.05 CAL. 22 US010214", "PUS", "PZA", 168.73, 163.67, 160.29),
    ("US010215", "CANAL LISTON USG DUROCK x 3.05 CAL.20 US010215", "PUS", "PZA", 86.94, 84.33, 82.59),
    ("US010216", "POSTE METALICO USG 4.10x 3.05 CAL. 26 US010216", "PUS", "PZA", 50.61, 49.09, 48.08),
    ("US010218", "POSTE METALICO USG 6.35x 3.05 CAL. 26 US010218", "PUS", "PZA", 61.49, 59.65, 58.42),
    ("US010220", "POSTE METALICO USG 9.20x 3.05 CAL 26 US010220", "PUS", "PZA", 73.22, 71.02, 69.56),
    ("US010222", "POSTE DUROCK USG 4.10x 3.05 CAL. 20 US010222", "PUS", "PZA", 104.17, 101.04, 98.96),
    ("US010223", "POSTE DUROCK USG 6.35x 3.05 CAL.20 US010223", "PUS", "PZA", 126.01, 122.23, 119.71),
    ("US010225", "POSTE DUROCK USG 9.20x 3.05 CAL. 20 US010225", "PUS", "PZA", 152.89, 148.30, 145.25),
    ("US010226", "POSTE DUROCK USG 1524x 305 DE 3.05 CAL. 20 US010226", "PUS", "PZA", 220.23, 213.62, 209.22),
    ("US010100", "ANGULO PERIMETRAL M7 DE 3.66 US010100", "PLA", "PZA", 181.02, 179.21, 175.59),
    ("US010101", "TEE CONECTORA DX-216 DE 0.61 MTS US010101", "PLA", "PZA", 42.23, 41.81, 41.39),
    ("US010102", "TEE CONECTORA DX-416 DE 1.22 MTS US010102", "PLA", "PZA", 82.74, 81.91, 81.09),
    ("US010103", "TEE PRINCIPAL DX-24 DE 3.66 MTS US010103", "PLA", "PZA", 274.96, 272.21, 269.46),
    ("US010310", "YESO SUPREMO 40 KG US010310", "PAS", "PZA", 160.99, 156.16, 152.94),
    ("US010312", "YESO SUPERMOLD 40 KG US010312", "PAS", "PZA", 157.25, 152.53, 149.39),
    ("IP050701-IP050702", "MASTER LASSER 3.0mm F.V. GRAV", "IMP", "PZA", 854.65, 829.01, 811.92),
    ("IP050709-IP050710", "MASTER LASSER 3.5mm F.V. GRAV.", "IMP", "PZA", 953.11, 907.44, 888.73),
    ("IP050712-IP050713", "MASTER LASSER 3.5mm F.P. GRAV", "IMP", "PZA", 1167.21, 1132.19, 1108.85),
    ("IP050715-IP050716", "MASTER LASSER 4.0mm F.P. GRAV", "IMP", "PZA", 1226.10, 1189.20, 1164.70),
    ("IP050718-IP050719", "MASTER LASSER 4.5mm F.P. GRAV", "IMP", "PZA", 1449.23, 1405.03, 1376.89),
    ("IP050704", "MASTER LASSER 3.0mm LISO ARENADO", "IMP", "PZA", 1227.32, 1202.77, 1165.95),
    ("CM010102", "CINTA FV AUTOADHESIVA 10 CM x 45 MTS.", "TOR", "PZA", 78.46, 65.00, 63.75),
    ("CM010106", "PERFACINTA IMAC 5cm x 75m.", "TOR", "PZA", 65.00, 59.20, 59.20),
    ("CV011009", "MULTICOLOR NG BASE NL CUBETA", "IMP", "PZA", 1599.00, 1590.50, 1585.58),
    ("IMA020101", "TORNILLO IMAC TIPO S DE 1\" (100 PZAS)", "TOR", "PZA", 16.00, 15.95, 15.95),
    ("IMA020102", "TORNILLO IMAC TIPO DS 1-1/4\" (100 PZAS)", "TOR", "PZA", 51.68, 51.68, 51.68),
    ("IMA020103", "TORNILLO IMAC TEK PLANO 1/2\" (100 PZAS)", "TOR", "PZA", 27.00, 26.40, 26.40),
    ("IMA020105", "TORNILLO IMAC P/TAQUETE 1 1/2\" (100 PZAS)", "TOR", "PZA", 36.26, 36.26, 36.26),
    ("IMA020106", "TORNILLO IMAC FRAMER AB7x7/16 (100 PZAS)", "TOR", "PZA", 18.96, 18.96, 18.96),
    ("IMA020109", "TORNILLO IMAC TEK BROCA 1\" (100 PZAS)", "TOR", "PZA", 21.33, 21.33, 21.33),
    ("IMA020110", "TORNILLO IMAC TEK BROCA 1 5/8\" (100 PZAS)", "TOR", "PZA", 21.40, 21.40, 21.40),
    ("IMA020201", "CINTA DE PAPEL C/ALUMINIO 50mm x 30m", "TOR", "PZA", 216.00, 216.00, 216.00),
    ("IMA030101", "IMPER IMAC 5 AÑOS FIBRATADO BLANCO", "IMP", "PZA", 853.44, 844.82, 844.82),
    ("IMA030102", "IMPER IMAC 5 AÑOS FIBRATADO ROJO", "IMP", "PZA", 853.44, 844.82, 844.82),
    ("IMA040202", "TAQUETE IMAC PLASTICO GRIS 1/4 (100 PZAS)", "TOR", "PZA", 32.00, 32.00, 32.00),
    ("IP050102", "MASTER PRIM \"A\" CUB. 19 LTS.", "IMP", "PZA", 800.00, 800.00, 800.00),
]

CATALOGO_LIGEROS = {
    clv: {"producto": prod, "categoria": _CATS[cat], "unidad": und, "n1": n1, "n2": n2, "n3": n3}
    for clv, prod, cat, und, n1, n2, n3 in _CAT_ITEMS
}

# --- MAPA EXACTO DE FICHAS TÉCNICAS (42 SKUs -> 14 ARCHIVOS ÚNICOS) ---
_FICHAS_GRUPOS = {
    "ultraligh_fichatecnica": ["US010604"],
    "basecoat_fichatecnica": ["US010301"],
    "redimix_fichatecnica": ["US010305", "US010306", "US010307"],
    "antimoho_fichastecnicas": ["US010605"],
    "durock_fichatecnica": ["US010601"],
    "texturizado_fichatecnicausg": ["US010610-11-12"],
    "radar_fichatecnica": ["US101131", "US101132"],
    "metalesusg_fichatecnica": [
        # "US010201", "US010202", "US010203", "US010204",  # Descomentar si también llevan ficha
        "US010205", "US010206", "US010208", "US010209", "US010210", "US010211",
        "US010212", "US010213", "US010214", "US010215", "US010216", "US010218",
        "US010220", "US010222", "US010223", "US010225", "US010226", "US010100",
    ],
    "suspensiondx_fichatecnica": ["US010101", "US010102", "US010103"],
    "yesosupremo_fichatecnica": ["US010310"],
    "yesosupermold_fichatecnica": ["US010312"],
    "masster_fichatecnica": [
        "IP050701-IP050702", "IP050709-IP050710", "IP050712-IP050713",
        "IP050715-IP050716", "IP050718-IP050719", "IP050704",
    ],
    "imperimac_fichatecnica": ["IMA030101", "IMA030102"],
    "masterprima_fichatecnica": ["IP050102"],
}
FICHAS_TECNICAS_MAP = {sku: ficha for ficha, skus in _FICHAS_GRUPOS.items() for sku in skus}

# --- NORMALIZACIÓN Y UTILIDADES ---
def normalizar_texto(texto):
    s = str(texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def resolver_sucursal_clave(sucursal_raw):
    obj = normalizar_texto(sucursal_raw)
    if not obj:
        return "IMAC"
    if any(p in obj for p in ["todas", "all", "general"]):
        return "TODAS"
    if any(p in obj for p in ["imacril", "centro", "5 de mayo"]):
        return "IMACRIL CENTRO"
    if any(p in obj for p in ["riviera", "playa dorada", "alvarado"]):
        return "RIVIERA"
    if any(p in obj for p in ["ejercito", "ylang"]):
        return "EJÉRCITO"
    if any(p in obj for p in ["boca", "306"]):
        return "BOCA DEL RÍO"
    if any(p in obj for p in ["framboyan", "tejeria", "bruno", "clouthier"]):
        return "FRAMBOYANES"
    if any(p in obj for p in ["imac", "matriz", "759"]):
        return "IMAC"
    return "IMAC"

def extraer_campo_flexible(fila_norm, posibles_claves, default=""):
    for k in posibles_claves:
        if k in fila_norm and fila_norm[k]:
            return fila_norm[k]
    for k_real, val in fila_norm.items():
        if val and any(p in k_real for p in posibles_claves):
            return val
    return default

def buscar_imagen(nombres_posibles):
    for nombre in nombres_posibles:
        if os.path.exists(nombre):
            return nombre
    return None

# --- MOTOR DE FICHAS TÉCNICAS (DEDUPLICACIÓN + FUSIÓN PDF/IMAGEN) ---
def buscar_archivo_ficha(nombre_base):
    base_clean = str(nombre_base or "").strip()
    if not base_clean:
        return None
    objetivo_lower = base_clean.lower()
    exts_validas = (".pdf", ".png", ".jpg", ".jpeg")

    for carpeta in (CARPETA_FICHAS, "."):
        if not os.path.isdir(carpeta):
            continue
        for ext in ("", ".pdf", ".PDF", ".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"):
            cand = os.path.join(carpeta, base_clean + ext) if carpeta != "." else (base_clean + ext)
            if os.path.isfile(cand):
                return cand
        try:
            for archivo in os.listdir(carpeta):
                ruta = os.path.join(carpeta, archivo) if carpeta != "." else archivo
                if not os.path.isfile(ruta):
                    continue
                stem, ext = os.path.splitext(archivo)
                if archivo.lower() == objetivo_lower or (stem.lower() == objetivo_lower and ext.lower() in exts_validas):
                    return ruta
        except Exception:
            continue
    return None

def obtener_fichas_unicas_carrito(carrito):
    fichas_unicas, vistas = [], set()
    for item in carrito:
        ficha_base = FICHAS_TECNICAS_MAP.get(str(item.get("clave", "")).strip())
        if not ficha_base:
            continue
        ficha_key = ficha_base.strip().lower()
        if ficha_key not in vistas:
            vistas.add(ficha_key)
            fichas_unicas.append(ficha_base.strip())
    return fichas_unicas

def convertir_imagen_a_pdf_bytes(ruta_img):
    from PIL import Image
    w_px, h_px = Image.open(ruta_img).size
    pdf_img = FPDF(unit="mm", format="A4")
    pdf_img.add_page()
    escala = min(190.0 / float(w_px), 277.0 / float(h_px))
    w_mm, h_mm = w_px * escala, h_px * escala
    pdf_img.image(ruta_img, x=(210.0 - w_mm) / 2.0, y=(297.0 - h_mm) / 2.0, w=w_mm, h=h_mm)
    return pdf_img.output(dest="S").encode("latin-1")

def anexar_fichas_a_pdf(pdf_base_bytes, carrito):
    if not PYPDF_OK:
        return pdf_base_bytes
    fichas_unicas = obtener_fichas_unicas_carrito(carrito)
    if not fichas_unicas:
        return pdf_base_bytes

    rutas = []
    for ficha_base in fichas_unicas:
        ruta = buscar_archivo_ficha(ficha_base)
        if ruta and ruta not in rutas:
            rutas.append(ruta)
    if not rutas:
        return pdf_base_bytes

    try:
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(pdf_base_bytes)).pages:
            writer.add_page(page)
        for ruta in rutas:
            try:
                ext = os.path.splitext(ruta)[1].lower()
                if ext == ".pdf":
                    for page in PdfReader(ruta).pages:
                        writer.add_page(page)
                elif ext in (".png", ".jpg", ".jpeg"):
                    for page in PdfReader(io.BytesIO(convertir_imagen_a_pdf_bytes(ruta))).pages:
                        writer.add_page(page)
            except Exception:
                continue
        salida = io.BytesIO()
        writer.write(salida)
        return salida.getvalue()
    except Exception:
        return pdf_base_bytes

# --- CONEXIÓN GOOGLE SHEETS, FOLIOS CORTOS Y CORREO ---
def obtener_secreto(clave):
    valor = os.environ.get(clave)
    if valor:
        return valor
    try:
        return st.secrets[clave]
    except Exception:
        return None

@st.cache_resource
def conectar_sheets_con_estado():
    try:
        credenciales_raw = obtener_secreto("GOOGLE_CREDENTIALS")
        id_excel = obtener_secreto("ID_EXCEL")
        if not credenciales_raw or not id_excel:
            return None, "Faltan variables GOOGLE_CREDENTIALS o ID_EXCEL en Streamlit Secrets."
        credenciales_dic = json.loads(credenciales_raw) if isinstance(credenciales_raw, str) else dict(credenciales_raw)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(credenciales_dic, scopes=scopes)
        return gspread.authorize(creds).open_by_key(id_excel), "OK"
    except Exception as e:
        return None, str(e)

def conectar_sheets():
    doc, _ = conectar_sheets_con_estado()
    return doc

def registrar_bitacora(doc, modulo, accion):
    try:
        if doc:
            doc.worksheet("Bitacora_Movimientos").append_row([
                ahora_mx().strftime("%d/%m/%Y %H:%M:%S"),
                st.session_state.get("usuario", "Sistema"),
                st.session_state.get("role", "Desconocido"),
                modulo,
                accion
            ])
    except Exception:
        pass

def obtener_nuevo_folio(doc, prefijo):
    """Genera folio corto independiente por sucursal (ej. IVR-0001) sin duplicados."""
    prefijo_clean = str(prefijo or "IVR").strip().upper()
    patron = re.compile(rf"^{re.escape(prefijo_clean)}-(\d+)$", re.IGNORECASE)
    max_num = 0
    try:
        if doc:
            for val in doc.worksheet("Cotizaciones").col_values(1):
                m = patron.match(str(val or "").strip())
                if m:
                    max_num = max(max_num, int(m.group(1)))
            return f"{prefijo_clean}-{max_num + 1:04d}"
    except Exception:
        pass
    return f"{prefijo_clean}-{ahora_mx().strftime('%H%M')}"

def limpiar_monto(valor):
    if valor is None or str(valor).strip() == "":
        return 0.0
    try:
        return float(str(valor).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0

def actualizar_fila_cotizacion(hoja, folio_objetivo, fila_idx_sugerida, valores_fila):
    fila_real = fila_idx_sugerida
    try:
        if str(hoja.cell(fila_real, 1).value or "").strip() != str(folio_objetivo).strip():
            col_folios = hoja.col_values(1)
            fila_real = next((i + 1 for i, v in enumerate(col_folios) if str(v).strip() == str(folio_objetivo).strip()), None)
    except Exception:
        col_folios = hoja.col_values(1)
        fila_real = next((i + 1 for i, v in enumerate(col_folios) if str(v).strip() == str(folio_objetivo).strip()), None)
    if not fila_real:
        return False, "No se encontró el folio en la pestaña Cotizaciones."

    rango = f"A{fila_real}:M{fila_real}"
    try:
        hoja.update(values=[valores_fila], range_name=rango)
    except TypeError:
        hoja.update(rango, [valores_fila])
    return True, f"Fila {fila_real} actualizada."

def enviar_respaldo_correo(pdf_bytes, nombre_archivo, folio, sucursal_nombre, cliente, asesor, total_mxn, correo_dest, es_edicion=False):
    try:
        remitente = obtener_secreto("CORREO_BOT")
        password = obtener_secreto("PASS_BOT")
        if not remitente or not password:
            return False, "Faltan CORREO_BOT o PASS_BOT en Secrets."

        prefijo = "ACTUALIZACION COTIZACION" if es_edicion else "COTIZACION MOSTRADOR"
        msg = EmailMessage()
        msg["Subject"] = f"{prefijo} {folio} | {sucursal_nombre} - {cliente}"
        msg["From"] = remitente
        msg["To"] = correo_dest
        msg.set_content(
            f"Se ha {'actualizado' if es_edicion else 'generado'} una cotización de Sistemas Ligeros.\n\n"
            f"Folio: {folio}\nSucursal: {sucursal_nombre}\nAsesor: {asesor}\n"
            f"Cliente: {cliente}\nTotal: ${total_mxn:,.2f} MXN\n\nSe adjunta el PDF oficial."
        )
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=nombre_archivo)
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(remitente, password)
            smtp.send_message(msg)
        return True, "OK"
    except Exception as e:
        return False, str(e)

# --- CÁLCULOS DE PRECIOS Y TOTALES (CUADRE EXACTO AL CENTAVO CON MONTO DE DESCUENTO) ---
def calcular_nivel_y_precio(clave, cantidad, precio_fallback=0.0):
    if clave in CATALOGO_LIGEROS:
        item = CATALOGO_LIGEROS[clave]
        if cantidad >= MIN_PZAS_NIVEL_3:
            return "NIVEL 3", item["n3"], item["n1"]
        elif cantidad >= MIN_PZAS_NIVEL_2:
            return "NIVEL 2", item["n2"], item["n1"]
        return "NIVEL 1", item["n1"], item["n1"]
    return "NIVEL 1", float(precio_fallback), float(precio_fallback)

def calcular_totales_carrito(carrito, flete, desc_extra_pct, precios_incluyen_iva):
    subtotal_bruto = 0.0
    total_desc_partidas = 0.0
    ahorro_nivel = 0.0
    desc_global_seguro = min(max(0.0, float(desc_extra_pct)), MAX_DESC_PCT)
    partidas_netas = []

    for x in carrito:
        cant = float(x["cantidad"])
        pu_base = round(float(x["precio_unit"]), 2)
        imp_bruto = round(cant * pu_base, 2)

        desc_p = min(max(0.0, float(x.get("desc_pct", 0.0))), MAX_DESC_PCT) if x.get("nivel") == "NIVEL 1" else 0.0
        desc_n1_m = round(imp_bruto * (desc_p / 100.0), 2)
        pu_neto = round(pu_base * (1.0 - desc_p / 100.0) * (1.0 - desc_global_seguro / 100.0), 2)
        imp_neto = round(imp_bruto - desc_n1_m, 2)

        subtotal_bruto += imp_bruto
        total_desc_partidas += desc_n1_m
        ahorro_nivel += max(0.0, (float(x.get("precio_lista", pu_base)) - pu_base) * cant)

        partidas_netas.append({
            "clave": str(x["clave"]),
            "producto": str(x["producto"]),
            "cantidad": cant,
            "pu_base": pu_base,
            "imp_bruto": imp_bruto,
            "pu_neto": pu_neto,
            "imp_neto": imp_neto
        })

    subtotal_bruto = round(subtotal_bruto, 2)
    total_desc_partidas = round(total_desc_partidas, 2)
    subtotal_post_n1 = round(subtotal_bruto - total_desc_partidas, 2)
    desc_global_monto = round(subtotal_post_n1 * (desc_global_seguro / 100.0), 2)
    descuento_total = round(total_desc_partidas + desc_global_monto, 2)
    base_neta = round(subtotal_bruto - descuento_total + float(flete), 2)

    if precios_incluyen_iva:
        total_final = base_neta
        subtotal_sin_iva = round(total_final / 1.16, 2)
        iva_monto = round(total_final - subtotal_sin_iva, 2)
    else:
        subtotal_sin_iva = base_neta
        iva_monto = round(subtotal_sin_iva * 0.16, 2)
        total_final = round(subtotal_sin_iva + iva_monto, 2)

    return {
        "subtotal_bruto": subtotal_bruto,
        "total_desc_partidas": total_desc_partidas,
        "desc_global_monto": desc_global_monto,
        "descuento_total": descuento_total,
        "ahorro_nivel": round(ahorro_nivel, 2),
        "subtotal_sin_iva": subtotal_sin_iva,
        "iva_monto": iva_monto,
        "total_final": total_final,
        "partidas_netas": partidas_netas
    }

def limpiar_pdf_txt(texto):
    return str(texto).encode("latin-1", "replace").decode("latin-1")

# --- GENERADOR PDF CORPORATIVO (SIN % NI N1/N2/N3; CON MONTO DE DESCUENTO Y FICHAS ANEXAS) ---
class PDFCorporativoIMAC(FPDF):
    def __init__(self, suc_info, folio_txt, fecha_hora_txt):
        super().__init__()
        self.suc_info = suc_info
        self.folio_txt = folio_txt
        self.fecha_hora_txt = fecha_hora_txt

    def header(self):
        self.set_fill_color(15, 60, 140)
        self.rect(0, 0, 210, 3, "F")

        img_imac = buscar_imagen(["logo_imac_2026.png", "logo_imac_2026.jpg", "logo_imac.png"])
        if img_imac:
            self.image(img_imac, x=10, y=6, w=20, h=20)

        img_ml = buscar_imagen(["logo_master_lasser.png", "logo_master_lasser.jpg", "logo_master_lasser.jpeg"])
        if img_ml:
            self.image(img_ml, x=152, y=10.5, w=48)

        self.set_xy(33, 8)
        self.set_font("Arial", "B", 13)
        self.set_text_color(15, 60, 140)
        self.cell(116, 6, limpiar_pdf_txt(self.suc_info["razon_social"]), ln=True, align="C")

        self.set_x(33)
        self.set_font("Arial", "B", 8.5)
        self.set_text_color(0, 140, 230)
        self.cell(116, 4.8, limpiar_pdf_txt(self.suc_info["sucursal_corta"].upper()), ln=True, align="C")

        self.set_x(33)
        self.set_font("Arial", "", 7.5)
        self.set_text_color(95, 95, 95)
        self.cell(116, 4.2, "COTIZACION DE MATERIALES | SISTEMAS LIGEROS", ln=True, align="C")

        self.set_xy(10, 28.5)
        self.set_font("Arial", "B", 9)
        self.set_text_color(200, 30, 30)
        self.cell(95, 5, limpiar_pdf_txt(f"FOLIO: {self.folio_txt}"), ln=False, align="L")

        self.set_font("Arial", "B", 8.5)
        self.set_text_color(60, 60, 60)
        self.cell(95, 5, limpiar_pdf_txt(f"Fecha y Hora: {self.fecha_hora_txt}"), ln=True, align="R")

        self.set_draw_color(200, 212, 230)
        self.line(10, 35, 200, 35)
        self.set_y(38)

    def footer(self):
        img_footer = buscar_imagen(["footer_marcas.png", "footer_marcas.jpg", "footer_marcas.jpeg"])
        if img_footer:
            self.image(img_footer, x=10, y=250, w=190)
            self.set_xy(10, 292.2)
            self.set_font("Arial", "I", 6.8)
            self.set_text_color(130, 130, 130)
            self.cell(
                190, 3.5,
                limpiar_pdf_txt(f"{self.suc_info['razon_social']} - {self.suc_info['sucursal_corta']} | Pagina {self.page_no()}"),
                align="R"
            )
        else:
            self.set_y(-19)
            self.set_draw_color(215, 222, 232)
            self.line(10, 277, 200, 277)
            self.set_font("Arial", "B", 7.2)
            self.set_text_color(15, 60, 140)
            self.cell(0, 4, "Conoce nuestras lineas de productos: USG  |  IMPAC  |  Sika  |  Master Lasser  |  RETEX  |  OWENS CORNING  |  COREV", ln=True, align="C")
            self.set_font("Arial", "I", 7)
            self.set_text_color(110, 110, 110)
            self.cell(
                0, 4,
                limpiar_pdf_txt(f"www.grupo-imac.com  |  FB: Grupo Imac  |  IG: grupo_imac  |  {self.suc_info['sucursal_corta']} - Pagina {self.page_no()}"),
                align="C"
            )

def generar_pdf_mostrador(
    folio,
    sucursal_nombre,
    suc_info,
    cliente,
    telefono_cli,
    correo_cli,
    asesor_nombre,
    asesor_telefono,
    asesor_correo,
    validez,
    carrito,
    flete,
    desc_extra_pct,
    precios_incluyen_iva,
    notas,
    mostrar_col_desc=False,
    incluir_fichas=True
):
    fecha_hora = ahora_mx().strftime("%d/%m/%Y %H:%M hrs")
    pdf = PDFCorporativoIMAC(suc_info, folio, fecha_hora)
    pdf.set_auto_page_break(auto=True, margin=52)
    pdf.add_page()

    tot = calcular_totales_carrito(carrito, flete, desc_extra_pct, precios_incluyen_iva)

    # --- TARJETA DEL CLIENTE ---
    y_att = pdf.get_y()
    pdf.set_fill_color(245, 247, 250)
    pdf.rect(10, y_att, 190, 19.5, "F")
    pdf.set_fill_color(15, 60, 140)
    pdf.rect(10, y_att, 2.5, 19.5, "F")

    pdf.set_xy(15, y_att + 2.8)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(15, 60, 140)
    pdf.cell(26, 4.8, "En atencion a:", ln=False)
    pdf.set_font("Arial", "B", 9.5)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(154, 4.8, limpiar_pdf_txt(cliente.upper() if cliente else "MOSTRADOR / PUBLICO EN GENERAL"), ln=True)

    pdf.set_x(15)
    pdf.set_font("Arial", "", 7.8)
    pdf.set_text_color(80, 80, 80)
    det_cli = f"Tel: {telefono_cli if telefono_cli else 'N/A'}   |   Correo: {correo_cli if correo_cli else 'N/A'}   |   Vigencia: {validez.strftime('%d/%m/%Y')}   |   Moneda: MXN"
    pdf.cell(180, 4.6, limpiar_pdf_txt(det_cli), ln=True)

    pdf.set_x(15)
    pdf.set_font("Arial", "B", 7.6)
    pdf.set_text_color(0, 130, 215)
    pdf.cell(180, 4.4, limpiar_pdf_txt(f"Atendido por: {asesor_nombre} ({suc_info['sucursal_corta']})"), ln=True)
    pdf.set_y(y_att + 23.5)

    # --- TABLA DE PARTIDAS (6 COLUMNAS, 190 mm, SIN % NI NIVELES) ---
    def dibujar_encabezado_tabla():
        pdf.set_fill_color(15, 60, 140)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 8)
        pdf.cell(16, 7.2, "CANT.", 0, 0, "C", True)
        pdf.cell(14, 7.2, "UNID.", 0, 0, "C", True)
        pdf.cell(27, 7.2, "CLAVE", 0, 0, "C", True)
        pdf.cell(83, 7.2, "DESCRIPCION", 0, 0, "L", True)
        pdf.cell(25, 7.2, "P. UNITARIO", 0, 0, "R", True)
        pdf.cell(25, 7.2, "IMPORTE", 0, 1, "R", True)

    dibujar_encabezado_tabla()

    for idx, row in enumerate(tot["partidas_netas"]):
        if pdf.get_y() > 236:
            pdf.add_page()
            dibujar_encabezado_tabla()

        fill = (idx % 2 == 1)
        pdf.set_fill_color(246, 249, 253)
        pdf.set_draw_color(222, 228, 238)
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Arial", "", 7.6)

        clave_r = row["clave"]
        unidad_r = CATALOGO_LIGEROS.get(clave_r, {}).get("unidad", "PZA")
        pdf.cell(16, 6.5, f"{row['cantidad']:g}", "B", 0, "C", fill)
        pdf.cell(14, 6.5, unidad_r, "B", 0, "C", fill)
        pdf.cell(27, 6.5, limpiar_pdf_txt(clave_r[:15]), "B", 0, "C", fill)
        pdf.cell(83, 6.5, limpiar_pdf_txt(row["producto"][:49]), "B", 0, "L", fill)
        pdf.cell(25, 6.5, f"${row['pu_base']:,.2f}", "B", 0, "R", fill)
        pdf.cell(25, 6.5, f"${row['imp_bruto']:,.2f}", "B", 1, "R", fill)

    # --- CONDICIONES (IZQUIERDA) + SUMATORIA CON DESCUENTO EN PESOS (DERECHA) ---
    if pdf.get_y() > 162:
        pdf.add_page()

    pdf.ln(5)
    y_resumen = pdf.get_y()

    pdf.set_xy(10, y_resumen)
    pdf.set_font("Arial", "B", 8.2)
    pdf.set_text_color(15, 60, 140)
    pdf.cell(106, 4.8, "Observaciones y Condiciones:", ln=True)

    pdf.set_x(10)
    pdf.set_font("Arial", "", 7.6)
    pdf.set_text_color(60, 60, 60)
    lineas_leyenda = []
    if notas.strip():
        lineas_leyenda.append(f"Nota: {notas.strip()}")
    lineas_leyenda.append(f"- {suc_info['leyenda_entrega']}")
    lineas_leyenda.append("- Precios + 16% de IVA" if not precios_incluyen_iva else "- Precios incluyen 16% de IVA")
    lineas_leyenda.append(f"- Precios validos al {validez.strftime('%d/%m/%Y')}")
    if suc_info.get("leyenda_extra"):
        lineas_leyenda.append(f"- {suc_info['leyenda_extra']}")
    lineas_leyenda.append("- Cotizacion sujeta a cambios sin previo aviso")
    pdf.multi_cell(106, 4.0, limpiar_pdf_txt("\n".join(lineas_leyenda)))
    y_fin_izq = pdf.get_y()

    pdf.set_xy(122, y_resumen)
    pdf.set_font("Arial", "B", 8.6)
    pdf.set_text_color(55, 55, 55)

    if tot["descuento_total"] > 0:
        pdf.set_x(122)
        pdf.cell(40, 5.4, "IMPORTE:", 0, 0, "R")
        pdf.cell(38, 5.4, f"${tot['subtotal_bruto']:,.2f}", 0, 1, "R")

        pdf.set_x(122)
        pdf.set_text_color(200, 30, 30)
        pdf.cell(40, 5.4, "DESCUENTO:", 0, 0, "R")
        pdf.cell(38, 5.4, f"-${tot['descuento_total']:,.2f}", 0, 1, "R")
        pdf.set_text_color(55, 55, 55)

    if float(flete) > 0:
        pdf.set_x(122)
        pdf.cell(40, 5.4, "FLETE / ENVIO:", 0, 0, "R")
        pdf.cell(38, 5.4, f"${float(flete):,.2f}", 0, 1, "R")

    pdf.set_x(122)
    pdf.cell(40, 5.6, "SUB TOTAL:", 0, 0, "R")
    pdf.cell(38, 5.6, f"${tot['subtotal_sin_iva']:,.2f}", 0, 1, "R")

    pdf.set_x(122)
    pdf.cell(40, 5.6, "IVA (16%):", 0, 0, "R")
    pdf.cell(38, 5.6, f"${tot['iva_monto']:,.2f}", 0, 1, "R")

    pdf.ln(1.5)
    y_tot_bar = pdf.get_y()
    pdf.set_xy(122, y_tot_bar)
    pdf.set_fill_color(15, 60, 140)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(32, 8.5, "TOTAL", 0, 0, "R", True)
    pdf.set_fill_color(0, 150, 255)
    pdf.cell(46, 8.5, f"${tot['total_final']:,.2f} MXN", 0, 1, "C", True)
    y_fin_der = pdf.get_y()

    # --- CIERRE: FIRMA ASESOR (IZQ) + TARJETA BBVA (DER) ---
    y_cierre = max(y_fin_izq, y_fin_der) + 7
    if y_cierre > 205:
        pdf.add_page()
        y_cierre = pdf.get_y() + 2

    pdf.set_xy(10, y_cierre)
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(70, 70, 70)
    pdf.cell(98, 4.4, "Quedamos a sus ordenes para cualquier duda o aclaracion.", ln=True)
    pdf.set_x(10)
    pdf.cell(98, 4.4, "Cordialmente,", ln=True)
    pdf.ln(1.8)

    pdf.set_x(10)
    pdf.set_font("Arial", "B", 9.5)
    pdf.set_text_color(15, 60, 140)
    pdf.cell(98, 4.8, limpiar_pdf_txt(asesor_nombre), ln=True)

    pdf.set_x(10)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(0, 140, 230)
    pdf.cell(98, 4.2, limpiar_pdf_txt(suc_info["sucursal_corta"]), ln=True)

    pdf.set_x(10)
    pdf.set_font("Arial", "", 7.5)
    pdf.set_text_color(75, 75, 75)
    tel_mostrar = asesor_telefono.strip() if asesor_telefono.strip() else suc_info["telefono"]
    correo_mostrar = asesor_correo.strip() if asesor_correo.strip() else suc_info["correo"]
    info_contacto = (
        f"{suc_info['direccion']}\n"
        f"Tel. Sucursal: {suc_info['telefono']}"
        + (f"  |  Cel. Asesor: {tel_mostrar}" if asesor_telefono.strip() and asesor_telefono.strip() != suc_info["telefono"] else "")
        + f"\nCorreo: {correo_mostrar}"
    )
    pdf.multi_cell(98, 3.8, limpiar_pdf_txt(info_contacto))

    pdf.set_fill_color(245, 248, 253)
    pdf.set_draw_color(218, 226, 238)
    pdf.rect(112, y_cierre, 88, 38, "DF")
    pdf.set_fill_color(15, 60, 140)
    pdf.rect(112, y_cierre, 2.5, 38, "F")

    img_bbva = buscar_imagen(["logo_bbva.png", "logo_bbva.jpg", "logo_bbva.jpeg"])
    if img_bbva:
        pdf.image(img_bbva, x=117.5, y=y_cierre + 3.5, w=24)
        y_txt_bank = y_cierre + 13.0
    else:
        pdf.set_xy(117.5, y_cierre + 3.5)
        pdf.set_font("Arial", "B", 11)
        pdf.set_text_color(15, 60, 140)
        pdf.cell(80, 6, limpiar_pdf_txt(suc_info["banco"]), ln=True)
        y_txt_bank = y_cierre + 11.5

    pdf.set_xy(117.5, y_txt_bank)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(35, 35, 35)
    pdf.cell(80, 4.6, limpiar_pdf_txt(suc_info["razon_social"]), ln=True)

    pdf.set_x(117.5)
    pdf.set_font("Arial", "", 8)
    pdf.set_text_color(55, 55, 55)
    bloque_banco = f"Cuenta: {suc_info['cuenta']}\nCLABE: {suc_info['clabe']}\nRFC: {suc_info['rfc']}"
    pdf.multi_cell(80, 4.8, limpiar_pdf_txt(bloque_banco))

    pdf_final_bytes = pdf.output(dest="S").encode("latin-1")
    if incluir_fichas:
        pdf_final_bytes = anexar_fichas_a_pdf(pdf_final_bytes, carrito)

    return (
        pdf_final_bytes,
        tot["total_final"],
        tot["subtotal_sin_iva"],
        tot["iva_monto"],
        tot["ahorro_nivel"],
        tot["total_desc_partidas"]
    )
