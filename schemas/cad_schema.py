from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

PlaneType = Literal["Front", "Top", "Right"]
AxisType = Literal["X", "Y", "Z"]


class CenterRectangle(BaseModel):
    """Rectángulo definido por su centro (cx, cy) y sus dimensiones (width, height) en mm."""

    kind: Literal["center_rectangle"] = "center_rectangle"
    cx: float = Field(default=0.0, description="Coordenada X del centro en milímetros (mm)")
    cy: float = Field(default=0.0, description="Coordenada Y del centro en milímetros (mm)")
    width: float = Field(..., gt=0.0, description="Ancho total (eje X) en milímetros (mm)")
    height: float = Field(..., gt=0.0, description="Alto total (eje Y) en milímetros (mm)")


class CornerRectangle(BaseModel):
    """Rectángulo definido por dos esquinas opuestas (x1, y1) y (x2, y2) en mm."""

    kind: Literal["corner_rectangle"] = "corner_rectangle"
    x1: float = Field(..., description="Coordenada X de la primera esquina en mm")
    y1: float = Field(..., description="Coordenada Y de la primera esquina en mm")
    x2: float = Field(..., description="Coordenada X de la esquina opuesta en mm")
    y2: float = Field(..., description="Coordenada Y de la esquina opuesta en mm")


class Circle(BaseModel):
    """Círculo definido por su centro (cx, cy) y su diámetro en mm."""

    kind: Literal["circle"] = "circle"
    cx: float = Field(default=0.0, description="Coordenada X del centro en milímetros (mm)")
    cy: float = Field(default=0.0, description="Coordenada Y del centro en milímetros (mm)")
    diameter: float = Field(..., gt=0.0, description="Diámetro del círculo en milímetros (mm)")


class Line(BaseModel):
    """Segmento de línea recta entre (x1, y1) y (x2, y2) en mm."""

    kind: Literal["line"] = "line"
    x1: float = Field(..., description="Coordenada X inicial en mm")
    y1: float = Field(..., description="Coordenada Y inicial en mm")
    x2: float = Field(..., description="Coordenada X final en mm")
    y2: float = Field(..., description="Coordenada Y final en mm")


class Polygon(BaseModel):
    """Polígono regular (ej. hexágono) definido por centro, diámetro, cantidad de lados e inscrito/circunscrito."""

    kind: Literal["polygon"] = "polygon"
    cx: float = Field(default=0.0, description="Coordenada X del centro en mm")
    cy: float = Field(default=0.0, description="Coordenada Y del centro en mm")
    diameter: float = Field(..., gt=0.0, description="Diámetro del círculo inscrito/circunscrito en mm")
    sides: int = Field(default=6, ge=3, le=100, description="Número de lados del polígono (ej. 6 para hexágono)")
    inscribed: bool = Field(default=True, description="True = inscrito, False = circunscrito")


class Arc(BaseModel):
    """Arco circular definido por centro (cx, cy), punto inicial (x1, y1), punto final (x2, y2) y sentido."""

    kind: Literal["arc"] = "arc"
    cx: float = Field(default=0.0, description="Coordenada X del centro del arco en mm")
    cy: float = Field(default=0.0, description="Coordenada Y del centro del arco en mm")
    x1: float = Field(..., description="Coordenada X del punto inicial del arco en mm")
    y1: float = Field(..., description="Coordenada Y del punto inicial del arco en mm")
    x2: float = Field(..., description="Coordenada X del punto final del arco en mm")
    y2: float = Field(..., description="Coordenada Y del punto final del arco en mm")
    direction: Literal[1, -1] = Field(default=1, description="Sentido del arco: 1 = antihorario, -1 = horario")


class Slot(BaseModel):
    """Ranura recta (agujero coliso) definida entre centros (x1, y1) y (x2, y2) con ancho width en mm."""

    kind: Literal["slot"] = "slot"
    x1: float = Field(..., description="Coordenada X del primer centro de la ranura en mm")
    y1: float = Field(..., description="Coordenada Y del primer centro de la ranura en mm")
    x2: float = Field(..., description="Coordenada X del segundo centro de la ranura en mm")
    y2: float = Field(..., description="Coordenada Y del segundo centro de la ranura en mm")
    width: float = Field(..., gt=0.0, description="Ancho total (diámetro de los extremos) de la ranura en mm")


ShapeType = Annotated[
    Union[CenterRectangle, CornerRectangle, Circle, Line, Polygon, Arc, Slot],
    Field(discriminator="kind"),
]


class Sketch(BaseModel):
    """Croquis 2D compuesto por una lista de primitivas geométricas."""

    shapes: list[ShapeType] = Field(
        ...,
        min_length=1,
        description="Lista de figuras geométricas 2D que componen el croquis",
    )


class AxisLine(BaseModel):
    """Línea constructiva (eje de revolución) dentro del croquis en mm."""

    x1: float = Field(default=0.0, description="Coordenada X inicial del eje en mm")
    y1: float = Field(default=0.0, description="Coordenada Y inicial del eje en mm")
    x2: float = Field(default=0.0, description="Coordenada X final del eje en mm")
    y2: float = Field(default=50.0, description="Coordenada Y final del eje en mm")


class ExtrudeBossOperation(BaseModel):
    """Operación 3D de extrusión de saliente/base (agrega material)."""

    type: Literal["extrude_boss"] = "extrude_boss"
    plane: PlaneType = Field(
        default="Front",
        description="Plano de referencia donde se abre el croquis ('Front', 'Top', 'Right')",
    )
    plane_offset_mm: float = Field(
        default=0.0,
        description="Desfase en mm para crear un plano paralelo de referencia (0.0 = usar plano base directo)",
    )
    depth_mm: float = Field(
        ...,
        gt=0.0,
        description="Profundidad de extrusión en milímetros (mm)",
    )
    midplane: bool = Field(
        default=False,
        description="Si es True, extruye simétricamente hacia ambos lados del plano (Plano medio)",
    )
    both_directions: bool = Field(
        default=False,
        description="Si es True, extruye hacia ambos lados desde el plano del croquis",
    )
    sketch: Sketch


class ExtrudeCutOperation(BaseModel):
    """Operación 3D de corte extruido (quita material)."""

    type: Literal["extrude_cut"] = "extrude_cut"
    plane: PlaneType = Field(
        default="Front",
        description="Plano de referencia donde se abre el croquis ('Front', 'Top', 'Right')",
    )
    plane_offset_mm: float = Field(
        default=0.0,
        description="Desfase en mm para crear un plano paralelo de referencia (0.0 = usar plano base directo)",
    )
    through_all: bool = Field(
        default=True,
        description="Si es True, el corte atraviesa toda la pieza ('Por todo')",
    )
    both_directions: bool = Field(
        default=False,
        description="Si es True, corta hacia AMBOS lados desde el plano del croquis (Sd=False, T2=ThroughAll)",
    )
    depth_mm: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Profundidad de corte en mm (requerido cuando through_all=False)",
    )
    sketch: Sketch

    @model_validator(mode="after")
    def validate_cut_depth(self) -> "ExtrudeCutOperation":
        if not self.through_all and self.depth_mm is None:
            raise ValueError("Se debe especificar 'depth_mm' cuando 'through_all' es False.")
        return self


class RevolveBossOperation(BaseModel):
    """Operación 3D de revolución de saliente/base alrededor de una línea constructiva."""

    type: Literal["revolve_boss"] = "revolve_boss"
    plane: PlaneType = Field(
        default="Front",
        description="Plano de referencia donde se abre el croquis ('Front', 'Top', 'Right')",
    )
    plane_offset_mm: float = Field(
        default=0.0,
        description="Desfase en mm para crear un plano paralelo de referencia",
    )
    angle_deg: float = Field(
        default=360.0,
        gt=0.0,
        le=360.0,
        description="Ángulo de revolución en grados (por defecto 360°)",
    )
    axis_line: AxisLine = Field(
        default_factory=AxisLine,
        description="Línea constructiva que actúa como eje de revolución",
    )
    sketch: Sketch


class RevolveCutOperation(BaseModel):
    """Operación 3D de corte por revolución alrededor de una línea constructiva."""

    type: Literal["revolve_cut"] = "revolve_cut"
    plane: PlaneType = Field(
        default="Front",
        description="Plano de referencia donde se abre el croquis ('Front', 'Top', 'Right')",
    )
    plane_offset_mm: float = Field(
        default=0.0,
        description="Desfase en mm para crear un plano paralelo de referencia",
    )
    angle_deg: float = Field(
        default=360.0,
        gt=0.0,
        le=360.0,
        description="Ángulo de corte por revolución en grados (por defecto 360°)",
    )
    axis_line: AxisLine = Field(
        default_factory=AxisLine,
        description="Línea constructiva que actúa como eje de revolución",
    )
    sketch: Sketch


class CircularPatternOperation(BaseModel):
    """Operación 3D de matriz circular sobre la última operación 3D creada."""

    type: Literal["circular_pattern"] = "circular_pattern"
    instances: int = Field(
        ...,
        ge=2,
        description="Cantidad total de instancias en la matriz circular (ej. 6)",
    )
    angle_deg: float = Field(
        default=360.0,
        gt=0.0,
        le=360.0,
        description="Ángulo total abarcado por la matriz en grados (por defecto 360°)",
    )
    axis: AxisType = Field(
        default="Y",
        description="Eje central de rotación ('Y' = intersección Front/Right, 'Z' = Top/Right, 'X' = Front/Top)",
    )
    equal_spacing: bool = Field(
        default=True,
        description="Si es True, reparte las instancias equitativamente en angle_deg",
    )


class LinearPatternOperation(BaseModel):
    """Operación 3D de matriz lineal en dirección X y/o Y sobre la última operación 3D creada."""

    type: Literal["linear_pattern"] = "linear_pattern"
    instances_x: int = Field(default=1, ge=1, description="Cantidad de instancias en dirección X")
    spacing_x_mm: float = Field(default=10.0, gt=0.0, description="Separación entre instancias en X (mm)")
    instances_y: int = Field(default=1, ge=1, description="Cantidad de instancias en dirección Y")
    spacing_y_mm: float = Field(default=10.0, gt=0.0, description="Separación entre instancias en Y (mm)")


class FilletOperation(BaseModel):
    """Operación 3D de redondeo constante sobre las aristas de la última operación 3D."""

    type: Literal["fillet"] = "fillet"
    radius_mm: float = Field(..., gt=0.0, description="Radio del redondeo en milímetros (mm)")


class ChamferOperation(BaseModel):
    """Operación 3D de chaflán (distancia y ángulo) sobre las aristas de la última operación 3D."""

    type: Literal["chamfer"] = "chamfer"
    distance_mm: float = Field(..., gt=0.0, description="Distancia o ancho del chaflán en milímetros (mm)")
    angle_deg: float = Field(default=45.0, gt=0.0, lt=90.0, description="Ángulo del chaflán en grados (por defecto 45°)")


class ShellOperation(BaseModel):
    """Operación 3D de vaciado (carcasa de pared delgada) eliminando la cara exterior indicada."""

    type: Literal["shell"] = "shell"
    thickness_mm: float = Field(..., gt=0.0, description="Espesor de pared del vaciado en milímetros (mm)")
    open_face: Literal["Top", "Bottom", "Front", "Back", "Right", "Left"] = Field(
        default="Top",
        description="Cara exterior a eliminar para abrir la carcasa ('Top', 'Bottom', 'Front', 'Back', 'Right', 'Left')",
    )
    outward: bool = Field(default=False, description="Si es True, agrega el espesor hacia afuera")


OperationType = Annotated[
    Union[
        ExtrudeBossOperation,
        ExtrudeCutOperation,
        RevolveBossOperation,
        RevolveCutOperation,
        CircularPatternOperation,
        LinearPatternOperation,
        FilletOperation,
        ChamferOperation,
        ShellOperation,
    ],
    Field(discriminator="type"),
]


class CADPart(BaseModel):
    """Representación intermedia de una pieza 3D parametrizada para SolidWorks."""

    part_name: str = Field(
        default="Pieza_Sketch2Solid",
        description="Nombre identificador de la pieza",
    )
    operations: list[OperationType] = Field(
        ...,
        min_length=1,
        description="Secuencia cronológica de operaciones constructivas 3D",
    )
