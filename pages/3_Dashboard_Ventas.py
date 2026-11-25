import streamlit as st
import datetime
import json
import os
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

# --- PALETA CORPORATIVA (AZUL IMAC + DORADO EJECUTIVO) ---
COLOR_AZUL_PRIMARIO = "#0F3C8C"
COLOR_AZUL_CLARO = "#0096FF"
COLOR_DORADO = "#C9A227"

# --- FUNCIONES DE PARSEO Y CARGA ---
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

        flete = 0.0
        desc_global_pct = 0.0
        desc_n1_monto_total = 0.0
        piezas_folio = 0.0

        if datos_json_raw:
            try:
                payload = json.loads(datos_json_raw)
                flete = float(payload.get("flete", 0.0) or 0.0)
                desc_global_pct = float(payload.get("desc_extra_pct", 0.0) or 0.0)
                partidas_list = payload.get("partidas", [])

                for p in partidas_list:
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
            except Exception:
                pass

        registros_cot.append({
            "Folio": folio,
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
            "Ahorro_Volumen": round(ahorro_vol, 2),
            "Desc_Especial_N1": round(desc_n1_monto_total, 2),
            "Desc_Global_Pct": desc_global_pct
        })

    df_cot = pd.DataFrame(registros_cot)
    df_prod = pd.DataFrame(registros_prod)
    return df_cot, df_prod

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
    st.title("Dashboard Comercial — Sistemas Ligeros")
    st.caption(f"Monitoreo ejecutivo de cotizaciones por sucursal, asesor y mezcla de productos | Corte: {ahora_mx().strftime('%d/%m/%Y %H:%M hrs')}")
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

f1, f2, f3, f4, f5 = st.columns([1.1, 1.1, 1.6, 1.4, 1.4])
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

# Aplicar filtros al DataFrame de cotizaciones
mask = pd.Series(True, index=df_cot.index)
mask &= df_cot["Fecha_Dia"].isna() | ((df_cot["Fecha_Dia"] >= f_inicio) & (df_cot["Fecha_Dia"] <= f_fin))
if sel_razon != "TODAS":
    mask &= (df_cot["Razon_Social"] == sel_razon)
if sel_suc != "TODAS":
    mask &= (df_cot["Sucursal"] == sel_suc)
if sel_asesor != "TODOS":
    mask &= (df_cot["Asesor"] == sel_asesor)

df_f = df_cot[mask].copy()

if df_f.empty:
    st.warning("No hay cotizaciones que coincidan con los filtros seleccionados.")
    st.stop()

folios_activos = set(df_f["Folio"].tolist())
df_pf = df_prod[df_prod["Folio"].isin(folios_activos)].copy() if not df_prod.empty else pd.DataFrame()

# --- 3. KPIs EJECUTIVOS ---
monto_total = float(df_f["Total_MXN"].sum())
subtotal_total = float(df_f["Subtotal"].sum())
num_folios = int(len(df_f))
ticket_prom = monto_total / num_folios if num_folios > 0 else 0.0
ticket_mediano = float(df_f["Total_MXN"].median()) if num_folios > 0 else 0.0
partidas_prom = float(df_f["Partidas"].mean()) if num_folios > 0 else 0.0
ahorro_total = float(df_f["Ahorro_Volumen"].sum() + df_f["Desc_Especial_N1"].sum())
clientes_unicos = int(df_f["Cliente"].nunique())

st.markdown("---")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("💰 Monto Cotizado (c/IVA)", f"${monto_total:,.2f}", f"Sub: ${subtotal_total:,.2f}")
k2.metric("📄 Cotizaciones", f"{num_folios:,}", f"{clientes_unicos} clientes")
k3.metric("🎯 Ticket Promedio", f"${ticket_prom:,.2f}", f"Mediana: ${ticket_mediano:,.2f}")
k4.metric("📦 Partidas / Folio", f"{partidas_prom:.1f}", f"{int(df_f['Piezas'].sum()):,} pzas")
k5.metric("🏷️ Ahorro / Desc. N1", f"${ahorro_total:,.2f}", f"{(ahorro_total / subtotal_total * 100) if subtotal_total > 0 else 0.0:.1f}% s/sub")

st.markdown("---")

# --- 4. PESTAÑAS ANALÍTICAS ---
tab_suc, tab_ase, tab_prod, tab_tend = st.tabs([
    "🏢 Por Sucursal",
    "👤 Por Asesor",
    "📦 Productos Más Cotizados",
    "📈 Tendencia y Detalle"
])

# ==========================================================
# TAB 1: MONTO COTIZADO POR SUCURSAL Y RAZÓN SOCIAL
# ==========================================================
with tab_suc:
    res_suc = (
        df_f.groupby(["Sucursal", "Razon_Social"], as_index=False)
        .agg(
            Folios=("Folio", "count"),
            Subtotal=("Subtotal", "sum"),
            Total_MXN=("Total_MXN", "sum"),
            Ticket_Promedio=("Total_MXN", "mean"),
            Ticket_Mediano=("Total_MXN", "median"),
            Ahorro_Volumen=("Ahorro_Volumen", "sum"),
        )
        .sort_values("Total_MXN", ascending=False)
    )
    res_suc["Participacion_Pct"] = (res_suc["Total_MXN"] / monto_total * 100.0) if monto_total > 0 else 0.0

    c_left, c_right = st.columns([1.3, 1.0])
    with c_left:
        st.markdown("#### Monto Total Cotizado por Sucursal (MXN)")
        if ALTAIR_OK:
            chart_suc = (
                alt.Chart(res_suc)
                .mark_bar(color=COLOR_AZUL_PRIMARIO, cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Total_MXN:Q", title="Monto Cotizado ($ MXN)"),
                    y=alt.Y("Sucursal:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("Sucursal:N", title="Sucursal"),
                        alt.Tooltip("Razon_Social:N", title="Razón Social"),
                        alt.Tooltip("Folios:Q", title="Cotizaciones"),
                        alt.Tooltip("Total_MXN:Q", title="Total MXN", format="$,.2f"),
                        alt.Tooltip("Ticket_Promedio:Q", title="Ticket Promedio", format="$,.2f"),
                        alt.Tooltip("Participacion_Pct:Q", title="Participación %", format=".1f"),
                    ],
                )
                .properties(height=300)
            )
            st.altair_chart(chart_suc, use_container_width=True)
        else:
            st.bar_chart(res_suc.set_index("Sucursal")["Total_MXN"])

    with c_right:
        st.markdown("#### Consolidado por Razón Social")
        res_rs = (
            df_f.groupby("Razon_Social", as_index=False)
            .agg(
                Folios=("Folio", "count"),
                Total_MXN=("Total_MXN", "sum"),
                Ticket_Promedio=("Total_MXN", "mean"),
            )
            .sort_values("Total_MXN", ascending=False)
        )
        res_rs["Participacion"] = (res_rs["Total_MXN"] / monto_total * 100.0).map(lambda v: f"{v:.1f}%")
        st.dataframe(
            res_rs.assign(
                Total_MXN=res_rs["Total_MXN"].map(lambda v: f"${v:,.2f}"),
                Ticket_Promedio=res_rs["Ticket_Promedio"].map(lambda v: f"${v:,.2f}"),
            ).rename(columns={"Razon_Social": "Razón Social", "Total_MXN": "Total MXN", "Ticket_Promedio": "Ticket Prom."}),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### Tabla Comparativa por Sucursal")
    df_suc_show = res_suc.copy()
    df_suc_show["Subtotal"] = df_suc_show["Subtotal"].map(lambda v: f"${v:,.2f}")
    df_suc_show["Total_MXN"] = df_suc_show["Total_MXN"].map(lambda v: f"${v:,.2f}")
    df_suc_show["Ticket_Promedio"] = df_suc_show["Ticket_Promedio"].map(lambda v: f"${v:,.2f}")
    df_suc_show["Ticket_Mediano"] = df_suc_show["Ticket_Mediano"].map(lambda v: f"${v:,.2f}")
    df_suc_show["Ahorro_Volumen"] = df_suc_show["Ahorro_Volumen"].map(lambda v: f"${v:,.2f}")
    df_suc_show["Participacion_Pct"] = df_suc_show["Participacion_Pct"].map(lambda v: f"{v:.1f}%")
    st.dataframe(
        df_suc_show.rename(columns={
            "Razon_Social": "Razón Social",
            "Total_MXN": "Total MXN",
            "Ticket_Promedio": "Ticket Promedio",
            "Ticket_Mediano": "Ticket Mediano",
            "Ahorro_Volumen": "Ahorro Vol.",
            "Participacion_Pct": "% Part.",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ==========================================================
# TAB 2: MONTO COTIZADO Y TICKET PROMEDIO POR ASESOR
# ==========================================================
with tab_ase:
    res_ase = (
        df_f.groupby("Asesor", as_index=False)
        .agg(
            Sucursal_Principal=("Sucursal", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
            Folios=("Folio", "count"),
            Total_MXN=("Total_MXN", "sum"),
            Ticket_Promedio=("Total_MXN", "mean"),
            Ticket_Max=("Total_MXN", "max"),
            Desc_N1=("Desc_Especial_N1", "sum"),
        )
        .sort_values("Total_MXN", ascending=False)
    )
    res_ase["Participacion_Pct"] = (res_ase["Total_MXN"] / monto_total * 100.0) if monto_total > 0 else 0.0

    c_a1, c_a2 = st.columns(2)
    with c_a1:
        st.markdown("#### Ranking por Monto Cotizado (MXN)")
        if ALTAIR_OK:
            chart_ase = (
                alt.Chart(res_ase.head(15))
                .mark_bar(color=COLOR_AZUL_CLARO, cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Total_MXN:Q", title="Monto Cotizado ($ MXN)"),
                    y=alt.Y("Asesor:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("Asesor:N", title="Asesor"),
                        alt.Tooltip("Sucursal_Principal:N", title="Sucursal"),
                        alt.Tooltip("Folios:Q", title="Cotizaciones"),
                        alt.Tooltip("Total_MXN:Q", title="Total MXN", format="$,.2f"),
                        alt.Tooltip("Ticket_Promedio:Q", title="Ticket Promedio", format="$,.2f"),
                    ],
                )
                .properties(height=320)
            )
            st.altair_chart(chart_ase, use_container_width=True)
        else:
            st.bar_chart(res_ase.head(15).set_index("Asesor")["Total_MXN"])

    with c_a2:
        st.markdown("#### Ticket Promedio por Asesor (MXN)")
        if ALTAIR_OK:
            chart_tk = (
                alt.Chart(res_ase.sort_values("Ticket_Promedio", ascending=False).head(15))
                .mark_bar(color=COLOR_DORADO, cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Ticket_Promedio:Q", title="Ticket Promedio ($ MXN)"),
                    y=alt.Y("Asesor:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("Asesor:N", title="Asesor"),
                        alt.Tooltip("Ticket_Promedio:Q", title="Ticket Promedio", format="$,.2f"),
                        alt.Tooltip("Ticket_Max:Q", title="Ticket Máximo", format="$,.2f"),
                        alt.Tooltip("Folios:Q", title="Folios"),
                    ],
                )
                .properties(height=320)
            )
            st.altair_chart(chart_tk, use_container_width=True)
        else:
            st.bar_chart(res_ase.head(15).set_index("Asesor")["Ticket_Promedio"])

    st.markdown("#### Desempeño Detallado por Asesor")
    df_ase_show = res_ase.copy()
    df_ase_show["Total_MXN"] = df_ase_show["Total_MXN"].map(lambda v: f"${v:,.2f}")
    df_ase_show["Ticket_Promedio"] = df_ase_show["Ticket_Promedio"].map(lambda v: f"${v:,.2f}")
    df_ase_show["Ticket_Max"] = df_ase_show["Ticket_Max"].map(lambda v: f"${v:,.2f}")
    df_ase_show["Desc_N1"] = df_ase_show["Desc_N1"].map(lambda v: f"${v:,.2f}")
    df_ase_show["Participacion_Pct"] = df_ase_show["Participacion_Pct"].map(lambda v: f"{v:.1f}%")
    st.dataframe(
        df_ase_show.rename(columns={
            "Sucursal_Principal": "Sucursal",
            "Total_MXN": "Total MXN",
            "Ticket_Promedio": "Ticket Promedio",
            "Ticket_Max": "Ticket Máximo",
            "Desc_N1": "Desc. N1 Otorgado",
            "Participacion_Pct": "% Part.",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ==========================================================
# TAB 3: PRODUCTOS MÁS COTIZADOS (SKUs, FAMILIAS Y NIVELES)
# ==========================================================
with tab_prod:
    if df_pf.empty:
        st.info("No se encontró desglose de partidas (`Datos_JSON`) en las cotizaciones filtradas.")
    else:
        criterio_top = st.radio(
            "Ordenar Top de Productos por:",
            ["Monto Cotizado ($ MXN sin IVA)", "Cantidad de Piezas", "Frecuencia (Folios)"],
            horizontal=True,
        )
        col_ord = {
            "Monto Cotizado ($ MXN sin IVA)": "Importe_Neto",
            "Cantidad de Piezas": "Cantidad",
            "Frecuencia (Folios)": "Folios",
        }[criterio_top]

        res_prod = (
            df_pf.groupby(["Clave", "Producto", "Familia"], as_index=False)
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

        st.markdown(f"#### Top 10 Productos Más Cotizados ({criterio_top})")
        top10 = res_prod.head(10)
        if ALTAIR_OK:
            chart_prod = (
                alt.Chart(top10)
                .mark_bar(color=COLOR_AZUL_PRIMARIO, cornerRadiusEnd=4)
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
                df_pf.groupby("Familia", as_index=False)
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
                df_pf.groupby("Nivel", as_index=False)
                .agg(Partidas=("Clave", "count"), Importe_Neto=("Importe_Neto", "sum"))
                .sort_values("Nivel")
            )
            res_niv["% Monto"] = (res_niv["Importe_Neto"] / total_neto_prod * 100.0).map(lambda v: f"{v:.1f}%")
            res_niv["Importe_Neto"] = res_niv["Importe_Neto"].map(lambda v: f"${v:,.2f}")
            st.dataframe(res_niv.rename(columns={"Importe_Neto": "Importe (s/IVA)"}), use_container_width=True, hide_index=True)

        st.markdown("#### Catálogo Detallado de Productos Cotizados (Top 25)")
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
# TAB 4: TENDENCIA DIARIA Y EXPORTACIÓN A EXCEL (CSV)
# ==========================================================
with tab_tend:
    df_fechas = df_f.dropna(subset=["Fecha_Dia"]).copy()
    if not df_fechas.empty:
        st.markdown("#### Evolución Diaria del Monto Cotizado (MXN)")
        res_dia = (
            df_fechas.groupby("Fecha_Dia", as_index=False)
            .agg(Folios=("Folio", "count"), Total_MXN=("Total_MXN", "sum"))
            .sort_values("Fecha_Dia")
        )
        res_dia["Fecha_Str"] = res_dia["Fecha_Dia"].astype(str)
        if ALTAIR_OK:
            chart_dia = (
                alt.Chart(res_dia)
                .mark_area(
                    line={"color": COLOR_AZUL_PRIMARIO, "strokeWidth": 2.5},
                    color=alt.Gradient(
                        gradient="linear",
                        stops=[
                            alt.GradientStop(color="#E8F0FE", offset=0),
                            alt.GradientStop(color="#0096FF", offset=1),
                        ],
                        x1=1, x2=1, y1=1, y2=0,
                    ),
                    point={"color": COLOR_DORADO, "size": 55},
                )
                .encode(
                    x=alt.X("Fecha_Str:N", title="Fecha"),
                    y=alt.Y("Total_MXN:Q", title="Monto Cotizado ($ MXN)"),
                    tooltip=[
                        alt.Tooltip("Fecha_Str:N", title="Fecha"),
                        alt.Tooltip("Folios:Q", title="Cotizaciones"),
                        alt.Tooltip("Total_MXN:Q", title="Total MXN", format="$,.2f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(chart_dia, use_container_width=True)
        else:
            st.line_chart(res_dia.set_index("Fecha_Str")["Total_MXN"])

    st.markdown("#### Base Filtrada de Cotizaciones")
    cols_exp = ["Folio", "Fecha_Texto", "Sucursal", "Razon_Social", "Asesor", "Cliente", "Partidas", "Subtotal", "IVA", "Total_MXN", "Ahorro_Volumen", "Desc_Especial_N1"]
    df_export = df_f[cols_exp].sort_values("Folio", ascending=False)
    st.dataframe(
        df_export.assign(
            Subtotal=df_export["Subtotal"].map(lambda v: f"${v:,.2f}"),
            IVA=df_export["IVA"].map(lambda v: f"${v:,.2f}"),
            Total_MXN=df_export["Total_MXN"].map(lambda v: f"${v:,.2f}"),
            Ahorro_Volumen=df_export["Ahorro_Volumen"].map(lambda v: f"${v:,.2f}"),
            Desc_Especial_N1=df_export["Desc_Especial_N1"].map(lambda v: f"${v:,.2f}"),
        ).rename(columns={
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
        label="⬇️ EXPORTAR REPORTE FILTRADO A EXCEL (CSV)",
        data=csv_bytes,
        file_name=f"Dashboard_Cotizaciones_IMAC_{ahora_mx().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )
