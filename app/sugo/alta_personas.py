"""Alta de personas físicas, morales y cuentas vinculadas al oficio."""
import asyncio
from playwright.async_api import Page
from app.config import URL_ALTA_PERSONA
from app.core.logging import _error, _info, _log_indent, _ok, _subsection, _warn
from app.core.text import limpiar_texto, normalizar_texto
import re
import unicodedata

def limpiar_nombre(texto: str, estricto: bool = True) -> str:
    if not texto:
        return ""

    texto = str(texto).strip().upper()
    texto = re.sub(r"([^n\u0300-\u036f]|n(?!\u0303(?![\u0300-\u036f])))[\u0300-\u036f]+", r"\1", unicodedata.normalize("NFD", texto), 0, re.I)
    texto = unicodedata.normalize("NFC", texto)

    if estricto:
        texto = re.sub(r"[^A-Z0-9Ñ\s&]", "", texto)
    else:
        texto = re.sub(r"['\"`´’‘“”]", "", texto)

    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def limpiar_rfc(rfc: str) -> str:
    if not rfc:
        return ""
    
    return re.sub(r"[^A-Z0-9Ñ&]", "", str(rfc).upper())

async def registro_alta_persona(
    page: Page,
    *,
    folio_sugo: str,
    instrucciones_oficio: str,
    tipo_operacion: str,
    clientes_objetivo: list[dict]
):
    try:
        _subsection("Instrucciones y personas", f"Folio SUGO: {folio_sugo}")
        with _log_indent():
            _info("Abriendo formulario de alta de personas.")
            await page.goto(URL_ALTA_PERSONA, wait_until="domcontentloaded", timeout=60000)

            _info("Buscando oficio por folio SUGO.")
            checkbox = page.locator("#porFolio")
            await checkbox.wait_for(state="visible")
            await checkbox.click()
            await page.fill("#noFolio", folio_sugo)
            await page.evaluate("""() => buscar();""")

            await page.locator("#tablaResultados").wait_for(state="visible", timeout=4000)
            fila_folio = page.locator("#tablaResultados tr").filter(has_text=folio_sugo).first

            if await fila_folio.count() > 0:
                radio_btn = fila_folio.locator("input[type='radio']").first
                async with page.expect_navigation():
                    await radio_btn.check()
                _ok("Oficio localizado y seleccionado.")
            else:
                _error(f"El folio '{folio_sugo}' no se encontró en la tabla.")
                return {
                    "status": "error",
                    "message": f"El folio '{folio_sugo}' no se encontró en la tabla.",
                }

            _info("Capturando instrucciones del oficio.")
            await page.locator("#Observaciones").press_sequentially(instrucciones_oficio)
            await asyncio.sleep(1)
            await page.locator("#btnGuardar").wait_for(state="visible")
            await page.locator("#btnGuardar").click()
            _ok("Instrucciones guardadas.")

            if not clientes_objetivo:
                _info("Lista de clientes objetivo vacía. Agregando registro por defecto (No detectado).")
                clientes_objetivo = [{
                    "tipo_persona": "moral",
                    "nombre": "No detectado"
                }]

            _info(f"Clientes objetivo a procesar: {len(clientes_objetivo)}")
            
            algun_registro_insertado = False
            contador_clientes = 0

            for numero_cliente, cliente in enumerate(clientes_objetivo, start=1):
                tipo_persona   = str(cliente.get("tipo_persona") or "").strip().lower()
                
                nombre_cliente = limpiar_nombre(cliente.get("nombre"), estricto=True)
                rfc            = limpiar_rfc(cliente.get("rfc"))
                
                etiqueta_cliente = nombre_cliente or rfc or f"Cliente #{numero_cliente} (sin nombre)"

                cuentas_raw = cliente.get("cuentas_especificas") or []
                if isinstance(cuentas_raw, (str, int)):
                    cuentas_raw = [cuentas_raw]

                # re.sub(r"\D", "", ...) elimina cualquier cosa que no sea dígito (espacios, guiones, letras ocultas)
                # Si tus cuentas pueden ser alfanuméricas, usa re.sub(r"[^A-Za-z0-9]", "", str(cuenta))
                cuentas_especificas = [
                    re.sub(r"[^A-Za-z0-9]", "", str(cuenta))
                    for cuenta in cuentas_raw
                    if cuenta is not None and str(cuenta).strip() != ""
                ]

                _subsection(f"Cliente {numero_cliente}/{len(clientes_objetivo)}", etiqueta_cliente)

                
                with _log_indent():
                    # CONDICIONAL: Si existe un nombre, se procede con la inserción
                    if nombre_cliente:
                        # --- PASO 1: Captura del nombre ---
                        try:
                            if tipo_persona == "moral":
                                _info("Capturando persona moral.")
                                await asyncio.sleep(0.5)
                                await page.locator("#moralR").click()
                                await asyncio.sleep(0.5)
                                await page.locator("#razonS").fill("")
                                await page.locator("#razonS").press_sequentially(nombre_cliente)

                            elif tipo_persona == "fisica":
                                _info("Capturando persona física.")
                                await asyncio.sleep(0.5)
                                await page.locator("#fisicaR").click()

                                partes = nombre_cliente.strip().split()
                                cantidad = len(partes)

                                if cantidad == 4:
                                    nombre = f"{partes[0]} {partes[1]}"
                                    apellido_paterno = partes[2]
                                    apellido_materno = partes[3]
                                elif cantidad >= 3:
                                    apellido_materno = partes[-1]
                                    apellido_paterno = partes[-2]
                                    nombre = " ".join(partes[:-2])
                                elif cantidad == 2:
                                    nombre = partes[0]
                                    apellido_paterno = partes[1]
                                    apellido_materno = ""
                                else:
                                    nombre = partes[0] if partes else ""
                                    apellido_paterno = ""
                                    apellido_materno = ""

                                await asyncio.sleep(0.5)
                                await page.locator("#nombreC").fill("")
                                await page.locator("#nombreC").press_sequentially(nombre)
                                await asyncio.sleep(0.5)
                                await page.locator("#paternoC").fill("")
                                await page.locator("#paternoC").press_sequentially(apellido_paterno)
                                await asyncio.sleep(0.5)
                                await page.locator("#maternoC").fill("")
                                await page.locator("#maternoC").press_sequentially(apellido_materno)

                            else:
                                raise ValueError(f"Tipo de persona inválido: '{tipo_persona}'")

                            if rfc:
                                await asyncio.sleep(0.5)
                                await page.locator("#rfc").fill("")
                                await page.locator("#rfc").press_sequentially(rfc)

                            await asyncio.sleep(0.5)

                            async with page.expect_navigation(timeout=10000):
                                await page.evaluate("anadePer()")

                            _ok(f"Cliente agregado: {etiqueta_cliente}")
                            algun_registro_insertado = True
                            await asyncio.sleep(0.5)

                        except Exception as e:
                            _warn(f"Error al insertar manualmente a '{etiqueta_cliente}': {e}. Continuando flujo...")

                        # --- PASO 2: Capturar las cuentas especificas del cliente ingresado ---
                        if cuentas_especificas:

                            selector_clientes = f"#radio1{contador_clientes}"

                            await page.wait_for_selector(selector_clientes)
                            checkbox_cliente = page.locator(selector_clientes)
                            await checkbox_cliente.wait_for(state="visible")
                            await checkbox_cliente.click()
                            await asyncio.sleep(0.5)

                            await page.wait_for_selector("#btnAgregarC")
                            async with page.expect_navigation(timeout=10_000):
                                await page.evaluate("agregaCtas();")

                            count_cuenta = 1

                            for cuenta in cuentas_especificas:

                                _subsection(f"Cuenta {count_cuenta}/{len(cuentas_especificas)}")
                                
                                try:        
                                    await page.wait_for_selector("#noCuenta")
                                    await page.locator("#noCuenta").press_sequentially(cuenta)
                                    await asyncio.sleep(0.3)

                                    await page.locator("#instruccion").press_sequentially(f'Cuenta detectada para el cliente "{nombre_cliente}"')
                                    await asyncio.sleep(0.3)

                                    async with page.expect_navigation(timeout=10_000):
                                        await page.evaluate("validarRegistro();")

                                    _ok(f"Cuenta agregada: {cuenta}")
                                    await asyncio.sleep(0.3)
                                except Exception as e:
                                    _error(f"No pudo registrarse la cuenta: {cuenta}")
                                finally:
                                    count_cuenta += 1

                            await page.evaluate("regresar();")
                        


                    # --- CONDICIONAL: Si no existe un nombre, intentamos insertar directamente las cuentas especificas
                    else: 
                        if cuentas_especificas:
                            _info(f"Cuentas específicas a consultar: {len(cuentas_especificas)}")

                            metodos_busqueda = [
                                ("cuenta", "#radioCuenta", "#consultaC"),
                                ("tarjeta", "#radioTarjeta", "#consultaTar"),
                                ("contrato", "#radioContrato", "#consultaCon"),
                            ]

                            for cuenta_original in cuentas_especificas:
                                cuenta = str(cuenta_original or "").strip()
                                if not cuenta:
                                    continue

                                localizado = False

                                for nombre_metodo, selector_radio, selector_input in metodos_busqueda:
                                    _info(f"Consultando por {nombre_metodo}: {cuenta}")

                                    try:
                                        checkbox = page.locator(selector_radio)
                                        await checkbox.wait_for(state="visible")
                                        await checkbox.click()
                                        await asyncio.sleep(0.5)
                                        
                                        campo_input = page.locator(selector_input)
                                        await campo_input.fill("")
                                        await campo_input.press_sequentially(cuenta)

                                        # 1ra navegación: Búsqueda con noMenor()
                                        async with page.expect_navigation(timeout=10000):
                                            await page.evaluate("() => noMenor();")

                                        # Verificar si el sistema pobló los campos tras la búsqueda
                                        await page.wait_for_function(
                                            "() => document.getElementById('razonS')?.value.trim() !== '' || document.getElementById('nombreC')?.value.trim() !== ''",
                                            timeout=5000,
                                        )

                                        # 2da navegación: Agregar persona con anadePer()
                                        async with page.expect_navigation(timeout=10000):
                                            await page.evaluate("() => anadePer();")

                                        _ok(f"Registro agregado exitosamente como {nombre_metodo}: {cuenta}")
                                        localizado = True
                                        algun_registro_insertado = True
                                        break

                                    except Exception:
                                        texto_error_sistema = "No se detectó el mensaje de éxito (Timeout)"
                                        try:
                                            await page.wait_for_selector("#BTACEPTAR", timeout=5000)
                                            texto_error_sistema = await page.locator(".TextoAlerta .txtAlertArqVN").inner_text()
                                            
                                            async with page.expect_navigation(timeout=10000):
                                                await page.click("#BTACEPTAR")
                                        except Exception:
                                            pass
                                        finally:
                                            _warn(f"Sin éxito en {nombre_metodo} para {cuenta} ({texto_error_sistema}). Probando siguiente opción...")

                                if not localizado:
                                    _warn(f"No se pudo localizar '{cuenta}' en ninguno de los 3 métodos.")

                                await asyncio.sleep(2)


                contador_clientes += 1

            # VALIDACIÓN FINAL (RESPALDO)
            if not algun_registro_insertado:
                _warn("Ningún cliente o cuenta pudo ser insertado. Capturando 'No detectado' en Persona Moral por defecto.")
                try:
                    await asyncio.sleep(0.5)
                    await page.locator("#moralR").click()
                    await asyncio.sleep(0.5)
                    await page.locator("#razonS").fill("")
                    await page.locator("#razonS").press_sequentially("No detectado")
                    await asyncio.sleep(0.5)

                    async with page.expect_navigation(timeout=10000):
                        await page.evaluate("anadePer()")

                    _ok("Registro por defecto ('No detectado') agregado exitosamente.")
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Fallo crítico: No se pudo insertar el cliente por defecto ('No detectado'): {e}"
                    }

            tipo_operacion_limpio = limpiar_texto(tipo_operacion)
            _info("Seleccionando tipo de operación.")

            if "informe" in tipo_operacion_limpio and "juridico" in tipo_operacion_limpio:
                _info("Tipo de operación detectado: informe jurídico.")
                await page.locator("#chJuridico").click()
            elif "aseg" in tipo_operacion_limpio and "insumos" in tipo_operacion_limpio:
                _info("Tipo de operacion detectado: Aseguramientos con insumos")
                await page.locator("#chAseguramiento").click()
                await page.locator("#chAnalisis").click()
            elif "informe" in tipo_operacion_limpio:
                _info("Tipo de operación detectado: informe de insumos.")
                await page.locator("#chAnalisis").click()
            elif "insumos" in tipo_operacion_limpio:
                _info("Tipo de operación detectado: insumos.")
                await page.locator("#chAnalisis").click()
            elif "aseg" in tipo_operacion_limpio:
                _info("Tipo de operacion detectado: Aseguramientos")
                await page.locator("#chAseguramiento").click()
            else:
                _warn(f"No se detectó checkbox para el tipo de operación '{tipo_operacion}'.")

            await asyncio.sleep(0.5)

            dialog_handled = asyncio.Event()
            mensaje_dialogo = ""

            async def handle_dialog(dialog):
                nonlocal mensaje_dialogo
                mensaje_dialogo = dialog.message.strip()
                await dialog.accept()
                dialog_handled.set()

            page.once("dialog", handle_dialog)

            _info("Guardando alta de personas.")
            await page.locator("#btnGuardar2").click()

            intentos = 0
            max_intentos = 15
            error_encontrado = False
            texto_error_sistema = "No se detectó el mensaje de éxito (Timeout)"

            while intentos < max_intentos:
                if dialog_handled.is_set():
                    break

                if await page.is_visible(".TextoAlerta .txtAlertArqVN") and not error_encontrado:
                    error_encontrado = True
                    texto_error_sistema = await page.locator(".TextoAlerta .txtAlertArqVN").inner_text()
                    _warn(f"Aviso del sistema detectado: {texto_error_sistema}")
                    
                    try:
                        await page.wait_for_selector("#BTACEPTAR", timeout=5000)
                        await page.click("#BTACEPTAR")
                    except Exception as e:
                        _warn(f"No se pudo clickear BTACEPTAR: {e}")
                
                await asyncio.sleep(1)
                intentos += 1

            if error_encontrado:
                _error(f"Error al capturar clientes: {texto_error_sistema}")
                return {
                    "status": "error",
                    "message": f"Error al capturar cliente: {texto_error_sistema}" 
                }

            if dialog_handled.is_set():
                dialogo_normalizado = normalizar_texto(mensaje_dialogo)
                if any(texto in dialogo_normalizado for texto in ("error", "incorrect", "fall", "no se pudo")):
                    return {
                        "status": "error",
                        "message": f"SUGO rechazó el alta de personas: {mensaje_dialogo}",
                    }
                _ok(f"Alerta aceptada correctamente: {mensaje_dialogo}")
            else:
                return {
                    "status": "error",
                    "message": "No se confirmó el guardado del alta de personas.",
                }

        return {
            "status": "ok",
            "message": "Alta de personas realizada correctamente",
        }
        
    except Exception as e:
        _error(f"Alta de personas falló: {e}")
        return {
            "status": "error",
            "message": f"Ocurrió un error inesperado en alta de personas: {e}",
        }
