"""
Registro explícito de adaptadores separados por versión de SOLIDWORKS (2017–2026).

Las importaciones son estáticas para que PyInstaller / Nuitka incluyan automáticamente
todos los módulos de versión al compilar el ejecutable sin requerir hidden-imports.
"""

from __future__ import annotations

from typing import Optional

from ..compat import SolidWorksVersionInfo
from .base import SolidWorksVersionAdapter
from .sw_2017 import SolidWorks2017Adapter
from .sw_2018 import SolidWorks2018Adapter
from .sw_2019 import SolidWorks2019Adapter
from .sw_2020 import SolidWorks2020Adapter
from .sw_2021 import SolidWorks2021Adapter
from .sw_2022 import SolidWorks2022Adapter
from .sw_2023 import SolidWorks2023Adapter
from .sw_2024 import SolidWorks2024Adapter
from .sw_2025 import SolidWorks2025Adapter
from .sw_2026 import SolidWorks2026Adapter


class _LegacyPre2017Adapter(SolidWorksVersionAdapter):
    """Respaldo automático si un usuario conecta un SOLIDWORKS anterior a 2017 (ej. 2013–2016)."""

    YEAR = 2016
    MAJOR = 24
    PROG_ID = "SldWorks.Application"
    TEMPLATE_SUBDIR = ""
    API_NOTES = "Respaldo conservador para versiones anteriores a 2017 (sin FeatureCut4 ni InsertWrapFeature2)."

    EXTRUDE_BOSS_COMMANDS = ("FeatureExtrusion3", "FeatureExtrusion2")
    EXTRUDE_CUT_COMMANDS = ("FeatureCut3",)
    REVOLVE_COMMANDS = ("FeatureRevolve2",)
    CIRCULAR_PATTERN_COMMANDS = ("FeatureCircularPattern4",)
    LINEAR_PATTERN_COMMANDS = ("FeatureLinearPattern3",)
    FILLET_COMMANDS = ("FeatureFillet3", "FeatureFillet")
    CHAMFER_COMMANDS = ("InsertFeatureChamfer", "FeatureChamfer")
    SHELL_COMMANDS = ("InsertFeatureShell",)
    WRAP_COMMANDS = ("InsertWrapFeature",)


# Registro oficial indexado por año comercial (2017..2026)
VERSION_ADAPTER_CLASSES: dict[int, type[SolidWorksVersionAdapter]] = {
    2017: SolidWorks2017Adapter,
    2018: SolidWorks2018Adapter,
    2019: SolidWorks2019Adapter,
    2020: SolidWorks2020Adapter,
    2021: SolidWorks2021Adapter,
    2022: SolidWorks2022Adapter,
    2023: SolidWorks2023Adapter,
    2024: SolidWorks2024Adapter,
    2025: SolidWorks2025Adapter,
    2026: SolidWorks2026Adapter,
}

# Instancias singleton por año
VERSION_ADAPTERS: dict[int, SolidWorksVersionAdapter] = {
    year: cls() for year, cls in VERSION_ADAPTER_CLASSES.items()
}

_LEGACY_ADAPTER = _LegacyPre2017Adapter()
_DEFAULT_ADAPTER = VERSION_ADAPTERS[2026]


def get_version_adapter(
    version_info: Optional[SolidWorksVersionInfo] = None,
    year: Optional[int] = None,
) -> SolidWorksVersionAdapter:
    """
    Devuelve el adaptador específico para la versión conectada de SOLIDWORKS:
    - 2017..2026 -> adaptador exacto (sw_2017.py .. sw_2026.py).
    - > 2026     -> SolidWorks2026Adapter (más reciente disponible).
    - 1..2016    -> _LegacyPre2017Adapter (respaldo seguro).
    - Desconocida (0 / None) -> SolidWorks2026Adapter (con cadena completa de fallbacks).
    """
    target_year = year if year is not None else (version_info.year if version_info else 0)
    if target_year in VERSION_ADAPTERS:
        return VERSION_ADAPTERS[target_year]
    if target_year > 2026:
        return VERSION_ADAPTERS[2026]
    if 0 < target_year < 2017:
        return _LEGACY_ADAPTER
    return _DEFAULT_ADAPTER


__all__ = [
    "SolidWorksVersionAdapter",
    "SolidWorks2017Adapter",
    "SolidWorks2018Adapter",
    "SolidWorks2019Adapter",
    "SolidWorks2020Adapter",
    "SolidWorks2021Adapter",
    "SolidWorks2022Adapter",
    "SolidWorks2023Adapter",
    "SolidWorks2024Adapter",
    "SolidWorks2025Adapter",
    "SolidWorks2026Adapter",
    "VERSION_ADAPTER_CLASSES",
    "VERSION_ADAPTERS",
    "get_version_adapter",
]
