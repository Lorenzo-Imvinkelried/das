# 02. Motor de Ejecución COM en SolidWorks 2018 (`sw_engine`)

Este documento detalla cómo funciona internamente el paquete `sw_engine/` y las reglas estrictas necesarias para que `pywin32` funcione sin crashear contra **SolidWorks 2018**.

---

## 1. Mapa de Responsabilidades dentro de `sw_engine/`

* **`sw_engine/connection.py`**:
  * Conexión COM (`connect_to_solidworks`).
  * Creación de documento de pieza (`create_new_part`).
  * Conversión de unidades (`mm_to_m`).
  * Invocación segura de métodos de 0 argumentos (`com_call_0`).
  * Selección segura de entidades (`select_by_id`) y planos multilenguaje (`select_reference_plane`).
  * Control de preferencias de interfaz (`set_input_dim_on_create`).
* **`sw_engine/primitives.py`**:
  * Traducción de figuras 2D Pydantic (`CenterRectangle`, `CornerRectangle`, `Circle`, `Line`) a llamadas de `ISketchManager` (`draw_shape`).
  * Ciclo de vida completo de un croquis (`build_sketch_on_plane`): seleccionar plano -> `InsertSketch(True)` -> `AddToDB = True` -> dibujar -> `AddToDB = False` -> `ClearSelection2(True)` -> `InsertSketch(True)` -> seleccionar croquis recién creado (`get_last_sketch_name`).
* **`sw_engine/features.py`**:
  * Operaciones 3D en `IFeatureManager`: extrusión de saliente (`execute_extrude_boss` con `FeatureExtrusion2`) y corte extruido (`execute_extrude_cut` con `FeatureCut3`).
  * Orquestador de pieza completa (`build_part`).

---

## 2. Las 7 Reglas de Oro de la API COM de SolidWorks 2018 en Python

### Regla 1: Conversión Obligatoria de Unidades (`mm` -> `metros`)
La API interna de SolidWorks trabaja exclusivamente en **metros** (y radianes).
* Si se pasa `100.0` directo a la API, SolidWorks dibuja una pieza de **100 metros**.
* Todo valor proveniente del JSON (`schemas/cad_schema.py`) debe pasar por `mm_to_m(valor)` (`valor / 1000.0`) antes de enviarse a cualquier método COM.

### Regla 2: Métodos de 0 Argumentos en Late-Binding (`com_call_0`)
En `pywin32` sin `gencache` (`win32com.client.dynamic.CDispatch`), cuando Python evalúa `obj.MetodoSinArgs`, `CDispatch.__getattr__` envía primero una petición COM `INVOKE_PROPERTYGET` con `0` argumentos.
* En SolidWorks 2018, los métodos de 0 argumentos (`NewPart`, `FirstFeature`, `GetNextFeature`, `GetTypeName2`, `EditRebuild3`, `ViewZoomtofit2`, `GetTitle`) **se ejecutan inmediatamente durante ese `getattr`** y devuelven el resultado (`CDispatch`, `str`, `bool` o `None`).
* Si en el código Python se escriben paréntesis `()` al final (ej. `model.FirstFeature()`), Python intenta ejecutar `CDispatch.__call__()` sobre el objeto devuelto (`IFeature`), lo cual invoca `DISPID 0` (miembro por defecto inexistente) y lanza el error fatal:
  `com_error: (-2147352573, 'No se ha encontrado el miembro.', None, None)`.
* **Solución obligatoria:** Usar siempre `com_call_0(obj, "NombreMetodo")` para cualquier método de 0 argumentos verificado en la TypeLib.

### Regla 3: Puntero COM Nulo en `SelectByID2` (`Callout`)
El método `IModelDocExtension::SelectByID2` recibe 9 parámetros, donde el 8.º (`Callout`) espera un puntero `IDispatch*`.
* Pasar `None` directo desde Python suele producir `Type Mismatch` en SolidWorks 2018.
* Siempre se debe pasar `win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)` a través del wrapper `select_by_id()`.

### Regla 4: Selección de Planos Multilenguaje (Español + Inglés + Fallback)
El nombre de los planos base depende del idioma de la plantilla `.prtdot` con la que se creó la pieza (no solo del idioma de Windows).
* Por ejemplo, en la PC de desarrollo Windows está en español, pero la plantilla por defecto (`C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2018\templates\Part.prtdot`) crea planos en inglés (`"Front Plane"`, `"Top Plane"`, `"Right Plane"`).
* `select_reference_plane()` prueba en orden:
  * `"Front"` -> `["Alzado", "Front Plane", "Plano frontal"]`
  * `"Top"` -> `["Planta", "Top Plane", "Plano superior"]`
  * `"Right"` -> `["Vista lateral", "Right Plane", "Plano derecho"]`
* Si ninguno coincide (plantilla personalizada), recorre el árbol con `FirstFeature` / `GetNextFeature` buscando los `RefPlane` por orden (0, 1, 2).

### Regla 5: `AddToDB = True` + `SetPickMode`, Sin Popups (`enum 10`) y Sin Inferencias (`enum 249`)
* Se envuelve la creación de entidades entre `sketch_mgr.AddToDB = True` y `False` seguido de `SetPickMode` para evitar que se quede abierto el panel lateral `<ED>uiSkRectangleProp_c "Rectangle"` en la UI.
* Además, se desactivan temporalmente **`swInputDimValOnCreate` (`enum 10`)** y **`swSketchInference` (`enum 249`)** durante el dibujo por API, restaurándolos a `True` en el bloque `finally`.
* Al terminar `build_in_solidworks` en `main.py`, se hace `del model` + `gc.collect()` para liberar todos los punteros COM antes de que el usuario edite la pieza en SolidWorks.

### Regla 6: Cierre y Reselección del Croquis Antes de Operar en 3D
* Todo croquis debe cerrarse con `sketch_mgr.InsertSketch(True)` **antes** de llamar a `FeatureExtrusion2` o `FeatureCut3`.
* Al limpiar selecciones y cerrar el croquis, SolidWorks puede dejar el croquis deseleccionccionado en el árbol. Por eso `build_sketch_on_plane` busca el nombre del último `ProfileFeature` creado (`get_last_sketch_name`) y lo selecciona explícitamente con `select_by_id(..., "SKETCH")` antes de invocar al `FeatureManager`.

### Regla 7: Dirección Normal en `FeatureCut3` sobre Planos de Referencia
* `FeatureExtrusion2` (23 parámetros) extruye por defecto en sentido `+Normal` del plano (`Dir=False`).
* `FeatureCut3` (26 parámetros) corta hacia `+Normal` cuando `Dir=True` (`reverse_dir=True`). Por eso `execute_extrude_cut` prueba primero con `reverse_dir=True` (evitando el aviso interno `'Cannot locate end of feature'`) y si devuelve `None`, reintenta con `reverse_dir=False` (y `Sd=False` en `through_all`).

### Regla 8: Verificación Obligatoria de Plantilla `.prtdot` en Disco (`Pieza.prtdot` vs `Part.prtdot`)
* **NUNCA llamar a `swApp.NewPart()` sin verificar antes que la ruta de `swDefaultTemplatePart (8)` exista físicamente en disco (`os.path.isfile`).**
* En instalaciones con recursos en español sobre plantillas en inglés, `swDefaultTemplatePart` apunta a `...\Pieza.prtdot` (inexistente), mientras que el archivo real en disco es `...\Part.prtdot`.
* Si `NewPart()` se ejecuta con una plantilla inexistente, SolidWorks crea una pieza en blanco sin tabla de estilos de cota (`pDimStyle = NULL`, dirección `0x0`), provocando un crash inmediato (`Access Violation at virtual address 0` en `slduiu:016A3C00`) apenas el usuario usa **Cota inteligente**.
* Por eso `create_new_part()` ejecuta primero `resolve_valid_part_template(sw_app)` y abre la pieza con `sw_app.NewDocument(valid_template_path, 0, 0.0, 0.0)`.

