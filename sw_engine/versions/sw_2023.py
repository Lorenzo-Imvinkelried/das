"""Adaptador COM específico para SOLIDWORKS 2023 (Revisión v31, ProgID SldWorks.Application.31)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2023Adapter(SolidWorksVersionAdapter):
    """Perfil COM para SOLIDWORKS 2023 (v31.x)."""

    YEAR = 2023
    MAJOR = 31
    PROG_ID = "SldWorks.Application.31"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2023\templates"
    API_NOTES = "Prioriza CreateDefinition + CreateFeature para patrones y redondeos con respaldo completo."

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
