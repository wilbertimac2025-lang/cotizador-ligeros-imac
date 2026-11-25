import streamlit as st
import datetime
import json
import os
import sys
import pandas as pd
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_imac import (
    CONFIG_SUCURSALES,
    CATALOGO_LIGEROS,
    MAX_DESC_PCT,
    PRECIOS_INCLUYEN_IVA,
    conectar_sheets,
    registrar_bitacora,
    limpiar_monto,
    normalizar_texto,
    resolver_sucursal_clave,
    enviar_respaldo_correo,
    calcular_nivel_y_precio,
    calcular_totales_carrito,
    generar_pdf_mostrador,
    ahora_mx,
)

# --- CONFIGURACIÓN DE PÁGINA ---
icono_nav = "logo_imac_2026.png" if os.path.exists("logo_imac_2026.png") else "🏢"
st.set_page_config(
    page_title="Consultar y Editar Cotizaciones | Grupo IMAC",
    page_icon=icono_nav,
    layout="wide"
)

# --- CANDADO DE SESIÓN ---
if not st.session_state.get("logged_in", False):
    st.warning("⚠️ Acceso denegado. Inicia sesión primero en la página principal (`app`).")
    st.stop()

# --- CATÁLOGO DE ESTATUS OFICIALES ---
ESTATUS_OPCIONES = ["Cotizada", "Vendida", "Cancelada"]
BADGE_ESTATUS = {
    "Cotizada": "🟡 Cotizada",
    "Vendida": "🟢 Vendida",
    "Cancelada": "🔴 Cancelada",
}

def normalizar_estatus(valor_raw):
    t = normalizar_texto(valor_raw)
    if "vendid" in t or "ganad" in t or "cerrad" in t:
        return "Vendida"
    if "cancel" in t or "perdid" in t or "anulad" in t:
        return "Cancelada"
    return "Cotizada"

def extraer_estatus_fila(fila):
    """Lee el Estatus desde la Columna N (índice 13) con respaldo en Datos_JSON y valor por defecto Cotizada."""
    if len(fila) > 13 and str(fila[13]).strip():
        return normalizar_estatus(fila[13])
    if len(fila) > 12 and str(fila[12]).strip():
        try:
            payload = json.loads(fila[12])
            if payload.get("estatus"):
                return normalizar_estatus(payload.get("estatus"))
        except Exception:
            pass
    return "Cotizada"

def localizar_fila_folio(hoja, folio_objetivo, fila_idx_sugerida):
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
    return fila_real

def asegurar_encabezado_estatus(hoja):
    """Asegura que la celda N1 tenga el encabezado 'Estatus' si todavía está vacía."""
    try:
        val_n1 = str(hoja.cell(1, 14).value or "").strip()
        if not val_n1:
            hoja.update_cell(1, 14, "Estatus")
    except Exception:
        pass

def actualizar_fila_cotizacion_con_estatus(hoja, folio_objetivo, fila_idx_sugerida, valores_fila_14):
    """Sobrescribe A:N (14 columnas, incluyendo Estatus) sin duplicar registros."""
    fila_real = localizar_fila_folio(hoja, folio_objetivo, fila_idx_sugerida)
    if not fila_real:
        return False, "No se encontró el folio en la pestaña Cotizaciones."
    asegurar_encabezado_estatus(hoja)
    rango = f"A{fila_real}:N{fila_real}"
    try:
        hoja.update(values=[valores_fila_14], range_name=rango)
    except TypeError:
        hoja.update(rango, [valores_fila_14])
    return True, f"Fila {fila_real} actualizada (A:N)."

def actualizar_solo_estatus_folio(hoja, folio_objetivo, fila_idx_sugerida, nuevo_estatus):
    """Actualiza únicamente la Columna N (Estatus) para cambios rápidos sin regenerar el PDF."""
    fila_real = localizar_fila_folio(hoja, folio_objetivo, fila_idx_sugerida)
    if not fila_real:
        return False, "No se encontró el folio en la pestaña Cotizaciones."
    asegurar_encabezado_estatus(hoja)
    hoja.update_cell(fila_real, 14, nuevo_estatus)
    return True, f"Estatus actualizado en fila {fila_real} (Columna N)."

# --- ESTADO DE EDICIÓN ---
defaults_ed = {
    "ed_folio": None,
    "ed_fila_idx": None,
    "ed_sucursal": "IMAC",
    "ed_carrito": [],
    "ed_total_anterior": 0.0,
    "ed_estatus_anterior": "Cotizada",
    "ed_estatus": "Cotizada",
    "ed_pdf_bytes": None,
    "ed_pdf_nombre": "",
    "ed_asesor_tel": "",
    "ed_asesor_correo": ""
}
for k_d, v_d in defaults_ed.items():
    if k_d not in st.session_state:
        st.session_state[k_d] = v_d

def cargar_cotizacion_en_editor(fila, fila_idx):
    folio = str(fila[0]).strip()
    suc = resolver_sucursal_clave(fila[2] if len(fila) > 2 else "IMAC")
    if suc not in CONFIG_SUCURSALES:
        suc = "IMAC"
    asesor_f = str(fila[3]).strip() if len(fila) > 3 else ""
    cliente_f = str(fila[4]).strip() if len(fila) > 4 else ""
    tel_f = str(fila[5]).strip() if len(fila) > 5 else ""
    total_ant = limpiar_monto(fila[10]) if len(fila) > 10 else 0.0
    estatus_f = extraer_estatus_fila(fila)

    partidas = []
    flete_f = 0.0
    desc_f = 0.0
    notas_f = ""
    correo_f = ""
    asesor_tel_f = st.session_state.get("telefono_asesor", "")
    asesor_correo_f = st.session_state.get("correo_asesor", "")
    vigencia_f = ahora_mx().date() + datetime.timedelta(days=7)

    if len(fila) > 12 and str(fila[12]).strip():
        try:
            payload = json.loads(fila[12])
            for p in payload.get("partidas", []):
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
            if payload.get("asesor_telefono"):
                asesor_tel_f = str(payload.get("asesor_telefono"))
            if payload.get("asesor_correo"):
                asesor_correo_f = str(payload.get("asesor_correo"))
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
    st.session_state["ed_estatus_anterior"] = estatus_f
    st.session_state["ed_estatus"] = estatus_f
    st.session_state["ed_cliente"] = cliente_f
    st.session_state["ed_telefono"] = tel_f
    st.session_state["ed_correo"] = correo_f
    st.session_state["ed_asesor"] = asesor_f
    st.session_state["ed_asesor_tel"] = asesor_tel_f
    st.session_state["ed_asesor_correo"] = asesor_correo_f
    st.session_state["ed_vigencia"] = vigencia_f
    st.session_state["ed_flete"] = flete_f
    st.session_state["ed_desc_extra"] = desc_f
    st.session_state["ed_notas"] = notas_f
    st.session_state["ed_pdf_bytes"] = None
    st.session_state["ed_pdf_nombre"] = ""

# --- BARRA LATERAL INFORMATIVA ---
rol_norm = normalizar_texto(st.session_state.get("role", ""))
puede_ver_todas = (
    st.session_state.get("sucursal_asignada", "") == "TODAS"
    or any(k in rol_norm for k in ["admin", "directiv", "director"])
)
suc_usuario = st.session_state.get("sucursal_activa", "IMAC")
asesor_nombre_db = st.session_state.get("nombre_asesor") or st.session_state.get("usuario", "")

with st.sidebar:
    st.markdown(f"**🏢 Sucursal:** {suc_usuario}")
    st.caption(f"👤 {asesor_nombre_db} ({st.session_state.get('role', '')})")
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
    st.title("Historial, Estatus y Edición de Cotizaciones")
    st.caption("Consulta folios guardados, actualiza su estatus (Cotizada / Vendida / Cancelada), ajusta partidas y regenera el PDF")
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
    suc_fila = resolver_sucursal_clave(fila[2] if len(fila) > 2 else "IMAC")
    if not puede_ver_todas and suc_fila != suc_usuario:
        continue
    est_fila = extraer_estatus_fila(fila)
    registros_disponibles.append((idx + 1, fila, suc_fila, est_fila))

registros_disponibles.reverse()

if not registros_disponibles:
    st.info("No hay cotizaciones guardadas todavía para tu sucursal.")
    st.stop()

# KPIs rápidos con tasa de conversión en vivo
total_folios_vis = len(registros_disponibles)
vendidas_vis = [f for _, f, _, est in registros_disponibles if est == "Vendida"]
monto_cot_vis = sum(limpiar_monto(f[10]) for _, f, _, _ in registros_disponibles if len(f) > 10)
monto_ven_vis = sum(limpiar_monto(f[10]) for f in vendidas_vis if len(f) > 10)
conv_folios_vis = (len(vendidas_vis) / total_folios_vis * 100.0) if total_folios_vis > 0 else 0.0
conv_monto_vis = (monto_ven_vis / monto_cot_vis * 100.0) if monto_cot_vis > 0 else 0.0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Cotizaciones Registradas", f"{total_folios_vis}")
m2.metric("Monto Total Cotizado", f"${monto_cot_vis:,.2f}")
m3.metric("Monto Vendido", f"${monto_ven_vis:,.2f}", f"{conv_monto_vis:.1f}% del monto")
m4.metric("Tasa de Conversión", f"{conv_folios_vis:.1f}%", f"{len(vendidas_vis)} de {total_folios_vis} vendidas")

st.markdown("---")
st.subheader("🔎 Buscar Cotización Guardada")

col_f1, col_f2, col_f3 = st.columns([1.2, 1.1, 2.2])
with col_f1:
    if puede_ver_todas:
        sucursales_en_datos = ["TODAS"] + sorted(list({s_norm for _, _, s_norm, _ in registros_disponibles}))
        filtro_suc = st.selectbox("Filtrar por Sucursal:", sucursales_en_datos)
    else:
        filtro_suc = suc_usuario
        st.text_input("Sucursal:", value=suc_usuario, disabled=True)
with col_f2:
    filtro_estatus = st.selectbox("Filtrar por Estatus:", ["TODOS"] + ESTATUS_OPCIONES)
with col_f3:
    filtro_texto = st.text_input("Buscar por Folio, Cliente o Asesor:", placeholder="Ej. LIG-IMAC-0001-26 o Constructora...")

registros_filtrados = []
for fila_idx, fila, suc_norm, est_fila in registros_disponibles:
    if filtro_suc != "TODAS" and suc_norm != filtro_suc:
        continue
    if filtro_estatus != "TODOS" and est_fila != filtro_estatus:
        continue
    if filtro_texto.strip():
        q = filtro_texto.strip().upper()
        bloque_busq = f"{fila[0]} {fila[3]} {fila[4]}".upper()
        if q not in bloque_busq:
            continue
    registros_filtrados.append((fila_idx, fila, suc_norm, est_fila))

if registros_filtrados:
    df_hist = pd.DataFrame([
        {
            "Folio": f[0],
            "Estatus": BADGE_ESTATUS.get(est_f, est_f),
            "Fecha": f[1] if len(f) > 1 else "",
            "Sucursal": s_norm,
            "Razón Social": CONFIG_SUCURSALES.get(s_norm, {}).get("razon_social", ""),
            "Asesor": f[3] if len(f) > 3 else "",
            "Cliente": f[4] if len(f) > 4 else "",
            "Total MXN": f"${limpiar_monto(f[10]):,.2f}" if len(f) > 10 else "$0.00"
        }
        for _, f, s_norm, est_f in registros_filtrados
    ])
    st.dataframe(df_hist, use_container_width=True, hide_index=True)

    mapa_folios = {
        f"{f[0]} | {BADGE_ESTATUS.get(est_f, est_f)} | {s_norm} | {f[4]} (${limpiar_monto(f[10]):,.2f})": (fila_idx, f)
        for fila_idx, f, s_norm, est_f in registros_filtrados
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
# ✏️ SECCIÓN 2: EDITOR DE LA COTIZACIÓN CARGADA + ESTATUS
# ==========================================================
if st.session_state.get("ed_folio"):
    folio_activo = st.session_state["ed_folio"]
    suc_folio = st.session_state["ed_sucursal"]
    suc_info_folio = CONFIG_SUCURSALES.get(suc_folio, CONFIG_SUCURSALES["IMAC"])

    st.markdown("---")
    st.success(
        f"✏️ Editando Folio: **{folio_activo}** | **{BADGE_ESTATUS.get(st.session_state['ed_estatus_anterior'], 'Cotizada')}** | "
        f"**{suc_info_folio['razon_social']}** ({suc_info_folio['sucursal_corta']}) | "
        f"Total original: **${st.session_state['ed_total_anterior']:,.2f} MXN**"
    )

    # --- Control de Estatus Comercial (con botón de guardado rápido en 1 clic) ---
    st.markdown("### 📌 Estatus Comercial de la Cotización")
    e_col1, e_col2 = st.columns([2.0, 1.5])
    with e_col1:
        estatus_ed = st.selectbox(
            "Estatus actual del folio:",
            ESTATUS_OPCIONES,
            key="ed_estatus",
            help="Marca como 'Vendida' cuando el cliente concrete la compra o 'Cancelada' si la cotización se descartó."
        )
    with e_col2:
        st.write("")
        st.write("")
        if st.button("📌 Actualizar Solo Estatus (sin regenerar PDF)", use_container_width=True):
            with st.spinner(f"Actualizando estatus de {folio_activo} a {estatus_ed}..."):
                ok_est, msg_est = actualizar_solo_estatus_folio(
                    hoja_cot, folio_activo, st.session_state["ed_fila_idx"], estatus_ed
                )
                if ok_est:
                    registrar_bitacora(
                        doc,
                        "Estatus Cotización",
                        f"Cambió estatus de {folio_activo} ({suc_folio}) de {st.session_state['ed_estatus_anterior']} a {estatus_ed}"
                    )
                    st.session_state["ed_estatus_anterior"] = estatus_ed
                    st.success(f"✅ Folio **{folio_activo}** marcado como **{BADGE_ESTATUS[estatus_ed]}** ({msg_est}).")
                else:
                    st.error(f"⚠️ No se pudo actualizar el estatus: {msg_est}")

    st.markdown("---")

    c1, c2, c3, c4, c5 = st.columns([2.2, 1.3, 1.6, 1.5, 1.2])
    with c1: cliente_ed = st.text_input("En atención a (Cliente / Empresa)", key="ed_cliente")
    with c2: telefono_ed = st.text_input("Teléfono Cliente", key="ed_telefono")
    with c3: correo_ed = st.text_input("Correo del Cliente", key="ed_correo")
    with c4: asesor_ed = st.text_input("Asesor", key="ed_asesor")
    with c5: vigencia_ed = st.date_input("Precios válidos al", key="ed_vigencia")

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

    st.markdown("### 📋 Modificar Cantidades, Descuento en Partidas N1 (Máx. 10%) o Quitar Partidas")
    if not st.session_state["ed_carrito"]:
        st.warning("⚠️ Este folio no tiene partidas cargadas. Agrega materiales arriba para reconstruirlo.")
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
                st.info("🏷️ **Excepción en Edición activa:** el descuento global permanece bloqueado por existir partidas en **Nivel 3 (Mayoreo)**, pero puedes aplicar hasta **10.0%** de descuento individual en partidas **Nivel 1**.")
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

        tot_ed = calcular_totales_carrito(st.session_state["ed_carrito"], flete_ed, desc_extra_ed, PRECIOS_INCLUYEN_IVA)
        diferencia_total = tot_ed["total_final"] - st.session_state["ed_total_anterior"]

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Subtotal", f"${tot_ed['subtotal_sin_iva']:,.2f}")
        k2.metric("IVA (16%)", f"${tot_ed['iva_monto']:,.2f}")
        k3.metric("Ahorro Volumen", f"${tot_ed['ahorro_nivel']:,.2f}")
        k4.metric("Desc. Partidas N1", f"-${tot_ed['total_desc_partidas']:,.2f}")
        k5.metric("NUEVO TOTAL MXN", f"${tot_ed['total_final']:,.2f}", f"{diferencia_total:+,.2f} vs original")

        enviar_correo_ed = st.checkbox("📧 Reenviar copia del PDF actualizado por correo", value=False, key="ed_chk_mail")

        if st.button(f"💾 GUARDAR CAMBIOS, ESTATUS ({estatus_ed.upper()}) Y REGENERAR PDF", type="primary", use_container_width=True):
            with st.spinner(f"Actualizando {folio_activo} en Google Sheets y regenerando PDF personalizado..."):
                cliente_final = cliente_ed.strip() if cliente_ed.strip() else "MOSTRADOR"
                asesor_final = asesor_ed.strip() if asesor_ed.strip() else asesor_nombre_db

                pdf_bytes, tot_pdf, sub_pdf, iva_pdf, ahorr_pdf, desc_n1_pdf = generar_pdf_mostrador(
                    folio=folio_activo,
                    sucursal_nombre=suc_folio,
                    suc_info=suc_info_folio,
                    cliente=cliente_final,
                    telefono_cli=telefono_ed,
                    correo_cli=correo_ed,
                    asesor_nombre=asesor_final,
                    asesor_telefono=st.session_state.get("ed_asesor_tel", ""),
                    asesor_correo=st.session_state.get("ed_asesor_correo", ""),
                    validez=vigencia_ed,
                    carrito=st.session_state["ed_carrito"],
                    flete=flete_ed,
                    desc_extra_pct=desc_extra_ed,
                    precios_incluyen_iva=PRECIOS_INCLUYEN_IVA,
                    notas=notas_ed,
                    mostrar_col_desc=False
                )

                fecha_act = ahora_mx().strftime("%d/%m/%Y %H:%M")
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
                    "vigencia": vigencia_ed.strftime("%d/%m/%Y"),
                    "asesor_telefono": st.session_state.get("ed_asesor_tel", ""),
                    "asesor_correo": st.session_state.get("ed_asesor_correo", ""),
                    "estatus": estatus_ed
                }, ensure_ascii=False)

                fila_actualizada = [
                    folio_activo, fecha_act, suc_folio, asesor_final,
                    cliente_final.upper(), telefono_ed, len(st.session_state["ed_carrito"]),
                    resumen_partidas, round(sub_pdf, 2), round(iva_pdf, 2),
                    round(tot_pdf, 2), round(ahorr_pdf, 2), payload_json, estatus_ed
                ]

                ok_upd, msg_upd = actualizar_fila_cotizacion_con_estatus(
                    hoja_cot, folio_activo, st.session_state["ed_fila_idx"], fila_actualizada
                )

                if ok_upd:
                    registrar_bitacora(
                        doc,
                        "Edición Cotizaciones",
                        f"Actualizó {folio_activo} ({suc_folio}) | Estatus: {st.session_state['ed_estatus_anterior']} -> {estatus_ed} | Total: ${st.session_state['ed_total_anterior']:,.2f} -> ${tot_pdf:,.2f} MXN"
                    )
                    st.session_state["ed_total_anterior"] = tot_pdf
                    st.session_state["ed_estatus_anterior"] = estatus_ed
                    nombre_pdf = f"Cotizacion_{folio_activo}_{cliente_final.replace(' ', '_')}.pdf"
                    st.session_state["ed_pdf_bytes"] = pdf_bytes
                    st.session_state["ed_pdf_nombre"] = nombre_pdf

                    if enviar_correo_ed:
                        destinos = [st.session_state.get("ed_asesor_correo") or suc_info_folio["correo"]]
                        if suc_info_folio["correo"] not in destinos:
                            destinos.append(suc_info_folio["correo"])
                        if correo_ed.strip():
                            destinos.append(correo_ed.strip())
                        dest_str = ", ".join(destinos)
                        ok_mail, msg_mail = enviar_respaldo_correo(
                            pdf_bytes, nombre_pdf, folio_activo, suc_folio,
                            cliente_final, asesor_final, tot_pdf, dest_str, es_edicion=True
                        )
                        if ok_mail:
                            st.info(f"📧 PDF actualizado enviado a: {dest_str}")
                        else:
                            st.warning(f"⚠️ No se pudo enviar el correo: {msg_mail}")

                    st.success(f"✅ Folio **{folio_activo}** ({BADGE_ESTATUS[estatus_ed]}) actualizado ({msg_upd}).")
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
