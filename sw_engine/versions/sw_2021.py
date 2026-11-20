"""Adaptador COM específico para SOLIDWORKS 2021 (Revisión v29, ProgID SldWorks.Application.29)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2021Adapter(SolidWorksVersionAdapter):
    """Perfil COM para SOLIDWORKS 2021 (v29.x)."""

    YEAR = 2021
    MAJOR = 29
    PROG_ID = "SldWorks.Application.29"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2021\templates"
    API_NOTES = "API moderna basada en CreateDefinition para patrones/redondeos y FeatureExtrusion3/FeatureCut4."

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
