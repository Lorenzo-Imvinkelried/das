"""Adaptador COM específico para SOLIDWORKS 2025 (Revisión v33, ProgID SldWorks.Application.33)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2025Adapter(SolidWorksVersionAdapter):
    """Perfil COM para SOLIDWORKS 2025 (v33.x)."""

    YEAR = 2025
    MAJOR = 33
    PROG_ID = "SldWorks.Application.33"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2025\templates"
    API_NOTES = "Verificado contra SOLIDWORKS 2025 API Help (CreateDefinition prioritario en patrones y redondeos)."

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
