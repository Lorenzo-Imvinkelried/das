"""Adaptador COM específico para SOLIDWORKS 2018 (Revisión v26, ProgID SldWorks.Application.26)."""

from .base import SolidWorksVersionAdapter


class SolidWorks2018Adapter(SolidWorksVersionAdapter):
    """
    Perfil COM para SOLIDWORKS 2018 (v26.x, verificado contra sldworks.tlb v26.0):
    - Soporta FeatureExtrusion3/2, FeatureCut4/3, FeatureRevolve2, FeatureCircularPattern5/4,
      FeatureLinearPattern4/3, FeatureFillet3, InsertFeatureChamfer, InsertFeatureShell
      e InsertWrapFeature2.
    - No posee FeatureLinearPattern5 ni ISimpleFilletFeatureData2.Initialize.
    """

    YEAR = 2018
    MAJOR = 26
    PROG_ID = "SldWorks.Application.26"
    TEMPLATE_SUBDIR = r"SOLIDWORKS\SOLIDWORKS 2018\templates"
    API_NOTES = "Verificado directamente en TypeLib local sldworks.tlb / swconst.tlb v26.0."

    EXTRUDE_BOSS_COMMANDS = ("FeatureExtrusion3", "FeatureExtrusion2")
    EXTRUDE_CUT_COMMANDS = ("FeatureCut4", "FeatureCut3")
    REVOLVE_COMMANDS = ("FeatureRevolve2",)
    CIRCULAR_PATTERN_COMMANDS = ("FeatureCircularPattern5", "FeatureCircularPattern4", "CreateDefinition")
    LINEAR_PATTERN_COMMANDS = ("FeatureLinearPattern4", "FeatureLinearPattern3", "CreateDefinition")
    FILLET_COMMANDS = ("FeatureFillet3", "FeatureFillet")
    CHAMFER_COMMANDS = ("InsertFeatureChamfer", "FeatureChamfer")
    SHELL_COMMANDS = ("InsertFeatureShell",)
    WRAP_COMMANDS = ("InsertWrapFeature2", "InsertWrapFeature")
