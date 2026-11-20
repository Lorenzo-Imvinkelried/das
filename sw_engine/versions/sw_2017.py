"""Adaptador COM específico para SOLIDWORKS 2017 (Revisión v25, ProgID SldWorks.Application.25)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2017Adapter(SolidWorksVersionAdapter):
    """
    Perfil COM para SOLIDWORKS 2017 (v25.x):
    - Primera versión con FeatureCut4 (27 params), FeatureCircularPattern5 (14 params)
      e InsertWrapFeature2 (5 params, Analytical + SplineSurface).
    - No posee ISimpleFilletFeatureData2.Initialize (introducido en 2020), por lo que
      usa FeatureFillet3 -> IModelDoc2.FeatureFillet.
    """

    YEAR = 2017
    MAJOR = 25
    PROG_ID = "SldWorks.Application.25"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2017\templates"
    API_NOTES = "Introduce FeatureCut4, FeatureCircularPattern5 e InsertWrapFeature2."

    EXTRUDE_BOSS_COMMANDS = ("FeatureExtrusion3", "FeatureExtrusion2")
    EXTRUDE_CUT_COMMANDS = ("FeatureCut4", "FeatureCut3")
    REVOLVE_COMMANDS = ("FeatureRevolve2",)
    CIRCULAR_PATTERN_COMMANDS = ("FeatureCircularPattern5", "FeatureCircularPattern4", "CreateDefinition")
    LINEAR_PATTERN_COMMANDS = ("FeatureLinearPattern4", "FeatureLinearPattern3", "CreateDefinition")
    FILLET_COMMANDS = ("FeatureFillet3", "FeatureFillet")
    CHAMFER_COMMANDS = ("InsertFeatureChamfer", "FeatureChamfer")
    SHELL_COMMANDS = ("InsertFeatureShell",)
    WRAP_COMMANDS = ("InsertWrapFeature2", "InsertWrapFeature")
