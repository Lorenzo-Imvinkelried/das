"""Adaptador COM específico para SOLIDWORKS 2020 (Revisión v28, ProgID SldWorks.Application.28)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2020Adapter(SolidWorksVersionAdapter):
    """
    Perfil COM para SOLIDWORKS 2020 (v28.x):
    - Introduce ISimpleFilletFeatureData2.Initialize (CreateDefinition + swFmFillet).
    - Prioriza IFeatureManager::CreateDefinition + CreateFeature para patrones circulares,
      patrones lineales y redondeos, manteniendo respaldos numerados clásicos.
    """

    YEAR = 2020
    MAJOR = 28
    PROG_ID = "SldWorks.Application.28"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2020\templates"
    API_NOTES = "Introduce ISimpleFilletFeatureData2.Initialize y transición a CreateDefinition."

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
