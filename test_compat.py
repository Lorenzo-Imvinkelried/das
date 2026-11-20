"""
Suite de verificación offline de compatibilidad multi-versión SOLIDWORKS 2017–2026+
y preparación para empaquetado/instalador en Windows.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main as app_main
from sw_engine import compat, connection
from sw_engine.versions import VERSION_ADAPTERS, get_version_adapter


class _FakeComError(Exception):
    def __init__(self, hresult: int, message: str = "COM error") -> None:
        super().__init__(hresult, message)
        self.hresult = hresult


class _DummyData:
    def __init__(self, with_initialize: bool = True) -> None:
        self.props: dict[str, object] = {}
        self.initialized_with: list[int] = []
        self._with_initialize = with_initialize

    def Initialize(self, fillet_type: int) -> None:
        if not self._with_initialize:
            raise _FakeComError(compat.HRESULT_DISP_E_MEMBERNOTFOUND, "No Initialize in SW 2018")
        self.initialized_with.append(fillet_type)

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("props", "initialized_with", "_with_initialize"):
            super().__setattr__(name, value)
        else:
            self.props[name] = value


class _MockFeatureManager:
    def __init__(self, supported_methods: set[str], return_none_for: set[str] | None = None) -> None:
        self.supported = supported_methods
        self.return_none_for = return_none_for or set()
        self.calls: list[tuple[str, int]] = []
        self.last_def_data: _DummyData | None = None

    def _dispatch(self, name: str, *args: object) -> object:
        self.calls.append((name, len(args)))
        if name not in self.supported:
            raise _FakeComError(compat.HRESULT_DISP_E_MEMBERNOTFOUND, f"{name} missing")
        if name in self.return_none_for:
            return None
        return f"OK:{name}:{len(args)}"

    def FeatureExtrusion3(self, *args: object) -> object:
        return self._dispatch("FeatureExtrusion3", *args)

    def FeatureExtrusion2(self, *args: object) -> object:
        return self._dispatch("FeatureExtrusion2", *args)

    def FeatureCut4(self, *args: object) -> object:
        return self._dispatch("FeatureCut4", *args)

    def FeatureCut3(self, *args: object) -> object:
        return self._dispatch("FeatureCut3", *args)

    def FeatureRevolve2(self, *args: object) -> object:
        return self._dispatch("FeatureRevolve2", *args)

    def FeatureCircularPattern5(self, *args: object) -> object:
        return self._dispatch("FeatureCircularPattern5", *args)

    def FeatureCircularPattern4(self, *args: object) -> object:
        return self._dispatch("FeatureCircularPattern4", *args)

    def FeatureLinearPattern5(self, *args: object) -> object:
        return self._dispatch("FeatureLinearPattern5", *args)

    def FeatureLinearPattern4(self, *args: object) -> object:
        return self._dispatch("FeatureLinearPattern4", *args)

    def FeatureLinearPattern3(self, *args: object) -> object:
        return self._dispatch("FeatureLinearPattern3", *args)

    def FeatureFillet3(self, *args: object) -> object:
        return self._dispatch("FeatureFillet3", *args)

    def InsertFeatureChamfer(self, *args: object) -> object:
        return self._dispatch("InsertFeatureChamfer", *args)

    def InsertWrapFeature2(self, *args: object) -> object:
        return self._dispatch("InsertWrapFeature2", *args)

    def InsertWrapFeature(self, *args: object) -> object:
        return self._dispatch("InsertWrapFeature", *args)

    def CreateDefinition(self, feat_type_id: int) -> object:
        self.calls.append(("CreateDefinition", feat_type_id))
        if "CreateDefinition" not in self.supported:
            raise _FakeComError(compat.HRESULT_DISP_E_MEMBERNOTFOUND, "CreateDefinition missing")
        if "CreateDefinition" in self.return_none_for:
            return None
        self.last_def_data = _DummyData(with_initialize=True)
        return self.last_def_data

    def CreateFeature(self, feat_data: object) -> object:
        self.calls.append(("CreateFeature", 1))
        if "CreateFeature" in self.return_none_for:
            return None
        return "OK:CreateFeature"


class _MockModel:
    def __init__(self, feat_mgr: _MockFeatureManager) -> None:
        self.FeatureManager = feat_mgr
        self.legacy_calls: list[tuple[str, int]] = []
        self.current_feat_name = "Boss-Extrude1"

    def FeatureFillet(self, *args: object) -> None:
        self.legacy_calls.append(("FeatureFillet", len(args)))
        self.current_feat_name = "Fillet1"

    def FeatureChamfer(self, *args: object) -> None:
        self.legacy_calls.append(("FeatureChamfer", len(args)))
        self.current_feat_name = "Chamfer1"

    def InsertFeatureShell(self, *args: object) -> None:
        self.legacy_calls.append(("InsertFeatureShell", len(args)))
        self.current_feat_name = "Shell1"


class TestSolidWorksCompat(unittest.TestCase):
    def test_version_mapping_2017_to_2027(self) -> None:
        expected = {
            2017: 25,
            2018: 26,
            2019: 27,
            2020: 28,
            2021: 29,
            2022: 30,
            2023: 31,
            2024: 32,
            2025: 33,
            2026: 34,
            2027: 35,
        }
        for year, major in expected.items():
            self.assertEqual(compat.year_to_major(year), major)
            self.assertEqual(compat.major_to_year(major), year)
            parsed_major, parsed_year = compat.parse_revision_number(f"{major}.2.0")
            self.assertEqual((parsed_major, parsed_year), (major, year))

    def test_local_swconst_typelib_loading(self) -> None:
        local_dir = r"D:\SW\SOLIDWORKS"
        if not os.path.isfile(os.path.join(local_dir, "swconst.tlb")):
            self.skipTest("swconst.tlb local no presente en este entorno")

        compat._CONSTANTS_CACHE.clear()
        vinfo = compat.SolidWorksVersionInfo(
            revision_str="26.0.0",
            major=26,
            year=2018,
            language="spanish",
            executable_dir=local_dir,
        )
        consts = compat.load_sw_constants(vinfo)
        self.assertTrue(consts.source.endswith("swconst.tlb"))
        self.assertEqual(consts.swDefaultTemplatePart, 8)
        self.assertEqual(consts.swFileLocationsDocumentTemplates, 6)
        self.assertEqual(consts.swInputDimValOnCreate, 10)
        self.assertEqual(consts.swSketchInference, 249)
        self.assertEqual(consts.swFmFillet, 1)
        self.assertEqual(consts.swFmCirPattern, 5)
        self.assertEqual(consts.swFmLPattern, 6)
        self.assertEqual(consts.swChamferAngleDistance, 1)
        self.assertEqual(consts.swFeatureChamferKeepFeature, 2)
        self.assertEqual(consts.swWrapMethods_SplineSurface, 1)

    def test_extrude_boss_and_cut_across_versions(self) -> None:
        sw2017 = compat.SolidWorksVersionInfo(revision_str="25.0", major=25, year=2017)
        sw2026 = compat.SolidWorksVersionInfo(revision_str="34.0", major=34, year=2026)

        # SW 2026 usa FeatureExtrusion3 (23 args) y FeatureCut4 (27 args)
        fm_modern = _MockFeatureManager({"FeatureExtrusion3", "FeatureCut4"})
        self.assertEqual(
            compat.call_extrude_boss(fm_modern, sw2026, True, 0, 0, 0.02),
            "OK:FeatureExtrusion3:23",
        )
        self.assertEqual(
            compat.call_extrude_cut(fm_modern, sw2026, True, True, 1, 0, 0.02),
            "OK:FeatureCut4:27",
        )

        # Fallback automático a FeatureExtrusion2 (23 args) y FeatureCut3 (26 args)
        fm_fallback = _MockFeatureManager({"FeatureExtrusion2", "FeatureCut3"})
        self.assertEqual(
            compat.call_extrude_boss(fm_fallback, sw2017, True, 0, 0, 0.02),
            "OK:FeatureExtrusion2:23",
        )
        self.assertEqual(
            compat.call_extrude_cut(fm_fallback, sw2017, True, True, 1, 0, 0.02),
            "OK:FeatureCut3:26",
        )

    def test_patterns_routing_2018_vs_2024_2026(self) -> None:
        consts = compat.SwConstants()
        sw2018 = compat.SolidWorksVersionInfo(revision_str="26.0", major=26, year=2018)
        sw2025 = compat.SolidWorksVersionInfo(revision_str="33.0", major=33, year=2025)

        # SW 2018 prioriza FeatureCircularPattern5 (14 args) y FeatureLinearPattern4 (20 args)
        fm18 = _MockFeatureManager({"FeatureCircularPattern5", "FeatureLinearPattern4"})
        model18 = _MockModel(fm18)
        res_c18 = compat.call_circular_pattern(
            model18, sw2018, consts, lambda: (True, True), 6, 6.283185, False, True
        )
        res_l18 = compat.call_linear_pattern(
            model18, sw2018, consts, lambda: None, 3, 0.01, 2, 0.02, False
        )
        self.assertEqual(res_c18, "OK:FeatureCircularPattern5:14")
        self.assertEqual(res_l18, "OK:FeatureLinearPattern4:20")

        # SW 2025/2026 prioriza CreateDefinition + CreateFeature
        fm25 = _MockFeatureManager({"CreateDefinition", "CreateFeature"})
        model25 = _MockModel(fm25)
        res_c25 = compat.call_circular_pattern(
            model25, sw2025, consts, lambda: (True, True), 4, 6.283185, True, True
        )
        self.assertEqual(res_c25, "OK:CreateFeature")
        assert fm25.last_def_data is not None
        self.assertEqual(fm25.last_def_data.props["TotalInstances"], 4)

        res_l25 = compat.call_linear_pattern(
            model25, sw2025, consts, lambda: None, 5, 0.015, 1, 0.0, False
        )
        self.assertEqual(res_l25, "OK:CreateFeature")
        self.assertEqual(fm25.last_def_data.props["D1TotalInstances"], 5)

        # Si CreateDefinition devuelve None en SW 2025, cae a FeatureLinearPattern5 (22 args)
        fm25_fb = _MockFeatureManager(
            {"CreateDefinition", "FeatureLinearPattern5"},
            return_none_for={"CreateDefinition"},
        )
        model25_fb = _MockModel(fm25_fb)
        res_l25_fb = compat.call_linear_pattern(
            model25_fb, sw2025, consts, lambda: None, 3, 0.01, 1, 0.0, False
        )
        self.assertEqual(res_l25_fb, "OK:FeatureLinearPattern5:22")

    def test_fillet_chamfer_shell_and_wrap_fallbacks(self) -> None:
        consts = compat.SwConstants()
        sw2018 = compat.SolidWorksVersionInfo(revision_str="26.0", major=26, year=2018)
        sw2026 = compat.SolidWorksVersionInfo(revision_str="34.0", major=34, year=2026)

        # Fillet moderno en SW 2018: FeatureFillet3 (14 args)
        fm_f = _MockFeatureManager({"FeatureFillet3"})
        model_f = _MockModel(fm_f)

        def _get_feat(m: _MockModel) -> tuple[str, str]:
            return (m.current_feat_name, "Fillet")

        model_f.current_feat_name = "Fillet1"
        created = compat.call_fillet(
            model_f, sw2018, consts, lambda: None, 0.005, True, _get_feat, "Boss-Extrude1"
        )
        self.assertEqual(created, "Fillet1")
        self.assertEqual(fm_f.calls[0], ("FeatureFillet3", 14))

        # Fillet fallback legacy si FeatureFillet3 y CreateDefinition fallan
        fm_legacy = _MockFeatureManager(set())
        model_legacy = _MockModel(fm_legacy)
        created_legacy = compat.call_fillet(
            model_legacy, sw2026, consts, lambda: None, 0.003, False, _get_feat, "Boss-Extrude1"
        )
        self.assertEqual(created_legacy, "Fillet1")
        self.assertEqual(model_legacy.legacy_calls[0], ("FeatureFillet", 5))

        # Chamfer moderno: InsertFeatureChamfer (8 args) y fallback FeatureChamfer (3 args)
        fm_c = _MockFeatureManager({"InsertFeatureChamfer"})
        model_c = _MockModel(fm_c)
        model_c.current_feat_name = "Chamfer1"
        self.assertEqual(
            compat.call_chamfer(model_c, consts, lambda: None, 0.002, 0.7854, _get_feat, "Boss-Extrude1"),
            "Chamfer1",
        )
        self.assertEqual(fm_c.calls[0], ("InsertFeatureChamfer", 8))

        fm_c_fb = _MockFeatureManager(set())
        model_c_fb = _MockModel(fm_c_fb)
        self.assertEqual(
            compat.call_chamfer(model_c_fb, consts, lambda: None, 0.002, 0.7854, _get_feat, "Boss-Extrude1"),
            "Chamfer1",
        )
        self.assertEqual(model_c_fb.legacy_calls[0], ("FeatureChamfer", 3))

        # Wrap 2017–2026 (InsertWrapFeature2, 5 args) + fallback <=2016 (InsertWrapFeature, 3 args)
        fm_w = _MockFeatureManager({"InsertWrapFeature2"})
        self.assertEqual(compat.call_wrap(fm_w, sw2026, 1, 0.002, False, 0), "OK:InsertWrapFeature2:5")
        fm_w_old = _MockFeatureManager({"InsertWrapFeature"})
        sw2016 = compat.SolidWorksVersionInfo(revision_str="24.0", major=24, year=2016)
        self.assertEqual(compat.call_wrap(fm_w_old, sw2016, 1, 0.002, False, 0), "OK:InsertWrapFeature:3")

    def test_dynamic_template_resolution_without_hardcoded_2018(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prog_data = Path(tmp) / "ProgramData"
            tpl_2025 = prog_data / "SOLIDWORKS" / "SOLIDWORKS 2025" / "templates"
            tpl_2025.mkdir(parents=True)
            real_tpl = tpl_2025 / "Part.prtdot"
            real_tpl.write_text("dummy", encoding="utf-8")

            saved_prefs: dict[int, str] = {}

            class _FakeSwApp:
                def GetUserPreferenceStringValue(self, enum_id: int) -> str:
                    if enum_id == 8:
                        return str(tpl_2025 / "Pieza.prtdot")  # No existe en disco
                    return ""

                def SetUserPreferenceStringValue(self, enum_id: int, val: str) -> None:
                    saved_prefs[enum_id] = val

            v2025 = compat.SolidWorksVersionInfo(revision_str="33.0", major=33, year=2025, language="spanish")
            with patch.dict(os.environ, {"PROGRAMDATA": str(prog_data)}):
                resolved = connection.resolve_valid_part_template(_FakeSwApp(), version_info=v2025)
            self.assertEqual(Path(resolved), real_tpl)
            self.assertEqual(Path(saved_prefs[8]), real_tpl)

    def test_main_frozen_paths_and_reload_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(app_main, "IS_FROZEN", True), patch.dict(
                os.environ, {"LOCALAPPDATA": tmp}
            ):
                user_dir = app_main.get_user_data_dir()
                self.assertEqual(user_dir, Path(tmp) / "Sketch2Solid")
                self.assertTrue(user_dir.is_dir())
                # En modo frozen, reload_engine_modules no debe ejecutar importlib.reload
                with patch("importlib.reload") as mock_reload:
                    app_main.reload_engine_modules()
                    mock_reload.assert_not_called()

    def test_uac_error_diagnosis(self) -> None:
        msg = compat.diagnose_com_connection_error(_FakeComError(compat.HRESULT_MK_E_UNAVAILABLE))
        self.assertIn("Administrador", msg)

    def test_per_version_adapter_modules_2017_to_2026(self) -> None:
        self.assertEqual(sorted(VERSION_ADAPTERS.keys()), list(range(2017, 2027)))
        for year in range(2017, 2027):
            major = year - 1992
            vinfo = compat.SolidWorksVersionInfo(revision_str=f"{major}.0", major=major, year=year)
            adapter = get_version_adapter(vinfo)
            self.assertEqual(adapter.YEAR, year)
            self.assertEqual(adapter.MAJOR, major)
            self.assertEqual(adapter.PROG_ID, f"SldWorks.Application.{major}")
            self.assertEqual(adapter.__class__.__module__, f"sw_engine.versions.sw_{year}")
            self.assertEqual(adapter.TEMPLATE_SUBDIR, rf"SOLIDWORKS\SOLIDWORKS {year}\templates")

        # 2018 no intenta FeatureLinearPattern5 ni CreateDefinition de fillet
        self.assertNotIn("FeatureLinearPattern5", get_version_adapter(year=2018).LINEAR_PATTERN_COMMANDS)
        self.assertEqual(get_version_adapter(year=2018).FILLET_COMMANDS[0], "FeatureFillet3")
        # 2019 incorpora FeatureLinearPattern5
        self.assertEqual(get_version_adapter(year=2019).LINEAR_PATTERN_COMMANDS[0], "FeatureLinearPattern5")
        # 2020..2026 priorizan CreateDefinition en patrones y redondeos
        for year in range(2020, 2027):
            ad = get_version_adapter(year=year)
            self.assertEqual(ad.CIRCULAR_PATTERN_COMMANDS[0], "CreateDefinition")
            self.assertEqual(ad.LINEAR_PATTERN_COMMANDS[0], "CreateDefinition")
            self.assertEqual(ad.FILLET_COMMANDS[0], "CreateDefinition")
        # Futura versión 2027 cae al adaptador más nuevo (2026) y 2016 al respaldo legacy
        self.assertEqual(get_version_adapter(year=2027).YEAR, 2026)
        self.assertEqual(get_version_adapter(year=2016).WRAP_COMMANDS, ("InsertWrapFeature",))


if __name__ == "__main__":
    unittest.main()
