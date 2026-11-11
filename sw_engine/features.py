import math
from typing import Any, Union
from schemas.cad_schema import (
    CADPart,
    CircularPatternOperation,
    ExtrudeBossOperation,
    ExtrudeCutOperation,
    LinearPatternOperation,
    OperationType,
    RevolveBossOperation,
    RevolveCutOperation,
)
from .connection import (
    com_call_0,
    connect_to_solidworks,
    create_new_part,
    create_reference_axis,
    get_last_solid_feature_name,
    mm_to_m,
    select_by_id,
    set_input_dim_on_create,
)
from .primitives import build_sketch_on_plane

# Constantes de condición final de extrusión (swEndConditions_e)
SW_END_COND_BLIND = 0        # Hasta profundidad especificada
SW_END_COND_THROUGH_ALL = 1  # Por todo
SW_END_COND_MID_PLANE = 6    # Plano medio

# Vista estándar Isométrica (swStandardViews_e.swIsometricView)
SW_VIEW_ISOMETRIC = 7


def execute_extrude_boss(model: Any, op: ExtrudeBossOperation) -> Any:
    """
    Ejecuta una operación de extrusión de saliente/base (FeatureExtrusion2)
    con los 23 parámetros exactos requeridos por SolidWorks 2018.
    Soporta planos desfasados (plane_offset_mm) y extrusión simétrica (midplane / both_directions).
    """
    sketch_name = build_sketch_on_plane(
        model,
        op.plane,
        op.sketch,
        plane_offset_mm=op.plane_offset_mm,
    )

    depth_m = mm_to_m(op.depth_mm)
    use_midplane = bool(op.midplane or op.both_directions)
    end_cond_1 = SW_END_COND_MID_PLANE if use_midplane else SW_END_COND_BLIND
    single_dir = not use_midplane

    feat_mgr = model.FeatureManager
    feat = feat_mgr.FeatureExtrusion2(
        bool(single_dir),  # 1. Sd: True = una dirección, False = plano medio / dos direcciones
        False,             # 2. Flip: invertir lado a cortar
        False,             # 3. Dir: invertir dirección de extrusión
        int(end_cond_1),   # 4. T1: condición final dirección 1
        0,                 # 5. T2: condición final dirección 2
        float(depth_m),    # 6. D1: profundidad dirección 1 (metros)
        0.0,               # 7. D2: profundidad dirección 2 (metros)
        False,             # 8. Dchk1: ángulo de salida dir 1
        False,             # 9. Dchk2: ángulo de salida dir 2
        False,             # 10. Ddir1: ángulo de salida hacia adentro dir 1
        False,             # 11. Ddir2: ángulo de salida hacia adentro dir 2
        0.0,               # 12. Dang1: ángulo de salida 1 (radianes)
        0.0,               # 13. Dang2: ángulo de salida 2 (radianes)
        False,             # 14. OffsetReverse1
        False,             # 15. OffsetReverse2
        False,             # 16. TranslateSurface1
        False,             # 17. TranslateSurface2
        True,              # 18. Merge: fusionar resultado
        False,             # 19. UseFeatScope: afectar a todos los sólidos
        True,              # 20. UseAutoSelect: selección automática de sólidos
        0,                 # 21. T0: condición inicial (0 = swStartSketchPlane)
        0.0,               # 22. StartOffset (metros)
        False,             # 23. FlipStartOffset
    )

    if feat is None:
        raise RuntimeError(
            f"Falló FeatureExtrusion2 para el croquis '{sketch_name}' en el plano '{op.plane}'."
        )

    model.ClearSelection2(True)
    return feat


def _call_feature_cut3(
    feat_mgr: Any,
    sd: bool,
    reverse_dir: bool,
    end_cond_1: int,
    end_cond_2: int,
    depth_1_m: float,
    depth_2_m: float = 0.0,
) -> Any:
    """Invoca FeatureCut3 con los 26 parámetros exactos de SolidWorks 2018."""
    return feat_mgr.FeatureCut3(
        bool(sd),            # 1. Sd: True = una dirección, False = dos direcciones
        False,               # 2. Flip: invertir lado a cortar
        bool(reverse_dir),   # 3. Dir: invertir dirección del corte
        int(end_cond_1),     # 4. T1: condición final dirección 1
        int(end_cond_2),     # 5. T2: condición final dirección 2
        float(depth_1_m),    # 6. D1: profundidad dirección 1 (metros)
        float(depth_2_m),    # 7. D2: profundidad dirección 2 (metros)
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
        False,               # 18. NormalCut (corte normal de chapa metálica)
        False,               # 19. UseFeatScope
        True,                # 20. UseAutoSelect
        False,               # 21. AssemblyFeatureScope
        False,               # 22. AutoSelectComponents
        False,               # 23. PropagateFeatureToParts
        0,                   # 24. T0 (0 = swStartSketchPlane)
        0.0,                 # 25. StartOffset (metros)
        False,               # 26. FlipStartOffset
    )


def execute_extrude_cut(model: Any, op: ExtrudeCutOperation) -> Any:
    """
    Ejecuta una operación de corte extruido (FeatureCut3) en SolidWorks 2018.
    - Soporta planos paralelos desfasados (plane_offset_mm).
    - Si both_directions=True, corta hacia ambos lados desde el plano del croquis
      (Sd=False, T1/T2=ThroughAll o Blind).
    - Si both_directions=False, prueba ambas orientaciones normales y hace fallback a Sd=False.
    """
    sketch_name = build_sketch_on_plane(
        model,
        op.plane,
        op.sketch,
        plane_offset_mm=op.plane_offset_mm,
    )

    end_cond_1 = SW_END_COND_THROUGH_ALL if op.through_all else SW_END_COND_BLIND
    depth_m = mm_to_m(op.depth_mm) if op.depth_mm is not None else 0.01

    feat_mgr = model.FeatureManager
    feat = None

    # 1. Si both_directions=True, cortar hacia ambos lados (Sd=False, T2=end_cond_1) primero
    if op.both_directions:
        feat = _call_feature_cut3(
            feat_mgr=feat_mgr,
            sd=False,
            reverse_dir=False,
            end_cond_1=end_cond_1,
            end_cond_2=end_cond_1,
            depth_1_m=depth_m,
            depth_2_m=depth_m,
        )
        if feat is None and sketch_name:
            select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)

    # 2. Intentar en dirección +Normal (Dir=True)
    if feat is None:
        feat = _call_feature_cut3(
            feat_mgr=feat_mgr,
            sd=True,
            reverse_dir=True,
            end_cond_1=end_cond_1,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m,
        )

    # 3. Si devuelve None, probar en la dirección opuesta (Dir=False)
    if feat is None and sketch_name:
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
        feat = _call_feature_cut3(
            feat_mgr=feat_mgr,
            sd=True,
            reverse_dir=False,
            end_cond_1=end_cond_1,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m,
        )

    # 4. Si es pasante (through_all) y aún no cortó, cortar hacia ambos lados (Sd=False)
    if feat is None and op.through_all and not op.both_directions and sketch_name:
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
        feat = _call_feature_cut3(
            feat_mgr=feat_mgr,
            sd=False,
            reverse_dir=False,
            end_cond_1=SW_END_COND_THROUGH_ALL,
            end_cond_2=SW_END_COND_THROUGH_ALL,
            depth_1_m=depth_m,
            depth_2_m=depth_m,
        )

    if feat is None:
        raise RuntimeError(
            f"Falló FeatureCut3 para el croquis '{sketch_name}' en el plano '{op.plane}'."
        )

    model.ClearSelection2(True)
    return feat


def execute_revolve(
    model: Any,
    op: Union[RevolveBossOperation, RevolveCutOperation],
    is_cut: bool = False,
) -> Any:
    """
    Ejecuta una operación de revolución (saliente o corte) mediante FeatureRevolve2
    con los 20 parámetros exactos de SolidWorks 2018.
    Dibuja automáticamente el perfil y la línea constructiva (axis_line) en el croquis.
    """
    sketch_name = build_sketch_on_plane(
        model,
        op.plane,
        op.sketch,
        plane_offset_mm=op.plane_offset_mm,
        axis_line=op.axis_line,
    )

    angle_rad = math.radians(float(op.angle_deg))
    feat_mgr = model.FeatureManager

    feat = feat_mgr.FeatureRevolve2(
        True,              # 1. SingleDir
        True,              # 2. IsSolid
        False,             # 3. IsThin
        bool(is_cut),      # 4. IsCut (False = saliente, True = corte)
        False,             # 5. ReverseDir
        False,             # 6. BothDirectionUpToSameEntity
        SW_END_COND_BLIND, # 7. Dir1Type (0 = swEndCondBlind)
        0,                 # 8. Dir2Type
        float(angle_rad),  # 9. Dir1Angle (radianes)
        0.0,               # 10. Dir2Angle
        False,             # 11. OffsetReverse1
        False,             # 12. OffsetReverse2
        0.0,               # 13. OffsetDistance1
        0.0,               # 14. OffsetDistance2
        0,                 # 15. ThinType
        0.0,               # 16. ThinThickness1
        0.0,               # 17. ThinThickness2
        True,              # 18. Merge
        False,             # 19. UseFeatScope
        True,              # 20. UseAutoSelect
    )

    if feat is None:
        raise RuntimeError(
            f"Falló FeatureRevolve2 ({'corte' if is_cut else 'saliente'}) "
            f"para el croquis '{sketch_name}' en el plano '{op.plane}'."
        )

    model.ClearSelection2(True)
    return feat


def execute_circular_pattern(model: Any, op: CircularPatternOperation) -> Any:
    """
    Ejecuta una matriz circular (FeatureCircularPattern4) sobre la última operación 3D creada:
    1. Identifica la última operación 3D sólida en el árbol del FeatureManager.
    2. Crea un eje de referencia (InsertAxis2) en la intersección de dos planos base según op.axis.
    3. Selecciona la operación con Mark=4 ('BODYFEATURE') y el eje con Mark=1 ('AXIS').
    4. Ejecuta FeatureCircularPattern4 con los 7 parámetros de SolidWorks 2018.
    """
    target_feat_name, _ = get_last_solid_feature_name(model)
    axis_name = create_reference_axis(model, op.axis)

    angle_rad = math.radians(float(op.angle_deg))
    feat_mgr = model.FeatureManager

    def _try_circular_pattern(geom_pattern: bool) -> Any:
        model.ClearSelection2(True)
        select_by_id(model, target_feat_name, "BODYFEATURE", 0.0, 0.0, 0.0, append=False, mark=4)
        select_by_id(model, axis_name, "AXIS", 0.0, 0.0, 0.0, append=True, mark=1)
        return feat_mgr.FeatureCircularPattern4(
            int(op.instances),       # 1. Number
            float(angle_rad),        # 2. Spacing (radianes)
            False,                   # 3. FlipDirection
            "NULL",                  # 4. DName
            bool(geom_pattern),      # 5. GeometryPattern
            bool(op.equal_spacing),  # 6. EqualSpacing
            False,                   # 7. VaryInstance
        )

    feat = _try_circular_pattern(geom_pattern=False)
    if feat is None:
        feat = _try_circular_pattern(geom_pattern=True)

    if feat is None:
        raise RuntimeError(
            f"Falló FeatureCircularPattern4 sobre la operación '{target_feat_name}' "
            f"alrededor del eje '{op.axis}' ({axis_name})."
        )

    model.ClearSelection2(True)
    return feat


def execute_linear_pattern(model: Any, op: LinearPatternOperation) -> Any:
    """
    Ejecuta una matriz lineal (FeatureLinearPattern3) sobre la última operación 3D creada:
    1. Identifica la última operación 3D sólida en el árbol del FeatureManager.
    2. Crea eje(s) de referencia en X (Mark=1) y opcionalmente en Y (Mark=2).
    3. Selecciona la operación con Mark=4 ('BODYFEATURE') y ejecuta FeatureLinearPattern3.
    """
    target_feat_name, _ = get_last_solid_feature_name(model)
    axis_x_name = create_reference_axis(model, "X")
    axis_y_name = create_reference_axis(model, "Y") if op.instances_y > 1 else ""

    spacing_x_m = mm_to_m(op.spacing_x_mm)
    spacing_y_m = mm_to_m(op.spacing_y_mm) if op.instances_y > 1 else 0.0
    feat_mgr = model.FeatureManager

    def _try_linear_pattern(geom_pattern: bool) -> Any:
        model.ClearSelection2(True)
        select_by_id(model, target_feat_name, "BODYFEATURE", 0.0, 0.0, 0.0, append=False, mark=4)
        select_by_id(model, axis_x_name, "AXIS", 0.0, 0.0, 0.0, append=True, mark=1)
        if axis_y_name:
            select_by_id(model, axis_y_name, "AXIS", 0.0, 0.0, 0.0, append=True, mark=2)
        return feat_mgr.FeatureLinearPattern3(
            int(op.instances_x),  # 1. Num1
            float(spacing_x_m),   # 2. Spacing1 (metros)
            int(op.instances_y),  # 3. Num2
            float(spacing_y_m),   # 4. Spacing2 (metros)
            False,                # 5. FlipDir1
            False,                # 6. FlipDir2
            "NULL",               # 7. DName1
            "NULL",               # 8. DName2
            bool(geom_pattern),   # 9. GeometryPattern
            False,                # 10. VaryInstance
        )

    feat = _try_linear_pattern(geom_pattern=False)
    if feat is None:
        feat = _try_linear_pattern(geom_pattern=True)

    if feat is None:
        raise RuntimeError(
            f"Falló FeatureLinearPattern3 sobre la operación '{target_feat_name}'."
        )

    model.ClearSelection2(True)
    return feat


def execute_operation(model: Any, op: OperationType) -> Any:
    """Despacha una operación validada por Pydantic hacia su ejecutor de SolidWorks."""
    if isinstance(op, ExtrudeBossOperation):
        return execute_extrude_boss(model, op)
    if isinstance(op, ExtrudeCutOperation):
        return execute_extrude_cut(model, op)
    if isinstance(op, RevolveBossOperation):
        return execute_revolve(model, op, is_cut=False)
    if isinstance(op, RevolveCutOperation):
        return execute_revolve(model, op, is_cut=True)
    if isinstance(op, CircularPatternOperation):
        return execute_circular_pattern(model, op)
    if isinstance(op, LinearPatternOperation):
        return execute_linear_pattern(model, op)
    raise ValueError(f"Tipo de operación no soportada: {type(op)}")


def _format_operation_summary(op: OperationType) -> str:
    """Genera una descripción legible de la operación para la consola."""
    if isinstance(op, CircularPatternOperation):
        return f"'{op.type}' ({op.instances} instancias a {op.angle_deg}° sobre eje '{op.axis}')"
    if isinstance(op, LinearPatternOperation):
        return f"'{op.type}' ({op.instances_x}x{op.instances_y} instancias)"
    offset_info = f" (offset {op.plane_offset_mm:g} mm)" if abs(op.plane_offset_mm) > 1e-6 else ""
    return f"'{op.type}' en plano '{op.plane}'{offset_info} ({len(op.sketch.shapes)} figura(s))"


def build_part(part: CADPart) -> Any:
    """
    Orquesta la construcción completa de una pieza CADPart en SolidWorks 2018:
    - Conecta a SolidWorks 2018 y abre una pieza limpia.
    - Desactiva temporalmente swInputDimValOnCreate (enum 10) y swSketchInference (enum 249).
    - Ejecuta secuencialmente cada croquis y operación 3D.
    - Restaura las preferencias del usuario y ajusta la vista isométrica.
    """
    sw_app = connect_to_solidworks()
    model = create_new_part(sw_app)

    prev_dim_toggle = set_input_dim_on_create(sw_app, False)
    try:
        for idx, operation in enumerate(part.operations, start=1):
            print(f"  [{idx}/{len(part.operations)}] Ejecutando {_format_operation_summary(operation)}...")
            execute_operation(model, operation)
    finally:
        # Restaurar las preferencias de cota e inferencia para que la UI quede 100% normal al editar
        set_input_dim_on_create(sw_app, True if prev_dim_toggle else True)

    # Reconstruir modelo y encuadrar en vista isométrica
    com_call_0(model, "EditRebuild3")
    model.ClearSelection2(True)
    model.ShowNamedView2("*Isometric", SW_VIEW_ISOMETRIC)
    com_call_0(model, "ViewZoomtofit2")
    return model

