import json
import sys
import traceback
from schemas.cad_schema import CADPart
from sw_engine import build_part, com_call_0

SAMPLE_PART_JSON = """
{
  "part_name": "Placa_Base_Perforada_100x50x8",
  "operations": [
    {
      "type": "extrude_boss",
      "plane": "Front",
      "depth_mm": 8.0,
      "sketch": {
        "shapes": [
          {
            "kind": "center_rectangle",
            "cx": 0.0,
            "cy": 0.0,
            "width": 100.0,
            "height": 50.0
          }
        ]
      }
    },
    {
      "type": "extrude_cut",
      "plane": "Front",
      "through_all": true,
      "sketch": {
        "shapes": [
          {
            "kind": "circle",
            "cx": -40.0,
            "cy": 15.0,
            "diameter": 6.0
          },
          {
            "kind": "circle",
            "cx": 40.0,
            "cy": 15.0,
            "diameter": 6.0
          },
          {
            "kind": "circle",
            "cx": -40.0,
            "cy": -15.0,
            "diameter": 6.0
          },
          {
            "kind": "circle",
            "cx": 40.0,
            "cy": -15.0,
            "diameter": 6.0
          }
        ]
      }
    }
  ]
}
"""


def main() -> int:
    print("=" * 60)
    print(" Sketch2Solid - Fase 1: Test del Motor Local (sw_engine)")
    print("=" * 60)

    # 1. Validar el JSON de prueba con el esquema Pydantic
    print("\n[1/2] Validando payload JSON con Pydantic...")
    part = CADPart.model_validate_json(SAMPLE_PART_JSON)
    print(f"  -> Pieza validada: '{part.part_name}' ({len(part.operations)} operaciones)")
    print(json.dumps(part.model_dump(), indent=2, ensure_ascii=False))

    # 2. Ejecutar la construcción en vivo en SolidWorks 2018
    print("\n[2/2] Conectando a SolidWorks 2018 y construyendo pieza en vivo...")
    model = build_part(part)
    try:
        doc_title = str(com_call_0(model, "GetTitle"))
    except Exception:
        doc_title = part.part_name
    print(f"\n[OK] Pieza generada exitosamente en SolidWorks 2018 (Documento: '{doc_title}').")
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(f"\n[ERROR] {err}", file=sys.stderr)
        traceback.print_exc()

