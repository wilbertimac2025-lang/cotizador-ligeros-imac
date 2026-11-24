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
    page_title="Cotizador Mostrador | Sistemas Ligeros IMAC",
    page_icon=icono_nav,
    layout="wide"
)

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

def obtener_nuevo_folio(doc, prefijo):
    anio = datetime.datetime.now().strftime("%y")
    try:
        if doc:
            hoja = doc.worksheet("Cotizaciones")
            filas = hoja.get_all_values()
            consecutivo = len(filas) if len(filas) > 0 else 1
            return f"LIG-{prefijo}-{consecutivo:04d}-{anio}"
    except Exception:
        pass
    return f"LIG-{prefijo}-{datetime.datetime.now().strftime('%H%M')}-{anio}"

def enviar_respaldo_correo(pdf_bytes, nombre_archivo, folio, sucursal_nombre, cliente, asesor, total_mxn, correo_dest):
    try:
        remitente = obtener_secreto("CORREO_BOT")
        password = obtener_secreto("PASS_BOT")
        if not remitente or not password:
            return False, "Faltan CORREO_BOT o PASS_BOT en Secrets."

        msg = EmailMessage()
        msg["Subject"] = f"COTIZACION MOSTRADOR {folio} | {sucursal_nombre} - {cliente}"
        msg["From"] = remitente
        msg["To"] = correo_dest
        msg.set_content(
            f"Se ha generado una cotización de Sistemas Ligeros en mostrador.\n\n"
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

def limpiar_pdf_txt(texto):
    return str(texto).encode("latin-1", "replace").decode("latin-1")

def calcular_nivel_y_precio(clave, cantidad, modo_nivel, min_n2, min_n3):
    item = CATALOGO_LIGEROS[clave]
    if modo_nivel == "Automático por Volumen":
        if cantidad >= min_n3:
            return "NIVEL 3", item["n3"]
        elif cantidad >= min_n2:
            return "NIVEL 2", item["n2"]
        return "NIVEL 1", item["n1"]
    elif modo_nivel == "Nivel 1 (Mostrador)":
        return "NIVEL 1", item["n1"]
    elif modo_nivel == "Nivel 2 (Medio Mayoreo)":
        return "NIVEL 2", item["n2"]
    return "NIVEL 3", item["n3"]

# --- DISEÑO PDF CORPORATIVO MODERNO (OPTIMIZADO PARA logo_imac_2026.png) ---
class PDFMostrador(FPDF):
    def __init__(self, suc_nombre, folio_txt, fecha_txt):
        super().__init__()
        self.suc_nombre = suc_nombre
        self.folio_txt = folio_txt
        self.fecha_txt = fecha_txt

    def header(self):
        # Franja superior azul corporativo
        self.set_fill_color(15, 60, 140)
        self.rect(0, 0, 210, 4, "F")

        # Logo corporativo IMAC 2026
        if os.path.exists("logo_imac_2026.png"):
            self.image("logo_imac_2026.png", x=10, y=8, w=32)
            x_titulo = 46
        else:
            x_titulo = 10

        self.set_xy(x_titulo, 10)
        self.set_font("Arial", "B", 14)
        self.set_text_color(15, 60, 140)
        self.cell(95, 6, "GRUPO IMAC", ln=False, align="L")

        # Folio y fecha en esquina derecha
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

        # Línea divisoria limpia
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

    # Encabezado de tabla
    def dibujar_encabezado_tabla():
        pdf.set_fill_color(15, 60, 140)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 8)
        pdf.cell(26, 7, "CLAVE", 0, 0, "C", True)
        pdf.cell(85, 7, "DESCRIPCION DEL MATERIAL", 0, 0, "L", True)
        pdf.cell(16, 7, "CANT.", 0, 0, "C", True)
        pdf.cell(15, 7, "NIVEL", 0, 0, "C", True)
        pdf.cell(23, 7, "P. UNIT.", 0, 0, "R", True)
        pdf.cell(25, 7, "IMPORTE", 0, 1, "R", True)

    dibujar_encabezado_tabla()

    subtotal_bruto = 0.0
    ahorro_nivel = 0.0

    for idx, row in enumerate(carrito):
        if pdf.get_y() > 258:
            pdf.add_page()
            dibujar_encabezado_tabla()

        fill = (idx % 2 == 1)
        pdf.set_fill_color(246, 249, 253)
        pdf.set_draw_color(225, 230, 238)
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Arial", "", 7.5)

        importe = row["cantidad"] * row["precio_unit"]
        subtotal_bruto += importe
        ahorro_nivel += max(0.0, (row["precio_lista"] - row["precio_unit"]) * row["cantidad"])

        pdf.cell(26, 6.5, limpiar_pdf_txt(row["clave"][:14]), "B", 0, "C", fill)
        pdf.cell(85, 6.5, limpiar_pdf_txt(row["producto"][:49]), "B", 0, "L", fill)
        pdf.cell(16, 6.5, f"{row['cantidad']:g}", "B", 0, "C", fill)
        pdf.cell(15, 6.5, limpiar_pdf_txt(row["nivel"].replace("NIVEL ", "N")), "B", 0, "C", fill)
        pdf.cell(23, 6.5, f"${row['precio_unit']:,.2f}", "B", 0, "R", fill)
        pdf.cell(25, 6.5, f"${importe:,.2f}", "B", 1, "R", fill)

    # Totales financieros
    descuento_extra_monto = subtotal_bruto * (desc_extra_pct / 100.0)
    base_neta = subtotal_bruto - descuento_extra_monto + flete

    if precios_incluyen_iva:
        total_final = base_neta
        subtotal_sin_iva = total_final / 1.16
        iva_monto = total_final - subtotal_sin_iva
    else:
        subtotal_sin_iva = base_neta
        iva_monto = subtotal_sin_iva * 0.16
        total_final = subtotal_sin_iva + iva_monto

    if pdf.get_y() > 210:
        pdf.add_page()

    pdf.ln(5)
    pdf.set_font("Arial", "B", 8.8)
    pdf.set_text_color(55, 55, 55)

    if ahorro_nivel > 0:
        pdf.set_text_color(0, 130, 70)
        pdf.cell(138, 5.5, "AHORRO APLICADO POR VOLUMEN:", 0, 0, "R")
        pdf.cell(52, 5.5, f"${ahorro_nivel:,.2f} MXN", 0, 1, "R")
        pdf.set_text_color(55, 55, 55)

    if descuento_extra_monto > 0:
        pdf.set_text_color(200, 30, 30)
        pdf.cell(138, 5.5, f"DESCUENTO ADICIONAL ({desc_extra_pct:.1f}%):", 0, 0, "R")
        pdf.cell(52, 5.5, f"-${descuento_extra_monto:,.2f} MXN", 0, 1, "R")
        pdf.set_text_color(55, 55, 55)

    if flete > 0:
        pdf.cell(138, 5.5, "FLETE / ENVIO:", 0, 0, "R")
        pdf.cell(52, 5.5, f"${flete:,.2f} MXN", 0, 1, "R")

    pdf.cell(138, 5.5, "SUBTOTAL:", 0, 0, "R")
    pdf.cell(52, 5.5, f"${subtotal_sin_iva:,.2f} MXN", 0, 1, "R")
    pdf.cell(138, 5.5, "IVA (16%):", 0, 0, "R")
    pdf.cell(52, 5.5, f"${iva_monto:,.2f} MXN", 0, 1, "R")

    pdf.ln(2)
    y_tot = pdf.get_y()
    pdf.set_fill_color(15, 60, 140)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 10.5)
    pdf.set_xy(88, y_tot)
    pdf.cell(58, 9, "TOTAL A PAGAR", 0, 0, "R", True)
    pdf.set_fill_color(0, 150, 255)
    pdf.cell(54, 9, f"${total_final:,.2f} MXN", 0, 1, "C", True)

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

    return pdf.output(dest="S").encode("latin-1"), total_final, subtotal_sin_iva, iva_monto, ahorro_nivel

# --- ESTADO DEL CARRITO ---
if "carrito_ligeros" not in st.session_state:
    st.session_state["carrito_ligeros"] = []

# --- BARRA LATERAL: SUCURSAL Y REGLAS DE VOLUMEN ---
with st.sidebar:
    st.header("⚙️ Reglas de Mostrador")
    puede_cambiar = (
        st.session_state.get("sucursal_asignada", "") == "TODAS"
        or st.session_state.get("role", "") in ["Admin", "Directivo"]
    )
    lista_suc = list(CONFIG_SUCURSALES.keys())
    suc_actual = st.session_state.get("sucursal_activa", "IMAC")
    if suc_actual not in lista_suc:
        suc_actual = lista_suc[0]

    if puede_cambiar:
        sucursal_sel = st.selectbox("🏢 Sucursal Activa:", lista_suc, index=lista_suc.index(suc_actual))
        st.session_state["sucursal_activa"] = sucursal_sel
    else:
        sucursal_sel = suc_actual
        st.info(f"🏢 Sucursal: **{sucursal_sel}**")

    modo_nivel = st.selectbox(
        "Asignación de Nivel:",
        ["Automático por Volumen", "Nivel 1 (Mostrador)", "Nivel 2 (Medio Mayoreo)", "Nivel 3 (Mayoreo)"]
    )
    min_n2 = st.number_input("Mínimo pzas para Nivel 2:", min_value=2, value=50, step=5)
    min_n3 = st.number_input("Mínimo pzas para Nivel 3:", min_value=int(min_n2) + 1, value=100, step=10)
    precios_incluyen_iva = st.toggle("¿Precios del catálogo incluyen IVA?", value=True)
    enviar_correo_chk = st.checkbox("Enviar copia PDF por correo", value=False)
    st.markdown("---")
    st.caption(f"📦 Catálogo activo: **{len(CATALOGO_LIGEROS)} SKUs** | 👤 **{st.session_state.get('usuario', '')}**")

suc_info_activa = CONFIG_SUCURSALES[sucursal_sel]

# --- ENCABEZADO PRINCIPAL ---
col_logo, col_tit = st.columns([1, 5])
with col_logo:
    if os.path.exists("logo_imac_2026.png"):
        st.image(Image.open("logo_imac_2026.png"), use_container_width=True)
    else:
        st.markdown("### 🏢 IMAC")
with col_tit:
    st.title(f"Cotizador Mostrador — {sucursal_sel}")
    st.caption(f"{suc_info_activa['nombre_oficial']} | {suc_info_activa['razon_social']}")
st.markdown("---")

# --- 1. DATOS DEL CLIENTE ---
c1, c2, c3, c4, c5 = st.columns([2.2, 1.3, 1.6, 1.5, 1.2])
with c1: cliente = st.text_input("Cliente / Razón Social", placeholder="Ej. Constructora del Golfo")
with c2: telefono = st.text_input("Teléfono", placeholder="229...")
with c3: correo_cli = st.text_input("Correo del Cliente (Opcional)", placeholder="cliente@correo.com")
with c4: asesor = st.text_input("Asesor Mostrador", value=st.session_state.get("usuario", "MOSTRADOR").upper())
with c5: fecha_validez = st.date_input("Válido hasta", value=datetime.date.today() + datetime.timedelta(days=7))

st.markdown("---")

# --- 2. SELECTOR DE PRODUCTOS Y CARRITO ---
st.subheader("🛒 Agregar Materiales al Carrito")

categorias_disponibles = ["TODAS"] + sorted(list({v["categoria"] for v in CATALOGO_LIGEROS.values()}))
f1, f2 = st.columns([1.3, 2.7])
with f1:
    cat_filtro = st.selectbox("Filtrar por Familia:", categorias_disponibles)
with f2:
    busqueda = st.text_input("🔍 Buscar por Clave o Descripción:", placeholder="Ej. TABLAROCA, DUROCK, POSTE 6.35, US010604...")

productos_filtrados = []
for clave, info in CATALOGO_LIGEROS.items():
    if cat_filtro != "TODAS" and info["categoria"] != cat_filtro:
        continue
    if busqueda.strip():
        q = busqueda.strip().upper()
        if q not in clave.upper() and q not in info["producto"].upper():
            continue
    productos_filtrados.append(f"{clave} | {info['producto']}")

if productos_filtrados:
    p1, p2, p3, p4 = st.columns([3.4, 1.0, 1.4, 1.2])
    with p1:
        sel_prod_str = st.selectbox("Producto:", productos_filtrados)
        clave_sel = sel_prod_str.split(" | ")[0]
        info_sel = CATALOGO_LIGEROS[clave_sel]
        st.caption(
            f"Tabulador MXN — **N1:** ${info_sel['n1']:,.2f} | "
            f"**N2:** ${info_sel['n2']:,.2f} | **N3:** ${info_sel['n3']:,.2f}"
        )
    with p2:
        cant_sel = st.number_input("Cantidad", min_value=1.0, value=10.0, step=1.0)
    with p3:
        nivel_calc, precio_calc = calcular_nivel_y_precio(clave_sel, cant_sel, modo_nivel, min_n2, min_n3)
        ahorro_unit = info_sel["n1"] - precio_calc
        delta_txt = f"-${ahorro_unit:,.2f}/u" if ahorro_unit > 0 else "Precio Lista"
        st.metric(f"{nivel_calc}", f"${precio_calc:,.2f}", delta_txt)
    with p4:
        st.write("")
        st.write("")
        if st.button("➕ Agregar", type="primary", use_container_width=True):
            existente = next((x for x in st.session_state["carrito_ligeros"] if x["clave"] == clave_sel), None)
            if existente:
                nueva_cant = existente["cantidad"] + cant_sel
                niv_n, prec_n = calcular_nivel_y_precio(clave_sel, nueva_cant, modo_nivel, min_n2, min_n3)
                existente["cantidad"] = nueva_cant
                existente["nivel"] = niv_n
                existente["precio_unit"] = prec_n
            else:
                st.session_state["carrito_ligeros"].append({
                    "clave": clave_sel,
                    "producto": info_sel["producto"],
                    "categoria": info_sel["categoria"],
                    "cantidad": cant_sel,
                    "nivel": nivel_calc,
                    "precio_lista": info_sel["n1"],
                    "precio_unit": precio_calc
                })
            st.rerun()
else:
    st.warning("No se encontraron materiales con ese filtro.")

# --- 3. CARRITO ACTIVO Y RESUMEN FINANCIERO ---
if st.session_state["carrito_ligeros"]:
    st.markdown("### 📋 Partidas en la Cotización")
    for item in st.session_state["carrito_ligeros"]:
        niv, prec = calcular_nivel_y_precio(item["clave"], item["cantidad"], modo_nivel, min_n2, min_n3)
        item["nivel"] = niv
        item["precio_unit"] = prec

    df_carrito = pd.DataFrame([
        {
            "Clave": x["clave"],
            "Producto": x["producto"],
            "Cantidad": x["cantidad"],
            "Nivel": x["nivel"],
            "P. Lista": f"${x['precio_lista']:,.2f}",
            "P. Aplicado": f"${x['precio_unit']:,.2f}",
            "Importe": f"${x['cantidad'] * x['precio_unit']:,.2f}"
        }
        for x in st.session_state["carrito_ligeros"]
    ])
    st.dataframe(df_carrito, use_container_width=True, hide_index=True)

    col_del1, col_del2 = st.columns([2.2, 1.3])
    with col_del1:
        clave_quitar = st.selectbox(
            "Seleccionar partida para eliminar:",
            ["Selecciona..."] + [f"{x['clave']} | {x['producto']}" for x in st.session_state["carrito_ligeros"]]
        )
    with col_del2:
        st.write("")
        st.write("")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🗑️ Quitar", use_container_width=True) and clave_quitar != "Selecciona...":
                c_rm = clave_quitar.split(" | ")[0]
                st.session_state["carrito_ligeros"] = [x for x in st.session_state["carrito_ligeros"] if x["clave"] != c_rm]
                st.rerun()
        with b2:
            if st.button("🧹 Vaciar Todo", use_container_width=True):
                st.session_state["carrito_ligeros"] = []
                st.rerun()

    st.markdown("---")
    a1, a2, a3 = st.columns([1.2, 1.2, 2.6])
    with a1: flete = st.number_input("🚚 Flete / Envío ($ MXN)", min_value=0.0, value=0.0, step=100.0)
    with a2: desc_extra_pct = st.number_input("🏷️ Descuento Adicional (%)", min_value=0.0, max_value=30.0, value=0.0, step=0.5)
    with a3: notas = st.text_input("Observaciones en PDF", placeholder="Ej. Entrega en planta baja, pago contra entrega...")

    subtotal_bruto = sum(x["cantidad"] * x["precio_unit"] for x in st.session_state["carrito_ligeros"])
    ahorro_vol = sum(max(0.0, (x["precio_lista"] - x["precio_unit"]) * x["cantidad"]) for x in st.session_state["carrito_ligeros"])
    desc_adicional = subtotal_bruto * (desc_extra_pct / 100.0)
    base_neta = subtotal_bruto - desc_adicional + flete

    if precios_incluyen_iva:
        total_calc = base_neta
        sub_calc = total_calc / 1.16
        iva_calc = total_calc - sub_calc
    else:
        sub_calc = base_neta
        iva_calc = sub_calc * 0.16
        total_calc = sub_calc + iva_calc

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Subtotal", f"${sub_calc:,.2f}")
    k2.metric("IVA (16%)", f"${iva_calc:,.2f}")
    k3.metric("Ahorro por Volumen", f"${ahorro_vol:,.2f}")
    k4.metric("TOTAL MXN", f"${total_calc:,.2f}")

    if st.button("📄 GENERAR COTIZACIÓN PDF Y GUARDAR EN DRIVE", type="primary", use_container_width=True):
        with st.spinner("Generando folio, registrando en Google Sheets y ensamblando PDF..."):
            doc = conectar_sheets()
            prefijo = suc_info_activa.get("prefijo_folio", "IMAC")
            folio_actual = obtener_nuevo_folio(doc, prefijo)
            cliente_final = cliente.strip() if cliente.strip() else "PUBLICO EN GENERAL"

            pdf_bytes, tot_pdf, sub_pdf, iva_pdf, ahorr_pdf = generar_pdf_mostrador(
                folio_actual, sucursal_sel, suc_info_activa, cliente_final, telefono,
                correo_cli, asesor, fecha_validez, st.session_state["carrito_ligeros"],
                flete, desc_extra_pct, precios_incluyen_iva, notas
            )

            # Guardar en las 13 columnas de la pestaña Cotizaciones
            if doc:
                try:
                    hoja_cot = doc.worksheet("Cotizaciones")
                    fecha_reg = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
                    resumen_partidas = " / ".join(
                        [f"{x['cantidad']:g}x {x['clave']} ({x['nivel']})" for x in st.session_state["carrito_ligeros"]]
                    )
                    payload_json = json.dumps({
                        "partidas": st.session_state["carrito_ligeros"],
                        "flete": flete,
                        "desc_extra_pct": desc_extra_pct,
                        "precios_incluyen_iva": precios_incluyen_iva,
                        "notas": notas,
                        "correo_cliente": correo_cli,
                        "vigencia": fecha_validez.strftime("%d/%m/%Y")
                    }, ensure_ascii=False)

                    hoja_cot.append_row([
                        folio_actual, fecha_reg, sucursal_sel, asesor.upper(),
                        cliente_final.upper(), telefono, len(st.session_state["carrito_ligeros"]),
                        resumen_partidas, round(sub_pdf, 2), round(iva_pdf, 2),
                        round(tot_pdf, 2), round(ahorr_pdf, 2), payload_json
                    ])
                    registrar_bitacora(
                        doc,
                        "Cotizador Mostrador",
                        f"Generó cotización {folio_actual} ({sucursal_sel}) por ${tot_pdf:,.2f} MXN ({len(st.session_state['carrito_ligeros'])} partidas)"
                    )
                except Exception as e:
                    st.warning(f"⚠️ PDF creado, pero ocurrió un error al guardar en Google Sheets: {e}")

            nombre_pdf = f"Cotizacion_{folio_actual}_{cliente_final.replace(' ', '_')}.pdf"

            if enviar_correo_chk:
                dest = suc_info_activa.get("correo", "comercial@grupo-imac.com")
                if correo_cli.strip():
                    dest = f"{dest}, {correo_cli.strip()}"
                ok_mail, msg_mail = enviar_respaldo_correo(
                    pdf_bytes, nombre_pdf, folio_actual, sucursal_sel,
                    cliente_final, asesor, tot_pdf, dest
                )
                if ok_mail:
                    st.info(f"📧 Copia enviada correctamente a: {dest}")
                else:
                    st.warning(f"⚠️ No se pudo enviar el correo: {msg_mail}")

        st.success(f"✅ Cotización **{folio_actual}** guardada y lista para entrega.")
        st.download_button(
            label="⬇️ DESCARGAR COTIZACIÓN PDF",
            data=pdf_bytes,
            file_name=nombre_pdf,
            mime="application/pdf",
            use_container_width=True
        )
else:
    st.info("Selecciona uno o más materiales arriba para armar la cotización de mostrador.")
