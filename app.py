import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(
    page_title="Gestor de Negocio Dinámico",
    page_icon="🌟",
    layout="wide"
)

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
            "inventario": spreadsheet.worksheet("Inventario"),
            "productos": spreadsheet.worksheet("Productos"),
            "clientes": spreadsheet.worksheet("Clientes"),
            "proveedores": spreadsheet.worksheet("Proveedores")
        }
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("🚨 No se encontró la hoja de cálculo 'BaseDeDatos_Negocio'. Asegúrate de que exista y esté compartida.")
        st.stop()

sheets = connect_to_gsheets()

# --- CARGA DE DATOS MAESTROS (Productos, Clientes, Proveedores) ---
@st.cache_data(ttl=600)
def load_master_data():
    """Carga los datos de las hojas de gestión y los procesa."""
    productos_df = pd.DataFrame(sheets["productos"].get_all_records())
    clientes_df = pd.DataFrame(sheets["clientes"].get_all_records())
    proveedores_df = pd.DataFrame(sheets["proveedores"].get_all_records())
    
    # Procesar productos para crear el diccionario dinámico
    productos_dict = {}
    if not productos_df.empty:
        for index, row in productos_df.iterrows():
            tallas = [t.strip() for t in str(row['TallasDisponibles']).split(',')]
            productos_dict[row['NombreProducto']] = tallas
            
    return productos_df, productos_dict, clientes_df, proveedores_df

productos_df, PRODUCTOS, clientes_df, proveedores_df = load_master_data()

# --- FUNCIONES AUXILIARES ---
def get_data(sheet_name):
    """Obtiene datos de una hoja y los devuelve como DataFrame."""
    records = sheets[sheet_name].get_all_records()
    if not records:
        headers = sheets[sheet_name].row_values(1)
        return pd.DataFrame(columns=headers)
    return pd.DataFrame(records)

def actualizar_inventario():
    # (El código de esta función no cambia, se deja igual)
    compras_df = get_data("compras")
    ventas_df = get_data("ventas")

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
if 'venta_actual' not in st.session_state:
    st.session_state.venta_actual = []

# --- INTERFAZ DE LA APLICACIÓN ---
st.title("🌟 Gestor de Negocio Dinámico")
st.markdown("---")

opcion = st.sidebar.radio(
    "Selecciona una opción:", 
    ["📈 Ver Inventario", "💰 Registrar Venta", "🛒 Registrar Compra", "📊 Finanzas", "⚙️ Gestión"]
)

# --- PESTAÑA DE GESTIÓN ---
if opcion == "⚙️ Gestión":
    st.header("Gestión de Datos Maestros")
    tab1, tab2, tab3 = st.tabs(["🛍️ Productos", "👥 Clientes", "🚚 Proveedores"])

    with tab1:
        st.subheader("Añadir Nuevo Producto")
        with st.form("nuevo_producto_form", clear_on_submit=True):
            nombre = st.text_input("Nombre del Nuevo Producto")
            tallas = st.text_input("Tallas Disponibles (separadas por coma, ej: S,M,L)")
            precio = st.number_input("Precio de Venta por Defecto", min_value=0.0, format="%.2f")
            costo = st.number_input("Costo de Compra por Defecto", min_value=0.0, format="%.2f")
            if st.form_submit_button("Añadir Producto"):
                sheets["productos"].append_row([nombre, tallas, precio, costo])
                st.success(f"¡Producto '{nombre}' añadido!")
                st.cache_data.clear() # Limpiar cache para recargar datos

        st.subheader("Lista de Productos Actual")
        st.dataframe(productos_df, use_container_width=True)

    with tab2:
        st.subheader("Añadir Nuevo Cliente")
        with st.form("nuevo_cliente_form", clear_on_submit=True):
            nombre = st.text_input("Nombre del Nuevo Cliente")
            if st.form_submit_button("Añadir Cliente"):
                sheets["clientes"].append_row([nombre])
                st.success(f"¡Cliente '{nombre}' añadido!")
                st.cache_data.clear()

        st.subheader("Lista de Clientes Actual")
        st.dataframe(clientes_df, use_container_width=True)

    with tab3:
        st.subheader("Añadir Nuevo Proveedor")
        with st.form("nuevo_proveedor_form", clear_on_submit=True):
            nombre = st.text_input("Nombre del Nuevo Proveedor")
            if st.form_submit_button("Añadir Proveedor"):
                sheets["proveedores"].append_row([nombre])
                st.success(f"¡Proveedor '{nombre}' añadido!")
                st.cache_data.clear()
        
        st.subheader("Lista de Proveedores Actual")
        st.dataframe(proveedores_df, use_container_width=True)


# --- PESTAÑA DE VENTAS ---
elif opcion == "💰 Registrar Venta":
    st.header("Formulario de Registro de Ventas")
    st.markdown("Añade uno o más productos a una venta y regístrala para un solo cliente.")

    with st.form("item_venta_form"):
        st.subheader("Añadir Producto a la Venta")
        producto_vendido = st.selectbox("Producto", options=list(PRODUCTOS.keys()), key="venta_prod")
        
        # Obtener precio por defecto
        precio_defecto = float(productos_df[productos_df['NombreProducto'] == producto_vendido]['PrecioVentaDefecto'].iloc[0])

        col1, col2, col3 = st.columns(3)
        with col1:
            talla_vendida = st.selectbox("Talla", options=PRODUCTOS[producto_vendido], key="venta_talla")
        with col2:
            cantidad_vendida = st.number_input("Cantidad", min_value=1, step=1)
        with col3:
            precio_unitario = st.number_input("Precio Unitario ($)", min_value=0.0, value=precio_defecto, format="%.2f")
        
        if st.form_submit_button("➕ Añadir Producto a la Venta"):
            # Lógica para añadir item...
            item = { "Producto": producto_vendido, "Talla": talla_vendida, "Cantidad": cantidad_vendida, "Precio Unitario": precio_unitario, "Total Venta": cantidad_vendida * precio_unitario }
            st.session_state.venta_actual.append(item)
            st.success(f"Añadido: {cantidad_vendida} x {producto_vendido} ({talla_vendida})")

    if st.session_state.venta_actual:
        st.markdown("---")
        st.subheader("Venta Actual")
        df_venta_actual = pd.DataFrame(st.session_state.venta_actual)
        st.dataframe(df_venta_actual, use_container_width=True)
        total_venta_actual = df_venta_actual["Total Venta"].sum()
        st.info(f"**Total de la Venta Actual: ${total_venta_actual:,.2f}**")

        with st.form("finalizar_venta_form"):
            cliente = st.selectbox("Cliente", options=clientes_df['NombreCliente'].tolist())
            estado_pago = st.selectbox("Estado del Pago", ["Pagado", "Abono", "Debe"])

            if st.form_submit_button("✅ Registrar Venta Completa"):
                # Lógica para registrar venta completa...
                with st.spinner("Registrando venta..."):
                    id_venta = f"VENTA-{uuid.uuid4().hex[:8].upper()}"
                    fecha_venta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    filas_para_añadir = []
                    for item in st.session_state.venta_actual:
                        fila = [id_venta, fecha_venta, item["Producto"], item["Talla"], cliente, item["Cantidad"], item["Precio Unitario"], item["Total Venta"], estado_pago]
                        filas_para_añadir.append(fila)
                    sheets["ventas"].append_rows(filas_para_añadir)
                    st.success(f"¡Venta {id_venta} registrada!")
                    st.balloons()
                    st.session_state.venta_actual = []
                    actualizar_inventario()
                    st.rerun()

# --- PESTAÑA DE COMPRAS ---
elif opcion == "🛒 Registrar Compra":
    st.header("Formulario de Registro de Compras")
    st.markdown("Añade productos a una orden y regístrala con un solo costo de envío.")

    with st.form("item_compra_form"):
        st.subheader("Añadir Producto a la Orden")
        producto_comprado = st.selectbox("Producto", options=list(PRODUCTOS.keys()), key="compra_prod")
        
        # Obtener costo por defecto
        costo_defecto = float(productos_df[productos_df['NombreProducto'] == producto_comprado]['CostoCompraDefecto'].iloc[0])

        col1, col2, col3 = st.columns(3)
        with col1:
            talla_comprada = st.selectbox("Talla", options=PRODUCTOS[producto_comprado], key="compra_talla")
        with col2:
            cantidad_comprada = st.number_input("Cantidad", min_value=1, step=1)
        with col3:
            costo_unitario = st.number_input("Costo Unitario ($)", min_value=0.0, value=costo_defecto, format="%.2f")
        
        if st.form_submit_button("➕ Añadir Producto a la Compra"):
            # Lógica para añadir item...
            item = {"Producto": producto_comprado, "Talla": talla_comprada, "Cantidad": cantidad_comprada, "Costo Total": cantidad_comprada * costo_unitario}
            st.session_state.compra_actual.append(item)
            st.success(f"Añadido: {cantidad_comprada} x {producto_comprado} ({talla_comprada})")

    if st.session_state.compra_actual:
        st.markdown("---")
        st.subheader("Orden de Compra Actual")
        st.dataframe(pd.DataFrame(st.session_state.compra_actual), use_container_width=True)

        with st.form("finalizar_compra_form"):
            proveedor = st.selectbox("Proveedor", options=proveedores_df['NombreProveedor'].tolist())
            costo_envio = st.number_input("Costo Total del Envío ($)", min_value=0.0, format="%.2f")

            if st.form_submit_button("✅ Registrar Compra Completa"):
                # Lógica para registrar compra completa...
                with st.spinner("Registrando compra..."):
                    id_compra = f"COMPRA-{uuid.uuid4().hex[:8].upper()}"
                    fecha_compra = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    filas_para_añadir = []
                    for item in st.session_state.compra_actual:
                        fila = [id_compra, fecha_compra, item["Producto"], item["Talla"], proveedor, item["Cantidad"], item["Costo Total"], costo_envio]
                        filas_para_añadir.append(fila)
                    sheets["compras"].append_rows(filas_para_añadir)
                    st.success(f"¡Compra {id_compra} registrada!")
                    st.balloons()
                    st.session_state.compra_actual = []
                    actualizar_inventario()
                    st.rerun()

# --- PESTAÑAS DE INVENTARIO Y FINANZAS (Sin cambios) ---
elif opcion == "📈 Ver Inventario":
    st.header("Vista del Inventario Actual")
    if st.button("🔄 Refrescar Inventario"):
        with st.spinner("Actualizando..."):
            actualizar_inventario()
    
    inventario_df = get_data("inventario")
    if not inventario_df.empty:
        st.dataframe(inventario_df, use_container_width=True)
    else:
        st.info("No hay datos de inventario. Registra compras para empezar.")

elif opcion == "📊 Finanzas":
    st.header("Análisis Financiero Mensual")
    ventas_df = get_data("ventas")
    compras_df = get_data("compras")

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
        
        total_costo_producto = pd.to_numeric(compras_filtradas['Costo Total']).sum()
        if not compras_filtradas.empty and 'ID Compra' in compras_filtradas.columns:
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
