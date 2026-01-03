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
import matplotlib.pyplot as plt
import seaborn as sns
from PIL import Image
import warnings
warnings.filterwarnings('ignore')

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería - Modo Supervisión",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# SISTEMA DE CARGA REMOTA VIA SSH - CORREGIDO CON VARIABLES DE SECRETS
# =============================================================================

class CargadorRemoto:
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.BASE_DIR_REMOTO = st.secrets.get("remote_dir")
        
    def conectar(self):
        """Establecer conexión SSH con el servidor remoto usando variables de secrets.toml"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
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
        """Cargar archivo CSV desde el servidor remoto - SIN DATOS DE EJEMPLO"""
        try:
            if not self.conectar():
                return pd.DataFrame()  # Devuelve DataFrame vacío si no puede conectar
            
            # Verificar si el archivo existe en el servidor remoto
            try:
                self.sftp.stat(ruta_remota)
            except FileNotFoundError:
                st.warning(f"📁 Archivo remoto no encontrado: {os.path.basename(ruta_remota)}")
                return pd.DataFrame()  # DataFrame vacío si no existe
            
            # Leer archivo remoto
            with self.sftp.file(ruta_remota, 'r') as archivo_remoto:
                # Intentar diferentes codificaciones
                try:
                    df = pd.read_csv(archivo_remoto, encoding='utf-8')
                except UnicodeDecodeError:
                    archivo_remoto.seek(0)
                    df = pd.read_csv(archivo_remoto, encoding='latin-1')
                
            st.success(f"✅ {os.path.basename(ruta_remota)} cargado desde servidor ({len(df)} registros)")
            return df
            
        except Exception as e:
            st.warning(f"⚠️ Error cargando {os.path.basename(ruta_remota)}: {str(e)}")
            return pd.DataFrame()  # Siempre devuelve DataFrame vacío en caso de error
        finally:
            self.desconectar()
    
    def cargar_todos_los_datos(self):
        """Cargar todos los archivos CSV del servidor remoto - SOLO CARGA REMOTA"""
        
        # RUTAS CORREGIDAS SEGÚN LA ESTRUCTURA DEL SERVIDOR - USANDO VARIABLES DE SECRETS
        rutas_remotas = {
            'inscritos': os.path.join(self.BASE_DIR_REMOTO, "datos", "inscritos.csv"),
            'estudiantes': os.path.join(self.BASE_DIR_REMOTO, "datos", "estudiantes.csv"),
            'egresados': os.path.join(self.BASE_DIR_REMOTO, "datos", "egresados.csv"),
            'contratados': os.path.join(self.BASE_DIR_REMOTO, "datos", "contratados.csv"),
            'actualizaciones_academicas': os.path.join(self.BASE_DIR_REMOTO, "datos", "actualizaciones_academicas.csv"),
            'certificaciones': os.path.join(self.BASE_DIR_REMOTO, "datos", "certificaciones.csv"),
            'programas_educativos': os.path.join(self.BASE_DIR_REMOTO, "datos", "programas_educativos.csv"),
            'costos_programas': os.path.join(self.BASE_DIR_REMOTO, "datos", "costos_programas.csv"),
            'usuarios': os.path.join(self.BASE_DIR_REMOTO, "config", "usuarios.csv"),
            'roles_permisos': os.path.join(self.BASE_DIR_REMOTO, "config", "roles_permisos.csv"),
            'bitacora': os.path.join(self.BASE_DIR_REMOTO, "datos", "bitacora.csv")
        }
        
        datos_cargados = {}
        
        with st.spinner("🌐 Conectando al servidor remoto..."):
            for nombre, ruta_remota in rutas_remotas.items():
                # SOLO CARGAR DESDE REMOTO, NO USAR DATOS DE EJEMPLO
                datos_cargados[nombre] = self.cargar_csv_remoto(ruta_remota)
        
        return datos_cargados

# Instanciar el cargador remoto
cargador_remoto = CargadorRemoto()

# =============================================================================
# CARGA DE TODOS LOS DATOS DESDE EL SERVIDOR REMOTO - SIN CACHE TEMPORAL
# =============================================================================

def cargar_datos_completos():
    """Cargar todos los datos desde el servidor remoto - SIN CACHE"""
    return cargador_remoto.cargar_todos_los_datos()

# Cargar todos los datos SIN cache para forzar carga remota
datos = cargar_datos_completos()

# Asignar a variables globales
df_inscritos = datos.get('inscritos', pd.DataFrame())
df_estudiantes = datos.get('estudiantes', pd.DataFrame())
df_egresados = datos.get('egresados', pd.DataFrame())
df_contratados = datos.get('contratados', pd.DataFrame())
df_actualizaciones = datos.get('actualizaciones_academicas', pd.DataFrame())
df_certificaciones = datos.get('certificaciones', pd.DataFrame())
df_programas = datos.get('programas_educativos', pd.DataFrame())
df_costos = datos.get('costos_programas', pd.DataFrame())
df_usuarios = datos.get('usuarios', pd.DataFrame())
df_roles = datos.get('roles_permisos', pd.DataFrame())
df_bitacora = datos.get('bitacora', pd.DataFrame())

# =============================================================================
# SISTEMA DE ENVÍO DE EMAILS - VERSIÓN MEJORADA CON COPIA A NOTIFICATION_EMAIL
# =============================================================================

class SistemaEmail:
    def __init__(self):
        self.config = self.obtener_configuracion_email()
        
    def obtener_configuracion_email(self):
        """Obtiene la configuración de email desde secrets.toml"""
        try:
            return {
                'smtp_server': st.secrets.get("smtp_server", "smtp.gmail.com"),
                'smtp_port': st.secrets.get("smtp_port", 587),
                'email_user': st.secrets.get("email_user", ""),
                'email_password': st.secrets.get("email_password", ""),
                'notification_email': st.secrets.get("notification_email", "")
            }
        except Exception as e:
            st.error(f"Error al cargar configuración de email: {e}")
            return {}
    
    def verificar_configuracion_email(self):
        """Verificar que la configuración de email esté completa"""
        try:
            config = self.obtener_configuracion_email()
            email_user = config.get('email_user', '')
            email_password = config.get('email_password', '')
            notification_email = config.get('notification_email', '')
            
            if not email_user:
                st.error("❌ No se encontró 'email_user' en los secrets")
                return False
                
            if not email_password:
                st.error("❌ No se encontró 'email_password' en los secrets")
                return False
                
            if not notification_email:
                st.error("❌ No se encontró 'notification_email' en los secrets")
                return False
                
            st.success("✅ Configuración de email encontrada en secrets")
            st.info(f"📧 Remitente: {email_user}")
            st.info(f"📧 Email de notificación: {notification_email}")
            return True
            
        except Exception as e:
            st.error(f"❌ Error verificando configuración: {e}")
            return False
    
    def test_conexion_smtp(self):
        """Probar conexión SMTP para diagnóstico"""
        try:
            config = self.obtener_configuracion_email()
            email_user = config.get('email_user', '')
            email_password = config.get('email_password', '')
            
            if not email_user or not email_password:
                return False, "Credenciales no configuradas"
                
            server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
            server.starttls()
            server.login(email_user, email_password)
            server.quit()
            
            return True, "✅ Conexión SMTP exitosa"
            
        except Exception as e:
            return False, f"❌ Error SMTP: {e}"
    
    def obtener_email_usuario(self, usuario):
        """Obtener email del usuario desde el archivo usuarios.csv"""
        try:
            if df_usuarios.empty:
                st.warning("⚠️ No hay datos de usuarios disponibles")
                return None
            
            if 'usuario' not in df_usuarios.columns or 'email' not in df_usuarios.columns:
                st.warning("⚠️ Las columnas 'usuario' o 'email' no existen en usuarios.csv")
                return None
            
            # Buscar usuario en el DataFrame
            usuario_data = df_usuarios[df_usuarios['usuario'].astype(str).str.strip() == str(usuario).strip()]
            
            if usuario_data.empty:
                st.warning(f"⚠️ Usuario '{usuario}' no encontrado en usuarios.csv")
                return None
            
            email = usuario_data.iloc[0]['email']
            
            if pd.isna(email) or str(email).strip() == '':
                st.warning(f"⚠️ Usuario '{usuario}' no tiene email registrado")
                return None
            
            return str(email).strip()
            
        except Exception as e:
            st.error(f"❌ Error obteniendo email del usuario: {e}")
            return None

    def enviar_notificacion_email(self, datos_inscripcion, documentos_guardados, es_completado=False):
        """Envía notificación por email cuando se completa una inscripción"""
        try:
            config = self.obtener_configuracion_email()
            
            if not config.get('email_user') or not config.get('email_password'):
                st.warning("⚠️ Configuración de email no disponible")
                return False
            
            # Obtener email del usuario destino desde usuarios.csv
            usuario_destino = datos_inscripcion.get('usuario', '')
            email_destino = self.obtener_email_usuario(usuario_destino)
            
            if not email_destino:
                st.warning(f"⚠️ No se pudo obtener email para el usuario: {usuario_destino}")
                # Usar el email del formulario como respaldo
                email_destino = datos_inscripcion.get('email', '')
                if not email_destino:
                    st.error("❌ No se pudo determinar el email destino")
                    return False
            
            # Configurar servidor SMTP
            server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
            server.starttls()
            server.login(config['email_user'], config['email_password'])
            
            # Crear mensaje
            msg = MIMEMultipart()
            msg['From'] = config['email_user']
            msg['To'] = email_destino
            msg['Cc'] = config['notification_email']  # AGREGAR COPIA AL EMAIL DE NOTIFICACIÓN
            msg['Subject'] = f"✅ Confirmación de Proceso - Instituto Nacional de Cardiología"
            
            # Determinar tipo de proceso
            if es_completado:
                tipo_proceso = "COMPLETADO"
                titulo = "✅ PROCESO COMPLETADO EXITOSAMENTE"
                mensaje_estado = "ha sido completado exitosamente"
            else:
                tipo_proceso = "PROGRESO GUARDADO"
                titulo = "💾 PROGRESO GUARDADO CORRECTAMENTE"
                mensaje_estado = "se ha guardado correctamente"
            
            # Cuerpo del email con formato HTML mejorado
            cuerpo_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <div style="text-align: center; background: linear-gradient(135deg, #003366 0%, #00509e 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h2 style="margin: 0; font-size: 24px;">Instituto Nacional de Cardiología </h2>
                        <h3 style="margin: 10px 0 0 0; font-size: 18px; font-weight: normal;">Escuela de Enfermería</h3>
                    </div>
                    
                    <div style="padding: 20px;">
                        <h3 style="color: #27ae60; margin-top: 0;">{titulo}</h3>
                        
                        <p>Estimado(a) <strong>{datos_inscripcion.get('nombre_completo', 'Usuario')}</strong>,</p>
                        
                        <p>Le informamos que su proceso {mensaje_estado} en nuestro sistema académico.</p>
                        
                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <p style="font-weight: bold; margin-bottom: 10px;">📋 Detalles del proceso:</p>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Usuario:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{usuario_destino}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Matrícula:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{datos_inscripcion.get('matricula', 'N/A')}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Tipo de proceso:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{tipo_proceso}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Fecha y hora:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{datetime.now().strftime('%d/%m/%Y %H:%M')}</td>
                                </tr>
                            </table>
                        </div>
                        
                        <div style="background-color: #e8f5e8; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <p style="font-weight: bold; margin-bottom: 10px;">📄 Documentos procesados:</p>
                            <p>Total de documentos: <strong>{len(documentos_guardados)}</strong></p>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                {''.join([f'<li>{doc.get("nombre_original", "Documento")}</li>' for doc in documentos_guardados])}
                            </ul>
                        </div>
                        
                        <p>El estado actual de su solicitud es: <strong style="color: #27ae60;">{tipo_proceso}</strong></p>
                        
                        <p>Si usted no realizó esta acción o tiene alguna duda, por favor contacte al administrador del sistema inmediatamente.</p>
                        
                        <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-radius: 5px;">
                            <p style="margin: 0; font-size: 12px; color: #856404;">
                                <strong>⚠️ Información importante:</strong><br>
                                • Este es un mensaje automático, por favor no responda a este email.<br>
                                • Sistema Académico - Instituto Nacional de Cardiología<br>
                                • Copia enviada a: {config['notification_email']}
                            </p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(cuerpo_html, 'html'))
            
            # Enviar email con timeout - INCLUYENDO EL EMAIL DE NOTIFICACIÓN EN LOS DESTINATARIOS
            destinatarios = [email_destino, config['notification_email']]
            
            server.sendmail(config['email_user'], destinatarios, msg.as_string())
            server.quit()
            
            st.success(f"✅ Email de confirmación enviado exitosamente a: {email_destino}")
            st.success(f"✅ Copia enviada a: {config['notification_email']}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            st.error("❌ Error de autenticación SMTP. Verifica:")
            st.error("1. Tu email y contraseña de aplicación")
            st.error("2. Que hayas habilitado la verificación en 2 pasos")
            st.error("3. Que hayas creado una contraseña de aplicación")
            return False
            
        except smtplib.SMTPConnectError:
            st.error("❌ Error de conexión SMTP. Verifica:")
            st.error("1. Tu conexión a internet")
            st.error("2. Que el puerto 587 no esté bloqueado")
            return False
            
        except Exception as e:
            st.error(f"❌ Error inesperado al enviar email: {e}")
            return False

    def enviar_email_confirmacion(self, usuario_destino, nombre_usuario, tipo_documento, nombre_archivo, tipo_accion="subida"):
        """Enviar email de confirmación al usuario con copia a notification_email"""
        # Crear estructura de datos compatible
        datos_inscripcion = {
            'usuario': usuario_destino,
            'nombre_completo': nombre_usuario,
            'matricula': 'Sistema',
            'email': self.obtener_email_usuario(usuario_destino) or ''
        }
        
        documentos_guardados = [{
            'nombre_original': f"{tipo_documento} - {nombre_archivo}",
            'tipo': tipo_documento
        }]
        
        es_completado = (tipo_accion == "completado")
        
        return self.enviar_notificacion_email(datos_inscripcion, documentos_guardados, es_completado)

# Instancia del sistema de email
sistema_email = SistemaEmail()

# =============================================================================
# SISTEMA DE AUTENTICACIÓN Y SEGURIDAD - VERSIÓN MEJORADA
# =============================================================================

class SistemaAutenticacion:
    def __init__(self):
        self.usuarios = df_usuarios
        self.sesion_activa = False
        self.usuario_actual = None
        
    def hash_password(self, password):
        """Hash simple para contraseñas"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de usuario - VERSIÓN CORREGIDA CON BÚSQUEDA FLEXIBLE"""
        try:
            if self.usuarios.empty:
                st.error("❌ No se pudieron cargar los usuarios del sistema")
                return False
            
            if 'usuario' not in self.usuarios.columns:
                st.error("❌ La columna 'usuario' no existe en la base de datos")
                return False
            
            # ✅ CORRECCIÓN: Búsqueda flexible que ignora mayúsculas/minúsculas y espacios
            usuario_input = str(usuario).strip().lower()
            
            # Buscar usuario (comparación flexible)
            usuario_df = self.usuarios[
                self.usuarios['usuario'].astype(str).str.strip().str.lower() == usuario_input
            ]
            
            if usuario_df.empty:
                # ✅ INTENTAR BÚSQUEDA PARCIAL si no se encuentra exacto
                usuario_df = self.usuarios[
                    self.usuarios['usuario'].astype(str).str.strip().str.lower().str.contains(usuario_input, na=False)
                ]
                
                if usuario_df.empty:
                    st.error(f"❌ Usuario '{usuario}' no encontrado")
                    usuarios_disponibles = list(self.usuarios['usuario'].astype(str).unique())
                    st.info(f"📋 Usuarios disponibles: {usuarios_disponibles}")
                    return False
                else:
                    st.warning(f"⚠️ Usuario '{usuario}' no encontrado exactamente, pero se encontró: {usuario_df.iloc[0]['usuario']}")
                    # Usar el usuario encontrado
                    usuario_encontrado = usuario_df.iloc[0]['usuario']
                    usuario_df = self.usuarios[
                        self.usuarios['usuario'].astype(str).str.strip() == str(usuario_encontrado).strip()
                    ]
            
            contraseña_almacenada = usuario_df.iloc[0].get('password', '')
            
            if contraseña_almacenada is not None:
                contraseña_almacenada = str(contraseña_almacenada).strip()
            
            # ✅ COMPARACIÓN CORREGIDA - Verificar contraseña directa o hash
            password_input = str(password).strip()
            
            if contraseña_almacenada == password_input or contraseña_almacenada == self.hash_password(password_input):
                usuario_real = usuario_df.iloc[0]['usuario']
                st.success(f"✅ ¡Bienvenido(a), {usuario_real}!")
                st.session_state.login_exitoso = True
                st.session_state.usuario_actual = usuario_df.iloc[0].to_dict()
                self.sesion_activa = True
                self.usuario_actual = usuario_df.iloc[0].to_dict()
                self.registrar_bitacora('LOGIN', f'Usuario {usuario_real} inició sesión')
                return True
            else:
                st.error("❌ Contraseña incorrecta")
                return False
                
        except Exception as e:
            st.error(f"❌ Error en verificar_login: {e}")
            # Mostrar más detalles para diagnóstico
            st.info(f"Usuario buscado: '{usuario}'")
            if not self.usuarios.empty:
                st.info(f"Primeros usuarios disponibles: {list(self.usuarios['usuario'].astype(str).head(10))}")
            return False
            
    def registrar_bitacora(self, accion, detalles):
        """Registrar actividad en bitácora"""
        nueva_entrada = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'usuario': self.usuario_actual['usuario'] if self.usuario_actual else 'Sistema',
            'accion': accion,
            'detalles': detalles,
            'ip': 'localhost'
        }
        
        global df_bitacora
        if df_bitacora.empty:
            df_bitacora = pd.DataFrame([nueva_entrada])
        else:
            df_bitacora = pd.concat([df_bitacora, pd.DataFrame([nueva_entrada])], ignore_index=True)
    
    def cerrar_sesion(self):
        if self.sesion_activa:
            self.registrar_bitacora('LOGOUT', f'Usuario {self.usuario_actual["usuario"]} cerró sesión')
        self.sesion_activa = False
        self.usuario_actual = None

# Instancia global del sistema de autenticación
auth = SistemaAutenticacion()

# =============================================================================
# SISTEMA DE GESTIÓN ACADÉMICA - MEJORADO PARA MOSTRAR DATOS PERSONALES
# =============================================================================

class SistemaAcademico:
    def __init__(self):
        self.inscritos = df_inscritos
        self.estudiantes = df_estudiantes
        self.egresados = df_egresados
        self.contratados = df_contratados
        self.programas = df_programas
        self.certificaciones = df_certificaciones
        self.costos = df_costos

    def obtener_datos_usuario_actual(self):
        """Obtener datos del usuario actual - VERSIÓN MEJORADA"""
        if not st.session_state.login_exitoso:
            return pd.DataFrame()
            
        usuario_actual = st.session_state.usuario_actual.get('usuario', '')
        rol_actual = st.session_state.usuario_actual.get('rol', '').lower()
        
        st.info(f"🔍 Buscando datos para usuario: {usuario_actual} (Rol: {rol_actual})")
        
        # Buscar en todos los datasets posibles
        datasets = []
        
        if rol_actual == 'inscrito' and not self.inscritos.empty:
            datasets.append(('inscritos', self.inscritos))
        elif rol_actual == 'estudiante' and not self.estudiantes.empty:
            datasets.append(('estudiantes', self.estudiantes))
        elif rol_actual == 'egresado' and not self.egresados.empty:
            datasets.append(('egresados', self.egresados))
        elif rol_actual == 'contratado' and not self.contratados.empty:
            datasets.append(('contratados', self.contratados))
        
        # Si no hay datasets específicos para el rol, buscar en todos
        if not datasets:
            datasets = [
                ('inscritos', self.inscritos),
                ('estudiantes', self.estudiantes), 
                ('egresados', self.egresados),
                ('contratados', self.contratados)
            ]
        
        for nombre_dataset, dataset in datasets:
            if dataset.empty:
                continue
                
            # Buscar por diferentes campos posibles
            campos_busqueda = ['matricula', 'usuario', 'email', 'nombre']
            
            for campo in campos_busqueda:
                if campo in dataset.columns:
                    # Buscar coincidencia exacta
                    resultado = dataset[dataset[campo].astype(str).str.strip() == str(usuario_actual).strip()]
                    
                    if not resultado.empty:
                        st.success(f"✅ Datos encontrados en {nombre_dataset} (campo: {campo})")
                        return resultado
            
            # Si no se encontró por coincidencia exacta, buscar por contenido
            for campo in campos_busqueda:
                if campo in dataset.columns:
                    # Buscar si el usuario está contenido en el campo
                    resultado = dataset[dataset[campo].astype(str).str.contains(str(usuario_actual), case=False, na=False)]
                    
                    if not resultado.empty:
                        st.success(f"✅ Datos encontrados en {nombre_dataset} (búsqueda parcial en: {campo})")
                        return resultado
        
        st.warning(f"⚠️ No se encontraron datos personales para el usuario {usuario_actual}")
        st.info("ℹ️ Esto puede ser porque:")
        st.info("• El usuario no tiene datos registrados en el sistema")
        st.info("• Los nombres de columnas en los archivos CSV no coinciden")
        st.info("• Los datos están en un archivo diferente")
        
        # Mostrar estructura de los datasets para diagnóstico
        with st.expander("🔍 Diagnóstico - Estructura de datos disponibles"):
            for nombre, dataset in [('inscritos', self.inscritos), 
                                  ('estudiantes', self.estudiantes),
                                  ('egresados', self.egresados),
                                  ('contratados', self.contratados)]:
                if not dataset.empty:
                    st.write(f"**{nombre}:** {len(dataset)} registros")
                    st.write(f"Columnas: {list(dataset.columns)}")
                    if len(dataset) > 0:
                        st.write("Primeras filas:")
                        st.dataframe(dataset.head(3))
        
        return pd.DataFrame()

    def obtener_certificaciones_usuario_actual(self):
        """Obtener certificaciones del usuario actual"""
        datos_usuario = self.obtener_datos_usuario_actual()
        
        if datos_usuario.empty or self.certificaciones.empty:
            return pd.DataFrame()
        
        # Obtener matrícula del usuario
        if 'matricula' in datos_usuario.columns and 'matricula' in self.certificaciones.columns:
            matricula = datos_usuario.iloc[0]['matricula']
            return self.certificaciones[self.certificaciones['matricula'] == matricula]
        
        return pd.DataFrame()

# Instancia del sistema académico
academico = SistemaAcademico()

# =============================================================================
# SISTEMA DE EDICIÓN Y GUARDADO REMOTO - CORREGIDO CON VARIABLES DE SECRETS
# =============================================================================

class EditorRemoto:
    def __init__(self):
        self.cargador = cargador_remoto
        self.BASE_DIR_REMOTO = cargador_remoto.BASE_DIR_REMOTO
    
    def obtener_ruta_archivo(self, tipo_datos):
        """Obtener ruta remota del archivo según el tipo de datos - USANDO VARIABLES DE SECRETS"""
        rutas = {
            'inscritos': os.path.join(self.BASE_DIR_REMOTO, "datos", "inscritos.csv"),
            'estudiantes': os.path.join(self.BASE_DIR_REMOTO, "datos", "estudiantes.csv"),
            'egresados': os.path.join(self.BASE_DIR_REMOTO, "datos", "egresados.csv"),
            'contratados': os.path.join(self.BASE_DIR_REMOTO, "datos", "contratados.csv"),
            'actualizaciones_academicas': os.path.join(self.BASE_DIR_REMOTO, "datos", "actualizaciones_academicas.csv"),
            'certificaciones': os.path.join(self.BASE_DIR_REMOTO, "datos", "certificaciones.csv"),
            'programas_educativos': os.path.join(self.BASE_DIR_REMOTO, "datos", "programas_educativos.csv"),
            'costos_programas': os.path.join(self.BASE_DIR_REMOTO, "datos", "costos_programas.csv"),
            'usuarios': os.path.join(self.BASE_DIR_REMOTO, "config", "usuarios.csv"),
            'roles_permisos': os.path.join(self.BASE_DIR_REMOTO, "config", "roles_permisos.csv"),
            'bitacora': os.path.join(self.BASE_DIR_REMOTO, "datos", "bitacora.csv")
        }
        return rutas.get(tipo_datos, "")
    
    def guardar_dataframe_remoto(self, df, ruta_remota):
        """Guardar DataFrame en el servidor remoto"""
        try:
            if self.cargador.conectar():
                # Guardar DataFrame en un buffer en memoria
                buffer = StringIO()
                df.to_csv(buffer, index=False, encoding='utf-8')
                buffer.seek(0)
                
                # Subir al servidor remoto
                with self.cargador.sftp.file(ruta_remota, 'w') as archivo_remoto:
                    archivo_remoto.write(buffer.getvalue())
                
                self.cargador.desconectar()
                return True
                
        except Exception as e:
            st.error(f"❌ Error guardando archivo remoto: {e}")
            return False

# Instancia del editor remoto
editor = EditorRemoto()

# =============================================================================
# SISTEMA DOCUMENTAL - MEJORADO Y CORREGIDO CON VARIABLES DE SECRETS
# =============================================================================

class SistemaDocumental:
    def __init__(self):
        self.inscritos = df_inscritos
        self.estudiantes = df_estudiantes
        self.egresados = df_egresados
        self.contratados = df_contratados
        self.BASE_DIR_REMOTO = cargador_remoto.BASE_DIR_REMOTO
        self.directorio_uploads = os.path.join(self.BASE_DIR_REMOTO, "uploads")

    def obtener_documentos_usuario_actual(self):
        """Obtener documentos del usuario actual desde el sistema de archivos"""
        if not st.session_state.login_exitoso:
            return []
            
        # Obtener datos del usuario actual
        datos_usuario = academico.obtener_datos_usuario_actual()
        
        if datos_usuario.empty:
            st.warning("No se pudieron obtener datos del usuario para buscar documentos")
            return []
        
        # Obtener matrícula del usuario
        campos_posibles = ['matricula', 'usuario', 'id']
        matricula = None
        
        for campo in campos_posibles:
            if campo in datos_usuario.columns:
                matricula = str(datos_usuario.iloc[0][campo])
                break
        
        if not matricula:
            st.warning("No se pudo identificar la matrícula del usuario")
            return []
        
        documentos = []
        
        try:
            # Buscar archivos del usuario en el directorio uploads
            if cargador_remoto.conectar():
                try:
                    # Listar archivos en el directorio uploads
                    archivos = cargador_remoto.sftp.listdir(self.directorio_uploads)
                    
                    # Filtrar archivos que pertenezcan a esta matrícula
                    for archivo in archivos:
                        if archivo.startswith(f"{matricula}_") or matricula in archivo:
                            documentos.append({
                                'nombre': archivo,
                                'ruta': os.path.join(self.directorio_uploads, archivo),
                                'tipo': self.obtener_tipo_documento(archivo),
                                'tamaño': self.obtener_tamaño_archivo(archivo)
                            })
                except FileNotFoundError:
                    st.warning(f"El directorio de uploads no existe: {self.directorio_uploads}")
                
                cargador_remoto.desconectar()
                
        except Exception as e:
            st.warning(f"⚠️ No se pudieron cargar documentos: {e}")
        
        return documentos

    def obtener_tipo_documento(self, nombre_archivo):
        """Determinar el tipo de documento basado en la extensión"""
        if nombre_archivo.lower().endswith('.pdf'):
            return "PDF"
        elif nombre_archivo.lower().endswith(('.jpg', '.jpeg', '.png')):
            return "Imagen"
        elif nombre_archivo.lower().endswith(('.doc', '.docx')):
            return "Documento Word"
        else:
            return "Archivo"

    def obtener_tamaño_archivo(self, nombre_archivo):
        """Obtener tamaño del archivo"""
        try:
            if cargador_remoto.conectar():
                ruta_completa = os.path.join(self.directorio_uploads, nombre_archivo)
                stats = cargador_remoto.sftp.stat(ruta_completa)
                cargador_remoto.desconectar()
                
                # Convertir bytes a KB o MB
                tamaño_bytes = stats.st_size
                if tamaño_bytes > 1024 * 1024:
                    return f"{tamaño_bytes / (1024 * 1024):.1f} MB"
                else:
                    return f"{tamaño_bytes / 1024:.1f} KB"
                    
        except:
            pass
        return "Desconocido"

    def descargar_documento(self, nombre_archivo):
        """Descargar documento desde el servidor remoto"""
        try:
            if cargador_remoto.conectar():
                ruta_remota = os.path.join(self.directorio_uploads, nombre_archivo)
                
                # Leer archivo del servidor
                with cargador_remoto.sftp.file(ruta_remota, 'rb') as archivo_remoto:
                    contenido = archivo_remoto.read()
                
                cargador_remoto.desconectar()
                
                # Determinar tipo MIME
                if nombre_archivo.lower().endswith('.pdf'):
                    mime_type = "application/pdf"
                elif nombre_archivo.lower().endswith(('.jpg', '.jpeg')):
                    mime_type = "image/jpeg"
                elif nombre_archivo.lower().endswith('.png'):
                    mime_type = "image/png"
                else:
                    mime_type = "application/octet-stream"
                
                # Crear botón de descarga
                st.download_button(
                    label=f"📥 Descargar {nombre_archivo}",
                    data=contenido,
                    file_name=nombre_archivo,
                    mime=mime_type,
                    key=f"doc_{nombre_archivo}"
                )
                return True
                
        except Exception as e:
            st.error(f"❌ Error al descargar {nombre_archivo}: {e}")
            return False

    def mostrar_documentos_usuario(self):
        """Mostrar documentos del usuario actual"""
        documentos_usuario = self.obtener_documentos_usuario_actual()
        
        if not documentos_usuario:
            st.info("📄 No hay documentos disponibles para descargar")
            return
        
        st.subheader("📂 Mis Documentos Disponibles")
        
        for documento in documentos_usuario:
            with st.expander(f"📋 {documento['nombre']}"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Tipo:** {documento['tipo']}")
                    st.write(f"**Tamaño:** {documento['tamaño']}")
                    st.write(f"**Ubicación:** {self.directorio_uploads}")
                
                with col2:
                    self.descargar_documento(documento['nombre'])

    def subir_documento(self, archivo, matricula, nombre_completo, tipo_documento):
        """Subir documento al servidor remoto y actualizar base de datos"""
        try:
            if cargador_remoto.conectar():
                # Generar nombre del archivo según el formato especificado
                timestamp = datetime.now().strftime("%y-%m-%d.%H.%M")
                nombre_archivo = f"{matricula}.{nombre_completo}.{tipo_documento}.{timestamp}.pdf"
                
                # Limpiar nombre del archivo (remover caracteres especiales)
                nombre_archivo = "".join(c for c in nombre_archivo if c.isalnum() or c in ('.', '-', '_')).replace(' ', '_')
                
                ruta_remota = os.path.join(self.directorio_uploads, nombre_archivo)
                
                # Subir archivo al servidor
                with cargador_remoto.sftp.file(ruta_remota, 'wb') as archivo_remoto:
                    archivo_remoto.write(archivo.getvalue())
                
                # ACTUALIZAR CAMPO documentos_subidos EN LA BASE DE DATOS CORRESPONDIENTE
                self.actualizar_documentos_subidos(matricula, nombre_archivo, tipo_documento)
                
                cargador_remoto.desconectar()
                
                # ENVIAR EMAIL DE CONFIRMACIÓN (con copia a notification_email)
                usuario_actual = st.session_state.usuario_actual.get('usuario', '')
                email_enviado = sistema_email.enviar_email_confirmacion(
                    usuario_actual,  # Usuario que subió el documento
                    nombre_completo, 
                    tipo_documento, 
                    nombre_archivo,
                    "subida"
                )
                
                if email_enviado:
                    st.success(f"✅ Documento '{tipo_documento}' subido exitosamente y email enviado")
                else:
                    st.success(f"✅ Documento '{tipo_documento}' subido exitosamente")
                    st.warning("⚠️ El documento se subió pero no se pudo enviar el email de confirmación")
                
                st.info(f"📁 Guardado como: {nombre_archivo}")
                return True
                
        except Exception as e:
            st.error(f"❌ Error al subir documento: {e}")
            return False

    def actualizar_documentos_subidos(self, matricula, nombre_archivo, tipo_documento):
        """Actualizar campo documentos_subidos en la base de datos correspondiente"""
        try:
            # Determinar en qué DataFrame buscar según el rol del usuario
            rol_actual = st.session_state.usuario_actual.get('rol', '').lower()
            
            if rol_actual == 'inscrito' and not self.inscritos.empty:
                df_actualizar = self.inscritos
                ruta_archivo = editor.obtener_ruta_archivo('inscritos')
            elif rol_actual == 'estudiante' and not self.estudiantes.empty:
                df_actualizar = self.estudiantes
                ruta_archivo = editor.obtener_ruta_archivo('estudiantes')
            elif rol_actual == 'egresado' and not self.egresados.empty:
                df_actualizar = self.egresados
                ruta_archivo = editor.obtener_ruta_archivo('egresados')
            elif rol_actual == 'contratado' and not self.contratados.empty:
                df_actualizar = self.contratados
                ruta_archivo = editor.obtener_ruta_archivo('contratados')
            else:
                return False
            
            # Buscar el registro del usuario - buscar por diferentes campos
            indice = None
            campos_busqueda = ['matricula', 'usuario', 'id']
            
            for campo in campos_busqueda:
                if campo in df_actualizar.columns:
                    coincidencias = df_actualizar[df_actualizar[campo].astype(str) == str(matricula)]
                    if not coincidencias.empty:
                        indice = coincidencias.index[0]
                        break
            
            if indice is None:
                st.warning(f"⚠️ No se encontró registro para matrícula/usuario {matricula}")
                return False
            
            # Crear o actualizar el campo documentos_subidos
            if 'documentos_subidos' not in df_actualizar.columns:
                df_actualizar['documentos_subidos'] = ''
            
            # Obtener documentos actuales
            documentos_actuales = df_actualizar.at[indice, 'documentos_subidos']
            if pd.isna(documentos_actuales) or documentos_actuales == '':
                documentos_actuales = f"{tipo_documento}:{nombre_archivo}"
            else:
                # CORRECCIÓN: Convertir a string si es necesario
                if not isinstance(documentos_actuales, str):
                    documentos_actuales = str(documentos_actuales)
                documentos_actuales += f";{tipo_documento}:{nombre_archivo}"
            
            # Actualizar el campo
            df_actualizar.at[indice, 'documentos_subidos'] = documentos_actuales
            
            # Guardar en el servidor remoto
            if editor.guardar_dataframe_remoto(df_actualizar, ruta_archivo):
                st.success("📝 Campo 'documentos_subidos' actualizado en la base de datos")
                return True
            else:
                st.error("❌ Error al actualizar la base de datos")
                return False
                
        except Exception as e:
            st.error(f"❌ Error al actualizar documentos subidos: {e}")
            return False

    def obtener_documentos_requeridos(self, rol):
        """Obtener lista de documentos requeridos según el rol"""
        documentos_requeridos = {
            'inscrito': [
                "CURP",
                "Acta de Nacimiento",
                "Comprobante de Estudios",
                "Fotografías Tamaño Infantil",
                "Comprobante de Domicilio"
            ],
            'estudiante': [
                "Certificado de Estudios",
                "Historial Académico",
                "Comprobante de Pagos",
                "Constancia de Servicio Social"
            ],
            'egresado': [
                "Título Profesional",
                "Cédula Profesional",
                "Certificado de Estudios Completos",
                "Constancia de Egreso"
            ],
            'contratado': [
                "Contrato Laboral",
                "CURP",
                "Comprobante de Estudios",
                "Identificación Oficial",
                "Comprobante de Domicilio"
            ]
        }
        return documentos_requeridos.get(rol.lower(), [])

# Instancia del sistema documental
documentos = SistemaDocumental()

# =============================================================================
# INTERFACES DE USUARIO POR ROL - MEJORADAS CON CAMPOS CORRECTOS
# =============================================================================

def mostrar_interfaz_inscrito():
    """Interfaz para usuarios con rol 'inscrito' - CAMPOS CORRECTOS"""
    st.title("🎓 Portal del Inscrito")
    
    # Obtener datos del usuario actual
    datos_usuario = academico.obtener_datos_usuario_actual()
    
    if datos_usuario.empty:
        st.error("❌ No se pudieron cargar tus datos. Contacta al administrador.")
        return
    
    usuario_actual = datos_usuario.iloc[0]
    
    # Mostrar información personal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("👤 Información Personal")
        
        # CAMPOS CORRECTOS PARA INSCRITOS
        campos_inscritos = ['matricula', 'nombre_completo', 'programa', 'email', 
                           'telefono', 'fecha_nacimiento', 'genero', 'fecha_inscripcion', 'estatus']
        
        for campo in campos_inscritos:
            if campo in usuario_actual and pd.notna(usuario_actual[campo]):
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {usuario_actual[campo]}")
    
    with col2:
        st.subheader("📊 Estado")
        st.success("✅ Inscrito")
        if 'estatus' in usuario_actual:
            st.write(f"**Estatus:** {usuario_actual['estatus']}")
    
    # SECCIÓN MEJORADA: Edición con campos correctos
    st.markdown("---")
    st.subheader("✏️ Actualizar Información Personal")
    
    with st.form("editar_datos_inscrito"):
        st.write("**Modifica tus datos personales:**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CAMPOS CORRECTOS PARA INSCRITOS
            nueva_matricula = st.text_input("Matrícula", 
                                          value=usuario_actual.get('matricula', ''))
            nuevo_nombre = st.text_input("Nombre completo", 
                                       value=usuario_actual.get('nombre_completo', ''))
            nuevo_programa = st.text_input("Programa", 
                                         value=usuario_actual.get('programa', ''))
            nuevo_email = st.text_input("Correo electrónico", 
                                      value=usuario_actual.get('email', ''))
        
        with col2:
            # CAMPOS CORRECTOS PARA INSCRITOS
            nuevo_telefono = st.text_input("Teléfono", 
                                         value=usuario_actual.get('telefono', ''))
            nueva_fecha_nacimiento = st.text_input("Fecha de nacimiento",
                                                 value=usuario_actual.get('fecha_nacimiento', ''))
            nuevo_genero = st.selectbox("Género", 
                                      ["Masculino", "Femenino", "Otro", "Prefiero no decir"],
                                      index=0)
            if 'genero' in usuario_actual:
                genero_actual = usuario_actual['genero']
                if genero_actual == 'Femenino':
                    nuevo_genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"], index=1)
                elif genero_actual == 'Otro':
                    nuevo_genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"], index=2)
                elif genero_actual == 'Prefiero no decir':
                    nuevo_genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"], index=3)
            
            nueva_fecha_inscripcion = st.text_input("Fecha de inscripción",
                                                  value=usuario_actual.get('fecha_inscripcion', ''))
            nuevo_estatus = st.selectbox("Estatus",
                                       ["Activo", "Inactivo", "En proceso"],
                                       index=0)
            if 'estatus' in usuario_actual:
                estatus_actual = usuario_actual['estatus']
                if estatus_actual == 'Inactivo':
                    nuevo_estatus = st.selectbox("Estatus", ["Activo", "Inactivo", "En proceso"], index=1)
                elif estatus_actual == 'En proceso':
                    nuevo_estatus = st.selectbox("Estatus", ["Activo", "Inactivo", "En proceso"], index=2)
        
        if st.form_submit_button("💾 Guardar Cambios"):
            cambios = False
            actualizaciones = {}
            
            # Verificar y aplicar cambios para campos de inscritos
            campos_verificar = [
                ('matricula', nueva_matricula),
                ('nombre_completo', nuevo_nombre),
                ('programa', nuevo_programa),
                ('email', nuevo_email),
                ('telefono', nuevo_telefono),
                ('fecha_nacimiento', nueva_fecha_nacimiento),
                ('genero', nuevo_genero),
                ('fecha_inscripcion', nueva_fecha_inscripcion),
                ('estatus', nuevo_estatus)
            ]
            
            for campo, nuevo_valor in campos_verificar:
                if nuevo_valor and nuevo_valor != usuario_actual.get(campo, ''):
                    actualizaciones[campo] = nuevo_valor
                    cambios = True
            
            if cambios:
                try:
                    # Actualizar el DataFrame local
                    for campo, valor in actualizaciones.items():
                        df_inscritos.loc[usuario_actual.name, campo] = valor
                    
                    # Guardar en el servidor remoto
                    if editor.guardar_dataframe_remoto(df_inscritos, editor.obtener_ruta_archivo('inscritos')):
                        st.success("✅ Cambios guardados exitosamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar los cambios en el servidor")
                except Exception as e:
                    st.error(f"❌ Error al actualizar datos: {e}")
            else:
                st.info("ℹ️ No se realizaron cambios")
    
    # Gestión de documentos
    st.markdown("---")
    st.subheader("📁 Gestión de Documentos")
    
    # Mostrar documentos requeridos
    documentos_requeridos = documentos.obtener_documentos_requeridos('inscrito')
    st.write("**Documentos requeridos:**")
    for i, doc in enumerate(documentos_requeridos, 1):
        st.write(f"{i}. {doc}")
    
    # Subir documentos
    st.subheader("📤 Subir Documentos")
    
    tipo_documento = st.selectbox(
        "Selecciona el tipo de documento:",
        documentos_requeridos,
        key="tipo_doc_inscrito"
    )
    
    archivo = st.file_uploader(
        "Selecciona el archivo:",
        type=['pdf', 'jpg', 'jpeg', 'png'],
        key="archivo_inscrito"
    )
    
    if archivo is not None and tipo_documento:
        if st.button("📤 Subir Documento", key="btn_subir_inscrito"):
            nombre_completo = usuario_actual.get('nombre_completo', 'Usuario')
            matricula = usuario_actual.get('matricula', '')
            
            if documentos.subir_documento(archivo, matricula, nombre_completo, tipo_documento):
                st.success("✅ Documento subido exitosamente")
                st.rerun()
    
    # Mostrar documentos existentes
    st.subheader("📂 Mis Documentos Subidos")
    documentos.mostrar_documentos_usuario()

def mostrar_interfaz_estudiante():
    """Interfaz para usuarios con rol 'estudiante' - CAMPOS CORRECTOS"""
    st.title("🎓 Portal del Estudiante")
    
    # Obtener datos del usuario actual
    datos_usuario = academico.obtener_datos_usuario_actual()
    
    if datos_usuario.empty:
        st.error("❌ No se pudieron cargar tus datos. Contacta al administrador.")
        return
    
    usuario_actual = datos_usuario.iloc[0]
    
    # Mostrar información académica
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("👤 Información Académica")
        
        # CAMPOS CORRECTOS PARA ESTUDIANTES
        campos_estudiantes = ['matricula', 'nombre_completo', 'programa', 'email', 
                             'telefono', 'fecha_nacimiento', 'genero', 'fecha_inscripcion', 'estatus']
        
        for campo in campos_estudiantes:
            if campo in usuario_actual and pd.notna(usuario_actual[campo]):
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {usuario_actual[campo]}")
    
    with col2:
        st.subheader("📊 Estado Académico")
        st.success("✅ Estudiante Activo")
        if 'estatus' in usuario_actual:
            st.write(f"**Estatus:** {usuario_actual['estatus']}")
    
    # SECCIÓN MEJORADA: Edición con campos correctos
    st.markdown("---")
    st.subheader("✏️ Actualizar Información Académica")
    
    with st.form("editar_datos_estudiante"):
        st.write("**Modifica tus datos académicos:**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CAMPOS CORRECTOS PARA ESTUDIANTES
            nueva_matricula = st.text_input("Matrícula", 
                                          value=usuario_actual.get('matricula', ''),
                                          key="matricula_estudiante")
            nuevo_nombre = st.text_input("Nombre completo", 
                                       value=usuario_actual.get('nombre_completo', ''),
                                       key="nombre_estudiante")
            nuevo_programa = st.text_input("Programa", 
                                         value=usuario_actual.get('programa', ''),
                                       key="programa_estudiante")
            nuevo_email = st.text_input("Correo electrónico", 
                                      value=usuario_actual.get('email', ''),
                                      key="email_estudiante")
        
        with col2:
            # CAMPOS CORRECTOS PARA ESTUDIANTES
            nuevo_telefono = st.text_input("Teléfono", 
                                         value=usuario_actual.get('telefono', ''),
                                         key="telefono_estudiante")
            nueva_fecha_nacimiento = st.text_input("Fecha de nacimiento",
                                                 value=usuario_actual.get('fecha_nacimiento', ''),
                                                 key="fecha_nacimiento_estudiante")
            nuevo_genero = st.selectbox("Género", 
                                      ["Masculino", "Femenino", "Otro", "Prefiero no decir"],
                                      index=0,
                                      key="genero_estudiante")
            if 'genero' in usuario_actual:
                genero_actual = usuario_actual['genero']
                if genero_actual == 'Femenino':
                    nuevo_genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"], index=1, key="genero_estudiante2")
                elif genero_actual == 'Otro':
                    nuevo_genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"], index=2, key="genero_estudiante3")
                elif genero_actual == 'Prefiero no decir':
                    nuevo_genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"], index=3, key="genero_estudiante4")
            
            nueva_fecha_inscripcion = st.text_input("Fecha de inscripción",
                                                  value=usuario_actual.get('fecha_inscripcion', ''),
                                                  key="fecha_inscripcion_estudiante")
            nuevo_estatus = st.selectbox("Estatus",
                                       ["Activo", "Inactivo", "Graduado"],
                                       index=0,
                                       key="estatus_estudiante")
            if 'estatus' in usuario_actual:
                estatus_actual = usuario_actual['estatus']
                if estatus_actual == 'Inactivo':
                    nuevo_estatus = st.selectbox("Estatus", ["Activo", "Inactivo", "Graduado"], index=1, key="estatus_estudiante2")
                elif estatus_actual == 'Graduado':
                    nuevo_estatus = st.selectbox("Estatus", ["Activo", "Inactivo", "Graduado"], index=2, key="estatus_estudiante3")
        
        if st.form_submit_button("💾 Guardar Cambios"):
            cambios = False
            actualizaciones = {}
            
            # Verificar y aplicar cambios para campos de estudiantes
            campos_verificar = [
                ('matricula', nueva_matricula),
                ('nombre_completo', nuevo_nombre),
                ('programa', nuevo_programa),
                ('email', nuevo_email),
                ('telefono', nuevo_telefono),
                ('fecha_nacimiento', nueva_fecha_nacimiento),
                ('genero', nuevo_genero),
                ('fecha_inscripcion', nueva_fecha_inscripcion),
                ('estatus', nuevo_estatus)
            ]
            
            for campo, nuevo_valor in campos_verificar:
                if nuevo_valor and nuevo_valor != usuario_actual.get(campo, ''):
                    actualizaciones[campo] = nuevo_valor
                    cambios = True
            
            if cambios:
                try:
                    # Actualizar el DataFrame local
                    for campo, valor in actualizaciones.items():
                        df_estudiantes.loc[usuario_actual.name, campo] = valor
                    
                    # Guardar en el servidor remoto
                    if editor.guardar_dataframe_remoto(df_estudiantes, editor.obtener_ruta_archivo('estudiantes')):
                        st.success("✅ Cambios guardados exitosamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar los cambios en el servidor")
                except Exception as e:
                    st.error(f"❌ Error al actualizar datos: {e}")
            else:
                st.info("ℹ️ No se realizaron cambios")
    
    # Gestión de documentos
    st.markdown("---")
    st.subheader("📁 Gestión de Documentos Estudiantiles")
    
    # Mostrar documentos requeridos
    documentos_requeridos = documentos.obtener_documentos_requeridos('estudiante')
    st.write("**Documentos requeridos:**")
    for i, doc in enumerate(documentos_requeridos, 1):
        st.write(f"{i}. {doc}")
    
    # Subir documentos
    st.subheader("📤 Subir Documentos")
    
    tipo_documento = st.selectbox(
        "Selecciona el tipo de documento:",
        documentos_requeridos,
        key="tipo_doc_estudiante"
    )
    
    archivo = st.file_uploader(
        "Selecciona el archivo:",
        type=['pdf', 'jpg', 'jpeg', 'png'],
        key="archivo_estudiante"
    )
    
    if archivo is not None and tipo_documento:
        if st.button("📤 Subir Documento", key="btn_subir_estudiante"):
            nombre_completo = usuario_actual.get('nombre_completo', 'Usuario')
            matricula = usuario_actual.get('matricula', '')
            
            if documentos.subir_documento(archivo, matricula, nombre_completo, tipo_documento):
                st.success("✅ Documento subido exitosamente")
                st.rerun()
    
    # Mostrar documentos existentes
    st.subheader("📂 Mis Documentos Académicos")
    documentos.mostrar_documentos_usuario()

def mostrar_interfaz_egresado():
    """Interfaz para usuarios con rol 'egresado' - CAMPOS CORRECTOS"""
    st.title("🎓 Portal del Egresado")
    
    # Obtener datos del usuario actual
    datos_usuario = academico.obtener_datos_usuario_actual()
    
    if datos_usuario.empty:
        st.error("❌ No se pudieron cargar tus datos. Contacta al administrador.")
        return
    
    usuario_actual = datos_usuario.iloc[0]
    
    # Mostrar información profesional
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("👤 Información Profesional")
        
        # CAMPOS CORRECTOS PARA EGRESADOS
        campos_egresados = ['matricula', 'nombre_completo', 'programa_original', 
                           'fecha_graduacion', 'nivel_academico', 'email', 'telefono', 
                           'estado_laboral', 'fecha_actualizacion']
        
        for campo in campos_egresados:
            if campo in usuario_actual and pd.notna(usuario_actual[campo]):
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {usuario_actual[campo]}")
    
    with col2:
        st.subheader("📊 Estado Profesional")
        st.success("✅ Egresado")
        if 'estado_laboral' in usuario_actual:
            st.write(f"**Estado Laboral:** {usuario_actual['estado_laboral']}")
    
    # SECCIÓN MEJORADA: Edición con campos correctos
    st.markdown("---")
    st.subheader("✏️ Actualizar Información Profesional")
    
    with st.form("editar_datos_egresado"):
        st.write("**Actualiza tu información profesional:**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CAMPOS CORRECTOS PARA EGRESADOS
            nueva_matricula = st.text_input("Matrícula",
                                          value=usuario_actual.get('matricula', ''),
                                          key="matricula_egresado")
            nuevo_nombre = st.text_input("Nombre completo",
                                       value=usuario_actual.get('nombre_completo', ''),
                                       key="nombre_egresado")
            nuevo_programa_original = st.text_input("Programa original",
                                                  value=usuario_actual.get('programa_original', ''),
                                                  key="programa_original_egresado")
            nueva_fecha_graduacion = st.text_input("Fecha de graduación",
                                                 value=usuario_actual.get('fecha_graduacion', ''),
                                                 key="fecha_graduacion_egresado")
            nuevo_nivel_academico = st.selectbox("Nivel académico",
                                               ["Licenciatura", "Maestría", "Doctorado", "Especialidad"],
                                               index=0,
                                               key="nivel_academico_egresado")
        
        with col2:
            # CAMPOS CORRECTOS PARA EGRESADOS
            nuevo_email = st.text_input("Correo electrónico",
                                      value=usuario_actual.get('email', ''),
                                      key="email_egresado")
            nuevo_telefono = st.text_input("Teléfono",
                                         value=usuario_actual.get('telefono', ''),
                                         key="telefono_egresado")
            nuevo_estado_laboral = st.selectbox("Estado laboral",
                                              ["Empleado", "Desempleado", "Estudiando", "Emprendedor"],
                                              index=0,
                                              key="estado_laboral_egresado")
            nueva_fecha_actualizacion = st.text_input("Fecha de actualización",
                                                    value=usuario_actual.get('fecha_actualizacion', ''),
                                                    key="fecha_actualizacion_egresado")
        
        if st.form_submit_button("💾 Guardar Cambios"):
            cambios = False
            actualizaciones = {}
            
            # Verificar y aplicar cambios para campos de egresados
            campos_verificar = [
                ('matricula', nueva_matricula),
                ('nombre_completo', nuevo_nombre),
                ('programa_original', nuevo_programa_original),
                ('fecha_graduacion', nueva_fecha_graduacion),
                ('nivel_academico', nuevo_nivel_academico),
                ('email', nuevo_email),
                ('telefono', nuevo_telefono),
                ('estado_laboral', nuevo_estado_laboral),
                ('fecha_actualizacion', nueva_fecha_actualizacion)
            ]
            
            for campo, nuevo_valor in campos_verificar:
                if nuevo_valor and nuevo_valor != usuario_actual.get(campo, ''):
                    actualizaciones[campo] = nuevo_valor
                    cambios = True
            
            if cambios:
                try:
                    # Actualizar el DataFrame local
                    for campo, valor in actualizaciones.items():
                        df_egresados.loc[usuario_actual.name, campo] = valor
                    
                    # Guardar en el servidor remoto
                    if editor.guardar_dataframe_remoto(df_egresados, editor.obtener_ruta_archivo('egresados')):
                        st.success("✅ Cambios guardados exitosamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar los cambios en el servidor")
                except Exception as e:
                    st.error(f"❌ Error al actualizar datos: {e}")
            else:
                st.info("ℹ️ No se realizaron cambios")
    
    # Gestión de documentos
    st.markdown("---")
    st.subheader("📁 Gestión de Documentos Profesionales")
    
    # Mostrar documentos requeridos
    documentos_requeridos = documentos.obtener_documentos_requeridos('egresado')
    st.write("**Documentos requeridos:**")
    for i, doc in enumerate(documentos_requeridos, 1):
        st.write(f"{i}. {doc}")
    
    # Subir documentos
    st.subheader("📤 Subir Documentos")
    
    tipo_documento = st.selectbox(
        "Selecciona el tipo de documento:",
        documentos_requeridos,
        key="tipo_doc_egresado"
    )
    
    archivo = st.file_uploader(
        "Selecciona el archivo:",
        type=['pdf', 'jpg', 'jpeg', 'png'],
        key="archivo_egresado"
    )
    
    if archivo is not None and tipo_documento:
        if st.button("📤 Subir Documento", key="btn_subir_egresado"):
            nombre_completo = usuario_actual.get('nombre_completo', 'Usuario')
            matricula = usuario_actual.get('matricula', '')
            
            if documentos.subir_documento(archivo, matricula, nombre_completo, tipo_documento):
                st.success("✅ Documento subido exitosamente")
                st.rerun()
    
    # Mostrar documentos existentes
    st.subheader("📂 Mis Documentos Profesionales")
    documentos.mostrar_documentos_usuario()


def mostrar_interfaz_contratado():
    """Interfaz para usuarios con rol 'contratado' - CAMPOS ACTUALIZADOS"""
    st.title("💼 Portal del Personal Contratado")

    # Obtener datos del usuario actual
    datos_usuario = academico.obtener_datos_usuario_actual()

    if datos_usuario.empty:
        st.error("❌ No se pudieron cargar tus datos. Contacta al administrador.")
        return

    usuario_actual = datos_usuario.iloc[0]

    # Mostrar información laboral
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("👤 Información Laboral")

        # CAMPOS ACTUALIZADOS PARA CONTRATADOS
        campos_contratados = ['matricula', 'fecha_contratacion', 'puesto', 'departamento',
                             'estatus', 'salario', 'tipo_contrato', 'fecha_inicio', 'fecha_fin']

        for campo in campos_contratados:
            if campo in usuario_actual and pd.notna(usuario_actual[campo]):
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {usuario_actual[campo]}")

    with col2:
        st.subheader("📊 Estado Laboral")
        st.success("✅ Contratado Activo")
        if 'estatus' in usuario_actual:
            st.write(f"**Estatus:** {usuario_actual['estatus']}")

    # SECCIÓN MEJORADA: Edición con campos actualizados
    st.markdown("---")
    st.subheader("✏️ Actualizar Información Laboral")

    with st.form("editar_datos_contratado"):
        st.write("**Actualiza tu información laboral:**")

        col1, col2 = st.columns(2)

        with col1:
            # CAMPOS ACTUALIZADOS PARA CONTRATADOS
            nueva_matricula = st.text_input("Matrícula",
                                          value=usuario_actual.get('matricula', ''),
                                          key="matricula_contratado")
            nueva_fecha_contratacion = st.text_input("Fecha de contratación",
                                                   value=usuario_actual.get('fecha_contratacion', ''),
                                                   key="fecha_contratacion_contratado")
            nuevo_puesto = st.text_input("Puesto",
                                       value=usuario_actual.get('puesto', ''),
                                       key="puesto_contratado")
            nuevo_departamento = st.text_input("Departamento",
                                             value=usuario_actual.get('departamento', ''),
                                             key="departamento_contratado")

            # Configurar estatus actual correctamente
            estatus_opciones = ["Activo", "Inactivo", "Suspendido"]
            estatus_default = 0
            if 'estatus' in usuario_actual:
                estatus_actual = usuario_actual['estatus']
                if estatus_actual == 'Inactivo':
                    estatus_default = 1
                elif estatus_actual == 'Suspendido':
                    estatus_default = 2
            nuevo_estatus = st.selectbox("Estatus",
                                       estatus_opciones,
                                       index=estatus_default,
                                       key="estatus_contratado")

        with col2:
            # CAMPOS ACTUALIZADOS PARA CONTRATADOS
            nuevo_salario = st.text_input("Salario",
                                        value=usuario_actual.get('salario', ''),
                                        key="salario_contratado")

            # Configurar tipo de contrato actual correctamente
            tipo_contrato_opciones = ["Tiempo completo", "Medio tiempo", "Temporal", "Prácticas"]
            tipo_contrato_default = 0
            if 'tipo_contrato' in usuario_actual:
                tipo_actual = usuario_actual['tipo_contrato']
                if tipo_actual == 'Medio tiempo':
                    tipo_contrato_default = 1
                elif tipo_actual == 'Temporal':
                    tipo_contrato_default = 2
                elif tipo_actual == 'Prácticas':
                    tipo_contrato_default = 3
            nuevo_tipo_contrato = st.selectbox("Tipo de contrato",
                                             tipo_contrato_opciones,
                                             index=tipo_contrato_default,
                                             key="tipo_contrato_contratado")

            nueva_fecha_inicio = st.text_input("Fecha de inicio",
                                             value=usuario_actual.get('fecha_inicio', ''),
                                             key="fecha_inicio_contratado")
            nueva_fecha_fin = st.text_input("Fecha de fin",
                                          value=usuario_actual.get('fecha_fin', ''),
                                          key="fecha_fin_contratado")

        if st.form_submit_button("💾 Guardar Cambios"):
            cambios = False
            actualizaciones = {}

            # Verificar y aplicar cambios para campos actualizados de contratados
            campos_verificar = [
                ('matricula', nueva_matricula),
                ('fecha_contratacion', nueva_fecha_contratacion),
                ('puesto', nuevo_puesto),
                ('departamento', nuevo_departamento),
                ('estatus', nuevo_estatus),
                ('salario', nuevo_salario),
                ('tipo_contrato', nuevo_tipo_contrato),
                ('fecha_inicio', nueva_fecha_inicio),
                ('fecha_fin', nueva_fecha_fin)
            ]

            for campo, nuevo_valor in campos_verificar:
                valor_actual = usuario_actual.get(campo, '')
                if str(nuevo_valor).strip() != str(valor_actual).strip():
                    actualizaciones[campo] = nuevo_valor
                    cambios = True

            if cambios:
                try:
                    # Actualizar el DataFrame local
                    for campo, valor in actualizaciones.items():
                        df_contratados.loc[usuario_actual.name, campo] = valor

                    # Guardar en el servidor remoto
                    if editor.guardar_dataframe_remoto(df_contratados, editor.obtener_ruta_archivo('contratados')):
                        st.success("✅ Cambios guardados exitosamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar los cambios en el servidor")
                except Exception as e:
                    st.error(f"❌ Error al actualizar datos: {e}")
            else:
                st.info("ℹ️ No se realizaron cambios")

    # Gestión de documentos
    st.markdown("---")
    st.subheader("📁 Gestión de Documentos Laborales")

    # Mostrar documentos requeridos
    documentos_requeridos = documentos.obtener_documentos_requeridos('contratado')
    st.write("**Documentos requeridos:**")
    for i, doc in enumerate(documentos_requeridos, 1):
        st.write(f"{i}. {doc}")

    # Subir documentos
    st.subheader("📤 Subir Documentos")

    tipo_documento = st.selectbox(
        "Selecciona el tipo de documento:",
        documentos_requeridos,
        key="tipo_doc_contratado"
    )

    archivo = st.file_uploader(
        "Selecciona el archivo:",
        type=['pdf', 'jpg', 'jpeg', 'png'],
        key="archivo_contratado"
    )

    if archivo is not None and tipo_documento:
        if st.button("📤 Subir Documento", key="btn_subir_contratado"):
            nombre_completo = usuario_actual.get('nombre', 'Usuario')
            matricula = usuario_actual.get('matricula', '')

            if documentos.subir_documento(archivo, matricula, nombre_completo, tipo_documento):
                st.success("✅ Documento subido exitosamente")
                st.rerun()

    # Mostrar documentos existentes
    st.subheader("📂 Mis Documentos Laborales")
    documentos.mostrar_documentos_usuario()

# =============================================================================
# INTERFAZ DE ADMINISTRADOR - COMPLETA Y CORREGIDA
# =============================================================================

def mostrar_interfaz_administrador():
    """Interfaz para usuarios con rol 'administrador'"""
    st.title("⚙️ Panel de Administración")
    
    # Verificar que el usuario actual es administrador
    if not st.session_state.login_exitoso or st.session_state.usuario_actual.get('rol') != 'administrador':
        st.error("❌ No tienes permisos de administrador")
        return
    
    # Menú de administración
    opcion = st.sidebar.selectbox(
        "Menú de Administración",
        [
            "📊 Dashboard General",
            "👥 Gestión de Usuarios", 
            "📁 Gestión de Documentos",
            "📧 Configuración de Email",
            "🔐 Roles y Permisos",
            "📈 Reportes y Estadísticas",
            "🔍 Verificación de Datos"
        ]
    )
    
    if opcion == "📊 Dashboard General":
        mostrar_dashboard_administrador()
    elif opcion == "👥 Gestión de Usuarios":
        mostrar_gestion_usuarios()
    elif opcion == "📁 Gestión de Documentos":
        mostrar_gestion_documentos()
    elif opcion == "📧 Configuración de Email":
        mostrar_configuracion_email()
    elif opcion == "🔐 Roles y Permisos":
        mostrar_roles_permisos()
    elif opcion == "📈 Reportes y Estadísticas":
        mostrar_reportes_estadisticas()
    elif opcion == "🔍 Verificación de Datos":
        verificar_vinculacion_usuarios()

def mostrar_dashboard_administrador():
    """Dashboard general para administradores"""
    st.subheader("📊 Dashboard General")
    
    # Métricas generales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_inscritos = len(df_inscritos) if not df_inscritos.empty else 0
        st.metric("Total Inscritos", total_inscritos)
    
    with col2:
        total_estudiantes = len(df_estudiantes) if not df_estudiantes.empty else 0
        st.metric("Total Estudiantes", total_estudiantes)
    
    with col3:
        total_egresados = len(df_egresados) if not df_egresados.empty else 0
        st.metric("Total Egresados", total_egresados)
    
    with col4:
        total_contratados = len(df_contratados) if not df_contratados.empty else 0
        st.metric("Total Contratados", total_contratados)
    
    # Información del sistema
    st.subheader("🔧 Estado del Sistema")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("**Conexión SSH:** ✅ Activa" if cargador_remoto.conectar() else "**Conexión SSH:** ❌ Inactiva")
        cargador_remoto.desconectar()
        
        # Verificar configuración de email
        estado_email, mensaje_email = sistema_email.test_conexion_smtp()
        st.info(f"**Sistema de Email:** {mensaje_email}")
    
    with col2:
        # Verificar archivos críticos
        archivos_criticos = {
            'usuarios.csv': not df_usuarios.empty,
            'inscritos.csv': not df_inscritos.empty,
            'estudiantes.csv': not df_estudiantes.empty
        }
        
        st.write("**Archivos del Sistema:**")
        for archivo, estado in archivos_criticos.items():
            estado_texto = "✅" if estado else "❌"
            st.write(f"{estado_texto} {archivo}")

def mostrar_gestion_usuarios():
    """Gestión de usuarios para administradores"""
    st.subheader("👥 Gestión de Usuarios")

    # Declarar que vamos a usar la variable global
    global df_usuarios

    if df_usuarios.empty:
        st.error("❌ No se pudo cargar la base de datos de usuarios")
        return

    # Mostrar tabla de usuarios
    st.dataframe(df_usuarios, width='stretch')

    # Opciones de gestión
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Agregar Usuario")
        with st.form("agregar_usuario"):
            nuevo_usuario = st.text_input("Usuario")
            nueva_contraseña = st.text_input("Contraseña", type="password")
            nuevo_rol = st.selectbox("Rol", ["inscrito", "estudiante", "egresado", "contratado", "administrador"])
            nuevo_email = st.text_input("Email")

            if st.form_submit_button("➕ Agregar Usuario"):
                # Validar que no exista el usuario
                if nuevo_usuario in df_usuarios['usuario'].values:
                    st.error("❌ El usuario ya existe")
                else:
                    nuevo_registro = {
                        'usuario': nuevo_usuario,
                        'password': auth.hash_password(nueva_contraseña),
                        'rol': nuevo_rol,
                        'email': nuevo_email,
                        'fecha_creacion': datetime.now().strftime('%Y-%m-%d'),
                        'estado': 'activo'
                    }

                    # Crear una copia para evitar problemas de referencia
                    df_temp = df_usuarios.copy()
                    df_temp = pd.concat([df_temp, pd.DataFrame([nuevo_registro])], ignore_index=True)

                    if editor.guardar_dataframe_remoto(df_temp, editor.obtener_ruta_archivo('usuarios')):
                        # Actualizar la variable global
                        df_usuarios = df_temp
                        st.success("✅ Usuario agregado exitosamente")
                        st.rerun()

    with col2:
        st.subheader("Eliminar Usuario")
        usuario_eliminar = st.selectbox("Seleccionar usuario a eliminar", df_usuarios['usuario'].values)

        if st.button("🗑️ Eliminar Usuario", type="secondary"):
            if usuario_eliminar == st.session_state.usuario_actual['usuario']:
                st.error("❌ No puedes eliminar tu propio usuario")
            else:
                # Crear una copia para evitar problemas de referencia
                df_temp = df_usuarios[df_usuarios['usuario'] != usuario_eliminar].copy()

                if editor.guardar_dataframe_remoto(df_temp, editor.obtener_ruta_archivo('usuarios')):
                    # Actualizar la variable global
                    df_usuarios = df_temp
                    st.success("✅ Usuario eliminado exitosamente")
                    st.rerun()

def mostrar_gestion_documentos():
    """Gestión de documentos para administradores - CORREGIDO"""
    st.subheader("📁 Gestión de Documentos")
    
    # Navegación por tipos de usuarios
    tipo_usuario = st.selectbox(
        "Seleccionar tipo de usuario",
        ["Inscritos", "Estudiantes", "Egresados", "Contratados"]
    )
    
    # Cargar datos según selección
    if tipo_usuario == "Inscritos":
        datos = df_inscritos
    elif tipo_usuario == "Estudiantes":
        datos = df_estudiantes
    elif tipo_usuario == "Egresados":
        datos = df_egresados
    else:  # Contratados
        datos = df_contratados
    
    if datos.empty:
        st.info(f"📝 No hay datos de {tipo_usuario.lower()} disponibles")
        return
    
    # Mostrar documentos subidos - CORRECCIÓN: Convertir a string antes de split
    if 'documentos_subidos' in datos.columns:
        st.subheader(f"Documentos de {tipo_usuario}")
        
        for _, usuario in datos.iterrows():
            documentos_subidos = usuario.get('documentos_subidos')
            
            # CORRECCIÓN: Verificar y convertir a string
            if pd.notna(documentos_subidos) and str(documentos_subidos).strip() != '':
                # Convertir a string si es necesario
                if not isinstance(documentos_subidos, str):
                    documentos_subidos = str(documentos_subidos)
                
                with st.expander(f"📂 {usuario.get('nombre', 'Usuario')} - {usuario.get('matricula', 'N/A')}"):
                    documentos_lista = documentos_subidos.split(';')
                    for doc in documentos_lista:
                        if ':' in doc:
                            try:
                                tipo, archivo = doc.split(':', 1)
                                st.write(f"**{tipo}:** {archivo}")
                                
                                # Botón para descargar
                                if st.button(f"📥 Descargar {tipo}", key=f"descargar_{archivo}"):
                                    if documentos.descargar_documento(archivo.strip()):
                                        st.success(f"✅ {archivo} descargado")
                            except ValueError:
                                st.warning(f"⚠️ Formato incorrecto: {doc}")
    else:
        st.info(f"📝 No hay documentos subidos para {tipo_usuario.lower()}")

def mostrar_configuracion_email():
    """Configuración del sistema de email"""
    st.subheader("📧 Configuración del Sistema de Email")
    
    # Verificar configuración actual
    st.write("### 🔍 Verificación de Configuración Actual")
    
    config_ok = sistema_email.verificar_configuracion_email()
    
    if config_ok:
        st.success("✅ Configuración de email encontrada en secrets.toml")
        
        # Mostrar configuración (ocultando información sensible)
        config = sistema_email.obtener_configuracion_email()
        email_user = config.get('email_user', '')
        notification_email = config.get('notification_email', '')
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Email remitente:** {email_user}")
        with col2:
            st.info(f"**Email de notificación:** {notification_email}")
        
        # Probar conexión SMTP
        st.write("### 🧪 Probar Conexión SMTP")
        if st.button("🔍 Probar Conexión"):
            with st.spinner("Probando conexión SMTP..."):
                exito, mensaje = sistema_email.test_conexion_smtp()
                if exito:
                    st.success(mensaje)
                else:
                    st.error(mensaje)
    
    else:
        st.error("❌ Configuración de email incompleta o incorrecta")
        
        st.write("### 📝 Instrucciones de Configuración")
        st.markdown("""
        1. **Crear un archivo `.streamlit/secrets.toml`** en tu directorio de proyecto
        2. **Agregar las siguientes configuraciones:**
        ```toml
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        email_user = "tu_email@gmail.com"
        email_password = "tu_contraseña_de_aplicacion"
        notification_email = "email_notificaciones@gmail.com"
        ```
        3. **Para Gmail, necesitas:**
           - Habilitar verificación en 2 pasos
           - Generar una contraseña de aplicación
           - Usar esa contraseña en `email_password`
        """)

def mostrar_roles_permisos():
    """Gestión de roles y permisos - CORREGIDO"""
    st.subheader("🔐 Gestión de Roles y Permisos")
    
    if df_roles.empty:
        st.info("📝 No hay configuración de roles disponible")
        return
    
    st.dataframe(df_roles, width='stretch')
    
    # Mostrar permisos por rol - CORRECCIÓN: Manejar JSON correctamente
    st.subheader("📋 Permisos por Rol")
    rol_seleccionado = st.selectbox("Seleccionar rol", df_roles['rol'].unique())
    
    permisos_rol = df_roles[df_roles['rol'] == rol_seleccionado]
    if not permisos_rol.empty:
        permisos_texto = permisos_rol.iloc[0].get('permisos', '')
        
        if permisos_texto and str(permisos_texto).strip() != '':
            try:
                # Intentar cargar como JSON
                if isinstance(permisos_texto, str):
                    permisos_dict = json.loads(permisos_texto)
                else:
                    permisos_dict = permisos_texto
                st.json(permisos_dict)
            except (json.JSONDecodeError, TypeError):
                # Si no es JSON válido, mostrar como texto
                st.text_area("Permisos (texto):", value=str(permisos_texto), height=200)
        else:
            st.info("⚠️ No hay permisos definidos para este rol")

def mostrar_reportes_estadisticas():
    """Reportes y estadísticas para administradores"""
    st.subheader("📈 Reportes y Estadísticas")
    
    # Estadísticas de usuarios por rol
    if not df_usuarios.empty and 'rol' in df_usuarios.columns:
        st.write("### 👥 Distribución de Usuarios por Rol")
        distribucion_roles = df_usuarios['rol'].value_counts()
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            fig, ax = plt.subplots()
            distribucion_roles.plot(kind='bar', ax=ax, color='skyblue')
            ax.set_title('Usuarios por Rol')
            ax.set_ylabel('Cantidad')
            plt.xticks(rotation=45)
            st.pyplot(fig)
        
        with col2:
            st.write("**Resumen:**")
            for rol, cantidad in distribucion_roles.items():
                st.write(f"- {rol}: {cantidad}")
    
    # Estadísticas de documentos - CORRECCIÓN: Convertir a string antes de split
    st.write("### 📊 Estadísticas de Documentos")
    
    total_documentos = 0
    
    if not df_inscritos.empty and 'documentos_subidos' in df_inscritos.columns:
        docs_inscritos = df_inscritos['documentos_subidos'].apply(
            lambda x: len(str(x).split(';')) if pd.notna(x) and str(x).strip() != '' else 0
        ).sum()
        total_documentos += docs_inscritos
        st.write(f"- **Inscritos:** {docs_inscritos} documentos")
    
    if not df_estudiantes.empty and 'documentos_subidos' in df_estudiantes.columns:
        docs_estudiantes = df_estudiantes['documentos_subidos'].apply(
            lambda x: len(str(x).split(';')) if pd.notna(x) and str(x).strip() != '' else 0
        ).sum()
        total_documentos += docs_estudiantes
        st.write(f"- **Estudiantes:** {docs_estudiantes} documentos")
    
    st.write(f"**Total de documentos en el sistema:** {total_documentos}")

def verificar_vinculacion_usuarios():
    """Verificar la vinculación entre usuarios y datos académicos"""
    st.subheader("🔍 Verificación de Vinculación de Usuarios")
    
    if df_usuarios.empty:
        st.error("❌ No hay datos de usuarios disponibles")
        return
    
    # Mostrar usuarios y su información vinculada
    st.write("### 👥 Usuarios del Sistema")
    
    for _, usuario in df_usuarios.iterrows():
        with st.expander(f"👤 {usuario['usuario']} - Rol: {usuario.get('rol', 'N/A')}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Información del usuario:**")
                st.write(f"- Email: {usuario.get('email', 'No disponible')}")
                st.write(f"- Rol: {usuario.get('rol', 'No disponible')}")
                st.write(f"- Estado: {usuario.get('estado', 'No disponible')}")
            
            with col2:
                st.write("**Datos vinculados:**")
                # Buscar en diferentes datasets según el rol
                rol = usuario.get('rol', '').lower()
                usuario_id = usuario['usuario']
                
                datos_vinculados = False
                
                if rol == 'inscrito' and not df_inscritos.empty:
                    for campo in ['matricula', 'usuario', 'id']:
                        if campo in df_inscritos.columns:
                            vinculado = df_inscritos[df_inscritos[campo].astype(str) == usuario_id]
                            if not vinculado.empty:
                                st.write(f"✅ Vinculado con inscritos (campo: {campo})")
                                st.write(f"- Matrícula: {vinculado.iloc[0].get('matricula', 'N/A')}")
                                st.write(f"- Nombre: {vinculado.iloc[0].get('nombre_completo', 'N/A')}")
                                datos_vinculados = True
                                break
                
                if rol == 'estudiante' and not df_estudiantes.empty:
                    for campo in ['matricula', 'usuario', 'id']:
                        if campo in df_estudiantes.columns:
                            vinculado = df_estudiantes[df_estudiantes[campo].astype(str) == usuario_id]
                            if not vinculado.empty:
                                st.write(f"✅ Vinculado con estudiantes (campo: {campo})")
                                st.write(f"- Matrícula: {vinculado.iloc[0].get('matricula', 'N/A')}")
                                st.write(f"- Programa: {vinculado.iloc[0].get('programa', 'N/A')}")
                                datos_vinculados = True
                                break
                
                if not datos_vinculados:
                    st.warning("⚠️ No se encontraron datos vinculados")

# =============================================================================
# SISTEMA DE LOGIN Y NAVEGACIÓN PRINCIPAL
# =============================================================================

def mostrar_diagnostico_email():
    """Mostrar diagnóstico del sistema de email"""
    st.subheader("🔧 Diagnóstico del Sistema de Email")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Verificación de Configuración:**")
        config_ok = sistema_email.verificar_configuracion_email()
        
        if config_ok:
            st.success("✅ Configuración encontrada")
        else:
            st.error("❌ Problema con la configuración")
    
    with col2:
        st.write("**Prueba de Conexión SMTP:**")
        if st.button("🧪 Probar Conexión SMTP"):
            with st.spinner("Probando conexión..."):
                conexion_ok, mensaje = sistema_email.test_conexion_smtp()
                if conexion_ok:
                    st.success(mensaje)
                else:
                    st.error(mensaje)
    
    st.write("**Configuración Requerida en secrets.toml:**")
    st.code("""
# Credenciales de email para Gmail
smtp_server = "smtp.gmail.com"
smtp_port = 587
email_user = "tu_email@gmail.com"
email_password = "tu_contraseña_de_aplicacion"
notification_email = "email_notificaciones@gmail.com"

# Nota: Para Gmail necesitas:
# 1. Habilitar verificación en 2 pasos
# 2. Generar una contraseña de aplicación
# 3. Usar esa contraseña aquí
    """)
    
    # Mostrar datos de usuarios disponibles
    if not df_usuarios.empty and 'email' in df_usuarios.columns:
        st.write("**📧 Emails de Usuarios Disponibles:**")
        usuarios_con_email = df_usuarios[df_usuarios['email'].notna() & (df_usuarios['email'] != '')]
        if not usuarios_con_email.empty:
            df_mostrar = usuarios_con_email[['usuario', 'email']].copy()
            df_mostrar.index = df_mostrar.index + 1
            st.dataframe(df_mostrar, width='stretch')
        else:
            st.warning("⚠️ No hay usuarios con email registrado")
    
    st.write("**Solución de Problemas Comunes:**")
    with st.expander("🔍 Ver soluciones para problemas comunes"):
        st.write("""
        **❌ Error de autenticación:**
        - Verifica que el email y contraseña sean correctos
        - Para Gmail: habilita verificación en 2 pasos y usa contraseña de aplicación
        - Ve a: Google Account → Security → 2-Step Verification → App passwords
        
        **❌ Error de conexión:**
        - Verifica tu conexión a internet
        - Asegúrate que el puerto 587 no esté bloqueado
        - Prueba con un servicio de email diferente
        
        **❌ Email no llega:**
        - Revisa la carpeta de spam
        - Verifica que la dirección de destino sea correcta
        - Prueba con una dirección de email diferente
        """)

def mostrar_login():
    """Interfaz de login - MEJORADA CON ESTADO DE CARGA REMOTA"""
    st.title("🔐 Sistema Escuela Enfermería - Modo Supervisión")
    st.markdown("---")

    # Estado de la carga remota
    with st.expander("🌐 Estado de la Carga Remota", expanded=True):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            asp = "✅" if not df_inscritos.empty else "❌"
            st.metric("Inscritos", f"{asp} {len(df_inscritos)}")
        with col2:
            est = "✅" if not df_estudiantes.empty else "❌"
            st.metric("Estudiantes", f"{est} {len(df_estudiantes)}")
        with col3:
            egr = "✅" if not df_egresados.empty else "❌"
            st.metric("Egresados", f"{egr} {len(df_egresados)}")
        with col4:
            con = "✅" if not df_contratados.empty else "❌"
            st.metric("Contratados", f"{con} {len(df_contratados)}")
        with col5:
            prog = "✅" if not df_programas.empty else "❌"
            st.metric("Programas", f"{prog} {len(df_programas)}")

        if st.button("🔄 Recargar Datos Remotos"):
            st.rerun()

    # Diagnóstico de email
    with st.expander("🔧 Diagnóstico del Sistema de Email", expanded=False):
        mostrar_diagnostico_email()

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("Iniciar Sesión")
            usuario = st.text_input("👤 Usuario")
            password = st.text_input("🔒 Contraseña", type="password")
            login_button = st.form_submit_button("🚀 Ingresar al Sistema")

            if login_button:
                if usuario and password:
                    with st.spinner("Verificando credenciales..."):
                        if auth.verificar_login(usuario, password):
                            st.success(f"✅ Bienvenido, {usuario}!")
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")

def main():
    """Función principal de la aplicación"""
    
    # Inicializar estado de sesión
    if 'login_exitoso' not in st.session_state:
        st.session_state.login_exitoso = False
    if 'usuario_actual' not in st.session_state:
        st.session_state.usuario_actual = None
    
    # Mostrar interfaz según estado de login
    if not st.session_state.login_exitoso:
        mostrar_login()
    else:
        # Barra superior con información del usuario
        usuario_actual = st.session_state.usuario_actual
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            st.title(f"🏥 Sistema Escuela Enfermería - Modo Supervisión")
        
        with col2:
            st.write(f"**👤 Usuario:** {usuario_actual['usuario']}")
            st.write(f"**🎭 Rol:** {usuario_actual['rol']}")
        
        with col3:
            if st.button("🚪 Cerrar Sesión"):
                auth.cerrar_sesion()
                st.session_state.login_exitoso = False
                st.session_state.usuario_actual = None
                st.rerun()
        
        st.markdown("---")
        
        # Mostrar interfaz según rol
        rol_actual = usuario_actual.get('rol', '').lower()
        
        if rol_actual == 'administrador':
            mostrar_interfaz_administrador()
        elif rol_actual == 'inscrito':
            mostrar_interfaz_inscrito()
        elif rol_actual == 'estudiante':
            mostrar_interfaz_estudiante()
        elif rol_actual == 'egresado':
            mostrar_interfaz_egresado()
        elif rol_actual == 'contratado':
            mostrar_interfaz_contratado()
        else:
            st.error(f"❌ Rol no reconocido: {rol_actual}")
            st.info("Roles disponibles: administrador, inscrito, estudiante, egresado, contratado")

if __name__ == "__main__":
    main()
