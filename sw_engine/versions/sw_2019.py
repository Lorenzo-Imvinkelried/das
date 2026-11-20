"""Adaptador COM específico para SOLIDWORKS 2019 (Revisión v27, ProgID SldWorks.Application.27)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2019Adapter(SolidWorksVersionAdapter):
    """
    Perfil COM para SOLIDWORKS 2019 (v27.x):
    - Incorpora FeatureLinearPattern5 (22 params) con respaldo a Pattern4/Pattern3.
    - Mantiene FeatureFillet3 como método principal de redondeo (previo a Initialize de 2020).
    """

    YEAR = 2019
    MAJOR = 27
    PROG_ID = "SldWorks.Application.27"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2019\templates"
    API_NOTES = "Agrega soporte prioritario para FeatureLinearPattern5 (22 params)."

    EXTRUDE_BOSS_COMMANDS = ("FeatureExtrusion3", "FeatureExtrusion2")
    EXTRUDE_CUT_COMMANDS = ("FeatureCut4", "FeatureCut3")
    REVOLVE_COMMANDS = ("FeatureRevolve2",)
    CIRCULAR_PATTERN_COMMANDS = ("FeatureCircularPattern5", "FeatureCircularPattern4", "CreateDefinition")
    LINEAR_PATTERN_COMMANDS = (
        "FeatureLinearPattern5",
        "FeatureLinearPattern4",
        "FeatureLinearPattern3",
        "CreateDefinition",
    )
    FILLET_COMMANDS = ("FeatureFillet3", "FeatureFillet")
    CHAMFER_COMMANDS = ("InsertFeatureChamfer", "FeatureChamfer")
    SHELL_COMMANDS = ("InsertFeatureShell",)
    WRAP_COMMANDS = ("InsertWrapFeature2", "InsertWrapFeature")
