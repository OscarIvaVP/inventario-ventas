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

# --- LOGO EN LA BARRA LATERAL ---
LOGO_URL = "https://raw.githubusercontent.com/OscarIvaVP/inventario-ventas/main/assets/logo.jpeg"
st.sidebar.image(LOGO_URL, use_container_width=True)
st.sidebar.title("Menú de Navegación")


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
@st.cache_data(ttl=300) # Cache por 5 minutos
def load_master_data():
    """Carga los datos de las hojas de gestión y los procesa."""
    productos_df = pd.DataFrame(sheets["productos"].get_all_records())
    clientes_df = pd.DataFrame(sheets["clientes"].get_all_records())
    proveedores_df = pd.DataFrame(sheets["proveedores"].get_all_records())
    
    productos_dict = {}
    if not productos_df.empty:
        for _, row in productos_df.iterrows():
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
    """Recalcula y actualiza el inventario basándose en un SKU (Producto + Talla)."""
    compras_df = get_data("compras")
    ventas_df = get_data("ventas")

    if compras_df.empty and ventas_df.empty:
        sheets["inventario"].clear()
        sheets["inventario"].update([["SKU", "Producto", "Talla", "Unidades Compradas", "Unidades Vendidas", "Stock Actual", "Fecha Actualizacion"]])
        return pd.DataFrame()

    if not compras_df.empty:
        compras_df['Cantidad'] = pd.to_numeric(compras_df['Cantidad'], errors='coerce').fillna(0)
        compras_df['SKU'] = compras_df['Producto'].astype(str) + " - " + compras_df['Talla'].astype(str)
        stock_comprado = compras_df.groupby('SKU')['Cantidad'].sum().reset_index().rename(columns={'Cantidad': 'Unidades Compradas'})
    else:
        stock_comprado = pd.DataFrame(columns=['SKU', 'Unidades Compradas'])

    if not ventas_df.empty:
        ventas_df['Cantidad'] = pd.to_numeric(ventas_df['Cantidad'], errors='coerce').fillna(0)
        ventas_df['SKU'] = ventas_df['Producto'].astype(str) + " - " + ventas_df['Talla'].astype(str)
        stock_vendido = ventas_df.groupby('SKU')['Cantidad'].sum().reset_index().rename(columns={'Cantidad': 'Unidades Vendidas'})
    else:
        stock_vendido = pd.DataFrame(columns=['SKU', 'Unidades Vendidas'])

    inventario_df = pd.merge(stock_comprado, stock_vendido, on='SKU', how='outer').fillna(0)
    
    inventario_df['Unidades Compradas'] = pd.to_numeric(inventario_df['Unidades Compradas'], errors='coerce').fillna(0)
    inventario_df['Unidades Vendidas'] = pd.to_numeric(inventario_df['Unidades Vendidas'], errors='coerce').fillna(0)

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

opcion = st.sidebar.radio(
    "Selecciona una opción:", 
    ["📈 Ver Inventario", "💰 Registrar Venta", "🛒 Registrar Compra", "📊 Finanzas", "🧾 Cuentas por Cobrar", "⚙️ Gestión"]
)

# --- PESTAÑA DE GESTIÓN ---
if opcion == "⚙️ Gestión":
    st.header("Gestión de Datos Maestros")
    st.info("Aquí puedes añadir nuevos productos, clientes y proveedores a tus listas.")
    tab1, tab2, tab3 = st.tabs(["🛍️ Productos", "👥 Clientes", "🚚 Proveedores"])

    with tab1:
        st.subheader("Añadir Nuevo Producto")
        with st.form("nuevo_producto_form", clear_on_submit=True):
            nombre = st.text_input("Nombre del Nuevo Producto")
            tallas = st.text_input("Tallas Disponibles (separadas por coma, ej: S,M,L)")
            precio = st.number_input("Precio de Venta por Defecto", min_value=0.0, format="%.2f")
            costo = st.number_input("Costo de Compra por Defecto", min_value=0.0, format="%.2f")
            if st.form_submit_button("Añadir Producto"):
                if nombre and tallas:
                    sheets["productos"].append_row([nombre, tallas, precio, costo])
                    st.success(f"¡Producto '{nombre}' añadido!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("Nombre y Tallas son campos obligatorios.")
        st.subheader("Lista de Productos Actual")
        st.dataframe(productos_df, use_container_width=True)
    
    with tab2:
        st.subheader("Añadir Nuevo Cliente")
        with st.form("nuevo_cliente_form", clear_on_submit=True):
            nombre = st.text_input("Nombre del Nuevo Cliente")
            if st.form_submit_button("Añadir Cliente"):
                if nombre:
                    sheets["clientes"].append_row([nombre])
                    st.success(f"¡Cliente '{nombre}' añadido!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("El nombre del cliente no puede estar vacío.")
        st.subheader("Lista de Clientes Actual")
        st.dataframe(clientes_df, use_container_width=True)

    with tab3:
        st.subheader("Añadir Nuevo Proveedor")
        with st.form("nuevo_proveedor_form", clear_on_submit=True):
            nombre = st.text_input("Nombre del Nuevo Proveedor")
            if st.form_submit_button("Añadir Proveedor"):
                if nombre:
                    sheets["proveedores"].append_row([nombre])
                    st.success(f"¡Proveedor '{nombre}' añadido!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("El nombre del proveedor no puede estar vacío.")
        st.subheader("Lista de Proveedores Actual")
        st.dataframe(proveedores_df, use_container_width=True)


# --- PESTAÑA DE VENTAS ---
elif opcion == "💰 Registrar Venta":
    st.header("Formulario de Registro de Ventas")
    
    st.subheader("Paso 1: Elige el Cliente")
    col1, col2 = st.columns([2, 2])
    with col1:
        lista_clientes = [""] + clientes_df['NombreCliente'].tolist()
        cliente_existente = st.selectbox("Selecciona un Cliente Existente", options=lista_clientes, help="Elige un cliente de tu lista.")
    with col2:
        cliente_nuevo = st.text_input("O añade un Cliente Nuevo aquí", help="Si el cliente no existe, escríbelo aquí.")
    
    cliente_final = cliente_nuevo.strip() if cliente_nuevo else cliente_existente

    if cliente_final:
        st.success(f"Cliente seleccionado: **{cliente_final}**")
        st.markdown("---")
        st.subheader("Paso 2: Añade Productos a la Venta")

        producto_vendido = st.selectbox(
            "Selecciona un producto", 
            options=[""] + list(PRODUCTOS.keys()), 
            key="venta_prod_selector",
            label_visibility="collapsed"
        )

        if producto_vendido:
            with st.form("item_venta_form", clear_on_submit=True):
                st.write(f"**Añadiendo:** {producto_vendido}")
                precio_defecto = float(productos_df[productos_df['NombreProducto'] == producto_vendido]['PrecioVentaDefecto'].iloc[0])
                
                c1, c2, c3 = st.columns(3)
                talla_vendida = c1.selectbox("Talla", options=PRODUCTOS.get(producto_vendido, []))
                cantidad_vendida = c2.number_input("Cantidad", min_value=1, step=1)
                precio_unitario = c3.number_input(
                    "Precio Unitario ($)", 
                    min_value=0.0, 
                    value=precio_defecto, 
                    format="%.2f",
                    key=f"precio_venta_{producto_vendido}"
                )
                
                if st.form_submit_button("➕ Añadir Producto"):
                    item = {"Producto": producto_vendido, "Talla": talla_vendida, "Cantidad": cantidad_vendida, "Precio Unitario": precio_unitario, "Total Venta": cantidad_vendida * precio_unitario}
                    st.session_state.venta_actual.append(item)
                    st.rerun()
        
        if st.session_state.venta_actual:
            st.markdown("---")
            st.subheader("Venta Actual")
            df_venta_actual = pd.DataFrame(st.session_state.venta_actual)
            st.dataframe(df_venta_actual, use_container_width=True)

            with st.form("eliminar_item_venta_form"):
                st.write("Para eliminar, selecciona uno o más productos de la lista y haz clic en el botón.")
                indices_a_eliminar = st.multiselect(
                    "Selecciona productos para eliminar",
                    options=range(len(st.session_state.venta_actual)),
                    format_func=lambda i: f"{st.session_state.venta_actual[i]['Producto']} (Talla: {st.session_state.venta_actual[i]['Talla']}, Cant: {st.session_state.venta_actual[i]['Cantidad']})"
                )
                if st.form_submit_button("🗑️ Eliminar Seleccionados"):
                    if indices_a_eliminar:
                        st.session_state.venta_actual = [item for i, item in enumerate(st.session_state.venta_actual) if i not in indices_a_eliminar]
                        st.rerun()
                    else:
                        st.warning("No has seleccionado ningún producto para eliminar.")
            
            if st.session_state.venta_actual:
                st.markdown("---")
                st.subheader(f"Paso 3: Finalizar Venta para {cliente_final}")
                total_venta_actual = pd.DataFrame(st.session_state.venta_actual)["Total Venta"].sum()
                st.info(f"**Total de la Venta Actual: ${total_venta_actual:,.2f}**")

                with st.form("finalizar_venta_form"):
                    estado_pago = st.selectbox("Estado del Pago", ["Pagado", "Abono", "Debe"])
                    if st.form_submit_button("✅ Registrar Venta Completa"):
                        if cliente_nuevo and cliente_nuevo not in clientes_df['NombreCliente'].tolist():
                            sheets["clientes"].append_row([cliente_nuevo])
                            st.success(f"¡Nuevo cliente '{cliente_nuevo}' añadido a la base de datos!")
                            st.cache_data.clear()
                        
                        with st.spinner("Registrando venta..."):
                            id_venta = f"VENTA-{uuid.uuid4().hex[:8].upper()}"
                            fecha_venta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            filas_para_añadir = []
                            for item in st.session_state.venta_actual:
                                fila = [id_venta, fecha_venta, item["Producto"], item["Talla"], cliente_final, item["Cantidad"], item["Precio Unitario"], item["Total Venta"], estado_pago]
                                filas_para_añadir.append(fila)
                            sheets["ventas"].append_rows(filas_para_añadir)
                            st.success(f"¡Venta {id_venta} registrada!")
                            st.balloons()
                            st.session_state.venta_actual = []
                            actualizar_inventario()
                            st.rerun()
    else:
        st.warning("Por favor, selecciona o añade un cliente para continuar.")

# --- PESTAÑA DE COMPRAS ---
elif opcion == "🛒 Registrar Compra":
    st.header("Formulario de Registro de Compras")
    
    st.subheader("Paso 1: Elige el Proveedor")
    col1, col2 = st.columns([2, 2])
    with col1:
        lista_proveedores = [""] + proveedores_df['NombreProveedor'].tolist()
        proveedor_existente = st.selectbox("Selecciona un Proveedor Existente", options=lista_proveedores)
    with col2:
        proveedor_nuevo = st.text_input("O añade un Proveedor Nuevo aquí")
    
    proveedor_final = proveedor_nuevo.strip() if proveedor_nuevo else proveedor_existente

    if proveedor_final:
        st.success(f"Proveedor seleccionado: **{proveedor_final}**")
        st.markdown("---")
        st.subheader("Paso 2: Añade Productos a la Orden")
        
        producto_comprado = st.selectbox(
            "Selecciona un producto", 
            options=[""] + list(PRODUCTOS.keys()), 
            key="compra_prod_selector",
            label_visibility="collapsed"
        )

        if producto_comprado:
            with st.form("item_compra_form", clear_on_submit=True):
                st.write(f"**Añadiendo:** {producto_comprado}")
                costo_defecto = float(productos_df[productos_df['NombreProducto'] == producto_comprado]['CostoCompraDefecto'].iloc[0])
                
                c1, c2, c3 = st.columns(3)
                talla_comprada = c1.selectbox("Talla", options=PRODUCTOS.get(producto_comprado, []))
                cantidad_comprada = c2.number_input("Cantidad", min_value=1, step=1)
                costo_unitario = c3.number_input(
                    "Costo Unitario ($)", 
                    min_value=0.0, 
                    value=costo_defecto, 
                    format="%.2f",
                    key=f"costo_compra_{producto_comprado}"
                )
                
                if st.form_submit_button("➕ Añadir Producto"):
                    item = {"Producto": producto_comprado, "Talla": talla_comprada, "Cantidad": cantidad_comprada, "Costo Total": cantidad_comprada * costo_unitario}
                    st.session_state.compra_actual.append(item)
                    st.rerun()

        if st.session_state.compra_actual:
            st.markdown("---")
            st.subheader("Orden de Compra Actual")
            st.dataframe(pd.DataFrame(st.session_state.compra_actual), use_container_width=True)

            with st.form("eliminar_item_compra_form"):
                st.write("Para eliminar, selecciona uno o más productos de la lista y haz clic en el botón.")
                indices_a_eliminar = st.multiselect(
                    "Selecciona productos para eliminar",
                    options=range(len(st.session_state.compra_actual)),
                    format_func=lambda i: f"{st.session_state.compra_actual[i]['Producto']} (Talla: {st.session_state.compra_actual[i]['Talla']}, Cant: {st.session_state.compra_actual[i]['Cantidad']})"
                )
                if st.form_submit_button("🗑️ Eliminar Seleccionados"):
                    if indices_a_eliminar:
                        st.session_state.compra_actual = [item for i, item in enumerate(st.session_state.compra_actual) if i not in indices_a_eliminar]
                        st.rerun()
                    else:
                        st.warning("No has seleccionado ningún producto para eliminar.")

            if st.session_state.compra_actual:
                st.markdown("---")
                st.subheader(f"Paso 3: Finalizar Compra de {proveedor_final}")
                with st.form("finalizar_compra_form"):
                    costo_envio = st.number_input("Costo Total del Envío ($)", min_value=0.0, format="%.2f")
                    if st.form_submit_button("✅ Registrar Compra Completa"):
                        if proveedor_nuevo and proveedor_nuevo not in proveedores_df['NombreProveedor'].tolist():
                            sheets["proveedores"].append_row([proveedor_nuevo])
                            st.success(f"¡Nuevo proveedor '{proveedor_nuevo}' añadido a la base de datos!")
                            st.cache_data.clear()
                        
                        with st.spinner("Registrando compra..."):
                            id_compra = f"COMPRA-{uuid.uuid4().hex[:8].upper()}"
                            fecha_compra = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            filas_para_añadir = []
                            for item in st.session_state.compra_actual:
                                fila = [id_compra, fecha_compra, item["Producto"], item["Talla"], proveedor_final, item["Cantidad"], item["Costo Total"], costo_envio]
                                filas_para_añadir.append(fila)
                            sheets["compras"].append_rows(filas_para_añadir)
                            st.success(f"¡Compra {id_compra} registrada!")
                            st.balloons()
                            st.session_state.compra_actual = []
                            actualizar_inventario()
                            st.rerun()
    else:
        st.warning("Por favor, selecciona o añade un proveedor para continuar.")

# --- PESTAÑA DE CUENTAS POR COBRAR ---
elif opcion == "🧾 Cuentas por Cobrar":
    st.header("Gestión de Cuentas por Cobrar")
    
    ventas_df = get_data("ventas")
    if not ventas_df.empty:
        # Asegurar que las columnas sean del tipo correcto
        ventas_df['Total Venta'] = pd.to_numeric(ventas_df['Total Venta'], errors='coerce').fillna(0)
        
        cuentas_pendientes = ventas_df[ventas_df['Estado Pago'].isin(['Debe', 'Abono'])]
        
        if not cuentas_pendientes.empty:
            st.subheader("Resumen de Deudas por Cliente")
            resumen_deudas = cuentas_pendientes.groupby(['ID Venta', 'Cliente', 'Estado Pago'])['Total Venta'].sum().reset_index()
            st.dataframe(resumen_deudas, use_container_width=True)

            st.markdown("---")
            st.subheader("Actualizar Estado de Pago")
            with st.form("actualizar_pago_form"):
                id_venta_a_actualizar = st.text_input("Ingresa el ID de la Venta a actualizar (ej: VENTA-ABC12345)")
                if st.form_submit_button("Marcar como Pagado"):
                    if id_venta_a_actualizar:
                        try:
                            with st.spinner("Actualizando estado..."):
                                # Encontrar todas las celdas que coinciden con el ID Venta
                                cell_list = sheets["ventas"].findall(id_venta_a_actualizar)
                                if not cell_list:
                                    st.error("No se encontró ninguna venta con ese ID.")
                                else:
                                    # Encontrar la columna de "Estado Pago"
                                    headers = sheets["ventas"].row_values(1)
                                    estado_col_index = headers.index('Estado Pago') + 1
                                    
                                    # Actualizar todas las filas de esa venta a "Pagado"
                                    for cell in cell_list:
                                        sheets["ventas"].update_cell(cell.row, estado_col_index, "Pagado")
                                    
                                    st.success(f"¡La venta {id_venta_a_actualizar} ha sido marcada como 'Pagado'!")
                                    st.balloons()
                                    st.cache_data.clear() # Limpiar cache para recargar datos
                        except Exception as e:
                            st.error(f"Ocurrió un error: {e}")
                    else:
                        st.warning("Por favor, ingresa un ID de Venta.")
        else:
            st.success("🎉 ¡Felicidades! No tienes ninguna cuenta por cobrar pendiente.")
    else:
        st.info("No hay datos de ventas para analizar.")


# --- PESTAÑA DE FINANZAS ---
elif opcion == "📊 Finanzas":
    st.header("Análisis Financiero")
    ventas_df = get_data("ventas")
    compras_df = get_data("compras")

    if ventas_df.empty and compras_df.empty:
        st.info("No hay datos de ventas o compras para analizar.")
    else:
        # Asegurar tipos de datos correctos
        if not ventas_df.empty:
            ventas_df['Fecha'] = pd.to_datetime(ventas_df['Fecha'], errors='coerce')
            ventas_df['Mes'] = ventas_df['Fecha'].dt.to_period('M').astype(str)
            ventas_df['Total Venta'] = pd.to_numeric(ventas_df['Total Venta'], errors='coerce').fillna(0)
        if not compras_df.empty:
            compras_df['Fecha'] = pd.to_datetime(compras_df['Fecha'], errors='coerce')
            compras_df['Mes'] = compras_df['Fecha'].dt.to_period('M').astype(str)
            compras_df['Costo Total'] = pd.to_numeric(compras_df['Costo Total'], errors='coerce').fillna(0)
            compras_df['Costo Envio'] = pd.to_numeric(compras_df['Costo Envio'], errors='coerce').fillna(0)
        
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
        
        # --- CÁLCULOS FINANCIEROS CORREGIDOS ---
        ventas_pagadas = ventas_filtradas[ventas_filtradas['Estado Pago'] == 'Pagado']
        cuentas_por_cobrar = ventas_filtradas[ventas_filtradas['Estado Pago'].isin(['Debe', 'Abono'])]
        
        total_ingresos_reales = ventas_pagadas['Total Venta'].sum()
        total_por_cobrar = cuentas_por_cobrar['Total Venta'].sum()
        
        total_costo_producto = compras_filtradas['Costo Total'].sum()
        if not compras_filtradas.empty and 'ID Compra' in compras_filtradas.columns:
            total_costo_envio = compras_filtradas.drop_duplicates(subset=['ID Compra'])['Costo Envio'].sum()
        else:
            total_costo_envio = 0

        total_gastos = total_costo_producto + total_costo_envio
        ganancia_real = total_ingresos_reales - total_gastos

        st.markdown("---")
        st.subheader(f"Resumen Financiero para: {mes_seleccionado}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Ingresos Reales (Pagado)", f"${total_ingresos_reales:,.2f}")
        col2.metric("💸 Gastos Totales", f"${total_gastos:,.2f}")
        col3.metric("📈 Ganancia Real", f"${ganancia_real:,.2f}", delta=f"{ganancia_real:,.2f}")
        col4.metric("🧾 Cuentas por Cobrar", f"${total_por_cobrar:,.2f}")

        st.markdown("---")
        st.subheader(f"Detalle de Movimientos para: {mes_seleccionado}")
        
        exp_ventas = st.expander("Ver detalle de todas las ventas")
        exp_ventas.dataframe(ventas_filtradas, use_container_width=True)

        exp_compras = st.expander("Ver detalle de compras")
        exp_compras.dataframe(compras_filtradas, use_container_width=True)

# --- PESTAÑA DE INVENTARIO ---
elif opcion == "📈 Ver Inventario":
    st.header("Vista del Inventario Actual")
    if st.button("🔄 Refrescar Inventario"):
        with st.spinner("Actualizando..."):
            actualizar_inventario()
            st.cache_data.clear() # Limpiar cache para ver cambios
    
    inventario_df = get_data("inventario")
    if not inventario_df.empty:
        st.dataframe(inventario_df, use_container_width=True)
    else:
        st.info("No hay datos de inventario. Registra compras para empezar.")
