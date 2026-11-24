import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import datetime
import json
import os
import unicodedata
from PIL import Image

# --- CONFIGURACIÓN DE PÁGINA ---
icono_nav = "logo_imac_2026.png" if os.path.exists("logo_imac_2026.png") else "🏢"
st.set_page_config(
    page_title="Acceso | Cotizador Sistemas Ligeros IMAC",
    page_icon=icono_nav,
    layout="centered"
)

# --- PERFILES MAESTROS DE LAS 6 SUCURSALES DE VERACRUZ ---
# Sucursal IMAC (Matriz) ya cargada con los datos reales de tu formato oficial.
# Las otras 5 sucursales quedan listas para actualizar sus datos fiscales/bancarios aquí.
CONFIG_SUCURSALES = {
    "IMAC": {
        "nombre_oficial": "IMAC DE VERACRUZ S.A. DE C.V. - SUCURSAL MATRIZ",
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
        "prefijo_folio": "IMAC"
    },
    "EJÉRCITO": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL EJÉRCITO MEXICANO",
        "sucursal_corta": "Sucursal Ejército",
        "razon_social": "IMAC DE VERACRUZ S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "AV. EJÉRCITO MEXICANO, BOCA DEL RÍO, VER.",
        "telefono": "POR DEFINIR",
        "correo": "ejercito@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "leyenda_entrega": "Precios de contado Libre Abordo Boca del Río, Ver.",
        "prefijo_folio": "EJER"
    },
    "BOCA DEL RÍO": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL BOCA DEL RÍO",
        "sucursal_corta": "Sucursal Boca del Río",
        "razon_social": "IMAC DE VERACRUZ S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "BLVD. MIGUEL ALEMÁN #306, COL. CENTRO, BOCA DEL RÍO, VER.",
        "telefono": "(229) 935 4525",
        "correo": "boca@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "leyenda_entrega": "Precios de contado Libre Abordo Boca del Río, Ver.",
        "prefijo_folio": "BOCA"
    },
    "RIVIERA": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL RIVIERA VERACRUZANA",
        "sucursal_corta": "Sucursal Riviera",
        "razon_social": "IMAC DE VERACRUZ S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "ZONA RIVIERA VERACRUZANA, ALVARADO / BOCA DEL RÍO, VER.",
        "telefono": "POR DEFINIR",
        "correo": "riviera@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "leyenda_entrega": "Precios de contado Libre Abordo Riviera Veracruzana, Ver.",
        "prefijo_folio": "RIV"
    },
    "FRAMBOYANES": {
        "nombre_oficial": "GRUPO IMAC - SUCURSAL FRAMBOYANES",
        "sucursal_corta": "Sucursal Framboyanes",
        "razon_social": "IMAC DE VERACRUZ S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "ZONA PLAZA FRAMBOYANES, VERACRUZ, VER.",
        "telefono": "POR DEFINIR",
        "correo": "framboyanes@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "leyenda_entrega": "Precios de contado Libre Abordo Veracruz, Ver.",
        "prefijo_folio": "FRAM"
    },
    "IMACRIL CENTRO": {
        "nombre_oficial": "IMACRIL - SUCURSAL CENTRO 5 DE MAYO",
        "sucursal_corta": "Sucursal IMACRIL Centro",
        "razon_social": "IMACRIL S.A. DE C.V.",
        "rfc": "PENDIENTE",
        "direccion": "AV. 5 DE MAYO, COL. CENTRO, VERACRUZ, VER.",
        "telefono": "POR DEFINIR",
        "correo": "centro@grupo-imac.com",
        "banco": "POR DEFINIR",
        "cuenta": "POR DEFINIR",
        "clabe": "POR DEFINIR",
        "leyenda_entrega": "Precios de contado Libre Abordo Veracruz, Ver.",
        "prefijo_folio": "CENT"
    }
}

def normalizar_texto(texto):
    s = str(texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def resolver_sucursal_clave(sucursal_raw):
    objetivo = normalizar_texto(sucursal_raw)
    if objetivo == "todas":
        return "TODAS"
    for clave in CONFIG_SUCURSALES.keys():
        if normalizar_texto(clave) == objetivo:
            return clave
    return "IMAC"

def extraer_campo_flexible(fila_norm, posibles_claves, default=""):
    for k in posibles_claves:
        if k in fila_norm and fila_norm[k]:
            return fila_norm[k]
    for k_real, val in fila_norm.items():
        if val and any(p in k_real for p in posibles_claves):
            return val
    return default

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
            fila_norm = {normalizar_texto(k): str(v).strip() for k, v in fila.items()}
            if fila_norm.get("usuario", "").lower() == u_clean and fila_norm.get("password", "") == p_clean:
                rol = fila_norm.get("rol", "Asesor")
                sucursal = resolver_sucursal_clave(fila_norm.get("sucursal", "IMAC"))
                nombre_asesor = extraer_campo_flexible(
                    fila_norm,
                    ["nombre_completo", "nombre_asesor", "nombre"],
                    default=user_input.strip().upper()
                )
                telefono_asesor = extraer_campo_flexible(
                    fila_norm,
                    ["telefono_asesor", "telefono", "numero", "celular", "whatsapp"],
                    default=""
                )
                correo_asesor = extraer_campo_flexible(
                    fila_norm,
                    ["correo_asesor", "correo", "email", "mail"],
                    default=""
                )
                perfil = {
                    "rol": rol,
                    "sucursal": sucursal,
                    "nombre_asesor": nombre_asesor,
                    "telefono_asesor": telefono_asesor,
                    "correo_asesor": correo_asesor
                }
                return True, perfil
        return False, None
    except Exception as e:
        st.error(f"⚠️ Error al leer la pestaña 'Usuarios': {e}")
        return False, None

# --- INICIALIZACIÓN DE SESIÓN ---
defaults_sesion = {
    "logged_in": False,
    "usuario": "",
    "role": "",
    "sucursal_asignada": "IMAC",
    "sucursal_activa": "IMAC",
    "nombre_asesor": "",
    "telefono_asesor": "",
    "correo_asesor": ""
}
for k_def, v_def in defaults_sesion.items():
    if k_def not in st.session_state:
        st.session_state[k_def] = v_def

# Compartimos la configuración maestra de sucursales con las páginas en pages/
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
        st.info("Verifica tus `Secrets` (`GOOGLE_CREDENTIALS` e `ID_EXCEL`) en Streamlit Cloud.")
    else:
        st.subheader("🔐 Inicio de Sesión")
        with st.form("form_login_ligeros"):
            u_in = st.text_input("Usuario", placeholder="Ej. wromero")
            p_in = st.text_input("Contraseña", type="password")
            btn_login = st.form_submit_button("Ingresar al Sistema", type="primary", use_container_width=True)

            if btn_login:
                ok, perfil = validar_usuario(doc, u_in, p_in)
                if ok and perfil:
                    st.session_state["logged_in"] = True
                    st.session_state["usuario"] = u_in.strip()
                    st.session_state["role"] = perfil["rol"]
                    st.session_state["sucursal_asignada"] = perfil["sucursal"]
                    st.session_state["nombre_asesor"] = perfil["nombre_asesor"]
                    st.session_state["telefono_asesor"] = perfil["telefono_asesor"]
                    st.session_state["correo_asesor"] = perfil["correo_asesor"]

                    if perfil["sucursal"] in CONFIG_SUCURSALES:
                        st.session_state["sucursal_activa"] = perfil["sucursal"]
                    else:
                        st.session_state["sucursal_activa"] = "IMAC"

                    registrar_bitacora(
                        doc,
                        "Login",
                        f"Inició sesión ({perfil['nombre_asesor']} | Sucursal: {perfil['sucursal']})"
                    )
                    st.rerun()
                else:
                    st.error("🚫 Usuario o contraseña incorrectos.")

# ==========================================
# ✅ PANEL DE BIENVENIDA Y PERFIL PERSONALIZADO
# ==========================================
else:
    nombre_mostrado = st.session_state["nombre_asesor"] or st.session_state["usuario"]
    st.success(f"Bienvenido, **{nombre_mostrado}** | Perfil: **{st.session_state['role']}**")

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

    # Diagnóstico de pestañas
    st.markdown("### 📡 Estado de la Base de Datos")
    pestanas_req = ["Usuarios", "Cotizaciones", "Bitacora_Movimientos"]
    cols_diag = st.columns(3)
    for idx_p, nombre_p in enumerate(pestanas_req):
        try:
            doc.worksheet(nombre_p)
            cols_diag[idx_p].metric(nombre_p, "Conectada", "OK")
        except Exception:
            cols_diag[idx_p].metric(nombre_p, "Falta", "Revisar", delta_color="inverse")

    # Perfil del Asesor (jalado automáticamente de la pestaña Usuarios)
    st.markdown("### 👤 Datos del Asesor (Cargados desde `Usuarios`)")
    a1, a2, a3 = st.columns(3)
    a1.write(f"**Nombre en PDF:** {st.session_state['nombre_asesor'] or 'Sin capturar'}")
    a2.write(f"**Teléfono:** {st.session_state['telefono_asesor'] or 'Sin capturar'}")
    a3.write(f"**Correo:** {st.session_state['correo_asesor'] or 'Sin capturar'}")

    # Perfil Fiscal y Bancario de la Sucursal Activa
    st.markdown("### 🏦 Perfil Fiscal y Bancario de la Sucursal Activa")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Razón Social:** {suc_info['razon_social']}")
        st.write(f"**RFC:** {suc_info['rfc']}")
        st.write(f"**Dirección:** {suc_info['direccion']}")
        st.write(f"**Teléfono Sucursal:** {suc_info['telefono']}")
        st.write(f"**Correo Sucursal:** {suc_info['correo']}")
    with c2:
        st.write(f"**Banco:** {suc_info['banco']}")
        st.write(f"**Cuenta:** {suc_info['cuenta']}")
        st.write(f"**CLABE:** {suc_info['clabe']}")
        st.write(f"**Leyenda Entrega:** {suc_info['leyenda_entrega']}")

    if st.button("🚪 Cerrar Sesión"):
        registrar_bitacora(doc, "Login", "Cerró sesión")
        st.session_state["logged_in"] = False
        st.rerun()
