# 02. Motor de Ejecución COM en SolidWorks 2018 (`sw_engine`)

Este documento detalla cómo funciona internamente el paquete `sw_engine/` y las reglas estrictas necesarias para que `pywin32` funcione sin crashear contra **SolidWorks 2018**.

---

## 1. Mapa de Responsabilidades dentro de `sw_engine/`

* **`sw_engine/connection.py`**:
  * Conexión COM (`connect_to_solidworks`).
  * Creación de documento de pieza verificando plantilla `.prtdot` en disco (`create_new_part`, `resolve_valid_part_template`).
  * Conversión de unidades (`mm_to_m`).
  * Invocación segura de métodos de 0 argumentos (`com_call_0`).
  * Selección segura de entidades (`select_by_id`), selección directa de geometría `IFace2`/`IEdge` mediante `SelectionManager.AddSelectionListObject` + `CreateSelectData` (`select_entity`), planos multilenguaje (`select_reference_plane`) y creación de planos paralelos desfasados (`select_or_create_plane` con `InsertRefPlane`).
  * Creación de ejes de referencia en la intersección de planos ortogonales (`create_reference_axis` con `InsertAxis2`) e identificación de la última operación 3D sólida (`get_last_solid_feature_name`).
  * Control de preferencias de interfaz (`set_input_dim_on_create`).
* **`sw_engine/primitives.py`**:
  * Traducción de 7 figuras 2D Pydantic (`CenterRectangle`, `CornerRectangle`, `Circle`, `Line`, `Polygon`, `Arc`, `Slot`) y línea constructiva (`AxisLine`) a llamadas de `ISketchManager` (`draw_shape`).
  * Ciclo de vida completo de un croquis (`build_sketch_on_plane`): seleccionar o crear plano desfasado -> `InsertSketch(True)` -> `AddToDB = True` -> dibujar primitivas y `CreateCenterLine` -> `AddToDB = False` -> `SetPickMode` -> `ClearSelection2(True)` -> `InsertSketch(True)` -> seleccionar croquis recién creado (`get_last_sketch_name`).
* **`sw_engine/features.py`**:
  * Las 9 operaciones 3D en SolidWorks 2018:
    * Extrusión de saliente (`execute_extrude_boss` con `FeatureExtrusion2`, 23 parámetros).
    * Corte extruido (`execute_extrude_cut` con `FeatureCut3`, 26 parámetros, incluyendo corte hacia ambos lados `both_directions`).
    * Revolución de saliente y corte por revolución (`execute_revolve` con `FeatureRevolve2`, 20 parámetros).
    * Matriz circular (`execute_circular_pattern` con `FeatureCircularPattern4`, 7 parámetros).
    * Matriz lineal (`execute_linear_pattern` con `FeatureLinearPattern3`, 10 parámetros).
    * Redondeo de aristas (`execute_fillet` con `IModelDoc2.FeatureFillet`, 5 parámetros, `VT_VOID`).
    * Chaflán de aristas (`execute_chamfer` con `IModelDoc2.FeatureChamfer`, 3 parámetros, `VT_VOID`).
    * Vaciado de carcasa (`execute_shell` con `IModelDoc2.InsertFeatureShell`, 2 parámetros, `VT_VOID`, seleccionando la cara exterior mediante normal + bounding box).
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

---

## 3. Firmas COM de Operaciones Avanzadas (Verificadas en TypeLib `v26.0` de SW 2018)

* **Planos Paralelos Desfasados (`IFeatureManager::InsertRefPlane`):**
  * `InsertRefPlane(FirstConstraint, FirstConstraintAngleOrDistance, SecondConstraint, SecondConstraintAngleOrDistance, ThirdConstraint, ThirdConstraintAngleOrDistance)`
  * `swRefPlaneReferenceConstraint_Distance = 8`, `swRefPlaneReferenceConstraint_OptionFlip = 256` (`8 | 256 = 264` cuando `plane_offset_mm < 0`).
* **Nuevas Primitivas 2D (`ISketchManager`):**
  * `CreatePolygon(XC, YC, Zc, Xp, Yp, Zp, Sides, Inscribed)` (8 parámetros).
  * `CreateArc(XC, YC, Zc, X1, Y1, Z1, X2, Y2, Z2, Direction)` (10 parámetros; `Direction = 1` antihorario, `-1` horario).
  * `CreateSketchSlot(SlotCreationType, SlotLengthType, Width, X1, Y1, Z1, X2, Y2, Z2, X3, Y3, Z3, CenterArcDirection, AddDimension)` (14 parámetros; `0 = line`, `0 = CenterCenter`).
  * `CreateCenterLine(X1, Y1, Z1, X2, Y2, Z2)` (6 parámetros; línea constructiva para eje de revolución).
* **Revolución y Corte por Revolución (`IFeatureManager::FeatureRevolve2`):**
  * 20 parámetros: `(SingleDir, IsSolid, IsThin, IsCut, ReverseDir, BothDirectionUpToSameEntity, Dir1Type, Dir2Type, Dir1Angle, Dir2Angle, OffsetReverse1, OffsetReverse2, OffsetDistance1, OffsetDistance2, ThinType, ThinThickness1, ThinThickness2, Merge, UseFeatScope, UseAutoSelect)`.
* **Ejes de Referencia y Matrices (`InsertAxis2`, `FeatureCircularPattern4`, `FeatureLinearPattern3`):**
  * `IModelDoc2::InsertAxis2(True)` con dos planos base seleccionados (`Mark=0`) crea un `RefAxis` en su intersección (`"Y" = Front+Right`, `"Z" = Top+Right`, `"X" = Front+Top`).
  * `FeatureCircularPattern4(Number, Spacing, FlipDirection, DName, GeometryPattern, EqualSpacing, VaryInstance)`: requiere seleccionar la operación 3D con `Mark=4` (`"BODYFEATURE"`) y el eje con `Mark=1` (`"AXIS"`).
  * `FeatureLinearPattern3(Num1, Spacing1, Num2, Spacing2, FlipDir1, FlipDir2, DName1, DName2, GeometryPattern, VaryInstance)`: requiere seleccionar la operación 3D con `Mark=4`, eje X con `Mark=1` y eje Y con `Mark=2`.
* **Selección de Caras/Aristas y Operaciones `VT_VOID` (`Fillet`, `Chamfer`, `Shell`):**
  * En `pywin32` late-binding, las interfaces `IFace2` e `IEdge` NO exponen `Select2()` en su `IDispatch` por defecto (`IEntity` es una interfaz COM separada). Por eso `select_entity()` usa `SelectionManager.AddSelectionListObject(obj, CreateSelectData())` con `Mark=1`.
  * Los métodos `IModelDoc2.FeatureFillet` (5 parámetros), `IModelDoc2.FeatureChamfer` (3 parámetros) y `IModelDoc2.InsertFeatureShell` (2 parámetros) devuelven `VT_VOID` (`None` en Python), por lo que el éxito de la operación se valida comparando el último nombre de operación 3D en el árbol (`get_last_solid_feature_name`).

