# Documentación Técnica de Sketch2Solid (Guía para IA y Desarrolladores)

Esta carpeta centraliza todo el conocimiento técnico, decisiones de arquitectura, configuración de entorno y soluciones a errores reales encontrados durante el desarrollo de **Sketch2Solid** contra **SolidWorks 2018**.

> **Propósito para Agentes de IA:** Si estás leyendo este repositorio para instalarlo en una nueva PC, depurar un fallo o continuar con una nueva fase, lee estos documentos en orden antes de modificar código o ejecutar comandos.

---

## Estructura de la Documentación (Separada por Responsabilidad)

1. **[01_entorno_e_instalacion.md](./01_entorno_e_instalacion.md)**
   * **Responsabilidad:** Configuración de Python en Windows, dependencias instaladas, conflicto con MSYS2 en el `PATH`, soporte para Python IDLE vs. `.venv`, y aislamiento de escritorio (`Window Desktop`) al conectar por COM.
   * **Cuándo leerlo:** Al instalar el proyecto en otra máquina o si fallan las importaciones (`pydantic`, `pythoncom`, `win32com`, `google.genai`).

2. **[02_motor_solidworks_com.md](./02_motor_solidworks_com.md)**
   * **Responsabilidad:** Reglas técnicas obligatorias de la API COM de SolidWorks 2018 (`sw_engine`), firma exacta de métodos (`SelectByID2`, `FeatureExtrusion2`, `FeatureCut3`), manejo de unidades (`mm` a `m`), selección de planos multilenguaje y el helper crítico `com_call_0`.
   * **Cuándo leerlo:** Antes de tocar cualquier archivo dentro de `sw_engine/` o agregar nuevas operaciones CAD.

3. **[03_bitacora_errores_y_soluciones.md](./03_bitacora_errores_y_soluciones.md)**
   * **Responsabilidad:** Historial cronológico de cada error real encontrado, su diagnóstico de causa raíz a bajo nivel y cómo se solucionó.
   * **Cuándo leerlo:** Cuando aparezca un error COM (`-2147352573`, `-2147221021`, `Type Mismatch`, corte fallido, etc.) para no repetir diagnósticos ya resueltos.

4. **[04_flujo_chat_sin_api.md](./04_flujo_chat_sin_api.md)**
   * **Responsabilidad:** Flujo de uso gratuito (\$0 en API) mediante cualquier chat web (ChatGPT, Gemini, Claude) usando `PROMPT_PARA_CHAT.txt`, `pieza.json`, la interfaz gráfica `main.py` y el lanzador `iniciar_sketch2solid.bat`.
   * **Cuándo leerlo:** Al modificar el prompt maestro, el esquema Pydantic o la interfaz gráfica local.

---

## Estado Actual del Proyecto

* **Fase 1 + Expansión Geométrica 80/20 (Completadas):**
  * Esquemas Pydantic en `schemas/cad_schema.py` con **10 operaciones 3D** (`extrude_boss`, `extrude_cut`, `revolve_boss`, `revolve_cut`, `circular_pattern`, `linear_pattern`, `mirror`, `fillet` con filtro inteligente de aristas `edges`, `chamfer`, `shell`), **7 primitivas 2D** (`center_rectangle`, `corner_rectangle`, `circle`, `line`, `polygon`, `arc`, `slot`), **planos paralelos desfasados** (`plane_offset_mm`) y **corte bilateral** (`both_directions`).
  * Motor de ejecución local `sw_engine` conectado a SolidWorks 2018 (`connection.py`, `primitives.py`, `features.py`).
  * Script de prueba `test_engine.py` y archivo de ejemplo `pieza.json` (`Cilindro_6_Ventanas_60mm`).
* **Modo Chat sin API (Completado):**
  * Prompt maestro listo para copiar y pegar (`PROMPT_PARA_CHAT.txt`).
  * Ventana gráfica en `main.py` (y acceso directo `iniciar_sketch2solid.bat`) para copiar el prompt, pegar el JSON devuelto por cualquier IA, limpiarlo, validarlo con Pydantic y construirlo en SolidWorks 2018.
* **Fase 2 API Directa (Opcional / Futura):**
  * Implementación de `ai/vision_agent.py` en caso de querer automatizar la llamada directa por API en el futuro.

