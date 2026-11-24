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
    obtener_nuevo_folio,
    enviar_respaldo_correo,
    calcular_nivel_y_precio,
    calcular_totales_carrito,
    generar_pdf_mostrador,
)

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

# --- ESTADO DEL CARRITO ---
if "carrito_ligeros" not in st.session_state:
    st.session_state["carrito_ligeros"] = []

# --- PERFIL ACTIVO DE SUCURSAL Y ASESOR (JALADO DE Usuarios) ---
lista_suc = list(CONFIG_SUCURSALES.keys())
sucursal_sel = st.session_state.get("sucursal_activa", "IMAC")
if sucursal_sel not in lista_suc:
    sucursal_sel = lista_suc[0]
suc_info_activa = CONFIG_SUCURSALES[sucursal_sel]

asesor_nombre_db = st.session_state.get("nombre_asesor") or st.session_state.get("usuario", "MOSTRADOR").upper()
asesor_tel_db = st.session_state.get("telefono_asesor", "")
asesor_correo_db = st.session_state.get("correo_asesor", "")

with st.sidebar:
    st.markdown(f"**🏢 Sucursal:** {sucursal_sel}")
    st.caption(f"🏛️ {suc_info_activa['razon_social']}")
    st.caption(f"👤 {asesor_nombre_db} ({st.session_state.get('role', '')})")
    st.caption(f"📦 Catálogo activo: **{len(CATALOGO_LIGEROS)} SKUs**")

# --- ENCABEZADO PRINCIPAL ---
col_logo, col_tit = st.columns([1, 5])
with col_logo:
    if os.path.exists("logo_imac_2026.png"):
        st.image(Image.open("logo_imac_2026.png"), use_container_width=True)
    else:
        st.markdown("### 🏢 IMAC")
with col_tit:
    st.title(f"Cotizador Mostrador — {suc_info_activa['sucursal_corta']}")
    st.caption(f"{suc_info_activa['razon_social']} | RFC: {suc_info_activa['rfc']} | BBVA Cta: {suc_info_activa['cuenta']}")
st.markdown("---")

# --- 1. DATOS DEL CLIENTE ---
c1, c2, c3, c4, c5 = st.columns([2.2, 1.3, 1.6, 1.5, 1.2])
with c1: cliente = st.text_input("En atención a (Cliente / Empresa)", placeholder="Ej. Constructora del Golfo")
with c2: telefono = st.text_input("Teléfono Cliente", placeholder="229...")
with c3: correo_cli = st.text_input("Correo del Cliente (Opcional)", placeholder="cliente@correo.com")
with c4: asesor = st.text_input("Asesor (desde Usuarios)", value=asesor_nombre_db)
with c5: fecha_validez = st.date_input("Precios válidos al", value=datetime.date.today() + datetime.timedelta(days=7))

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
            f"Tabulador interno MXN — **N1:** ${info_sel['n1']:,.2f} | "
            f"**N2:** ${info_sel['n2']:,.2f} | **N3:** ${info_sel['n3']:,.2f}"
        )
    with p2:
        cant_sel = st.number_input("Cantidad", min_value=1.0, value=10.0, step=1.0)
    with p3:
        nivel_calc, precio_calc, _ = calcular_nivel_y_precio(clave_sel, cant_sel)
        ahorro_unit = info_sel["n1"] - precio_calc
        delta_txt = f"-${ahorro_unit:,.2f}/u" if ahorro_unit > 0 else "Precio Lista"
        st.metric(f"{nivel_calc} (Interno)", f"${precio_calc:,.2f}", delta_txt)
    with p4:
        st.write("")
        st.write("")
        if st.button("➕ Agregar", type="primary", use_container_width=True):
            existente = next((x for x in st.session_state["carrito_ligeros"] if x["clave"] == clave_sel), None)
            if existente:
                nueva_cant = existente["cantidad"] + cant_sel
                niv_n, prec_n, _ = calcular_nivel_y_precio(clave_sel, nueva_cant)
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
                    "precio_unit": precio_calc,
                    "desc_pct": 0.0
                })
            st.rerun()
else:
    st.warning("No se encontraron materiales con ese filtro.")

# --- 3. CARRITO ACTIVO Y RESUMEN FINANCIERO ---
if st.session_state["carrito_ligeros"]:
    st.markdown("### 📋 Partidas en la Cotización (Vista Interna)")
    for item in st.session_state["carrito_ligeros"]:
        niv, prec, _ = calcular_nivel_y_precio(item["clave"], item["cantidad"])
        item["nivel"] = niv
        item["precio_unit"] = prec

    tiene_nivel_3 = any(x["nivel"] == "NIVEL 3" for x in st.session_state["carrito_ligeros"])

    df_carrito = pd.DataFrame([
        {
            "Clave": x["clave"],
            "Producto": x["producto"],
            "Cantidad": x["cantidad"],
            "Nivel (Interno)": x["nivel"],
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

    # --- REGLA DE DESCUENTO: SOLO VISIBLE EN NIVEL 1 Y NIVEL 2 (MÁX. 10%) ---
    if tiene_nivel_3:
        desc_extra_pct = 0.0
        a1, a3 = st.columns([1.4, 3.6])
        with a1:
            flete = st.number_input("🚚 Flete / Envío ($ MXN)", min_value=0.0, value=0.0, step=100.0)
        with a3:
            notas = st.text_input("Observaciones en PDF", placeholder="Ej. Tiempo de entrega o indicaciones especiales...")
        st.info("🔒 **Descuento adicional deshabilitado:** esta cotización ya incluye precios preferenciales de **Nivel 3 (Mayoreo)**.")
    else:
        a1, a2, a3 = st.columns([1.2, 1.2, 2.6])
        with a1:
            flete = st.number_input("🚚 Flete / Envío ($ MXN)", min_value=0.0, value=0.0, step=100.0)
        with a2:
            desc_extra_pct = st.number_input("🏷️ Descuento Adicional (%, máx 10%)", min_value=0.0, max_value=MAX_DESC_PCT, value=0.0, step=0.5)
        with a3:
            notas = st.text_input("Observaciones en PDF", placeholder="Ej. Tiempo de entrega o indicaciones especiales...")

    tot_calc = calcular_totales_carrito(st.session_state["carrito_ligeros"], flete, desc_extra_pct, PRECIOS_INCLUYEN_IVA)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Subtotal", f"${tot_calc['subtotal_sin_iva']:,.2f}")
    k2.metric("IVA (16%)", f"${tot_calc['iva_monto']:,.2f}")
    k3.metric("Ahorro por Volumen", f"${tot_calc['ahorro_nivel']:,.2f}")
    k4.metric("TOTAL MXN", f"${tot_calc['total_final']:,.2f}")

    enviar_correo_chk = st.checkbox("📧 Enviar copia PDF por correo", value=False)

    if st.button("📄 GENERAR COTIZACIÓN PDF Y GUARDAR EN DRIVE", type="primary", use_container_width=True):
        with st.spinner("Generando folio, registrando en Google Sheets y ensamblando PDF personalizado..."):
            doc = conectar_sheets()
            prefijo = suc_info_activa.get("prefijo_folio", "IMAC")
            folio_actual = obtener_nuevo_folio(doc, prefijo)
            cliente_final = cliente.strip() if cliente.strip() else "MOSTRADOR"
            asesor_final = asesor.strip() if asesor.strip() else asesor_nombre_db

            pdf_bytes, tot_pdf, sub_pdf, iva_pdf, ahorr_pdf, _ = generar_pdf_mostrador(
                folio=folio_actual,
                sucursal_nombre=sucursal_sel,
                suc_info=suc_info_activa,
                cliente=cliente_final,
                telefono_cli=telefono,
                correo_cli=correo_cli,
                asesor_nombre=asesor_final,
                asesor_telefono=asesor_tel_db,
                asesor_correo=asesor_correo_db,
                validez=fecha_validez,
                carrito=st.session_state["carrito_ligeros"],
                flete=flete,
                desc_extra_pct=desc_extra_pct,
                precios_incluyen_iva=PRECIOS_INCLUYEN_IVA,
                notas=notas,
                mostrar_col_desc=False
            )

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
                        "precios_incluyen_iva": PRECIOS_INCLUYEN_IVA,
                        "notas": notas,
                        "correo_cliente": correo_cli,
                        "vigencia": fecha_validez.strftime("%d/%m/%Y"),
                        "asesor_telefono": asesor_tel_db,
                        "asesor_correo": asesor_correo_db
                    }, ensure_ascii=False)

                    hoja_cot.append_row([
                        folio_actual, fecha_reg, sucursal_sel, asesor_final,
                        cliente_final.upper(), telefono, len(st.session_state["carrito_ligeros"]),
                        resumen_partidas, round(sub_pdf, 2), round(iva_pdf, 2),
                        round(tot_pdf, 2), round(ahorr_pdf, 2), payload_json
                    ])
                    registrar_bitacora(
                        doc,
                        "Cotizador Mostrador",
                        f"Generó {folio_actual} ({sucursal_sel} - {suc_info_activa['razon_social']}) por ${tot_pdf:,.2f} MXN"
                    )
                except Exception as e:
                    st.warning(f"⚠️ PDF creado, pero ocurrió un error al guardar en Google Sheets: {e}")

            nombre_pdf = f"Cotizacion_{folio_actual}_{cliente_final.replace(' ', '_')}.pdf"

            if enviar_correo_chk:
                destinos = [asesor_correo_db or suc_info_activa["correo"]]
                if suc_info_activa["correo"] not in destinos:
                    destinos.append(suc_info_activa["correo"])
                if correo_cli.strip():
                    destinos.append(correo_cli.strip())
                dest_str = ", ".join(destinos)
                ok_mail, msg_mail = enviar_respaldo_correo(
                    pdf_bytes, nombre_pdf, folio_actual, sucursal_sel,
                    cliente_final, asesor_final, tot_pdf, dest_str, es_edicion=False
                )
                if ok_mail:
                    st.info(f"📧 Copia enviada correctamente a: {dest_str}")
                else:
                    st.warning(f"⚠️ No se pudo enviar el correo: {msg_mail}")

        st.success(f"✅ Cotización **{folio_actual}** ({suc_info_activa['razon_social']}) guardada y lista para entrega.")
        st.download_button(
            label="⬇️ DESCARGAR COTIZACIÓN PDF",
            data=pdf_bytes,
            file_name=nombre_pdf,
            mime="application/pdf",
            use_container_width=True
        )
else:
    st.info("Selecciona uno o más materiales arriba para armar la cotización de mostrador.")
