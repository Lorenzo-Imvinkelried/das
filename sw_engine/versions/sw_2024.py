"""Adaptador COM específico para SOLIDWORKS 2024 (Revisión v32, ProgID SldWorks.Application.32)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2024Adapter(SolidWorksVersionAdapter):
    """Perfil COM para SOLIDWORKS 2024 (v32.x)."""

    YEAR = 2024
    MAJOR = 32
    PROG_ID = "SldWorks.Application.32"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2024\templates"
    API_NOTES = "Verificado contra SOLIDWORKS 2024 API Help (FeatureExtrusion3, FeatureCut4, CreateDefinition, InsertWrapFeature2)."

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
