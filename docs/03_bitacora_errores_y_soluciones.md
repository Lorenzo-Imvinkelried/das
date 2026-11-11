# 03. Bitácora de Errores, Causas Raíz y Soluciones (Troubleshooting Log)

Este documento registra cada problema real encontrado durante la construcción y prueba del sistema, por qué ocurrió exactamente y cómo se solucionó.

> **Instrucción de Mantenimiento:** Cada vez que se resuelva un bug nuevo o se instale/ajuste un componente, agregar una nueva entrada numerada al final de este documento.

---

## Incidente #1: `ModuleNotFoundError: No module named 'pydantic'` y `No module named 'pip'` al usar `python`
* **Síntoma:** Al ejecutar `python` en consola, no encontraba `pydantic` ni tenía el módulo `pip`.
* **Causa Raíz:** En la PC existen múltiples instalaciones de Python (`C:\msys64\ucrt64\bin\python.exe`, `C:\msys64\mingw64\bin\python.exe` y `C:\Python313\python.exe`). El comando `python` apuntaba primero al Python de MSYS2 (`ucrt64`), que carecía de `pip` y de las librerías del proyecto.
* **Solución Aplicada:**
  1. Se utilizó el lanzador de Python de Windows (`py`, que apunta a `C:\Python313\python.exe`) para crear el entorno virtual `D:\Usuario\Desktop\sketch2solid\.venv`.
  2. Se instalaron todas las dependencias de `requirements.txt` dentro de `.venv`.

---

## Incidente #2: `ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements.txt'`
* **Síntoma:** Al correr `pip install -r requirements.txt` en el Símbolo del sistema (CMD), arrojaba error de archivo no encontrado.
* **Causa Raíz:** La consola CMD estaba posicionada en el directorio por defecto del usuario (`C:\Users\Usuario>`) en lugar de la carpeta del proyecto (`D:\Usuario\Desktop\sketch2solid`).
* **Solución Aplicada:** Documentar el cambio obligatorio de unidad y carpeta con `cd /d D:\Usuario\Desktop\sketch2solid` en CMD (o `cd D:\Usuario\Desktop\sketch2solid` en PowerShell).

---

## Incidente #3: `com_error(-2147221021, 'Operación no disponible')` (`MK_E_UNAVAILABLE`) desde la terminal del agente
* **Síntoma:** Aunque `SLDWORKS.exe` estaba abierto (`SOLIDWORKS Premium 2018 x64 Edition - [Part1]`), ejecutar `test_engine.py` desde la herramienta de comandos interna del agente fallaba al conectar con `SldWorks.Application`.
* **Causa Raíz:** Al inspeccionar la estación de ventanas y escritorio con `win32service.GetThreadDesktop`, se comprobó que el agente ejecuta comandos en un escritorio aislado (`Desktop: exebox-...`), donde la `Running Object Table` (`ROT`) tiene `0` entradas y no puede ver procesos COM del escritorio interactivo del usuario (`Desktop: Default`).
* **Solución Aplicada:**
  1. Ejecutar el script desde el escritorio normal del usuario (vía CMD, PowerShell o Python IDLE).
  2. Mejorar `connect_to_solidworks()` en `sw_engine/connection.py` para intentar primero `win32com.client.GetActiveObject("SldWorks.Application")` (conexión instantánea a instancia abierta) con fallback a `Dispatch("SldWorks.Application")`, e incluir el detalle de la excepción COM en el mensaje de error.

---

## Incidente #4: `(-2147352573, 'No se ha encontrado el miembro.', None, None)` justo después de dibujar `Sketch1`
* **Síntoma:** El script conectaba con SolidWorks 2018, creaba `Part1`, seleccionaba `"Front Plane"`, abría `Sketch1`, dibujaba el rectángulo de `100 x 50 mm`, cerraba `Sketch1` y se detenía inmediatamente con `(-2147352573, 'No se ha encontrado el miembro.', None, None)` (`DISP_E_MEMBERNOTFOUND`).
* **Causa Raíz:**
  1. Al inspeccionar la librería de tipos `SldWorks 2018 Type Library` (`{83A33D31-27C5-11CE-BFD4-00400513BB57}`) y el código interno de `win32com.client.dynamic.CDispatch.__getattr__`, se descubrió que cuando se accede a un método de **0 argumentos** (como `model.FirstFeature`, `feat.GetTypeName2`, `feat.GetNextFeature`, `sw_app.NewPart`, `model.EditRebuild3`, `model.ViewZoomtofit2`, `model.GetTitle`), `CDispatch.__getattr__` invoca primero `INVOKE_PROPERTYGET` con 0 argumentos.
  2. SolidWorks 2018 acepta `INVOKE_PROPERTYGET` en funciones de 0 argumentos, ejecuta la función en ese instante y devuelve el objeto resultado (por ejemplo, un `CDispatch` representando `IFeature`).
  3. Luego, al tener `()` en Python (`model.FirstFeature()`), Python invocaba `CDispatch.__call__()` sobre el objeto `IFeature` devuelto, intentando ejecutar `DISPID 0` (miembro por defecto), el cual no existe en `IFeature`, disparando `DISP_E_MEMBERNOTFOUND (-2147352573)`.
* **Solución Aplicada:**
  * Se implementó el helper `com_call_0(obj, member_name)` en `sw_engine/connection.py`:
    ```python
    def com_call_0(obj: Any, member_name: str) -> Any:
        val = getattr(obj, member_name)
        if callable(val) and not hasattr(val, "_oleobj_"):
            return val()
        return val
    ```
  * Se reemplazaron todas las llamadas a métodos COM de 0 argumentos en `sw_engine/connection.py`, `sw_engine/primitives.py`, `sw_engine/features.py` y `test_engine.py` por `com_call_0(...)`.

---

## Incidente #5: `ModuleNotFoundError: No module named 'pythoncom'` al ejecutar desde Python IDLE (F5)
* **Síntoma:** Al abrir `test_engine.py` con **Python IDLE** y darle a `Run Module (F5)`, lanzaba `ModuleNotFoundError: No module named 'pythoncom'`.
* **Causa Raíz:** Python IDLE corre sobre la instalación global de Python (`C:\Python313\python.exe`), mientras que `pywin32` y `google-genai` se habían instalado inicialmente solo en `.venv`.
* **Solución Aplicada:**
  1. Se ejecutó `C:\Python313\python.exe -m pip install -r requirements.txt` para dejar `pywin32` y `google-genai` instalados también en el Python global.
  2. Se eliminó `sys.exit()` al final de `test_engine.py` para evitar el cuadro emergente `SystemExit` de IDLE al finalizar la ejecución.
  3. **Resultado:** Ejecución 100% funcional desde Python IDLE en vivo contra SolidWorks 2018.

---

## Incidente #6: Crash de SolidWorks (`Fault Module: slduiu:016A3C00`, `virtual address 0`) al poner una Cota Inteligente
* **Síntoma:** La pieza 3D se construía bien desde el JSON, pero en cuanto el usuario entraba en SolidWorks a **Editar croquis** y usaba **Cota inteligente (Smart Dimension)** sobre cualquier línea, SolidWorks crasheaba con:
  `Access Violation at 0000000049573C00 (virtual address 0), attempt to read from memory` en `slduiu:016A3C00`.
* **Causa Raíz Exacta (confirmada en `swxJRNL.swj` y el log de crash):**
  1. **Plantilla `.prtdot` por defecto inexistente (`Pieza.prtdot` vs `Part.prtdot`):**
     * En `swxJRNL.swj` (línea 28) quedó registrado que al llamar a `swApp.NewPart()`, SolidWorks ejecutaba internamente:
       `swApp.NewDocument("C:\ProgramData\SolidWorks\SOLIDWORKS 2018\templates\Pieza.prtdot", 0, 0, 0)`
     * Al verificar en disco con `Test-Path`, `Pieza.prtdot` **NO EXISTE** (`False`), porque la plantilla real instalada se llama `Part.prtdot` (`True`).
     * Como la preferencia de registro `Dont Ask Default Template Preferences` estaba en `1`, `swApp.NewPart()` creaba silenciosamente un documento `PartDoc` en blanco **sin plantilla** (con sus tablas internas de estilos de cota, fuentes y estándar de acotación en **`NULL` / dirección virtual `0x0`**).
     * Ese documento sin plantilla permitía dibujar líneas y extruir sólidos, pero en el instante en que el usuario seleccionaba **Cota inteligente** (`<CD>=8 32888 0`), `slduiu.dll` intentaba leer el estilo de cota en `0x0000000000000000` (`virtual address 0`) y crasheaba de inmediato.
  2. **Otros ajustes complementarios detectados en el journal y TypeLib:**
     * En `D:\SW\SOLIDWORKS\swconst.tlb`, `swInputDimValOnCreate` es el enum **`10`** (el `8` es `swDxfMapping`) y `swSketchInference` es **`249`**.
     * Al llamar a `CreateCenterRectangle` con `AddToDB = False`, SolidWorks dejaba abierto el PropertyManager `<ED>uiSkRectangleProp_c "Rectangle"` en la barra lateral; en cambio, envolver en `AddToDB = True` + `SetPickMode` evita que se abra ese panel.
     * En `FeatureCut3`, probar `reverse_dir=False` primero sobre un plano base disparaba un aviso interno `'Cut-Extrude1: Cannot locate end of feature'` antes de reintentar con `reverse_dir=True`.
* **Solución Aplicada:**
  1. Se implementó [`resolve_valid_part_template`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/connection.py#L123-L185) en `sw_engine/connection.py`, que verifica con `os.path.isfile()` si la plantilla configurada existe realmente en disco; si no existe (`Pieza.prtdot`), localiza automáticamente `Part.prtdot`, actualiza la preferencia `swDefaultTemplatePart (8)` en SolidWorks y abre el documento mediante `sw_app.NewDocument(template_path, 0, 0.0, 0.0)` **antes** de recurrir a `NewPart()`.
  2. Se mantuvo `sketch_mgr.AddToDB = True` seguido de `SetPickMode` en `sw_engine/primitives.py` para no abrir paneles PropertyManager residuales.
  3. Se invirtió el orden de prueba en `execute_extrude_cut` (`reverse_dir=True` primero) para cortar en la misma dirección `+Normal` del saliente sin generar errores de reconstrucción intermedios.
  4. En `main.py`, se libera `del model` + `gc.collect()` inmediatamente al finalizar la construcción.

