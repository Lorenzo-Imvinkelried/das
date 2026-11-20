"""
Clase base para adaptadores por versión de SOLIDWORKS (2017–2026+).

Cada versión en sw_engine/versions/sw_<año>.py hereda de SolidWorksVersionAdapter,
declara su mapa exacto de comandos COM prioritarios y respaldos, y puede sobrescribir
cualquier operación si esa versión específica necesita un ajuste propio sin afectar al resto.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..compat import (
    SwConstants,
    get_empty_double_array_variant,
    is_com_signature_error,
)


class SolidWorksVersionAdapter:
    """Adaptador base con implementaciones COM verificadas para SOLIDWORKS 2017–2026+."""

    YEAR: int = 0
    MAJOR: int = 0
    PROG_ID: str = "SldWorks.Application"
    TEMPLATE_SUBDIR: str = ""
    API_NOTES: str = ""

    # Orden de comandos COM por operación (cada versión fija los suyos explícitamente)
    EXTRUDE_BOSS_COMMANDS: tuple[str, ...] = ("FeatureExtrusion3", "FeatureExtrusion2")
    EXTRUDE_CUT_COMMANDS: tuple[str, ...] = ("FeatureCut4", "FeatureCut3")
    REVOLVE_COMMANDS: tuple[str, ...] = ("FeatureRevolve2",)
    CIRCULAR_PATTERN_COMMANDS: tuple[str, ...] = (
        "FeatureCircularPattern5",
        "FeatureCircularPattern4",
        "CreateDefinition",
    )
    LINEAR_PATTERN_COMMANDS: tuple[str, ...] = (
        "FeatureLinearPattern4",
        "FeatureLinearPattern3",
        "CreateDefinition",
    )
    FILLET_COMMANDS: tuple[str, ...] = ("FeatureFillet3", "FeatureFillet")
    CHAMFER_COMMANDS: tuple[str, ...] = ("InsertFeatureChamfer", "FeatureChamfer")
    SHELL_COMMANDS: tuple[str, ...] = ("InsertFeatureShell",)
    WRAP_COMMANDS: tuple[str, ...] = ("InsertWrapFeature2", "InsertWrapFeature")

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def summary(self) -> str:
        return f"{self.name} (SOLIDWORKS {self.YEAR} / v{self.MAJOR}, ProgID={self.PROG_ID})"

    # ------------------------------------------------------------------
    # 1. EXTRUDE BOSS (FeatureExtrusion3 / FeatureExtrusion2)
    # ------------------------------------------------------------------
    def _build_extrude_boss_args(
        self,
        sd: bool,
        end_cond_1: int,
        end_cond_2: int,
        depth_1_m: float,
        depth_2_m: float,
        reverse_dir: bool,
    ) -> tuple[Any, ...]:
        return (
            bool(sd),           # 1. Sd
            False,              # 2. Flip
            bool(reverse_dir),  # 3. Dir
            int(end_cond_1),    # 4. T1
            int(end_cond_2),    # 5. T2
            float(depth_1_m),   # 6. D1 (metros)
            float(depth_2_m),   # 7. D2 (metros)
            False,              # 8. Dchk1
            False,              # 9. Dchk2
            False,              # 10. Ddir1
            False,              # 11. Ddir2
            0.0,                # 12. Dang1
            0.0,                # 13. Dang2
            False,              # 14. OffsetReverse1
            False,              # 15. OffsetReverse2
            False,              # 16. TranslateSurface1
            False,              # 17. TranslateSurface2
            True,               # 18. Merge
            False,              # 19. UseFeatScope
            True,               # 20. UseAutoSelect
            0,                  # 21. T0 (0 = swStartSketchPlane)
            0.0,                # 22. StartOffset (metros)
            False,              # 23. FlipStartOffset
        )

    def extrude_boss(
        self,
        feat_mgr: Any,
        sd: bool,
        end_cond_1: int,
        end_cond_2: int,
        depth_1_m: float,
        depth_2_m: float = 0.0,
        reverse_dir: bool = False,
    ) -> Any:
        args = self._build_extrude_boss_args(sd, end_cond_1, end_cond_2, depth_1_m, depth_2_m, reverse_dir)
        for cmd in self.EXTRUDE_BOSS_COMMANDS:
            try:
                feat = getattr(feat_mgr, cmd)(*args)
                if feat is not None:
                    return feat
            except Exception as exc:
                if not is_com_signature_error(exc):
                    raise
        return None

    # ------------------------------------------------------------------
    # 2. EXTRUDE CUT (FeatureCut4 / FeatureCut3)
    # ------------------------------------------------------------------
    def _build_extrude_cut3_args(
        self,
        sd: bool,
        reverse_dir: bool,
        end_cond_1: int,
        end_cond_2: int,
        depth_1_m: float,
        depth_2_m: float,
    ) -> tuple[Any, ...]:
        return (
            bool(sd),            # 1. Sd
            False,               # 2. Flip
            bool(reverse_dir),   # 3. Dir
            int(end_cond_1),     # 4. T1
            int(end_cond_2),     # 5. T2
            float(depth_1_m),    # 6. D1 (metros)
            float(depth_2_m),    # 7. D2 (metros)
            False,               # 8. Dchk1
            False,               # 9. Dchk2
            False,               # 10. Ddir1
            False,               # 11. Ddir2
            0.0,                 # 12. Dang1
            0.0,                 # 13. Dang2
            False,               # 14. OffsetReverse1
            False,               # 15. OffsetReverse2
            False,               # 16. TranslateSurface1
            False,               # 17. TranslateSurface2
            False,               # 18. NormalCut
            False,               # 19. UseFeatScope
            True,                # 20. UseAutoSelect
            False,               # 21. AssemblyFeatureScope
            False,               # 22. AutoSelectComponents
            False,               # 23. PropagateFeatureToParts
            0,                   # 24. T0 (0 = swStartSketchPlane)
            0.0,                 # 25. StartOffset (metros)
            False,               # 26. FlipStartOffset
        )

    def extrude_cut(
        self,
        feat_mgr: Any,
        sd: bool,
        reverse_dir: bool,
        end_cond_1: int,
        end_cond_2: int,
        depth_1_m: float,
        depth_2_m: float = 0.0,
    ) -> Any:
        cut3_args = self._build_extrude_cut3_args(sd, reverse_dir, end_cond_1, end_cond_2, depth_1_m, depth_2_m)
        args_by_cmd: dict[str, tuple[Any, ...]] = {
            "FeatureCut4": cut3_args + (False,),  # 27. OptimizeGeometry
            "FeatureCut3": cut3_args,
        }
        for cmd in self.EXTRUDE_CUT_COMMANDS:
            try:
                feat = getattr(feat_mgr, cmd)(*args_by_cmd[cmd])
                if feat is not None:
                    return feat
            except Exception as exc:
                if not is_com_signature_error(exc):
                    raise
        return None

    # ------------------------------------------------------------------
    # 3. REVOLVE (FeatureRevolve2)
    # ------------------------------------------------------------------
    def revolve(
        self,
        feat_mgr: Any,
        consts: SwConstants,
        is_cut: bool,
        angle_rad: float,
    ) -> Any:
        for cmd in self.REVOLVE_COMMANDS:
            if cmd == "FeatureRevolve2":
                return feat_mgr.FeatureRevolve2(
                    True,                        # 1. SingleDir
                    True,                        # 2. IsSolid
                    False,                       # 3. IsThin
                    bool(is_cut),                # 4. IsCut
                    False,                       # 5. ReverseDir
                    False,                       # 6. BothDirectionUpToSameEntity
                    int(consts.swEndCondBlind),  # 7. Dir1Type
                    0,                           # 8. Dir2Type
                    float(angle_rad),            # 9. Dir1Angle (radianes)
                    0.0,                         # 10. Dir2Angle
                    False,                       # 11. OffsetReverse1
                    False,                       # 12. OffsetReverse2
                    0.0,                         # 13. OffsetDistance1
                    0.0,                         # 14. OffsetDistance2
                    0,                           # 15. ThinType
                    0.0,                         # 16. ThinThickness1
                    0.0,                         # 17. ThinThickness2
                    True,                        # 18. Merge
                    False,                       # 19. UseFeatScope
                    True,                        # 20. UseAutoSelect
                )
        return None

    # ------------------------------------------------------------------
    # 4. CIRCULAR PATTERN (CreateDefinition / Pattern5 / Pattern4)
    # ------------------------------------------------------------------
    def _circular_pattern_via_definition(
        self,
        feat_mgr: Any,
        consts: SwConstants,
        instances: int,
        spacing_rad: float,
        geom_pattern: bool,
        equal_spacing: bool,
    ) -> Any:
        feat_data = feat_mgr.CreateDefinition(int(consts.swFmCirPattern))
        if feat_data is None:
            return None
        feat_data.TotalInstances = int(instances)
        feat_data.Spacing = float(spacing_rad)
        feat_data.EqualSpacing = bool(equal_spacing)
        feat_data.GeometryPattern = bool(geom_pattern)
        feat_data.ReverseDirection = False
        for attr, val in (("Direction2", False), ("VarySketch", False)):
            try:
                setattr(feat_data, attr, val)
            except Exception:
                pass
        return feat_mgr.CreateFeature(feat_data)

    def _circular_pattern_via_5(
        self,
        feat_mgr: Any,
        instances: int,
        spacing_rad: float,
        geom_pattern: bool,
        equal_spacing: bool,
    ) -> Any:
        return feat_mgr.FeatureCircularPattern5(
            int(instances),        # 1. Number
            float(spacing_rad),    # 2. Spacing (radianes)
            False,                 # 3. FlipDirection
            "NULL",                # 4. DName
            bool(geom_pattern),    # 5. GeometryPattern
            bool(equal_spacing),   # 6. EqualSpacing
            False,                 # 7. VaryInstance
            False,                 # 8. SyncSubAssemblies
            False,                 # 9. BDir2
            False,                 # 10. BSymmetric
            1,                     # 11. Number2
            0.0,                   # 12. Spacing2
            "NULL",                # 13. DName2
            False,                 # 14. EqualSpacing2
        )

    def _circular_pattern_via_4(
        self,
        feat_mgr: Any,
        instances: int,
        spacing_rad: float,
        geom_pattern: bool,
        equal_spacing: bool,
    ) -> Any:
        return feat_mgr.FeatureCircularPattern4(
            int(instances),        # 1. Number
            float(spacing_rad),    # 2. Spacing (radianes)
            False,                 # 3. FlipDirection
            "NULL",                # 4. DName
            bool(geom_pattern),    # 5. GeometryPattern
            bool(equal_spacing),   # 6. EqualSpacing
            False,                 # 7. VaryInstance
        )

    def circular_pattern(
        self,
        model: Any,
        consts: SwConstants,
        prepare_selection: Callable[[], tuple[bool, bool]],
        instances: int,
        spacing_rad: float,
        geom_pattern: bool,
        equal_spacing: bool,
    ) -> Any:
        feat_mgr = model.FeatureManager
        cmds = self.CIRCULAR_PATTERN_COMMANDS
        for idx, cmd in enumerate(cmds):
            is_last = idx == len(cmds) - 1
            try:
                prepare_selection()
                if cmd == "CreateDefinition":
                    feat = self._circular_pattern_via_definition(
                        feat_mgr, consts, instances, spacing_rad, geom_pattern, equal_spacing
                    )
                elif cmd == "FeatureCircularPattern5":
                    feat = self._circular_pattern_via_5(
                        feat_mgr, instances, spacing_rad, geom_pattern, equal_spacing
                    )
                elif cmd == "FeatureCircularPattern4":
                    feat = self._circular_pattern_via_4(
                        feat_mgr, instances, spacing_rad, geom_pattern, equal_spacing
                    )
                else:
                    feat = None
                if feat is not None:
                    return feat
            except Exception as exc:
                if not is_com_signature_error(exc) and is_last:
                    raise
        return None

    # ------------------------------------------------------------------
    # 5. LINEAR PATTERN (CreateDefinition / Pattern5 / Pattern4 / Pattern3)
    # ------------------------------------------------------------------
    def _linear_pattern_via_definition(
        self,
        feat_mgr: Any,
        consts: SwConstants,
        instances_x: int,
        spacing_x_m: float,
        instances_y: int,
        spacing_y_m: float,
        geom_pattern: bool,
    ) -> Any:
        feat_data = feat_mgr.CreateDefinition(int(consts.swFmLPattern))
        if feat_data is None:
            return None
        feat_data.D1TotalInstances = int(instances_x)
        feat_data.D1Spacing = float(spacing_x_m)
        feat_data.D1ReverseDirection = False
        feat_data.D2TotalInstances = int(instances_y)
        feat_data.D2Spacing = float(spacing_y_m)
        feat_data.D2ReverseDirection = False
        feat_data.GeometryPattern = bool(geom_pattern)
        for attr, val in (
            ("D1EndCondition", 0),
            ("D2EndCondition", 0),
            ("D2PatternSeedOnly", False),
            ("VarySketch", False),
        ):
            try:
                setattr(feat_data, attr, val)
            except Exception:
                pass
        return feat_mgr.CreateFeature(feat_data)

    def _linear_pattern_via_5(
        self,
        feat_mgr: Any,
        instances_x: int,
        spacing_x_m: float,
        instances_y: int,
        spacing_y_m: float,
        geom_pattern: bool,
    ) -> Any:
        return feat_mgr.FeatureLinearPattern5(
            int(instances_x),    # 1. Num1
            float(spacing_x_m),  # 2. Spacing1 (metros)
            int(instances_y),    # 3. Num2
            float(spacing_y_m),  # 4. Spacing2 (metros)
            False,               # 5. FlipDir1
            False,               # 6. FlipDir2
            "NULL",              # 7. DName1
            "NULL",              # 8. DName2
            bool(geom_pattern),  # 9. GeometryPattern
            False,               # 10. VaryInstance
            False,               # 11. HasOffset1
            False,               # 12. HasOffset2
            False,               # 13. CtrlByNum1
            False,               # 14. CtrlByNum2
            False,               # 15. FromCentroid1
            False,               # 16. FromCentroid2
            False,               # 17. RevOffset1
            False,               # 18. RevOffset2
            0.0,                 # 19. Offset1
            0.0,                 # 20. Offset2
            False,               # 21. D2PatternSeedOnly
            False,               # 22. SyncSubAssemblies
        )

    def _linear_pattern_via_4(
        self,
        feat_mgr: Any,
        instances_x: int,
        spacing_x_m: float,
        instances_y: int,
        spacing_y_m: float,
        geom_pattern: bool,
    ) -> Any:
        return feat_mgr.FeatureLinearPattern4(
            int(instances_x),    # 1. Num1
            float(spacing_x_m),  # 2. Spacing1 (metros)
            int(instances_y),    # 3. Num2
            float(spacing_y_m),  # 4. Spacing2 (metros)
            False,               # 5. FlipDir1
            False,               # 6. FlipDir2
            "NULL",              # 7. DName1
            "NULL",              # 8. DName2
            bool(geom_pattern),  # 9. GeometryPattern
            False,               # 10. VaryInstance
            False,               # 11. HasOffset1
            False,               # 12. HasOffset2
            False,               # 13. CtrlByNum1
            False,               # 14. CtrlByNum2
            False,               # 15. FromCentroid1
            False,               # 16. FromCentroid2
            False,               # 17. RevOffset1
            False,               # 18. RevOffset2
            0.0,                 # 19. Offset1
            0.0,                 # 20. Offset2
        )

    def _linear_pattern_via_3(
        self,
        feat_mgr: Any,
        instances_x: int,
        spacing_x_m: float,
        instances_y: int,
        spacing_y_m: float,
        geom_pattern: bool,
    ) -> Any:
        return feat_mgr.FeatureLinearPattern3(
            int(instances_x),    # 1. Num1
            float(spacing_x_m),  # 2. Spacing1 (metros)
            int(instances_y),    # 3. Num2
            float(spacing_y_m),  # 4. Spacing2 (metros)
            False,               # 5. FlipDir1
            False,               # 6. FlipDir2
            "NULL",              # 7. DName1
            "NULL",              # 8. DName2
            bool(geom_pattern),  # 9. GeometryPattern
            False,               # 10. VaryInstance
        )

    def linear_pattern(
        self,
        model: Any,
        consts: SwConstants,
        prepare_selection: Callable[[], None],
        instances_x: int,
        spacing_x_m: float,
        instances_y: int,
        spacing_y_m: float,
        geom_pattern: bool,
    ) -> Any:
        feat_mgr = model.FeatureManager
        cmds = self.LINEAR_PATTERN_COMMANDS
        for idx, cmd in enumerate(cmds):
            is_last = idx == len(cmds) - 1
            try:
                prepare_selection()
                if cmd == "CreateDefinition":
                    feat = self._linear_pattern_via_definition(
                        feat_mgr, consts, instances_x, spacing_x_m, instances_y, spacing_y_m, geom_pattern
                    )
                elif cmd == "FeatureLinearPattern5":
                    feat = self._linear_pattern_via_5(
                        feat_mgr, instances_x, spacing_x_m, instances_y, spacing_y_m, geom_pattern
                    )
                elif cmd == "FeatureLinearPattern4":
                    feat = self._linear_pattern_via_4(
                        feat_mgr, instances_x, spacing_x_m, instances_y, spacing_y_m, geom_pattern
                    )
                elif cmd == "FeatureLinearPattern3":
                    feat = self._linear_pattern_via_3(
                        feat_mgr, instances_x, spacing_x_m, instances_y, spacing_y_m, geom_pattern
                    )
                else:
                    feat = None
                if feat is not None:
                    return feat
            except Exception as exc:
                if not is_com_signature_error(exc) and is_last:
                    raise
        return None

    # ------------------------------------------------------------------
    # 6. FILLET (CreateDefinition / FeatureFillet3 / IModelDoc2.FeatureFillet)
    # ------------------------------------------------------------------
    def _fillet_via_3(
        self,
        model: Any,
        consts: SwConstants,
        radius_m: float,
        propagate: bool,
        get_last_feature_name: Callable[[Any], tuple[str, str]],
    ) -> Optional[str]:
        empty_arr = get_empty_double_array_variant()
        options = int(consts.swFeatureFilletUniformRadius)
        if propagate:
            options |= int(consts.swFeatureFilletPropagate)
        feat = model.FeatureManager.FeatureFillet3(
            options,                                   # 1. Options
            float(radius_m),                           # 2. R1
            0.0,                                       # 3. R2
            0.0,                                       # 4. Rho
            int(consts.swFeatureFilletType_Simple),    # 5. Ftyp
            int(consts.swFilletOverFlowType_Default),  # 6. OverflowType
            int(consts.swFeatureFilletCircular),       # 7. ConicRhoType
            empty_arr,                                 # 8. Radii
            empty_arr,                                 # 9. Dist2Arr
            empty_arr,                                 # 10. RhoArr
            empty_arr,                                 # 11. SetBackDistances
            empty_arr,                                 # 12. PointRadiusArray
            empty_arr,                                 # 13. PointDist2Array
            empty_arr,                                 # 14. PointRhoArray
        )
        if feat is not None:
            after_name, _ = get_last_feature_name(model)
            return after_name
        return None

    def _fillet_via_definition(
        self,
        model: Any,
        consts: SwConstants,
        radius_m: float,
        propagate: bool,
        get_last_feature_name: Callable[[Any], tuple[str, str]],
    ) -> Optional[str]:
        feat_mgr = model.FeatureManager
        feat_data = feat_mgr.CreateDefinition(int(consts.swFmFillet))
        if feat_data is None:
            return None
        try:
            feat_data.Initialize(int(consts.swConstRadiusFillet))
        except Exception:
            pass
        feat_data.DefaultRadius = float(radius_m)
        for attr, val in (
            ("PropagateToTangentFaces", bool(propagate)),
            ("OverflowType", int(consts.swFilletOverFlowType_Default)),
            ("ConicTypeForCrossSectionProfile", int(consts.swFeatureFilletCircular)),
        ):
            try:
                setattr(feat_data, attr, val)
            except Exception:
                pass
        feat = feat_mgr.CreateFeature(feat_data)
        if feat is not None:
            after_name, _ = get_last_feature_name(model)
            return after_name
        return None

    def _fillet_via_legacy(
        self,
        model: Any,
        consts: SwConstants,
        radius_m: float,
        propagate: bool,
        get_last_feature_name: Callable[[Any], tuple[str, str]],
        prev_feat_name: str,
    ) -> Optional[str]:
        model.FeatureFillet(
            float(radius_m),
            bool(propagate),
            False,
            False,
            int(consts.swFilletOverFlowType_Default),
        )
        after_name, _ = get_last_feature_name(model)
        return after_name if after_name != prev_feat_name else None

    def fillet(
        self,
        model: Any,
        consts: SwConstants,
        prepare_selection: Callable[[], None],
        radius_m: float,
        propagate: bool,
        get_last_feature_name: Callable[[Any], tuple[str, str]],
        prev_feat_name: str,
    ) -> Optional[str]:
        cmds = self.FILLET_COMMANDS
        for idx, cmd in enumerate(cmds):
            is_last = idx == len(cmds) - 1
            try:
                prepare_selection()
                if cmd == "CreateDefinition":
                    created = self._fillet_via_definition(
                        model, consts, radius_m, propagate, get_last_feature_name
                    )
                elif cmd == "FeatureFillet3":
                    created = self._fillet_via_3(
                        model, consts, radius_m, propagate, get_last_feature_name
                    )
                elif cmd == "FeatureFillet":
                    created = self._fillet_via_legacy(
                        model, consts, radius_m, propagate, get_last_feature_name, prev_feat_name
                    )
                else:
                    created = None
                if created:
                    return created
            except Exception as exc:
                if not is_com_signature_error(exc) and is_last:
                    raise
        return None

    # ------------------------------------------------------------------
    # 7. CHAMFER (IFeatureManager.InsertFeatureChamfer / IModelDoc2.FeatureChamfer)
    # ------------------------------------------------------------------
    def chamfer(
        self,
        model: Any,
        consts: SwConstants,
        prepare_selection: Callable[[], None],
        width_m: float,
        angle_rad: float,
        get_last_feature_name: Callable[[Any], tuple[str, str]],
        prev_feat_name: str,
    ) -> Optional[str]:
        cmds = self.CHAMFER_COMMANDS
        for idx, cmd in enumerate(cmds):
            is_last = idx == len(cmds) - 1
            try:
                prepare_selection()
                if cmd == "InsertFeatureChamfer":
                    feat = model.FeatureManager.InsertFeatureChamfer(
                        int(consts.swFeatureChamferKeepFeature),  # 1. Options
                        int(consts.swChamferAngleDistance),       # 2. ChamferType
                        float(width_m),                           # 3. Width (metros)
                        float(angle_rad),                         # 4. Angle (radianes)
                        0.0,                                      # 5. OtherDist
                        0.0,                                      # 6. VertexChamDist1
                        0.0,                                      # 7. VertexChamDist2
                        0.0,                                      # 8. VertexChamDist3
                    )
                    if feat is not None:
                        after_name, _ = get_last_feature_name(model)
                        return after_name
                elif cmd == "FeatureChamfer":
                    model.FeatureChamfer(float(width_m), float(angle_rad), False)
                    after_name, _ = get_last_feature_name(model)
                    if after_name != prev_feat_name:
                        return after_name
            except Exception as exc:
                if not is_com_signature_error(exc) and is_last:
                    raise
        return None

    # ------------------------------------------------------------------
    # 8. SHELL (IModelDoc2.InsertFeatureShell)
    # ------------------------------------------------------------------
    def shell(self, model: Any, thickness_m: float, outward: bool) -> None:
        for cmd in self.SHELL_COMMANDS:
            if cmd == "InsertFeatureShell":
                model.InsertFeatureShell(float(thickness_m), bool(outward))
                return

    # ------------------------------------------------------------------
    # 9. WRAP (InsertWrapFeature2 / InsertWrapFeature)
    # ------------------------------------------------------------------
    def wrap(
        self,
        feat_mgr: Any,
        wrap_type: int,
        thickness_m: float,
        reverse_dir: bool,
        method: int,
        mesh_factor: int = 5,
    ) -> Any:
        for cmd in self.WRAP_COMMANDS:
            try:
                if cmd == "InsertWrapFeature2":
                    feat = feat_mgr.InsertWrapFeature2(
                        int(wrap_type),
                        float(thickness_m),
                        bool(reverse_dir),
                        int(method),
                        int(mesh_factor),
                    )
                elif cmd == "InsertWrapFeature":
                    feat = feat_mgr.InsertWrapFeature(
                        int(wrap_type),
                        float(thickness_m),
                        bool(reverse_dir),
                    )
                else:
                    feat = None
                if feat is not None:
                    return feat
            except Exception as exc:
                if not is_com_signature_error(exc):
                    raise
        return None
