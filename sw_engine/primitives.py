from typing import Any
from schemas.cad_schema import (
    CenterRectangle,
    Circle,
    CornerRectangle,
    Line,
    ShapeType,
    Sketch,
)
from .connection import com_call_0, mm_to_m, select_by_id, select_reference_plane


def draw_shape(sketch_mgr: Any, shape: ShapeType) -> Any:
    """
    Dibuja una primitiva 2D individual dentro del croquis activo de SolidWorks.
    Convierte automáticamente todas las coordenadas y dimensiones de milímetros a metros.
    """
    if isinstance(shape, CenterRectangle):
        cx_m = mm_to_m(shape.cx)
        cy_m = mm_to_m(shape.cy)
        corner_x_m = mm_to_m(shape.cx + (shape.width / 2.0))
        corner_y_m = mm_to_m(shape.cy + (shape.height / 2.0))
        return sketch_mgr.CreateCenterRectangle(
            cx_m, cy_m, 0.0, corner_x_m, corner_y_m, 0.0
        )

    if isinstance(shape, CornerRectangle):
        x1_m = mm_to_m(shape.x1)
        y1_m = mm_to_m(shape.y1)
        x2_m = mm_to_m(shape.x2)
        y2_m = mm_to_m(shape.y2)
        return sketch_mgr.CreateCornerRectangle(
            x1_m, y1_m, 0.0, x2_m, y2_m, 0.0
        )

    if isinstance(shape, Circle):
        cx_m = mm_to_m(shape.cx)
        cy_m = mm_to_m(shape.cy)
        radius_m = mm_to_m(shape.diameter / 2.0)
        return sketch_mgr.CreateCircleByRadius(cx_m, cy_m, 0.0, radius_m)

    if isinstance(shape, Line):
        x1_m = mm_to_m(shape.x1)
        y1_m = mm_to_m(shape.y1)
        x2_m = mm_to_m(shape.x2)
        y2_m = mm_to_m(shape.y2)
        return sketch_mgr.CreateLine(x1_m, y1_m, 0.0, x2_m, y2_m, 0.0)

    raise ValueError(f"Tipo de figura de croquis no soportado: {type(shape)}")


def get_last_sketch_name(model: Any) -> str:
    """Obtiene el nombre del último croquis ('ProfileFeature') en el árbol del FeatureManager."""
    last_sketch_name = ""
    feat = com_call_0(model, "FirstFeature")
    while feat is not None:
        if com_call_0(feat, "GetTypeName2") == "ProfileFeature":
            last_sketch_name = str(com_call_0(feat, "Name"))
        feat = com_call_0(feat, "GetNextFeature")

    if not last_sketch_name:
        try:
            last_feat = model.FeatureByPositionReverse(0)
            if last_feat is not None:
                last_sketch_name = str(com_call_0(last_feat, "Name"))
        except Exception:
            pass

    return last_sketch_name


def build_sketch_on_plane(model: Any, plane: str, sketch: Sketch) -> str:
    """
    1. Selecciona el plano de referencia (multilenguaje Español/Inglés).
    2. Abre un nuevo croquis 2D con SketchManager.InsertSketch(True).
    3. Envuelve las llamadas de dibujo entre SketchManager.AddToDB = True y False
       (evita que se quede abierto el PropertyManager uiSkRectangleProp_c en la UI).
    4. Cierra el croquis con SketchManager.InsertSketch(True) ANTES de la operación 3D.
    5. Deja seleccionado el croquis recién cerrado y devuelve su nombre.
    """
    select_reference_plane(model, plane)

    sketch_mgr = model.SketchManager
    # Abrir croquis sobre el plano seleccionado
    sketch_mgr.InsertSketch(True)

    # Dibujar con AddToDB = True para no abrir paneles PropertyManager (uiSkRectangleProp_c)
    sketch_mgr.AddToDB = True
    try:
        for shape in sketch.shapes:
            draw_shape(sketch_mgr, shape)
    finally:
        sketch_mgr.AddToDB = False

    try:
        com_call_0(model, "SetPickMode")
    except Exception:
        pass

    # Limpiar selección de entidades internas antes de salir del croquis
    model.ClearSelection2(True)

    # Cerrar el croquis ANTES de llamar al FeatureManager
    sketch_mgr.InsertSketch(True)

    # Identificar y seleccionar el croquis cerrado para la operación 3D subsiguiente
    sketch_name = get_last_sketch_name(model)
    if sketch_name:
        select_by_id(model, sketch_name, "SKETCH", 0.0, 0.0, 0.0, append=False, mark=0)

    return sketch_name

