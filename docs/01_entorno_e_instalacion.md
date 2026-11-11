# 01. Entorno, Dependencias e Instalación en Nueva Máquina

## 1. Requisitos del Sistema
* **Sistema Operativo:** Windows 10 / 11 (64 bits).
* **CAD:** SolidWorks 2018 x64 instalado y registrado en COM (`ProgID: SldWorks.Application` / `SldWorks.Application.26`, `CLSID: {13551c8b-f74d-493e-b550-489532b7a905}`, `TypeLib: {83A33D31-27C5-11CE-BFD4-00400513BB57}` v26.0).
* **Python:** Python 3.10+ nativo de Windows (en la PC original se utiliza **Python 3.13.13** en `C:\Python313\python.exe`).

---

## 2. Librerías Instaladas (`requirements.txt`)

| Paquete | Versión mínima | Versión instalada (PC original) | Para qué sirve |
| :--- | :--- | :--- | :--- |
| `pywin32` | `>=306` | `312` | Provee `pythoncom` y `win32com.client` para comunicarse con la API COM de SolidWorks 2018. |
| `pydantic` | `>=2.7.0` | `2.13.4` / `2.14.3` | Valida estrictamente el esquema JSON intermedio (`schemas/cad_schema.py`) antes de tocar SolidWorks. |
| `google-genai` | `>=1.0.0` | `3.1.0` | SDK oficial de Google Gemini para analizar imágenes de croquis con Structured Outputs (Fase 2). |
| `pillow` | `>=10.0.0` | `11.3.0` / `13.0.0` | Carga y preprocesamiento de imágenes `.png`/`.jpg` de los croquis (Fase 2). |
| `python-dotenv` | `>=1.0.0` | `1.2.2` / `1.2.4` | Carga la variable `GEMINI_API_KEY` desde el archivo `.env` (Fase 2). |

---

## 3. Particularidades Críticas Detectadas en Windows (Para IA / Instaladores)

### A. Conflicto de `PATH` con MSYS2 / MinGW (`python` vs `py`)
* **Qué se detectó:** En máquinas que tienen instalado **MSYS2** (`C:\msys64\ucrt64\bin\python.exe` o `mingw64`), el comando `python` a secas en consola suele resolver al Python de MSYS2 en lugar del Python nativo de Windows.
* **Por qué es un problema:** El Python de MSYS2 muchas veces no trae `pip` activado ni soporta limpiamente `pywin32` para automatización COM nativa.
* **Regla de instalación:** Verificar siempre con `where.exe python` y `py -0p`. Usar siempre el lanzador oficial de Windows (`py`) o la ruta explícita al Python nativo (ej. `C:\Python313\python.exe`).

### B. Instalación Dual: `.venv` + Python Global (Soporte para Python IDLE)
* **Qué se hizo:** Se instalaron los paquetes tanto dentro del entorno virtual del proyecto (`.venv`) como en el Python global (`C:\Python313\python.exe`).
* **Por qué:** Cuando el usuario abre `test_engine.py` con **Python IDLE** y presiona **F5**, IDLE ejecuta con el intérprete global (`C:\Python313\python.exe`), ignorando `.venv`. Tener las dependencias instaladas en ambos permite ejecutar el proyecto indistintamente desde **IDLE (F5)** o desde **CMD/PowerShell (`.venv`)**.

### C. Aislamiento de Escritorio (`Window Desktop`) en Terminales de Agentes IA
* **Qué se detectó:** Las terminales integradas de ciertos agentes de IA corren en un escritorio aislado de Windows (`Desktop: exebox-...` dentro de `WinSta0`), mientras que SolidWorks 2018 corre en el escritorio interactivo del usuario (`Desktop: Default`).
* **Por qué importa:** En Windows, la tabla de objetos activos COM (`Running Object Table` / `ROT`) está aislada por escritorio. Un script lanzado desde un escritorio aislado recibe `MK_E_UNAVAILABLE (-2147221021)` aunque SolidWorks esté abierto.
* **Regla:** Los scripts que se conectan en vivo a SolidWorks (`test_engine.py`, `main.py`) deben ejecutarse desde la sesión interactiva del usuario (**Python IDLE**, **CMD** o **PowerShell** abierto en el escritorio normal).

---

## 4. Receta de Instalación Paso a Paso en una Máquina Nueva

Si una IA o desarrollador debe instalar este proyecto desde cero en otra PC:

```powershell
# 1. Ir a la carpeta del repositorio
cd D:\ruta\a\sketch2solid

# 2. Verificar que exista el Python nativo de Windows
py -0p

# 3. Crear entorno virtual con el Python nativo de Windows
py -m venv .venv

# 4. Instalar dependencias en el entorno virtual (.venv)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 5. (Opcional pero recomendado si se usa Python IDLE) Instalar también en el Python global
py -m pip install -r requirements.txt

# 6. Verificar que las 5 librerías importen sin errores
.\.venv\Scripts\python.exe -c "import pythoncom, win32com.client, pydantic, google.genai, PIL, dotenv; print('OK')"
```

