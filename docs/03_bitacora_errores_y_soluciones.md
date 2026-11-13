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

---

## Incidente #7: Selección de `IFace2`/`IEdge` en Late-Binding y Retorno `VT_VOID` en `FeatureFillet` / `FeatureChamfer` / `InsertFeatureShell`
* **Síntoma Preventivo Detectado en TypeLib (`v26.0`):**
  1. En SolidWorks 2018 COM, las interfaces `IFace2` (`{4A8BA4D8-DA25-4B75-8E2D-4922B74D81ED}`) e `IEdge` (`{83A33D42-27C5-11CE-BFD4-00400513BB57}`) **no exponen** `Select2()` ni `Select4()` en su interfaz `IDispatch` por defecto; dichos métodos pertenecen a la interfaz separada `IEntity` (`{83A33D65-27C5-11CE-BFD4-00400513BB57}`). Llamar `edge.Select2(True, 1)` o `face.Select2(False, 1)` desde `pywin32` en late-binding arroja error de miembro inexistente.
  2. Además, `IModelDoc2.FeatureFillet`, `IModelDoc2.FeatureChamfer` e `IModelDoc2.InsertFeatureShell` están declarados con tipo de retorno `ret=24` (`VT_VOID`), por lo que en Python siempre devuelven `None` aunque la operación 3D se haya creado con éxito.
* **Solución Aplicada:**
  1. Se implementó [`select_entity`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/connection.py#L229-L256) en `sw_engine/connection.py`, que selecciona cualquier objeto geométrico (`IFace2`, `IEdge`) a través de `model.SelectionManager.AddSelectionListObject(entity_obj, sel_data)` junto con `com_call_0(sel_mgr, "CreateSelectData")` (`sel_data.Mark = mark`).
  2. En [`execute_fillet`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/features.py#L375-L407), [`execute_chamfer`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/features.py#L410-L433) y [`execute_shell`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/features.py#L436-L497), se verifica la creación comprobando que `get_last_solid_feature_name(model)` haya cambiado tras la llamada COM.

---

## Incidente #8: `Falló FeatureExtrusion2 para el croquis 'Sketch1' en el plano 'Top'` en `Soporte_Abrazadera_Brida`
* **Síntoma:** Al intentar construir `Soporte_Abrazadera_Brida` (`pieza.json`), arrojó error en la primera operación `extrude_boss` sobre el plano `Top`.
* **Causa Raíz Doble:**
  1. **Parámetro `Sd` en Plano Medio (`midplane: true`):** En `FeatureExtrusion2`, cuando `T1 = 6` (`swEndCondMidPlane`), el primer parámetro `Sd` (`SingleDir`) **debe ser `True`**. Al pasar `Sd = False` con `D2 = 0.0`, SolidWorks activaba la Dirección 2 con profundidad `0.0 m` e invalidaba la extrusión de plano medio.
  2. **Contornos 2D solapados en un mismo croquis (`Sketch1`):** La IA colocó 5 primitivas que se intersectaban entre sí dentro del mismo `Sketch1` (un círculo central de `Ø60`, un rectángulo de `-40` a `0`, un círculo de `Ø20` en `(-40, 0)` y dos orejas de `Ø16` en `(32.48, 18.75)` y `(0, -37.5)`). En SolidWorks, un croquis con contornos cerrados cuyas líneas se cruzan sin recortar (`TrimEntities`) es rechazado por `FeatureExtrusion2` por tener regiones auto-intersectantes.
  3. **Cortes pasantes (`through_all: true`) sobre piezas con `midplane: true`:** Cuando el sólido base se extruye con `midplane: true`, el plano base queda en la mitad del sólido (`Y = 0`). Si un `extrude_cut` posterior con `through_all: true` corta en una sola dirección (`Sd = True`), solo perfora la mitad del espesor.
* **Solución Aplicada:**
  1. En `_extrude_single_sketch_boss` (`sw_engine/features.py`), se corrigió `sd=True` para `SW_END_COND_MID_PLANE` (con fallback a `sd=False` y `depth_m / 2.0` hacia cada lado).
  2. Se implementó **Descomposición Booleana 3D Automática** en `execute_extrude_boss` y `execute_extrude_cut`: si un croquis con múltiples figuras cerradas (`Circle`, `CenterRectangle`, `CornerRectangle`, `Polygon`, `Slot`) falla porque sus contornos se solapan, el motor elimina el croquis combinado huérfano (`DeleteSelection2(0)`) y extruye/corta cada figura secuencialmente con `Merge = True`, logrando que el kernel Parasolid de SolidWorks las una en un único sólido 3D limpio sin necesidad de recortar líneas 2D.
  3. En `_cut_single_sketch`, cuando `through_all=True` o `both_directions=True`, se prueba primero `sd=False` (corte hacia ambos lados del plano) para atravesar piezas simétricas completas.

---

## Incidente #9: `Falló FeatureCircularPattern4 sobre la operación 'Cut-Extrude4' alrededor del eje 'Y' (Axis1)` en `Abrazadera_Brida_Partida`
* **Síntoma:** Las primeras 9 operaciones de `Abrazadera_Brida_Partida` (`pieza.json`) se ejecutaron con éxito, pero la operación 10 (`circular_pattern` con `instances: 3` sobre `Cut-Extrude4`) falló.
* **Causa Raíz:**
  1. **Profundidad duplicada cuando `both_directions=True` y `through_all=False`:** En la operación 9 (`Cut-Extrude4`), la IA indicó `"both_directions": true, "through_all": false, "depth_mm": 10.0` sobre un cilindro de `20.0 mm` de alto total (`midplane: true`). Al invocar `FeatureCut3` con `sd=False` y `D1=10 mm, D2=10 mm`, el corte perforó `20 mm` totales (`10 mm` hacia arriba + `10 mm` hacia abajo), cortando la pared completa del anillo en vez de dejar `5 mm` arriba y `5 mm` abajo. Al intentar repetir ese corte 3 veces en círculo, el sólido se dividía en múltiples cuerpos inconexos (prohibido por `FeatureCircularPattern4`).
  2. **Cambio topológico al cruzar la ranura de apriete (`Cut-Extrude3`):** Al rotar `Cut-Extrude4` $+120^\circ$, la segunda instancia cae sobre la ranura de apriete (`x = -55..0`), donde la cara cilíndrica ya está partida en dos mitades, lo que hace que el solucionador de patrones de operaciones de SolidWorks devuelva `None`.
* **Solución Aplicada:**
  1. En `_cut_single_sketch` (`sw_engine/features.py`), cuando `both_directions=True` y `through_all=False`, se usa `SW_END_COND_MID_PLANE (6)` con `depth_1_m = depth_m` (o `sd=False` con `depth_m / 2.0` hacia cada lado), respetando la profundidad total centrada.
  2. En `execute_circular_pattern`, además de probar `FeatureCircularPattern4` con `GeometryPattern=False/True` y ángulo total/paso angular, se implementó un **Fallback Geométrico de Rotación 2D** (`_rotate_sketch`): si SolidWorks rechaza la matriz 3D por cambio topológico, el motor rota automáticamente las coordenadas 2D del croquis anterior por $k \times \Delta\theta$ y ejecuta los cortes directamente con el kernel booleano.
  3. En `main.py`, se redirigió `sys.stdout` en tiempo real hacia el cuadro de texto de la GUI y hacia el archivo `ultimo_log.txt` para contar con trazabilidad completa en cada ejecución.

---

## Incidente #10: Cortes pasantes (`through_all: true`) a mitad de altura en piezas `midplane: true` y vaciado en sección (`SECTION A-A`)
* **Síntoma:** Al construir `Abrazadera_Brida_Partida` (`pieza.json`), el agujero central de `Ø50`, los dos de `Ø10`, el de `Ø8` y la ranura de `2 mm` perforaban solo la mitad superior del sólido (`10 mm` en vez de `20 mm`), dejando un piso macizo en el plano medio (`Y = 0`). Además, el vaciado central de `10 mm` (`SECTION A-A`) rebanaba la oreja izquierda de apriete (`180°`) al rotarse con `circular_pattern`.
* **Causa Raíz:**
  1. En `_cut_single_sketch` (`sw_engine/features.py`), cuando `op.through_all = True`, el primer intento llamaba a `FeatureCut3` con `sd = True` (*Single Direction*) y `end_cond_1 = SW_END_COND_THROUGH_ALL_BOTH (9)`. En SolidWorks 2018, pasar `Sd = True` hace que `FeatureCut3` evalúe únicamente la Dirección 1 y corte solo una mitad desde el plano central (`Y = 0` a `+10 mm`), devolviendo un puntero `IFeature` válido e impidiendo que se ejecutara el bloque `sd = False`.
  2. Como el centro `(0,0)` había quedado macizo en la mitad inferior (`Y = -10` a `0`), los cortes en cuña con vértice en `(0,0)` generaban geometría de espesor cero en el origen al rotarse.
  3. En el plano original (`SECTION A-A`), las dos orejas derechas (`±60°`) llevan un vaciado central de `10 mm` por fuera del cilindro de `Ø60` (convirtiéndolas en horquillas dobles sin cortar la pared del cilindro detrás de ellas), mientras que las 3 ventanas pasantes de la pared del cilindro están ubicadas *entre* las orejas (`0°`, `120°`, `240°`).
* **Solución Aplicada:**
  1. Se eliminó el intento con `sd = True, end_cond_1 = SW_END_COND_THROUGH_ALL_BOTH` en `_cut_single_sketch` (`sw_engine/features.py`) para que `op.through_all = True` invoque directamente `sd = False` (ambas direcciones) con `end_cond_1 = SW_END_COND_THROUGH_ALL (1)` y `end_cond_2 = SW_END_COND_THROUGH_ALL (1)`.
  2. Se reestructuró `pieza.json` y se agregaron dos herramientas estructurales nuevas al esquema (`schemas/cad_schema.py`), al motor (`sw_engine/features.py`) y al prompt (`PROMPT_PARA_CHAT.txt` / `ai/system_prompt.md`):
     - **`MirrorOperation` (`"type": "mirror"`, `"plane": "Front" | "Top" | "Right"`):** permite reflejar un vaciado asimétrico (como el sector `[+15°, +120°]` de `SECTION A-A` que ahorquilla la oreja de `+60°` y abre las ventanas a ambos lados de la oreja) hacia `[-15°, -120°]` sin usar un `circular_pattern` de `360°` que destruiría la mordaza izquierda (`180°`).
     - **Filtro topológico `edges` en `FilletOperation` (`"vertical"`, `"horizontal_slot_ends"`, `"last_feature"`, `"all"`):**
       - `"vertical"` detecta las aristas rectas verticales paralelas a `Y` para aplicar empalmes de cuello (`R8` entre orejas y cilindro) antes de los cortes.
       - `"horizontal_slot_ends"` detecta las caras verticales interiores de fin de vaciado (`-max_y < y_min < y_max < +max_y`) y redondea sus aristas horizontales superior e inferior (con fallback automático `0.96 * R` para evitar el error de cara nula de Parasolid cuando $2R = H$), creando los extremos semicirculares redondos ("redondeles" `R5`) en las aperturas laterales.

---

## Incidente #11: Propagación excesiva de `FeatureFillet` 3D y error `Sketch7` en `mirror` (`Abrazadera_Brida_Partida_Exacta`)
* **Síntoma:**
  1. Al activar `FeatureFillet` sobre aristas interiores con propagación tangente (`Propagate = True`), SolidWorks propagaba el redondeo a lo largo de la corona superior y deformaba la pieza.
  2. Tras quitar los `fillet` automáticos y regenerar la pieza desde visión con `mirror`, la operación 7 (`mirror` sobre `Front`, croquis `Sketch7`) falló en `FeatureCut3`.
* **Causa Raíz:**
  1. En SolidWorks, los redondeos 3D selectivos (`Fillet` / `Chamfer`) dependen de aristas puntuales difíciles de predecir en un JSON generado a ciegas; es más limpio y confiable delegarlos al ajuste manual del usuario en SolidWorks.
  2. En `Abrazadera_Brida_Partida_Exacta`, las operaciones 6 y 7 eran dos cuñas parciales reflejadas cuyo vértice convergía exactamente en `(0,0)` *antes* de realizar el agujero pasante central de `Ø50` (operación 8), generando geometría de espesor cero (*Zero-Thickness*) en el origen; además, `_mirror_sketch` invertía `direction` de los arcos sin invertir el orden de recorrido.
* **Solución Aplicada:**
  1. Se desactivó el uso automático de `fillet` y `chamfer` 3D en `PROMPT_PARA_CHAT.txt`, `ai/system_prompt.md` y `pieza.json` (dejando las aristas vivas para redondeo manual del usuario).
  2. En `sw_engine/features.py`, `_mirror_sketch` ahora invierte el orden de segmentos e intercambia `(x1, y1) <-> (x2, y2)` conservando `direction = 1`, y `_optimize_operation_order` ejecuta automáticamente los cortes pasantes (`through_all=True`) antes que los cortes parciales dentro de cada bloque de cortes, logrando la construcción completa de `Abrazadera_Brida_Partida_Exacta` (10 operaciones).

---

## Incidente #12: `Falló FeatureExtrusion2 para el croquis 'Sketch2' en el plano 'Front'` en contornos multi-arco (`Mascara_IronMan_Placa_Frontal`)
* **Síntoma:** La Operación 1 (`Sketch1`, 10 figuras) se extruyó con éxito (`Boss-Extrude1`), pero la Operación 2 (`Sketch2`, 16 figuras con 4 arcos) falló en `FeatureExtrusion2`.
* **Causa Raíz Doble:**
  1. **Desajuste de radios ($R_1 \neq R_2$) por redondeo decimal de la IA en primitivas `arc`:** En los 4 arcos de `Sketch2`, las coordenadas redondeadas por la IA tenían una diferencia entre $\text{dist}(C, P_1)$ y $\text{dist}(C, P_2)$ de `0.339 mm` (`134.76 mm` vs `135.10 mm`) y `0.061 mm` (`98.00 mm` vs `98.06 mm`). En SolidWorks, `SketchManager.CreateArc` fija el radio exclusivamente con $\text{dist}(C, P_1)$ y proyecta $P_2$ a ese radio, desplazando el extremo real del arco y dejando **4 brechas abiertas (contorno abierto)** con las líneas contiguas.
  2. **Saliente secundario sumergido en el mismo plano (`plane_offset_mm: 0.0`):** `Op 1` extruyó una placa base de `12.0 mm` en `+Normal` (`Z = 0..+12 mm`) y `Op 2` intentó extruir un relieve interior más pequeño de `6.0 mm` sobre el mismo plano `Front` (`Z = 0..+6 mm`). Con `Merge = True`, un saliente 100% sumergido dentro de un sólido existente no aporta volumen nuevo y `FeatureExtrusion2` devuelve `None`.
* **Solución Aplicada:**
  1. En [`draw_shape`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/primitives.py#L78-L108) (`sw_engine/primitives.py`), antes de llamar a `CreateArc`, el motor proyecta ortogonalmente el centro `(cx, cy)` sobre la **mediatriz (bisectriz perpendicular)** de la cuerda $P_1 P_2$. Por geometría euclidiana, cualquier punto sobre la mediatriz cumple $\text{dist}(C_{\text{exact}}, P_1) \equiv \text{dist}(C_{\text{exact}}, P_2)$ con precisión `float64` ($10^{-16}$), eliminando para siempre los contornos abiertos por redondeo decimal en arcos generados por IA.
  2. En [`_extrude_single_sketch_boss`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/features.py#L121-L135) (`sw_engine/features.py`), si la extrusión en `+Normal` (`reverse_dir=False`) devuelve `None` porque el saliente queda sumergido en el sólido base, el motor reintenta automáticamente en dirección `-Normal` (`reverse_dir=True`, hacia el frente del plano base).

---

## Incidente #13: Micro-escalón de micrones al combinar `arc` truncado con `revolve_cut` en bayonetas (`Cilindro_Bayoneta_Limpio`)
* **Síntoma:** Al construir cortes radiales de bayoneta con `extrude_cut` (`arc` + `line` usando coordenadas trigonométricas redondeadas a 3 decimales en el JSON, ej. `21.637`, `6.179`) seguidos de `revolve_cut` con ángulo exacto (`40.0°`), aparecía una costura / micro-escalón de ~`0.002 mm` (dentro de la tolerancia Parasolid de `10^-6 m`).
* **Causa Raíz:** Los vértices del JSON redondeados a 3 decimales no cumplen exactamente $x^2 + y^2 = R^2$ ni $\text{atan2}(y, x) = \theta$ respecto al `revolve_cut` exacto, y al pasar por el ajuste de radio en `CreateArc`, el límite radial o angular se desplaza unos micrones respecto a la cara cilíndrica/radial revolucionada.
* **Solución Aplicada (Doble Capacidad en Esquema, Motor y Prompts):**
  1. **Primitiva 2D [`AnnularSector`](file:///d:/Usuario/Desktop/sketch2solid/schemas/cad_schema.py) (`"kind": "annular_sector"`) y [`_draw_annular_sector`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/primitives.py):** Permite expresar sectores de corona circular directamente con `inner_radius`, `outer_radius`, `start_angle_deg` y `end_angle_deg`. El motor calcula los 4 vértices internamente en `float64` (`math.cos`/`math.sin`), eliminando las diferencias de redondeo respecto a `revolve_cut` y soportando rotación/simetría exacta en [`_rotate_sketch`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/features.py) y [`_mirror_sketch`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/features.py).
  2. **Operación 3D [`WrapOperation`](file:///d:/Usuario/Desktop/sketch2solid/schemas/cad_schema.py) (`"type": "wrap"`) y [`execute_wrap`](file:///d:/Usuario/Desktop/sketch2solid/sw_engine/features.py):** Envuelve un croquis 2D cerrado sobre la cara cilíndrica mediante `IFeatureManager::InsertWrapFeature2` (probando `Analytical` y `SplineSurface`, seleccionando el croquis con `Mark=4` y la cara cilíndrica con `Mark=1` identificada vía `ISurface.IsCylinder`/`CylinderParams`). Se documentó además la precaución de mantener el croquis de `wrap` dentro de la altura de la cara cilíndrica (o recortar un cilindro más largo después) si la ranura abre hacia el borde superior.
  3. Se actualizaron [`PROMPT_PARA_CHAT.txt`](file:///d:/Usuario/Desktop/sketch2solid/PROMPT_PARA_CHAT.txt) y [`ai/system_prompt.md`](file:///d:/Usuario/Desktop/sketch2solid/ai/system_prompt.md) con ambas capacidades.




