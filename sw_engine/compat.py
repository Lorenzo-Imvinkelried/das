"""
Capa de compatibilidad multi-versión para la API COM de SOLIDWORKS en Windows (2017–2026+).

Responsabilidades:
1. Tabla oficial de versiones y ProgIDs (SOLIDWORKS 2017 = v25 .. SOLIDWORKS 2026 = v34, y futuras).
2. Detección en tiempo de ejecución de versión, idioma y ruta de instalación (ISldWorks).
3. Carga dinámica de constantes (swconst.tlb) desde el SOLIDWORKS instalado del usuario,
   con valores verificados como respaldo (sin requerir escritura de gencache en Program Files).
4. Enrutamiento versionado de comandos COM (FeatureExtrusion3/2, FeatureCut4/3,
   CreateDefinition/FeatureCircularPattern5/4, FeatureLinearPattern5/4/3,
   FeatureFillet3/CreateDefinition/FeatureFillet, InsertFeatureChamfer/FeatureChamfer,
   InsertFeatureShell, InsertWrapFeature2/InsertWrapFeature) con fallback automático.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
import sys
from typing import Any, Callable, Optional

try:
    import pythoncom
    import win32com.client
except ImportError:  # pragma: no cover - permite inspeccionar/testear metadatos fuera de Windows
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]


# Rango oficial soportado y verificado
SUPPORTED_SW_MIN_YEAR = 2017
SUPPORTED_SW_MAX_YEAR = 2026

# GUID oficial del TypeLib de constantes de SOLIDWORKS (swconst.tlb)
SWCONST_TYPELIB_GUID = "{4687F359-55D0-4CD3-B6CF-2EB42C11F989}"

# Tabla oficial de años -> número mayor de revisión COM (fórmula SOLIDWORKS: major = year - 1992)
SW_YEAR_TO_MAJOR: dict[int, int] = {
    2013: 21,
    2014: 22,
    2015: 23,
    2016: 24,
    2017: 25,
    2018: 26,
    2019: 27,
    2020: 28,
    2021: 29,
    2022: 30,
    2023: 31,
    2024: 32,
    2025: 33,
    2026: 34,
}
SW_MAJOR_TO_YEAR: dict[int, int] = {major: year for year, major in SW_YEAR_TO_MAJOR.items()}

# Códigos HRESULT COM relevantes para diagnóstico y fallback
HRESULT_DISP_E_MEMBERNOTFOUND = -2147352573   # 0x80020003
HRESULT_DISP_E_PARAMNOTFOUND = -2147352572    # 0x80020004
HRESULT_DISP_E_TYPEMISMATCH = -2147352571     # 0x80020005
HRESULT_DISP_E_UNKNOWNNAME = -2147352570      # 0x80020006
HRESULT_DISP_E_BADPARAMCOUNT = -2147352562    # 0x8002000E
HRESULT_MK_E_UNAVAILABLE = -2147221021        # 0x800401E3 (ROT vacía / distinto nivel UAC o escritorio)
HRESULT_E_ACCESSDENIED = -2147024891          # 0x80070005 (desajuste de privilegios Administrador/Usuario)
HRESULT_CO_E_SERVER_EXEC_FAILURE = -2146959355  # 0x80080005
HRESULT_CO_E_CLASSSTRING = -2147221005        # 0x800401F3 (ProgID no registrado)

_FALLBACK_COM_HRESULTS: set[int] = {
    HRESULT_DISP_E_MEMBERNOTFOUND,
    HRESULT_DISP_E_PARAMNOTFOUND,
    HRESULT_DISP_E_TYPEMISMATCH,
    HRESULT_DISP_E_UNKNOWNNAME,
    HRESULT_DISP_E_BADPARAMCOUNT,
}


def major_to_year(major: int) -> int:
    """Convierte el número mayor de revisión COM de SOLIDWORKS a año comercial (ej. 26 -> 2018, 34 -> 2026)."""
    if major <= 0:
        return 0
    if major in SW_MAJOR_TO_YEAR:
        return SW_MAJOR_TO_YEAR[major]
    if major >= 17:
        return major + 1992
    return 0


def year_to_major(year: int) -> int:
    """Convierte un año comercial de SOLIDWORKS a su número mayor COM (ej. 2026 -> 34)."""
    if year in SW_YEAR_TO_MAJOR:
        return SW_YEAR_TO_MAJOR[year]
    if year >= 2009:
        return year - 1992
    return 0


def parse_revision_number(revision_str: str) -> tuple[int, int]:
    """
    Analiza ISldWorks::RevisionNumber (ej. '26.0.0', '32.3.0', '34.1') y devuelve (major, year).
    """
    text = str(revision_str or "").strip()
    match = re.match(r"^(\d+)", text)
    if not match:
        return 0, 0
    major = int(match.group(1))
    return major, major_to_year(major)


@dataclass(frozen=True)
class SolidWorksVersionInfo:
    """Metadatos detectados en tiempo de ejecución de la instancia conectada de SOLIDWORKS."""

    revision_str: str = ""
    major: int = 0
    year: int = 0
    language: str = ""
    executable_path: str = ""
    executable_dir: str = ""
    prog_id: str = "SldWorks.Application"

    @property
    def display_name(self) -> str:
        if self.year > 0 and self.revision_str:
            return f"SOLIDWORKS {self.year} (v{self.revision_str})"
        if self.year > 0:
            return f"SOLIDWORKS {self.year}"
        if self.revision_str:
            return f"SOLIDWORKS (v{self.revision_str})"
        return "SOLIDWORKS"

    @property
    def is_supported_range(self) -> bool:
        return self.year == 0 or self.year >= SUPPORTED_SW_MIN_YEAR

    @property
    def prefers_definition_patterns(self) -> bool:
        """
        En SOLIDWORKS 2020+ (v28+), FeatureCircularPattern5 y FeatureLinearPattern4/5 están marcados
        como obsoletos y SOLIDWORKS recomienda IFeatureManager::CreateDefinition + CreateFeature.
        """
        return self.major >= 28


@dataclass
class SwConstants:
    """
    Constantes de swconst.tlb con valores verificados como respaldo seguro.
    Al conectar a SOLIDWORKS se refrescan dinámicamente desde el swconst.tlb instalado en el equipo.
    """

    # swUserPreferenceStringValue_e
    swFileLocationsDocumentTemplates: int = 6
    swDefaultTemplatePart: int = 8

    # swUserPreferenceToggle_e
    swInputDimValOnCreate: int = 10
    swSketchInference: int = 249

    # swRefPlaneReferenceConstraints_e
    swRefPlaneReferenceConstraint_Distance: int = 8
    swRefPlaneReferenceConstraint_OptionFlip: int = 256

    # swEndConditions_e
    swEndCondBlind: int = 0
    swEndCondThroughAll: int = 1
    swEndCondMidPlane: int = 6
    swEndCondThroughAllBoth: int = 9

    # swBodyType_e
    swSolidBody: int = 0

    # swWrapSketchType_e / swWrapMethods_e
    swWrapSketchType_Emboss: int = 0
    swWrapSketchType_Engrave: int = 1
    swWrapSketchType_Scribe: int = 2
    swWrapMethods_Analytical: int = 0
    swWrapMethods_SplineSurface: int = 1

    # swDeleteSelectionOptions_e
    swDelete_Children: int = 1

    # swStandardViews_e
    swIsometricView: int = 7

    # swSketchSlotCreationType_e / swSketchSlotLengthType_e
    swSketchSlotCreationType_line: int = 0
    swSketchSlotLengthType_CenterCenter: int = 0

    # swFeatureFilletOptions_e
    swFeatureFilletPropagate: int = 1
    swFeatureFilletUniformRadius: int = 2

    # swFeatureFilletType_e / swFilletOverFlowType_e / swFeatureFilletProfileType_e
    swFeatureFilletType_Simple: int = 0
    swFilletOverFlowType_Default: int = 0
    swFeatureFilletCircular: int = 0
    swConstRadiusFillet: int = 0

    # swFeatureChamferOption_e / swChamferType_e
    swFeatureChamferKeepFeature: int = 2
    swFeatureChamferTangentPropagation: int = 4
    swChamferAngleDistance: int = 1

    # swFeatureNameID_e (para IFeatureManager::CreateDefinition)
    swFmChamfer: int = 0
    swFmFillet: int = 1
    swFmCirPattern: int = 5
    swFmLPattern: int = 6

    source: str = "defaults"


# Mapa de qué enum de swconst.tlb contiene cada atributo de SwConstants
_SWCONST_ENUM_GROUPS: dict[str, tuple[str, ...]] = {
    "swUserPreferenceStringValue_e": (
        "swFileLocationsDocumentTemplates",
        "swDefaultTemplatePart",
    ),
    "swUserPreferenceToggle_e": (
        "swInputDimValOnCreate",
        "swSketchInference",
    ),
    "swRefPlaneReferenceConstraints_e": (
        "swRefPlaneReferenceConstraint_Distance",
        "swRefPlaneReferenceConstraint_OptionFlip",
    ),
    "swEndConditions_e": (
        "swEndCondBlind",
        "swEndCondThroughAll",
        "swEndCondMidPlane",
        "swEndCondThroughAllBoth",
    ),
    "swBodyType_e": ("swSolidBody",),
    "swWrapSketchType_e": (
        "swWrapSketchType_Emboss",
        "swWrapSketchType_Engrave",
        "swWrapSketchType_Scribe",
    ),
    "swWrapMethods_e": (
        "swWrapMethods_Analytical",
        "swWrapMethods_SplineSurface",
    ),
    "swDeleteSelectionOptions_e": ("swDelete_Children",),
    "swStandardViews_e": ("swIsometricView",),
    "swSketchSlotCreationType_e": ("swSketchSlotCreationType_line",),
    "swSketchSlotLengthType_e": ("swSketchSlotLengthType_CenterCenter",),
    "swFeatureFilletOptions_e": (
        "swFeatureFilletPropagate",
        "swFeatureFilletUniformRadius",
    ),
    "swFeatureFilletType_e": ("swFeatureFilletType_Simple",),
    "swFilletOverFlowType_e": ("swFilletOverFlowType_Default",),
    "swFeatureFilletProfileType_e": ("swFeatureFilletCircular",),
    "swSimpleFilletType_e": ("swConstRadiusFillet",),
    "swFeatureChamferOption_e": (
        "swFeatureChamferKeepFeature",
        "swFeatureChamferTangentPropagation",
    ),
    "swChamferType_e": ("swChamferAngleDistance",),
    "swFeatureNameID_e": (
        "swFmChamfer",
        "swFmFillet",
        "swFmCirPattern",
        "swFmLPattern",
    ),
}

_CONSTANTS_CACHE: dict[str, SwConstants] = {}


def _safe_com_call_0(obj: Any, member_name: str) -> Any:
    """Helper local de invocación segura de métodos/propiedades COM de 0 argumentos."""
    val = getattr(obj, member_name)
    if callable(val) and not hasattr(val, "_oleobj_"):
        return val()
    return val


def get_empty_double_array_variant() -> Any:
    """Devuelve un VARIANT SAFEARRAY vacío de doubles (VT_ARRAY | VT_R8) para FeatureFillet3."""
    if win32com is not None and pythoncom is not None:
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [])
    return ()


def extract_com_hresult(exc: BaseException) -> Optional[int]:
    """Extrae el código HRESULT numérico de un pywintypes.com_error si está presente."""
    hresult = getattr(exc, "hresult", None)
    if isinstance(hresult, int):
        return hresult
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], int):
        return args[0]
    return None


def is_com_signature_error(exc: BaseException) -> bool:
    """Devuelve True si el error indica que el método COM no existe o cambió firma en esta versión."""
    if isinstance(exc, (AttributeError, TypeError)):
        return True
    hr = extract_com_hresult(exc)
    return hr in _FALLBACK_COM_HRESULTS


def diagnose_com_connection_error(exc: BaseException) -> str:
    """Genera un diagnóstico claro en español según el HRESULT COM recibido al conectar."""
    hr = extract_com_hresult(exc)
    if hr in (HRESULT_MK_E_UNAVAILABLE, HRESULT_E_ACCESSDENIED, HRESULT_CO_E_SERVER_EXEC_FAILURE):
        return (
            "Posible desajuste de permisos (UAC) o escritorio aislado: si abriste SOLIDWORKS "
            "'Como Administrador', ejecuta Sketch2Solid también como Administrador (o abre ambos "
            "como usuario normal) y asegúrate de no tener cuadros de diálogo modales abiertos."
        )
    if hr == HRESULT_CO_E_CLASSSTRING:
        return (
            "No se encontró SOLIDWORKS registrado en el Registro COM de Windows "
            "(ProgID 'SldWorks.Application'). Verifica que SOLIDWORKS 2017–2026 esté instalado."
        )
    return (
        "Asegúrate de tener SOLIDWORKS (2017–2026) instalado y abierto en tu sesión de escritorio "
        "de Windows sin cuadros de diálogo emergentes abiertos."
    )


def list_installed_solidworks_versions() -> list[tuple[int, int, str]]:
    """
    Inspecciona HKEY_CLASSES_ROOT en Windows para listar todas las versiones de SOLIDWORKS
    registradas en COM como lista ordenada de más nueva a más vieja: [(year, major, prog_id), ...].
    """
    if winreg is None or sys.platform != "win32":
        return []

    found: dict[int, tuple[int, int, str]] = {}
    # 1. Probar explícitamente el rango conocido y futuro cercano (2028..2013)
    for year in range(2028, 2012, -1):
        major = year_to_major(year)
        prog_id = f"SldWorks.Application.{major}"
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id):
                found[major] = (year, major, prog_id)
        except OSError:
            pass

    # 2. Escanear ProgIDs SldWorks.Application.<N> adicionales en HKCR por si hay versiones >2028
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as root_key:
            idx = 0
            while True:
                try:
                    subkey = winreg.EnumKey(root_key, idx)
                except OSError:
                    break
                idx += 1
                if subkey.lower().startswith("sldworks.application."):
                    suffix = subkey.rsplit(".", 1)[-1]
                    if suffix.isdigit():
                        major = int(suffix)
                        if major not in found:
                            found[major] = (major_to_year(major), major, subkey)
    except OSError:
        pass

    return sorted(found.values(), key=lambda item: item[1], reverse=True)


def detect_solidworks_version(sw_app: Any, prog_id: str = "SldWorks.Application") -> SolidWorksVersionInfo:
    """Consulta revisión, idioma y ruta ejecutable a la instancia COM conectada de SOLIDWORKS."""
    revision_str = ""
    try:
        revision_str = str(_safe_com_call_0(sw_app, "RevisionNumber") or "").strip()
    except Exception:
        revision_str = ""

    major, year = parse_revision_number(revision_str)

    language = ""
    try:
        language = str(_safe_com_call_0(sw_app, "GetCurrentLanguage") or "").strip().lower()
    except Exception:
        language = ""

    executable_path = ""
    executable_dir = ""
    try:
        raw_exe = str(_safe_com_call_0(sw_app, "GetExecutablePath") or "").strip()
        if raw_exe:
            executable_path = raw_exe
            if raw_exe.lower().endswith(".exe"):
                executable_dir = os.path.dirname(raw_exe)
            else:
                executable_dir = raw_exe.rstrip("\\/")
    except Exception:
        executable_path = ""
        executable_dir = ""

    resolved_prog_id = f"SldWorks.Application.{major}" if major > 0 else prog_id

    return SolidWorksVersionInfo(
        revision_str=revision_str,
        major=major,
        year=year,
        language=language,
        executable_path=executable_path,
        executable_dir=executable_dir,
        prog_id=resolved_prog_id,
    )


def _populate_constants_from_typelib(tlb: Any, consts: SwConstants) -> int:
    """Extrae únicamente los enums requeridos por Sketch2Solid desde un ITypeLib de swconst.tlb."""
    loaded_count = 0
    total_infos = tlb.GetTypeInfoCount()
    for idx in range(total_infos):
        type_name = tlb.GetDocumentation(idx)[0]
        wanted_members = _SWCONST_ENUM_GROUPS.get(type_name)
        if not wanted_members:
            continue
        ti = tlb.GetTypeInfo(idx)
        attr = ti.GetTypeAttr()
        wanted_set = set(wanted_members)
        for v_idx in range(attr.cVars):
            vd = ti.GetVarDesc(v_idx)
            member_name = ti.GetNames(vd.memid)[0]
            if member_name in wanted_set and isinstance(vd.value, int):
                setattr(consts, member_name, int(vd.value))
                loaded_count += 1
    return loaded_count


def load_sw_constants(version_info: Optional[SolidWorksVersionInfo] = None) -> SwConstants:
    """
    Carga dinámicamente las constantes COM desde el archivo swconst.tlb del SOLIDWORKS instalado
    (sin escribir caché de gencache en disco, seguro para instalaciones en Program Files).
    Si no se encuentra el TypeLib, devuelve los valores verificados por defecto.
    """
    if pythoncom is None:
        return SwConstants()

    tlb_path = ""
    if version_info and version_info.executable_dir:
        candidate = os.path.join(version_info.executable_dir, "swconst.tlb")
        if os.path.isfile(candidate):
            tlb_path = candidate

    cache_key = tlb_path or (f"reg:{version_info.major}" if version_info and version_info.major else "defaults")
    if cache_key in _CONSTANTS_CACHE:
        return _CONSTANTS_CACHE[cache_key]

    consts = SwConstants()

    # 1. Intentar cargar directamente el swconst.tlb de la carpeta de instalación activa
    if tlb_path:
        try:
            tlb = pythoncom.LoadTypeLib(tlb_path)
            loaded = _populate_constants_from_typelib(tlb, consts)
            if loaded > 0:
                consts.source = tlb_path
                _CONSTANTS_CACHE[cache_key] = consts
                return consts
        except Exception:
            pass

    # 2. Fallback: intentar cargar swconst.tlb desde el Registro de Windows por GUID y versión
    if version_info and version_info.major > 0:
        try:
            tlb = pythoncom.LoadRegTypeLib(SWCONST_TYPELIB_GUID, version_info.major, 0)
            loaded = _populate_constants_from_typelib(tlb, consts)
            if loaded > 0:
                consts.source = f"registry:{SWCONST_TYPELIB_GUID} v{version_info.major}.0"
                _CONSTANTS_CACHE[cache_key] = consts
                return consts
        except Exception:
            pass

    _CONSTANTS_CACHE[cache_key] = consts
    return consts


# ==============================================================================
# FACHADA DE ENRUTAMIENTO HACIA LOS ADAPTADORES POR VERSIÓN (sw_engine/versions/)
# ==============================================================================
# Cada versión (sw_2017.py .. sw_2026.py) define su propia tabla de comandos COM
# prioritarios y respaldos heredando de SolidWorksVersionAdapter.


def _resolve_adapter(version_info: Optional[SolidWorksVersionInfo]) -> Any:
    from .versions import get_version_adapter

    return get_version_adapter(version_info)


def call_extrude_boss(
    feat_mgr: Any,
    version_info: Optional[SolidWorksVersionInfo],
    sd: bool,
    end_cond_1: int,
    end_cond_2: int,
    depth_1_m: float,
    depth_2_m: float = 0.0,
    reverse_dir: bool = False,
) -> Any:
    """Delega extrusión de saliente al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).extrude_boss(
        feat_mgr=feat_mgr,
        sd=sd,
        end_cond_1=end_cond_1,
        end_cond_2=end_cond_2,
        depth_1_m=depth_1_m,
        depth_2_m=depth_2_m,
        reverse_dir=reverse_dir,
    )


def call_extrude_cut(
    feat_mgr: Any,
    version_info: Optional[SolidWorksVersionInfo],
    sd: bool,
    reverse_dir: bool,
    end_cond_1: int,
    end_cond_2: int,
    depth_1_m: float,
    depth_2_m: float = 0.0,
) -> Any:
    """Delega corte extruido al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).extrude_cut(
        feat_mgr=feat_mgr,
        sd=sd,
        reverse_dir=reverse_dir,
        end_cond_1=end_cond_1,
        end_cond_2=end_cond_2,
        depth_1_m=depth_1_m,
        depth_2_m=depth_2_m,
    )


def call_revolve(
    feat_mgr: Any,
    consts: SwConstants,
    is_cut: bool,
    angle_rad: float,
    version_info: Optional[SolidWorksVersionInfo] = None,
) -> Any:
    """Delega revolución al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).revolve(
        feat_mgr=feat_mgr,
        consts=consts,
        is_cut=is_cut,
        angle_rad=angle_rad,
    )


def call_circular_pattern(
    model: Any,
    version_info: Optional[SolidWorksVersionInfo],
    consts: SwConstants,
    prepare_selection: Callable[[], tuple[bool, bool]],
    instances: int,
    spacing_rad: float,
    geom_pattern: bool,
    equal_spacing: bool,
) -> Any:
    """Delega matriz circular al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).circular_pattern(
        model=model,
        consts=consts,
        prepare_selection=prepare_selection,
        instances=instances,
        spacing_rad=spacing_rad,
        geom_pattern=geom_pattern,
        equal_spacing=equal_spacing,
    )


def call_linear_pattern(
    model: Any,
    version_info: Optional[SolidWorksVersionInfo],
    consts: SwConstants,
    prepare_selection: Callable[[], None],
    instances_x: int,
    spacing_x_m: float,
    instances_y: int,
    spacing_y_m: float,
    geom_pattern: bool,
) -> Any:
    """Delega matriz lineal al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).linear_pattern(
        model=model,
        consts=consts,
        prepare_selection=prepare_selection,
        instances_x=instances_x,
        spacing_x_m=spacing_x_m,
        instances_y=instances_y,
        spacing_y_m=spacing_y_m,
        geom_pattern=geom_pattern,
    )


def call_fillet(
    model: Any,
    version_info: Optional[SolidWorksVersionInfo],
    consts: SwConstants,
    prepare_selection: Callable[[], None],
    radius_m: float,
    propagate: bool,
    get_last_feature_name: Callable[[Any], tuple[str, str]],
    prev_feat_name: str,
) -> Optional[str]:
    """Delega redondeo constante al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).fillet(
        model=model,
        consts=consts,
        prepare_selection=prepare_selection,
        radius_m=radius_m,
        propagate=propagate,
        get_last_feature_name=get_last_feature_name,
        prev_feat_name=prev_feat_name,
    )


def call_chamfer(
    model: Any,
    consts: SwConstants,
    prepare_selection: Callable[[], None],
    width_m: float,
    angle_rad: float,
    get_last_feature_name: Callable[[Any], tuple[str, str]],
    prev_feat_name: str,
    version_info: Optional[SolidWorksVersionInfo] = None,
) -> Optional[str]:
    """Delega chaflán al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).chamfer(
        model=model,
        consts=consts,
        prepare_selection=prepare_selection,
        width_m=width_m,
        angle_rad=angle_rad,
        get_last_feature_name=get_last_feature_name,
        prev_feat_name=prev_feat_name,
    )


def call_shell(
    model: Any,
    thickness_m: float,
    outward: bool,
    version_info: Optional[SolidWorksVersionInfo] = None,
) -> None:
    """Delega vaciado (shell) al adaptador específico de la versión conectada."""
    _resolve_adapter(version_info).shell(
        model=model,
        thickness_m=thickness_m,
        outward=outward,
    )


def call_wrap(
    feat_mgr: Any,
    version_info: Optional[SolidWorksVersionInfo],
    wrap_type: int,
    thickness_m: float,
    reverse_dir: bool,
    method: int,
    mesh_factor: int = 5,
) -> Any:
    """Delega envoltura cilíndrica (wrap) al adaptador específico de la versión conectada."""
    return _resolve_adapter(version_info).wrap(
        feat_mgr=feat_mgr,
        wrap_type=wrap_type,
        thickness_m=thickness_m,
        reverse_dir=reverse_dir,
        method=method,
        mesh_factor=mesh_factor,
    )
