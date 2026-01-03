import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import paramiko
from io import StringIO, BytesIO
import time
import hashlib
import base64
import warnings
warnings.filterwarnings('ignore')

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería - Modo Migración",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# SISTEMA DE CARGA REMOTA VIA SSH
# =============================================================================

class CargadorRemoto:
    def __init__(self):
        self.ssh = None
        self.sftp = None
        
    def conectar(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Cargar credenciales desde secrets de Streamlit
            self.ssh.connect(
                hostname=st.secrets["remote_host"],
                port=st.secrets["remote_port"],
                username=st.secrets["remote_user"],
                password=st.secrets["remote_password"],
                timeout=30
            )
            self.sftp = self.ssh.open_sftp()
            return True
        except Exception as e:
            st.error(f"❌ Error de conexión SSH: {e}")
            return False
    
    def desconectar(self):
        """Cerrar conexión SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close()
        except:
            pass
    
    def cargar_csv_remoto(self, ruta_remota):
        """Cargar archivo CSV desde el servidor remoto"""
        try:
            if not self.conectar():
                return pd.DataFrame()
            
            # Verificar si el archivo existe en el servidor remoto
            try:
                self.sftp.stat(ruta_remota)
            except FileNotFoundError:
                st.warning(f"📁 Archivo remoto no encontrado: {os.path.basename(ruta_remota)}")
                return pd.DataFrame()
            
            # Leer archivo remoto
            with self.sftp.file(ruta_remota, 'r') as archivo_remoto:
                try:
                    df = pd.read_csv(archivo_remoto, encoding='utf-8')
                except UnicodeDecodeError:
                    archivo_remoto.seek(0)
                    df = pd.read_csv(archivo_remoto, encoding='latin-1')
                
            return df
            
        except Exception as e:
            st.warning(f"⚠️ Error cargando {os.path.basename(ruta_remota)}: {str(e)}")
            return pd.DataFrame()
        finally:
            self.desconectar()
    
    def cargar_todos_los_datos(self):
        """Cargar todos los archivos CSV del servidor remoto"""
        
        BASE_DIR_REMOTO = st.secrets["remote_dir"]
        
        rutas_remotas = {
            'inscritos': os.path.join(BASE_DIR_REMOTO, "datos", "inscritos.csv"),
            'estudiantes': os.path.join(BASE_DIR_REMOTO, "datos", "estudiantes.csv"),
            'egresados': os.path.join(BASE_DIR_REMOTO, "datos", "egresados.csv"),
            'contratados': os.path.join(BASE_DIR_REMOTO, "datos", "contratados.csv"),
            'usuarios': os.path.join(BASE_DIR_REMOTO, "config", "usuarios.csv"),
            'bitacora': os.path.join(BASE_DIR_REMOTO, "datos", "bitacora.csv")
        }
        
        datos_cargados = {}
        
        for nombre, ruta_remota in rutas_remotas.items():
            datos_cargados[nombre] = self.cargar_csv_remoto(ruta_remota)
        
        return datos_cargados

# Instanciar el cargador remoto
cargador_remoto = CargadorRemoto()

# =============================================================================
# CARGA DE TODOS LOS DATOS DESDE EL SERVIDOR REMOTO
# =============================================================================

@st.cache_data(ttl=300)  # Cache por 5 minutos
def cargar_datos_completos():
    """Cargar todos los datos desde el servidor remoto"""
    with st.spinner("🌐 Conectando al servidor remoto..."):
        datos = cargador_remoto.cargar_todos_los_datos()
        
        # Mostrar estado de carga
        if datos:
            st.success("✅ Datos cargados exitosamente desde el servidor remoto")
            for nombre, df in datos.items():
                if not df.empty:
                    st.info(f"📊 {nombre}: {len(df)} registros")
        else:
            st.error("❌ Error cargando datos del servidor remoto")
            
        return datos

# Cargar todos los datos al inicio
datos = cargar_datos_completos()

# Asignar a variables globales
df_inscritos = datos.get('inscritos', pd.DataFrame())
df_estudiantes = datos.get('estudiantes', pd.DataFrame())
df_egresados = datos.get('egresados', pd.DataFrame())
df_contratados = datos.get('contratados', pd.DataFrame())
df_usuarios = datos.get('usuarios', pd.DataFrame())
df_bitacora = datos.get('bitacora', pd.DataFrame())

# =============================================================================
# SISTEMA DE EDICIÓN Y GUARDADO REMOTO - MEJORADO
# =============================================================================

class EditorRemoto:
    def __init__(self):
        self.cargador = cargador_remoto
    
    def obtener_ruta_archivo(self, tipo_datos):
        """Obtener ruta remota del archivo según el tipo de datos"""
        BASE_DIR_REMOTO = st.secrets["remote_dir"]
        
        rutas = {
            'inscritos': os.path.join(BASE_DIR_REMOTO, "datos", "inscritos.csv"),
            'estudiantes': os.path.join(BASE_DIR_REMOTO, "datos", "estudiantes.csv"),
            'egresados': os.path.join(BASE_DIR_REMOTO, "datos", "egresados.csv"),
            'contratados': os.path.join(BASE_DIR_REMOTO, "datos", "contratados.csv"),
            'usuarios': os.path.join(BASE_DIR_REMOTO, "config", "usuarios.csv"),
            'bitacora': os.path.join(BASE_DIR_REMOTO, "datos", "bitacora.csv")
        }
        return rutas.get(tipo_datos, "")
    
    def guardar_dataframe_remoto(self, df, ruta_remota):
        """Guardar DataFrame en el servidor remoto - MEJORADO"""
        try:
            if self.cargador.conectar():
                # Crear directorio si no existe
                directorio = os.path.dirname(ruta_remota)
                try:
                    self.cargador.sftp.stat(directorio)
                except FileNotFoundError:
                    # Crear directorio recursivamente
                    partes = directorio.split('/')
                    path_actual = ''
                    for parte in partes:
                        if parte:
                            path_actual += '/' + parte
                            try:
                                self.cargador.sftp.stat(path_actual)
                            except FileNotFoundError:
                                self.cargador.sftp.mkdir(path_actual)
                
                # Guardar DataFrame en un buffer en memoria
                buffer = StringIO()
                df.to_csv(buffer, index=False, encoding='utf-8')
                buffer.seek(0)
                contenido = buffer.getvalue()
                
                # Subir al servidor remoto
                with self.cargador.sftp.file(ruta_remota, 'w') as archivo_remoto:
                    archivo_remoto.write(contenido)
                
                self.cargador.desconectar()
                st.success(f"✅ Archivo guardado exitosamente: {os.path.basename(ruta_remota)}")
                return True
            else:
                st.error(f"❌ No se pudo conectar para guardar {os.path.basename(ruta_remota)}")
                return False
                
        except Exception as e:
            st.error(f"❌ Error guardando archivo remoto {os.path.basename(ruta_remota)}: {e}")
            return False

# Instancia del editor remoto
editor = EditorRemoto()

# =============================================================================
# SISTEMA DE AUTENTICACIÓN
# =============================================================================

class SistemaAutenticacion:
    def __init__(self):
        self.usuarios = df_usuarios
        self.sesion_activa = False
        self.usuario_actual = None
        
    def verificar_credenciales_desde_archivo(self, usuario_input, password_input):
        """Verificar credenciales desde el archivo remoto usuarios.csv"""
        try:
            if self.usuarios.empty:
                st.error("❌ No se pudieron cargar los usuarios del sistema desde el servidor remoto")
                return False, None
            
            # Buscar usuario en el DataFrame
            usuario_encontrado = None
            
            # Estrategia 1: Buscar por columna 'usuario'
            if 'usuario' in self.usuarios.columns:
                usuario_df = self.usuarios[
                    self.usuarios['usuario'].astype(str).str.strip().str.lower() == usuario_input.lower().strip()
                ]
                
                if not usuario_df.empty:
                    usuario_encontrado = usuario_df.iloc[0]
            
            if usuario_encontrado is None:
                st.error(f"❌ Usuario '{usuario_input}' no encontrado en la base de datos remota")
                return False, None
            
            # Verificar contraseña
            if 'password' in usuario_encontrado:
                contraseña_almacenada = str(usuario_encontrado['password']).strip()
                password_input_clean = str(password_input).strip()
                
                if contraseña_almacenada == password_input_clean:
                    return True, usuario_encontrado
                else:
                    st.error("❌ Contraseña incorrecta")
                    return False, None
            else:
                st.error("❌ No se encontró campo 'password' en el registro del usuario")
                return False, None
                
        except Exception as e:
            st.error(f"❌ Error en verificación de credenciales: {e}")
            return False, None
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de usuario desde archivo remoto"""
        try:
            if not usuario or not password:
                st.error("❌ Usuario y contraseña son obligatorios")
                return False
            
            with st.spinner("🔐 Verificando credenciales en servidor remoto..."):
                # Recargar usuarios para asegurar datos actualizados
                BASE_DIR_REMOTO = st.secrets["remote_dir"]
                ruta_usuarios = os.path.join(BASE_DIR_REMOTO, "config", "usuarios.csv")
                df_usuarios_actualizado = cargador_remoto.cargar_csv_remoto(ruta_usuarios)
                
                if df_usuarios_actualizado.empty:
                    st.error("❌ No se pudo cargar el archivo de usuarios desde el servidor")
                    return False
                
                self.usuarios = df_usuarios_actualizado
                
                # Verificar credenciales
                credenciales_ok, usuario_data = self.verificar_credenciales_desde_archivo(usuario, password)
                
                if credenciales_ok and usuario_data is not None:
                    # Verificar que sea administrador
                    rol_usuario = usuario_data.get('rol', '')
                    
                    if rol_usuario != 'administrador':
                        st.error("❌ Solo los usuarios con rol 'administrador' pueden acceder a este sistema")
                        return False
                    
                    usuario_real = usuario_data.get('usuario', '')
                    nombre_real = usuario_data.get('nombre', 'Usuario')
                    
                    st.success(f"✅ ¡Bienvenido(a), {nombre_real}!")
                    st.session_state.login_exitoso = True
                    st.session_state.usuario_actual = usuario_data.to_dict()
                    self.sesion_activa = True
                    self.usuario_actual = usuario_data.to_dict()
                    
                    # Registrar en bitácora
                    self.registrar_bitacora('LOGIN', f'Administrador {usuario_real} inició sesión en el migrador')
                    return True
                else:
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error en el proceso de login: {e}")
            return False
            
    def registrar_bitacora(self, accion, detalles):
        """Registrar actividad en bitácora"""
        try:
            nueva_entrada = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'usuario': self.usuario_actual.get('usuario', 'Sistema') if self.usuario_actual else 'Sistema',
                'accion': accion,
                'detalles': detalles,
                'ip': 'localhost'
            }
            
            global df_bitacora
            if df_bitacora.empty:
                df_bitacora = pd.DataFrame([nueva_entrada])
            else:
                df_bitacora = pd.concat([df_bitacora, pd.DataFrame([nueva_entrada])], ignore_index=True)
                
        except Exception as e:
            st.error(f"❌ Error registrando en bitácora: {e}")
    
    def cerrar_sesion(self):
        """Cerrar sesión del usuario"""
        try:
            if self.sesion_activa and self.usuario_actual:
                usuario = self.usuario_actual.get('usuario', '')
                self.registrar_bitacora('LOGOUT', f'Administrador {usuario} cerró sesión del migrador')
                
            self.sesion_activa = False
            self.usuario_actual = None
            st.session_state.login_exitoso = False
            st.session_state.usuario_actual = None
            st.success("✅ Sesión cerrada exitosamente")
            
        except Exception as e:
            st.error(f"❌ Error cerrando sesión: {e}")

# Instancia global del sistema de autenticación
auth = SistemaAutenticacion()

# =============================================================================
# SISTEMA DE MIGRACIÓN DE ROLES - COMPLETAMENTE CORREGIDO
# =============================================================================

class SistemaMigracion:
    def __init__(self):
        self.inscritos = df_inscritos
        self.estudiantes = df_estudiantes
        self.egresados = df_egresados
        self.contratados = df_contratados
        self.usuarios = df_usuarios
        self.directorio_uploads = os.path.join(st.secrets["remote_dir"], "uploads")
    
    def obtener_prefijo_rol(self, rol):
        """Obtener prefijo de matrícula según el rol"""
        prefijos = {
            'inscrito': 'MAT-INS',
            'estudiante': 'MAT-EST',
            'egresado': 'MAT-EGR',
            'contratado': 'MAT-CON'
        }
        return prefijos.get(rol, 'MAT-')
    
    def generar_nueva_matricula(self, matricula_actual, rol_destino):
        """Generar nueva matrícula según el rol destino"""
        prefijo_destino = self.obtener_prefijo_rol(rol_destino)
        
        # Extraer el número de la matrícula actual
        for prefijo in ['MAT-INS', 'MAT-EST', 'MAT-EGR', 'MAT-CON']:
            if matricula_actual.startswith(prefijo):
                numero = matricula_actual.replace(prefijo, '')
                return f"{prefijo_destino}{numero}"
        
        # Si no tiene formato conocido, generar nueva
        return f"{prefijo_destino}{datetime.now().strftime('%y%m%d%H%M')}"
    
    def buscar_usuario_por_matricula(self, matricula_inscrito):
        """Buscar usuario específicamente por matrícula"""
        try:
            if self.usuarios.empty:
                st.error("❌ No hay datos de usuarios disponibles")
                return None
            
            st.info(f"🔍 Buscando usuario por matrícula: '{matricula_inscrito}'")
            
            # Buscar exactamente por matrícula en la columna 'usuario'
            usuario_idx = self.usuarios[
                self.usuarios['usuario'].astype(str).str.strip() == matricula_inscrito
            ].index
            
            if not usuario_idx.empty:
                usuario_encontrado = self.usuarios.iloc[usuario_idx[0]]['usuario']
                rol_actual = self.usuarios.iloc[usuario_idx[0]]['rol']
                st.success(f"✅ Usuario encontrado: {usuario_encontrado} (rol actual: {rol_actual})")
                return usuario_idx[0]
            else:
                st.warning(f"⚠️ Usuario con matrícula '{matricula_inscrito}' no encontrado en usuarios.csv")
                return None
            
        except Exception as e:
            st.error(f"❌ Error en búsqueda de usuario: {e}")
            return None
    
    def actualizar_rol_usuario(self, usuario_idx, nuevo_rol, nueva_matricula):
        """Actualizar rol y matrícula del usuario en usuarios.csv"""
        try:
            if self.usuarios.empty or usuario_idx is None:
                st.error("❌ No hay datos de usuarios disponibles o índice inválido")
                return False
            
            # Obtener datos actuales del usuario
            usuario_actual = self.usuarios.loc[usuario_idx, 'usuario']
            rol_actual = self.usuarios.loc[usuario_idx, 'rol']
            
            st.info(f"🔄 Actualizando usuario: {usuario_actual}")
            st.info(f"   - Rol actual: {rol_actual}")
            st.info(f"   - Nuevo rol: {nuevo_rol}")
            st.info(f"   - Nueva matrícula: {nueva_matricula}")
            
            # Actualizar rol
            self.usuarios.loc[usuario_idx, 'rol'] = nuevo_rol
            
            # Actualizar usuario (matrícula)
            self.usuarios.loc[usuario_idx, 'usuario'] = nueva_matricula
            
            st.success(f"✅ Usuario actualizado exitosamente: {usuario_actual} -> {nueva_matricula} ({nuevo_rol})")
            return True
            
        except Exception as e:
            st.error(f"❌ Error actualizando usuario: {e}")
            return False
    
    def renombrar_archivos_pdf(self, matricula_vieja, matricula_nueva):
        """Renombrar archivos PDF en el servidor remoto - COMPLETAMENTE CORREGIDA"""
        try:
            if not cargador_remoto.conectar():
                st.error("❌ No se pudo conectar al servidor para renombrar archivos")
                return 0
            
            archivos_renombrados = 0
            directorio_uploads = os.path.join(st.secrets["remote_dir"], "uploads")
            
            try:
                archivos = cargador_remoto.sftp.listdir(directorio_uploads)
                st.info(f"📁 Buscando archivos de {matricula_vieja} en {directorio_uploads}")
                st.info(f"📋 Total de archivos en directorio: {len(archivos)}")
                
                for archivo in archivos:
                    # CORRECCIÓN CRÍTICA: Buscar archivos que contengan EXACTAMENTE la matrícula vieja
                    # y sean archivos PDF. Usamos una verificación más estricta para evitar 
                    # que MAT-EGR coincida con MAT-INS accidentalmente
                    if archivo.lower().endswith('.pdf') and matricula_vieja in archivo:
                        # VERIFICACIÓN ADICIONAL: Asegurarnos de que es el archivo correcto
                        # Buscando el patrón donde la matrícula es parte del nombre pero no necesariamente al inicio
                        # pero evitando falsos positivos
                        partes_nombre = archivo.split('_')
                        
                        # Si la matrícula está al inicio (caso ideal)
                        if archivo.startswith(matricula_vieja + '_'):
                            nuevo_nombre = archivo.replace(matricula_vieja, matricula_nueva)
                            es_valido = True
                        # Si la matrícula está en medio del nombre (caso menos común)
                        elif matricula_vieja + '_' in archivo:
                            nuevo_nombre = archivo.replace(matricula_vieja, matricula_nueva)
                            es_valido = True
                        else:
                            # Si no coincide claramente, saltar este archivo
                            es_valido = False
                            st.warning(f"⚠️ Saltando archivo '{archivo}' - patrón de matrícula no claro")
                        
                        if es_valido:
                            ruta_vieja = os.path.join(directorio_uploads, archivo)
                            ruta_nueva = os.path.join(directorio_uploads, nuevo_nombre)
                            
                            st.info(f"🔄 Confirmando renombrado: {archivo} -> {nuevo_nombre}")
                            
                            try:
                                # Verificar que el archivo origen existe
                                cargador_remoto.sftp.stat(ruta_vieja)
                                
                                # Verificar que el archivo destino no existe (para evitar sobreescribir)
                                try:
                                    cargador_remoto.sftp.stat(ruta_nueva)
                                    st.error(f"❌ El archivo destino ya existe: {ruta_nueva}")
                                    continue
                                except FileNotFoundError:
                                    # El archivo destino no existe, proceder con el renombrado
                                    pass
                                
                                # Renombrar archivo
                                cargador_remoto.sftp.rename(ruta_vieja, ruta_nueva)
                                archivos_renombrados += 1
                                st.success(f"✅ Renombrado exitosamente: {archivo} -> {nuevo_nombre}")
                                
                            except FileNotFoundError:
                                st.error(f"❌ Archivo origen no encontrado: {ruta_vieja}")
                            except Exception as rename_error:
                                st.error(f"❌ Error renombrando {archivo}: {rename_error}")
                
                if archivos_renombrados == 0:
                    st.warning(f"⚠️ No se encontraron archivos PDF para renombrar con la matrícula: {matricula_vieja}")
                    
                    # DEBUG: Mostrar archivos que podrían coincidir
                    archivos_pdf = [a for a in archivos if a.lower().endswith('.pdf')]
                    st.info(f"🔍 Archivos PDF en el directorio: {len(archivos_pdf)}")
                    
                    archivos_coincidentes = [a for a in archivos_pdf if matricula_vieja in a]
                    st.info(f"🔍 Archivos PDF que contienen '{matricula_vieja}': {len(archivos_coincidentes)}")
                    for archivo in archivos_coincidentes:
                        st.info(f"   - {archivo}")
                    
                    # También mostrar archivos con diferentes prefijos para debug
                    st.info("🔍 Archivos con diferentes prefijos para referencia:")
                    prefijos = ['MAT-INS', 'MAT-EST', 'MAT-EGR', 'MAT-CON']
                    for prefijo in prefijos:
                        archivos_prefijo = [a for a in archivos_pdf if a.startswith(prefijo)]
                        if archivos_prefijo:
                            st.info(f"   {prefijo}: {len(archivos_prefijo)} archivos")
                    
            except FileNotFoundError:
                st.warning(f"📁 Directorio de uploads no encontrado: {directorio_uploads}")
            except Exception as list_error:
                st.error(f"❌ Error listando archivos: {list_error}")
            
            cargador_remoto.desconectar()
            
            if archivos_renombrados > 0:
                st.success(f"🎉 Se renombraron {archivos_renombrados} archivos PDF correctamente")
            else:
                st.warning("📝 No se renombraron archivos PDF")
                
            return archivos_renombrados
            
        except Exception as e:
            st.error(f"❌ Error renombrando archivos: {e}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return 0

    def obtener_nombres_archivos_pdf(self, matricula):
        """Obtener los nombres de los archivos PDF renombrados para una matrícula - CORREGIDA"""
        try:
            if not cargador_remoto.conectar():
                return "Identificación Oficial"
            
            nombres_archivos = []
            directorio_uploads = os.path.join(st.secrets["remote_dir"], "uploads")
            
            try:
                archivos = cargador_remoto.sftp.listdir(directorio_uploads)
                
                # CORRECCIÓN: Buscar archivos que contengan exactamente la matrícula
                for archivo in archivos:
                    # Buscar archivos que contengan la matrícula y sean PDF
                    # Verificación más estricta para evitar falsos positivos
                    if (archivo.lower().endswith('.pdf') and 
                        (archivo.startswith(matricula + '_') or f"_{matricula}_" in archivo or matricula in archivo)):
                        nombres_archivos.append(archivo)
                
                st.info(f"🔍 Encontrados {len(nombres_archivos)} archivos PDF para {matricula}")
                
                # Mostrar los archivos encontrados para debug
                if nombres_archivos:
                    for archivo in nombres_archivos:
                        st.info(f"   📄 {archivo}")
                
            except FileNotFoundError:
                st.warning(f"📁 Directorio de uploads no encontrado: {directorio_uploads}")
            except Exception as list_error:
                st.error(f"❌ Error listando archivos: {list_error}")
            
            cargador_remoto.desconectar()
            
            # CORRECCIÓN: Unir todos los nombres de archivos con comas
            if nombres_archivos:
                resultado = ", ".join(nombres_archivos)
                st.success(f"📄 Archivos PDF registrados en contratados.csv: {resultado}")
                return resultado
            else:
                st.warning(f"⚠️ No se encontraron archivos PDF para la matrícula: {matricula}")
                return "Identificación Oficial"
                
        except Exception as e:
            st.error(f"❌ Error obteniendo nombres de archivos PDF: {e}")
            return "Identificación Oficial"

    def eliminar_inscrito_y_crear_estudiante(self, inscrito_data, datos_form):
        """Eliminar inscrito y crear estudiante - COMPLETAMENTE CORREGIDO"""
        try:
            matricula_inscrito = inscrito_data.get('matricula', '')
            matricula_estudiante = datos_form['matricula_estudiante']
            
            st.subheader("📋 Procesando archivos CSV...")
            
            # 1. ELIMINAR INSCRITO - CORREGIDO
            st.info("🗑️ Eliminando registro de inscritos.csv...")
            global df_inscritos
            
            if not df_inscritos.empty and 'matricula' in df_inscritos.columns:
                # Crear copia para no modificar el original durante la iteración
                df_inscritos_original = df_inscritos.copy()
                
                # Filtrar para excluir el registro a eliminar - CORREGIDO
                # Usar la matrícula exacta del inscrito seleccionado
                df_inscritos = df_inscritos_original[df_inscritos_original['matricula'] != matricula_inscrito]
                
                # Verificar si se eliminó
                if len(df_inscritos) < len(df_inscritos_original):
                    st.success(f"✅ Registro eliminado de inscritos.csv: {matricula_inscrito}")
                    
                    # Mostrar confirmación de eliminación
                    st.info(f"📊 Inscritos antes: {len(df_inscritos_original)}, después: {len(df_inscritos)}")
                else:
                    st.warning(f"⚠️ No se encontró el registro {matricula_inscrito} en inscritos.csv")
                    # Mostrar las matrículas disponibles para debug
                    st.info(f"📋 Matrículas en inscritos.csv: {list(df_inscritos_original['matricula'].astype(str).values)}")
            else:
                st.error("❌ No se pudo acceder a inscritos.csv")
                return False
            
            # 2. CREAR ESTUDIANTE - COMPLETAMENTE CORREGIDO
            st.info("🎓 Creando registro en estudiantes.csv...")
            global df_estudiantes
            
            # Preparar datos del nuevo estudiante - MÁS COMPLETO
            nuevo_estudiante = {
                'matricula': matricula_estudiante,
                'nombre_completo': inscrito_data.get('nombre_completo', ''),
                'programa': datos_form['programa'],
                'email': inscrito_data.get('email', ''),
                'telefono': inscrito_data.get('telefono', ''),
                'fecha_nacimiento': datos_form['fecha_nacimiento'].strftime('%Y-%m-%d'),
                'genero': datos_form['genero'],
                'fecha_inscripcion': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'estatus': datos_form['estatus'],
                'documentos_subidos': datos_form['documentos_subidos'],
                'fecha_registro': datos_form['fecha_registro'].strftime('%Y-%m-%d %H:%M:%S'),
                'programa_interes': datos_form['programa_interes'],
                'folio': datos_form['folio'],
                'como_se_entero': datos_form['como_se_entero'],
                'fecha_ingreso': datos_form['fecha_ingreso'].strftime('%Y-%m-%d'),
                'usuario': matricula_estudiante
            }
            
            # Mantener otros datos del inscrito que puedan existir
            campos_adicionales = [
                'curp', 'direccion', 'ciudad', 'estado', 'codigo_postal', 
                'nacionalidad', 'documentos_guardados'
            ]
            
            for campo in campos_adicionales:
                if campo in inscrito_data and pd.notna(inscrito_data[campo]):
                    nuevo_estudiante[campo] = inscrito_data[campo]
            
            # CORREGIR: Actualizar documentos_guardados con nueva matrícula
            if 'documentos_guardados' in nuevo_estudiante and nuevo_estudiante['documentos_guardados']:
                documentos_actualizados = str(nuevo_estudiante['documentos_guardados']).replace(
                    matricula_inscrito, matricula_estudiante
                )
                nuevo_estudiante['documentos_guardados'] = documentos_actualizados
            
            # Crear DataFrame para el nuevo estudiante
            nuevo_estudiante_df = pd.DataFrame([nuevo_estudiante])
            
            if df_estudiantes.empty:
                # Si no hay estudiantes, crear el DataFrame
                df_estudiantes = nuevo_estudiante_df
                st.success(f"✅ Registro creado en estudiantes.csv: {matricula_estudiante}")
            else:
                # Si ya hay estudiantes, concatenar
                # Asegurarse de que todas las columnas existan en ambos DataFrames
                for columna in nuevo_estudiante_df.columns:
                    if columna not in df_estudiantes.columns:
                        df_estudiantes[columna] = None
                
                for columna in df_estudiantes.columns:
                    if columna not in nuevo_estudiante_df.columns:
                        nuevo_estudiante_df[columna] = None
                
                # Concatenar el nuevo registro
                df_estudiantes = pd.concat([df_estudiantes, nuevo_estudiante_df], ignore_index=True)
                st.success(f"✅ Registro creado en estudiantes.csv: {matricula_estudiante}")
            
            # Mostrar confirmación
            st.info(f"📊 Estudiantes antes: {len(df_estudiantes)-1}, después: {len(df_estudiantes)}")
            
            return True
            
        except Exception as e:
            st.error(f"❌ Error procesando archivos CSV: {e}")
            import traceback
            st.error(f"Detalles: {traceback.format_exc()}")
            return False

    def eliminar_estudiante_y_crear_egresado(self, estudiante_data, datos_form):
        """Eliminar estudiante y crear egresado - NUEVA FUNCIÓN CORREGIDA"""
        try:
            matricula_estudiante = estudiante_data.get('matricula', '')
            matricula_egresado = datos_form['matricula_egresado']
            
            st.subheader("📋 Procesando archivos CSV...")
            
            # 1. ELIMINAR ESTUDIANTE
            st.info("🗑️ Eliminando registro de estudiantes.csv...")
            global df_estudiantes
            
            if not df_estudiantes.empty and 'matricula' in df_estudiantes.columns:
                # Crear copia para no modificar el original durante la iteración
                df_estudiantes_original = df_estudiantes.copy()
                
                # Filtrar para excluir el registro a eliminar
                df_estudiantes = df_estudiantes_original[df_estudiantes_original['matricula'] != matricula_estudiante]
                
                # Verificar si se eliminó
                if len(df_estudiantes) < len(df_estudiantes_original):
                    st.success(f"✅ Registro eliminado de estudiantes.csv: {matricula_estudiante}")
                    st.info(f"📊 Estudiantes antes: {len(df_estudiantes_original)}, después: {len(df_estudiantes)}")
                else:
                    st.warning(f"⚠️ No se encontró el registro {matricula_estudiante} en estudiantes.csv")
                    st.info(f"📋 Matrículas en estudiantes.csv: {list(df_estudiantes_original['matricula'].astype(str).values)}")
            else:
                st.error("❌ No se pudo acceder a estudiantes.csv")
                return False
            
            # 2. CREAR EGRESADO - CORREGIDO: Obtener nombres reales de archivos PDF
            st.info("🎓 Creando registro en egresados.csv...")
            global df_egresados
            
            # Obtener los nombres reales de los archivos PDF renombrados
            nombres_archivos_pdf = self.obtener_nombres_archivos_pdf(matricula_egresado)
            
            # Preparar datos del nuevo egresado según el layout
            nuevo_egresado = {
                'matricula': matricula_egresado,
                'nombre_completo': estudiante_data.get('nombre_completo', ''),
                'programa_original': datos_form['programa_original'],
                'fecha_graduacion': datos_form['fecha_graduacion'].strftime('%Y-%m-%d'),
                'nivel_academico': datos_form['nivel_academico'],
                'email': datos_form['email'],
                'telefono': datos_form['telefono'],
                'estado_laboral': datos_form['estado_laboral'],
                'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d'),
                'documentos_subidos': nombres_archivos_pdf  # USAR NOMBRES REALES DE ARCHIVOS PDF
            }
            
            # Crear DataFrame para el nuevo egresado
            nuevo_egresado_df = pd.DataFrame([nuevo_egresado])
            
            if df_egresados.empty:
                # Si no hay egresados, crear el DataFrame
                df_egresados = nuevo_egresado_df
                st.success(f"✅ Registro creado en egresados.csv: {matricula_egresado}")
            else:
                # Si ya hay egresados, concatenar
                # Asegurarse de que todas las columnas existan en ambos DataFrames
                for columna in nuevo_egresado_df.columns:
                    if columna not in df_egresados.columns:
                        df_egresados[columna] = None
                
                for columna in df_egresados.columns:
                    if columna not in nuevo_egresado_df.columns:
                        nuevo_egresado_df[columna] = None
                
                # Concatenar el nuevo registro
                df_egresados = pd.concat([df_egresados, nuevo_egresado_df], ignore_index=True)
                st.success(f"✅ Registro creado en egresados.csv: {matricula_egresado}")
            
            # Mostrar confirmación
            st.info(f"📊 Egresados antes: {len(df_egresados)-1}, después: {len(df_egresados)}")
            st.info(f"📁 Archivos PDF registrados: {nombres_archivos_pdf}")
            
            return True
            
        except Exception as e:
            st.error(f"❌ Error procesando archivos CSV: {e}")
            import traceback
            st.error(f"Detalles: {traceback.format_exc()}")
            return False

    def eliminar_egresado_y_crear_contratado(self, egresado_data, datos_form):
        """Eliminar egresado y crear contratado - NUEVA FUNCIÓN"""
        try:
            matricula_egresado = egresado_data.get('matricula', '')
            matricula_contratado = datos_form['matricula_contratado']
            
            st.subheader("📋 Procesando archivos CSV...")
            
            # 1. ELIMINAR EGRESADO
            st.info("🗑️ Eliminando registro de egresados.csv...")
            global df_egresados
            
            if not df_egresados.empty and 'matricula' in df_egresados.columns:
                # Crear copia para no modificar el original durante la iteración
                df_egresados_original = df_egresados.copy()
                
                # Filtrar para excluir el registro a eliminar
                df_egresados = df_egresados_original[df_egresados_original['matricula'] != matricula_egresado]
                
                # Verificar si se eliminó
                if len(df_egresados) < len(df_egresados_original):
                    st.success(f"✅ Registro eliminado de egresados.csv: {matricula_egresado}")
                    st.info(f"📊 Egresados antes: {len(df_egresados_original)}, después: {len(df_egresados)}")
                else:
                    st.warning(f"⚠️ No se encontró el registro {matricula_egresado} en egresados.csv")
                    st.info(f"📋 Matrículas en egresados.csv: {list(df_egresados_original['matricula'].astype(str).values)}")
            else:
                st.error("❌ No se pudo acceder a egresados.csv")
                return False
            
            # 2. CREAR CONTRATADO
            st.info("💼 Creando registro en contratados.csv...")
            global df_contratados
            
            # Obtener los nombres reales de los archivos PDF renombrados
            nombres_archivos_pdf = self.obtener_nombres_archivos_pdf(matricula_contratado)
            
            # Preparar datos del nuevo contratado según el layout
            nuevo_contratado = {
                'matricula': matricula_contratado,
                'fecha_contratacion': datos_form['fecha_contratacion'].strftime('%Y-%m-%d'),
                'puesto': datos_form['puesto'],
                'departamento': datos_form['departamento'],
                'estatus': datos_form['estatus'],
                'salario': datos_form['salario'],
                'tipo_contrato': datos_form['tipo_contrato'],
                'fecha_inicio': datos_form['fecha_inicio'].strftime('%Y-%m-%d'),
                'fecha_fin': datos_form['fecha_fin'].strftime('%Y-%m-%d'),
                'documentos_subidos': nombres_archivos_pdf  # USAR NOMBRES REALES DE ARCHIVOS PDF
            }
            
            # Crear DataFrame para el nuevo contratado
            nuevo_contratado_df = pd.DataFrame([nuevo_contratado])
            
            if df_contratados.empty:
                # Si no hay contratados, crear el DataFrame
                df_contratados = nuevo_contratado_df
                st.success(f"✅ Registro creado en contratados.csv: {matricula_contratado}")
            else:
                # Si ya hay contratados, concatenar
                # Asegurarse de que todas las columnas existan en ambos DataFrames
                for columna in nuevo_contratado_df.columns:
                    if columna not in df_contratados.columns:
                        df_contratados[columna] = None
                
                for columna in df_contratados.columns:
                    if columna not in nuevo_contratado_df.columns:
                        nuevo_contratado_df[columna] = None
                
                # Concatenar el nuevo registro
                df_contratados = pd.concat([df_contratados, nuevo_contratado_df], ignore_index=True)
                st.success(f"✅ Registro creado en contratados.csv: {matricula_contratado}")
            
            # Mostrar confirmación
            st.info(f"📊 Contratados antes: {len(df_contratados)-1}, después: {len(df_contratados)}")
            st.info(f"📁 Archivos PDF registrados: {nombres_archivos_pdf}")
            
            return True
            
        except Exception as e:
            st.error(f"❌ Error procesando archivos CSV: {e}")
            import traceback
            st.error(f"Detalles: {traceback.format_exc()}")
            return False
    
    def migrar_inscrito_a_estudiante(self, inscrito_data):
        """Migrar de inscrito a estudiante - CORREGIDO CON VALIDACIÓN"""
        try:
            # VALIDACIÓN CRÍTICA: Verificar que inscrito_data no sea None
            if inscrito_data is None:
                st.error("❌ Error: No se encontraron datos del inscrito seleccionado")
                st.info("🔁 Por favor, seleccione un inscrito nuevamente")
                # Limpiar el estado de sesión
                if 'inscrito_seleccionado' in st.session_state:
                    del st.session_state.inscrito_seleccionado
                return False
            
            matricula_inscrito = inscrito_data.get('matricula', '')
            nombre_completo = inscrito_data.get('nombre_completo', '')
            email_inscrito = inscrito_data.get('email', '')
            
            # Validar datos críticos
            if not matricula_inscrito:
                st.error("❌ Error: No se pudo obtener la matrícula del inscrito")
                return False
            
            st.info(f"🔄 Iniciando migración: INSCRITO → ESTUDIANTE")
            st.info(f"📛 Nombre: {nombre_completo}")
            st.info(f"📧 Email: {email_inscrito}")
            st.info(f"🆔 Matrícula actual: {matricula_inscrito}")
            
            # Generar nueva matrícula
            matricula_estudiante = self.generar_nueva_matricula(matricula_inscrito, 'estudiante')
            st.info(f"🆕 Matrícula nueva: {matricula_estudiante}")
            
            # BUSQUEDA DEL USUARIO
            st.subheader("🔍 Búsqueda de Usuario en Base de Datos")
            usuario_idx = self.buscar_usuario_por_matricula(matricula_inscrito)
            
            if usuario_idx is None:
                st.error(f"❌ No se encontró el usuario '{matricula_inscrito}' en usuarios.csv")
                st.error("❌ No se puede proceder con la migración. Verifique que el usuario exista.")
                return False
            
            # Formulario para completar datos del estudiante
            st.subheader("📝 Formulario de Datos del Estudiante")
            
            with st.form("formulario_estudiante"):
                st.write("Complete la información requerida para el estudiante:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Datos básicos del estudiante
                    programa = st.text_input("Programa Educativo*", 
                                           value=inscrito_data.get('programa_interes', 'Especialidad en Enfermería Cardiovascular'))
                    fecha_nacimiento = st.date_input("Fecha de Nacimiento*", 
                                                   value=datetime.strptime(inscrito_data.get('fecha_nacimiento', '1998-09-10'), '%Y-%m-%d') 
                                                   if inscrito_data.get('fecha_nacimiento') else datetime.now())
                    genero = st.selectbox("Género*", ["Masculino", "Femenino", "Otro", "Prefiero no decir"])
                    fecha_ingreso = st.date_input("Fecha de Ingreso*", value=datetime.now())
                    programa_interes = st.text_input("Programa de Interés*", 
                                                   value=inscrito_data.get('programa_interes', 'Especialidad en Enfermería Cardiovascular'))
                
                with col2:
                    # Información adicional
                    folio = st.text_input("Folio", value=inscrito_data.get('folio', 'FOL-20250930-1830'))
                    como_se_entero = st.selectbox("¿Cómo se enteró del programa?*",
                                                ["Internet", "Redes Sociales", "Amigo/Familiar", 
                                                 "Publicidad", "Evento", "Otro"],
                                                index=1)
                    documentos_subidos = st.text_input("Documentos Subidos*", 
                                                     value=inscrito_data.get('documentos_subidos', '4'))
                    fecha_registro_str = inscrito_data.get('fecha_registro', '2025-09-30 15:18:53')
                    try:
                        fecha_registro_default = datetime.strptime(fecha_registro_str.split()[0], '%Y-%m-%d')
                    except:
                        fecha_registro_default = datetime.now()
                    
                    fecha_registro = st.date_input("Fecha de Registro*", value=fecha_registro_default)
                    estatus = st.selectbox("Estatus*", ["ACTIVO", "INACTIVO", "PENDIENTE"], index=0)
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Estudiante")
                
                if submitted:
                    # Validar campos obligatorios
                    if not programa or not programa_interes:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Guardar los datos del formulario en session_state para usar después
                    st.session_state.datos_formulario = {
                        'programa': programa,
                        'fecha_nacimiento': fecha_nacimiento,
                        'genero': genero,
                        'fecha_ingreso': fecha_ingreso,
                        'programa_interes': programa_interes,
                        'folio': folio,
                        'como_se_entero': como_se_entero,
                        'documentos_subidos': documentos_subidos,
                        'fecha_registro': fecha_registro,
                        'estatus': estatus,
                        'usuario_idx': usuario_idx,
                        'matricula_inscrito': matricula_inscrito,
                        'matricula_estudiante': matricula_estudiante,
                        'nombre_completo': nombre_completo,
                        'email_inscrito': email_inscrito,
                        'inscrito_data': inscrito_data  # Guardar el objeto completo
                    }
                    
                    # Mostrar resumen y pedir confirmación final FUERA del form
                    st.session_state.mostrar_confirmacion = True
                    st.rerun()
            
            # CONFIRMACIÓN FINAL FUERA DEL FORM
            if st.session_state.get('mostrar_confirmacion', False):
                datos_form = st.session_state.get('datos_formulario', {})
                
                if datos_form:
                    st.subheader("📋 Resumen de la Migración")
                    st.info(f"**Matrícula actual:** {datos_form['matricula_inscrito']}")
                    st.info(f"**Nueva matrícula:** {datos_form['matricula_estudiante']}")
                    st.info(f"**Nombre:** {datos_form['nombre_completo']}")
                    st.info(f"**Programa:** {datos_form['programa']}")
                    st.info(f"**Email:** {datos_form['email_inscrito']}")
                    
                    st.warning("⚠️ **¿Está seguro de proceder con la migración?** Esta acción no se puede deshacer.")
                    
                    col_confirm1, col_confirm2 = st.columns(2)
                    with col_confirm1:
                        if st.button("✅ Sí, proceder con la migración", type="primary", key="confirmar_migracion"):
                            return self.ejecutar_migracion_inscrito_estudiante(datos_form)
                    
                    with col_confirm2:
                        if st.button("❌ Cancelar migración", key="cancelar_migracion"):
                            st.info("Migración cancelada")
                            # Limpiar estados
                            if 'mostrar_confirmacion' in st.session_state:
                                del st.session_state.mostrar_confirmacion
                            if 'datos_formulario' in st.session_state:
                                del st.session_state.datos_formulario
                            st.rerun()
                            return False
            
            return False
            
        except Exception as e:
            st.error(f"❌ Error en la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def migrar_estudiante_a_egresado(self, estudiante_data):
        """Migrar de estudiante a egresado - NUEVA FUNCIÓN"""
        try:
            # VALIDACIÓN CRÍTICA: Verificar que estudiante_data no sea None
            if estudiante_data is None:
                st.error("❌ Error: No se encontraron datos del estudiante seleccionado")
                st.info("🔁 Por favor, seleccione un estudiante nuevamente")
                # Limpiar el estado de sesión
                if 'estudiante_seleccionado' in st.session_state:
                    del st.session_state.estudiante_seleccionado
                return False
            
            matricula_estudiante = estudiante_data.get('matricula', '')
            nombre_completo = estudiante_data.get('nombre_completo', '')
            email_estudiante = estudiante_data.get('email', '')
            
            # Validar datos críticos
            if not matricula_estudiante:
                st.error("❌ Error: No se pudo obtener la matrícula del estudiante")
                return False
            
            st.info(f"🔄 Iniciando migración: ESTUDIANTE → EGRESADO")
            st.info(f"📛 Nombre: {nombre_completo}")
            st.info(f"📧 Email: {email_estudiante}")
            st.info(f"🆔 Matrícula actual: {matricula_estudiante}")
            
            # Generar nueva matrícula
            matricula_egresado = self.generar_nueva_matricula(matricula_estudiante, 'egresado')
            st.info(f"🆕 Matrícula nueva: {matricula_egresado}")
            
            # BUSQUEDA DEL USUARIO
            st.subheader("🔍 Búsqueda de Usuario en Base de Datos")
            usuario_idx = self.buscar_usuario_por_matricula(matricula_estudiante)
            
            if usuario_idx is None:
                st.error(f"❌ No se encontró el usuario '{matricula_estudiante}' en usuarios.csv")
                st.error("❌ No se puede proceder con la migración. Verifique que el usuario exista.")
                return False
            
            # Formulario para completar datos del egresado
            st.subheader("📝 Formulario de Datos del Egresado")
            
            with st.form("formulario_egresado"):
                st.write("Complete la información requerida para el egresado:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Datos básicos del egresado
                    programa_original = st.text_input("Programa Original*", 
                                                    value=estudiante_data.get('programa', 'Especialidad en Enfermería Cardiovascular'))
                    fecha_graduacion = st.date_input("Fecha de Graduación*", value=datetime.now())
                    nivel_academico = st.selectbox("Nivel Académico*", 
                                                 ["Especialidad", "Maestría", "Doctorado", "Diplomado"],
                                                 index=0)
                    estado_laboral = st.selectbox("Estado Laboral*",
                                                ["Contratada", "Buscando empleo", "Empleado independiente", "Estudiando", "Otro"],
                                                index=0)
                
                with col2:
                    # Información adicional
                    documentos_subidos = st.text_input("Documentos Subidos*", 
                                                     value="Cédula Profesional")
                    # Campos que no existen en estudiantes pero son necesarios para egresados
                    telefono = st.text_input("Teléfono", 
                                           value=estudiante_data.get('telefono', ''))
                    email = st.text_input("Email*", 
                                        value=estudiante_data.get('email', ''))
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Egresado")
                
                if submitted:
                    # Validar campos obligatorios
                    if not programa_original or not nivel_academico or not estado_laboral or not email:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Guardar los datos del formulario en session_state para usar después
                    st.session_state.datos_formulario_egresado = {
                        'programa_original': programa_original,
                        'fecha_graduacion': fecha_graduacion,
                        'nivel_academico': nivel_academico,
                        'estado_laboral': estado_laboral,
                        'documentos_subidos': documentos_subidos,
                        'telefono': telefono,
                        'email': email,
                        'usuario_idx': usuario_idx,
                        'matricula_estudiante': matricula_estudiante,
                        'matricula_egresado': matricula_egresado,
                        'nombre_completo': nombre_completo,
                        'estudiante_data': estudiante_data  # Guardar el objeto completo
                    }
                    
                    # Mostrar resumen y pedir confirmación final FUERA del form
                    st.session_state.mostrar_confirmacion_egresado = True
                    st.rerun()
            
            # CONFIRMACIÓN FINAL FUERA DEL FORM
            if st.session_state.get('mostrar_confirmacion_egresado', False):
                datos_form = st.session_state.get('datos_formulario_egresado', {})
                
                if datos_form:
                    st.subheader("📋 Resumen de la Migración")
                    st.info(f"**Matrícula actual:** {datos_form['matricula_estudiante']}")
                    st.info(f"**Nueva matrícula:** {datos_form['matricula_egresado']}")
                    st.info(f"**Nombre:** {datos_form['nombre_completo']}")
                    st.info(f"**Programa Original:** {datos_form['programa_original']}")
                    st.info(f"**Nivel Académico:** {datos_form['nivel_academico']}")
                    st.info(f"**Estado Laboral:** {datos_form['estado_laboral']}")
                    
                    st.warning("⚠️ **¿Está seguro de proceder con la migración?** Esta acción no se puede deshacer.")
                    
                    col_confirm1, col_confirm2 = st.columns(2)
                    with col_confirm1:
                        if st.button("✅ Sí, proceder con la migración", type="primary", key="confirmar_migracion_egresado"):
                            return self.ejecutar_migracion_estudiante_egresado(datos_form)
                    
                    with col_confirm2:
                        if st.button("❌ Cancelar migración", key="cancelar_migracion_egresado"):
                            st.info("Migración cancelada")
                            # Limpiar estados
                            if 'mostrar_confirmacion_egresado' in st.session_state:
                                del st.session_state.mostrar_confirmacion_egresado
                            if 'datos_formulario_egresado' in st.session_state:
                                del st.session_state.datos_formulario_egresado
                            st.rerun()
                            return False
            
            return False
            
        except Exception as e:
            st.error(f"❌ Error en la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def migrar_egresado_a_contratado(self, egresado_data):
        """Migrar de egresado a contratado - NUEVA FUNCIÓN"""
        try:
            # VALIDACIÓN CRÍTICA: Verificar que egresado_data no sea None
            if egresado_data is None:
                st.error("❌ Error: No se encontraron datos del egresado seleccionado")
                st.info("🔁 Por favor, seleccione un egresado nuevamente")
                # Limpiar el estado de sesión
                if 'egresado_seleccionado' in st.session_state:
                    del st.session_state.egresado_seleccionado
                return False
            
            matricula_egresado = egresado_data.get('matricula', '')
            nombre_completo = egresado_data.get('nombre_completo', '')
            email_egresado = egresado_data.get('email', '')
            
            # Validar datos críticos
            if not matricula_egresado:
                st.error("❌ Error: No se pudo obtener la matrícula del egresado")
                return False
            
            st.info(f"🔄 Iniciando migración: EGRESADO → CONTRATADO")
            st.info(f"📛 Nombre: {nombre_completo}")
            st.info(f"📧 Email: {email_egresado}")
            st.info(f"🆔 Matrícula actual: {matricula_egresado}")
            
            # Generar nueva matrícula
            matricula_contratado = self.generar_nueva_matricula(matricula_egresado, 'contratado')
            st.info(f"🆕 Matrícula nueva: {matricula_contratado}")
            
            # BUSQUEDA DEL USUARIO
            st.subheader("🔍 Búsqueda de Usuario en Base de Datos")
            usuario_idx = self.buscar_usuario_por_matricula(matricula_egresado)
            
            if usuario_idx is None:
                st.error(f"❌ No se encontró el usuario '{matricula_egresado}' en usuarios.csv")
                st.error("❌ No se puede proceder con la migración. Verifique que el usuario exista.")
                return False
            
            # Formulario para completar datos del contratado
            st.subheader("📝 Formulario de Datos del Contratado")
            
            with st.form("formulario_contratado"):
                st.write("Complete la información requerida para el contratado:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Datos básicos del contratado
                    fecha_contratacion = st.date_input("Fecha de Contratación*", value=datetime.now())
                    puesto = st.text_input("Puesto*", 
                                         value="Enfermera Especialista en Cardiología")
                    departamento = st.text_input("Departamento*", 
                                               value="Terapia Intensiva Cardiovascular")
                    estatus = st.selectbox("Estatus*", 
                                         ["Activo", "Inactivo", "Licencia", "Baja"],
                                         index=0)
                
                with col2:
                    # Información adicional del contratado
                    salario = st.text_input("Salario*", 
                                          value="25000 MXN")
                    tipo_contrato = st.selectbox("Tipo de Contrato*", 
                                               ["Tiempo completo", "Medio tiempo", "Por honorarios", "Temporal"],
                                               index=0)
                    fecha_inicio = st.date_input("Fecha Inicio*", value=datetime.now())
                    fecha_fin = st.date_input("Fecha Fin*", 
                                            value=datetime.now() + timedelta(days=365))
                    documentos_subidos = st.text_input("Documentos Subidos*", 
                                                     value="Identificación Oficial")
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Contratado")
                
                if submitted:
                    # Validar campos obligatorios
                    if not puesto or not departamento or not estatus or not salario or not tipo_contrato:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Guardar los datos del formulario en session_state para usar después
                    st.session_state.datos_formulario_contratado = {
                        'fecha_contratacion': fecha_contratacion,
                        'puesto': puesto,
                        'departamento': departamento,
                        'estatus': estatus,
                        'salario': salario,
                        'tipo_contrato': tipo_contrato,
                        'fecha_inicio': fecha_inicio,
                        'fecha_fin': fecha_fin,
                        'documentos_subidos': documentos_subidos,
                        'usuario_idx': usuario_idx,
                        'matricula_egresado': matricula_egresado,
                        'matricula_contratado': matricula_contratado,
                        'nombre_completo': nombre_completo,
                        'egresado_data': egresado_data  # Guardar el objeto completo
                    }
                    
                    # Mostrar resumen y pedir confirmación final FUERA del form
                    st.session_state.mostrar_confirmacion_contratado = True
                    st.rerun()
            
            # CONFIRMACIÓN FINAL FUERA DEL FORM
            if st.session_state.get('mostrar_confirmacion_contratado', False):
                datos_form = st.session_state.get('datos_formulario_contratado', {})
                
                if datos_form:
                    st.subheader("📋 Resumen de la Migración")
                    st.info(f"**Matrícula actual:** {datos_form['matricula_egresado']}")
                    st.info(f"**Nueva matrícula:** {datos_form['matricula_contratado']}")
                    st.info(f"**Nombre:** {datos_form['nombre_completo']}")
                    st.info(f"**Puesto:** {datos_form['puesto']}")
                    st.info(f"**Departamento:** {datos_form['departamento']}")
                    st.info(f"**Salario:** {datos_form['salario']}")
                    st.info(f"**Tipo de Contrato:** {datos_form['tipo_contrato']}")
                    
                    st.warning("⚠️ **¿Está seguro de proceder con la migración?** Esta acción no se puede deshacer.")
                    
                    col_confirm1, col_confirm2 = st.columns(2)
                    with col_confirm1:
                        if st.button("✅ Sí, proceder con la migración", type="primary", key="confirmar_migracion_contratado"):
                            return self.ejecutar_migracion_egresado_contratado(datos_form)
                    
                    with col_confirm2:
                        if st.button("❌ Cancelar migración", key="cancelar_migracion_contratado"):
                            st.info("Migración cancelada")
                            # Limpiar estados
                            if 'mostrar_confirmacion_contratado' in st.session_state:
                                del st.session_state.mostrar_confirmacion_contratado
                            if 'datos_formulario_contratado' in st.session_state:
                                del st.session_state.datos_formulario_contratado
                            st.rerun()
                            return False
            
            return False
            
        except Exception as e:
            st.error(f"❌ Error en la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def ejecutar_migracion_inscrito_estudiante(self, datos_form):
        """Ejecutar el proceso de migración inscrito → estudiante - CORREGIDO"""
        try:
            # Extraer datos del formulario
            usuario_idx = datos_form['usuario_idx']
            matricula_inscrito = datos_form['matricula_inscrito']
            matricula_estudiante = datos_form['matricula_estudiante']
            inscrito_data = datos_form['inscrito_data']
            
            # Validar datos críticos
            if not inscrito_data:
                st.error("❌ Error: Datos del inscrito no disponibles")
                return False
            
            # 1. Actualizar usuario en usuarios.csv
            st.subheader("👤 Actualizando usuario en usuarios.csv...")
            if not self.actualizar_rol_usuario(usuario_idx, 'estudiante', matricula_estudiante):
                st.error("❌ Error actualizando usuario en la base de datos")
                return False
            
            # 2. Renombrar archivos PDF
            st.subheader("📁 Renombrando archivos PDF en uploads/...")
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_inscrito, matricula_estudiante)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.warning("⚠️ No se renombraron archivos PDF")
            
            # 3. Eliminar inscrito y crear estudiante
            if not self.eliminar_inscrito_y_crear_estudiante(inscrito_data, datos_form):
                st.error("❌ Error procesando archivos CSV")
                return False
            
            # 4. Guardar cambios
            st.subheader("💾 Guardando cambios en el servidor...")
            if self.guardar_cambios():
                usuario_actual = self.usuarios.loc[usuario_idx, 'usuario']
                auth.registrar_bitacora('MIGRACION_INSCRITO_ESTUDIANTE', 
                                      f'Usuario {usuario_actual} migrado de inscrito a estudiante. Matrícula: {matricula_inscrito} -> {matricula_estudiante}')
                
                st.success(f"🎉 ¡Migración completada exitosamente!")
                st.balloons()
                
                # Mostrar resumen final
                st.subheader("📊 Resumen Final de la Migración")
                st.success(f"✅ Usuario actualizado: {matricula_inscrito} → {matricula_estudiante}")
                st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
                st.success(f"✅ Registro creado en estudiantes.csv")
                st.success(f"✅ Registro eliminado de inscritos.csv")
                
                # Limpiar estado de sesión
                if 'inscrito_seleccionado' in st.session_state:
                    del st.session_state.inscrito_seleccionado
                if 'mostrar_confirmacion' in st.session_state:
                    del st.session_state.mostrar_confirmacion
                if 'datos_formulario' in st.session_state:
                    del st.session_state.datos_formulario
                
                # Recargar datos
                cargar_datos_completos.clear()
                st.rerun()
                return True
            else:
                st.error("❌ Error guardando cambios en el servidor")
                return False
                
        except Exception as e:
            st.error(f"❌ Error ejecutando la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def ejecutar_migracion_estudiante_egresado(self, datos_form):
        """Ejecutar el proceso de migración estudiante → egresado - NUEVA FUNCIÓN"""
        try:
            # Extraer datos del formulario
            usuario_idx = datos_form['usuario_idx']
            matricula_estudiante = datos_form['matricula_estudiante']
            matricula_egresado = datos_form['matricula_egresado']
            estudiante_data = datos_form['estudiante_data']
            
            # Validar datos críticos
            if not estudiante_data:
                st.error("❌ Error: Datos del estudiante no disponibles")
                return False
            
            # 1. Actualizar usuario en usuarios.csv
            st.subheader("👤 Actualizando usuario en usuarios.csv...")
            if not self.actualizar_rol_usuario(usuario_idx, 'egresado', matricula_egresado):
                st.error("❌ Error actualizando usuario en la base de datos")
                return False
            
            # 2. Renombrar archivos PDF
            st.subheader("📁 Renombrando archivos PDF en uploads/...")
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_estudiante, matricula_egresado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.warning("⚠️ No se renombraron archivos PDF")
            
            # 3. Eliminar estudiante y crear egresado
            if not self.eliminar_estudiante_y_crear_egresado(estudiante_data, datos_form):
                st.error("❌ Error procesando archivos CSV")
                return False
            
            # 4. Guardar cambios
            st.subheader("💾 Guardando cambios en el servidor...")
            if self.guardar_cambios():
                usuario_actual = self.usuarios.loc[usuario_idx, 'usuario']
                auth.registrar_bitacora('MIGRACION_ESTUDIANTE_EGRESADO', 
                                      f'Usuario {usuario_actual} migrado de estudiante a egresado. Matrícula: {matricula_estudiante} -> {matricula_egresado}')
                
                st.success(f"🎉 ¡Migración completada exitosamente!")
                st.balloons()
                
                # Mostrar resumen final
                st.subheader("📊 Resumen Final de la Migración")
                st.success(f"✅ Usuario actualizado: {matricula_estudiante} → {matricula_egresado}")
                st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
                st.success(f"✅ Registro creado en egresados.csv")
                st.success(f"✅ Registro eliminado de estudiantes.csv")
                
                # Limpiar estado de sesión
                if 'estudiante_seleccionado' in st.session_state:
                    del st.session_state.estudiante_seleccionado
                if 'mostrar_confirmacion_egresado' in st.session_state:
                    del st.session_state.mostrar_confirmacion_egresado
                if 'datos_formulario_egresado' in st.session_state:
                    del st.session_state.datos_formulario_egresado
                
                # Recargar datos
                cargar_datos_completos.clear()
                st.rerun()
                return True
            else:
                st.error("❌ Error guardando cambios en el servidor")
                return False
                
        except Exception as e:
            st.error(f"❌ Error ejecutando la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def ejecutar_migracion_egresado_contratado(self, datos_form):
        """Ejecutar el proceso de migración egresado → contratado - NUEVA FUNCIÓN"""
        try:
            # Extraer datos del formulario
            usuario_idx = datos_form['usuario_idx']
            matricula_egresado = datos_form['matricula_egresado']
            matricula_contratado = datos_form['matricula_contratado']
            egresado_data = datos_form['egresado_data']
            
            # Validar datos críticos
            if not egresado_data:
                st.error("❌ Error: Datos del egresado no disponibles")
                return False
            
            # 1. Actualizar usuario en usuarios.csv
            st.subheader("👤 Actualizando usuario en usuarios.csv...")
            if not self.actualizar_rol_usuario(usuario_idx, 'contratado', matricula_contratado):
                st.error("❌ Error actualizando usuario en la base de datos")
                return False
            
            # 2. Renombrar archivos PDF
            st.subheader("📁 Renombrando archivos PDF en uploads/...")
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_egresado, matricula_contratado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.warning("⚠️ No se renombraron archivos PDF")
            
            # 3. Eliminar egresado y crear contratado
            if not self.eliminar_egresado_y_crear_contratado(egresado_data, datos_form):
                st.error("❌ Error procesando archivos CSV")
                return False
            
            # 4. Guardar cambios
            st.subheader("💾 Guardando cambios en el servidor...")
            if self.guardar_cambios():
                usuario_actual = self.usuarios.loc[usuario_idx, 'usuario']
                auth.registrar_bitacora('MIGRACION_EGRESADO_CONTRATADO', 
                                      f'Usuario {usuario_actual} migrado de egresado a contratado. Matrícula: {matricula_egresado} -> {matricula_contratado}')
                
                st.success(f"🎉 ¡Migración completada exitosamente!")
                st.balloons()
                
                # Mostrar resumen final
                st.subheader("📊 Resumen Final de la Migración")
                st.success(f"✅ Usuario actualizado: {matricula_egresado} → {matricula_contratado}")
                st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
                st.success(f"✅ Registro creado en contratados.csv")
                st.success(f"✅ Registro eliminado de egresados.csv")
                
                # Limpiar estado de sesión
                if 'egresado_seleccionado' in st.session_state:
                    del st.session_state.egresado_seleccionado
                if 'mostrar_confirmacion_contratado' in st.session_state:
                    del st.session_state.mostrar_confirmacion_contratado
                if 'datos_formulario_contratado' in st.session_state:
                    del st.session_state.datos_formulario_contratado
                
                # Recargar datos
                cargar_datos_completos.clear()
                st.rerun()
                return True
            else:
                st.error("❌ Error guardando cambios en el servidor")
                return False
                
        except Exception as e:
            st.error(f"❌ Error ejecutando la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def guardar_cambios(self):
        """Guardar todos los cambios en el servidor remoto - MEJORADO"""
        try:
            with st.spinner("💾 Guardando cambios en el servidor remoto..."):
                cambios_realizados = 0
                
                # Actualizar referencias globales
                global df_inscritos, df_estudiantes, df_egresados, df_contratados, df_usuarios, df_bitacora
                self.inscritos = df_inscritos
                self.estudiantes = df_estudiantes
                self.egresados = df_egresados
                self.contratados = df_contratados
                self.usuarios = df_usuarios
                
                # Guardar usuarios
                if editor.guardar_dataframe_remoto(self.usuarios, editor.obtener_ruta_archivo('usuarios')):
                    cambios_realizados += 1
                    st.success("✅ usuarios.csv guardado")
                else:
                    st.error("❌ Error guardando usuarios.csv")
                
                # Guardar inscritos
                if editor.guardar_dataframe_remoto(self.inscritos, editor.obtener_ruta_archivo('inscritos')):
                    cambios_realizados += 1
                    st.success("✅ inscritos.csv guardado")
                else:
                    st.error("❌ Error guardando inscritos.csv")
                
                # Guardar estudiantes
                if editor.guardar_dataframe_remoto(self.estudiantes, editor.obtener_ruta_archivo('estudiantes')):
                    cambios_realizados += 1
                    st.success("✅ estudiantes.csv guardado")
                else:
                    st.error("❌ Error guardando estudiantes.csv")
                
                # Guardar egresados
                if editor.guardar_dataframe_remoto(self.egresados, editor.obtener_ruta_archivo('egresados')):
                    cambios_realizados += 1
                    st.success("✅ egresados.csv guardado")
                else:
                    st.error("❌ Error guardando egresados.csv")
                
                # Guardar contratados
                if editor.guardar_dataframe_remoto(self.contratados, editor.obtener_ruta_archivo('contratados')):
                    cambios_realizados += 1
                    st.success("✅ contratados.csv guardado")
                else:
                    st.error("❌ Error guardando contratados.csv")
                
                # Guardar bitácora
                if editor.guardar_dataframe_remoto(df_bitacora, editor.obtener_ruta_archivo('bitacora')):
                    cambios_realizados += 1
                    st.success("✅ bitacora.csv guardado")
                
                if cambios_realizados >= 5:  # Al menos usuarios, inscritos, estudiantes, egresados y contratados
                    st.success("✅ Todos los cambios guardados exitosamente en el servidor")
                    return True
                else:
                    st.error("❌ No se pudieron guardar todos los cambios en el servidor")
                    return False
                
        except Exception as e:
            st.error(f"❌ Error guardando cambios: {e}")
            return False

# Instancia del sistema de migración
migrador = SistemaMigracion()

# =============================================================================
# INTERFAZ PRINCIPAL DEL MIGRADOR
# =============================================================================

def mostrar_login():
    """Interfaz de login para el migrador"""
    st.title("🔄 Sistema Escuela Enfermería - Modo Migración")
#    st.subheader("Instituto Nacional de Cardiología")
    st.markdown("---")
    
    # Estado de la carga remota
    with st.expander("🌐 Estado de la Carga Remota", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Inscritos", len(df_inscritos) if not df_inscritos.empty else 0)
        with col2:
            st.metric("Estudiantes", len(df_estudiantes) if not df_estudiantes.empty else 0)
        with col3:
            st.metric("Egresados", len(df_egresados) if not df_egresados.empty else 0)
        with col4:
            st.metric("Contratados", len(df_contratados) if not df_contratados.empty else 0)

        if st.button("🔄 Recargar Datos Remotos"):
            # Limpiar cache y recargar
            cargar_datos_completos.clear()
            st.rerun()
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔐 Acceso de Administrador")
            st.info("Ingrese sus credenciales del archivo config/usuarios.csv")
            
            usuario = st.text_input("👤 Usuario", placeholder="Ej: administrador")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Contraseña del usuario")
            
            login_button = st.form_submit_button("🚀 Ingresar al Migrador")

            if login_button:
                if usuario and password:
                    if auth.verificar_login(usuario, password):
                        st.rerun()
                    else:
                        st.error("❌ No se pudo iniciar sesión. Verifique sus credenciales.")
                else:
                    st.warning("⚠️ Complete todos los campos")

def mostrar_interfaz_migrador():
    """Interfaz principal del sistema de migración"""
    st.title("🔄 Sistema Escuela Enfermería - Modo Migración")
#    st.subheader("Instituto Nacional de Cardiología - Escuela de Enfermería")
    
    # Barra superior
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        st.write(f"**Administrador:** {usuario_actual.get('nombre', usuario_actual.get('usuario', 'Usuario'))}")
        st.write(f"**Usuario:** {usuario_actual.get('usuario', '')}")
    
    with col2:
        if st.button("🔄 Recargar Datos"):
            cargar_datos_completos.clear()
            st.rerun()
    
    with col3:
        if st.button("🚪 Cerrar Sesión"):
            auth.cerrar_sesion()
            st.rerun()
    
    st.markdown("---")
    
    # =============================================================================
    # SELECCIÓN DE TIPO DE MIGRACIÓN - AHORA ES LO PRIMERO QUE SE MUESTRA
    # =============================================================================
    
    st.subheader("🎯 Seleccionar Tipo de Migración")
    
    tipo_migracion = st.radio(
        "Seleccione el tipo de migración a realizar:",
        [
            "📝 Inscrito → Estudiante",
            "🎓 Estudiante → Egresado", 
            "💼 Egresado → Contratado"
        ],
        horizontal=True
    )
    
    st.markdown("---")
    
    # Mostrar interfaz según el tipo de migración seleccionado
    if tipo_migracion == "📝 Inscrito → Estudiante":
        mostrar_migracion_inscritos()
    elif tipo_migracion == "🎓 Estudiante → Egresado":
        mostrar_migracion_estudiantes()
    elif tipo_migracion == "💼 Egresado → Contratado":
        mostrar_migracion_egresados()

def mostrar_migracion_inscritos():
    """Interfaz para migración de inscritos a estudiantes - CORREGIDA"""
    st.header("📝 Migración: Inscrito → Estudiante")
    
    if df_inscritos.empty:
        st.warning("📭 No hay inscritos disponibles para migrar")
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Inscritos Disponibles para Migración")
    st.info(f"Total de inscritos: {len(df_inscritos)}")
    
    # Crear una copia para mostrar
    df_mostrar = df_inscritos.copy()
    
    # Seleccionar inscrito
    st.subheader("🎯 Seleccionar Inscrito para Migrar")
    
    if not df_mostrar.empty:
        # Crear lista de opciones usando matrícula y nombre
        opciones_inscritos = []
        for idx, inscrito in df_mostrar.iterrows():
            matricula = inscrito.get('matricula', 'Sin matrícula')
            nombre = inscrito.get('nombre_completo', 'Sin nombre')
            email = inscrito.get('email', 'Sin email')
            
            info = f"{matricula} | {nombre} | {email}"
            opciones_inscritos.append((info, idx))
        
        seleccion = st.selectbox(
            "Seleccione el inscrito a migrar:",
            options=[op[0] for op in opciones_inscritos],
            key="select_inscrito_migracion"
        )
        
        if seleccion:
            # Obtener el índice del inscrito seleccionado
            idx_seleccionado = [op[1] for op in opciones_inscritos if op[0] == seleccion][0]
            inscrito_seleccionado = df_mostrar.iloc[idx_seleccionado]
            
            # Mostrar datos del inscrito seleccionado
            st.subheader("📋 Datos del Inscrito Seleccionado")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**👤 Información Personal:**")
                st.write(f"**Matrícula:** {inscrito_seleccionado.get('matricula', 'No disponible')}")
                st.write(f"**Nombre:** {inscrito_seleccionado.get('nombre_completo', 'No disponible')}")
                st.write(f"**Email:** {inscrito_seleccionado.get('email', 'No disponible')}")
                st.write(f"**Teléfono:** {inscrito_seleccionado.get('telefono', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa de Interés:** {inscrito_seleccionado.get('programa_interes', 'No disponible')}")
                st.write(f"**Fecha Registro:** {inscrito_seleccionado.get('fecha_registro', 'No disponible')}")
                st.write(f"**Estatus:** {inscrito_seleccionado.get('estatus', 'No disponible')}")
                st.write(f"**Documentos Subidos:** {inscrito_seleccionado.get('documentos_subidos', 'No disponible')}")
            
            # Mostrar documentos si existen
            if 'documentos_guardados' in inscrito_seleccionado and pd.notna(inscrito_seleccionado['documentos_guardados']):
                st.write("**📁 Documentos Guardados:**")
                documentos = str(inscrito_seleccionado['documentos_guardados']).split(',')
                for doc in documentos:
                    st.write(f"• {doc.strip()}")
            
            # Botón para proceder con la migración
            st.markdown("---")
            if st.button("🚀 Iniciar Migración a Estudiante", type="primary", key="iniciar_migracion"):
                # GUARDAR CORRECTAMENTE el inscrito seleccionado como diccionario
                st.session_state.inscrito_seleccionado = inscrito_seleccionado.to_dict()
                st.success("✅ Inscrito seleccionado. Complete el formulario de migración a continuación.")
                st.rerun()
            
            # Si ya se seleccionó un inscrito, mostrar formulario de migración
            if 'inscrito_seleccionado' in st.session_state and st.session_state.inscrito_seleccionado is not None:
                st.markdown("---")
                # Validar que los datos sean correctos antes de pasar a la migración
                inscrito_data = st.session_state.inscrito_seleccionado
                if isinstance(inscrito_data, dict) and 'matricula' in inscrito_data:
                    migrador.migrar_inscrito_a_estudiante(inscrito_data)
                else:
                    st.error("❌ Error: Datos del inscrito no válidos")
                    # Limpiar el estado corrupto
                    del st.session_state.inscrito_seleccionado
                    st.rerun()
    
    else:
        st.warning("No hay inscritos disponibles para mostrar")

def mostrar_migracion_estudiantes():
    """Interfaz para migración de estudiantes a egresados - NUEVA FUNCIÓN"""
    st.header("🎓 Migración: Estudiante → Egresado")
    
    if df_estudiantes.empty:
        st.warning("📭 No hay estudiantes disponibles para migrar")
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Estudiantes Disponibles para Migración")
    st.info(f"Total de estudiantes: {len(df_estudiantes)}")
    
    # Crear una copia para mostrar
    df_mostrar = df_estudiantes.copy()
    
    # Seleccionar estudiante
    st.subheader("🎯 Seleccionar Estudiante para Migrar")
    
    if not df_mostrar.empty:
        # Crear lista de opciones usando matrícula y nombre
        opciones_estudiantes = []
        for idx, estudiante in df_mostrar.iterrows():
            matricula = estudiante.get('matricula', 'Sin matrícula')
            nombre = estudiante.get('nombre_completo', 'Sin nombre')
            email = estudiante.get('email', 'Sin email')
            
            info = f"{matricula} | {nombre} | {email}"
            opciones_estudiantes.append((info, idx))
        
        seleccion = st.selectbox(
            "Seleccione el estudiante a migrar:",
            options=[op[0] for op in opciones_estudiantes],
            key="select_estudiante_migracion"
        )
        
        if seleccion:
            # Obtener el índice del estudiante seleccionado
            idx_seleccionado = [op[1] for op in opciones_estudiantes if op[0] == seleccion][0]
            estudiante_seleccionado = df_mostrar.iloc[idx_seleccionado]
            
            # Mostrar datos del estudiante seleccionado
            st.subheader("📋 Datos del Estudiante Seleccionado")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**👤 Información Personal:**")
                st.write(f"**Matrícula:** {estudiante_seleccionado.get('matricula', 'No disponible')}")
                st.write(f"**Nombre:** {estudiante_seleccionado.get('nombre_completo', 'No disponible')}")
                st.write(f"**Email:** {estudiante_seleccionado.get('email', 'No disponible')}")
                st.write(f"**Teléfono:** {estudiante_seleccionado.get('telefono', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa:** {estudiante_seleccionado.get('programa', 'No disponible')}")
                st.write(f"**Fecha Inscripción:** {estudiante_seleccionado.get('fecha_inscripcion', 'No disponible')}")
                st.write(f"**Estatus:** {estudiante_seleccionado.get('estatus', 'No disponible')}")
                st.write(f"**Documentos Subidos:** {estudiante_seleccionado.get('documentos_subidos', 'No disponible')}")
            
            # Mostrar documentos si existen
            if 'documentos_guardados' in estudiante_seleccionado and pd.notna(estudiante_seleccionado['documentos_guardados']):
                st.write("**📁 Documentos Guardados:**")
                documentos = str(estudiante_seleccionado['documentos_guardados']).split(',')
                for doc in documentos:
                    st.write(f"• {doc.strip()}")
            
            # Botón para proceder con la migración
            st.markdown("---")
            if st.button("🚀 Iniciar Migración a Egresado", type="primary", key="iniciar_migracion_egresado"):
                # GUARDAR CORRECTAMENTE el estudiante seleccionado como diccionario
                st.session_state.estudiante_seleccionado = estudiante_seleccionado.to_dict()
                st.success("✅ Estudiante seleccionado. Complete el formulario de migración a continuación.")
                st.rerun()
            
            # Si ya se seleccionó un estudiante, mostrar formulario de migración
            if 'estudiante_seleccionado' in st.session_state and st.session_state.estudiante_seleccionado is not None:
                st.markdown("---")
                # Validar que los datos sean correctos antes de pasar a la migración
                estudiante_data = st.session_state.estudiante_seleccionado
                if isinstance(estudiante_data, dict) and 'matricula' in estudiante_data:
                    migrador.migrar_estudiante_a_egresado(estudiante_data)
                else:
                    st.error("❌ Error: Datos del estudiante no válidos")
                    # Limpiar el estado corrupto
                    del st.session_state.estudiante_seleccionado
                    st.rerun()
    
    else:
        st.warning("No hay estudiantes disponibles para mostrar")

def mostrar_migracion_egresados():
    """Interfaz para migración de egresados a contratados - NUEVA FUNCIÓN"""
    st.header("💼 Migración: Egresado → Contratado")
    
    if df_egresados.empty:
        st.warning("📭 No hay egresados disponibles para migrar")
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Egresados Disponibles para Migración")
    st.info(f"Total de egresados: {len(df_egresados)}")
    
    # Crear una copia para mostrar
    df_mostrar = df_egresados.copy()
    
    # Seleccionar egresado
    st.subheader("🎯 Seleccionar Egresado para Migrar")
    
    if not df_mostrar.empty:
        # Crear lista de opciones usando matrícula y nombre
        opciones_egresados = []
        for idx, egresado in df_mostrar.iterrows():
            matricula = egresado.get('matricula', 'Sin matrícula')
            nombre = egresado.get('nombre_completo', 'Sin nombre')
            email = egresado.get('email', 'Sin email')
            
            info = f"{matricula} | {nombre} | {email}"
            opciones_egresados.append((info, idx))
        
        seleccion = st.selectbox(
            "Seleccione el egresado a migrar:",
            options=[op[0] for op in opciones_egresados],
            key="select_egresado_migracion"
        )
        
        if seleccion:
            # Obtener el índice del egresado seleccionado
            idx_seleccionado = [op[1] for op in opciones_egresados if op[0] == seleccion][0]
            egresado_seleccionado = df_mostrar.iloc[idx_seleccionado]
            
            # Mostrar datos del egresado seleccionado
            st.subheader("📋 Datos del Egresado Seleccionado")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**👤 Información Personal:**")
                st.write(f"**Matrícula:** {egresado_seleccionado.get('matricula', 'No disponible')}")
                st.write(f"**Nombre:** {egresado_seleccionado.get('nombre_completo', 'No disponible')}")
                st.write(f"**Email:** {egresado_seleccionado.get('email', 'No disponible')}")
                st.write(f"**Teléfono:** {egresado_seleccionado.get('telefono', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa Original:** {egresado_seleccionado.get('programa_original', 'No disponible')}")
                st.write(f"**Fecha Graduación:** {egresado_seleccionado.get('fecha_graduacion', 'No disponible')}")
                st.write(f"**Nivel Académico:** {egresado_seleccionado.get('nivel_academico', 'No disponible')}")
                st.write(f"**Estado Laboral:** {egresado_seleccionado.get('estado_laboral', 'No disponible')}")
            
            # Mostrar documentos si existen
            if 'documentos_subidos' in egresado_seleccionado and pd.notna(egresado_seleccionado['documentos_subidos']):
                st.write("**📁 Documentos Subidos:**")
                st.write(f"{egresado_seleccionado.get('documentos_subidos', 'No disponible')}")
            
            # Botón para proceder con la migración
            st.markdown("---")
            if st.button("🚀 Iniciar Migración a Contratado", type="primary", key="iniciar_migracion_contratado"):
                # GUARDAR CORRECTAMENTE el egresado seleccionado como diccionario
                st.session_state.egresado_seleccionado = egresado_seleccionado.to_dict()
                st.success("✅ Egresado seleccionado. Complete el formulario de migración a continuación.")
                st.rerun()
            
            # Si ya se seleccionó un egresado, mostrar formulario de migración
            if 'egresado_seleccionado' in st.session_state and st.session_state.egresado_seleccionado is not None:
                st.markdown("---")
                # Validar que los datos sean correctos antes de pasar a la migración
                egresado_data = st.session_state.egresado_seleccionado
                if isinstance(egresado_data, dict) and 'matricula' in egresado_data:
                    migrador.migrar_egresado_a_contratado(egresado_data)
                else:
                    st.error("❌ Error: Datos del egresado no válidos")
                    # Limpiar el estado corrupto
                    del st.session_state.egresado_seleccionado
                    st.rerun()
    
    else:
        st.warning("No hay egresados disponibles para mostrar")

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

def main():
    # Inicializar estado de sesión
    if 'login_exitoso' not in st.session_state:
        st.session_state.login_exitoso = False
    if 'usuario_actual' not in st.session_state:
        st.session_state.usuario_actual = None
    if 'mostrar_confirmacion' not in st.session_state:
        st.session_state.mostrar_confirmacion = False
    if 'datos_formulario' not in st.session_state:
        st.session_state.datos_formulario = {}
    if 'inscrito_seleccionado' not in st.session_state:
        st.session_state.inscrito_seleccionado = None
    if 'estudiante_seleccionado' not in st.session_state:
        st.session_state.estudiante_seleccionado = None
    if 'egresado_seleccionado' not in st.session_state:
        st.session_state.egresado_seleccionado = None
    if 'mostrar_confirmacion_egresado' not in st.session_state:
        st.session_state.mostrar_confirmacion_egresado = False
    if 'datos_formulario_egresado' not in st.session_state:
        st.session_state.datos_formulario_egresado = {}
    if 'mostrar_confirmacion_contratado' not in st.session_state:
        st.session_state.mostrar_confirmacion_contratado = False
    if 'datos_formulario_contratado' not in st.session_state:
        st.session_state.datos_formulario_contratado = {}
    
    # Mostrar interfaz según estado de autenticación
    if not st.session_state.login_exitoso:
        mostrar_login()
    else:
        mostrar_interfaz_migrador()

if __name__ == "__main__":
    main()
