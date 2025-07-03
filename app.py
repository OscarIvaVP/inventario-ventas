import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- CONFIGURACIÓN INICIAL Y CONEXIÓN A GOOGLE SHEETS ---

# Configuración de la página de Streamlit
st.set_page_config(
    page_title="Gestor de Negocio",
    page_icon="📈",
    layout="wide"
)

# Alcance de los permisos para la API de Google Sheets
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Cargar las credenciales desde el archivo JSON (o desde los secretos de Streamlit)
# Para desarrollo local, asegúrate de tener el archivo `credentials.json`
# Para despliegue en Streamlit Cloud, usa st.secrets
try:
    creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
except FileNotFoundError:
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

# Autorizar y crear el cliente de gspread
client = gspread.authorize(creds)

# Abrir la hoja de cálculo por su nombre
try:
    spreadsheet = client.open("BaseDeDatos_Negocio")
    sheet_ventas = spreadsheet.worksheet("Ventas")
    sheet_compras = spreadsheet.worksheet("Compras")
    sheet_inventario = spreadsheet.worksheet("Inventario")
except gspread.exceptions.SpreadsheetNotFound:
    st.error("🚨 No se encontró la hoja de cálculo 'BaseDeDatos_Negocio'. Asegúrate de que exista y esté compartida.")
    st.stop()

# --- FUNCIONES AUXILIARES ---

def actualizar_inventario():
    """
    Recalcula y actualiza la hoja de inventario basándose en las ventas y compras.
    """
    # Leer datos de compras y ventas
    compras_df = pd.DataFrame(sheet_compras.get_all_records())
    ventas_df = pd.DataFrame(sheet_ventas.get_all_records())

    # Calcular total de unidades compradas por producto
    if not compras_df.empty:
        stock_comprado = compras_df.groupby('Producto')['Cantidad'].sum().reset_index()
        stock_comprado = stock_comprado.rename(columns={'Cantidad': 'Unidades Compradas'})
    else:
        stock_comprado = pd.DataFrame(columns=['Producto', 'Unidades Compradas'])

    # Calcular total de unidades vendidas por producto
    if not ventas_df.empty:
        stock_vendido = ventas_df.groupby('Producto')['Cantidad'].sum().reset_index()
        stock_vendido = stock_vendido.rename(columns={'Cantidad': 'Unidades Vendidas'})
    else:
        stock_vendido = pd.DataFrame(columns=['Producto', 'Unidades Vendidas'])

    # Unir los dataframes de compras y ventas
    inventario_df = pd.merge(stock_comprado, stock_vendido, on='Producto', how='outer').fillna(0)
    
    # Calcular el stock actual
    inventario_df['Stock Actual'] = inventario_df['Unidades Compradas'] - inventario_df['Unidades Vendidas']
    
    # Actualizar la hoja de inventario en Google Sheets
    inventario_df['Fecha Actualizacion'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet_inventario.clear()
    sheet_inventario.update([inventario_df.columns.values.tolist()] + inventario_df.values.tolist())
    
    return inventario_df

# --- INTERFAZ DE LA APLICACIÓN ---

st.title("📊 Aplicativo de Gestión de Negocio")
st.markdown("---")

# Menú de navegación en la barra lateral
opcion = st.sidebar.radio("Selecciona una opción:", ["📈 Ver Inventario", "💰 Registrar Venta", "🛒 Registrar Compra"])

if opcion == "💰 Registrar Venta":
    st.header("Formulario de Registro de Ventas")

    with st.form("venta_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("Nombre del Cliente")
            producto_vendido = st.text_input("Nombre del Producto")
            cantidad_vendida = st.number_input("Cantidad Vendida", min_value=1, step=1)
        with col2:
            precio_unitario = st.number_input("Precio Unitario ($)", min_value=0.0, format="%.2f")
            estado_pago = st.selectbox("Estado del Pago", ["Pagado", "Abono", "Debe"])

        total_venta = cantidad_vendida * precio_unitario
        st.info(f"**Total de la Venta: ${total_venta:,.2f}**")

        submitted = st.form_submit_button("Registrar Venta")
        if submitted:
            if not cliente or not producto_vendido:
                st.warning("Por favor, completa los campos de Cliente y Producto.")
            else:
                fecha_venta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                nueva_venta = [fecha_venta, producto_vendido, cliente, cantidad_vendida, precio_unitario, total_venta, estado_pago]
                
                # Añadir fila a Google Sheets
                sheet_ventas.append_row(nueva_venta)
                st.success("✅ ¡Venta registrada exitosamente!")
                
                # Actualizar el inventario
                actualizar_inventario()

elif opcion == "🛒 Registrar Compra":
    st.header("Formulario de Registro de Compras a Proveedores")

    with st.form("compra_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            proveedor = st.text_input("Nombre del Proveedor")
            producto_comprado = st.text_input("Nombre del Producto")
        with col2:
            cantidad_comprada = st.number_input("Cantidad Comprada", min_value=1, step=1)
            costo_total = st.number_input("Costo Total de la Compra ($)", min_value=0.0, format="%.2f")

        submitted = st.form_submit_button("Registrar Compra")
        if submitted:
            if not proveedor or not producto_comprado:
                st.warning("Por favor, completa los campos de Proveedor y Producto.")
            else:
                fecha_compra = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                nueva_compra = [fecha_compra, producto_comprado, proveedor, cantidad_comprada, costo_total]

                # Añadir fila a Google Sheets
                sheet_compras.append_row(nueva_compra)
                st.success("✅ ¡Compra registrada exitosamente!")

                # Actualizar el inventario
                actualizar_inventario()

elif opcion == "📈 Ver Inventario":
    st.header("Vista del Inventario Actual")

    if st.button("🔄 Refrescar Inventario"):
        with st.spinner("Actualizando..."):
            inventario_actual_df = actualizar_inventario()
            st.success("¡Inventario actualizado!")
    else:
        # Cargar datos directamente al iniciar
        inventario_actual_df = pd.DataFrame(sheet_inventario.get_all_records())

    if not inventario_actual_df.empty:
        st.dataframe(inventario_actual_df, use_container_width=True)
    else:
        st.info("No hay datos de inventario. Registra compras para empezar.")
    
    st.markdown("---")
    
    # Mostrar también las últimas ventas y compras
    st.subheader("Últimos Movimientos")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Últimas Ventas")
        ventas_df = pd.DataFrame(sheet_ventas.get_all_records())
        st.dataframe(ventas_df.tail(), use_container_width=True)
    
    with col2:
        st.markdown("#### Últimas Compras")
        compras_df = pd.DataFrame(sheet_compras.get_all_records())
        st.dataframe(compras_df.tail(), use_container_width=True)