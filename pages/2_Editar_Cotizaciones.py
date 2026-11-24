import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
import datetime
import json
import os
import smtplib
from email.message import EmailMessage
import pandas as pd
from PIL import Image

# --- CONFIGURACIÓN DE PÁGINA ---
icono_nav = "logo_imac_2026.png" if os.path.exists("logo_imac_2026.png") else "🏢"
st.set_page_config(
    page_title="Consultar y Editar Cotizaciones | Grupo IMAC",
    page_icon=icono_nav,
    layout="wide"
)

# --- REGLAS COMERCIALES INTERNAS (OCULTAS EN PANTALLA PARA TODOS) ---
MIN_PZAS_NIVEL_2 = 50
MIN_PZAS_NIVEL_3 = 60
MAX_DESC_PCT = 10.0  # Límite máximo permitido tanto en descuento individual N1 como en global (10%)
PRECIOS_INCLUYEN_IVA = False  # False = Precios más 16% IVA | True = Precios con IVA incluido

# --- CANDADO DE SESIÓN ---
if not st.session_state.get("logged_in", False):
    st.warning("⚠️ Acceso denegado. Inicia sesión primero en la página principal (`app`).")
    st.stop()

# --- RESPALDO DE CONFIGURACIÓN DE SUCURSALES (SINCRONIZADO CON app.py) ---
CONFIG_SUCURSALES_DEFAULT = {
    "IMAC": {
        "nombre_oficial": "GRUPO IMAC - MATRIZ MIGUEL ALEMÁN",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "AV. MIGUEL ALEMÁN #759, COL. CENTRO, VERACRUZ, VER.",
        "telefono": "(229) 935 3940",
        "correo": "comercial@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "prefijo_folio": "IMAC"
    },
    "EJÉRCITO": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL EJÉRCITO MEXICANO",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "AV. EJÉRCITO MEXICANO, BOCA DEL RÍO, VER.",
        "telefono": "POR DEFINIR",
        "correo": "ejercito@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "prefijo_folio": "EJER"
    },
    "BOCA DEL RÍO": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL BOCA DEL RÍO",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "BLVD. MIGUEL ALEMÁN #306, COL. CENTRO, BOCA DEL RÍO, VER.",
        "telefono": "(229) 935 4525",
        "correo": "boca@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "prefijo_folio": "BOCA"
    },
    "RIVIERA": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL RIVIERA VERACRUZANA",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "ZONA RIVIERA VERACRUZANA, ALVARADO / BOCA DEL RÍO, VER.",
        "telefono": "POR DEFINIR",
        "correo": "riviera@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "prefijo_folio": "RIV"
    },
    "FRAMBOYANES": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL FRAMBOYANES",
        "razon_social": "TARC S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "ZONA PLAZA FRAMBOYANES, VERACRUZ, VER.",
        "telefono": "POR DEFINIR",
        "correo": "framboyanes@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "prefijo_folio": "FRAM"
    },
    "IMACRIL CENTRO": {
        "nombre_oficial": "IMACRIL - SUCURSAL CENTRO 5 DE MAYO",
        "razon_social": "IMACRIL S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "AV. 5 DE MAYO, COL. CENTRO, VERACRUZ, VER.",
        "telefono": "POR DEFINIR",
        "correo": "centro@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "prefijo_folio": "CENT"
    }
}

CONFIG_SUCURSALES = st.session_state.get("config_sucursales", CONFIG_SUCURSALES_DEFAULT)

# --- CATÁLOGO AUDITADO: 74 PRODUCTOS MXN (PUNTO DECIMAL + ANOMALÍAS CORREGIDAS) ---
CATALOGO_LIGEROS = {
    "US010604": {"producto": "TABLAROCA ULTRALIGHT 12.7mm x 1.22 US010604", "categoria": "Paneles (Tablaroca / Durock)", "n1": 206.24, "n2": 199.85, "n3": 189.00},
    "US010301": {"producto": "BASECOAT DUROCK FORTE 20 KG. US010301", "categoria": "Pastas, Basecoat y Yesos", "n1": 515.09, "n2": 499.64, "n3": 489.34},
    "US010305": {"producto": "REDIMIX 25 KGS. US010305", "categoria": "Pastas, Basecoat y Yesos", "n1": 461.41, "n2": 447.57, "n3": 438.34},
    "US010306": {"producto": "REDIMIX 28 KGS. US010306", "categoria": "Pastas, Basecoat y Yesos", "n1": 597.00, "n2": 585.06, "n3": 573.12},
    "US010307": {"producto": "PASTA TABLAROCA 21.8 KG US010307", "categoria": "Pastas, Basecoat y Yesos", "n1": 367.00, "n2": 363.33, "n3": 355.99},
    "US010605": {"producto": "TABLAROCA ANTI-MOHO 12.7MM US010605", "categoria": "Paneles (Tablaroca / Durock)", "n1": 302.00, "n2": 292.94, "n3": 286.90},
    "US010601": {"producto": "TABLAROCA DUROCK ( TABLACEMENTO) US010601", "categoria": "Paneles (Tablaroca / Durock)", "n1": 874.00, "n2": 847.78, "n3": 799.00},
    "US010610-11-12": {"producto": "TABLAROCA TEXT ASTRAL, POLAR, SOLAR", "categoria": "Paneles (Tablaroca / Durock)", "n1": 118.12, "n2": 114.58, "n3": 112.21},
    "US101131": {"producto": "PLAFON RADAR LS 0.61x 0.61 ITEM:2220 US101131", "categoria": "Plafones y Suspensión", "n1": 2280.50, "n2": 2212.09, "n3": 2166.48},
    "US101132": {"producto": "PLAFON RADAR OC 61x 1.22 Item: 2410", "categoria": "Plafones y Suspensión", "n1": 1893.00, "n2": 1836.41, "n3": 1798.89},
    "GN010101": {"producto": "ANGULO COMERCIAL 3.05 CAL. 26 GN010101", "categoria": "Perfiles Comerciales", "n1": 21.89, "n2": 21.23, "n3": 20.58},
    "GN010102": {"producto": "CANAL COMERCIAL 4.10x 3.05 CAL. 26 GN010102", "categoria": "Perfiles Comerciales", "n1": 36.96, "n2": 35.85, "n3": 34.37},
    "GN010103": {"producto": "CANAL COMERCIAL 6.35x 3.05 CAL. 26 GN010103", "categoria": "Perfiles Comerciales", "n1": 47.57, "n2": 46.14, "n3": 44.72},
    "GN010104": {"producto": "CANAL LISTON COMERCIAL DE 3.05 CAL. 26 GN010104", "categoria": "Perfiles Comerciales", "n1": 38.14, "n2": 37.00, "n3": 35.85},
    "GN010105": {"producto": "CANALETA DE CARGA COMERCIAL 3.05 CAL. 22 GN010105", "categoria": "Perfiles Comerciales", "n1": 36.57, "n2": 35.47, "n3": 34.38},
    "GN010107": {"producto": "POSTE COMERCIAL 4.10x 3.05 CAL.26 GN010107", "categoria": "Perfiles Comerciales", "n1": 47.28, "n2": 45.86, "n3": 44.44},
    "GN010109": {"producto": "POSTE COMERCIAL 6.35x 3.05 CAL. 26 GN010109", "categoria": "Perfiles Comerciales", "n1": 55.88, "n2": 54.20, "n3": 52.53},
    "GN010110": {"producto": "ESQUINERO COMERCIAL 3.05 CAL. 28 GN010110", "categoria": "Perfiles Comerciales", "n1": 20.38, "n2": 19.97, "n3": 19.36},
    "GN010112": {"producto": "CANAL COMERCIAL 9.20x 3.05 CAL. 26 GN010112", "categoria": "Perfiles Comerciales", "n1": 60.18, "n2": 58.37, "n3": 56.57},
    "GN010114": {"producto": "POSTE COMERCIAL 9.20x 3.05 CAL. 26 GN010114", "categoria": "Perfiles Comerciales", "n1": 70.34, "n2": 68.23, "n3": 66.12},
    "GN010116": {"producto": "POSTE COMERCIAL 6.35x 3.05 CAL.20 GN010116", "categoria": "Perfiles Comerciales", "n1": 109.41, "n2": 106.13, "n3": 102.85},
    "GN010121": {"producto": "CANAL COMERCIAL 6.35x 3.05 CAL. 22 GN010121", "categoria": "Perfiles Comerciales", "n1": 84.86, "n2": 83.16, "n3": 81.47},
    "GN010123": {"producto": "CANAL AMARRE COMERCIAL 4.10x 3.05 CAL. 22 GN010123", "categoria": "Perfiles Comerciales", "n1": 57.83, "n2": 56.10, "n3": 54.36},
    "GN010124": {"producto": "POSTE COMERCIAL 4.10x 3.05 CAL. 20 GN010124", "categoria": "Perfiles Comerciales", "n1": 92.21, "n2": 89.44, "n3": 86.68},
    "GN010126": {"producto": "CANAL COMERCIAL 9.20x 3.05 CAL. 22 GN010126", "categoria": "Perfiles Comerciales", "n1": 95.34, "n2": 92.48, "n3": 89.62},
    "GN010127": {"producto": "POSTE COMERCIAL 9.20x 3.05 CAL. 20 GN010127", "categoria": "Perfiles Comerciales", "n1": 137.71, "n2": 133.58, "n3": 128.07},
    "US010201": {"producto": "ANGULO PERIMETRAL USG 3.05 MTS CAL 26 US010201", "categoria": "Perfiles USG", "n1": 24.74, "n2": 24.00, "n3": 23.50},
    "US010202": {"producto": "CANAL DE AMARRE USG 4.10x 3.05 CAL. 26 US010202", "categoria": "Perfiles USG", "n1": 41.05, "n2": 40.23, "n3": 39.00},
    "US010203": {"producto": "CANAL DE AMARRE USG 6.35x 3.05 CAL. 26 US010203", "categoria": "Perfiles USG", "n1": 49.81, "n2": 48.81, "n3": 47.32},
    "US010204": {"producto": "CANAL GALV. USG 9.20x 3.05 MTS CAL. 26 US010204", "categoria": "Perfiles USG", "n1": 64.83, "n2": 63.53, "n3": 61.59},
    "US010205": {"producto": "CANAL LISTON USG DE 3.05 CAL. 26 US010205", "categoria": "Perfiles USG", "n1": 40.61, "n2": 39.80, "n3": 38.58},
    "US010206": {"producto": "CANALETA DE CARGA USG 1.5x 3.05 CAL. 22 US010206", "categoria": "Perfiles USG", "n1": 45.16, "n2": 44.71, "n3": 44.26},
    "US010208": {"producto": "ESQUINERO METALICO USG 3.05 MTS CAL 28 US010208", "categoria": "Perfiles USG", "n1": 28.77, "n2": 27.91, "n3": 27.33},
    "US010209": {"producto": "REBORDE TIPO J USG 3.05 MTS CAL 28 US010209", "categoria": "Perfiles USG", "n1": 31.70, "n2": 30.75, "n3": 30.12},
    "US010210": {"producto": "ANGULO USG DUROCK DE 3.05 CAL. 20 US010210", "categoria": "Perfiles USG", "n1": 50.20, "n2": 48.69, "n3": 46.69},
    "US010211": {"producto": "CANAL USG DUROCK 4.10x 3.05 CAL.22 US010211", "categoria": "Perfiles USG", "n1": 70.14, "n2": 68.04, "n3": 66.63},
    "US010212": {"producto": "CANAL USG DUROCK 6.35x 3.05 CAL.22 US010212", "categoria": "Perfiles USG", "n1": 87.37, "n2": 85.62, "n3": 83.00},
    "US010213": {"producto": "CANAL USG DUROCK 9.20x 3.05 CAL.22 US010213", "categoria": "Perfiles USG", "n1": 113.10, "n2": 109.71, "n3": 106.31},
    "US010214": {"producto": "CANAL USG DUROCK 1524x 3.05 CAL. 22 US010214", "categoria": "Perfiles USG", "n1": 168.73, "n2": 163.67, "n3": 160.29},
    "US010215": {"producto": "CANAL LISTON USG DUROCK x 3.05 CAL.20 US010215", "categoria": "Perfiles USG", "n1": 86.94, "n2": 84.33, "n3": 82.59},
    "US010216": {"producto": "POSTE METALICO USG 4.10x 3.05 CAL. 26 US010216", "categoria": "Perfiles USG", "n1": 50.61, "n2": 49.09, "n3": 48.08},
    "US010218": {"producto": "POSTE METALICO USG 6.35x 3.05 CAL. 26 US010218", "categoria": "Perfiles USG", "n1": 61.49, "n2": 59.65, "n3": 58.42},
    "US010220": {"producto": "POSTE METALICO USG 9.20x 3.05 CAL 26 US010220", "categoria": "Perfiles USG", "n1": 73.22, "n2": 71.02, "n3": 69.56},
    "US010222": {"producto": "POSTE DUROCK USG 4.10x 3.05 CAL. 20 US010222", "categoria": "Perfiles USG", "n1": 104.17, "n2": 101.04, "n3": 98.96},
    "US010223": {"producto": "POSTE DUROCK USG 6.35x 3.05 CAL.20 US010223", "categoria": "Perfiles USG", "n1": 126.01, "n2": 122.23, "n3": 119.71},
    "US010225": {"producto": "POSTE DUROCK USG 9.20x 3.05 CAL. 20 US010225", "categoria": "Perfiles USG", "n1": 152.89, "n2": 148.30, "n3": 145.25},
    "US010226": {"producto": "POSTE DUROCK USG 1524x 305 DE 3.05 CAL. 20 US010226", "categoria": "Perfiles USG", "n1": 220.23, "n2": 213.62, "n3": 209.22},
    "US010100": {"producto": "ANGULO PERIMETRAL M7 DE 3.66 US010100", "categoria": "Plafones y Suspensión", "n1": 181.02, "n2": 179.21, "n3": 175.59},
    "US010101": {"producto": "TEE CONECTORA DX-216 DE 0.61 MTS US010101", "categoria": "Plafones y Suspensión", "n1": 42.23, "n2": 41.81, "n3": 41.39},
    "US010102": {"producto": "TEE CONECTORA DX-416 DE 1.22 MTS US010102", "categoria": "Plafones y Suspensión", "n1": 82.74, "n2": 81.91, "n3": 81.09},
    "US010103": {"producto": "TEE PRINCIPAL DX-24 DE 3.66 MTS US010103", "categoria": "Plafones y Suspensión", "n1": 274.96, "n2": 272.21, "n3": 269.46},
    "US010310": {"producto": "YESO SUPREMO 40 KG US010310", "categoria": "Pastas, Basecoat y Yesos", "n1": 160.99, "n2": 156.16, "n3": 152.94},
    "US010312": {"producto": "YESO SUPERMOLD 40 KG US010312", "categoria": "Pastas, Basecoat y Yesos", "n1": 157.25, "n2": 152.53, "n3": 149.39},
    "IP050701-IP050702": {"producto": "MASTER LASSER 3.0mm F.V. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 854.65, "n2": 829.01, "n3": 811.92},
    "IP050709-IP050710": {"producto": "MASTER LASSER 3.5mm F.V. GRAV.", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 953.11, "n2": 907.44, "n3": 888.73},
    "IP050712-IP050713": {"producto": "MASTER LASSER 3.5mm F.P. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 1167.21, "n2": 1132.19, "n3": 1108.85},
    "IP050715-IP050716": {"producto": "MASTER LASSER 4.0mm F.P. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 1226.10, "n2": 1189.20, "n3": 1164.70},
    "IP050718-IP050719": {"producto": "MASTER LASSER 4.5mm F.P. GRAV", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 1449.23, "n2": 1405.03, "n3": 1376.89},
    "IP050704": {"producto": "MASTER LASSER 3.0mm LISO ARENADO", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 1227.32, "n2": 1202.77, "n3": 1165.95},
    "CM010102": {"producto": "CINTA FV AUTOADHESIVA 10 CM x 45 MTS.", "categoria": "Tornillería, Cintas y Fijación", "n1": 78.46, "n2": 65.00, "n3": 63.75},
    "CM010106": {"producto": "PERFACINTA IMAC 5cm x 75m.", "categoria": "Tornillería, Cintas y Fijación", "n1": 65.00, "n2": 59.20, "n3": 59.20},
    "CV011009": {"producto": "MULTICOLOR NG BASE NL CUBETA", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 1599.00, "n2": 1590.50, "n3": 1585.58},
    "IMA020101": {"producto": "TORNILLO IMAC TIPO S DE 1\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 16.00, "n2": 15.95, "n3": 15.95},
    "IMA020102": {"producto": "TORNILLO IMAC TIPO DS 1-1/4\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 51.68, "n2": 51.68, "n3": 51.68},
    "IMA020103": {"producto": "TORNILLO IMAC TEK PLANO 1/2\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 27.00, "n2": 26.40, "n3": 26.40},
    "IMA020105": {"producto": "TORNILLO IMAC P/TAQUETE 1 1/2\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 36.26, "n2": 36.26, "n3": 36.26},
    "IMA020106": {"producto": "TORNILLO IMAC FRAMER AB7x7/16 (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 18.96, "n2": 18.96, "n3": 18.96},
    "IMA020109": {"producto": "TORNILLO IMAC TEK BROCA 1\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 21.33, "n2": 21.33, "n3": 21.33},
    "IMA020110": {"producto": "TORNILLO IMAC TEK BROCA 1 5/8\" (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 21.40, "n2": 21.40, "n3": 21.40},
    "IMA020201": {"producto": "CINTA DE PAPEL C/ALUMINIO 50mm x 30m", "categoria": "Tornillería, Cintas y Fijación", "n1": 216.00, "n2": 216.00, "n3": 216.00},
    "IMA030101": {"producto": "IMPER IMAC 5 AÑOS FIBRATADO BLANCO", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 853.44, "n2": 844.82, "n3": 844.82},
    "IMA030102": {"producto": "IMPER IMAC 5 AÑOS FIBRATADO ROJO", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 853.44, "n2": 844.82, "n3": 844.82},
    "IMA040202": {"producto": "TAQUETE IMAC PLASTICO GRIS 1/4 (100 PZAS)", "categoria": "Tornillería, Cintas y Fijación", "n1": 32.00, "n2": 32.00, "n3": 32.00},
    "IP050102": {"producto": "MASTER PRIM \"A\" CUB. 19 LTS.", "categoria": "Impermeabilizantes y Recubrimientos", "n1": 800.00, "n2": 800.00, "n3": 800.00}
}

# --- CONEXIÓN Y UTILIDADES ---
def obtener_secreto(clave):
    valor = os.environ.get(clave)
    if valor:
        return valor
    try:
        return st.secrets[clave]
    except Exception:
        return None

@st.cache_resource
def conectar_sheets():
    try:
        credenciales_raw = obtener_secreto("GOOGLE_CREDENTIALS")
        id_excel = obtener_secreto("ID_EXCEL")
        if not credenciales_raw or not id_excel:
            return None
        credenciales_dic = json.loads(credenciales_raw) if isinstance(credenciales_raw, str) else dict(credenciales_raw)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(credenciales_dic, scopes=scopes)
        cliente = gspread.authorize(creds)
        return cliente.open_by_key(id_excel)
    except Exception:
        return None

def registrar_bitacora(doc, modulo, accion):
    try:
        if doc:
            hoja_bit = doc.worksheet("Bitacora_Movimientos")
            fecha_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            usuario = st.session_state.get("usuario", "Sistema")
            rol = st.session_state.get("role", "Desconocido")
            hoja_bit.append_row([fecha_hora, usuario, rol, modulo, accion])
    except Exception:
        pass

def limpiar_monto(valor):
    if valor is None or str(valor).strip() == "":
        return 0.0
    try:
        return float(str(valor).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0

def actualizar_fila_cotizacion(hoja, folio_objetivo, fila_idx_sugerida, valores_fila):
    """Localiza la fila exacta del folio y sobrescribe A:M sin duplicar registros."""
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

def enviar_respaldo_correo(pdf_bytes, nombre_archivo, folio, sucursal_nombre, cliente, asesor, total_mxn, correo_dest):
    try:
        remitente = obtener_secreto("CORREO_BOT")
        password = obtener_secreto("PASS_BOT")
        if not remitente or not password:
            return False, "Faltan CORREO_BOT o PASS_BOT en Secrets."

        msg = EmailMessage()
        msg["Subject"] = f"ACTUALIZACION COTIZACION {folio} | {sucursal_nombre} - {cliente}"
        msg["From"] = remitente
        msg["To"] = correo_dest
        msg.set_content(
            f"Se ha actualizado una cotización de Sistemas Ligeros en mostrador.\n\n"
            f"Folio (conservado): {folio}\n"
            f"Sucursal: {sucursal_nombre}\n"
            f"Asesor: {asesor}\n"
            f"Cliente: {cliente}\n"
            f"Nuevo Total: ${total_mxn:,.2f} MXN\n\n"
            f"Se adjunta el PDF actualizado."
        )
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=nombre_archivo)
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(remitente, password)
            smtp.send_message(msg)
        return True, "OK"
    except Exception as e:
        return False, str(e)

def limpiar_pdf_txt(texto):
    return str(texto).encode("latin-1", "replace").decode("latin-1")

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

    for x in carrito:
        imp_bruto = x["cantidad"] * x["precio_unit"]
        desc_p = min(max(0.0, float(x.get("desc_pct", 0.0))), MAX_DESC_PCT) if x["nivel"] == "NIVEL 1" else 0.0
        desc_monto = imp_bruto * (desc_p / 100.0)
        subtotal_bruto += imp_bruto
        total_desc_partidas += desc_monto
        ahorro_nivel += max(0.0, (x["precio_lista"] - x["precio_unit"]) * x["cantidad"])

    subtotal_post_partidas = subtotal_bruto - total_desc_partidas
    desc_global_monto = subtotal_post_partidas * (desc_global_seguro / 100.0)
    base_neta = subtotal_post_partidas - desc_global_monto + flete

    if precios_incluyen_iva:
        total_final = base_neta
        subtotal_sin_iva = total_final / 1.16
        iva_monto = total_final - subtotal_sin_iva
    else:
        subtotal_sin_iva = base_neta
        iva_monto = subtotal_sin_iva * 0.16
        total_final = subtotal_sin_iva + iva_monto

    return {
        "subtotal_bruto": subtotal_bruto,
        "total_desc_partidas": total_desc_partidas,
        "desc_global_monto": desc_global_monto,
        "ahorro_nivel": ahorro_nivel,
        "subtotal_sin_iva": subtotal_sin_iva,
        "iva_monto": iva_monto,
        "total_final": total_final
    }

# --- DISEÑO PDF CORPORATIVO MODERNO (SIN MOSTRAR N1/N2/N3 AL CLIENTE) ---
class PDFMostrador(FPDF):
    def __init__(self, suc_nombre, folio_txt, fecha_txt):
        super().__init__()
        self.suc_nombre = suc_nombre
        self.folio_txt = folio_txt
        self.fecha_txt = fecha_txt

    def header(self):
        self.set_fill_color(15, 60, 140)
        self.rect(0, 0, 210, 4, "F")

        if os.path.exists("logo_imac_2026.png"):
            self.image("logo_imac_2026.png", x=10, y=8, w=32)
            x_titulo = 46
        else:
            x_titulo = 10

        self.set_xy(x_titulo, 10)
        self.set_font("Arial", "B", 14)
        self.set_text_color(15, 60, 140)
        self.cell(95, 6, "GRUPO IMAC", ln=False, align="L")

        self.set_xy(135, 10)
        self.set_font("Arial", "B", 10.5)
        self.set_text_color(200, 30, 30)
        self.cell(65, 5.5, limpiar_pdf_txt(f"FOLIO: {self.folio_txt}"), ln=True, align="R")

        self.set_xy(x_titulo, 16)
        self.set_font("Arial", "B", 8.5)
        self.set_text_color(0, 140, 230)
        self.cell(90, 5, "COTIZACION DE MATERIALES | SISTEMAS LIGEROS", ln=False, align="L")

        self.set_xy(135, 16)
        self.set_font("Arial", "I", 8.5)
        self.set_text_color(95, 95, 95)
        self.cell(65, 5, limpiar_pdf_txt(f"Veracruz, Ver. | {self.fecha_txt}"), ln=True, align="R")

        self.set_draw_color(215, 222, 232)
        self.line(10, 31, 200, 31)
        self.set_y(35)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(220, 225, 235)
        self.line(10, 282, 200, 282)
        self.set_font("Arial", "I", 7.5)
        self.set_text_color(120, 120, 120)
        self.cell(
            0, 6,
            limpiar_pdf_txt(f"Grupo IMAC - Sucursal {self.suc_nombre} | Precios en Pesos Mexicanos (MXN) - Pagina {self.page_no()}"),
            align="C"
        )

def generar_pdf_mostrador(folio, sucursal_nombre, suc_info, cliente, telefono, correo, asesor, validez, carrito, flete, desc_extra_pct, precios_incluyen_iva, notas):
    fecha_hoy = datetime.datetime.now().strftime("%d/%m/%Y")
    pdf = PDFMostrador(sucursal_nombre, folio, fecha_hoy)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    desc_extra_pct = min(max(0.0, float(desc_extra_pct)), MAX_DESC_PCT)
    y_cards = pdf.get_y()

    # Tarjeta 1: Sucursal Emisora
    pdf.set_fill_color(245, 247, 250)
    pdf.rect(10, y_cards, 93, 36, "F")
    pdf.set_fill_color(15, 60, 140)
    pdf.rect(10, y_cards, 2.2, 36, "F")

    pdf.set_xy(15, y_cards + 3.5)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(15, 60, 140)
    pdf.cell(84, 4.5, "SUCURSAL EMISORA:", ln=True)
    pdf.set_x(15)
    pdf.set_font("Arial", "B", 8.5)
    pdf.set_text_color(35, 35, 35)
    pdf.cell(84, 4.5, limpiar_pdf_txt(suc_info["nombre_oficial"]), ln=True)
    pdf.set_x(15)
    pdf.set_font("Arial", "", 7.5)
    pdf.set_text_color(90, 90, 90)
    texto_suc = f"{suc_info['razon_social']} | RFC: {suc_info['rfc']}\n{suc_info['direccion']}\nTel: {suc_info['telefono']} | {suc_info['correo']}"
    pdf.multi_cell(84, 3.8, limpiar_pdf_txt(texto_suc))
    pdf.set_x(15)
    pdf.set_font("Arial", "B", 7.5)
    pdf.set_text_color(0, 140, 230)
    pdf.cell(84, 4.5, limpiar_pdf_txt(f"ASESOR: {asesor.upper()}"), ln=True)

    # Tarjeta 2: Cliente
    pdf.set_fill_color(245, 247, 250)
    pdf.rect(107, y_cards, 93, 36, "F")
    pdf.set_fill_color(0, 150, 255)
    pdf.rect(107, y_cards, 2.2, 36, "F")

    pdf.set_xy(112, y_cards + 3.5)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(15, 60, 140)
    pdf.cell(84, 4.5, "DATOS DEL CLIENTE:", ln=True)
    pdf.set_x(112)
    pdf.set_font("Arial", "B", 9)
    pdf.set_text_color(35, 35, 35)
    pdf.cell(84, 5, limpiar_pdf_txt(cliente.upper() if cliente else "PUBLICO EN GENERAL"), ln=True)
    pdf.set_x(112)
    pdf.set_font("Arial", "", 7.8)
    pdf.set_text_color(90, 90, 90)
    info_cli = (
        f"Telefono: {telefono if telefono else 'N/A'}\n"
        f"Correo: {correo if correo else 'N/A'}\n"
        f"Vigencia: {validez.strftime('%d/%m/%Y')}\n"
        f"Moneda: PESOS MEXICANOS (MXN)"
    )
    pdf.multi_cell(84, 4.2, limpiar_pdf_txt(info_cli))

    pdf.set_y(y_cards + 42)

    # Encabezado de tabla SIN columna NIVEL (suma exacta = 190mm)
    def dibujar_encabezado_tabla():
        pdf.set_fill_color(15, 60, 140)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 7.8)
        pdf.cell(24, 7, "CLAVE", 0, 0, "C", True)
        pdf.cell(87, 7, "DESCRIPCION DEL MATERIAL", 0, 0, "L", True)
        pdf.cell(15, 7, "CANT.", 0, 0, "C", True)
        pdf.cell(15, 7, "DESC.", 0, 0, "C", True)
        pdf.cell(24, 7, "P. UNIT.", 0, 0, "R", True)
        pdf.cell(25, 7, "IMPORTE", 0, 1, "R", True)

    dibujar_encabezado_tabla()

    for idx, row in enumerate(carrito):
        if pdf.get_y() > 258:
            pdf.add_page()
            dibujar_encabezado_tabla()

        fill = (idx % 2 == 1)
        pdf.set_fill_color(246, 249, 253)
        pdf.set_draw_color(225, 230, 238)
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Arial", "", 7.3)

        desc_p_pct = min(max(0.0, float(row.get("desc_pct", 0.0))), MAX_DESC_PCT) if row["nivel"] == "NIVEL 1" else 0.0
        importe_bruto = row["cantidad"] * row["precio_unit"]
        importe_neto = importe_bruto * (1.0 - desc_p_pct / 100.0)
        desc_txt = f"{desc_p_pct:.1f}%" if desc_p_pct > 0 else "-"

        pdf.cell(24, 6.5, limpiar_pdf_txt(row["clave"][:13]), "B", 0, "C", fill)
        pdf.cell(87, 6.5, limpiar_pdf_txt(row["producto"][:51]), "B", 0, "L", fill)
        pdf.cell(15, 6.5, f"{row['cantidad']:g}", "B", 0, "C", fill)
        pdf.cell(15, 6.5, desc_txt, "B", 0, "C", fill)
        pdf.cell(24, 6.5, f"${row['precio_unit']:,.2f}", "B", 0, "R", fill)
        pdf.cell(25, 6.5, f"${importe_neto:,.2f}", "B", 1, "R", fill)

    tot = calcular_totales_carrito(carrito, flete, desc_extra_pct, precios_incluyen_iva)

    if pdf.get_y() > 205:
        pdf.add_page()

    pdf.ln(5)
    pdf.set_font("Arial", "B", 8.8)
    pdf.set_text_color(55, 55, 55)

    if tot["ahorro_nivel"] > 0:
        pdf.set_text_color(0, 130, 70)
        pdf.cell(138, 5.5, "AHORRO APLICADO POR VOLUMEN:", 0, 0, "R")
        pdf.cell(52, 5.5, f"${tot['ahorro_nivel']:,.2f} MXN", 0, 1, "R")
        pdf.set_text_color(55, 55, 55)

    if tot["total_desc_partidas"] > 0:
        pdf.set_text_color(200, 30, 30)
        pdf.cell(138, 5.5, "DESCUENTO ESPECIAL APLICADO:", 0, 0, "R")
        pdf.cell(52, 5.5, f"-${tot['total_desc_partidas']:,.2f} MXN", 0, 1, "R")
        pdf.set_text_color(55, 55, 55)

    if tot["desc_global_monto"] > 0:
        pdf.set_text_color(200, 30, 30)
        pdf.cell(138, 5.5, f"DESCUENTO ADICIONAL ({desc_extra_pct:.1f}%):", 0, 0, "R")
        pdf.cell(52, 5.5, f"-${tot['desc_global_monto']:,.2f} MXN", 0, 1, "R")
        pdf.set_text_color(55, 55, 55)

    if flete > 0:
        pdf.cell(138, 5.5, "FLETE / ENVIO:", 0, 0, "R")
        pdf.cell(52, 5.5, f"${flete:,.2f} MXN", 0, 1, "R")

    pdf.cell(138, 5.5, "SUBTOTAL:", 0, 0, "R")
    pdf.cell(52, 5.5, f"${tot['subtotal_sin_iva']:,.2f} MXN", 0, 1, "R")
    pdf.cell(138, 5.5, "IVA (16%):", 0, 0, "R")
    pdf.cell(52, 5.5, f"${tot['iva_monto']:,.2f} MXN", 0, 1, "R")

    pdf.ln(2)
    y_tot = pdf.get_y()
    pdf.set_fill_color(15, 60, 140)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 10.5)
    pdf.set_xy(88, y_tot)
    pdf.cell(58, 9, "TOTAL A PAGAR", 0, 0, "R", True)
    pdf.set_fill_color(0, 150, 255)
    pdf.cell(54, 9, f"${tot['total_final']:,.2f} MXN", 0, 1, "C", True)

    # Bloque Bancario Dinámico por Sucursal
    pdf.ln(6)
    if pdf.get_y() > 238:
        pdf.add_page()
    y_bank = pdf.get_y()
    pdf.set_fill_color(245, 248, 252)
    pdf.rect(10, y_bank, 190, 22, "F")
    pdf.set_fill_color(15, 60, 140)
    pdf.rect(10, y_bank, 2.2, 22, "F")

    pdf.set_xy(15, y_bank + 3)
    pdf.set_font("Arial", "B", 8.5)
    pdf.set_text_color(15, 60, 140)
    pdf.cell(180, 4.5, limpiar_pdf_txt(f"DATOS BANCARIOS PARA TRANSFERENCIA - SUCURSAL {sucursal_nombre}"), ln=True)
    pdf.set_x(15)
    pdf.set_font("Arial", "", 8)
    pdf.set_text_color(50, 50, 50)
    datos_banco = (
        f"Beneficiario: {suc_info['razon_social']}   |   Banco: {suc_info['banco']}\n"
        f"Cuenta: {suc_info['cuenta']}   |   CLABE Interbancaria: {suc_info['clabe']}"
    )
    pdf.multi_cell(180, 4.5, limpiar_pdf_txt(datos_banco))

    # Condiciones comerciales y notas
    pdf.set_y(y_bank + 26)
    pdf.set_font("Arial", "B", 8.2)
    pdf.set_text_color(15, 60, 140)
    pdf.cell(0, 4.5, "Condiciones Comerciales:", ln=True)
    pdf.set_font("Arial", "I", 7.8)
    pdf.set_text_color(85, 85, 85)
    condiciones = (
        "- Precios en Pesos Mexicanos (MXN), sujetos a cambios sin previo aviso.\n"
        "- Existencias sujetas a disponibilidad en sucursal al momento de confirmar pedido.\n"
        "- Enviar comprobante de pago al asesor para programar surtido o entrega."
    )
    pdf.multi_cell(0, 3.8, limpiar_pdf_txt(condiciones))

    if notas.strip():
        pdf.ln(2)
        pdf.set_font("Arial", "B", 8.2)
        pdf.set_text_color(0, 140, 230)
        pdf.cell(0, 4.5, "Observaciones:", ln=True)
        pdf.set_font("Arial", "", 8)
        pdf.set_text_color(55, 55, 55)
        pdf.multi_cell(0, 4, limpiar_pdf_txt(notas))

    return (
        pdf.output(dest="S").encode("latin-1"),
        tot["total_final"],
        tot["subtotal_sin_iva"],
        tot["iva_monto"],
        tot["ahorro_nivel"],
        tot["total_desc_partidas"]
    )

# --- ESTADO DE EDICIÓN ---
if "ed_folio" not in st.session_state:
    st.session_state["ed_folio"] = None
if "ed_fila_idx" not in st.session_state:
    st.session_state["ed_fila_idx"] = None
if "ed_sucursal" not in st.session_state:
    st.session_state["ed_sucursal"] = "IMAC"
if "ed_carrito" not in st.session_state:
    st.session_state["ed_carrito"] = []
if "ed_total_anterior" not in st.session_state:
    st.session_state["ed_total_anterior"] = 0.0
if "ed_pdf_bytes" not in st.session_state:
    st.session_state["ed_pdf_bytes"] = None
if "ed_pdf_nombre" not in st.session_state:
    st.session_state["ed_pdf_nombre"] = ""

def cargar_cotizacion_en_editor(fila, fila_idx):
    """Carga los 13 campos y el Datos_JSON (con descuentos topados al 10%) en el editor."""
    folio = str(fila[0]).strip()
    suc = str(fila[2]).strip() if len(fila) > 2 and str(fila[2]).strip() in CONFIG_SUCURSALES else "IMAC"
    asesor_f = str(fila[3]).strip() if len(fila) > 3 else ""
    cliente_f = str(fila[4]).strip() if len(fila) > 4 else ""
    tel_f = str(fila[5]).strip() if len(fila) > 5 else ""
    total_ant = limpiar_monto(fila[10]) if len(fila) > 10 else 0.0

    partidas = []
    flete_f = 0.0
    desc_f = 0.0
    notas_f = ""
    correo_f = ""
    vigencia_f = datetime.date.today() + datetime.timedelta(days=7)

    if len(fila) > 12 and str(fila[12]).strip():
        try:
            payload = json.loads(fila[12])
            partidas_raw = payload.get("partidas", [])
            for p in partidas_raw:
                clave_p = str(p.get("clave", "")).strip()
                cant_p = float(p.get("cantidad", 1.0))
                niv_p, prec_p, lista_p = calcular_nivel_y_precio(clave_p, cant_p, p.get("precio_unit", 0.0))
                desc_p_guardado = min(max(0.0, float(p.get("desc_pct", 0.0))), MAX_DESC_PCT) if niv_p == "NIVEL 1" else 0.0
                prod_nombre = CATALOGO_LIGEROS[clave_p]["producto"] if clave_p in CATALOGO_LIGEROS else str(p.get("producto", clave_p))
                cat_nombre = CATALOGO_LIGEROS[clave_p]["categoria"] if clave_p in CATALOGO_LIGEROS else str(p.get("categoria", "General"))
                partidas.append({
                    "clave": clave_p,
                    "producto": prod_nombre,
                    "categoria": cat_nombre,
                    "cantidad": cant_p,
                    "nivel": niv_p,
                    "precio_lista": lista_p,
                    "precio_unit": prec_p,
                    "desc_pct": desc_p_guardado
                })
            flete_f = max(0.0, float(payload.get("flete", 0.0)))
            desc_f = min(max(0.0, float(payload.get("desc_extra_pct", 0.0))), MAX_DESC_PCT)
            notas_f = str(payload.get("notas", ""))
            correo_f = str(payload.get("correo_cliente", ""))
            if payload.get("vigencia"):
                try:
                    vigencia_f = datetime.datetime.strptime(payload["vigencia"], "%d/%m/%Y").date()
                except Exception:
                    pass
        except Exception:
            partidas = []

    st.session_state["ed_folio"] = folio
    st.session_state["ed_fila_idx"] = fila_idx
    st.session_state["ed_sucursal"] = suc
    st.session_state["ed_carrito"] = partidas
    st.session_state["ed_total_anterior"] = total_ant
    st.session_state["ed_cliente"] = cliente_f
    st.session_state["ed_telefono"] = tel_f
    st.session_state["ed_correo"] = correo_f
    st.session_state["ed_asesor"] = asesor_f
    st.session_state["ed_vigencia"] = vigencia_f
    st.session_state["ed_flete"] = flete_f
    st.session_state["ed_desc_extra"] = desc_f
    st.session_state["ed_notas"] = notas_f
    st.session_state["ed_pdf_bytes"] = None
    st.session_state["ed_pdf_nombre"] = ""

# --- BARRA LATERAL INFORMATIVA (SIN PANEL DE REGLAS) ---
puede_ver_todas = (
    st.session_state.get("sucursal_asignada", "") == "TODAS"
    or st.session_state.get("role", "") in ["Admin", "Directivo"]
)
suc_usuario = st.session_state.get("sucursal_activa", "IMAC")

with st.sidebar:
    st.markdown(f"**🏢 Sucursal:** {suc_usuario}")
    st.caption(f"👤 {st.session_state.get('usuario', '')} ({st.session_state.get('role', '')})")
    alcance_txt = "Todas las sucursales" if puede_ver_todas else f"Solo {suc_usuario}"
    st.caption(f"🔎 Alcance consulta: **{alcance_txt}**")

# --- ENCABEZADO PRINCIPAL ---
col_logo, col_tit = st.columns([1, 5])
with col_logo:
    if os.path.exists("logo_imac_2026.png"):
        st.image(Image.open("logo_imac_2026.png"), use_container_width=True)
    else:
        st.markdown("### 🏢 IMAC")
with col_tit:
    st.title("Historial y Edición de Cotizaciones")
    st.caption("Consulta folios guardados, ajusta partidas o aplica descuentos (máx. 10%) y regenera el PDF limpio para el cliente")
st.markdown("---")

doc = conectar_sheets()
if not doc:
    st.error("⚠️ No se pudo conectar con Google Sheets. Verifica tus credenciales.")
    st.stop()

try:
    hoja_cot = doc.worksheet("Cotizaciones")
    todas_filas = hoja_cot.get_all_values()
except Exception as e:
    st.error(f"⚠️ No se pudo leer la pestaña 'Cotizaciones': {e}")
    st.stop()

# --- 1. CONSULTA Y FILTROS DEL HISTORIAL ---
registros_disponibles = []
for idx, fila in enumerate(todas_filas):
    if idx == 0 and len(fila) > 0 and "FOLIO" in str(fila[0]).upper():
        continue
    if len(fila) < 5 or not str(fila[0]).strip():
        continue
    suc_fila = str(fila[2]).strip()
    if not puede_ver_todas and suc_fila.upper() != suc_usuario.upper():
        continue
    registros_disponibles.append((idx + 1, fila))

registros_disponibles.reverse()

if not registros_disponibles:
    st.info("No hay cotizaciones guardadas todavía para tu sucursal.")
    st.stop()

# KPIs rápidos del historial visible
totales_hist = [limpiar_monto(f[10]) for _, f in registros_disponibles if len(f) > 10]
ticket_prom = (sum(totales_hist) / len(totales_hist)) if totales_hist else 0.0
m1, m2, m3 = st.columns(3)
m1.metric("Cotizaciones Registradas", f"{len(registros_disponibles)}")
m2.metric("Monto Total Cotizado", f"${sum(totales_hist):,.2f}")
m3.metric("Ticket Promedio", f"${ticket_prom:,.2f}")

st.markdown("---")
st.subheader("🔎 Buscar Cotización Guardada")

col_f1, col_f2 = st.columns([1.3, 2.7])
with col_f1:
    if puede_ver_todas:
        sucursales_en_datos = ["TODAS"] + sorted(list({str(f[2]).strip() for _, f in registros_disponibles if len(f) > 2}))
        filtro_suc = st.selectbox("Filtrar por Sucursal:", sucursales_en_datos)
    else:
        filtro_suc = suc_usuario
        st.text_input("Sucursal:", value=suc_usuario, disabled=True)
with col_f2:
    filtro_texto = st.text_input("Buscar por Folio, Cliente o Asesor:", placeholder="Ej. LIG-IMAC-0001-26 o Constructora...")

registros_filtrados = []
for fila_idx, fila in registros_disponibles:
    if filtro_suc != "TODAS" and str(fila[2]).strip().upper() != filtro_suc.upper():
        continue
    if filtro_texto.strip():
        q = filtro_texto.strip().upper()
        bloque_busq = f"{fila[0]} {fila[3]} {fila[4]}".upper()
        if q not in bloque_busq:
            continue
    registros_filtrados.append((fila_idx, fila))

if registros_filtrados:
    df_hist = pd.DataFrame([
        {
            "Folio": f[0],
            "Fecha": f[1] if len(f) > 1 else "",
            "Sucursal": f[2] if len(f) > 2 else "",
            "Asesor": f[3] if len(f) > 3 else "",
            "Cliente": f[4] if len(f) > 4 else "",
            "Partidas": f[6] if len(f) > 6 else "",
            "Total MXN": f"${limpiar_monto(f[10]):,.2f}" if len(f) > 10 else "$0.00"
        }
        for _, f in registros_filtrados
    ])
    st.dataframe(df_hist, use_container_width=True, hide_index=True)

    mapa_folios = {
        f"{f[0]} | {f[4]} (${limpiar_monto(f[10]):,.2f}) - {f[1]}": (fila_idx, f)
        for fila_idx, f in registros_filtrados
    }
    col_sel, col_btn = st.columns([3.2, 1.2])
    with col_sel:
        etiqueta_sel = st.selectbox("Selecciona el Folio a consultar / editar:", list(mapa_folios.keys()))
    with col_btn:
        st.write("")
        st.write("")
        if st.button("📥 Cargar para Editar", type="primary", use_container_width=True):
            idx_cargar, fila_cargar = mapa_folios[etiqueta_sel]
            cargar_cotizacion_en_editor(fila_cargar, idx_cargar)
            st.rerun()
else:
    st.warning("No se encontraron cotizaciones con esos criterios de búsqueda.")

# ==========================================================
# ✏️ SECCIÓN 2: EDITOR DE LA COTIZACIÓN CARGADA
# ==========================================================
if st.session_state.get("ed_folio"):
    folio_activo = st.session_state["ed_folio"]
    suc_folio = st.session_state["ed_sucursal"]
    suc_info_folio = CONFIG_SUCURSALES.get(suc_folio, CONFIG_SUCURSALES_DEFAULT["IMAC"])

    st.markdown("---")
    st.success(f"✏️ Editando Folio: **{folio_activo}** | Sucursal: **{suc_folio}** (Total original: **${st.session_state['ed_total_anterior']:,.2f} MXN**)")

    # --- Datos del Cliente ---
    c1, c2, c3, c4, c5 = st.columns([2.2, 1.3, 1.6, 1.5, 1.2])
    with c1: cliente_ed = st.text_input("Cliente / Razón Social", key="ed_cliente")
    with c2: telefono_ed = st.text_input("Teléfono", key="ed_telefono")
    with c3: correo_ed = st.text_input("Correo del Cliente", key="ed_correo")
    with c4: asesor_ed = st.text_input("Asesor Mostrador", key="ed_asesor")
    with c5: vigencia_ed = st.date_input("Válido hasta", key="ed_vigencia")

    # --- Agregar nuevas partidas del catálogo de 74 SKUs ---
    with st.expander("➕ Agregar Material Adicional al Folio", expanded=False):
        categorias_disp = ["TODAS"] + sorted(list({v["categoria"] for v in CATALOGO_LIGEROS.values()}))
        ef1, ef2 = st.columns([1.3, 2.7])
        with ef1:
            cat_add = st.selectbox("Familia:", categorias_disp, key="ed_cat_add")
        with ef2:
            busq_add = st.text_input("Buscar Clave o Nombre:", placeholder="Ej. TABLAROCA, POSTE 6.35...", key="ed_busq_add")

        prods_add = []
        for clv, inf in CATALOGO_LIGEROS.items():
            if cat_add != "TODAS" and inf["categoria"] != cat_add:
                continue
            if busq_add.strip():
                qa = busq_add.strip().upper()
                if qa not in clv.upper() and qa not in inf["producto"].upper():
                    continue
            prods_add.append(f"{clv} | {inf['producto']}")

        if prods_add:
            ep1, ep2, ep3, ep4 = st.columns([3.4, 1.0, 1.4, 1.2])
            with ep1:
                sel_add_str = st.selectbox("Producto a agregar:", prods_add, key="ed_sel_add")
                clv_add = sel_add_str.split(" | ")[0]
                inf_add = CATALOGO_LIGEROS[clv_add]
            with ep2:
                cant_add = st.number_input("Cantidad", min_value=1.0, value=10.0, step=1.0, key="ed_cant_add")
            with ep3:
                niv_a, prec_a, _ = calcular_nivel_y_precio(clv_add, cant_add)
                st.metric(f"{niv_a} (Interno)", f"${prec_a:,.2f}")
            with ep4:
                st.write("")
                st.write("")
                if st.button("➕ Añadir", type="primary", use_container_width=True, key="ed_btn_add"):
                    existente = next((x for x in st.session_state["ed_carrito"] if x["clave"] == clv_add), None)
                    if existente:
                        nueva_c = existente["cantidad"] + cant_add
                        n_niv, n_prec, n_list = calcular_nivel_y_precio(clv_add, nueva_c)
                        existente["cantidad"] = nueva_c
                        existente["nivel"] = n_niv
                        existente["precio_unit"] = n_prec
                        existente["precio_lista"] = n_list
                        if n_niv != "NIVEL 1":
                            existente["desc_pct"] = 0.0
                    else:
                        st.session_state["ed_carrito"].append({
                            "clave": clv_add,
                            "producto": inf_add["producto"],
                            "categoria": inf_add["categoria"],
                            "cantidad": cant_add,
                            "nivel": niv_a,
                            "precio_lista": inf_add["n1"],
                            "precio_unit": prec_a,
                            "desc_pct": 0.0
                        })
                    st.rerun()
        else:
            st.warning("Sin coincidencias en el catálogo.")

    # --- Edición directa de cantidades, descuento individual N1 (máx. 10%) y eliminación ---
    st.markdown("### 📋 Modificar Cantidades, Descuento en Partidas N1 (Máx. 10%) o Quitar Partidas")
    if not st.session_state["ed_carrito"]:
        st.warning("⚠️ Este folio no tiene partidas cargadas (o es un registro antiguo sin Datos_JSON). Agrega materiales arriba para reconstruirlo.")
    else:
        indice_a_eliminar = None
        h1, h2, h3, h4, h5, h6, h7 = st.columns([1.1, 2.7, 1.2, 0.7, 1.2, 1.2, 0.6])
        h1.caption("**Clave**")
        h2.caption("**Producto**")
        h3.caption("**Cantidad**")
        h4.caption("**Nivel**")
        h5.caption("**Desc. N1 (máx 10%)**")
        h6.caption("**Importe Neto**")
        h7.caption("**Quitar**")

        for idx, item in enumerate(st.session_state["ed_carrito"]):
            r1, r2, r3, r4, r5, r6, r7 = st.columns([1.1, 2.7, 1.2, 0.7, 1.2, 1.2, 0.6])
            with r1:
                st.write(f"`{item['clave']}`")
            with r2:
                st.write(item["producto"])
            with r3:
                nueva_qty = st.number_input(
                    "Cant.",
                    min_value=1.0,
                    value=float(item["cantidad"]),
                    step=1.0,
                    key=f"qty_{folio_activo}_{item['clave']}_{idx}",
                    label_visibility="collapsed"
                )
                niv_r, prec_r, list_r = calcular_nivel_y_precio(item["clave"], nueva_qty, item["precio_unit"])
                item["cantidad"] = nueva_qty
                item["nivel"] = niv_r
                item["precio_unit"] = prec_r
                item["precio_lista"] = list_r
            with r4:
                st.write(item["nivel"].replace("NIVEL ", "N"))
            with r5:
                # EXCEPCIÓN EN EDICIÓN: permite descuento % individual en partidas N1 con tope máximo de 10%
                if item["nivel"] == "NIVEL 1":
                    valor_inicial_desc = min(max(0.0, float(item.get("desc_pct", 0.0))), MAX_DESC_PCT)
                    desc_p_val = st.number_input(
                        "Desc %",
                        min_value=0.0,
                        max_value=MAX_DESC_PCT,
                        value=valor_inicial_desc,
                        step=0.5,
                        key=f"descp_{folio_activo}_{item['clave']}_{idx}",
                        label_visibility="collapsed"
                    )
                    item["desc_pct"] = desc_p_val
                else:
                    item["desc_pct"] = 0.0
                    st.caption("🔒 0%" if item["nivel"] == "NIVEL 3" else "—")
            with r6:
                imp_neto_fila = (item["cantidad"] * item["precio_unit"]) * (1.0 - item["desc_pct"] / 100.0)
                st.write(f"${imp_neto_fila:,.2f}")
            with r7:
                if st.button("🗑️", key=f"del_{folio_activo}_{item['clave']}_{idx}", help="Eliminar partida"):
                    indice_a_eliminar = idx

        if indice_a_eliminar is not None:
            st.session_state["ed_carrito"].pop(indice_a_eliminar)
            st.rerun()

        st.markdown("---")

        # --- Regla de Descuento Global (máx. 10%) vs. Excepción por Partida N1 (máx. 10%) ---
        tiene_nivel_3 = any(x["nivel"] == "NIVEL 3" for x in st.session_state["ed_carrito"])
        tiene_nivel_1 = any(x["nivel"] == "NIVEL 1" for x in st.session_state["ed_carrito"])

        if tiene_nivel_3:
            desc_extra_ed = 0.0
            a1, a3 = st.columns([1.4, 3.6])
            with a1:
                flete_ed = st.number_input("🚚 Flete / Envío ($ MXN)", min_value=0.0, step=100.0, key="ed_flete")
            with a3:
                notas_ed = st.text_input("Observaciones en PDF", key="ed_notas")
            if tiene_nivel_1:
                st.info("🏷️ **Excepción en Edición activa:** el descuento global permanece bloqueado por existir partidas en **Nivel 3 (Mayoreo)**, pero puedes aplicar hasta **10.0%** de descuento individual en la columna **Desc. N1 (máx 10%)** a cada partida en **Nivel 1**.")
            else:
                st.info("🔒 **Descuento adicional deshabilitado:** todas las partidas cuentan con tarifa preferencial de mayoreo.")
        else:
            a1, a2, a3 = st.columns([1.2, 1.2, 2.6])
            with a1:
                flete_ed = st.number_input("🚚 Flete / Envío ($ MXN)", min_value=0.0, step=100.0, key="ed_flete")
            with a2:
                desc_extra_ed = st.number_input("🏷️ Descuento Adicional Global (%, máx 10%)", min_value=0.0, max_value=MAX_DESC_PCT, step=0.5, key="ed_desc_extra")
            with a3:
                notas_ed = st.text_input("Observaciones en PDF", key="ed_notas")

        # --- Totales en tiempo real y comparativa vs. total anterior ---
        tot_ed = calcular_totales_carrito(st.session_state["ed_carrito"], flete_ed, desc_extra_ed, PRECIOS_INCLUYEN_IVA)
        diferencia_total = tot_ed["total_final"] - st.session_state["ed_total_anterior"]

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Subtotal", f"${tot_ed['subtotal_sin_iva']:,.2f}")
        k2.metric("IVA (16%)", f"${tot_ed['iva_monto']:,.2f}")
        k3.metric("Ahorro Volumen", f"${tot_ed['ahorro_nivel']:,.2f}")
        k4.metric("Desc. Partidas N1", f"-${tot_ed['total_desc_partidas']:,.2f}")
        k5.metric("NUEVO TOTAL MXN", f"${tot_ed['total_final']:,.2f}", f"{diferencia_total:+,.2f} vs original")

        enviar_correo_ed = st.checkbox("📧 Reenviar copia del PDF actualizado por correo", value=False, key="ed_chk_mail")

        if st.button(f"💾 GUARDAR CAMBIOS EN {folio_activo} Y REGENERAR PDF", type="primary", use_container_width=True):
            with st.spinner(f"Actualizando {folio_activo} en Google Sheets y regenerando PDF..."):
                cliente_final = cliente_ed.strip() if cliente_ed.strip() else "PUBLICO EN GENERAL"

                pdf_bytes, tot_pdf, sub_pdf, iva_pdf, ahorr_pdf, desc_n1_pdf = generar_pdf_mostrador(
                    folio_activo, suc_folio, suc_info_folio, cliente_final, telefono_ed,
                    correo_ed, asesor_ed, vigencia_ed, st.session_state["ed_carrito"],
                    flete_ed, desc_extra_ed, PRECIOS_INCLUYEN_IVA, notas_ed
                )

                fecha_act = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
                resumen_partidas = " / ".join([
                    f"{x['cantidad']:g}x {x['clave']} ({x['nivel']}" + (f" -{x['desc_pct']:g}%" if x.get("desc_pct", 0.0) > 0 else "") + ")"
                    for x in st.session_state["ed_carrito"]
                ])
                payload_json = json.dumps({
                    "partidas": st.session_state["ed_carrito"],
                    "flete": flete_ed,
                    "desc_extra_pct": desc_extra_ed,
                    "precios_incluyen_iva": PRECIOS_INCLUYEN_IVA,
                    "notas": notas_ed,
                    "correo_cliente": correo_ed,
                    "vigencia": vigencia_ed.strftime("%d/%m/%Y")
                }, ensure_ascii=False)

                fila_actualizada = [
                    folio_activo, fecha_act, suc_folio, asesor_ed.upper(),
                    cliente_final.upper(), telefono_ed, len(st.session_state["ed_carrito"]),
                    resumen_partidas, round(sub_pdf, 2), round(iva_pdf, 2),
                    round(tot_pdf, 2), round(ahorr_pdf, 2), payload_json
                ]

                ok_upd, msg_upd = actualizar_fila_cotizacion(
                    hoja_cot, folio_activo, st.session_state["ed_fila_idx"], fila_actualizada
                )

                if ok_upd:
                    registrar_bitacora(
                        doc,
                        "Edición Cotizaciones",
                        f"Actualizó {folio_activo} ({suc_folio}) de ${st.session_state['ed_total_anterior']:,.2f} a ${tot_pdf:,.2f} MXN ({len(st.session_state['ed_carrito'])} partidas, desc. N1 ${desc_n1_pdf:,.2f}, desc. global {desc_extra_ed:.1f}%)"
                    )
                    st.session_state["ed_total_anterior"] = tot_pdf
                    nombre_pdf = f"Cotizacion_{folio_activo}_{cliente_final.replace(' ', '_')}.pdf"
                    st.session_state["ed_pdf_bytes"] = pdf_bytes
                    st.session_state["ed_pdf_nombre"] = nombre_pdf

                    if enviar_correo_ed:
                        dest = suc_info_folio.get("correo", "comercial@grupo-imac.com")
                        if correo_ed.strip():
                            dest = f"{dest}, {correo_ed.strip()}"
                        ok_mail, msg_mail = enviar_respaldo_correo(
                            pdf_bytes, nombre_pdf, folio_activo, suc_folio,
                            cliente_final, asesor_ed, tot_pdf, dest
                        )
                        if ok_mail:
                            st.info(f"📧 PDF actualizado enviado a: {dest}")
                        else:
                            st.warning(f"⚠️ No se pudo enviar el correo: {msg_mail}")

                    st.success(f"✅ Folio **{folio_activo}** actualizado correctamente ({msg_upd}) sin duplicar filas.")
                else:
                    st.error(f"⚠️ No se pudo actualizar en Google Sheets: {msg_upd}")

        if st.session_state.get("ed_pdf_bytes"):
            st.download_button(
                label=f"⬇️ DESCARGAR PDF ACTUALIZADO ({folio_activo})",
                data=st.session_state["ed_pdf_bytes"],
                file_name=st.session_state["ed_pdf_nombre"],
                mime="application/pdf",
                use_container_width=True
            )
