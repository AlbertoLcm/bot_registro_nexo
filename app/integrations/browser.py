"""Gestión de sesiones Chrome, SUGO y Google Drive."""
import asyncio
import re
from typing import Optional
from pathlib import Path
from playwright.async_api import BrowserContext, Page, Playwright
from app.config import (
    URL_SUGO_LOGIN, URL_SUGO, URL_GOOGLE_DRIVE, URL_LOGIN_GOOGLE,
    USER_DATA_DIR, ARGUMENTOS_CHROME,
)
from app.core.logging import _info, _ok, _error

async def load_page_sugo(context: BrowserContext, user: str, password: str) -> Optional[Page]:
    page_sugo = await context.new_page()

    try:
        _info("Validando sesión existente de SUGO.")
        async with context.expect_page(timeout=5_000) as page_info:
            await page_sugo.goto(URL_SUGO_LOGIN, timeout=60_000)

        popup = await page_info.value
        await popup.wait_for_load_state()
        await popup.close()

        await page_sugo.bring_to_front()
        await page_sugo.goto(URL_SUGO, timeout=60_000)
        await page_sugo.wait_for_load_state("domcontentloaded")
        _ok("Sesión existente de SUGO disponible.")

    except Exception:
        _info("No se detectó sesión activa. Iniciando sesión con credenciales.")
        await asyncio.sleep(2)
        await page_sugo.fill(".name", user)
        await page_sugo.fill(".pass", password)
        await asyncio.sleep(1)

        try:
            async with context.expect_page(timeout=60_000) as page_info:
                if await page_sugo.locator(
                    "//p[@onclick='validaCampos()']"
                ).is_visible():
                    await page_sugo.evaluate("validaCampos()")

            popup = await page_info.value
            await popup.wait_for_load_state()
            await popup.close()

            await page_sugo.bring_to_front()
            await page_sugo.goto(URL_SUGO, timeout=60_000)
            await page_sugo.wait_for_load_state("domcontentloaded")
            _ok("Login en SUGO completado.")

        except Exception:
            _error("No fue posible iniciar sesión en SUGO.")
            return None

    return page_sugo


async def load_page_drive(
    context: BrowserContext,
    p: Playwright,
    headless: bool,
    user_data_dir: Path = USER_DATA_DIR,
):
    page_drive = context.pages[0] if context.pages else await context.new_page()

    await page_drive.goto(URL_GOOGLE_DRIVE, timeout=30_000)
    await page_drive.wait_for_load_state(state="domcontentloaded")

    if (
        ("idp/profile" in page_drive.url)
        or ("accounts.google" in page_drive.url)
        or ("workspace.google" in page_drive.url)
    ):
        await context.close()

        # Se abre UN SOLO Chrome visible para que el usuario inicie sesión
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="chrome",
            args=ARGUMENTOS_CHROME,
        )
        page_login = context.pages[0] if context.pages else await context.new_page()

        await page_login.goto(URL_LOGIN_GOOGLE, timeout=30_000)
        await page_login.wait_for_load_state(state="domcontentloaded")

        await page_login.wait_for_url(re.compile(r"myaccount"), timeout=0)

        await context.close()

        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            channel="chrome",
            args=ARGUMENTOS_CHROME,
        )
        page_drive = context.pages[0] if context.pages else await context.new_page()

        await page_drive.goto(URL_GOOGLE_DRIVE, timeout=30_000)
        await page_drive.wait_for_load_state(state="domcontentloaded")

    if "home" not in page_drive.url and "drive/u/" not in page_drive.url and "drive/my-drive" not in page_drive.url:
        return context, None

    return context, page_drive
