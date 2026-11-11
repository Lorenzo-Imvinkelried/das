from typing import Any
from schemas.cad_schema import (
    CADPart,
    ExtrudeBossOperation,
    ExtrudeCutOperation,
    OperationType,
)
from .connection import (
    com_call_0,
    connect_to_solidworks,
    create_new_part,
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
    """
    sketch_name = build_sketch_on_plane(model, op.plane, op.sketch)

    depth_m = mm_to_m(op.depth_mm)
    end_cond_1 = SW_END_COND_MID_PLANE if op.midplane else SW_END_COND_BLIND
    single_dir = not op.midplane

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
    Si el croquis se dibujó sobre el mismo plano de referencia base desde el cual
    se extruyó el saliente, la dirección normal por defecto del corte puede apuntar
    hacia el vacío; en ese caso reintenta automáticamente invirtiendo Dir.
    """
    sketch_name = build_sketch_on_plane(model, op.plane, op.sketch)

    end_cond_1 = SW_END_COND_THROUGH_ALL if op.through_all else SW_END_COND_BLIND
    depth_m = mm_to_m(op.depth_mm) if op.depth_mm is not None else 0.01

    feat_mgr = model.FeatureManager

    # 1. Cuando se dibuja sobre un plano de referencia base, FeatureExtrusion2 extruye hacia +Normal (Dir=False),
    #    mientras que FeatureCut3 corta hacia +Normal cuando Dir=True. Probamos Dir=True primero para evitar
    #    el mensaje de error interno 'Cannot locate end of feature'.
    feat = _call_feature_cut3(
        feat_mgr=feat_mgr,
        sd=True,
        reverse_dir=True,
        end_cond_1=end_cond_1,
        end_cond_2=SW_END_COND_BLIND,
        depth_1_m=depth_m,
    )

    # 2. Si devuelve None, probar en la dirección opuesta (Dir=False)
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

    # 3. Si es pasante (through_all) y aún no cortó, cortar hacia ambos lados (Sd=False)
    if feat is None and op.through_all and sketch_name:
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


def execute_operation(model: Any, op: OperationType) -> Any:
    """Despacha una operación validada por Pydantic hacia su ejecutor de SolidWorks."""
    if isinstance(op, ExtrudeBossOperation):
        return execute_extrude_boss(model, op)
    if isinstance(op, ExtrudeCutOperation):
        return execute_extrude_cut(model, op)
    raise ValueError(f"Tipo de operación no soportada: {type(op)}")


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
            print(
                f"  [{idx}/{len(part.operations)}] Ejecutando '{operation.type}' "
                f"en plano '{operation.plane}' ({len(operation.sketch.shapes)} figura(s))..."
            )
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

