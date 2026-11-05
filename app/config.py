"""URLs, rutas y parámetros de ejecución de la aplicación."""
from pathlib import Path
import sys

URL_SUGO_LOGIN = "https://acprod.intranet.com.mx/mbom_mx_ws/mbom_mx_web/PortalLogon"
URL_SUGO_MAIN = "https://acprod.intranet.com.mx/mbom_mx_ws/mbom_mx_web/mbom_mx_web_jsp/portal3.jsp"
URL_ALTA_OFICIO = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX002&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10010"
URL_ALTA_PERSONA = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX003&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10021"
URL_FINALIZAR_CAPTURA = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX005&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10180"
URL_SUGO = "https://acprod.intranet.com.mx/mbom_mx_ws/mbom_mx_web/mbom_mx_web_jsp/portal3.jsp"
URL_SUGO_ESTATUS = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX012&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10090"
URL_GOOGLE_DRIVE = "https://drive.google.com/drive/u/0/"
URL_LOGIN_GOOGLE = "https://accounts.google.com/"

ARGUMENTOS_CHROME = [
    "--ignore-certificate-errors",
    "--disable-blink-features=AutomationControlled",
    "--disable-gpu",
    "--no-sandbox",
    "--no-first-run",             
    "--no-default-browser-check", 
    "--disable-sync",             
    "--disable-popup-blocking",
    "--disable-signin-promo",
    "--disable-features=ChromeSigninInterceptBubble,DiceWebSigninIntercept"
]

# =========================================
# Rutas y Configuración de Archivos
# =========================================

IS_FROZEN = getattr(sys, 'frozen', False)  # Detecta si es ejecutable Exe o Desarrollo

if IS_FROZEN:
    ejecutable = Path(sys.executable).resolve()
    # Si está dentro de un paquete .app de macOS (.../NexoSUGO.app/Contents/MacOS/NexoSUGO)
    if sys.platform == "darwin" and ".app/Contents/MacOS" in str(ejecutable):
        BASE_DIR = ejecutable.parents[3]  # Sube hasta la carpeta donde está el .app
    else:
        BASE_DIR = ejecutable.parent
    INTERNAL_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    INTERNAL_DIR = BASE_DIR

DIST_DIR = BASE_DIR / "dist"
DIR_ARCHIVOS = BASE_DIR / "archivos"
INPUT_FILE = BASE_DIR / "Oficios.xlsx"
INPUT_JSON_FILE = BASE_DIR / "oficios.json"
ARCHIVO_CREDENCIALES = BASE_DIR / "usuario_sugo.json"
USER_DATA_DIR = DIST_DIR / "perfil_google_drive"
ASSETS_DIR = INTERNAL_DIR / "app" / "assets"
TEMP_FILE = DIST_DIR / "resultados_temp.csv"
FILE_EXITOS = DIST_DIR / "resultados_procesados.xlsx"

BATCH_GUARDADO = 10
PROGRESS_STATUS_COLUMN = "Validacion Informe"
PROGRESS_COLUMNS = [
    PROGRESS_STATUS_COLUMN,
    "folio_sugo",
    "fase_proceso",
    "mensaje",
    "fecha_actualizacion",
]
PROGRESS_ID_COLUMN = "id_progreso"
PROGRESS_KEY_COLUMNS = [PROGRESS_ID_COLUMN]
