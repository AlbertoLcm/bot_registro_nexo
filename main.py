"""Entrada para la GUI y la ejecución por línea de comandos.

Uso: python main.py [--cli] [--headless | --oculto]
"""
import asyncio
import sys

from app.config import INPUT_JSON_FILE
from app.workflows.orchestrator import ejecutar_rpa_async


def main() -> None:
    if "--cli" in sys.argv:
        modo_oculto = "--headless" in sys.argv or "--oculto" in sys.argv
        asyncio.run(ejecutar_rpa_async(INPUT_JSON_FILE, modo_oculto))
    else:
        # GUI es opcional para permitir usar el modo CLI sin instalar CustomTkinter.
        from app.ui.app import BBVARpaApp

        app = BBVARpaApp()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()


if __name__ == "__main__":
    main()

    
