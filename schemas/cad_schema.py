from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

PlaneType = Literal["Front", "Top", "Right"]


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


ShapeType = Annotated[
    Union[CenterRectangle, CornerRectangle, Circle, Line],
    Field(discriminator="kind"),
]


class Sketch(BaseModel):
    """Croquis 2D compuesto por una lista de primitivas geométricas."""

    shapes: list[ShapeType] = Field(
        ...,
        min_length=1,
        description="Lista de figuras geométricas 2D que componen el croquis",
    )


class ExtrudeBossOperation(BaseModel):
    """Operación 3D de extrusión de saliente/base (agrega material)."""

    type: Literal["extrude_boss"] = "extrude_boss"
    plane: PlaneType = Field(
        default="Front",
        description="Plano de referencia donde se abre el croquis ('Front', 'Top', 'Right')",
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
    sketch: Sketch


class ExtrudeCutOperation(BaseModel):
    """Operación 3D de corte extruido (quita material)."""

    type: Literal["extrude_cut"] = "extrude_cut"
    plane: PlaneType = Field(
        default="Front",
        description="Plano de referencia donde se abre el croquis ('Front', 'Top', 'Right')",
    )
    through_all: bool = Field(
        default=True,
        description="Si es True, el corte atraviesa toda la pieza ('Por todo')",
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


OperationType = Annotated[
    Union[ExtrudeBossOperation, ExtrudeCutOperation],
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

