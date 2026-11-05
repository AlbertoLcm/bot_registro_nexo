"""Logs de consola y niveles de sangría para trazabilidad."""
import contextvars
from contextlib import contextmanager
from datetime import datetime

_LOG_INDENT = contextvars.ContextVar("log_indent", default=0)


@contextmanager
def _log_indent(levels: int = 1):
    token = _LOG_INDENT.set(_LOG_INDENT.get() + levels)
    try:
        yield
    finally:
        _LOG_INDENT.reset(token)


def _log_prefix(extra_indent: int = 0) -> str:
    return "  " * max(_LOG_INDENT.get() + extra_indent, 0)


def _log_line(label: str, color: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    indent = _log_prefix()
    print(f"\033[90m[{ts}]\033[0m {indent}{color}{label}\033[0m {msg}")


def _section(title: str, subtitle: str = None) -> None:
    """Imprime un encabezado de sección resaltado y con color, con subtítulo opcional."""
    ts = datetime.now().strftime("%H:%M:%S")

    CYAN = "\033[96m"
    GRIS = "\033[90m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    RESET = "\033[0m"

    longitud_maxima = len(title)
    if subtitle and len(subtitle) > len(title):
        longitud_maxima = len(subtitle)

    linea = "━" * (longitud_maxima + 15)

    print(f"\n{GRIS}[{ts}]{RESET} {CYAN}{BOLD}✦ {title.upper()} {RESET}")

    if subtitle:
        print(f"             {GRIS}{ITALIC}{subtitle}{RESET}")

    print(f"{CYAN}{linea}{RESET}")


def _subsection(title: str, subtitle: str = None) -> None:
    ts = datetime.now().strftime("%H:%M:%S")

    CYAN = "\033[96m"
    GRIS = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    indent = _log_prefix()
    print(f"\033[90m[{ts}]\033[0m {indent}{CYAN}{BOLD}▸ {title}{RESET}")
    if subtitle:
        print(f"           {indent}{GRIS}{subtitle}{RESET}")


def _ok(msg: str) -> None:
    _log_line("[OK]   ", "\033[92m", msg)


def _info(msg: str) -> None:
    _log_line("[INFO] ", "\033[94m", msg)


def _warn(msg: str) -> None:
    _log_line("[WARN] ", "\033[93m", msg)


def _error(msg: str) -> None:
    _log_line("[ERROR]", "\033[91m", msg)
