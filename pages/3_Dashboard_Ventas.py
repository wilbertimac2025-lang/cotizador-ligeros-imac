import streamlit as st
import datetime
import json
import os
import re
import sys
import pandas as pd
from PIL import Image

try:
    import altair as alt
    ALTAIR_OK = True
except Exception:
    ALTAIR_OK = False

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_imac import (
    CONFIG_SUCURSALES,
    CATALOGO_LIGEROS,
    conectar_sheets,
    limpiar_monto,
    normalizar_texto,
    resolver_sucursal_clave,
    ahora_mx,
)

# --- CONFIGURACIÓN DE PÁGINA ---
icono_nav = "logo_imac_2026.png" if os.path.exists("logo_imac_2026.png") else "🏢"
st.set_page_config(
    page_title="Dashboard de Ventas | Grupo IMAC",
    page_icon=icono_nav,
    layout="wide"
)

# --- 1. CANDADO DE SESIÓN Y RESTRICCIÓN ESTRICTA DE ROL (SOLO ADMIN Y DIRECTIVO) ---
if not st.session_state.get("logged_in", False):
    st.warning("⚠️ Acceso denegado. Inicia sesión primero en la página principal (`app`).")
    st.stop()

rol_actual = str(st.session_state.get("role", "")).strip()
rol_norm = normalizar_texto(rol_actual)
es_autorizado = any(clave in rol_norm for clave in ["admin", "directiv", "director"])

if not es_autorizado:
    st.error("🔒 Acceso restringido. El **Dashboard de Ventas** está habilitado exclusivamente para perfiles **Admin** y **Directivo**.")
    st.info(f"Tu perfil actual es **{rol_actual or 'Mostrador'}**. Utiliza el menú lateral para acceder al Cotizador o a Editar Cotizaciones.")
    st.stop()

# --- PALETA CORPORATIVA Y SEMÁNTICA ---
COLOR_AZUL_PRIMARIO = "#0F3C8C"
COLOR_AZUL_CLARO = "#0096FF"
COLOR_DORADO = "#C9A227"
COLOR_VERDE = "#1B8A5A"
COLOR_ROJO = "#C81E1E"

ESTATUS_OPCIONES = ["Cotizada", "Vendida", "Cancelada"]
ESCALA_ESTATUS = {
    "domain": ["Vendida", "Cotizada", "Cancelada"],
    "range": [COLOR_VERDE, COLOR_AZUL_CLARO, COLOR_ROJO],
}

# --- FUNCIONES DE PARSEO Y CARGA ---
def normalizar_estatus(valor_raw):
    t = normalizar_texto(valor_raw)
    if "vendid" in t or "ganad" in t or "cerrad" in t:
        return "Vendida"
    if "cancel" in t or "perdid" in t or "anulad" in t:
        return "Cancelada"
    return "Cotizada"

def normalizar_folio_factura(raw):
    return re.sub(r"\s+", "", str(raw or "").strip().upper())

def parsear_fecha_sheet(fecha_str):
    txt = str(fecha_str or "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(txt, fmt)
        except Exception:
            continue
    return None

def cargar_datos_cotizaciones(doc):
    hoja = doc.worksheet("Cotizaciones")
    filas = hoja.get_all_values()

    registros_cot = []
    registros_prod = []

    for idx, fila in enumerate(filas):
        if idx == 0 and len(fila) > 0 and "FOLIO" in str(fila[0]).upper():
            continue
        if len(fila) < 5 or not str(fila[0]).strip():
            continue

        folio = str(fila[0]).strip()
        fecha_raw = str(fila[1]).strip() if len(fila) > 1 else ""
        fecha_dt = parsear_fecha_sheet(fecha_raw)
        suc_norm = resolver_sucursal_clave(fila[2] if len(fila) > 2 else "IMAC")
        if suc_norm not in CONFIG_SUCURSALES:
            suc_norm = "IMAC"
        razon_social = CONFIG_SUCURSALES[suc_norm]["razon_social"]

        asesor = str(fila[3]).strip().upper() if len(fila) > 3 and str(fila[3]).strip() else "SIN ASESOR"
        cliente = str(fila[4]).strip().upper() if len(fila) > 4 and str(fila[4]).strip() else "MOSTRADOR"
        partidas_cnt = int(limpiar_monto(fila[6])) if len(fila) > 6 else 0
        subtotal = limpiar_monto(fila[8]) if len(fila) > 8 else 0.0
        iva = limpiar_monto(fila[9]) if len(fila) > 9 else 0.0
        total_mxn = limpiar_monto(fila[10]) if len(fila) > 10 else 0.0
        ahorro_vol = limpiar_monto(fila[11]) if len(fila) > 11 else 0.0
        datos_json_raw = str(fila[12]).strip() if len(fila) > 12 else ""

        estatus_col = str(fila[13]).strip() if len(fila) > 13 else ""
        estatus = normalizar_estatus(estatus_col) if estatus_col else ""
        no_factura = normalizar_folio_factura(fila[14]) if len(fila) > 14 else ""

        flete = 0.0
        desc_global_pct = 0.0
        desc_n1_monto_total = 0.0
        piezas_folio = 0.0
        partidas_temp = []

        if datos_json_raw:
            try:
                payload = json.loads(datos_json_raw)
                if not estatus and payload.get("estatus"):
                    estatus = normalizar_estatus(payload.get("estatus"))
                if not no_factura and payload.get("no_factura"):
                    no_factura = normalizar_folio_factura(payload.get("no_factura"))
                flete = float(payload.get("flete", 0.0) or 0.0)
                desc_global_pct = float(payload.get("desc_extra_pct", 0.0) or 0.0)
                partidas_temp = payload.get("partidas", [])
            except Exception:
                partidas_temp = []

        if not estatus:
            estatus = "Cotizada"

        for p in partidas_temp:
            clave_p = str(p.get("clave", "")).strip()
            cat_info = CATALOGO_LIGEROS.get(clave_p, {})
            prod_nom = cat_info.get("producto") or str(p.get("producto", clave_p)).strip()
            familia = cat_info.get("categoria") or str(p.get("categoria", "Otros")).strip()
            cant = float(p.get("cantidad", 0.0) or 0.0)
            nivel = str(p.get("nivel", "NIVEL 1")).strip().upper()
            pu_base = float(p.get("precio_unit", 0.0) or 0.0)
            desc_p = float(p.get("desc_pct", 0.0) or 0.0) if nivel == "NIVEL 1" else 0.0

            pu_post_n1 = pu_base * (1.0 - desc_p / 100.0)
            pu_neto = round(pu_post_n1 * (1.0 - desc_global_pct / 100.0), 2)
            imp_neto = round(cant * pu_neto, 2)
            desc_n1_monto_total += max(0.0, (cant * pu_base) - (cant * pu_post_n1))
            piezas_folio += cant

            registros_prod.append({
                "Folio": folio,
                "Estatus": estatus,
                "No_Factura": no_factura,
                "Fecha_DT": fecha_dt,
                "Sucursal": suc_norm,
                "Razon_Social": razon_social,
                "Asesor": asesor,
                "Clave": clave_p,
                "Producto": prod_nom,
                "Familia": familia,
                "Nivel": nivel,
                "Cantidad": cant,
                "Importe_Neto": imp_neto
            })

        registros_cot.append({
            "Folio": folio,
            "Estatus": estatus,
            "No_Factura": no_factura,
            "Tiene_Factura": 1 if (estatus == "Vendida" and bool(no_factura)) else 0,
            "Fecha_Texto": fecha_raw,
            "Fecha_DT": fecha_dt,
            "Fecha_Dia": fecha_dt.date() if fecha_dt else None,
            "Sucursal": suc_norm,
            "Razon_Social": razon_social,
            "Asesor": asesor,
            "Cliente": cliente,
            "Partidas": partidas_cnt,
            "Piezas": piezas_folio,
            "Flete": round(flete, 2),
            "Subtotal": round(subtotal, 2),
            "IVA": round(iva, 2),
            "Total_MXN": round(total_mxn, 2),
            "Monto_Vendido": round(total_mxn, 2) if estatus == "Vendida" else 0.0,
            "Monto_Cotizado_Abierto": round(total_mxn, 2) if estatus == "Cotizada" else 0.0,
            "Monto_Cancelado": round(total_mxn, 2) if estatus == "Cancelada" else 0.0,
            "Es_Vendida": 1 if estatus == "Vendida" else 0,
            "Es_Cotizada": 1 if estatus == "Cotizada" else 0,
            "Es_Cancelada": 1 if estatus == "Cancelada" else 0,
            "Ahorro_Volumen": round(ahorro_vol, 2),
            "Desc_Especial_N1": round(desc_n1_monto_total, 2),
            "Desc_Global_Pct": desc_global_pct
        })

    df_cot = pd.DataFrame(registros_cot)
    df_prod = pd.DataFrame(registros_prod)
    return df_cot, df_prod

def calcular_tabla_conversion(df_base, cols_grupo):
    """Agrupa por sucursal/asesor/razón social y calcula tasas de conversión por folios, monto y respaldo SAE."""
    res = (
        df_base.groupby(cols_grupo, as_index=False)
        .agg(
            Folios=("Folio", "count"),
            Cotizadas=("Es_Cotizada", "sum"),
            Vendidas=("Es_Vendida", "sum"),
            Con_Factura=("Tiene_Factura", "sum"),
            Canceladas=("Es_Cancelada", "sum"),
            Total_MXN=("Total_MXN", "sum"),
            Monto_Vendido=("Monto_Vendido", "sum"),
            Ticket_Promedio=("Total_MXN", "mean"),
            Ahorro_Volumen=("Ahorro_Volumen", "sum"),
            Desc_N1=("Desc_Especial_N1", "sum"),
        )
    )
    res["Conv_Folios_Pct"] = res.apply(
        lambda r: (r["Vendidas"] / r["Folios"] * 100.0) if r["Folios"] > 0 else 0.0, axis=1
    )
    res["Conv_Monto_Pct"] = res.apply(
        lambda r: (r["Monto_Vendido"] / r["Total_MXN"] * 100.0) if r["Total_MXN"] > 0 else 0.0, axis=1
    )
    res["Ticket_Vendido"] = res.apply(
        lambda r: (r["Monto_Vendido"] / r["Vendidas"]) if r["Vendidas"] > 0 else 0.0, axis=1
    )
    return res

# --- BARRA LATERAL ---
asesor_nombre_db = st.session_state.get("nombre_asesor") or st.session_state.get("usuario", "")
with st.sidebar:
    st.markdown("**📊 Panel Directivo**")
    st.caption(f"👤 {asesor_nombre_db} ({rol_actual})")
    st.caption("🔐 Acceso exclusivo Admin / Directivo")
    st.markdown("---")
    if st.button("🔄 Actualizar Datos", use_container_width=True):
        st.rerun()

# --- ENCABEZADO PRINCIPAL ---
col_logo, col_tit = st.columns([1, 5])
with col_logo:
    if os.path.exists("logo_imac_2026.png"):
        st.image(Image.open("logo_imac_2026.png"), use_container_width=True)
    else:
        st.markdown("### 🏢 IMAC")
with col_tit:
    st.title("Dashboard Comercial y Conversión — Grupo IMAC")
    st.caption(f"Monitoreo ejecutivo de cotizaciones, cierres y folios de factura SAE | Corte: {ahora_mx().strftime('%d/%m/%Y %H:%M hrs')}")
st.markdown("---")

doc = conectar_sheets()
if not doc:
    st.error("⚠️ No se pudo conectar con Google Sheets. Verifica tus credenciales en Secrets.")
    st.stop()

try:
    df_cot, df_prod = cargar_datos_cotizaciones(doc)
except Exception as e:
    st.error(f"⚠️ Error al leer la pestaña 'Cotizaciones': {e}")
    st.stop()

if df_cot.empty:
    st.info("Todavía no hay cotizaciones registradas en Google Sheets para analizar.")
    st.stop()

# --- 2. FILTROS DINÁMICOS ---
st.subheader("🔎 Filtros del Análisis")
fechas_validas = df_cot["Fecha_Dia"].dropna()
hoy_mx = ahora_mx().date()
fecha_min_def = fechas_validas.min() if not fechas_validas.empty else hoy_mx
fecha_max_def = fechas_validas.max() if not fechas_validas.empty else hoy_mx

f1, f2, f3, f4, f5, f6 = st.columns([1.0, 1.0, 1.4, 1.2, 1.2, 1.1])
with f1:
    f_inicio = st.date_input("Desde:", value=fecha_min_def, min_value=datetime.date(2024, 1, 1), max_value=hoy_mx + datetime.timedelta(days=365))
with f2:
    f_fin = st.date_input("Hasta:", value=max(fecha_max_def, f_inicio), min_value=f_inicio, max_value=hoy_mx + datetime.timedelta(days=365))
with f3:
    razones_disp = ["TODAS"] + sorted(df_cot["Razon_Social"].dropna().unique().tolist())
    sel_razon = st.selectbox("Razón Social:", razones_disp)
with f4:
    suc_base = df_cot if sel_razon == "TODAS" else df_cot[df_cot["Razon_Social"] == sel_razon]
    sucs_disp = ["TODAS"] + sorted(suc_base["Sucursal"].dropna().unique().tolist())
    sel_suc = st.selectbox("Sucursal:", sucs_disp)
with f5:
    as_base = suc_base if sel_suc == "TODAS" else suc_base[suc_base["Sucursal"] == sel_suc]
    asesores_disp = ["TODOS"] + sorted(as_base["Asesor"].dropna().unique().tolist())
    sel_asesor = st.selectbox("Asesor:", asesores_disp)
with f6:
    sel_estatus = st.selectbox("Estatus:", ["TODOS"] + ESTATUS_OPCIONES)

mask_base = pd.Series(True, index=df_cot.index)
mask_base &= df_cot["Fecha_Dia"].isna() | ((df_cot["Fecha_Dia"] >= f_inicio) & (df_cot["Fecha_Dia"] <= f_fin))
if sel_razon != "TODAS":
    mask_base &= (df_cot["Razon_Social"] == sel_razon)
if sel_suc != "TODAS":
    mask_base &= (df_cot["Sucursal"] == sel_suc)
if sel_asesor != "TODOS":
    mask_base &= (df_cot["Asesor"] == sel_asesor)

df_scope = df_cot[mask_base].copy()
df_f = df_scope[df_scope["Estatus"] == sel_estatus].copy() if sel_estatus != "TODOS" else df_scope.copy()

if df_f.empty:
    st.warning("No hay cotizaciones que coincidan con los filtros seleccionados.")
    st.stop()

folios_activos = set(df_f["Folio"].tolist())
df_pf = df_prod[df_prod["Folio"].isin(folios_activos)].copy() if not df_prod.empty else pd.DataFrame()

# --- 3. KPIs EJECUTIVOS, CONVERSIÓN Y RESPALDO SAE ---
monto_total = float(df_f["Total_MXN"].sum())
monto_vendido = float(df_f["Monto_Vendido"].sum())
num_folios = int(len(df_f))
num_vendidas = int(df_f["Es_Vendida"].sum())
num_con_fac = int(df_f["Tiene_Factura"].sum())
num_cotizadas = int(df_f["Es_Cotizada"].sum())
num_canceladas = int(df_f["Es_Cancelada"].sum())

conv_folios_pct = (num_vendidas / num_folios * 100.0) if num_folios > 0 else 0.0
conv_monto_pct = (monto_vendido / monto_total * 100.0) if monto_total > 0 else 0.0
respaldo_sae_pct = (num_con_fac / num_vendidas * 100.0) if num_vendidas > 0 else 100.0

ticket_prom = monto_total / num_folios if num_folios > 0 else 0.0
ticket_prom_vendido = monto_vendido / num_vendidas if num_vendidas > 0 else 0.0

st.markdown("---")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("💰 Monto Cotizado (c/IVA)", f"${monto_total:,.2f}", f"{num_folios:,} folios totales")
k2.metric("🟢 Monto Vendido", f"${monto_vendido:,.2f}", f"{conv_monto_pct:.1f}% del monto")
k3.metric("📈 Conversión (Folios)", f"{conv_folios_pct:.1f}%", f"{num_vendidas} de {num_folios} vendidas")
k4.metric("🎯 Ticket Promedio", f"${ticket_prom:,.2f}", f"Vendido: ${ticket_prom_vendido:,.2f}")
k5.metric("🧾 Respaldo Factura SAE", f"{respaldo_sae_pct:.1f}%", f"{num_con_fac}/{num_vendidas} con folio SAE")

if sel_estatus != "TODOS":
    st.caption(f"ℹ️ Estás filtrando únicamente el estatus **{sel_estatus}**. Para ver la tasa de conversión completa entre los 3 estatus, selecciona **TODOS**.")

st.markdown("---")

# --- 4. PESTAÑAS ANALÍTICAS ---
tab_suc, tab_ase, tab_prod, tab_sae = st.tabs([
    "🏢 Conversión por Sucursal",
    "👤 Conversión por Asesor",
    "📦 Productos Más Cotizados",
    "🧾 Auditoría SAE y Detalle"
])

# ==========================================================
# TAB 1: MONTO Y TASA DE CONVERSIÓN POR SUCURSAL
# ==========================================================
with tab_suc:
    res_suc = calcular_tabla_conversion(df_f, ["Sucursal", "Razon_Social"]).sort_values("Total_MXN", ascending=False)

    c_left, c_right = st.columns([1.25, 1.0])
    with c_left:
        st.markdown("#### Monto Cotizado por Sucursal y Estatus (MXN)")
        if ALTAIR_OK:
            suc_est = (
                df_f.groupby(["Sucursal", "Estatus"], as_index=False)
                .agg(Total_MXN=("Total_MXN", "sum"), Folios=("Folio", "count"))
            )
            orden_suc = res_suc["Sucursal"].tolist()
            chart_suc = (
                alt.Chart(suc_est)
                .mark_bar(cornerRadiusEnd=3)
                .encode(
                    x=alt.X("Total_MXN:Q", title="Monto ($ MXN)"),
                    y=alt.Y("Sucursal:N", sort=orden_suc, title=""),
                    color=alt.Color("Estatus:N", scale=alt.Scale(**ESCALA_ESTATUS), legend=alt.Legend(orient="top")),
                    tooltip=[
                        alt.Tooltip("Sucursal:N", title="Sucursal"),
                        alt.Tooltip("Estatus:N", title="Estatus"),
                        alt.Tooltip("Folios:Q", title="Folios"),
                        alt.Tooltip("Total_MXN:Q", title="Monto MXN", format="$,.2f"),
                    ],
                )
                .properties(height=310)
            )
            st.altair_chart(chart_suc, use_container_width=True)
        else:
            st.bar_chart(res_suc.set_index("Sucursal")[["Total_MXN", "Monto_Vendido"]])

    with c_right:
        st.markdown("#### Tasa de Conversión por Sucursal (% Folios Vendidos)")
        if ALTAIR_OK:
            chart_conv_suc = (
                alt.Chart(res_suc.sort_values("Conv_Folios_Pct", ascending=False))
                .mark_bar(color=COLOR_VERDE, cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Conv_Folios_Pct:Q", title="Conversión (%)", scale=alt.Scale(domain=[0, 100])),
                    y=alt.Y("Sucursal:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("Sucursal:N", title="Sucursal"),
                        alt.Tooltip("Vendidas:Q", title="Vendidas"),
                        alt.Tooltip("Con_Factura:Q", title="Con Factura SAE"),
                        alt.Tooltip("Folios:Q", title="Total Folios"),
                        alt.Tooltip("Conv_Folios_Pct:Q", title="Conv. Folios %", format=".1f"),
                        alt.Tooltip("Conv_Monto_Pct:Q", title="Conv. Monto %", format=".1f"),
                    ],
                )
                .properties(height=310)
            )
            st.altair_chart(chart_conv_suc, use_container_width=True)
        else:
            st.bar_chart(res_suc.set_index("Sucursal")["Conv_Folios_Pct"])

    st.markdown("#### Consolidado y Conversión por Razón Social")
    res_rs = calcular_tabla_conversion(df_f, ["Razon_Social"]).sort_values("Total_MXN", ascending=False)
    df_rs_show = res_rs[["Razon_Social", "Folios", "Cotizadas", "Vendidas", "Con_Factura", "Canceladas", "Conv_Folios_Pct", "Total_MXN", "Monto_Vendido", "Conv_Monto_Pct"]].copy()
    df_rs_show["Conv_Folios_Pct"] = df_rs_show["Conv_Folios_Pct"].map(lambda v: f"{v:.1f}%")
    df_rs_show["Conv_Monto_Pct"] = df_rs_show["Conv_Monto_Pct"].map(lambda v: f"{v:.1f}%")
    df_rs_show["Total_MXN"] = df_rs_show["Total_MXN"].map(lambda v: f"${v:,.2f}")
    df_rs_show["Monto_Vendido"] = df_rs_show["Monto_Vendido"].map(lambda v: f"${v:,.2f}")
    st.dataframe(
        df_rs_show.rename(columns={
            "Razon_Social": "Razón Social",
            "Con_Factura": "Con Fact. SAE",
            "Conv_Folios_Pct": "Conv. Folios",
            "Total_MXN": "Monto Cotizado",
            "Monto_Vendido": "Monto Vendido",
            "Conv_Monto_Pct": "Conv. Monto",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Tabla Comparativa por Sucursal")
    df_suc_show = res_suc[[
        "Sucursal", "Razon_Social", "Folios", "Cotizadas", "Vendidas", "Con_Factura", "Canceladas",
        "Conv_Folios_Pct", "Total_MXN", "Monto_Vendido", "Conv_Monto_Pct", "Ticket_Promedio"
    ]].copy()
    df_suc_show["Conv_Folios_Pct"] = df_suc_show["Conv_Folios_Pct"].map(lambda v: f"{v:.1f}%")
    df_suc_show["Conv_Monto_Pct"] = df_suc_show["Conv_Monto_Pct"].map(lambda v: f"{v:.1f}%")
    for col_m in ["Total_MXN", "Monto_Vendido", "Ticket_Promedio"]:
        df_suc_show[col_m] = df_suc_show[col_m].map(lambda v: f"${v:,.2f}")
    st.dataframe(
        df_suc_show.rename(columns={
            "Razon_Social": "Razón Social",
            "Con_Factura": "Con Fact. SAE",
            "Conv_Folios_Pct": "Conv. Folios",
            "Total_MXN": "Cotizado MXN",
            "Monto_Vendido": "Vendido MXN",
            "Conv_Monto_Pct": "Conv. Monto",
            "Ticket_Promedio": "Ticket Prom.",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ==========================================================
# TAB 2: MONTO Y TASA DE CONVERSIÓN POR ASESOR
# ==========================================================
with tab_ase:
    res_ase = calcular_tabla_conversion(df_f, ["Asesor"]).sort_values("Monto_Vendido", ascending=False)
    suc_modo = df_f.groupby("Asesor")["Sucursal"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "").reset_index()
    res_ase = res_ase.merge(suc_modo, on="Asesor", how="left")

    c_a1, c_a2 = st.columns(2)
    with c_a1:
        st.markdown("#### Monto Cotizado por Asesor y Estatus (MXN)")
        if ALTAIR_OK:
            top_asesores = res_ase.sort_values("Total_MXN", ascending=False).head(15)["Asesor"].tolist()
            ase_est = (
                df_f[df_f["Asesor"].isin(top_asesores)]
                .groupby(["Asesor", "Estatus"], as_index=False)
                .agg(Total_MXN=("Total_MXN", "sum"), Folios=("Folio", "count"))
            )
            chart_ase = (
                alt.Chart(ase_est)
                .mark_bar(cornerRadiusEnd=3)
                .encode(
                    x=alt.X("Total_MXN:Q", title="Monto ($ MXN)"),
                    y=alt.Y("Asesor:N", sort=top_asesores, title=""),
                    color=alt.Color("Estatus:N", scale=alt.Scale(**ESCALA_ESTATUS), legend=alt.Legend(orient="top")),
                    tooltip=[
                        alt.Tooltip("Asesor:N", title="Asesor"),
                        alt.Tooltip("Estatus:N", title="Estatus"),
                        alt.Tooltip("Folios:Q", title="Folios"),
                        alt.Tooltip("Total_MXN:Q", title="Monto MXN", format="$,.2f"),
                    ],
                )
                .properties(height=330)
            )
            st.altair_chart(chart_ase, use_container_width=True)
        else:
            st.bar_chart(res_ase.head(15).set_index("Asesor")[["Total_MXN", "Monto_Vendido"]])

    with c_a2:
        st.markdown("#### Tasa de Conversión por Asesor (% Folios Vendidos)")
        if ALTAIR_OK:
            chart_conv_ase = (
                alt.Chart(res_ase.sort_values("Conv_Folios_Pct", ascending=False).head(15))
                .mark_bar(color=COLOR_DORADO, cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Conv_Folios_Pct:Q", title="Conversión (%)", scale=alt.Scale(domain=[0, 100])),
                    y=alt.Y("Asesor:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("Asesor:N", title="Asesor"),
                        alt.Tooltip("Sucursal:N", title="Sucursal"),
                        alt.Tooltip("Vendidas:Q", title="Vendidas"),
                        alt.Tooltip("Con_Factura:Q", title="Con Factura SAE"),
                        alt.Tooltip("Folios:Q", title="Total Folios"),
                        alt.Tooltip("Conv_Folios_Pct:Q", title="Conv. Folios %", format=".1f"),
                        alt.Tooltip("Conv_Monto_Pct:Q", title="Conv. Monto %", format=".1f"),
                    ],
                )
                .properties(height=330)
            )
            st.altair_chart(chart_conv_ase, use_container_width=True)
        else:
            st.bar_chart(res_ase.head(15).set_index("Asesor")["Conv_Folios_Pct"])

    st.markdown("#### Desempeño y Conversión Detallada por Asesor")
    df_ase_show = res_ase[[
        "Asesor", "Sucursal", "Folios", "Cotizadas", "Vendidas", "Con_Factura", "Canceladas",
        "Conv_Folios_Pct", "Total_MXN", "Monto_Vendido", "Conv_Monto_Pct", "Ticket_Promedio", "Desc_N1"
    ]].copy()
    df_ase_show["Conv_Folios_Pct"] = df_ase_show["Conv_Folios_Pct"].map(lambda v: f"{v:.1f}%")
    df_ase_show["Conv_Monto_Pct"] = df_ase_show["Conv_Monto_Pct"].map(lambda v: f"{v:.1f}%")
    for col_m in ["Total_MXN", "Monto_Vendido", "Ticket_Promedio", "Desc_N1"]:
        df_ase_show[col_m] = df_ase_show[col_m].map(lambda v: f"${v:,.2f}")
    st.dataframe(
        df_ase_show.rename(columns={
            "Con_Factura": "Con Fact. SAE",
            "Conv_Folios_Pct": "Conv. Folios",
            "Total_MXN": "Cotizado MXN",
            "Monto_Vendido": "Vendido MXN",
            "Conv_Monto_Pct": "Conv. Monto",
            "Ticket_Promedio": "Ticket Prom.",
            "Desc_N1": "Desc. N1",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ==========================================================
# TAB 3: PRODUCTOS MÁS COTIZADOS Y VENDIDOS
# ==========================================================
with tab_prod:
    if df_pf.empty:
        st.info("No se encontró desglose de partidas (`Datos_JSON`) en las cotizaciones filtradas.")
    else:
        p_col1, p_col2 = st.columns([2.2, 1.4])
        with p_col1:
            criterio_top = st.radio(
                "Ordenar Top de Productos por:",
                ["Monto Cotizado ($ MXN sin IVA)", "Cantidad de Piezas", "Frecuencia (Folios)"],
                horizontal=True,
            )
        with p_col2:
            solo_vendidas_prod = st.toggle("Ver solo productos de cotizaciones Vendidas", value=False)

        df_p_use = df_pf[df_pf["Estatus"] == "Vendida"].copy() if solo_vendidas_prod else df_pf.copy()

        if df_p_use.empty:
            st.info("No hay partidas con estatus Vendida en el rango seleccionado.")
        else:
            col_ord = {
                "Monto Cotizado ($ MXN sin IVA)": "Importe_Neto",
                "Cantidad de Piezas": "Cantidad",
                "Frecuencia (Folios)": "Folios",
            }[criterio_top]

            res_prod = (
                df_p_use.groupby(["Clave", "Producto", "Familia"], as_index=False)
                .agg(
                    Folios=("Folio", "nunique"),
                    Cantidad=("Cantidad", "sum"),
                    Importe_Neto=("Importe_Neto", "sum"),
                )
                .sort_values(col_ord, ascending=False)
            )
            total_neto_prod = float(res_prod["Importe_Neto"].sum())
            res_prod["Participacion_Pct"] = (res_prod["Importe_Neto"] / total_neto_prod * 100.0) if total_neto_prod > 0 else 0.0
            res_prod["Etiqueta"] = res_prod["Clave"] + " — " + res_prod["Producto"].str.slice(0, 32)

            st.markdown(f"#### Top 10 Productos ({'Vendidos' if solo_vendidas_prod else 'Cotizados'} — {criterio_top})")
            top10 = res_prod.head(10)
            if ALTAIR_OK:
                chart_prod = (
                    alt.Chart(top10)
                    .mark_bar(color=COLOR_VERDE if solo_vendidas_prod else COLOR_AZUL_PRIMARIO, cornerRadiusEnd=4)
                    .encode(
                        x=alt.X(f"{col_ord}:Q", title=criterio_top),
                        y=alt.Y("Etiqueta:N", sort="-x", title=""),
                        tooltip=[
                            alt.Tooltip("Clave:N", title="Clave"),
                            alt.Tooltip("Producto:N", title="Producto"),
                            alt.Tooltip("Familia:N", title="Familia"),
                            alt.Tooltip("Folios:Q", title="Folios"),
                            alt.Tooltip("Cantidad:Q", title="Piezas", format=",.0f"),
                            alt.Tooltip("Importe_Neto:Q", title="Importe Neto (s/IVA)", format="$,.2f"),
                        ],
                    )
                    .properties(height=340)
                )
                st.altair_chart(chart_prod, use_container_width=True)
            else:
                st.bar_chart(top10.set_index("Clave")[col_ord])

            c_fam, c_niv = st.columns([1.4, 1.0])
            with c_fam:
                st.markdown("#### Mezcla por Familia de Materiales")
                res_fam = (
                    df_p_use.groupby("Familia", as_index=False)
                    .agg(Folios=("Folio", "nunique"), Piezas=("Cantidad", "sum"), Importe_Neto=("Importe_Neto", "sum"))
                    .sort_values("Importe_Neto", ascending=False)
                )
                res_fam["% Mezcla"] = (res_fam["Importe_Neto"] / total_neto_prod * 100.0).map(lambda v: f"{v:.1f}%")
                res_fam["Importe_Neto"] = res_fam["Importe_Neto"].map(lambda v: f"${v:,.2f}")
                res_fam["Piezas"] = res_fam["Piezas"].map(lambda v: f"{v:,.0f}")
                st.dataframe(res_fam.rename(columns={"Importe_Neto": "Importe (s/IVA)"}), use_container_width=True, hide_index=True)

            with c_niv:
                st.markdown("#### Distribución Interna por Nivel")
                res_niv = (
                    df_p_use.groupby("Nivel", as_index=False)
                    .agg(Partidas=("Clave", "count"), Importe_Neto=("Importe_Neto", "sum"))
                    .sort_values("Nivel")
                )
                res_niv["% Monto"] = (res_niv["Importe_Neto"] / total_neto_prod * 100.0).map(lambda v: f"{v:.1f}%")
                res_niv["Importe_Neto"] = res_niv["Importe_Neto"].map(lambda v: f"${v:,.2f}")
                st.dataframe(res_niv.rename(columns={"Importe_Neto": "Importe (s/IVA)"}), use_container_width=True, hide_index=True)

            st.markdown("#### Catálogo Detallado de Productos (Top 25)")
            df_p_show = res_prod.head(25)[["Clave", "Producto", "Familia", "Folios", "Cantidad", "Importe_Neto", "Participacion_Pct"]].copy()
            df_p_show["Cantidad"] = df_p_show["Cantidad"].map(lambda v: f"{v:,.0f}")
            df_p_show["Importe_Neto"] = df_p_show["Importe_Neto"].map(lambda v: f"${v:,.2f}")
            df_p_show["Participacion_Pct"] = df_p_show["Participacion_Pct"].map(lambda v: f"{v:.1f}%")
            st.dataframe(
                df_p_show.rename(columns={"Importe_Neto": "Importe (s/IVA)", "Participacion_Pct": "% Part."}),
                use_container_width=True,
                hide_index=True,
            )

# ==========================================================
# TAB 4: AUDITORÍA DE FACTURAS SAE, TENDENCIA Y EXPORTACIÓN
# ==========================================================
with tab_sae:
    st.markdown("#### 🧾 Lista de Ventas Reportadas para Cotejo en Aspel SAE")
    df_vendidas = df_f[df_f["Estatus"] == "Vendida"].copy()

    if df_vendidas.empty:
        st.info("No hay cotizaciones marcadas como Vendida en los filtros actuales.")
    else:
        sin_fac = df_vendidas[df_vendidas["No_Factura"] == ""]
        con_fac_series = df_vendidas[df_vendidas["No_Factura"] != ""]["No_Factura"]
        dups_fac = con_fac_series[con_fac_series.duplicated(keep=False)].unique().tolist()

        if len(sin_fac) > 0:
            st.warning(f"⚠️ Hay **{len(sin_fac)}** cotización(es) marcada(s) como Vendida sin folio de factura SAE registrado (registros previos al candado).")
        if dups_fac:
            st.error(f"🚨 Se detectaron folios de factura SAE repetidos en la hoja: **{', '.join(dups_fac)}**.")
        if len(sin_fac) == 0 and not dups_fac:
            st.success(f"✅ **100.0%** de las {len(df_vendidas)} ventas reportadas cuentan con folio de factura SAE único listo para cotejar en sistema.")

        df_sae_tbl = df_vendidas[["No_Factura", "Folio", "Fecha_Texto", "Sucursal", "Razon_Social", "Asesor", "Cliente", "Total_MXN"]].sort_values("Folio", ascending=False)
        st.dataframe(
            df_sae_tbl.assign(
                No_Factura=df_sae_tbl["No_Factura"].replace("", "⚠️ SIN FOLIO"),
                Total_MXN=df_sae_tbl["Total_MXN"].map(lambda v: f"${v:,.2f}")
            ).rename(columns={
                "No_Factura": "Factura SAE",
                "Fecha_Texto": "Fecha",
                "Razon_Social": "Razón Social",
                "Total_MXN": "Total MXN"
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    df_fechas = df_f.dropna(subset=["Fecha_Dia"]).copy()
    if not df_fechas.empty:
        st.markdown("#### 📈 Evolución Diaria por Estatus (MXN)")
        res_dia = (
            df_fechas.groupby(["Fecha_Dia", "Estatus"], as_index=False)
            .agg(Folios=("Folio", "count"), Total_MXN=("Total_MXN", "sum"))
            .sort_values("Fecha_Dia")
        )
        res_dia["Fecha_Str"] = res_dia["Fecha_Dia"].astype(str)
        if ALTAIR_OK:
            chart_dia = (
                alt.Chart(res_dia)
                .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("Fecha_Str:N", title="Fecha"),
                    y=alt.Y("Total_MXN:Q", title="Monto ($ MXN)"),
                    color=alt.Color("Estatus:N", scale=alt.Scale(**ESCALA_ESTATUS), legend=alt.Legend(orient="top")),
                    tooltip=[
                        alt.Tooltip("Fecha_Str:N", title="Fecha"),
                        alt.Tooltip("Estatus:N", title="Estatus"),
                        alt.Tooltip("Folios:Q", title="Cotizaciones"),
                        alt.Tooltip("Total_MXN:Q", title="Monto MXN", format="$,.2f"),
                    ],
                )
                .properties(height=270)
            )
            st.altair_chart(chart_dia, use_container_width=True)
        else:
            st.bar_chart(res_dia.pivot(index="Fecha_Str", columns="Estatus", values="Total_MXN").fillna(0))

    st.markdown("#### Base Completa Filtrada de Cotizaciones")
    cols_exp = [
        "Folio", "Estatus", "No_Factura", "Fecha_Texto", "Sucursal", "Razon_Social", "Asesor",
        "Cliente", "Partidas", "Subtotal", "IVA", "Total_MXN", "Ahorro_Volumen", "Desc_Especial_N1"
    ]
    df_export = df_f[cols_exp].sort_values("Folio", ascending=False)
    st.dataframe(
        df_export.assign(
            No_Factura=df_export["No_Factura"].replace("", "—"),
            Subtotal=df_export["Subtotal"].map(lambda v: f"${v:,.2f}"),
            IVA=df_export["IVA"].map(lambda v: f"${v:,.2f}"),
            Total_MXN=df_export["Total_MXN"].map(lambda v: f"${v:,.2f}"),
            Ahorro_Volumen=df_export["Ahorro_Volumen"].map(lambda v: f"${v:,.2f}"),
            Desc_Especial_N1=df_export["Desc_Especial_N1"].map(lambda v: f"${v:,.2f}"),
        ).rename(columns={
            "No_Factura": "Factura SAE",
            "Fecha_Texto": "Fecha",
            "Razon_Social": "Razón Social",
            "Total_MXN": "Total MXN",
            "Ahorro_Volumen": "Ahorro Vol.",
            "Desc_Especial_N1": "Desc. N1",
        }),
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = df_export.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ EXPORTAR REPORTE CON FACTURAS SAE A EXCEL (CSV)",
        data=csv_bytes,
        file_name=f"Dashboard_Auditoria_SAE_IMAC_{ahora_mx().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )
