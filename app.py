import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# --- CONFIGURACIÓN INICIAL Y CONEXIÓN A GOOGLE SHEETS ---

st.set_page_config(
    page_title="Gestor de Negocio Pro",
    page_icon="🚀",
    layout="wide"
)

# Estructura de datos para productos y tallas
PRODUCTOS = {
    "Bata Short": ["S", "M", "L", "XL"],
    "Bata Pantalon": ["S", "M", "L", "XL"],
    "Bata": ["S", "M", "L", "XL"],
    "Boxer": ["S", "M", "L", "XL"],
    "Medias Corta": ["Talla Unica"],
    "Medias Larga": ["Talla Unica"]
}

# --- CONEXIÓN A GOOGLE SHEETS ---
@st.cache_resource
def connect_to_gsheets():
    """Conecta a Google Sheets y devuelve los objetos de las hojas."""
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    try:
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    except FileNotFoundError:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    
    client = gspread.authorize(creds)
    
    try:
        spreadsheet = client.open("BaseDeDatos_Negocio")
        return {
            "ventas": spreadsheet.worksheet("Ventas"),
            "compras": spreadsheet.worksheet("Compras"),
            "inventario": spreadsheet.worksheet("Inventario")
        }
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("🚨 No se encontró la hoja de cálculo 'BaseDeDatos_Negocio'. Asegúrate de que exista y esté compartida.")
        st.stop()

sheets = connect_to_gsheets()

# --- FUNCIONES AUXILIARES ---

def get_data(sheet):
    """Obtiene datos de una hoja y los devuelve como DataFrame."""
    records = sheet.get_all_records()
    if not records:
        headers = sheet.row_values(1)
        return pd.DataFrame(columns=headers)
    return pd.DataFrame(records)

def actualizar_inventario():
    """Recalcula y actualiza el inventario basándose en un SKU (Producto + Talla)."""
    compras_df = get_data(sheets["compras"])
    ventas_df = get_data(sheets["ventas"])

    if compras_df.empty and ventas_df.empty:
        sheets["inventario"].clear()
        sheets["inventario"].update([["SKU", "Producto", "Talla", "Unidades Compradas", "Unidades Vendidas", "Stock Actual", "Fecha Actualizacion"]])
        return pd.DataFrame()

    if not compras_df.empty:
        compras_df['SKU'] = compras_df['Producto'].astype(str) + " - " + compras_df['Talla'].astype(str)
        stock_comprado = compras_df.groupby('SKU')['Cantidad'].sum().reset_index().rename(columns={'Cantidad': 'Unidades Compradas'})
    else:
        stock_comprado = pd.DataFrame(columns=['SKU', 'Unidades Compradas'])

    if not ventas_df.empty:
        ventas_df['SKU'] = ventas_df['Producto'].astype(str) + " - " + ventas_df['Talla'].astype(str)
        stock_vendido = ventas_df.groupby('SKU')['Cantidad'].sum().reset_index().rename(columns={'Cantidad': 'Unidades Vendidas'})
    else:
        stock_vendido = pd.DataFrame(columns=['SKU', 'Unidades Vendidas'])

    inventario_df = pd.merge(stock_comprado, stock_vendido, on='SKU', how='outer').fillna(0)
    inventario_df[['Producto', 'Talla']] = inventario_df['SKU'].str.split(' - ', expand=True)
    inventario_df['Stock Actual'] = inventario_df['Unidades Compradas'] - inventario_df['Unidades Vendidas']
    inventario_df['Fecha Actualizacion'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    column_order = ["SKU", "Producto", "Talla", "Unidades Compradas", "Unidades Vendidas", "Stock Actual", "Fecha Actualizacion"]
    inventario_df = inventario_df[column_order]

    sheets["inventario"].clear()
    sheets["inventario"].update([inventario_df.columns.values.tolist()] + inventario_df.values.tolist())
    return inventario_df

# --- INICIALIZACIÓN DEL ESTADO DE SESIÓN ---
if 'compra_actual' not in st.session_state:
    st.session_state.compra_actual = []

# --- INTERFAZ DE LA APLICACIÓN ---

st.title("🚀 Gestor de Negocio Pro")
st.markdown("---")

opcion = st.sidebar.radio(
    "Selecciona una opción:", 
    ["📈 Ver Inventario", "💰 Registrar Venta", "🛒 Registrar Compra", "📊 Finanzas"]
)

# --- PESTAÑA DE VENTAS ---
if opcion == "💰 Registrar Venta":
    st.header("Formulario de Registro de Ventas")
    with st.form("venta_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("Nombre del Cliente")
            producto_vendido = st.selectbox("Producto", options=list(PRODUCTOS.keys()), key="venta_prod")
            talla_vendida = st.selectbox("Talla", options=PRODUCTOS[producto_vendido], key="venta_talla")
        with col2:
            cantidad_vendida = st.number_input("Cantidad Vendida", min_value=1, step=1)
            precio_unitario = st.number_input("Precio Unitario ($)", min_value=0.0, format="%.2f")
            estado_pago = st.selectbox("Estado del Pago", ["Pagado", "Abono", "Debe"])
        
        total_venta = cantidad_vendida * precio_unitario
        st.info(f"**Total de la Venta: ${total_venta:,.2f}**")

        if st.form_submit_button("Registrar Venta"):
            if not cliente or not producto_vendido:
                st.warning("Por favor, completa todos los campos.")
            else:
                fecha_venta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                nueva_venta = [fecha_venta, producto_vendido, talla_vendida, cliente, cantidad_vendida, precio_unitario, total_venta, estado_pago]
                sheets["ventas"].append_row(nueva_venta)
                st.success("✅ ¡Venta registrada exitosamente!")
                st.balloons()
                actualizar_inventario()

# --- PESTAÑA DE COMPRAS (LÓGICA MEJORADA) ---
elif opcion == "🛒 Registrar Compra":
    st.header("Formulario de Registro de Compras")
    st.markdown("Añade uno o más productos a una orden de compra y regístrala con un solo costo de envío.")

    # Formulario para añadir un item a la compra
    with st.form("item_compra_form"):
        st.subheader("Añadir Producto a la Orden")
        col1, col2, col3 = st.columns(3)
        with col1:
            producto_comprado = st.selectbox("Producto", options=list(PRODUCTOS.keys()), key="compra_prod")
        with col2:
            talla_comprada = st.selectbox("Talla", options=PRODUCTOS[producto_comprado], key="compra_talla")
        with col3:
            cantidad_comprada = st.number_input("Cantidad", min_value=1, step=1)
            costo_unitario = st.number_input("Costo Unitario ($)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("➕ Añadir Producto a la Compra"):
            item = {
                "Producto": producto_comprado,
                "Talla": talla_comprada,
                "Cantidad": cantidad_comprada,
                "Costo Total": cantidad_comprada * costo_unitario
            }
            st.session_state.compra_actual.append(item)
            st.success(f"Añadido: {cantidad_comprada} x {producto_comprado} ({talla_comprada})")

    # Mostrar la orden de compra actual
    if st.session_state.compra_actual:
        st.markdown("---")
        st.subheader("Orden de Compra Actual")
        df_compra_actual = pd.DataFrame(st.session_state.compra_actual)
        st.dataframe(df_compra_actual, use_container_width=True)

        with st.form("finalizar_compra_form"):
            col1, col2 = st.columns(2)
            with col1:
                proveedor = st.text_input("Nombre del Proveedor")
            with col2:
                costo_envio = st.number_input("Costo Total del Envío ($)", min_value=0.0, format="%.2f")

            if st.form_submit_button("✅ Registrar Compra Completa en Google Sheets"):
                if not proveedor:
                    st.warning("Por favor, ingresa el nombre del proveedor.")
                else:
                    with st.spinner("Registrando compra..."):
                        id_compra = f"COMPRA-{uuid.uuid4().hex[:8].upper()}"
                        fecha_compra = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        filas_para_añadir = []
                        for item in st.session_state.compra_actual:
                            fila = [
                                id_compra,
                                fecha_compra,
                                item["Producto"],
                                item["Talla"],
                                proveedor,
                                item["Cantidad"],
                                item["Costo Total"],
                                costo_envio
                            ]
                            filas_para_añadir.append(fila)
                        
                        sheets["compras"].append_rows(filas_para_añadir)
                        st.success(f"¡Compra {id_compra} registrada exitosamente con {len(filas_para_añadir)} productos!")
                        st.balloons()
                        st.session_state.compra_actual = [] # Limpiar el carrito
                        actualizar_inventario()
                        st.experimental_rerun()

# --- PESTAÑA DE INVENTARIO ---
elif opcion == "📈 Ver Inventario":
    st.header("Vista del Inventario Actual")
    if st.button("🔄 Refrescar Inventario"):
        with st.spinner("Actualizando..."):
            actualizar_inventario()
    
    inventario_df = get_data(sheets["inventario"])
    if not inventario_df.empty:
        st.dataframe(inventario_df, use_container_width=True)
    else:
        st.info("No hay datos de inventario. Registra compras para empezar.")

# --- PESTAÑA DE FINANZAS (LÓGICA MEJORADA) ---
elif opcion == "📊 Finanzas":
    st.header("Análisis Financiero Mensual")
    ventas_df = get_data(sheets["ventas"])
    compras_df = get_data(sheets["compras"])

    if ventas_df.empty and compras_df.empty:
        st.info("No hay datos de ventas o compras para analizar.")
    else:
        if not ventas_df.empty:
            ventas_df['Fecha'] = pd.to_datetime(ventas_df['Fecha'])
            ventas_df['Mes'] = ventas_df['Fecha'].dt.to_period('M').astype(str)
        if not compras_df.empty:
            compras_df['Fecha'] = pd.to_datetime(compras_df['Fecha'])
            compras_df['Mes'] = compras_df['Fecha'].dt.to_period('M').astype(str)
        
        meses_disponibles = sorted(pd.concat([ventas_df.get('Mes'), compras_df.get('Mes')]).dropna().unique(), reverse=True)
        if not meses_disponibles:
             st.warning("No hay datos con fechas válidas para generar el reporte.")
             st.stop()

        mes_seleccionado = st.selectbox("Selecciona un Mes para Analizar", options=["Todos"] + meses_disponibles)

        if mes_seleccionado != "Todos":
            ventas_filtradas = ventas_df[ventas_df['Mes'] == mes_seleccionado] if not ventas_df.empty else pd.DataFrame()
            compras_filtradas = compras_df[compras_df['Mes'] == mes_seleccionado] if not compras_df.empty else pd.DataFrame()
        else:
            ventas_filtradas = ventas_df
            compras_filtradas = compras_df
        
        total_ingresos = pd.to_numeric(ventas_filtradas['Total Venta']).sum()
        
        # Lógica de gastos mejorada para no sumar el envío múltiples veces
        total_costo_producto = pd.to_numeric(compras_filtradas['Costo Total']).sum()
        if not compras_filtradas.empty and 'ID Compra' in compras_filtradas.columns:
            # Sumar el costo de envío solo una vez por cada ID de Compra único
            total_costo_envio = pd.to_numeric(compras_filtradas.drop_duplicates(subset=['ID Compra'])['Costo Envio']).sum()
        else:
            total_costo_envio = 0

        total_gastos = total_costo_producto + total_costo_envio
        ganancia = total_ingresos - total_gastos

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Ingresos por Ventas", f"${total_ingresos:,.2f}")
        col2.metric("💸 Gastos Totales", f"${total_gastos:,.2f}")
        col3.metric("📈 Ganancia Bruta", f"${ganancia:,.2f}", delta=f"{ganancia:,.2f} {'✅' if ganancia >= 0 else '🔻'}")

        st.markdown("---")
        st.subheader(f"Detalle para: {mes_seleccionado}")
        
        exp_ventas = st.expander("Ver detalle de ventas")
        exp_ventas.dataframe(ventas_filtradas)

        exp_compras = st.expander("Ver detalle de compras")
        exp_compras.dataframe(compras_filtradas)
