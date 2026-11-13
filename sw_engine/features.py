import math
from typing import Any, Literal, Optional, Union
from schemas.cad_schema import (
    AnnularSector,
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
    MirrorOperation,
    OperationType,
    Polygon,
    RevolveBossOperation,
    RevolveCutOperation,
    ShapeType,
    ShellOperation,
    Sketch,
    Slot,
    WrapOperation,
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

# Constantes de operación Wrap en SolidWorks 2018 (verificadas en swconst.tlb)
SW_WRAP_TYPE_EMBOSS = 0            # swWrapSketchType_Emboss (saliente/relieve)
SW_WRAP_TYPE_ENGRAVE = 1           # swWrapSketchType_Engrave (deboss/grabado/corte)
SW_WRAP_TYPE_SCRIBE = 2            # swWrapSketchType_Scribe (línea de partición)
SW_WRAP_METHOD_ANALYTICAL = 0      # swWrapMethods_Analytical (cilindros y conos analíticos)
SW_WRAP_METHOD_SPLINE_SURFACE = 1  # swWrapMethods_SplineSurface (fallback multi-cara/complejo)

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
    reverse_dir: bool = False,
) -> Any:
    """Invoca FeatureExtrusion2 con los 23 parámetros exactos de SolidWorks 2018."""
    return feat_mgr.FeatureExtrusion2(
        bool(sd),           # 1. Sd: True = una condición final (incluye MidPlane), False = dos direcciones independientes
        False,              # 2. Flip: invertir lado a cortar
        bool(reverse_dir),  # 3. Dir: invertir dirección de extrusión
        int(end_cond_1),    # 4. T1: condición final dirección 1
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
        # Si un saliente secundario sobre el mismo plano base (ej. relieve de 6 mm sobre placa de 12 mm)
        # queda sumergido dentro del sólido existente en dirección +Normal, extruir en -Normal (reverse_dir=True)
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
        feat = _call_feature_extrusion2(
            feat_mgr=feat_mgr,
            sd=True,
            end_cond_1=SW_END_COND_BLIND,
            end_cond_2=SW_END_COND_BLIND,
            depth_1_m=depth_m,
            depth_2_m=0.0,
            reverse_dir=True,
        )

    if feat is None and sketch_name:
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)
        feat = _call_feature_extrusion2(
            feat_mgr=feat_mgr,
            sd=True,
            end_cond_1=SW_END_COND_MID_PLANE,
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

    # 1A. Si through_all=True, usar primero Sd=False (ambas direcciones) con SW_END_COND_THROUGH_ALL.
    #     En SolidWorks 2018, pasar Sd=True ignora la segunda dirección y corta solo la mitad del
    #     sólido cuando el croquis reside en el plano central (midplane=True).
    if op.through_all:
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
        elif isinstance(s, AnnularSector):
            nx, ny = _rotate_point(s.cx, s.cy, rad)
            rotated_shapes.append(
                AnnularSector(
                    cx=nx,
                    cy=ny,
                    inner_radius=s.inner_radius,
                    outer_radius=s.outer_radius,
                    start_angle_deg=s.start_angle_deg + float(angle_deg),
                    end_angle_deg=s.end_angle_deg + float(angle_deg),
                )
            )
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


def _mirror_point(x: float, y: float, flip_x: bool, flip_y: bool) -> tuple[float, float]:
    """Refleja un punto 2D (x, y) invirtiendo X y/o Y sin generar -0.0."""
    nx = round(-x if flip_x else x, 4)
    ny = round(-y if flip_y else y, 4)
    return (0.0 if nx == 0.0 else nx, 0.0 if ny == 0.0 else ny)


def _mirror_sketch(sketch: Sketch, flip_x: bool, flip_y: bool) -> Sketch:
    """
    Devuelve una copia del Sketch reflejada respecto al eje X o Y del croquis.
    Cuando se invierte un solo eje (flip_x ^ flip_y), invierte también el orden de recorrido
    de líneas y arcos intercambiando (x1,y1)<->(x2,y2) para conservar exactamente el mismo
    sentido de giro (antihorario, direction=1) que funcionó en el croquis original.
    """
    mirrored_shapes: list[ShapeType] = []
    invert_winding = bool(flip_x ^ flip_y)
    source_shapes = list(reversed(sketch.shapes)) if invert_winding else list(sketch.shapes)

    for s in source_shapes:
        if isinstance(s, Circle):
            nx, ny = _mirror_point(s.cx, s.cy, flip_x, flip_y)
            mirrored_shapes.append(Circle(cx=nx, cy=ny, diameter=s.diameter))
        elif isinstance(s, Polygon):
            nx, ny = _mirror_point(s.cx, s.cy, flip_x, flip_y)
            mirrored_shapes.append(
                Polygon(cx=nx, cy=ny, diameter=s.diameter, sides=s.sides, inscribed=s.inscribed)
            )
        elif isinstance(s, Line):
            x1, y1 = _mirror_point(s.x1, s.y1, flip_x, flip_y)
            x2, y2 = _mirror_point(s.x2, s.y2, flip_x, flip_y)
            if invert_winding:
                mirrored_shapes.append(Line(x1=x2, y1=y2, x2=x1, y2=y1))
            else:
                mirrored_shapes.append(Line(x1=x1, y1=y1, x2=x2, y2=y2))
        elif isinstance(s, Arc):
            cx, cy = _mirror_point(s.cx, s.cy, flip_x, flip_y)
            x1, y1 = _mirror_point(s.x1, s.y1, flip_x, flip_y)
            x2, y2 = _mirror_point(s.x2, s.y2, flip_x, flip_y)
            if invert_winding:
                mirrored_shapes.append(Arc(cx=cx, cy=cy, x1=x2, y1=y2, x2=x1, y2=y1, direction=s.direction))
            else:
                mirrored_shapes.append(Arc(cx=cx, cy=cy, x1=x1, y1=y1, x2=x2, y2=y2, direction=s.direction))
        elif isinstance(s, Slot):
            x1, y1 = _mirror_point(s.x1, s.y1, flip_x, flip_y)
            x2, y2 = _mirror_point(s.x2, s.y2, flip_x, flip_y)
            mirrored_shapes.append(Slot(x1=x1, y1=y1, x2=x2, y2=y2, width=s.width))
        elif isinstance(s, CenterRectangle):
            nx, ny = _mirror_point(s.cx, s.cy, flip_x, flip_y)
            mirrored_shapes.append(CenterRectangle(cx=nx, cy=ny, width=s.width, height=s.height))
        elif isinstance(s, CornerRectangle):
            x1, y1 = _mirror_point(s.x1, s.y1, flip_x, flip_y)
            x2, y2 = _mirror_point(s.x2, s.y2, flip_x, flip_y)
            mirrored_shapes.append(CornerRectangle(x1=x1, y1=y1, x2=x2, y2=y2))
        elif isinstance(s, AnnularSector):
            nx, ny = _mirror_point(s.cx, s.cy, flip_x, flip_y)
            a_low = min(float(s.start_angle_deg), float(s.end_angle_deg))
            a_high = max(float(s.start_angle_deg), float(s.end_angle_deg))
            if flip_x and not flip_y:
                new_start, new_end = 180.0 - a_high, 180.0 - a_low
            elif flip_y and not flip_x:
                new_start, new_end = -a_high, -a_low
            elif flip_x and flip_y:
                new_start, new_end = a_low + 180.0, a_high + 180.0
            else:
                new_start, new_end = a_low, a_high
            mirrored_shapes.append(
                AnnularSector(
                    cx=nx,
                    cy=ny,
                    inner_radius=s.inner_radius,
                    outer_radius=s.outer_radius,
                    start_angle_deg=new_start,
                    end_angle_deg=new_end,
                )
            )

    return Sketch(shapes=mirrored_shapes)


def execute_mirror(
    model: Any,
    op: MirrorOperation,
    prev_op: Optional[OperationType] = None,
) -> Any:
    """
    Ejecuta una simetría 3D (mirror) de la última operación respecto al plano op.plane:
    - Si prev_op es una operación de croquis (ExtrudeBoss / ExtrudeCut), refleja las coordenadas
      2D respecto al plano de simetría o utiliza InsertMirrorFeature2 de SolidWorks.
    """
    target_feat_name, _ = get_last_solid_feature_name(model)
    if isinstance(prev_op, (ExtrudeCutOperation, ExtrudeBossOperation)):
        # Mapa (sketch_plane, mirror_plane) -> (flip_x, flip_y)
        flip_map: dict[tuple[str, str], tuple[bool, bool]] = {
            ("Top", "Front"): (False, True),
            ("Top", "Right"): (True, False),
            ("Front", "Top"): (False, True),
            ("Front", "Right"): (True, False),
            ("Right", "Top"): (False, True),
            ("Right", "Front"): (True, False),
        }
        flip_x, flip_y = flip_map.get((prev_op.plane, op.plane), (False, True))
        mirrored_sketch = _mirror_sketch(prev_op.sketch, flip_x=flip_x, flip_y=flip_y)
        if isinstance(prev_op, ExtrudeCutOperation):
            mirrored_op: Union[ExtrudeCutOperation, ExtrudeBossOperation] = ExtrudeCutOperation(
                plane=prev_op.plane,
                plane_offset_mm=prev_op.plane_offset_mm,
                through_all=prev_op.through_all,
                both_directions=prev_op.both_directions,
                depth_mm=prev_op.depth_mm,
                sketch=mirrored_sketch,
            )
            return execute_extrude_cut(model, mirrored_op)
        else:
            mirrored_op = ExtrudeBossOperation(
                plane=prev_op.plane,
                plane_offset_mm=prev_op.plane_offset_mm,
                depth_mm=prev_op.depth_mm,
                midplane=prev_op.midplane,
                both_directions=prev_op.both_directions,
                sketch=mirrored_sketch,
            )
            return execute_extrude_boss(model, mirrored_op)

    raise RuntimeError(
        f"No se pudo reflejar la operación '{target_feat_name}' respecto al plano '{op.plane}'."
    )


def _collect_unique_straight_edges(
    model: Any,
) -> list[tuple[Any, tuple[float, float, float], tuple[float, float, float]]]:
    """
    Recorre los cuerpos sólidos del modelo y devuelve una lista deduplicada de aristas
    con vértices de inicio y fin definidos: (edge_obj, p1, p2) en metros.
    """
    result: list[tuple[Any, tuple[float, float, float], tuple[float, float, float]]] = []
    seen_keys: set[tuple[float, float, float, float, float, float]] = set()
    bodies = model.GetBodies2(0, True)  # 0 = swSolidBody
    if not bodies:
        return result

    for body in bodies:
        edges = com_call_0(body, "GetEdges")
        if not edges:
            faces = com_call_0(body, "GetFaces") or []
            edge_list = []
            for f in faces:
                f_edges = com_call_0(f, "GetEdges")
                if f_edges:
                    edge_list.extend(f_edges)
            edges = edge_list

        for edge in edges or []:
            try:
                curve = com_call_0(edge, "GetCurve")
                if curve is not None and not bool(com_call_0(curve, "IsLine")):
                    continue
                v1 = com_call_0(edge, "GetStartVertex")
                v2 = com_call_0(edge, "GetEndVertex")
                if v1 is None or v2 is None:
                    continue
                p1_raw = com_call_0(v1, "GetPoint")
                p2_raw = com_call_0(v2, "GetPoint")
                if not p1_raw or not p2_raw or len(p1_raw) < 3 or len(p2_raw) < 3:
                    continue
                p1 = (float(p1_raw[0]), float(p1_raw[1]), float(p1_raw[2]))
                p2 = (float(p2_raw[0]), float(p2_raw[1]), float(p2_raw[2]))
                pts = sorted([
                    (round(p1[0], 5), round(p1[1], 5), round(p1[2], 5)),
                    (round(p2[0], 5), round(p2[1], 5), round(p2[2], 5)),
                ])
                key = (pts[0][0], pts[0][1], pts[0][2], pts[1][0], pts[1][1], pts[1][2])
                if key not in seen_keys:
                    seen_keys.add(key)
                    result.append((edge, p1, p2))
            except Exception:
                pass
    return result


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
    Ejecuta un redondeo de radio constante (IModelDoc2.FeatureFillet) según el filtro op.edges:
    - 'vertical': selecciona aristas rectas verticales paralelas al eje Y (ej. cuellos R8 entre salientes).
    - 'horizontal_slot_ends': selecciona aristas horizontales interiores a mitad de altura (ej. extremos R5 de vaciados).
    - 'last_feature' / 'all': selecciona las aristas de la última operación o de todo el sólido.
    Incluye fallback de radio al 96% cuando 2*R coincide exactamente con el espesor de la cara (Full-Round límite)
    y fallback arista por arista si un lote falla parcialmente.
    """
    target_feat_name, _ = get_last_solid_feature_name(model)
    radius_m = mm_to_m(op.radius_mm)

    if op.edges in ("vertical", "horizontal_slot_ends"):
        all_edges = _collect_unique_straight_edges(model)
        candidate_edges: list[Any] = []

        if op.edges == "vertical":
            for edge, p1, p2 in all_edges:
                dx = abs(p1[0] - p2[0])
                dy = abs(p1[1] - p2[1])
                dz = abs(p1[2] - p2[2])
                if dx < 1e-4 and dz < 1e-4 and dy > 1e-3:
                    candidate_edges.append(edge)
        else:
            # 'horizontal_slot_ends': detecta caras PLANAS verticales interiores de fin de ranura
            # (cuyo rango Y está estrictamente dentro de la altura total de la pieza, ej. [-5mm, +5mm]
            # dentro de [-10mm, +10mm]) y selecciona sus aristas rectas horizontales superior e inferior.
            max_abs_y = max((max(abs(p1[1]), abs(p2[1])) for _, p1, p2 in all_edges), default=0.01)
            bodies = model.GetBodies2(0, True) or []
            seen_end_edges: set[tuple[float, float, float, float, float, float]] = set()
            for body in bodies:
                for face in com_call_0(body, "GetFaces") or []:
                    try:
                        surf = com_call_0(face, "GetSurface")
                        if surf is not None and not bool(com_call_0(surf, "IsPlane")):
                            continue
                        box = com_call_0(face, "GetBox")
                        if not box or len(box) < 6:
                            continue
                        f_ymin, f_ymax = float(box[1]), float(box[4])
                        f_height = f_ymax - f_ymin
                        # La cara plana debe abarcar el espesor del vaciado central sin tocar Y=±max_abs_y
                        if (
                            f_height > 0.001
                            and f_ymin > (-max_abs_y + 0.0005)
                            and f_ymax < (max_abs_y - 0.0005)
                        ):
                            for edge in com_call_0(face, "GetEdges") or []:
                                curve = com_call_0(edge, "GetCurve")
                                if curve is not None and not bool(com_call_0(curve, "IsLine")):
                                    continue
                                v1 = com_call_0(edge, "GetStartVertex")
                                v2 = com_call_0(edge, "GetEndVertex")
                                if v1 is None or v2 is None:
                                    continue
                                p1 = com_call_0(v1, "GetPoint")
                                p2 = com_call_0(v2, "GetPoint")
                                if not p1 or not p2 or len(p1) < 3 or len(p2) < 3:
                                    continue
                                if abs(float(p1[1]) - float(p2[1])) < 1e-4:
                                    pts = sorted([
                                        (round(float(p1[0]), 5), round(float(p1[1]), 5), round(float(p1[2]), 5)),
                                        (round(float(p2[0]), 5), round(float(p2[1]), 5), round(float(p2[2]), 5)),
                                    ])
                                    key = (pts[0][0], pts[0][1], pts[0][2], pts[1][0], pts[1][1], pts[1][2])
                                    if key not in seen_end_edges:
                                        seen_end_edges.add(key)
                                        candidate_edges.append(edge)
                    except Exception:
                        pass

        print(f"     -> Filtro fillet '{op.edges}': {len(candidate_edges)} arista(s) candidata(s) detectada(s)...")

        # Para horizontal_slot_ends donde 2*R suele igualar la altura del vaciado (ej. R5 en ranura de 10mm),
        # probamos primero 0.96*R para evitar que Parasolid rechace la desaparición total de la cara plana.
        radii_to_try = (
            [radius_m * 0.96, radius_m * 0.90, radius_m]
            if op.edges == "horizontal_slot_ends"
            else [radius_m, radius_m * 0.96]
        )

        for r_try in radii_to_try:
            model.ClearSelection2(True)
            for edge in candidate_edges:
                select_entity(model, edge, append=True, mark=1)
            model.FeatureFillet(float(r_try), False, False, False, 0)
            after_name, _ = get_last_solid_feature_name(model)
            if after_name != target_feat_name:
                model.ClearSelection2(True)
                return after_name

    # Modo 'last_feature' o 'all'
    _select_edges_of_last_feature(model, target_feat_name)
    for r_try in (radius_m, radius_m * 0.96):
        model.FeatureFillet(
            float(r_try),     # 1. R1: radio en metros
            True,             # 2. Propagate: propagación tangente
            False,            # 3. Ftyp: radio constante
            False,            # 4. VarRadTyp
            0,                # 5. OverflowType (0 = default)
        )
        after_name, _ = get_last_solid_feature_name(model)
        if after_name != target_feat_name:
            model.ClearSelection2(True)
            return after_name

    model.ClearSelection2(True)
    select_by_id(model, target_feat_name, "BODYFEATURE", 0.0, 0.0, 0.0, append=False, mark=1)
    model.FeatureFillet(float(radius_m), True, False, False, 0)
    after_name, _ = get_last_solid_feature_name(model)

    if after_name == target_feat_name:
        raise RuntimeError(
            f"Falló FeatureFillet ({op.radius_mm} mm, edges='{op.edges}') sobre la operación '{target_feat_name}'."
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


def _find_wrap_cylindrical_faces(
    model: Any,
    plane: str,
    plane_offset_mm: float,
    target_radius_mm: Optional[float],
) -> tuple[Any, list[Any]]:
    """
    Busca la(s) cara(s) cilíndrica(s) válida(s) cuyo eje sea perpendicular a la normal del croquis.
    Prioriza coincidencia con target_radius_mm (si se indicó) o el cilindro exterior de mayor radio,
    desempatando por orientación respecto a plane_offset_mm y área de cara.
    """
    plane_normals: dict[str, tuple[float, float, float]] = {
        "Front": (0.0, 0.0, 1.0),
        "Top": (0.0, 1.0, 0.0),
        "Right": (1.0, 0.0, 0.0),
    }
    p_norm = plane_normals.get(plane, (0.0, 0.0, 1.0))
    target_r_m = mm_to_m(target_radius_mm) if target_radius_mm is not None else None
    offset_sign = 1.0 if plane_offset_mm >= 0.0 else -1.0

    scored: list[tuple[tuple[float, float, float], float, Any]] = []
    bodies = model.GetBodies2(0, True) or []
    for body in bodies:
        for face in com_call_0(body, "GetFaces") or []:
            try:
                surf = com_call_0(face, "GetSurface")
                if surf is None or not bool(com_call_0(surf, "IsCylinder")):
                    continue
                cparams = com_call_0(surf, "CylinderParams")
                if not cparams or len(cparams) < 7:
                    continue
                ax, ay, az = float(cparams[3]), float(cparams[4]), float(cparams[5])
                radius_m = float(cparams[6])
                if abs(ax * p_norm[0] + ay * p_norm[1] + az * p_norm[2]) > 0.25:
                    continue

                face_area = float(com_call_0(face, "GetArea") or 0.0)
                box = com_call_0(face, "GetBox")
                side_proj = 0.0
                if box and len(box) >= 6:
                    fcx = 0.5 * (float(box[0]) + float(box[3]))
                    fcy = 0.5 * (float(box[1]) + float(box[4]))
                    fcz = 0.5 * (float(box[2]) + float(box[5]))
                    side_proj = offset_sign * (
                        fcx * p_norm[0] + fcy * p_norm[1] + fcz * p_norm[2]
                    )

                primary = (
                    round(abs(radius_m - target_r_m), 6)
                    if target_r_m is not None
                    else -round(radius_m, 6)
                )
                key = (primary, -round(side_proj, 6), -round(face_area, 8))
                scored.append((key, radius_m, face))
            except Exception:
                pass

    if not scored:
        raise RuntimeError(
            f"No se encontró ninguna cara cilíndrica válida paralela al plano '{plane}' para aplicar Wrap."
        )

    scored.sort(key=lambda item: item[0])
    best_radius_m = scored[0][1]
    best_face = scored[0][2]
    same_radius_faces = [f for _, r_m, f in scored if abs(r_m - best_radius_m) <= 2e-4]
    return best_face, same_radius_faces


def _try_insert_wrap_feature(
    model: Any,
    sketch_name: str,
    faces: list[Any],
    wrap_type: int,
    thickness_m: float,
    reverse_dir: bool,
    method: int,
) -> Any:
    """Selecciona el croquis (Mark=4) y la(s) cara(s) destino (Mark=1) e invoca InsertWrapFeature2."""
    model.ClearSelection2(True)
    if not select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=4):
        return None
    selected_faces = 0
    for face in faces:
        if select_entity(model, face, append=True, mark=1):
            selected_faces += 1
    if selected_faces == 0:
        return None

    return model.FeatureManager.InsertWrapFeature2(
        int(wrap_type),
        float(thickness_m),
        bool(reverse_dir),
        int(method),
        5,
    )


def execute_wrap(model: Any, op: WrapOperation) -> Any:
    """
    Ejecuta una operación de envoltura (IFeatureManager::InsertWrapFeature2) sobre una cara cilíndrica.
    Soporta modos 'deboss'/'engrave', 'emboss' y 'scribe', probando Analytical y SplineSurface.
    """
    wrap_type_map: dict[str, int] = {
        "emboss": SW_WRAP_TYPE_EMBOSS,
        "deboss": SW_WRAP_TYPE_ENGRAVE,
        "engrave": SW_WRAP_TYPE_ENGRAVE,
        "scribe": SW_WRAP_TYPE_SCRIBE,
    }
    wrap_type = wrap_type_map[op.mode]
    thickness_m = mm_to_m(op.depth_mm)

    sketch_name = build_sketch_on_plane(
        model,
        op.plane,
        op.sketch,
        plane_offset_mm=op.plane_offset_mm,
    )

    best_face, same_radius_faces = _find_wrap_cylindrical_faces(
        model,
        plane=op.plane,
        plane_offset_mm=op.plane_offset_mm,
        target_radius_mm=op.target_radius_mm,
    )

    rev_primary = bool(op.reverse_dir)
    attempts: list[tuple[list[Any], int, bool]] = [
        ([best_face], SW_WRAP_METHOD_ANALYTICAL, rev_primary),
        ([best_face], SW_WRAP_METHOD_SPLINE_SURFACE, rev_primary),
        ([best_face], SW_WRAP_METHOD_ANALYTICAL, not rev_primary),
        ([best_face], SW_WRAP_METHOD_SPLINE_SURFACE, not rev_primary),
    ]
    if len(same_radius_faces) > 1:
        attempts.append((same_radius_faces, SW_WRAP_METHOD_SPLINE_SURFACE, rev_primary))
        attempts.append((same_radius_faces, SW_WRAP_METHOD_SPLINE_SURFACE, not rev_primary))

    feat = None
    for target_faces, method, rev_dir in attempts:
        feat = _try_insert_wrap_feature(
            model=model,
            sketch_name=sketch_name,
            faces=target_faces,
            wrap_type=wrap_type,
            thickness_m=thickness_m,
            reverse_dir=rev_dir,
            method=method,
        )
        if feat is not None:
            break

    if feat is None:
        raise RuntimeError(
            f"Falló InsertWrapFeature2 (mode='{op.mode}', depth={op.depth_mm} mm) "
            f"para el croquis '{sketch_name}' en el plano '{op.plane}'. "
            "Verifica que el croquis sea un contorno cerrado contenido dentro de la cara cilíndrica."
        )

    model.ClearSelection2(True)
    return feat


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
    if isinstance(op, MirrorOperation):
        return execute_mirror(model, op, prev_op=prev_op)
    if isinstance(op, FilletOperation):
        return execute_fillet(model, op)
    if isinstance(op, ChamferOperation):
        return execute_chamfer(model, op)
    if isinstance(op, ShellOperation):
        return execute_shell(model, op)
    if isinstance(op, WrapOperation):
        return execute_wrap(model, op)
    raise ValueError(f"Tipo de operación no soportada: {type(op)}")


def _format_operation_summary(op: OperationType) -> str:
    """Genera una descripción legible de la operación para la consola."""
    if isinstance(op, CircularPatternOperation):
        return f"'{op.type}' ({op.instances} instancias a {op.angle_deg}° sobre eje '{op.axis}')"
    if isinstance(op, LinearPatternOperation):
        return f"'{op.type}' ({op.instances_x}x{op.instances_y} instancias)"
    if isinstance(op, MirrorOperation):
        return f"'{op.type}' (simetría respecto al plano '{op.plane}')"
    if isinstance(op, FilletOperation):
        return f"'{op.type}' (R{op.radius_mm:g} mm, edges='{op.edges}')"
    if isinstance(op, ChamferOperation):
        return f"'{op.type}' ({op.distance_mm:g} mm x {op.angle_deg:g}°)"
    if isinstance(op, ShellOperation):
        return f"'{op.type}' (espesor {op.thickness_mm:g} mm, cara abierta '{op.open_face}')"
    if isinstance(op, WrapOperation):
        offset_info = f" (offset {op.plane_offset_mm:g} mm)" if abs(op.plane_offset_mm) > 1e-6 else ""
        return f"'{op.type}' ({op.mode}, {op.depth_mm:g} mm en '{op.plane}'{offset_info}, {len(op.sketch.shapes)} figura(s))"
    offset_info = f" (offset {op.plane_offset_mm:g} mm)" if abs(op.plane_offset_mm) > 1e-6 else ""
    return f"'{op.type}' en plano '{op.plane}'{offset_info} ({len(op.sketch.shapes)} figura(s))"


def _optimize_operation_order(operations: list[OperationType]) -> list[OperationType]:
    """
    Reordena de forma segura bloques contiguos de cortes (ExtrudeCutOperation + sus patrones/espejos)
    para que los agujeros pasantes (through_all=True, ej. agujero central Ø50 en el origen 0,0)
    se ejecuten ANTES que los cortes parciales en cuña (through_all=False con vértice en 0,0).
    En geometría booleana CSG la resta es conmutativa ((B - C1) - C2 == (B - C2) - C1), y vaciar
    primero el centro evita que dos cuñas reflejadas generen espesor cero (Zero-Thickness) en (0,0).
    """
    units: list[list[OperationType]] = []
    for op in operations:
        if isinstance(op, (CircularPatternOperation, LinearPatternOperation, MirrorOperation)) and units:
            units[-1].append(op)
        else:
            units.append([op])

    optimized_units: list[list[OperationType]] = []
    cut_buffer: list[list[OperationType]] = []

    def _flush_cut_buffer() -> None:
        if not cut_buffer:
            return
        through_all_cuts = [
            u for u in cut_buffer if isinstance(u[0], ExtrudeCutOperation) and u[0].through_all
        ]
        partial_cuts = [
            u for u in cut_buffer if not (isinstance(u[0], ExtrudeCutOperation) and u[0].through_all)
        ]
        optimized_units.extend(through_all_cuts)
        optimized_units.extend(partial_cuts)
        cut_buffer.clear()

    for u in units:
        if isinstance(u[0], ExtrudeCutOperation):
            cut_buffer.append(u)
        else:
            _flush_cut_buffer()
            optimized_units.append(u)
    _flush_cut_buffer()

    return [op for u in optimized_units for op in u]


def build_part(part: CADPart) -> Any:
    """
    Orquesta la construcción completa de una pieza CADPart en SolidWorks 2018:
    - Conecta a SolidWorks 2018 y abre una pieza limpia.
    - Desactiva temporalmente swInputDimValOnCreate (enum 10) y swSketchInference (enum 249).
    - Optimiza el orden de cortes pasantes antes de cortes parciales para evitar espesor cero en (0,0).
    - Ejecuta secuencialmente cada croquis y operación 3D imprimiendo telemetría detallada.
    - Restaura las preferencias del usuario y ajusta la vista isométrica.
    """
    sw_app = connect_to_solidworks()
    model = create_new_part(sw_app)

    ordered_ops = _optimize_operation_order(part.operations)
    prev_dim_toggle = set_input_dim_on_create(sw_app, False)
    prev_op: Optional[OperationType] = None
    try:
        for idx, operation in enumerate(ordered_ops, start=1):
            print(f"  [{idx}/{len(ordered_ops)}] Ejecutando {_format_operation_summary(operation)}...")
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

