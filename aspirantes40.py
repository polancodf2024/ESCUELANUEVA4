import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, date
import hashlib
import base64
import random
import string
from PIL import Image
import paramiko
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import warnings
warnings.filterwarnings('ignore')

# Configuración de página para website público
st.set_page_config(
    page_title="Sistema Escuela Enfermería - Modo Inscripción",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# SISTEMA DE CARGA REMOTA VIA SSH - COMPLETO
# =============================================================================

class CargadorRemoto:
    def __init__(self):
        self.ssh = None
        self.sftp = None
        
    def conectar(self):
        """Establecer conexión SSH con el servidor remoto usando variables de secrets.toml"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # CONEXIÓN CON VARIABLES DE SECRETS.TOML
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
    
    def crear_directorio_remoto(self, ruta):
        """Crear directorio remoto recursivamente si no existe"""
        try:
            self.sftp.stat(ruta)
            return True  # El directorio ya existe
        except FileNotFoundError:
            try:
                # Crear directorio recursivamente
                partes = ruta.strip('/').split('/')
                path_actual = ''
                for parte in partes:
                    if parte:
                        path_actual += '/' + parte
                        try:
                            self.sftp.stat(path_actual)
                        except FileNotFoundError:
                            self.sftp.mkdir(path_actual)
                return True
            except Exception as e:
                st.error(f"❌ Error creando directorio {ruta}: {e}")
                return False
    
    def cargar_csv_remoto(self, ruta_remota):
        """Cargar archivo CSV desde el servidor remoto"""
        try:
            if not self.conectar():
                return pd.DataFrame()
            
            # Verificar si el archivo existe en el servidor remoto
            try:
                self.sftp.stat(ruta_remota)
            except FileNotFoundError:
                # Si el archivo no existe, crear estructura vacía
                return pd.DataFrame()
            
            # Leer archivo remoto
            with self.sftp.file(ruta_remota, 'r') as archivo_remoto:
                # Intentar diferentes codificaciones
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
    
    def guardar_dataframe_remoto(self, dataframe, archivo_remoto):
        """Guardar DataFrame en el servidor remoto"""
        try:
            if not self.conectar():
                st.error("❌ No se pudo conectar al servidor remoto")
                return False
            
            # Crear directorio si no existe
            directorio = os.path.dirname(archivo_remoto)
            if not self.crear_directorio_remoto(directorio):
                return False
            
            # Convertir DataFrame a CSV en memoria
            csv_data = dataframe.to_csv(index=False, encoding='utf-8')
            
            # Subir al servidor remoto
            with self.sftp.file(archivo_remoto, 'w') as archivo_remoto_obj:
                archivo_remoto_obj.write(csv_data)
            
            self.desconectar()
            return True
            
        except Exception as e:
            st.error(f"❌ Error al guardar en remoto: {e}")
            return False
    
    def guardar_archivo_bytes_remoto(self, contenido_bytes, ruta_remota):
        """Guardar archivo físico en el servidor remoto - MÉTODO AÑADIDO"""
        try:
            if not self.conectar():
                st.error("❌ No se pudo conectar al servidor remoto")
                return False
            
            # Crear directorio si no existe
            directorio = os.path.dirname(ruta_remota)
            if not self.crear_directorio_remoto(directorio):
                return False
            
            # Guardar archivo
            with self.sftp.file(ruta_remota, 'wb') as archivo_remoto:
                archivo_remoto.write(contenido_bytes)
            
            self.desconectar()
            return True
            
        except Exception as e:
            st.error(f"❌ Error guardando archivo remoto {ruta_remota}: {e}")
            return False
    
    def listar_archivos_directorio(self, ruta_directorio):
        """Listar archivos en un directorio remoto"""
        try:
            if not self.conectar():
                return []
            
            archivos = self.sftp.listdir(ruta_directorio)
            self.desconectar()
            return archivos
            
        except Exception as e:
            st.warning(f"⚠️ Error listando archivos en {ruta_directorio}: {e}")
            return []

# =============================================================================
# SISTEMA DE ENVÍO DE CORREOS ELECTRÓNICOS - COMPLETO
# =============================================================================

class SistemaCorreos:
    def __init__(self):
        try:
            # Usar variables de secrets.toml
            self.smtp_server = st.secrets["smtp_server"]
            self.smtp_port = st.secrets["smtp_port"]
            self.smtp_username = st.secrets["email_user"]
            self.smtp_password = st.secrets["email_password"]
            self.email_from = st.secrets["email_user"]
            self.correos_habilitados = True
        except Exception as e:
            st.warning(f"⚠️ Configuración de correo no disponible: {e}")
            self.correos_habilitados = False
    
    def enviar_correo_confirmacion(self, destinatario, nombre_estudiante, matricula, folio, programa):
        """Enviar correo de confirmación de pre-inscripción"""
        if not self.correos_habilitados:
            st.warning("⚠️ Sistema de correos no configurado. No se enviará correo de confirmación.")
            return False
            
        try:
            # Crear mensaje
            mensaje = MIMEMultipart()
            mensaje['From'] = self.email_from
            mensaje['To'] = destinatario
            mensaje['Subject'] = f"Confirmación de Pre-Inscripción - {matricula}"
            
            # Cuerpo del correo
            cuerpo = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <div style="text-align: center; background-color: #2E86AB; color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h1>🏥 Escuela de Enfermería</h1>
                        <h2>Confirmación de Pre-Inscripción</h2>
                    </div>
                    
                    <div style="padding: 20px;">
                        <p>Estimado/a <strong>{nombre_estudiante}</strong>,</p>
                        
                        <p>Hemos recibido exitosamente tu solicitud de pre-inscripción. A continuación encontrarás los detalles de tu registro:</p>
                        
                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <h3 style="color: #2E86AB; margin-top: 0;">📋 Datos de tu Registro</h3>
                            <p><strong>Matrícula:</strong> {matricula}</p>
                            <p><strong>Folio:</strong> {folio}</p>
                            <p><strong>Programa:</strong> {programa}</p>
                            <p><strong>Fecha de registro:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                            <p><strong>Estatus:</strong> Pre-inscrito</p>
                        </div>
                        
                        <h3 style="color: #2E86AB;">📬 Próximos Pasos</h3>
                        <ol>
                            <li><strong>Revisión de documentos</strong> (2-3 días hábiles)</li>
                            <li><strong>Correo de confirmación</strong> con fecha de examen</li>
                            <li><strong>Examen de admisión</strong> (presencial/online)</li>
                            <li><strong>Entrevista personal</strong> (si aplica)</li>
                            <li><strong>Resultados finales</strong> (5-7 días después del examen)</li>
                        </ol>
                        
                        <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <h4 style="color: #A23B72; margin-top: 0;">ℹ️ Información Importante</h4>
                            <p>Guarda esta información, ya que tu matrícula y folio serán necesarios para cualquier consulta sobre tu proceso de admisión.</p>
                        </div>
                        
                        <p>Si tienes alguna pregunta, no dudes en contactarnos:</p>
                        <ul>
                            <li>📧 Email: admisiones@escuelaenfermeria.edu.mx</li>
                            <li>📞 Teléfono: (55) 1234-5678</li>
                            <li>🕒 Horario: Lunes a Viernes de 9:00 a 18:00 hrs</li>
                        </ul>
                        
                        <p>¡Te deseamos mucho éxito en tu proceso de admisión!</p>
                        
                        <p>Atentamente,<br>
                        <strong>Departamento de Admisiones</strong><br>
                        Escuela de Enfermería<br>
                        Formando Líderes en Salud Cardiovascular</p>
                    </div>
                    
                    <div style="text-align: center; background-color: #f1f1f1; padding: 15px; border-radius: 0 0 10px 10px; font-size: 12px; color: #666;">
                        <p>Este es un correo automático, por favor no respondas a este mensaje.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            mensaje.attach(MIMEText(cuerpo, 'html'))
            
            # Enviar correo
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(mensaje)
            
            return True
            
        except Exception as e:
            st.error(f"❌ Error al enviar correo de confirmación: {e}")
            return False

# =============================================================================
# SISTEMA DE GESTIÓN DE INSCRITOS CON CONEXIÓN REMOTA - COMPLETO
# =============================================================================

class SistemaInscritos:
    def __init__(self):
        # USAR VARIABLES DE SECRETS.TOML PARA RUTAS
        self.BASE_DIR_REMOTO = st.secrets["remote_dir"]
        
        # Archivos CSV usando rutas relativas desde el directorio base
        self.archivo_inscritos = os.path.join(self.BASE_DIR_REMOTO, "datos", "inscritos.csv")
        self.archivo_usuarios = os.path.join(self.BASE_DIR_REMOTO, "config", "usuarios.csv")
        
        # Carpeta para documentos PDF usando ruta relativa
        self.carpeta_documentos = os.path.join(self.BASE_DIR_REMOTO, "uploads")
        
        # Instancia del cargador remoto
        self.cargador_remoto = CargadorRemoto()
        
        # Instancia del sistema de correos
        self.sistema_correos = SistemaCorreos()
        
        # Cargar datos iniciales
        self.cargar_datos()
    
    def cargar_datos(self):
        """Cargar datos de inscritos desde el servidor remoto"""
        try:
            # Cargar inscritos
            self.df_inscritos = self.cargador_remoto.cargar_csv_remoto(self.archivo_inscritos)
            if self.df_inscritos.empty:
                self.df_inscritos = pd.DataFrame(columns=[
                    'matricula', 'fecha_registro', 'nombre_completo', 'email', 
                    'telefono', 'programa_interes', 'estatus', 'folio',
                    'documentos_subidos', 'fecha_nacimiento', 'como_se_entero', 'documentos_guardados'
                ])
            
            # Cargar usuarios
            self.df_usuarios = self.cargador_remoto.cargar_csv_remoto(self.archivo_usuarios)
            if self.df_usuarios.empty:
                self.df_usuarios = pd.DataFrame(columns=[
                    'usuario', 'password', 'rol', 'nombre', 'email', 
                    'activo', 'fecha_registro', 'estatus'
                ])
                
        except Exception as e:
            st.error(f"❌ Error cargando datos iniciales: {e}")
            # DataFrames vacíos como fallback
            self.df_inscritos = pd.DataFrame(columns=[
                'matricula', 'fecha_registro', 'nombre_completo', 'email', 
                'telefono', 'programa_interes', 'estatus', 'folio',
                'documentos_subidos', 'fecha_nacimiento', 'como_se_entero', 'documentos_guardados'
            ])
            self.df_usuarios = pd.DataFrame(columns=[
                'usuario', 'password', 'rol', 'nombre', 'email', 
                'activo', 'fecha_registro', 'estatus'
            ])
    
    def guardar_datos(self):
        """Guardar datos de inscritos en el servidor remoto"""
        try:
            # Crear directorios remotos si no existen
            if not self.crear_estructura_directorios():
                return False
            
            # Guardar inscritos
            if not self.cargador_remoto.guardar_dataframe_remoto(self.df_inscritos, self.archivo_inscritos):
                return False
            
            # Guardar usuarios
            if not self.cargador_remoto.guardar_dataframe_remoto(self.df_usuarios, self.archivo_usuarios):
                return False
            
            return True
            
        except Exception as e:
            st.error(f"❌ Error guardando datos de inscritos: {e}")
            return False
    
    def crear_estructura_directorios(self):
        """Crear estructura de directorios remota si no existe"""
        try:
            if not self.cargador_remoto.conectar():
                return False
            
            # Crear directorio base
            self.cargador_remoto.crear_directorio_remoto(self.BASE_DIR_REMOTO)
            
            # Crear subdirectorios necesarios
            directorios = [
                self.BASE_DIR_REMOTO,
                os.path.join(self.BASE_DIR_REMOTO, "datos"),
                os.path.join(self.BASE_DIR_REMOTO, "config"), 
                os.path.join(self.BASE_DIR_REMOTO, "uploads")
            ]
            
            for directorio in directorios:
                if not self.cargador_remoto.crear_directorio_remoto(directorio):
                    return False
            
            self.cargador_remoto.desconectar()
            return True
            
        except Exception as e:
            st.error(f"❌ Error creando estructura de directorios: {e}")
            return False
    
    def guardar_archivo_remoto(self, contenido_bytes, ruta_remota):
        """Guardar archivo físico en el servidor remoto"""
        try:
            return self.cargador_remoto.guardar_archivo_bytes_remoto(contenido_bytes, ruta_remota)
            
        except Exception as e:
            st.error(f"❌ Error en guardar_archivo_remoto: {e}")
            return False
    
    def generar_matricula_inscrito(self):
        """Generar matrícula única para inscrito"""
        try:
            while True:
                numero = ''.join(random.choices(string.digits, k=5))
                matricula = f"MAT-INS{numero}"
                
                # Verificar que no exista
                if self.df_inscritos.empty or matricula not in self.df_inscritos['matricula'].values:
                    return matricula
        except Exception as e:
            return f"MAT-INS{random.randint(10000, 99999)}"
    
    def registrar_inscrito(self, matricula, datos_inscrito, nombres_documentos):
        """Registrar nuevo inscrito en el sistema remoto"""
        try:
            # Crear registro del inscrito
            nuevo_inscrito = {
                'matricula': matricula,
                'fecha_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'nombre_completo': datos_inscrito['nombre_completo'],
                'email': datos_inscrito['email'],
                'telefono': datos_inscrito['telefono'],
                'programa_interes': datos_inscrito['programa_interes'],
                'estatus': 'Pre-inscrito',
                'folio': f"FOL-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}",
                'documentos_subidos': len(nombres_documentos),
                'documentos_guardados': ', '.join(nombres_documentos) if nombres_documentos else 'Ninguno'
            }
            
            # Agregar campos adicionales
            if 'fecha_nacimiento' in datos_inscrito and datos_inscrito['fecha_nacimiento']:
                nuevo_inscrito['fecha_nacimiento'] = str(datos_inscrito['fecha_nacimiento'])
            else:
                nuevo_inscrito['fecha_nacimiento'] = ''
            
            if 'como_se_entero' in datos_inscrito and datos_inscrito['como_se_entero']:
                nuevo_inscrito['como_se_entero'] = datos_inscrito['como_se_entero']
            else:
                nuevo_inscrito['como_se_entero'] = ''
            
            # Agregar al DataFrame de inscritos
            nuevo_df = pd.DataFrame([nuevo_inscrito])
            if self.df_inscritos.empty:
                self.df_inscritos = nuevo_df
            else:
                self.df_inscritos = pd.concat([self.df_inscritos, nuevo_df], ignore_index=True)
            
            # También crear registro en usuarios.csv
            nuevo_usuario = {
                'usuario': matricula,
                'password': '123',
                'rol': 'inscrito',
                'nombre': datos_inscrito['nombre_completo'],
                'email': datos_inscrito['email'],
                'activo': 'True',
                'fecha_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'estatus': 'activo'
            }
            
            nuevo_user_df = pd.DataFrame([nuevo_usuario])
            if self.df_usuarios.empty:
                self.df_usuarios = nuevo_user_df
            else:
                self.df_usuarios = pd.concat([self.df_usuarios, nuevo_user_df], ignore_index=True)
            
            # Guardar datos en servidor remoto
            if self.guardar_datos():
                # ENVIAR CORREO DE CONFIRMACIÓN
                correo_enviado = self.sistema_correos.enviar_correo_confirmacion(
                    destinatario=datos_inscrito['email'],
                    nombre_estudiante=datos_inscrito['nombre_completo'],
                    matricula=matricula,
                    folio=nuevo_inscrito['folio'],
                    programa=datos_inscrito['programa_interes']
                )
                
                if correo_enviado:
                    st.success("📧 ¡Correo de confirmación enviado exitosamente!")
                else:
                    st.warning("⚠️ Registro completado, pero no se pudo enviar el correo de confirmación.")
                
                return matricula, nuevo_inscrito['folio']
            else:
                return None, None
                
        except Exception as e:
            st.error(f"❌ Error al registrar inscrito: {e}")
            return None, None
    
    def guardar_documento(self, matricula, nombre_completo, tipo_documento, archivo_streamlit):
        """Guardar documento del inscrito en uploads/ - COMPLETO"""
        try:
            # Generar nombre de archivo estandarizado
            timestamp = datetime.now().strftime('%y%m%d%H%M%S')
            nombre_limpio = ''.join(c for c in nombre_completo if c.isalnum() or c in (' ', '-', '_')).rstrip()
            nombre_limpio = nombre_limpio.replace(' ', '_')[:30]
            tipo_limpio = tipo_documento.replace(' ', '_').upper()
            
            # Obtener extensión del archivo
            nombre_original = archivo_streamlit.name
            extension = nombre_original.split('.')[-1].lower() if '.' in nombre_original else 'pdf'
            
            # Nombre del archivo final
            nombre_archivo = f"{matricula}_{nombre_limpio}_{timestamp}_{tipo_limpio}.{extension}"
            
            # Ruta completa en servidor remoto
            ruta_completa = os.path.join(self.carpeta_documentos, nombre_archivo)
            
            # Obtener bytes del archivo Streamlit
            archivo_bytes = archivo_streamlit.getvalue()
            
            # Guardar archivo en servidor remoto
            if self.guardar_archivo_remoto(archivo_bytes, ruta_completa):
                return nombre_archivo
            else:
                return None
            
        except Exception as e:
            st.error(f"❌ Error al guardar documento {tipo_documento}: {e}")
            return None

# Instancia del sistema de inscritos
sistema_inscritos = SistemaInscritos()

# =============================================================================
# CONFIGURACIÓN Y ESTILOS DEL WEBSITE PÚBLICO - COMPLETO
# =============================================================================

def aplicar_estilos_publicos():
    """Aplicar estilos CSS para el website público"""
    st.markdown("""
    <style>
    .main-header {
        font-size: 3.5rem;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: bold;
    }
    .sub-header {
        font-size: 2rem;
        color: #A23B72;
        text-align: center;
        margin-bottom: 1.5rem;
        font-weight: 600;
    }
    .programa-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #2E86AB;
        margin-bottom: 1rem;
    }
    .testimonio {
        background-color: #e8f4f8;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #A23B72;
    }
    .btn-primary {
        background-color: #2E86AB;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
    }
    .stButton > button {
        width: 100%;
    }
    .stDownloadButton > button {
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# DATOS ESTÁTICOS DE LA INSTITUCIÓN (SOLO INFORMACIÓN PÚBLICA) - COMPLETO
# =============================================================================

def obtener_programas_academicos():
    """Obtener lista de programas académicos disponibles - SOLO INFORMACIÓN PÚBLICA"""
    return [
        {
            "nombre": "Especialidad en Enfermería Cardiovascular",
            "duracion": "2 años",
            "modalidad": "Presencial",
            "descripcion": "Formación especializada en el cuidado de pacientes con patologías cardiovasculares.",
            "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "2 años de experiencia"]
        },
        {
            "nombre": "Licenciatura en Enfermería",
            "duracion": "4 años",
            "modalidad": "Presencial",
            "descripcion": "Formación integral en enfermería con enfoque en cardiología.",
            "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0"]
        },
        {
            "nombre": "Diplomado de Cardiología Básica",
            "duracion": "6 meses",
            "modalidad": "Híbrida",
            "descripcion": "Actualización en fundamentos de cardiología para profesionales de la salud.",
            "requisitos": ["Título profesional en área de la salud"]
        },
        {
            "nombre": "Maestría en Ciencias Cardiológicas",
            "duracion": "2 años",
            "modalidad": "Presencial",
            "descripcion": "Formación de investigadores en el área de ciencias cardiológicas.",
            "requisitos": ["Licenciatura en áreas afines", "Promedio mínimo 8.5"]
        }
    ]

def obtener_testimonios():
    """Obtener testimonios de estudiantes y egresados - SOLO INFORMACIÓN PÚBLICA"""
    return [
        {
            "nombre": "Dra. Ana Martínez",
            "programa": "Especialidad en Enfermería Cardiovascular",
            "testimonio": "La especialidad me dio las herramientas para trabajar en la unidad de cardiología del hospital más importante del país.",
            "foto": "👩‍⚕️"
        },
        {
            "nombre": "Lic. Carlos Rodríguez",
            "programa": "Licenciatura en Enfermería",
            "testimonio": "La formación con enfoque cardiológico me diferenció en el mercado laboral. ¡Altamente recomendable!",
            "foto": "👨‍⚕️"
        },
        {
            "nombre": "Dr. Miguel Torres",
            "programa": "Diplomado de Cardiología Básica",
            "testimonio": "Perfecto para actualizarse sin dejar de trabajar. Los profesores son expertos en su área.",
            "foto": "🧑‍⚕️"
        }
    ]

# =============================================================================
# SECCIONES DEL WEBSITE PÚBLICO - COMPLETO
# =============================================================================

def mostrar_header():
    """Mostrar header del website"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="main-header">🏥 Escuela de Enfermería</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Formando Líderes en Salud Cardiovascular</div>', unsafe_allow_html=True)
    
    st.markdown("---")

def mostrar_hero():
    """Sección hero principal"""
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("## 🎓 Excelencia Académica en Cardiología")
        st.markdown("""
        ### **Forma parte de la institución líder en educación cardiovascular**
        
        - 👨‍⚕️ **Claustro docente** de alto nivel
        - 🏥 **Vinculación hospitalaria** con las mejores instituciones
        - 🔬 **Investigación** de vanguardia
        - 💼 **Bolsa de trabajo** exclusiva para egresados
        - 🌐 **Red de egresados** a nivel nacional
        
        *40 años formando profesionales de excelencia en el cuidado cardiovascular*
        """)
        
        if st.button("📝 ¡Inscríbete Ahora!", key="hero_inscripcion", use_container_width=True):
            st.session_state.mostrar_formulario = True
            st.rerun()
    
    with col2:
        st.info("**🏛️ Instalaciones de Vanguardia**")
        st.write("""
        - Laboratorios especializados
        - Simuladores de alta fidelidad
        - Biblioteca especializada
        - Aulas tecnológicas
        """)

def mostrar_programas_academicos():
    """Mostrar oferta académica"""
    st.markdown('<div class="sub-header">📚 Nuestra Oferta Académica</div>', unsafe_allow_html=True)
    
    programas = obtener_programas_academicos()
    
    for i, programa in enumerate(programas):
        with st.container():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f'<div class="programa-card">', unsafe_allow_html=True)
                st.markdown(f"### **{programa['nombre']}**")
                st.markdown(f"**Duración:** {programa['duracion']} | **Modalidad:** {programa['modalidad']}")
                st.markdown(f"{programa['descripcion']}")
                
                with st.expander("📋 Ver requisitos"):
                    for requisito in programa['requisitos']:
                        st.write(f"• {requisito}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.write("")  # Espacio
                if st.button(f"🎯 Solicitar Informes", key=f"info_{i}", use_container_width=True):
                    st.session_state.programa_seleccionado = programa['nombre']
                    st.session_state.mostrar_formulario = True
                    st.rerun()

def mostrar_testimonios():
    """Mostrar testimonios de estudiantes y egresados"""
    st.markdown("---")
    st.markdown('<div class="sub-header">🌟 Testimonios de Nuestra Comunidad</div>', unsafe_allow_html=True)
    
    testimonios = obtener_testimonios()
    cols = st.columns(3)
    
    for i, testimonio in enumerate(testimonios):
        with cols[i]:
            st.markdown(f'<div class="testimonio">', unsafe_allow_html=True)
            st.markdown(f"### {testimonio['foto']}")
            st.markdown(f"**{testimonio['nombre']}**")
            st.markdown(f"*{testimonio['programa']}*")
            st.markdown(f"\"{testimonio['testimonio']}\"")
            st.markdown('</div>', unsafe_allow_html=True)

def mostrar_formulario_inscripcion():
    """Mostrar formulario de pre-inscripción para inscritos - COMPLETO"""
    st.markdown("---")
    st.markdown('<div class="sub-header">📝 Formulario de Pre-Inscripción</div>', unsafe_allow_html=True)
    
    if 'formulario_enviado' not in st.session_state:
        st.session_state.formulario_enviado = False
    
    if not st.session_state.formulario_enviado:
        with st.form("formulario_inscripcion", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre_completo = st.text_input("👤 Nombre Completo *", placeholder="Ej: María González López")
                email = st.text_input("📧 Correo Electrónico *", placeholder="ejemplo@email.com")
                programa_interes = st.selectbox(
                    "🎯 Programa de Interés *",
                    [p['nombre'] for p in obtener_programas_academicos()]
                )
            
            with col2:
                telefono = st.text_input("📞 Teléfono *", placeholder="5512345678")
                
                # FECHA DE NACIMIENTO CON RANGO DESDE 1980
                fecha_actual = date.today()
                fecha_minima = date(1980, 1, 1)
                fecha_maxima = fecha_actual
                
                fecha_nacimiento = st.date_input(
                    "🎂 Fecha de Nacimiento",
                    min_value=fecha_minima,
                    max_value=fecha_maxima,
                    value=None,
                    format="YYYY-MM-DD"
                )
                
                # OPCIONES PARA "¿CÓMO SE ENTERÓ?"
                opciones_como_se_entero = ["Redes Sociales", "Google/Buscador", "Recomendación", "Evento", "Otro"]
                como_se_entero = st.selectbox(
                    "🔍 ¿Cómo se enteró de nosotros? *",
                    opciones_como_se_entero
                )
            
            # Documentos requeridos
            st.markdown("### 📎 Documentos Requeridos")
            st.info("Por favor, suba los siguientes documentos en formato PDF:")
            
            col_doc1, col_doc2 = st.columns(2)
            
            with col_doc1:
                acta_nacimiento = st.file_uploader("📄 Acta de Nacimiento", type=['pdf'], key="acta")
                curp = st.file_uploader("🆔 CURP", type=['pdf'], key="curp")
            
            with col_doc2:
                certificado = st.file_uploader("🎓 Último Grado de Estudios", type=['pdf'], key="certificado")
                foto = st.file_uploader("📷 Fotografía", type=['pdf', 'jpg', 'png'], key="foto")
            
            # Términos y condiciones
            acepta_terminos = st.checkbox("✅ Acepto los términos y condiciones del proceso de admisión *")
            
            enviado = st.form_submit_button("🚀 Enviar Solicitud de Admisión", use_container_width=True)
            
            if enviado:
                # Validar campos obligatorios
                if not all([nombre_completo, email, telefono, programa_interes, acepta_terminos]):
                    st.error("❌ Por favor completa todos los campos obligatorios (*)")
                    return
                
                # Validar que se seleccionó una opción en "¿Cómo se enteró?"
                if not como_se_entero:
                    st.error("❌ Por favor selecciona cómo te enteraste de nosotros")
                    return
                
                # Validar documentos requeridos
                documentos_requeridos = [acta_nacimiento, curp, certificado]
                nombres_docs = ["Acta de Nacimiento", "CURP", "Certificado de Estudios"]
                docs_faltantes = [nombres_docs[i] for i, doc in enumerate(documentos_requeridos) if doc is None]
                
                if docs_faltantes:
                    st.error(f"❌ Faltan los siguientes documentos: {', '.join(docs_faltantes)}")
                    return
                
                # Registrar inscrito
                with st.spinner("Procesando tu solicitud..."):
                    # PRIMERO: Generar la matrícula única UNA SOLA VEZ
                    matricula_unica = sistema_inscritos.generar_matricula_inscrito()
                    
                    datos_inscrito = {
                        'nombre_completo': nombre_completo,
                        'email': email,
                        'telefono': telefono,
                        'programa_interes': programa_interes,
                        'fecha_nacimiento': fecha_nacimiento,
                        'como_se_entero': como_se_entero
                    }
                    
                    # SEGUNDO: Guardar documentos con la MISMA matrícula
                    documentos_guardados = 0
                    nombres_documentos = []
                    
                    # Lista de documentos a procesar
                    documentos_a_procesar = [
                        (acta_nacimiento, "ACTA_NACIMIENTO"),
                        (curp, "CURP"), 
                        (certificado, "CERTIFICADO_ESTUDIOS"),
                        (foto, "FOTOGRAFIA") if foto else None
                    ]
                    
                    # Procesar cada documento
                    for doc_info in documentos_a_procesar:
                        if doc_info and doc_info[0] is not None:
                            try:
                                nombre_archivo = sistema_inscritos.guardar_documento(
                                    matricula_unica, 
                                    nombre_completo, 
                                    doc_info[1], 
                                    doc_info[0]
                                )
                                if nombre_archivo:
                                    documentos_guardados += 1
                                    nombres_documentos.append(nombre_archivo)
                                    st.success(f"✅ {doc_info[1]} guardado correctamente")
                                else:
                                    st.warning(f"⚠️ No se pudo guardar: {doc_info[1]}")
                            except Exception as e:
                                st.warning(f"⚠️ Error con {doc_info[1]}: {e}")
                    
                    # TERCERO: Registrar el inscrito con la MISMA matrícula y nombres de documentos
                    if documentos_guardados >= 3:  # Al menos los 3 documentos obligatorios
                        matricula_registrada, folio = sistema_inscritos.registrar_inscrito(
                            matricula_unica, 
                            datos_inscrito, 
                            nombres_documentos
                        )
                        
                        if matricula_registrada and folio:
                            st.session_state.formulario_enviado = True
                            st.session_state.datos_exitosos = {
                                'folio': folio,
                                'matricula': matricula_registrada,
                                'email': email,
                                'telefono': telefono,
                                'programa': programa_interes,
                                'documentos': documentos_guardados,
                                'nombre': nombre_completo
                            }
                            st.rerun()
                        else:
                            st.error("❌ Error al registrar el inscrito. Por favor intenta nuevamente.")
                    else:
                        st.error("❌ No se pudieron guardar los documentos obligatorios. Por favor intenta nuevamente.")
    
    else:
        # Mostrar resultados exitosos
        datos = st.session_state.datos_exitosos
        
        st.success("🎉 ¡Solicitud enviada exitosamente!")
        
        col_res1, col_res2 = st.columns(2)
        with col_res1:
            st.info(f"**📋 Folio de solicitud:** {datos['folio']}")
            st.info(f"**🎓 Matrícula de inscrito:** {datos['matricula']}")
            st.info(f"**📧 Email de contacto:** {datos['email']}")
        
        with col_res2:
            st.info(f"**📞 Teléfono registrado:** {datos['telefono']}")
            st.info(f"**🎯 Programa de interés:** {datos['programa']}")
            st.info(f"**📎 Documentos subidos:** {datos['documentos']}/4")
        
        st.markdown("---")
        st.markdown("### 📬 Próximos Pasos")
        st.markdown("""
        1. **Revisión de documentos** (2-3 días hábiles)
        2. **Correo de confirmación** con fecha de examen  
        3. **Examen de admisión** (presencial/online)
        4. **Entrevista personal** (si aplica)
        5. **Resultados finales** (5-7 días después del examen)
        
        *Te contactaremos al correo proporcionado para informarte los siguientes pasos.*
        """)
        
        st.info("📧 **Se ha enviado un correo de confirmación a tu dirección de email con todos los detalles de tu registro.**")
        
        # Mostrar información importante
        st.warning("""
        **⚠️ IMPORTANTE:** 
        - Guarda tu matrícula y folio para futuras consultas
        - Verifica tu bandeja de entrada y spam
        - Si no recibes el correo en 24 horas, contacta a admisiones@escuelaenfermeria.edu.mx
        """)
        
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("📝 Realizar otra pre-inscripción", use_container_width=True):
                st.session_state.formulario_enviado = False
                st.session_state.mostrar_formulario = False
                st.rerun()

def mostrar_contacto():
    """Mostrar información de contacto"""
    st.markdown("---")
    st.markdown('<div class="sub-header">📞 Información de Contacto</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏛️ Dirección")
        st.markdown("""
        Av. Insurgentes Sur 1234  
        Col. Nápoles  
        Ciudad de México, CDMX  
        C.P. 03810
        """)
    
    with col2:
        st.markdown("### 📱 Contacto")
        st.markdown("""
        **Teléfono:** (55) 1234-5678  
        **WhatsApp:** (55) 8765-4321  
        **Email:** admisiones@escuelaenfermeria.edu.mx
        """)
    
    with col3:
        st.markdown("### 🕒 Horarios")
        st.markdown("""
        **Atención a aspirantes:**  
        Lunes a Viernes: 9:00 - 18:00  
        Sábados: 9:00 - 13:00  
        **Proceso de admisión:**  
        Abierto todo el año
        """)

def mostrar_footer():
    """Mostrar footer del website"""
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("### 🏥 Instituto")
        st.markdown("""
        - Nuestra historia
        - Misión y visión
        - Directiva
        - Instalaciones
        """)
    
    with col2:
        st.markdown("### 📚 Programas")
        st.markdown("""
        - Licenciaturas
        - Especialidades
        - Maestrías
        - Diplomados
        """)
    
    with col3:
        st.markdown("### 📞 Contacto")
        st.markdown("""
        - Tel: 55-1234-5678
        - Email: admisiones@cardio.edu.mx
        - Dirección: Av. Instituto 123
        - Horario: 9:00 - 18:00 hrs
        """)
    
    with col4:
        st.markdown("### 🔗 Síguenos")
        st.markdown("""
        - Facebook
        - Twitter
        Instagram
        - LinkedIn
        """)
    
    st.markdown("---")
    st.markdown("<center>© 2024 Instituto Nacional de Cardiología. Todos los derechos reservados.</center>", unsafe_allow_html=True)

# =============================================================================
# APLICACIÓN PRINCIPAL - WEBSITE PÚBLICO - COMPLETO
# =============================================================================

def main():
    """Función principal del website público"""
    
    # Aplicar estilos
    aplicar_estilos_publicos()
    
    # Inicializar variables de sesión
    if 'mostrar_formulario' not in st.session_state:
        st.session_state.mostrar_formulario = False
    
    if 'formulario_enviado' not in st.session_state:
        st.session_state.formulario_enviado = False
    
    if 'programa_seleccionado' not in st.session_state:
        st.session_state.programa_seleccionado = None
    
    if 'datos_exitosos' not in st.session_state:
        st.session_state.datos_exitosos = None
    
    # Mostrar header
    mostrar_header()
    
    # Navegación
    if not st.session_state.mostrar_formulario:
        # Página principal
        mostrar_hero()
        mostrar_programas_academicos()
        mostrar_testimonios()
        mostrar_contacto()
    else:
        # Formulario de inscripción
        mostrar_formulario_inscripcion()
        mostrar_contacto()
    
    # Mostrar footer
    mostrar_footer()

# =============================================================================
# EJECUCIÓN DE LA APLICACIÓN
# =============================================================================

if __name__ == "__main__":
    main()
