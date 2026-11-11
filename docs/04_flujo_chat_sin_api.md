# 04. Flujo Manual por Chat Web sin Costo de API (`main.py` + `PROMPT_PARA_CHAT.txt`)

## 1. Por qué se diseñó este flujo
* **Motivación:** Evitar el costo de uso de una API paga (como Gemini API o OpenAI API) durante el uso cotidiano o prototipado, aprovechando cualquier chat gratuito con capacidad de visión (ChatGPT Web, Gemini Web, Claude, etc.).
* **Desafío Técnico Resuelto:** Cuando se usa la API por código, el esquema Pydantic (`schemas/cad_schema.py`) se inyecta automáticamente en el parámetro `response_schema`. En cambio, en un chat web la IA no conoce los nombres de los campos ni las restricciones de nuestro motor local a menos que estén explícitamente definidos dentro del texto del prompt.

---

## 2. Componentes Creados

1. **[PROMPT_PARA_CHAT.txt](../PROMPT_PARA_CHAT.txt)** (y sincronizado en **[ai/system_prompt.md](../ai/system_prompt.md)**):
   * Contiene las reglas geométricas (origen en `(0,0)`, todas las medidas en milímetros, conversión obligatoria de radios `R` a `"diameter"`, secuencia constructiva sustractiva) y la **especificación exacta del esquema JSON** (`part_name`, `operations`, `plane: "Front" | "Top" | "Right"`, `extrude_boss`, `extrude_cut`, `center_rectangle`, `corner_rectangle`, `circle`, `line`).
2. **[pieza.json](../pieza.json)**:
   * Archivo JSON activo donde se guarda la última pieza validada y ejecutada.
3. **[main.py](../main.py)**:
   * Interfaz gráfica local con **Tkinter** (no requiere librerías externas) que permite:
     * **Botón `1. Copiar Prompt Maestro`:** Copia automáticamente `PROMPT_PARA_CHAT.txt` al portapapeles de Windows.
     * **Botón `2. Pegar JSON del Portapapeles`:** Toma la respuesta copiada del chat de IA y pasa por `clean_json_text()`, que elimina bloques Markdown (` ```json ... ``` `) o texto conversacional antes/después de las llaves `{ ... }`.
     * **Botón `Validar JSON`:** Valida la estructura contra `CADPart` (`schemas/cad_schema.py`) e informa cuántas operaciones y figuras se detectaron.
     * **Botón `3. Construir en SolidWorks 2018`:** Valida el JSON, lo guarda en `pieza.json` y llama a `build_part(part)` de `sw_engine` para construir la pieza en vivo en SolidWorks 2018.
   * También soporta ejecución directa por consola: `py main.py --file pieza.json`.
4. **[iniciar_sketch2solid.bat](../iniciar_sketch2solid.bat)**:
   * Acceso directo ejecutable con doble clic desde el Explorador de Windows que abre la ventana gráfica de `main.py` sin necesidad de abrir consola ni IDLE.

