import math
from typing import Any, Optional, Union
from schemas.cad_schema import (
    Arc,
    CADPart,
    CenterRectangle,
    ChamferOperation,
    Circle,
    CircularPatternOperation,
    CornerRectangle,
    ExtrudeBossOperation,
    ExtrudeCutOperation,
    FilletOperation,
    Line,
    LinearPatternOperation,
    OperationType,
    Polygon,
    RevolveBossOperation,
    RevolveCutOperation,
    ShapeType,
    ShellOperation,
    Sketch,
    Slot,
)
from .connection import (
    com_call_0,
    connect_to_solidworks,
    create_new_part,
    create_reference_axis,
    get_last_solid_feature_name,
    mm_to_m,
    select_by_id,
    select_entity,
    set_input_dim_on_create,
)
from .primitives import build_sketch_on_plane

# Constantes de condición final de extrusión (swEndConditions_e)
SW_END_COND_BLIND = 0              # Hasta profundidad especificada
SW_END_COND_THROUGH_ALL = 1        # Por todo (una dirección)
SW_END_COND_MID_PLANE = 6          # Plano medio
SW_END_COND_THROUGH_ALL_BOTH = 9   # Por todo - Ambos lados

# Opción de borrado en IModelDocExtension.DeleteSelection2 (swDeleteSelectionOptions_e)
SW_DELETE_CHILDREN = 1             # swDelete_Children

# Vista estándar Isométrica (swStandardViews_e.swIsometricView)
SW_VIEW_ISOMETRIC = 7


def _call_feature_extrusion2(
    feat_mgr: Any,
    sd: bool,
    end_cond_1: int,
    end_cond_2: int,
    depth_1_m: float,
    depth_2_m: float = 0.0,
) -> Any:
    """Invoca FeatureExtrusion2 con los 23 parámetros exactos de SolidWorks 2018."""
    return feat_mgr.FeatureExtrusion2(
        bool(sd),          # 1. Sd: True = una condición final (incluye MidPlane), False = dos direcciones independientes
        False,             # 2. Flip: invertir lado a cortar
        False,             # 3. Dir: invertir dirección de extrusión
        int(end_cond_1),   # 4. T1: condición final dirección 1
        int(end_cond_2),   # 5. T2: condición final dirección 2
        float(depth_1_m),  # 6. D1: profundidad dirección 1 (metros)
        float(depth_2_m),  # 7. D2: profundidad dirección 2 (metros)
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


def _extrude_single_sketch_boss(
    model: Any,
    sketch_name: str,
    depth_m: float,
    use_midplane: bool,
) -> Any:
    """Intenta extruir un croquis ya cerrado y seleccionado (con fallback en plano medio y ciego)."""
    feat_mgr = model.FeatureManager
    end_cond_1 = SW_END_COND_MID_PLANE if use_midplane else SW_END_COND_BLIND

    # IMPORTANTE: En SolidWorks 2018, swEndCondMidPlane (6) requiere Sd=True.
    # Si se pasa Sd=False con D2=0.0, SolidWorks interpreta Dirección 2 con espesor 0 y falla.
    feat = _call_feature_extrusion2(
        feat_mgr=feat_mgr,
        sd=True,
        end_cond_1=end_cond_1,
        end_cond_2=SW_END_COND_BLIND,
        depth_1_m=depth_m,
        depth_2_m=0.0,
    )

    if feat is None and use_midplane and sketch_name:
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
        feat = _call_feature_extrusion2(
            feat_mgr=feat_mgr,
            sd=False,
            end_cond_1=SW_END_COND_BLIND,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m / 2.0,
            depth_2_m=depth_m / 2.0,
        )

    if feat is None and sketch_name:
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
        feat = _call_feature_extrusion2(
            feat_mgr=feat_mgr,
            sd=True,
            end_cond_1=SW_END_COND_BLIND,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m,
            depth_2_m=0.0,
        )

    return feat


def _delete_sketch_silently(model: Any, sketch_name: str) -> None:
    """Elimina un croquis fallido del árbol para no dejar geometría huérfana."""
    if not sketch_name:
        return
    try:
        model.ClearSelection2(True)
        if select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0):
            model.Extension.DeleteSelection2(SW_DELETE_CHILDREN)
        model.ClearSelection2(True)
    except Exception:
        pass


def _all_shapes_are_closed_primitives(sketch: Sketch) -> bool:
    """Indica si todas las figuras del croquis son primitivas cerradas independientes."""
    return all(not isinstance(s, (Line, Arc)) for s in sketch.shapes)


def _are_concentric_shapes(sketch: Sketch) -> bool:
    """
    Devuelve True si todas las figuras del croquis tienen el mismo centro (cx, cy),
    por ejemplo dos círculos concéntricos para formar un tubo hueco.
    """
    centers: list[tuple[float, float]] = []
    for s in sketch.shapes:
        cx = getattr(s, "cx", None)
        cy = getattr(s, "cy", None)
        if cx is None or cy is None:
            return False
        centers.append((round(float(cx), 4), round(float(cy), 4)))
    return len(set(centers)) == 1


def execute_extrude_boss(model: Any, op: ExtrudeBossOperation) -> Any:
    """
    Ejecuta una operación de extrusión de saliente/base (FeatureExtrusion2)
    con los 23 parámetros exactos requeridos por SolidWorks 2018.
    - Soporta planos desfasados (plane_offset_mm) y extrusión simétrica (midplane / both_directions).
    - Si la IA agrupa varias figuras cerradas no concéntricas en el mismo croquis de saliente
      (ej. cilindro + brazo + orejas de brida), las extruye directamente una por una con
      Merge=True para que SolidWorks haga la unión booleana 3D sin fallar por contornos cruzados.
    """
    depth_m = mm_to_m(op.depth_mm)
    use_midplane = bool(op.midplane or op.both_directions)

    # Si hay múltiples primitivas cerradas en distintas posiciones dentro de un extrude_boss,
    # extruirlas una por una directamente evita el fallo de contornos auto-intersectantes en 2D.
    if (
        len(op.sketch.shapes) > 1
        and _all_shapes_are_closed_primitives(op.sketch)
        and not _are_concentric_shapes(op.sketch)
    ):
        feat = None
        for shape in op.sketch.shapes:
            sub_sketch = Sketch(shapes=[shape])
            sub_sketch_name = build_sketch_on_plane(
                model,
                op.plane,
                sub_sketch,
                plane_offset_mm=op.plane_offset_mm,
            )
            feat = _extrude_single_sketch_boss(model, sub_sketch_name, depth_m, use_midplane)
            if feat is None:
                raise RuntimeError(
                    f"Falló FeatureExtrusion2 al extruir figura '{shape.kind}' en el plano '{op.plane}'."
                )
        model.ClearSelection2(True)
        return feat

    sketch_name = build_sketch_on_plane(
        model,
        op.plane,
        op.sketch,
        plane_offset_mm=op.plane_offset_mm,
    )

    feat = _extrude_single_sketch_boss(model, sketch_name, depth_m, use_midplane)

    # Fallback de descomposición booleana 3D si falló un croquis múltiple
    if feat is None and len(op.sketch.shapes) > 1 and _all_shapes_are_closed_primitives(op.sketch):
        _delete_sketch_silently(model, sketch_name)
        for shape in op.sketch.shapes:
            sub_sketch = Sketch(shapes=[shape])
            sub_sketch_name = build_sketch_on_plane(
                model,
                op.plane,
                sub_sketch,
                plane_offset_mm=op.plane_offset_mm,
            )
            feat = _extrude_single_sketch_boss(model, sub_sketch_name, depth_m, use_midplane)
            if feat is None:
                raise RuntimeError(
                    f"Falló FeatureExtrusion2 al descomponer figura '{shape.kind}' en el plano '{op.plane}'."
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


def _cut_single_sketch(
    model: Any,
    sketch_name: str,
    op: ExtrudeCutOperation,
    end_cond_1: int,
    depth_m: float,
) -> Any:
    """Ejecuta FeatureCut3 sobre un croquis cerrado probando las direcciones válidas."""
    feat_mgr = model.FeatureManager
    feat = None

    # 1A. Si through_all=True, probar primero SW_END_COND_THROUGH_ALL_BOTH (9) y luego Sd=False.
    #     Esto garantiza que si la pieza se extruyó con midplane=True, un corte pasante en el plano
    #     central atraviese AMBAS mitades del sólido y no solo una mitad.
    if op.through_all:
        feat = _call_feature_cut3(
            feat_mgr=feat_mgr,
            sd=True,
            reverse_dir=False,
            end_cond_1=SW_END_COND_THROUGH_ALL_BOTH,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m,
        )
        if feat is None and sketch_name:
            select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)

        if feat is None:
            feat = _call_feature_cut3(
                feat_mgr=feat_mgr,
                sd=False,
                reverse_dir=False,
                end_cond_1=SW_END_COND_THROUGH_ALL,
                end_cond_2=SW_END_COND_THROUGH_ALL,
                depth_1_m=depth_m,
                depth_2_m=depth_m,
            )
            if feat is None and sketch_name:
                select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)

    # 1B. Si through_all=False y both_directions=True, el usuario/IA indicó una profundidad total
    #     centrada en el plano (igual que midplane=True). Usamos SW_END_COND_MID_PLANE (6) o
    #     depth_m / 2.0 hacia cada lado para no duplicar la profundidad y partir la pieza en dos.
    if feat is None and not op.through_all and op.both_directions:
        feat = _call_feature_cut3(
            feat_mgr=feat_mgr,
            sd=True,
            reverse_dir=False,
            end_cond_1=SW_END_COND_MID_PLANE,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m,
        )
        if feat is None and sketch_name:
            select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
            feat = _call_feature_cut3(
                feat_mgr=feat_mgr,
                sd=False,
                reverse_dir=False,
                end_cond_1=SW_END_COND_BLIND,
                end_cond_2=SW_END_COND_BLIND,
                depth_1_m=depth_m / 2.0,
                depth_2_m=depth_m / 2.0,
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

    # 4. Si es un corte ciego desde un plano central y fallaron las direcciones simples, probar Plano Medio
    if feat is None and not op.through_all and sketch_name:
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
        feat = _call_feature_cut3(
            feat_mgr=feat_mgr,
            sd=True,
            reverse_dir=False,
            end_cond_1=SW_END_COND_MID_PLANE,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m,
        )

    return feat


def execute_extrude_cut(model: Any, op: ExtrudeCutOperation) -> Any:
    """
    Ejecuta una operación de corte extruido (FeatureCut3) en SolidWorks 2018.
    - Soporta planos paralelos desfasados (plane_offset_mm).
    - Si both_directions=True o through_all=True, intenta primero cortar hacia ambos lados (Sd=False)
      para atravesar piezas simétricas (midplane=True) de lado a lado, con fallback a una dirección.
    - Si hay múltiples primitivas cerradas solapadas que fallan como croquis único,
      descompone el corte automáticamente figura por figura.
    """
    sketch_name = build_sketch_on_plane(
        model,
        op.plane,
        op.sketch,
        plane_offset_mm=op.plane_offset_mm,
    )

    end_cond_1 = SW_END_COND_THROUGH_ALL if op.through_all else SW_END_COND_BLIND
    depth_m = mm_to_m(op.depth_mm) if op.depth_mm is not None else 0.01

    feat = _cut_single_sketch(model, sketch_name, op, end_cond_1, depth_m)

    # Fallback de descomposición booleana si múltiples figuras de corte se solapan en el croquis
    if feat is None and len(op.sketch.shapes) > 1 and _all_shapes_are_closed_primitives(op.sketch):
        _delete_sketch_silently(model, sketch_name)
        for shape in op.sketch.shapes:
            sub_sketch = Sketch(shapes=[shape])
            sub_sketch_name = build_sketch_on_plane(
                model,
                op.plane,
                sub_sketch,
                plane_offset_mm=op.plane_offset_mm,
            )
            feat = _cut_single_sketch(model, sub_sketch_name, op, end_cond_1, depth_m)
            if feat is None:
                raise RuntimeError(
                    f"Falló FeatureCut3 al descomponer figura '{shape.kind}' en el plano '{op.plane}'."
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


def _rotate_point(x: float, y: float, angle_rad: float) -> tuple[float, float]:
    """Rota un punto 2D (x, y) alrededor del origen (0, 0) por angle_rad radianes."""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return (
        round(x * cos_a - y * sin_a, 4),
        round(x * sin_a + y * cos_a, 4),
    )


def _rotate_sketch(sketch: Sketch, angle_deg: float) -> Sketch:
    """Devuelve una copia del Sketch con todas sus figuras rotadas angle_deg grados alrededor de (0,0)."""
    rad = math.radians(float(angle_deg))
    rotated_shapes: list[ShapeType] = []

    for s in sketch.shapes:
        if isinstance(s, Circle):
            nx, ny = _rotate_point(s.cx, s.cy, rad)
            rotated_shapes.append(Circle(cx=nx, cy=ny, diameter=s.diameter))
        elif isinstance(s, Polygon):
            nx, ny = _rotate_point(s.cx, s.cy, rad)
            rotated_shapes.append(
                Polygon(cx=nx, cy=ny, diameter=s.diameter, sides=s.sides, inscribed=s.inscribed)
            )
        elif isinstance(s, Line):
            x1, y1 = _rotate_point(s.x1, s.y1, rad)
            x2, y2 = _rotate_point(s.x2, s.y2, rad)
            rotated_shapes.append(Line(x1=x1, y1=y1, x2=x2, y2=y2))
        elif isinstance(s, Arc):
            cx, cy = _rotate_point(s.cx, s.cy, rad)
            x1, y1 = _rotate_point(s.x1, s.y1, rad)
            x2, y2 = _rotate_point(s.x2, s.y2, rad)
            rotated_shapes.append(Arc(cx=cx, cy=cy, x1=x1, y1=y1, x2=x2, y2=y2, direction=s.direction))
        elif isinstance(s, Slot):
            x1, y1 = _rotate_point(s.x1, s.y1, rad)
            x2, y2 = _rotate_point(s.x2, s.y2, rad)
            rotated_shapes.append(Slot(x1=x1, y1=y1, x2=x2, y2=y2, width=s.width))
        elif isinstance(s, CenterRectangle):
            hw = s.width / 2.0
            hh = s.height / 2.0
            corners = [
                _rotate_point(s.cx - hw, s.cy - hh, rad),
                _rotate_point(s.cx + hw, s.cy - hh, rad),
                _rotate_point(s.cx + hw, s.cy + hh, rad),
                _rotate_point(s.cx - hw, s.cy + hh, rad),
            ]
            for i in range(4):
                p1 = corners[i]
                p2 = corners[(i + 1) % 4]
                rotated_shapes.append(Line(x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1]))
        elif isinstance(s, CornerRectangle):
            corners = [
                _rotate_point(s.x1, s.y1, rad),
                _rotate_point(s.x2, s.y1, rad),
                _rotate_point(s.x2, s.y2, rad),
                _rotate_point(s.x1, s.y2, rad),
            ]
            for i in range(4):
                p1 = corners[i]
                p2 = corners[(i + 1) % 4]
                rotated_shapes.append(Line(x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1]))

    return Sketch(shapes=rotated_shapes)


def _find_feature_by_name(model: Any, target_name: str) -> Any:
    """Busca y devuelve el puntero IFeature en el árbol del FeatureManager por su nombre."""
    feat = com_call_0(model, "FirstFeature")
    while feat is not None:
        if str(com_call_0(feat, "Name") or "") == target_name:
            return feat
        feat = com_call_0(feat, "GetNextFeature")
    return None


def execute_circular_pattern(
    model: Any,
    op: CircularPatternOperation,
    prev_op: Optional[OperationType] = None,
) -> Any:
    """
    Ejecuta una matriz circular (FeatureCircularPattern4) sobre la última operación 3D creada:
    1. Identifica la última operación 3D sólida en el árbol del FeatureManager.
    2. Crea un eje de referencia (InsertAxis2) en la intersección de dos planos base según op.axis.
    3. Selecciona la operación con Mark=4 ('BODYFEATURE') y el eje con Mark=1 ('AXIS').
    4. Ejecuta FeatureCircularPattern4 (con GeometryPattern=False y fallback a True).
    5. Si SolidWorks rechaza la matriz de operación (ej. cuando una instancia cruza una ranura
       previa que altera la topología de caras), aplica automáticamente rotación geométrica 2D
       sobre el croquis de prev_op para construir las instancias restantes sin fallar.
    """
    target_feat_name, target_feat_type = get_last_solid_feature_name(model)
    axis_name = create_reference_axis(model, op.axis)
    print(
        f"     -> Matriz circular sobre '{target_feat_name}' (tipo '{target_feat_type}') "
        f"alrededor de '{axis_name}' (eje '{op.axis}', {op.instances} instancias)..."
    )

    # En FeatureCircularPattern4 de SolidWorks 2018:
    # - Si EqualSpacing=True, Spacing es el ángulo TOTAL en radianes (ej. 2*pi).
    # - Si EqualSpacing=False, Spacing es el paso angular entre instancias (total / instances).
    total_rad = math.radians(float(op.angle_deg))
    step_rad = total_rad / float(op.instances)
    feat_mgr = model.FeatureManager
    target_feat_obj = _find_feature_by_name(model, target_feat_name)

    def _try_circular_pattern(geom_pattern: bool, equal_spacing: bool, spacing_rad: float) -> Any:
        model.ClearSelection2(True)
        ok_feat = select_by_id(model, target_feat_name, "BODYFEATURE", 0.0, 0.0, 0.0, append=False, mark=4)
        if not ok_feat and target_feat_obj is not None:
            ok_feat = select_entity(model, target_feat_obj, append=False, mark=4)
        ok_axis = select_by_id(model, axis_name, "AXIS", 0.0, 0.0, 0.0, append=True, mark=1)
        print(
            f"     -> Intento FeatureCircularPattern4(geom={geom_pattern}, equal={equal_spacing}): "
            f"sel_feat={ok_feat}, sel_axis={ok_axis}"
        )
        return feat_mgr.FeatureCircularPattern4(
            int(op.instances),       # 1. Number
            float(spacing_rad),      # 2. Spacing (radianes)
            False,                   # 3. FlipDirection
            "NULL",                  # 4. DName
            bool(geom_pattern),      # 5. GeometryPattern
            bool(equal_spacing),     # 6. EqualSpacing
            False,                   # 7. VaryInstance
        )

    feat = _try_circular_pattern(geom_pattern=False, equal_spacing=op.equal_spacing, spacing_rad=total_rad)
    if feat is None:
        feat = _try_circular_pattern(geom_pattern=True, equal_spacing=op.equal_spacing, spacing_rad=total_rad)
    if feat is None:
        feat = _try_circular_pattern(geom_pattern=False, equal_spacing=False, spacing_rad=step_rad)
    if feat is None:
        feat = _try_circular_pattern(geom_pattern=True, equal_spacing=False, spacing_rad=step_rad)

    # Fallback infalible: si SolidWorks rechaza la matriz 3D por cambio topológico (ej. el corte
    # rotado cruza una ranura o unión de caras distinta), rotar las coordenadas del croquis anterior
    if feat is None and isinstance(prev_op, (ExtrudeCutOperation, ExtrudeBossOperation)):
        step_deg = float(op.angle_deg) / float(op.instances) if op.equal_spacing else float(op.angle_deg)
        # Cuando el croquis está en el plano perpendicular al eje de rotación (ej. Top con eje Y,
        # Front con eje Z, Right con eje X), rotamos el croquis 2D directamente:
        perp_plane_map = {"Y": "Top", "Z": "Front", "X": "Right"}
        if prev_op.plane == perp_plane_map.get(op.axis.upper(), "Top"):
            print(
                f"     -> [FALLBACK GEOMÉTRICO] SolidWorks rechazó el patrón de operación sobre '{target_feat_name}' "
                f"(posible cruce de topología/ranura). Ejecutando las {op.instances - 1} instancias rotadas por croquis..."
            )
            for k in range(1, int(op.instances)):
                rot_angle = k * step_deg
                # En el plano Top de SolidWorks, el giro alrededor de +Y invierte el signo en el plano 2D
                rot_sketch = _rotate_sketch(prev_op.sketch, rot_angle)
                if isinstance(prev_op, ExtrudeCutOperation):
                    rot_op: Union[ExtrudeCutOperation, ExtrudeBossOperation] = ExtrudeCutOperation(
                        plane=prev_op.plane,
                        plane_offset_mm=prev_op.plane_offset_mm,
                        through_all=prev_op.through_all,
                        both_directions=prev_op.both_directions,
                        depth_mm=prev_op.depth_mm,
                        sketch=rot_sketch,
                    )
                    feat = execute_extrude_cut(model, rot_op)
                else:
                    rot_op = ExtrudeBossOperation(
                        plane=prev_op.plane,
                        plane_offset_mm=prev_op.plane_offset_mm,
                        depth_mm=prev_op.depth_mm,
                        midplane=prev_op.midplane,
                        both_directions=prev_op.both_directions,
                        sketch=rot_sketch,
                    )
                    feat = execute_extrude_boss(model, rot_op)

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


def _select_edges_of_last_feature(model: Any, target_feat_name: str) -> int:
    """Selecciona la última operación 3D y sus aristas para redondeo o chaflán."""
    model.ClearSelection2(True)
    selected_edges = 0
    feat = com_call_0(model, "FirstFeature")
    while feat is not None:
        if str(com_call_0(feat, "Name") or "") == target_feat_name:
            faces = com_call_0(feat, "GetFaces")
            if faces:
                for face in faces:
                    edges = com_call_0(face, "GetEdges")
                    if edges:
                        for edge in edges:
                            if select_entity(model, edge, append=True, mark=1):
                                selected_edges += 1
            break
        feat = com_call_0(feat, "GetNextFeature")

    if selected_edges == 0:
        select_by_id(model, target_feat_name, "BODYFEATURE", 0.0, 0.0, 0.0, append=False, mark=1)
    return selected_edges


def execute_fillet(model: Any, op: FilletOperation) -> Any:
    """
    Ejecuta un redondeo de radio constante (IModelDoc2.FeatureFillet) sobre las aristas
    de la última operación 3D creada.
    Nota: IModelDoc2.FeatureFillet retorna VT_VOID (None en COM), por lo que se verifica
    su creación comparando la última operación 3D en el FeatureManager.
    """
    target_feat_name, _ = get_last_solid_feature_name(model)
    radius_m = mm_to_m(op.radius_mm)

    _select_edges_of_last_feature(model, target_feat_name)
    model.FeatureFillet(
        float(radius_m),  # 1. R1: radio en metros
        True,             # 2. Propagate: propagación tangente
        False,            # 3. Ftyp: radio constante
        False,            # 4. VarRadTyp
        0,                # 5. OverflowType (0 = default)
    )

    after_name, after_type = get_last_solid_feature_name(model)
    if after_name == target_feat_name:
        model.ClearSelection2(True)
        select_by_id(model, target_feat_name, "BODYFEATURE", 0.0, 0.0, 0.0, append=False, mark=1)
        model.FeatureFillet(float(radius_m), True, False, False, 0)
        after_name, after_type = get_last_solid_feature_name(model)

    if after_name == target_feat_name:
        raise RuntimeError(
            f"Falló FeatureFillet ({op.radius_mm} mm) sobre la operación '{target_feat_name}'."
        )

    model.ClearSelection2(True)
    return after_name


def execute_chamfer(model: Any, op: ChamferOperation) -> Any:
    """
    Ejecuta un chaflán de distancia y ángulo (IModelDoc2.FeatureChamfer) sobre las aristas
    de la última operación 3D creada.
    Nota: IModelDoc2.FeatureChamfer retorna VT_VOID (None en COM), por lo que se verifica
    su creación comparando la última operación 3D en el FeatureManager.
    """
    target_feat_name, _ = get_last_solid_feature_name(model)
    width_m = mm_to_m(op.distance_mm)
    angle_rad = math.radians(float(op.angle_deg))

    _select_edges_of_last_feature(model, target_feat_name)
    model.FeatureChamfer(
        float(width_m),    # 1. Width (metros)
        float(angle_rad),  # 2. Angle (radianes)
        False,             # 3. Flip
    )

    after_name, _ = get_last_solid_feature_name(model)
    if after_name == target_feat_name:
        raise RuntimeError(
            f"Falló FeatureChamfer ({op.distance_mm} mm x {op.angle_deg}°) sobre '{target_feat_name}'."
        )

    model.ClearSelection2(True)
    return after_name


def execute_shell(model: Any, op: ShellOperation) -> Any:
    """
    Ejecuta un vaciado (IModelDoc2.InsertFeatureShell) sobre el sólido actual, seleccionando
    automáticamente la cara exterior plana cuya normal apunta en la dirección op.open_face.
    """
    direction_vectors: dict[str, tuple[float, float, float]] = {
        "Top": (0.0, 1.0, 0.0),
        "Bottom": (0.0, -1.0, 0.0),
        "Front": (0.0, 0.0, 1.0),
        "Back": (0.0, 0.0, -1.0),
        "Right": (1.0, 0.0, 0.0),
        "Left": (-1.0, 0.0, 0.0),
    }
    target_vec = direction_vectors.get(op.open_face, (0.0, 1.0, 0.0))

    prev_feat_name, _ = get_last_solid_feature_name(model)
    model.ClearSelection2(True)
    best_face = None
    best_score = -1e9

    bodies = model.GetBodies2(0, True)  # 0 = swSolidBody
    if bodies:
        for body in bodies:
            faces = com_call_0(body, "GetFaces")
            if not faces:
                continue
            for face in faces:
                try:
                    normal = com_call_0(face, "Normal")
                    box = com_call_0(face, "GetBox")
                    if normal and len(normal) >= 3:
                        dot = (
                            float(normal[0]) * target_vec[0]
                            + float(normal[1]) * target_vec[1]
                            + float(normal[2]) * target_vec[2]
                        )
                        pos_proj = 0.0
                        if box and len(box) >= 6:
                            cx = 0.5 * (float(box[0]) + float(box[3]))
                            cy = 0.5 * (float(box[1]) + float(box[4]))
                            cz = 0.5 * (float(box[2]) + float(box[5]))
                            pos_proj = cx * target_vec[0] + cy * target_vec[1] + cz * target_vec[2]
                        score = dot * 100.0 + pos_proj
                        if score > best_score:
                            best_score = score
                            best_face = face
                except Exception:
                    pass

    if best_face is None:
        raise RuntimeError(
            f"No se encontró una cara exterior en dirección '{op.open_face}' para ejecutar el vaciado (shell)."
        )

    if not select_entity(model, best_face, append=False, mark=1):
        raise RuntimeError(
            f"No se pudo seleccionar la cara '{op.open_face}' en SolidWorks para ejecutar el vaciado (shell)."
        )

    thickness_m = mm_to_m(op.thickness_mm)
    model.InsertFeatureShell(float(thickness_m), bool(op.outward))

    after_name, _ = get_last_solid_feature_name(model)
    if after_name == prev_feat_name:
        raise RuntimeError(
            f"Falló InsertFeatureShell (espesor {op.thickness_mm} mm, cara '{op.open_face}')."
        )

    model.ClearSelection2(True)
    return after_name


def execute_operation(
    model: Any,
    op: OperationType,
    prev_op: Optional[OperationType] = None,
) -> Any:
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
        return execute_circular_pattern(model, op, prev_op=prev_op)
    if isinstance(op, LinearPatternOperation):
        return execute_linear_pattern(model, op)
    if isinstance(op, FilletOperation):
        return execute_fillet(model, op)
    if isinstance(op, ChamferOperation):
        return execute_chamfer(model, op)
    if isinstance(op, ShellOperation):
        return execute_shell(model, op)
    raise ValueError(f"Tipo de operación no soportada: {type(op)}")


def _format_operation_summary(op: OperationType) -> str:
    """Genera una descripción legible de la operación para la consola."""
    if isinstance(op, CircularPatternOperation):
        return f"'{op.type}' ({op.instances} instancias a {op.angle_deg}° sobre eje '{op.axis}')"
    if isinstance(op, LinearPatternOperation):
        return f"'{op.type}' ({op.instances_x}x{op.instances_y} instancias)"
    if isinstance(op, FilletOperation):
        return f"'{op.type}' (R{op.radius_mm:g} mm)"
    if isinstance(op, ChamferOperation):
        return f"'{op.type}' ({op.distance_mm:g} mm x {op.angle_deg:g}°)"
    if isinstance(op, ShellOperation):
        return f"'{op.type}' (espesor {op.thickness_mm:g} mm, cara abierta '{op.open_face}')"
    offset_info = f" (offset {op.plane_offset_mm:g} mm)" if abs(op.plane_offset_mm) > 1e-6 else ""
    return f"'{op.type}' en plano '{op.plane}'{offset_info} ({len(op.sketch.shapes)} figura(s))"


def build_part(part: CADPart) -> Any:
    """
    Orquesta la construcción completa de una pieza CADPart en SolidWorks 2018:
    - Conecta a SolidWorks 2018 y abre una pieza limpia.
    - Desactiva temporalmente swInputDimValOnCreate (enum 10) y swSketchInference (enum 249).
    - Ejecuta secuencialmente cada croquis y operación 3D imprimiendo telemetría detallada.
    - Restaura las preferencias del usuario y ajusta la vista isométrica.
    """
    sw_app = connect_to_solidworks()
    model = create_new_part(sw_app)

    prev_dim_toggle = set_input_dim_on_create(sw_app, False)
    prev_op: Optional[OperationType] = None
    try:
        for idx, operation in enumerate(part.operations, start=1):
            print(f"  [{idx}/{len(part.operations)}] Ejecutando {_format_operation_summary(operation)}...")
            execute_operation(model, operation, prev_op=prev_op)
            last_name, last_type = get_last_solid_feature_name(model)
            print(f"     [OK] Operación {idx} completada -> última feature en árbol: '{last_name}' ({last_type})")
            prev_op = operation
    finally:
        # Restaurar las preferencias de cota e inferencia para que la UI quede 100% normal al editar
        set_input_dim_on_create(sw_app, True if prev_dim_toggle else True)

    # Reconstruir modelo y encuadrar en vista isométrica
    com_call_0(model, "EditRebuild3")
    model.ClearSelection2(True)
    model.ShowNamedView2("*Isometric", SW_VIEW_ISOMETRIC)
    com_call_0(model, "ViewZoomtofit2")
    return model

