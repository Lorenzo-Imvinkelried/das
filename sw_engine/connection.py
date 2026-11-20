import glob
import os
import re
import sys
from typing import Any, Optional

import pythoncom
import win32com.client

from .compat import (
    SUPPORTED_SW_MAX_YEAR,
    SUPPORTED_SW_MIN_YEAR,
    SolidWorksVersionInfo,
    SwConstants,
    detect_solidworks_version,
    diagnose_com_connection_error,
    get_empty_double_array_variant,
    list_installed_solidworks_versions,
    load_sw_constants,
    year_to_major,
)
from .versions import SolidWorksVersionAdapter, get_version_adapter

# Constantes por defecto (se mantienen por retrocompatibilidad; en tiempo de ejecución
# se usan las resueltas dinámicamente desde swconst.tlb de la versión conectada)
_DEFAULT_CONSTS = SwConstants()
SW_FILE_LOCATIONS_DOC_TEMPLATES = _DEFAULT_CONSTS.swFileLocationsDocumentTemplates
SW_DEFAULT_TEMPLATE_PART = _DEFAULT_CONSTS.swDefaultTemplatePart
SW_INPUT_DIM_VAL_ON_CREATE = _DEFAULT_CONSTS.swInputDimValOnCreate
SW_SKETCH_INFERENCE = _DEFAULT_CONSTS.swSketchInference

# Constantes de planos de referencia (swRefPlaneReferenceConstraints_e)
SW_REF_PLANE_DISTANCE = _DEFAULT_CONSTS.swRefPlaneReferenceConstraint_Distance
SW_REF_PLANE_OPTION_FLIP = _DEFAULT_CONSTS.swRefPlaneReferenceConstraint_OptionFlip

# Estado de la sesión COM activa (versión detectada, adaptador por versión y constantes de swconst.tlb)
_ACTIVE_VERSION_INFO: SolidWorksVersionInfo = SolidWorksVersionInfo()
_ACTIVE_ADAPTER: SolidWorksVersionAdapter = get_version_adapter(_ACTIVE_VERSION_INFO)
_ACTIVE_CONSTANTS: SwConstants = _DEFAULT_CONSTS

# Mapeo multilenguaje (Español, Inglés, Portugués, Alemán, Francés, Italiano) para planos base.
# Si la plantilla usa cualquier otro idioma/nombre personalizado, select_reference_plane cae al
# fallback por orden de RefPlane (0, 1, 2) en el árbol del FeatureManager.
PLANE_NAMES_MAP: dict[str, list[str]] = {
    "Front": [
        "Alzado",
        "Front Plane",
        "Plano frontal",
        "Plano Frontal",
        "Ebene vorne",
        "Plan de face",
        "Piano frontale",
    ],
    "Top": [
        "Planta",
        "Top Plane",
        "Plano superior",
        "Plano Superior",
        "Ebene oben",
        "Plan de dessus",
        "Piano superiore",
    ],
    "Right": [
        "Vista lateral",
        "Right Plane",
        "Plano derecho",
        "Plano Direito",
        "Ebene rechts",
        "Plan de droite",
        "Piano destro",
    ],
}

PLANE_INDEX_MAP: dict[str, int] = {
    "Front": 0,
    "Top": 1,
    "Right": 2,
}

# Mapeo de ejes principales a la intersección de dos planos base ortogonales
AXIS_PLANES_MAP: dict[str, tuple[str, str]] = {
    "Y": ("Front", "Right"),  # Eje vertical Y (intersección Alzado + Vista lateral)
    "Z": ("Top", "Right"),    # Eje longitudinal Z (intersección Planta + Vista lateral)
    "X": ("Front", "Top"),    # Eje horizontal X (intersección Alzado + Planta)
}

# Tipos de elementos del árbol del FeatureManager que NO son operaciones 3D sólidas
NON_SOLID_FEATURE_TYPES: set[str] = {
    "OriginProfileFeature",
    "RefPlane",
    "RefAxis",
    "RefPoint",
    "CoordSys",
    "ProfileFeature",
    "3DProfileFeature",
    "HistoryFolder",
    "SensorFolder",
    "DetailCabinet",
    "MaterialFolder",
    "CommentsFolder",
    "FavoriteFolder",
    "SelectionSetFolder",
    "DocsFolder",
    "EqnFolder",
    "SolidBodyFolder",
    "SurfaceBodyFolder",
    "CutListFolder",
    "SubWeldFolder",
    "AmbientLight",
    "DirectionLight",
}

# Nombres prioritarios de plantilla de pieza (.prtdot) en múltiples idiomas
PREFERRED_PART_TEMPLATE_NAMES: tuple[str, ...] = (
    "Part.prtdot",
    "part.prtdot",
    "Pieza.prtdot",
    "pieza.prtdot",
    "Peça.prtdot",
    "Peca.prtdot",
    "Teil.prtdot",
    "Pièce.prtdot",
    "Piece.prtdot",
    "Parte.prtdot",
)


def get_connected_version_info() -> SolidWorksVersionInfo:
    """Devuelve los metadatos de la última instancia de SOLIDWORKS conectada."""
    return _ACTIVE_VERSION_INFO


def get_connected_adapter() -> SolidWorksVersionAdapter:
    """Devuelve el adaptador de comandos correspondiente a la versión de SOLIDWORKS conectada."""
    return _ACTIVE_ADAPTER


def get_connected_constants() -> SwConstants:
    """Devuelve las constantes swconst activas (cargadas desde swconst.tlb si estuvo disponible)."""
    return _ACTIVE_CONSTANTS


def mm_to_m(value_mm: float) -> float:
    """Convierte milímetros a metros (unidad interna obligatoria de la API de SOLIDWORKS)."""
    return float(value_mm) / 1000.0


def get_null_dispatch() -> win32com.client.VARIANT:
    """Devuelve un puntero COM IDispatch nulo seguro para SOLIDWORKS (evita Type Mismatch)."""
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def com_call_0(obj: Any, member_name: str) -> Any:
    """
    Invoca de forma segura un método o propiedad de 0 argumentos en SOLIDWORKS (pywin32).
    En late-binding (CDispatch), hacer getattr(obj, nombre) envía INVOKE_PROPERTYGET con 0 args,
    lo cual hace que SOLIDWORKS ejecute el método inmediatamente y devuelva el resultado
    (un CDispatch, str, bool o None). Llamar luego a () sobre un CDispatch invoca DISPID 0
    y lanza (-2147352573, 'No se ha encontrado el miembro.').
    """
    val = getattr(obj, member_name)
    if callable(val) and not hasattr(val, "_oleobj_"):
        return val()
    return val


def select_by_id(
    model: Any,
    name: str,
    obj_type: str,
    x_m: float = 0.0,
    y_m: float = 0.0,
    z_m: float = 0.0,
    append: bool = False,
    mark: int = 0,
    select_option: int = 0,
) -> bool:
    """Wrapper seguro sobre Extension.SelectByID2 con Callout VARIANT(VT_DISPATCH, None)."""
    null_callout = get_null_dispatch()
    return bool(
        model.Extension.SelectByID2(
            name,
            obj_type,
            float(x_m),
            float(y_m),
            float(z_m),
            bool(append),
            int(mark),
            null_callout,
            int(select_option),
        )
    )


def select_reference_plane(
    model: Any,
    plane: str = "Front",
    append: bool = False,
    mark: int = 0,
) -> bool:
    """
    Selecciona el plano base soportando SOLIDWORKS en cualquier idioma.
    Intenta primero por nombres conocidos (ES/EN/PT/DE/FR/IT) y si devuelve False
    recorre los primeros RefPlane del árbol del FeatureManager por índice (0, 1, 2).
    """
    candidates = PLANE_NAMES_MAP.get(plane, [plane])
    if not append:
        model.ClearSelection2(True)

    for candidate_name in candidates:
        if select_by_id(model, candidate_name, "PLANE", 0.0, 0.0, 0.0, append=append, mark=mark):
            return True

    # Fallback universal independiente del idioma: buscar por orden de RefPlane en el árbol
    target_idx = PLANE_INDEX_MAP.get(plane, 0)
    ref_plane_idx = 0
    feat = com_call_0(model, "FirstFeature")
    while feat is not None:
        if com_call_0(feat, "GetTypeName2") == "RefPlane":
            if ref_plane_idx == target_idx:
                feat_name = str(com_call_0(feat, "Name"))
                return select_by_id(model, feat_name, "PLANE", 0.0, 0.0, 0.0, append=append, mark=mark)
            ref_plane_idx += 1
        feat = com_call_0(feat, "GetNextFeature")

    raise RuntimeError(f"No se pudo seleccionar el plano base '{plane}' (intentados: {candidates}).")


def select_or_create_plane(model: Any, plane: str = "Front", offset_mm: float = 0.0) -> str:
    """
    Selecciona el plano base indicado o, si offset_mm != 0, crea un plano de referencia
    paralelo desfasado (InsertRefPlane) y lo deja seleccionado para abrir el croquis.
    """
    consts = get_connected_constants()
    select_reference_plane(model, plane, append=False, mark=0)
    if abs(offset_mm) <= 1e-6:
        return plane

    dist_flag = int(consts.swRefPlaneReferenceConstraint_Distance)
    flip_flag = int(consts.swRefPlaneReferenceConstraint_OptionFlip)
    constraint = dist_flag if offset_mm > 0 else (dist_flag | flip_flag)
    distance_m = mm_to_m(abs(offset_mm))

    ref_plane_feat = model.FeatureManager.InsertRefPlane(
        int(constraint),
        float(distance_m),
        0,
        0.0,
        0,
        0.0,
    )
    if ref_plane_feat is None:
        raise RuntimeError(
            f"No se pudo crear el plano paralelo desfasado ({offset_mm} mm) desde '{plane}'."
        )

    # Buscar el nombre del último RefPlane creado en el árbol
    last_plane_name = ""
    try:
        last_plane_name = str(com_call_0(ref_plane_feat, "Name") or "")
    except Exception:
        last_plane_name = ""

    if not last_plane_name:
        feat = com_call_0(model, "FirstFeature")
        while feat is not None:
            if com_call_0(feat, "GetTypeName2") == "RefPlane":
                last_plane_name = str(com_call_0(feat, "Name"))
            feat = com_call_0(feat, "GetNextFeature")

    if not last_plane_name:
        raise RuntimeError("Se creó el plano de referencia pero no se pudo obtener su nombre.")

    model.ClearSelection2(True)
    select_by_id(model, last_plane_name, "PLANE", 0.0, 0.0, 0.0, append=False, mark=0)
    return last_plane_name


def create_reference_axis(model: Any, axis: str = "Y") -> str:
    """
    Crea un eje de referencia (RefAxis) en la intersección de dos planos base ortogonales
    mediante ModelDoc2.InsertAxis2(True) y devuelve su nombre en el árbol.
    - 'Y': intersección de 'Front' y 'Right' (eje vertical)
    - 'Z': intersección de 'Top' y 'Right' (eje longitudinal)
    - 'X': intersección de 'Front' y 'Top' (eje horizontal)
    """
    plane_1, plane_2 = AXIS_PLANES_MAP.get(axis.upper(), ("Front", "Right"))
    select_reference_plane(model, plane_1, append=False, mark=0)
    select_reference_plane(model, plane_2, append=True, mark=0)

    ok = bool(model.InsertAxis2(True))
    if not ok:
        raise RuntimeError(
            f"Falló InsertAxis2(True) al crear el eje de referencia '{axis}' "
            f"(intersección de '{plane_1}' y '{plane_2}')."
        )

    last_axis_name = ""
    feat = com_call_0(model, "FirstFeature")
    while feat is not None:
        if com_call_0(feat, "GetTypeName2") == "RefAxis":
            last_axis_name = str(com_call_0(feat, "Name"))
        feat = com_call_0(feat, "GetNextFeature")

    if not last_axis_name:
        raise RuntimeError(f"No se encontró el eje de referencia creado para el eje '{axis}'.")

    model.ClearSelection2(True)
    return last_axis_name


def select_entity(
    model: Any,
    entity_obj: Any,
    append: bool = False,
    mark: int = 1,
) -> bool:
    """
    Selecciona una entidad geométrica COM (IFace2, IEdge, etc.) en SOLIDWORKS.
    En late-binding (pywin32), IFace2 e IEdge no exponen directamente IEntity.Select2(),
    por lo que se utiliza SelectionManager.AddSelectionListObject con CreateSelectData().
    """
    if not append:
        model.ClearSelection2(True)

    try:
        sel_mgr = model.SelectionManager
        sel_data = com_call_0(sel_mgr, "CreateSelectData")
        if sel_data is not None:
            sel_data.Mark = int(mark)
            if bool(sel_mgr.AddSelectionListObject(entity_obj, sel_data)):
                return True
    except Exception:
        pass

    # Fallback en caso de que el objeto soporte Select2 directamente (ej. IFeature)
    try:
        return bool(entity_obj.Select2(bool(append), int(mark)))
    except Exception:
        return False


def get_last_solid_feature_name(model: Any) -> tuple[str, str]:
    """
    Recorre el FeatureManager y devuelve (nombre, tipo) de la última operación 3D sólida
    creada (ej. Extrusion, Cut, ICE, Revolve, RevCut, etc.), ignorando carpetas, planos y croquis.
    """
    last_name = ""
    last_type = ""
    feat = com_call_0(model, "FirstFeature")
    while feat is not None:
        feat_type = str(com_call_0(feat, "GetTypeName2") or "")
        if feat_type and feat_type not in NON_SOLID_FEATURE_TYPES:
            last_name = str(com_call_0(feat, "Name") or "")
            last_type = feat_type
        feat = com_call_0(feat, "GetNextFeature")

    if not last_name:
        raise RuntimeError(
            "No se encontró una operación 3D previa en el árbol para aplicar la operación."
        )
    return last_name, last_type


def connect_to_solidworks(preferred_year: Optional[int] = None) -> Any:
    """
    Conecta con la instancia activa de SOLIDWORKS (2017–2026+) o la inicia si no está abierta.
    - Prioriza la instancia ya abierta en la sesión del usuario (GetActiveObject).
    - Si preferred_year se indica (ej. 2024), prioriza SldWorks.Application.<major>.
    - Si el ProgID genérico falla, prueba los ProgIDs versionados instalados en el Registro.
    - Detecta automáticamente versión, idioma y carga swconst.tlb de la instalación activa.
    """
    global _ACTIVE_VERSION_INFO, _ACTIVE_ADAPTER, _ACTIVE_CONSTANTS

    if sys.platform != "win32":
        raise RuntimeError(
            "La conexión COM en vivo con SOLIDWORKS solo está disponible en Windows."
        )

    pythoncom.CoInitialize()

    installed_versions = list_installed_solidworks_versions()
    prog_ids: list[str] = []
    if preferred_year is not None:
        pref_major = year_to_major(preferred_year)
        if pref_major > 0:
            prog_ids.append(f"SldWorks.Application.{pref_major}")
    if "SldWorks.Application" not in prog_ids:
        prog_ids.append("SldWorks.Application")
    for _, _, ver_prog_id in installed_versions:
        if ver_prog_id not in prog_ids:
            prog_ids.append(ver_prog_id)

    sw_app = None
    used_prog_id = "SldWorks.Application"
    last_exc: Optional[Exception] = None

    # 1. Intentar engancharse primero a cualquier instancia ya abierta (ROT)
    for pid in prog_ids:
        try:
            sw_app = win32com.client.GetActiveObject(pid)
            used_prog_id = pid
            break
        except Exception as exc:
            last_exc = exc

    # 2. Si no había ninguna abierta, lanzar SOLIDWORKS vía Dispatch
    if sw_app is None:
        for pid in prog_ids:
            try:
                sw_app = win32com.client.Dispatch(pid)
                used_prog_id = pid
                break
            except Exception as exc:
                last_exc = exc

    if sw_app is None:
        hint = diagnose_com_connection_error(last_exc) if last_exc is not None else ""
        installed_str = (
            ", ".join(f"SW {y} ({p})" for y, _, p in installed_versions)
            if installed_versions
            else "ninguna detectada en HKCR"
        )
        raise RuntimeError(
            f"No se pudo conectar con SOLIDWORKS ({used_prog_id}). {hint} "
            f"[Versiones registradas: {installed_str}] [Detalle COM: {last_exc}]"
        ) from last_exc

    try:
        sw_app.Visible = True
    except Exception:
        pass

    version_info = detect_solidworks_version(sw_app, prog_id=used_prog_id)
    adapter = get_version_adapter(version_info)
    consts = load_sw_constants(version_info)
    _ACTIVE_VERSION_INFO = version_info
    _ACTIVE_ADAPTER = adapter
    _ACTIVE_CONSTANTS = consts

    if not version_info.is_supported_range:
        print(
            f"[AVISO] Versión detectada {version_info.display_name} es anterior al rango "
            f"garantizado ({SUPPORTED_SW_MIN_YEAR}–{SUPPORTED_SW_MAX_YEAR}). "
            "Se usarán comandos de respaldo cuando existan."
        )

    return sw_app


def _discover_dynamic_template_dirs(version_info: Optional[SolidWorksVersionInfo] = None) -> list[str]:
    """
    Descubre dinámicamente carpetas de plantillas de SOLIDWORKS en el equipo para cualquier versión
    (2017–2026+) e idioma, sin rutas hardcodeadas a un año ni disco específico.
    """
    discovered: list[str] = []

    def _add_if_dir(path: str) -> None:
        if path and os.path.isdir(path) and path not in discovered:
            discovered.append(path)

    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")

    # 1. Priorizar la carpeta ProgramData definida por el adaptador de la versión conectada
    adapter = get_version_adapter(version_info)
    if version_info and version_info.year > 0:
        if adapter.TEMPLATE_SUBDIR and adapter.YEAR == version_info.year:
            _add_if_dir(os.path.join(program_data, adapter.TEMPLATE_SUBDIR))
        _add_if_dir(
            os.path.join(program_data, "SOLIDWORKS", f"SOLIDWORKS {version_info.year}", "templates")
        )

    # 2. Escanear todas las carpetas C:\ProgramData\SOLIDWORKS\SOLIDWORKS *\templates (más reciente primero)
    pattern = os.path.join(program_data, "SOLIDWORKS", "SOLIDWORKS *", "templates")

    def _year_sort_key(folder_path: str) -> int:
        match = re.search(r"SOLIDWORKS\s+(\d{4})", folder_path, flags=re.IGNORECASE)
        return int(match.group(1)) if match else 0

    for tpl_dir in sorted(glob.glob(pattern), key=_year_sort_key, reverse=True):
        _add_if_dir(tpl_dir)

    # 3. Directorios dentro de la instalación activa obtenida de ISldWorks::GetExecutablePath
    exe_dir = version_info.executable_dir if version_info else ""
    if exe_dir and os.path.isdir(exe_dir):
        langs_to_check: list[str] = []
        if version_info and version_info.language:
            langs_to_check.append(version_info.language)
        for fallback_lang in ("english", "spanish", "portuguese-brazilian", "german", "french", "italian"):
            if fallback_lang not in langs_to_check:
                langs_to_check.append(fallback_lang)

        for lang_name in langs_to_check:
            _add_if_dir(os.path.join(exe_dir, "lang", lang_name, "Tutorial"))
            _add_if_dir(os.path.join(exe_dir, "lang", lang_name))
        _add_if_dir(os.path.join(exe_dir, "data", "templates"))

    return discovered


def resolve_valid_part_template(
    sw_app: Any,
    version_info: Optional[SolidWorksVersionInfo] = None,
    consts: Optional[SwConstants] = None,
) -> str:
    """
    Obtiene una ruta válida y existente en disco hacia una plantilla de pieza (.prtdot).
    IMPORTANTE: En instalaciones de SOLIDWORKS con interfaz en Español sobre plantillas en Inglés,
    swDefaultTemplatePart suele apuntar a 'Pieza.prtdot' (que NO existe en disco), mientras
    que el archivo real es 'Part.prtdot'. Si se llama a NewPart() o NewDocument() con una plantilla
    inexistente, SOLIDWORKS crea una pieza corrupta sin estilos de cota (puntero NULL en 0x0)
    que crashea en slduiu.dll apenas el usuario toca Cota Inteligente.
    """
    active_consts = consts or get_connected_constants()
    active_version = version_info or get_connected_version_info()
    pref_default_part = int(active_consts.swDefaultTemplatePart)
    pref_doc_templates = int(active_consts.swFileLocationsDocumentTemplates)

    search_dirs: list[str] = []

    try:
        pref_template = str(sw_app.GetUserPreferenceStringValue(pref_default_part) or "").strip()
        if pref_template:
            if os.path.isfile(pref_template):
                return pref_template
            parent_dir = os.path.dirname(pref_template)
            if parent_dir and os.path.isdir(parent_dir):
                search_dirs.append(parent_dir)
    except Exception:
        pass

    try:
        tpl_folders = str(sw_app.GetUserPreferenceStringValue(pref_doc_templates) or "")
        for folder in tpl_folders.split(";"):
            folder = folder.strip()
            if folder and os.path.isdir(folder) and folder not in search_dirs:
                search_dirs.append(folder)
    except Exception:
        pass

    for dyn_dir in _discover_dynamic_template_dirs(active_version):
        if dyn_dir not in search_dirs:
            search_dirs.append(dyn_dir)

    for directory in search_dirs:
        for name in PREFERRED_PART_TEMPLATE_NAMES:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                try:
                    sw_app.SetUserPreferenceStringValue(pref_default_part, candidate)
                except Exception:
                    pass
                return candidate

        # Si tiene otro nombre (ej. plantilla corporativa), tomar cualquier .prtdot válido del directorio
        try:
            for entry in sorted(os.listdir(directory)):
                if entry.lower().endswith(".prtdot"):
                    candidate = os.path.join(directory, entry)
                    if os.path.isfile(candidate):
                        try:
                            sw_app.SetUserPreferenceStringValue(pref_default_part, candidate)
                        except Exception:
                            pass
                        return candidate
        except Exception:
            pass

    return ""


def create_new_part(sw_app: Any) -> Any:
    """
    Crea un documento de pieza nuevo en SOLIDWORKS garantizando el uso de una
    plantilla .prtdot existente en disco (evita documentos sin estilos de acotación).
    """
    model = None

    # 1. Resolver plantilla .prtdot existente en disco y abrir con NewDocument
    template_path = resolve_valid_part_template(sw_app)
    if template_path:
        try:
            model = sw_app.NewDocument(template_path, 0, 0.0, 0.0)
        except Exception:
            model = None

    # 2. Respaldo con NewPart (con swDefaultTemplatePart ya corregido si existía plantilla)
    if model is None:
        try:
            model = com_call_0(sw_app, "NewPart")
        except Exception:
            model = None

    # 3. Verificar ActiveDoc como último respaldo
    if model is None:
        model = com_call_0(sw_app, "ActiveDoc")

    if model is None:
        ver_label = get_connected_version_info().display_name
        raise RuntimeError(
            f"No se pudo crear una pieza nueva en {ver_label}. "
            "Verifica que exista una plantilla .prtdot en Opciones -> Plantillas predeterminadas "
            "y que no haya ningún cuadro de diálogo modal abierto."
        )

    return model


def get_sketch_ui_preferences(sw_app: Any) -> tuple[bool, bool]:
    """Lee el estado actual de (swInputDimValOnCreate, swSketchInference) en SOLIDWORKS."""
    consts = get_connected_constants()
    prev_dim = True
    prev_inf = True
    try:
        prev_dim = bool(sw_app.GetUserPreferenceToggle(int(consts.swInputDimValOnCreate)))
    except Exception:
        prev_dim = True
    try:
        prev_inf = bool(sw_app.GetUserPreferenceToggle(int(consts.swSketchInference)))
    except Exception:
        prev_inf = True
    return prev_dim, prev_inf


def restore_sketch_ui_preferences(
    sw_app: Any,
    input_dim_enabled: bool,
    sketch_inference_enabled: bool,
) -> None:
    """Restaura independientemente swInputDimValOnCreate y swSketchInference a su estado previo."""
    consts = get_connected_constants()
    try:
        sw_app.SetUserPreferenceToggle(int(consts.swInputDimValOnCreate), bool(input_dim_enabled))
    except Exception:
        pass
    try:
        sw_app.SetUserPreferenceToggle(int(consts.swSketchInference), bool(sketch_inference_enabled))
    except Exception:
        pass


def set_input_dim_on_create(sw_app: Any, enabled: bool) -> bool:
    """
    Activa o desactiva temporalmente swInputDimValOnCreate y swSketchInference
    para evitar que SOLIDWORKS abra cuadros de diálogo o haga inferencias erráticas al dibujar por API.
    Devuelve el estado previo de swInputDimValOnCreate.
    """
    consts = get_connected_constants()
    prev_state = bool(sw_app.GetUserPreferenceToggle(int(consts.swInputDimValOnCreate)))
    sw_app.SetUserPreferenceToggle(int(consts.swInputDimValOnCreate), bool(enabled))
    try:
        sw_app.SetUserPreferenceToggle(int(consts.swSketchInference), bool(enabled))
    except Exception:
        pass
    return prev_state
