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
CARPETA_FICHAS = "fichas_tecnicas"  # Carpeta recomendada en GitHub (también busca en la raíz como respaldo)

# --- ZONA HORARIA LOCAL (VERACRUZ / MÉXICO CENTRO) ---
def ahora_mx():
    """Devuelve fecha y hora local de Veracruz/México (corrige el desfase +6h UTC de Streamlit Cloud)."""
    try:
        return datetime.datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-6)))

# --- PERFILES FISCALES Y BANCARIOS REALES DE LAS 6 SUCURSALES DE VERACRUZ ---
# 3 Razones Sociales independientes:
# - IMAC DE VERACRUZ S.A. DE C.V. (1 sucursal: IMAC Matriz)
# - IMACRIL S.A. DE C.V. (1 sucursal: IMACRIL CENTRO)
# - TARC S.A. DE C.V. (4 sucursales: EJÉRCITO, BOCA DEL RÍO, FRAMBOYANES, RIVIERA)
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

# --- CATÁLOGO AUDITADO: 74 PRODUCTOS MXN (PUNTO DECIMAL + ANOMALÍAS CORREGIDAS) ---
CATALOGO_LIGEROS = {
    "US010604": {"producto": "TABLAROCA ULTRALIGHT 12.7mm x 1.22 US010604", "categoria": "Paneles (Tablaroca / Durock)", "unidad": "PZA", "n1": 206.24, "n2": 199.85, "n3": 189.00},
    "US010301": {"producto": "BASECOAT DUROCK FORTE 20 KG. US010301", "categoria": "Pastas, Basecoat y Yesos", "unidad": "PZA", "n1": 515.09, "n2": 499.64, "n3": 489.34},
    "US010305": {"producto": "REDIMIX 25 KGS. US010305", "categoria": "Pastas, Basecoat y Yesos", "unidad": "PZA", "n1": 461.41, "n2": 447.57, "n3": 438.34},
    "US010306": {"producto": "REDIMIX 28 KGS. US010306", "categoria": "Pastas, Basecoat y Yesos", "unidad": "PZA", "n1": 597.00, "n2": 585.06, "n3": 573.12},
    "US010307": {"producto": "PASTA TABLAROCA 21.8 KG US010307", "categoria": "Pastas, Basecoat y Yesos", "unidad": "PZA", "n1": 367.00, "n2": 363.33, "n3": 355.99},
    "US010605": {"producto": "TABLAROCA ANTI-MOHO 12.7MM US010605", "categoria": "Paneles (Tablaroca / Durock)", "unidad": "PZA", "n1": 302.00, "n2": 292.94, "n3": 286.90},
    "US010601": {"producto": "TABLAROCA DUROCK ( TABLACEMENTO) US010601", "categoria": "Paneles (Tablaroca / Durock)", "unidad": "PZA", "n1": 874.00, "n2": 847.78, "n3": 799.00},
    "US010610-11-12": {"producto": "TABLAROCA TEXT ASTRAL, POLAR, SOLAR", "categoria": "Paneles (Tablaroca / Durock)", "unidad": "PZA", "n1": 118.12, "n2": 114.58, "n3": 112.21},
    "US101131": {"producto": "PLAFON RADAR LS 0.61x 0.61 ITEM:2220 US101131", "categoria": "Plafones y Suspensión", "unidad": "CJA", "n1": 2280.50, "n2": 2212.09, "n3": 2166.48},
    "US101132": {"producto": "PLAFON RADAR OC 61x 1.22 Item: 2410", "categoria": "Plafones y Suspensión", "unidad": "CJA", "n1": 1893.00, "n2": 1836.41, "n3": 1798.89},
    "GN010101": {"producto": "ANGULO COMERCIAL 3.05 CAL. 26 GN010101", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 21.89, "n2": 21.23, "n3": 20.58},
    "GN010102": {"producto": "CANAL COMERCIAL 4.10x 3.05 CAL. 26 GN010102", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 36.96, "n2": 35.85, "n3": 34.37},
    "GN010103": {"producto": "CANAL COMERCIAL 6.35x 3.05 CAL. 26 GN010103", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 47.57, "n2": 46.14, "n3": 44.72},
    "GN010104": {"producto": "CANAL LISTON COMERCIAL DE 3.05 CAL. 26 GN010104", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 38.14, "n2": 37.00, "n3": 35.85},
    "GN010105": {"producto": "CANALETA DE CARGA COMERCIAL 3.05 CAL. 22 GN010105", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 36.57, "n2": 35.47, "n3": 34.38},
    "GN010107": {"producto": "POSTE COMERCIAL 4.10x 3.05 CAL.26 GN010107", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 47.28, "n2": 45.86, "n3": 44.44},
    "GN010109": {"producto": "POSTE COMERCIAL 6.35x 3.05 CAL. 26 GN010109", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 55.88, "n2": 54.20, "n3": 52.53},
    "GN010110": {"producto": "ESQUINERO COMERCIAL 3.05 CAL. 28 GN010110", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 20.38, "n2": 19.97, "n3": 19.36},
    "GN010112": {"producto": "CANAL COMERCIAL 9.20x 3.05 CAL. 26 GN010112", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 60.18, "n2": 58.37, "n3": 56.57},
    "GN010114": {"producto": "POSTE COMERCIAL 9.20x 3.05 CAL. 26 GN010114", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 70.34, "n2": 68.23, "n3": 66.12},
    "GN010116": {"producto": "POSTE COMERCIAL 6.35x 3.05 CAL.20 GN010116", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 109.41, "n2": 106.13, "n3": 102.85},
    "GN010121": {"producto": "CANAL COMERCIAL 6.35x 3.05 CAL. 22 GN010121", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 84.86, "n2": 83.16, "n3": 81.47},
    "GN010123": {"producto": "CANAL AMARRE COMERCIAL 4.10x 3.05 CAL. 22 GN010123", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 57.83, "n2": 56.10, "n3": 54.36},
    "GN010124": {"producto": "POSTE COMERCIAL 4.10x 3.05 CAL. 20 GN010124", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 92.21, "n2": 89.44, "n3": 86.68},
    "GN010126": {"producto": "CANAL COMERCIAL 9.20x 3.05 CAL. 22 GN010126", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 95.34, "n2": 92.48, "n3": 89.62},
    "GN010127": {"producto": "POSTE COMERCIAL 9.20x 3.05 CAL. 20 GN010127", "categoria": "Perfiles Comerciales", "unidad": "PZA", "n1": 137.71, "n2": 133.58, "n3": 128.07},
    "US010201": {"producto": "ANGULO PERIMETRAL USG 3.05 MTS CAL 26 US010201", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 24.74, "n2": 24.00, "n3": 23.50},
    "US010202": {"producto": "CANAL DE AMARRE USG 4.10x 3.05 CAL. 26 US010202", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 41.05, "n2": 40.23, "n3": 39.00},
    "US010203": {"producto": "CANAL DE AMARRE USG 6.35x 3.05 CAL. 26 US010203", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 49.81, "n2": 48.81, "n3": 47.32},
    "US010204": {"producto": "CANAL GALV. USG 9.20x 3.05 MTS CAL. 26 US010204", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 64.83, "n2": 63.53, "n3": 61.59},
    "US010205": {"producto": "CANAL LISTON USG DE 3.05 CAL. 26 US010205", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 40.61, "n2": 39.80, "n3": 38.58},
    "US010206": {"producto": "CANALETA DE CARGA USG 1.5x 3.05 CAL. 22 US010206", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 45.16, "n2": 44.71, "n3": 44.26},
    "US010208": {"producto": "ESQUINERO METALICO USG 3.05 MTS CAL 28 US010208", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 28.77, "n2": 27.91, "n3": 27.33},
    "US010209": {"producto": "REBORDE TIPO J USG 3.05 MTS CAL 28 US010209", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 31.70, "n2": 30.75, "n3": 30.12},
    "US010210": {"producto": "ANGULO USG DUROCK DE 3.05 CAL. 20 US010210", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 50.20, "n2": 48.69, "n3": 46.69},
    "US010211": {"producto": "CANAL USG DUROCK 4.10x 3.05 CAL.22 US010211", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 70.14, "n2": 68.04, "n3": 66.63},
    "US010212": {"producto": "CANAL USG DUROCK 6.35x 3.05 CAL.22 US010212", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 87.37, "n2": 85.62, "n3": 83.00},
    "US010213": {"producto": "CANAL USG DUROCK 9.20x 3.05 CAL.22 US010213", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 113.10, "n2": 109.71, "n3": 106.31},
    "US010214": {"producto": "CANAL USG DUROCK 1524x 3.05 CAL. 22 US010214", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 168.73, "n2": 163.67, "n3": 160.29},
    "US010215": {"producto": "CANAL LISTON USG DUROCK x 3.05 CAL.20 US010215", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 86.94, "n2": 84.33, "n3": 82.59},
    "US010216": {"producto": "POSTE METALICO USG 4.10x 3.05 CAL. 26 US010216", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 50.61, "n2": 49.09, "n3": 48.08},
    "US010218": {"producto": "POSTE METALICO USG 6.35x 3.05 CAL. 26 US010218", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 61.49, "n2": 59.65, "n3": 58.42},
    "US010220": {"producto": "POSTE METALICO USG 9.20x 3.05 CAL 26 US010220", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 73.22, "n2": 71.02, "n3": 69.56},
    "US010222": {"producto": "POSTE DUROCK USG 4.10x 3.05 CAL. 20 US010222", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 104.17, "n2": 101.04, "n3": 98.96},
    "US010223": {"producto": "POSTE DUROCK USG 6.35x 3.05 CAL.20 US010223", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 126.01, "n2": 122.23, "n3": 119.71},
    "US010225": {"producto": "POSTE DUROCK USG 9.20x 3.05 CAL. 20 US010225", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 152.89, "n2": 148.30, "n3": 145.25},
    "US010226": {"producto": "POSTE DUROCK USG 1524x 305 DE 3.05 CAL. 20 US010226", "categoria": "Perfiles USG", "unidad": "PZA", "n1": 220.23, "n2": 213.62, "n3": 209.22},
    "US010100": {"producto": "ANGULO PERIMETRAL M7 DE 3.66 US010100", "categoria": "Plafones y Suspensión", "unidad": "PZA", "n1": 181.02, "n2": 179.21, "n3": 175.59},
    "US010101": {"producto": "TEE CONECTORA DX-216 DE 0.61 MTS US010101", "categoria": "Plafones y Suspensión", "unidad": "PZA", "n1": 42.23, "n2": 41.81, "n3": 41.39},
    "US010102": {"producto": "TEE CONECTORA DX-416 DE 1.22 MTS US010102", "categoria": "Plafones y Suspensión", "unidad": "PZA", "n1": 82.74, "n2": 81.91, "n3": 81.09},
    "US010103": {"producto": "TEE PRINCIPAL DX-24 DE 3.66 MTS US010103", "categoria": "Plafones y Suspensión", "unidad": "PZA", "n1": 274.96, "n2": 272.21, "n3": 269.46},
    "US010310": {"producto": "YESO SUPREMO 40 KG US010310", "categoria": "Pastas, Basecoat y Yesos", "unidad": "PZA", "n1": 160.99, "n2": 156.16, "n3": 152.94},
    "US010312": {"producto": "YESO SUPERMOLD 40 KG US010312", "categoria": "Pastas, Basecoat y Yesos", "unidad": "PZA", "n1": 157.25, "n2": 152.53, "n3": 149.39},
    "IP050701-IP050702": {"producto": "MASTER LASSER 3.0mm F.V. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 854.65, "n2": 829.01, "n3": 811.92},
    "IP050709-IP050710": {"producto": "MASTER LASSER 3.5mm F.V. GRAV.", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 953.11, "n2": 907.44, "n3": 888.73},
    "IP050712-IP050713": {"producto": "MASTER LASSER 3.5mm F.P. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 1167.21, "n2": 1132.19, "n3": 1108.85},
    "IP050715-IP050716": {"producto": "MASTER LASSER 4.0mm F.P. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 1226.10, "n2": 1189.20, "n3": 1164.70},
    "IP050718-IP050719": {"producto": "MASTER LASSER 4.5mm F.P. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 1449.23, "n2": 1405.03, "n3": 1376.89},
    "IP050704": {"producto": "MASTER LASSER 3.0mm LISO ARENADO", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 1227.32, "n2": 1202.77, "n3": 1165.95},
    "CM010102": {"producto": "CINTA FV AUTOADHESIVA 10 CM x 45 MTS.", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 78.46, "n2": 65.00, "n3": 63.75},
    "CM010106": {"producto": "PERFACINTA IMAC 5cm x 75m.", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 65.00, "n2": 59.20, "n3": 59.20},
    "CV011009": {"producto": "MULTICOLOR NG BASE NL CUBETA", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 1599.00, "n2": 1590.50, "n3": 1585.58},
    "IMA020101": {"producto": "TORNILLO IMAC TIPO S DE 1\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 16.00, "n2": 15.95, "n3": 15.95},
    "IMA020102": {"producto": "TORNILLO IMAC TIPO DS 1-1/4\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 51.68, "n2": 51.68, "n3": 51.68},
    "IMA020103": {"producto": "TORNILLO IMAC TEK PLANO 1/2\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 27.00, "n2": 26.40, "n3": 26.40},
    "IMA020105": {"producto": "TORNILLO IMAC P/TAQUETE 1 1/2\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 36.26, "n2": 36.26, "n3": 36.26},
    "IMA020106": {"producto": "TORNILLO IMAC FRAMER AB7x7/16 (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 18.96, "n2": 18.96, "n3": 18.96},
    "IMA020109": {"producto": "TORNILLO IMAC TEK BROCA 1\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 21.33, "n2": 21.33, "n3": 21.33},
    "IMA020110": {"producto": "TORNILLO IMAC TEK BROCA 1 5/8\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 21.40, "n2": 21.40, "n3": 21.40},
    "IMA020201": {"producto": "CINTA DE PAPEL C/ALUMINIO 50mm x 30m", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 216.00, "n2": 216.00, "n3": 216.00},
    "IMA030101": {"producto": "IMPER IMAC 5 AÑOS FIBRATADO BLANCO", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 853.44, "n2": 844.82, "n3": 844.82},
    "IMA030102": {"producto": "IMPER IMAC 5 AÑOS FIBRATADO ROJO", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 853.44, "n2": 844.82, "n3": 844.82},
    "IMA040202": {"producto": "TAQUETE IMAC PLASTICO GRIS 1/4 (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "unidad": "PZA", "n1": 32.00, "n2": 32.00, "n3": 32.00},
    "IP050102": {"producto": "MASTER PRIM \"A\" CUB. 19 LTS.", "categoria": "Impermeabilizantes y Recubrimientos", "unidad": "PZA", "n1": 800.00, "n2": 800.00, "n3": 800.00}
}

# --- MAPA EXACTO DE FICHAS TÉCNICAS (42 SKUs -> 14 ARCHIVOS ÚNICOS DE FICHAS.xlsx) ---
# Nota: Si deseas incluir también los 4 perfiles USG iniciales (US010201-US010204), solo descomenta esas 4 líneas.
FICHAS_TECNICAS_MAP = {
    "US010604": "ultraligh_fichatecnica",
    "US010301": "basecoat_fichatecnica",
    "US010305": "redimix_fichatecnica",
    "US010306": "redimix_fichatecnica",
    "US010307": "redimix_fichatecnica",
    "US010605": "antimoho_fichastecnicas",
    "US010601": "durock_fichatecnica",
    "US010610-11-12": "texturizado_fichatecnicausg",
    "US101131": "radar_fichatecnica",
    "US101132": "radar_fichatecnica",
    # "US010201": "metalesusg_fichatecnica",
    # "US010202": "metalesusg_fichatecnica",
    # "US010203": "metalesusg_fichatecnica",
    # "US010204": "metalesusg_fichatecnica",
    "US010205": "metalesusg_fichatecnica",
    "US010206": "metalesusg_fichatecnica",
    "US010208": "metalesusg_fichatecnica",
    "US010209": "metalesusg_fichatecnica",
    "US010210": "metalesusg_fichatecnica",
    "US010211": "metalesusg_fichatecnica",
    "US010212": "metalesusg_fichatecnica",
    "US010213": "metalesusg_fichatecnica",
    "US010214": "metalesusg_fichatecnica",
    "US010215": "metalesusg_fichatecnica",
    "US010216": "metalesusg_fichatecnica",
    "US010218": "metalesusg_fichatecnica",
    "US010220": "metalesusg_fichatecnica",
    "US010222": "metalesusg_fichatecnica",
    "US010223": "metalesusg_fichatecnica",
    "US010225": "metalesusg_fichatecnica",
    "US010226": "metalesusg_fichatecnica",
    "US010100": "metalesusg_fichatecnica",
    "US010101": "suspensiondx_fichatecnica",
    "US010102": "suspensiondx_fichatecnica",
    "US010103": "suspensiondx_fichatecnica",
    "US010310": "yesosupremo_fichatecnica",
    "US010312": "yesosupermold_fichatecnica",
    "IP050701-IP050702": "masster_fichatecnica",
    "IP050709-IP050710": "masster_fichatecnica",
    "IP050712-IP050713": "masster_fichatecnica",
    "IP050715-IP050716": "masster_fichatecnica",
    "IP050718-IP050719": "masster_fichatecnica",
    "IP050704": "masster_fichatecnica",
    "IMA030101": "imperimac_fichatecnica",
    "IMA030102": "imperimac_fichatecnica",
    "IP050102": "masterprima_fichatecnica",
}

# --- FUNCIONES DE NORMALIZACIÓN Y RESOLUCIÓN DE SUCURSAL ---
def normalizar_texto(texto):
    s = str(texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def resolver_sucursal_clave(sucursal_raw):
    """Mapea cualquier variante escrita en Google Sheets (acentos, abreviaturas) a la clave exacta."""
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

# --- MOTOR DE BÚSQUEDA, DEDUPLICACIÓN Y FUSIÓN DE FICHAS TÉCNICAS ---
def buscar_archivo_ficha(nombre_base):
    """Busca la ficha técnica en fichas_tecnicas/ o raíz, tolerando mayúsculas/minúsculas y extensión (.pdf/.png/.jpg)."""
    base_clean = str(nombre_base or "").strip()
    if not base_clean:
        return None
    objetivo_lower = base_clean.lower()
    exts_validas = (".pdf", ".png", ".jpg", ".jpeg")

    directorios = [CARPETA_FICHAS, "."]
    for carpeta in directorios:
        if not os.path.isdir(carpeta):
            continue
        # 1) Búsqueda directa rápida
        for ext in ("", ".pdf", ".PDF", ".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"):
            cand = os.path.join(carpeta, base_clean + ext) if carpeta != "." else (base_clean + ext)
            if os.path.isfile(cand):
                return cand
        # 2) Búsqueda insensible a mayúsculas/minúsculas dentro del directorio
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
    """Devuelve lista ordenada y SIN DUPLICADOS de fichas técnicas correspondientes a las partidas del carrito."""
    fichas_unicas = []
    vistas = set()
    for item in carrito:
        clave = str(item.get("clave", "")).strip()
        ficha_base = FICHAS_TECNICAS_MAP.get(clave)
        if not ficha_base:
            continue
        ficha_key = ficha_base.strip().lower()
        if ficha_key in vistas:
            continue
        vistas.add(ficha_key)
        fichas_unicas.append(ficha_base.strip())
    return fichas_unicas

def convertir_imagen_a_pdf_bytes(ruta_img):
    """Convierte una ficha técnica en imagen (PNG/JPG) a una página PDF A4 proporcional."""
    from PIL import Image
    im = Image.open(ruta_img)
    w_px, h_px = im.size
    pdf_img = FPDF(unit="mm", format="A4")
    pdf_img.add_page()
    max_w, max_h = 190.0, 277.0
    escala = min(max_w / float(w_px), max_h / float(h_px))
    w_mm = w_px * escala
    h_mm = h_px * escala
    x_pos = (210.0 - w_mm) / 2.0
    y_pos = (297.0 - h_mm) / 2.0
    pdf_img.image(ruta_img, x=x_pos, y=y_pos, w=w_mm, h=h_mm)
    return pdf_img.output(dest="S").encode("latin-1")

def anexar_fichas_a_pdf(pdf_base_bytes, carrito):
    """Une al final del PDF de la cotización las fichas técnicas únicas (0 repeticiones)."""
    if not PYPDF_OK:
        return pdf_base_bytes

    fichas_unicas = obtener_fichas_unicas_carrito(carrito)
    if not fichas_unicas:
        return pdf_base_bytes

    rutas_encontradas = []
    for ficha_base in fichas_unicas:
        ruta = buscar_archivo_ficha(ficha_base)
        if ruta and ruta not in rutas_encontradas:
            rutas_encontradas.append(ruta)

    if not rutas_encontradas:
        return pdf_base_bytes

    try:
        writer = PdfWriter()
        base_reader = PdfReader(io.BytesIO(pdf_base_bytes))
        for page in base_reader.pages:
            writer.add_page(page)

        for ruta in rutas_encontradas:
            try:
                ext = os.path.splitext(ruta)[1].lower()
                if ext == ".pdf":
                    ficha_reader = PdfReader(ruta)
                    for page in ficha_reader.pages:
                        writer.add_page(page)
                elif ext in (".png", ".jpg", ".jpeg"):
                    img_pdf_bytes = convertir_imagen_a_pdf_bytes(ruta)
                    img_reader = PdfReader(io.BytesIO(img_pdf_bytes))
                    for page in img_reader.pages:
                        writer.add_page(page)
            except Exception:
                # Si una ficha individual está dañada, continúa sin bloquear la cotización
                continue

        salida = io.BytesIO()
        writer.write(salida)
        return salida.getvalue()
    except Exception:
        return pdf_base_bytes

# --- CONEXIÓN GOOGLE SHEETS Y BITÁCORA ---
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
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(credenciales_dic, scopes=scopes)
        cliente = gspread.authorize(creds)
        return cliente.open_by_key(id_excel), "OK"
    except Exception as e:
        return None, str(e)

def conectar_sheets():
    doc, _ = conectar_sheets_con_estado()
    return doc

def registrar_bitacora(doc, modulo, accion):
    try:
        if doc:
            hoja_bit = doc.worksheet("Bitacora_Movimientos")
            fecha_hora = ahora_mx().strftime("%d/%m/%Y %H:%M:%S")
            usuario = st.session_state.get("usuario", "Sistema")
            rol = st.session_state.get("role", "Desconocido")
            hoja_bit.append_row([fecha_hora, usuario, rol, modulo, accion])
    except Exception:
        pass

def obtener_nuevo_folio(doc, prefijo):
    """Genera folio corto e independiente por sucursal (ej. IVR-0001) sin duplicados."""
    prefijo_clean = str(prefijo or "IVR").strip().upper()
    patron = re.compile(rf"^{re.escape(prefijo_clean)}-(\d+)$", re.IGNORECASE)
    max_num = 0
    try:
        if doc:
            hoja = doc.worksheet("Cotizaciones")
            col_folios = hoja.col_values(1)
            for val in col_folios:
                m = patron.match(str(val or "").strip())
                if m:
                    num = int(m.group(1))
                    if num > max_num:
                        max_num = num
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
        celda_check = str(hoja.cell(fila_real, 1).value or "").strip()
        if celda_check != str(folio_objetivo).strip():
            col_folios = hoja.col_values(1)
            fila_real = next(
                (idx + 1 for idx, val in enumerate(col_folios) if str(val).strip() == str(folio_objetivo).strip()),
                None
            )
    except Exception:
        col_folios = hoja.col_values(1)
        fila_real = next(
            (idx + 1 for idx, val in enumerate(col_folios) if str(val).strip() == str(folio_objetivo).strip()),
            None
        )
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
            f"Folio: {folio}\n"
            f"Sucursal: {sucursal_nombre}\n"
            f"Asesor: {asesor}\n"
            f"Cliente: {cliente}\n"
            f"Total: ${total_mxn:,.2f} MXN\n\n"
            f"Se adjunta el PDF oficial."
        )
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=nombre_archivo)
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(remitente, password)
            smtp.send_message(msg)
        return True, "OK"
    except Exception as e:
        return False, str(e)

# --- CÁLCULOS DE PRECIOS Y TOTALES (PRECIO NETO CUADRADO AL CENTAVO) ---
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
    desc_global_monto = 0.0
    subtotal_neto_partidas = 0.0
    ahorro_nivel = 0.0
    desc_global_seguro = min(max(0.0, float(desc_extra_pct)), MAX_DESC_PCT)
    partidas_netas = []

    for x in carrito:
        cant = float(x["cantidad"])
        pu_base = float(x["precio_unit"])
        imp_bruto = cant * pu_base

        desc_p = min(max(0.0, float(x.get("desc_pct", 0.0))), MAX_DESC_PCT) if x.get("nivel") == "NIVEL 1" else 0.0
        pu_post_n1 = pu_base * (1.0 - desc_p / 100.0)
        pu_neto = round(pu_post_n1 * (1.0 - desc_global_seguro / 100.0), 2)
        imp_neto = round(cant * pu_neto, 2)

        desc_n1_m = imp_bruto - (cant * pu_post_n1)
        desc_glob_m = (cant * pu_post_n1) - imp_neto

        subtotal_bruto += imp_bruto
        total_desc_partidas += max(0.0, desc_n1_m)
        desc_global_monto += max(0.0, desc_glob_m)
        subtotal_neto_partidas += imp_neto
        ahorro_nivel += max(0.0, (float(x.get("precio_lista", pu_base)) - pu_base) * cant)

        partidas_netas.append({
            "clave": str(x["clave"]),
            "producto": str(x["producto"]),
            "cantidad": cant,
            "pu_neto": pu_neto,
            "imp_neto": imp_neto
        })

    base_neta = round(subtotal_neto_partidas + float(flete), 2)

    if precios_incluyen_iva:
        total_final = base_neta
        subtotal_sin_iva = round(total_final / 1.16, 2)
        iva_monto = round(total_final - subtotal_sin_iva, 2)
    else:
        subtotal_sin_iva = base_neta
        iva_monto = round(subtotal_sin_iva * 0.16, 2)
        total_final = round(subtotal_sin_iva + iva_monto, 2)

    return {
        "subtotal_bruto": round(subtotal_bruto, 2),
        "total_desc_partidas": round(total_desc_partidas, 2),
        "desc_global_monto": round(desc_global_monto, 2),
        "ahorro_nivel": round(ahorro_nivel, 2),
        "subtotal_sin_iva": subtotal_sin_iva,
        "iva_monto": iva_monto,
        "total_final": total_final,
        "partidas_netas": partidas_netas
    }

def limpiar_pdf_txt(texto):
    return str(texto).encode("latin-1", "replace").decode("latin-1")

# --- GENERADOR PDF CORPORATIVO CUADRADO AL MILÍMETRO (CON ANEXO AUTOMÁTICO DE FICHAS TÉCNICAS) ---
class PDFCorporativoIMAC(FPDF):
    def __init__(self, suc_info, folio_txt, fecha_hora_txt):
        super().__init__()
        self.suc_info = suc_info
        self.folio_txt = folio_txt
        self.fecha_hora_txt = fecha_hora_txt

    def header(self):
        # 1. Franja superior azul corporativo (y = 0..3 mm)
        self.set_fill_color(15, 60, 140)
        self.rect(0, 0, 210, 3, "F")

        # 2. Logo IMAC 2026 cuadrado (720x720 -> 20x20 mm en x=10..30, y=6..26)
        img_imac = buscar_imagen(["logo_imac_2026.png", "logo_imac_2026.jpg", "logo_imac.png"])
        if img_imac:
            self.image(img_imac, x=10, y=6, w=20, h=20)

        # 3. Logo Master Lasser (302x62 -> 48x9.85 mm en x=152..200, y=10.5..20.35)
        img_ml = buscar_imagen(["logo_master_lasser.png", "logo_master_lasser.jpg", "logo_master_lasser.jpeg"])
        if img_ml:
            self.image(img_ml, x=152, y=10.5, w=48)

        # 4. Encabezado Central (x=33..149 -> 116 mm sin tocar ningún logo)
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

        # 5. Barra de metadatos debajo del logo IMAC (y = 28.5..34.0 mm, cero colisiones)
        self.set_xy(10, 28.5)
        self.set_font("Arial", "B", 9)
        self.set_text_color(200, 30, 30)
        self.cell(95, 5, limpiar_pdf_txt(f"FOLIO: {self.folio_txt}"), ln=False, align="L")

        self.set_font("Arial", "B", 8.5)
        self.set_text_color(60, 60, 60)
        self.cell(95, 5, limpiar_pdf_txt(f"Fecha y Hora: {self.fecha_hora_txt}"), ln=True, align="R")

        # 6. Línea divisoria (y = 35 mm) y arranque seguro del contenido (y = 38 mm)
        self.set_draw_color(200, 212, 230)
        self.line(10, 35, 200, 35)
        self.set_y(38)

    def footer(self):
        # Footer gráfico oficial (1051x232 -> 190x41.94 mm en y=250..291.94 mm)
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
    # Hora local de Veracruz / México (formato 24h con hrs)
    fecha_hora = ahora_mx().strftime("%d/%m/%Y %H:%M hrs")
    pdf = PDFCorporativoIMAC(suc_info, folio, fecha_hora)
    # Margen inferior 52 mm -> salto automático a los 245 mm (5 mm seguros arriba del footer en y=250)
    pdf.set_auto_page_break(auto=True, margin=52)
    pdf.add_page()

    # Calcular totales netos (los descuentos se integran de forma invisible al precio unitario)
    tot = calcular_totales_carrito(carrito, flete, desc_extra_pct, precios_incluyen_iva)

    # --- TARJETA DEL CLIENTE (y = 38..57.5 mm) ---
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

    # --- TABLA DE PARTIDAS LIMPIA (6 COLUMNAS, 190 mm EXACTOS, CERO % Y CERO NIVELES) ---
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
        pdf.cell(25, 6.5, f"${row['pu_neto']:,.2f}", "B", 0, "R", fill)
        pdf.cell(25, 6.5, f"${row['imp_neto']:,.2f}", "B", 1, "R", fill)

    # --- BLOQUE DE CONDICIONES (IZQUIERDA) + SUMATORIA LIMPIA (DERECHA) ---
    if pdf.get_y() > 172:
        pdf.add_page()

    pdf.ln(5)
    y_resumen = pdf.get_y()

    # Izquierda: Observaciones y Condiciones (x = 10..116, ancho 106 mm)
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

    # Derecha: SOLO SUMATORIA FINAL (x = 122..200, ancho 78 mm alineado al borde de la tabla)
    pdf.set_xy(122, y_resumen)
    pdf.set_font("Arial", "B", 8.6)
    pdf.set_text_color(55, 55, 55)

    if float(flete) > 0:
        pdf.set_x(122)
        pdf.cell(40, 5.5, "FLETE / ENVIO:", 0, 0, "R")
        pdf.cell(38, 5.5, f"${float(flete):,.2f}", 0, 1, "R")

    pdf.set_x(122)
    pdf.cell(40, 5.8, "SUB TOTAL:", 0, 0, "R")
    pdf.cell(38, 5.8, f"${tot['subtotal_sin_iva']:,.2f}", 0, 1, "R")

    pdf.set_x(122)
    pdf.cell(40, 5.8, "IVA (16%):", 0, 0, "R")
    pdf.cell(38, 5.8, f"${tot['iva_monto']:,.2f}", 0, 1, "R")

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

    # --- BLOQUE DE CIERRE: FIRMA ASESOR (IZQ) + TARJETA BBVA (DER) ---
    y_cierre = max(y_fin_izq, y_fin_der) + 7
    if y_cierre > 205:
        pdf.add_page()
        y_cierre = pdf.get_y() + 2

    # Izquierda: Firma del Asesor (x = 10..108, ancho 98 mm)
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

    # Derecha: Tarjeta Bancaria BBVA (x = 112..200, ancho 88 mm, alto 38 mm)
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
    bloque_banco = (
        f"Cuenta: {suc_info['cuenta']}\n"
        f"CLABE: {suc_info['clabe']}\n"
        f"RFC: {suc_info['rfc']}"
    )
    pdf.multi_cell(80, 4.8, limpiar_pdf_txt(bloque_banco))

    pdf_final_bytes = pdf.output(dest="S").encode("latin-1")

    # Anexar automáticamente las fichas técnicas únicas al final del PDF (sin repeticiones)
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
