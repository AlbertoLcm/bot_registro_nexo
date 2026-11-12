""" Notificador de finalización de procesos y errores. """
import platform
import subprocess
from plyer import notification

def notificar_fin_rpa(titulo, mensaje, exito=True, usar_voz_mac=True):
    sistema = platform.system()
    
    try:
        if sistema == "Windows":
            import winsound
            sonido = winsound.MB_ICONASTERISK if exito else winsound.MB_ICONHAND
            winsound.MessageBeep(sonido)
                
        elif sistema == "Darwin":
            sonido_mac = "Hero" if exito else "Sosumi"
            ruta_sonido = f"/System/Library/Sounds/{sonido_mac}.aiff"
            subprocess.run(["afplay", "-v", "2", ruta_sonido], check=False)

            if usar_voz_mac:
                frase = "El bot ha finalizado"
                subprocess.Popen(["say", frase])

    except Exception as e:
        print(f"Aviso: No se pudo reproducir el sonido: {e}")

    if sistema == "Windows":
        try:
            notification.notify(
                title=titulo,
                message=mensaje,
                app_name="Monitor RPA",
                timeout=10
            )
        except Exception as e:
            print(f"Error en notificación Windows: {e}")

    elif sistema == "Darwin":
        try:
            cmd = ["terminal-notifier", "-title", titulo, "-message", mensaje]
            subprocess.run(cmd, check=True)
        except Exception:
            script_mac = f'display notification "{mensaje}" with title "{titulo}"'
            subprocess.run(["osascript", "-e", script_mac], check=False)