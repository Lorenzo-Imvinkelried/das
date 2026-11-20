"""Adaptador COM específico para SOLIDWORKS 2026 (Revisión v34, ProgID SldWorks.Application.34)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2026Adapter(SolidWorksVersionAdapter):
    """Perfil COM para SOLIDWORKS 2026 (v34.x) y base de respaldo para versiones futuras >2026."""

    YEAR = 2026
    MAJOR = 34
    PROG_ID = "SldWorks.Application.34"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2026\templates"
    API_NOTES = "Verificado contra SOLIDWORKS 2026 API Help (FeatureExtrusion3, FeatureCut4, CreateDefinition, InsertFeatureChamfer, InsertWrapFeature2)."

    EXTRUDE_BOSS_COMMANDS = ("FeatureExtrusion3", "FeatureExtrusion2")
    EXTRUDE_CUT_COMMANDS = ("FeatureCut4", "FeatureCut3")
    REVOLVE_COMMANDS = ("FeatureRevolve2",)
    CIRCULAR_PATTERN_COMMANDS = ("CreateDefinition", "FeatureCircularPattern5", "FeatureCircularPattern4")
    LINEAR_PATTERN_COMMANDS = (
        "CreateDefinition",
        "FeatureLinearPattern5",
        "FeatureLinearPattern4",
        "FeatureLinearPattern3",
    )
    FILLET_COMMANDS = ("CreateDefinition", "FeatureFillet3", "FeatureFillet")
    CHAMFER_COMMANDS = ("InsertFeatureChamfer", "FeatureChamfer")
    SHELL_COMMANDS = ("InsertFeatureShell",)
    WRAP_COMMANDS = ("InsertWrapFeature2", "InsertWrapFeature")
