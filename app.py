import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import datetime
import json
import os
from PIL import Image

# --- CONFIGURACIÓN DE PÁGINA ---
icono_nav = "logo_imac_2026.png" if os.path.exists("logo_imac_2026.png") else "🏢"
st.set_page_config(
    page_title="Acceso | Cotizador Sistemas Ligeros IMAC",
    page_icon=icono_nav,
    layout="centered"
)

# --- PERFILES MAESTROS DE LAS 6 SUCURSALES DE VERACRUZ ---
# (Estos campos de dirección y cuenta bancaria los iremos afinando poco a poco en la Fase 4)
CONFIG_SUCURSALES = {
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
            return None, "Faltan variables GOOGLE_CREDENTIALS o ID_EXCEL en Streamlit Secrets."

        if isinstance(credenciales_raw, str):
            credenciales_dic = json.loads(credenciales_raw)
        else:
            credenciales_dic = dict(credenciales_raw)

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(credenciales_dic, scopes=scopes)
        cliente = gspread.authorize(creds)
        doc = cliente.open_by_key(id_excel)
        return doc, "OK"
    except Exception as e:
        return None, str(e)

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

def validar_usuario(doc, user_input, pass_input):
    try:
        hoja_users = doc.worksheet("Usuarios")
        registros = hoja_users.get_all_records()
        u_clean = user_input.strip().lower()
        p_clean = pass_input.strip()

        for fila in registros:
            fila_norm = {str(k).strip().lower(): str(v).strip() for k, v in fila.items()}
            if fila_norm.get("usuario", "").lower() == u_clean and fila_norm.get("password", "") == p_clean:
                rol = fila_norm.get("rol", "Asesor")
                sucursal = fila_norm.get("sucursal", "IMAC").upper()
                return True, rol, sucursal
        return False, None, None
    except Exception as e:
        st.error(f"⚠️ Error al leer la pestaña 'Usuarios': {e}")
        return False, None, None

# --- INICIALIZACIÓN DE SESIÓN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "usuario" not in st.session_state:
    st.session_state["usuario"] = ""
if "role" not in st.session_state:
    st.session_state["role"] = ""
if "sucursal_asignada" not in st.session_state:
    st.session_state["sucursal_asignada"] = "IMAC"
if "sucursal_activa" not in st.session_state:
    st.session_state["sucursal_activa"] = "IMAC"

# Guardamos la configuración de sucursales en session_state para compartirla con pages/
st.session_state["config_sucursales"] = CONFIG_SUCURSALES

# --- ENCABEZADO VISUAL ---
col_l, col_t = st.columns([1, 4])
with col_l:
    if os.path.exists("logo_imac_2026.png"):
        st.image(Image.open("logo_imac_2026.png"), use_container_width=True)
    elif os.path.exists("logo_tarc.png"):
        st.image(Image.open("logo_tarc.png"), use_container_width=True)
    else:
        st.markdown("### 🏢 IMAC")
with col_t:
    st.title("Cotizador Sistemas Ligeros")
    st.caption("Plataforma Comercial de Mostrador — Zona Veracruz")

st.markdown("---")

doc, estado_conexion = conectar_sheets()

# ==========================================
# 🔐 PANTALLA DE INICIO DE SESIÓN
# ==========================================
if not st.session_state["logged_in"]:
    if not doc:
        st.warning(f"🔌 Conexión pendiente con Google Sheets: {estado_conexion}")
        st.info("Continúa a la **Fase 3** en Streamlit Cloud para pegar tus `Secrets` (`GOOGLE_CREDENTIALS` e `ID_EXCEL`).")
    else:
        st.subheader("🔐 Inicio de Sesión")
        with st.form("form_login_ligeros"):
            u_in = st.text_input("Usuario", placeholder="Ej. wilbert")
            p_in = st.text_input("Contraseña", type="password")
            btn_login = st.form_submit_button("Ingresar al Sistema", type="primary", use_container_width=True)

            if btn_login:
                ok, rol_db, suc_db = validar_usuario(doc, u_in, p_in)
                if ok:
                    st.session_state["logged_in"] = True
                    st.session_state["usuario"] = u_in.strip()
                    st.session_state["role"] = rol_db
                    st.session_state["sucursal_asignada"] = suc_db
                    if suc_db in CONFIG_SUCURSALES:
                        st.session_state["sucursal_activa"] = suc_db
                    else:
                        st.session_state["sucursal_activa"] = "IMAC"
                    registrar_bitacora(doc, "Login", f"Inició sesión (Sucursal asignada: {suc_db})")
                    st.rerun()
                else:
                    st.error("🚫 Usuario o contraseña incorrectos.")

# ==========================================
# ✅ PANEL DE BIENVENIDA Y DIAGNÓSTICO
# ==========================================
else:
    st.success(f"Bienvenido, **{st.session_state['usuario']}** | Perfil: **{st.session_state['role']}**")

    # Selector de sucursal solo si tiene acceso a TODAS o es Admin/Directivo
    puede_cambiar = (
        st.session_state["sucursal_asignada"] == "TODAS"
        or st.session_state["role"] in ["Admin", "Directivo"]
    )
    lista_suc = list(CONFIG_SUCURSALES.keys())

    if puede_cambiar:
        idx_actual = lista_suc.index(st.session_state["sucursal_activa"]) if st.session_state["sucursal_activa"] in lista_suc else 0
        nueva_suc = st.selectbox("🏢 Sucursal Activa para Cotizar:", lista_suc, index=idx_actual)
        st.session_state["sucursal_activa"] = nueva_suc
    else:
        st.info(f"🏢 Sucursal asignada a tu cuenta: **{st.session_state['sucursal_activa']}**")

    suc_info = CONFIG_SUCURSALES[st.session_state["sucursal_activa"]]

    # Diagnóstico de las 3 pestañas del Google Sheet
    st.markdown("### 📡 Estado de la Base de Datos")
    pestanas_req = ["Usuarios", "Cotizaciones", "Bitacora_Movimientos"]
    cols_diag = st.columns(3)
    pestanas_ok = 0
    for idx_p, nombre_p in enumerate(pestanas_req):
        try:
            doc.worksheet(nombre_p)
            cols_diag[idx_p].metric(nombre_p, "Conectada", "OK")
            pestanas_ok += 1
        except Exception:
            cols_diag[idx_p].metric(nombre_p, "Falta", "Revisar", delta_color="inverse")

    st.markdown("### 🏦 Perfil Fiscal y Bancario de la Sucursal Activa")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Razón Social:** {suc_info['razon_social']}")
        st.write(f"**Dirección:** {suc_info['direccion']}")
        st.write(f"**Teléfono:** {suc_info['telefono']}")
    with c2:
        st.write(f"**Banco:** {suc_info['banco']}")
        st.write(f"**Cuenta:** {suc_info['cuenta']}")
        st.write(f"**CLABE:** {suc_info['clabe']}")

    st.info("👉 Cuando completes la Fase 3 y confirmes que las **3/3 pestañas** marcan `OK`, agregaremos la carpeta `pages/` con el cotizador de los 74 productos y el nuevo diseño PDF.")

    if st.button("🚪 Cerrar Sesión"):
        registrar_bitacora(doc, "Login", "Cerró sesión")
        st.session_state["logged_in"] = False
        st.rerun()
