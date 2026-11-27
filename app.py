import streamlit as st
import os
from PIL import Image
from config_imac import (
    CONFIG_SUCURSALES,
    conectar_sheets_con_estado,
    registrar_bitacora,
    normalizar_texto,
    resolver_sucursal_clave,
    extraer_campo_flexible,
)

# --- CONFIGURACIÓN DE PÁGINA ---
icono_nav = "logo_imac_2026.png" if os.path.exists("logo_imac_2026.png") else "🏢"
st.set_page_config(
    page_title="Acceso | Cotizador Prospección IMAC",
    page_icon=icono_nav,
    layout="centered"
)

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
                return True, {
                    "rol": rol,
                    "sucursal": sucursal,
                    "nombre_asesor": nombre_asesor,
                    "telefono_asesor": telefono_asesor,
                    "correo_asesor": correo_asesor
                }
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

# --- ENCABEZADO VISUAL ---
col_l, col_t = st.columns([1, 4])
with col_l:
    if os.path.exists("logo_imac_2026.png"):
        st.image(Image.open("logo_imac_2026.png"), use_container_width=True)
    else:
        st.markdown("### 🏢 IMAC")
with col_t:
    st.title("Cotizador Prospección Grupo IMAC")
    st.caption("Plataforma Comercial de Mostrador — Zona Veracruz")

st.markdown("---")

doc, estado_conexion = conectar_sheets_con_estado()

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

    st.markdown("### 📡 Estado de la Base de Datos")
    pestanas_req = ["Usuarios", "Cotizaciones", "Bitacora_Movimientos"]
    cols_diag = st.columns(3)
    for idx_p, nombre_p in enumerate(pestanas_req):
        try:
            doc.worksheet(nombre_p)
            cols_diag[idx_p].metric(nombre_p, "Conectada", "OK")
        except Exception:
            cols_diag[idx_p].metric(nombre_p, "Falta", "Revisar", delta_color="inverse")

    st.markdown("### 👤 Datos del Asesor (Cargados desde `Usuarios`)")
    a1, a2, a3 = st.columns(3)
    a1.write(f"**Nombre en PDF:** {st.session_state['nombre_asesor'] or 'Sin capturar'}")
    a2.write(f"**Teléfono:** {st.session_state['telefono_asesor'] or 'Sin capturar'}")
    a3.write(f"**Correo:** {st.session_state['correo_asesor'] or 'Sin capturar'}")

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
