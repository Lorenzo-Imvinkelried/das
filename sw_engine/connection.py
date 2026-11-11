import os
from typing import Any
import pythoncom
import win32com.client

# Constantes de preferencias de SolidWorks 2018 (verificadas en swconst.tlb)
SW_FILE_LOCATIONS_DOC_TEMPLATES = 6  # swUserPreferenceStringValue_e.swFileLocationsDocumentTemplates
SW_DEFAULT_TEMPLATE_PART = 8         # swUserPreferenceStringValue_e.swDefaultTemplatePart
SW_INPUT_DIM_VAL_ON_CREATE = 10      # swUserPreferenceToggle_e.swInputDimValOnCreate
SW_SKETCH_INFERENCE = 249            # swUserPreferenceToggle_e.swSketchInference

# Mapeo multilenguaje (Español -> Inglés) para planos base de SolidWorks
PLANE_NAMES_MAP: dict[str, list[str]] = {
    "Front": ["Alzado", "Front Plane", "Plano frontal"],
    "Top": ["Planta", "Top Plane", "Plano superior"],
    "Right": ["Vista lateral", "Right Plane", "Plano derecho"],
}

PLANE_INDEX_MAP: dict[str, int] = {
    "Front": 0,
    "Top": 1,
    "Right": 2,
}


def mm_to_m(value_mm: float) -> float:
    """Convierte milímetros a metros (unidad interna obligatoria de la API de SolidWorks)."""
    return float(value_mm) / 1000.0


def get_null_dispatch() -> win32com.client.VARIANT:
    """Devuelve un puntero COM IDispatch nulo seguro para SolidWorks 2018 (evita Type Mismatch)."""
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def com_call_0(obj: Any, member_name: str) -> Any:
    """
    Invoca de forma segura un método o propiedad de 0 argumentos en SolidWorks 2018 (pywin32).
    En late-binding (CDispatch), hacer getattr(obj, nombre) envía INVOKE_PROPERTYGET con 0 args,
    lo cual hace que SolidWorks ejecute el método inmediatamente y devuelva el resultado
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


def select_reference_plane(model: Any, plane: str = "Front") -> bool:
    """
    Selecciona el plano base soportando SolidWorks en Español e Inglés.
    Intenta primero el nombre en español ('Alzado', 'Planta', 'Vista lateral') y
    si devuelve False intenta con el nombre en inglés ('Front Plane', 'Top Plane', 'Right Plane').
    """
    candidates = PLANE_NAMES_MAP.get(plane, [plane])
    model.ClearSelection2(True)

    for candidate_name in candidates:
        if select_by_id(model, candidate_name, "PLANE", 0.0, 0.0, 0.0, append=False, mark=0):
            return True

    # Fallback: buscar por orden de RefPlane en el árbol del FeatureManager si la plantilla usa otros nombres
    target_idx = PLANE_INDEX_MAP.get(plane, 0)
    ref_plane_idx = 0
    feat = com_call_0(model, "FirstFeature")
    while feat is not None:
        if com_call_0(feat, "GetTypeName2") == "RefPlane":
            if ref_plane_idx == target_idx:
                feat_name = str(com_call_0(feat, "Name"))
                return select_by_id(model, feat_name, "PLANE", 0.0, 0.0, 0.0, append=False, mark=0)
            ref_plane_idx += 1
        feat = com_call_0(feat, "GetNextFeature")

    raise RuntimeError(f"No se pudo seleccionar el plano base '{plane}' (intentados: {candidates}).")


def connect_to_solidworks() -> Any:
    """Conecta con la instancia activa de SolidWorks 2018 (o la inicia si no está abierta)."""
    pythoncom.CoInitialize()
    try:
        try:
            sw_app = win32com.client.GetActiveObject("SldWorks.Application")
        except Exception:
            sw_app = win32com.client.Dispatch("SldWorks.Application")
        sw_app.Visible = True
        return sw_app
    except Exception as exc:
        raise RuntimeError(
            "No se pudo conectar con 'SldWorks.Application'. "
            f"Asegúrate de tener SolidWorks 2018 abierto en tu sesión de escritorio. Detalle COM: {exc}"
        ) from exc


def resolve_valid_part_template(sw_app: Any) -> str:
    """
    Obtiene una ruta válida y existente en disco hacia una plantilla de pieza (.prtdot).
    IMPORTANTE: En instalaciones de SolidWorks 2018 con idioma Español sobre plantillas en Inglés,
    swDefaultTemplatePart (8) suele apuntar a 'Pieza.prtdot' (que NO existe en disco), mientras
    que el archivo real es 'Part.prtdot'. Si se llama a NewPart() o NewDocument() con una plantilla
    inexistente, SolidWorks crea una pieza corrupta sin estilos de cota (puntero NULL en 0x0)
    que crashea en slduiu.dll (016A3C00) apenas el usuario toca Cota Inteligente.
    """
    search_dirs: list[str] = []

    try:
        pref_template = str(sw_app.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART) or "").strip()
        if pref_template:
            if os.path.isfile(pref_template):
                return pref_template
            parent_dir = os.path.dirname(pref_template)
            if parent_dir and os.path.isdir(parent_dir):
                search_dirs.append(parent_dir)
    except Exception:
        pass

    try:
        tpl_folders = str(sw_app.GetUserPreferenceStringValue(SW_FILE_LOCATIONS_DOC_TEMPLATES) or "")
        for folder in tpl_folders.split(";"):
            folder = folder.strip()
            if folder and os.path.isdir(folder) and folder not in search_dirs:
                search_dirs.append(folder)
    except Exception:
        pass

    fallback_dirs = [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2018\templates",
        r"D:\SW\SOLIDWORKS\lang\english\Tutorial",
    ]
    for d in fallback_dirs:
        if os.path.isdir(d) and d not in search_dirs:
            search_dirs.append(d)

    preferred_names = ["Part.prtdot", "part.prtdot", "Pieza.prtdot", "pieza.prtdot"]
    for directory in search_dirs:
        for name in preferred_names:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                try:
                    sw_app.SetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART, candidate)
                except Exception:
                    pass
                return candidate

        # Si tiene otro nombre, tomar cualquier .prtdot válido del directorio
        try:
            for entry in os.listdir(directory):
                if entry.lower().endswith(".prtdot"):
                    candidate = os.path.join(directory, entry)
                    if os.path.isfile(candidate):
                        try:
                            sw_app.SetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART, candidate)
                        except Exception:
                            pass
                        return candidate
        except Exception:
            pass

    return ""


def create_new_part(sw_app: Any) -> Any:
    """
    Crea un documento de pieza nuevo en SolidWorks 2018 garantizando el uso de una
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

    # 2. Respaldo con NewPart (ahora con swDefaultTemplatePart ya corregido si existía plantilla)
    if model is None:
        try:
            model = com_call_0(sw_app, "NewPart")
        except Exception:
            model = None

    # 3. Verificar ActiveDoc como último respaldo
    if model is None:
        model = com_call_0(sw_app, "ActiveDoc")

    if model is None:
        raise RuntimeError(
            "No se pudo crear una pieza nueva en SolidWorks 2018. "
            "Verifica que exista una plantilla .prtdot y que no haya ningún cuadro de diálogo modal abierto."
        )

    return model


def set_input_dim_on_create(sw_app: Any, enabled: bool) -> bool:
    """
    Activa o desactiva temporalmente swInputDimValOnCreate (enum 10) y swSketchInference (enum 249)
    para evitar que SolidWorks abra cuadros de diálogo o haga inferencias erráticas al dibujar por API.
    Devuelve el estado previo de swInputDimValOnCreate.
    """
    prev_state = bool(sw_app.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE))
    sw_app.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, bool(enabled))
    try:
        sw_app.SetUserPreferenceToggle(SW_SKETCH_INFERENCE, bool(enabled))
    except Exception:
        pass
    return prev_state

