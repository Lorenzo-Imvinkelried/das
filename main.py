import argparse
import gc
import importlib
import json
import os
from pathlib import Path
import re
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext
import traceback
from typing import Any

import schemas
import schemas.cad_schema
import sw_engine
import sw_engine.compat
import sw_engine.versions
import sw_engine.versions.base
import sw_engine.connection
import sw_engine.primitives
import sw_engine.features
from sw_engine import (
    SUPPORTED_SW_MAX_YEAR,
    SUPPORTED_SW_MIN_YEAR,
    com_call_0,
    connect_to_solidworks,
    get_connected_adapter,
    get_connected_constants,
    get_connected_version_info,
    list_installed_solidworks_versions,
)

APP_NAME = "Sketch2Solid"
IS_FROZEN = bool(getattr(sys, "frozen", False))


def get_resource_dir() -> Path:
    """Devuelve la carpeta de recursos de solo lectura (compatible con desarrollo y PyInstaller/Nuitka)."""
    if IS_FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _is_dir_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".sketch2solid_write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def get_user_data_dir() -> Path:
    """
    Devuelve la carpeta escribible para pieza.json y ultimo_log.txt.
    - En ejecutables empaquetados (ej. instalados en C:\\Program Files\\Sketch2Solid):
      usa %LOCALAPPDATA%\\Sketch2Solid para evitar PermissionError.
    - En modo desarrollo desde código fuente: usa la carpeta del repositorio si es escribible.
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    fallback_dir = (
        Path(local_app_data) / APP_NAME
        if local_app_data
        else (Path.home() / "AppData" / "Local" / APP_NAME)
    )
    if IS_FROZEN:
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir

    source_dir = Path(__file__).resolve().parent
    if _is_dir_writable(source_dir):
        return source_dir

    fallback_dir.mkdir(parents=True, exist_ok=True)
    return fallback_dir


def resolve_prompt_path() -> Path:
    """Localiza PROMPT_PARA_CHAT.txt tanto en código fuente como dentro de un instalador congelado."""
    candidates = [
        RESOURCE_DIR / "PROMPT_PARA_CHAT.txt",
        Path(sys.executable).resolve().parent / "PROMPT_PARA_CHAT.txt",
        USER_DATA_DIR / "PROMPT_PARA_CHAT.txt",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


RESOURCE_DIR = get_resource_dir()
USER_DATA_DIR = get_user_data_dir()
BASE_DIR = RESOURCE_DIR
DEFAULT_JSON_PATH = USER_DATA_DIR / "pieza.json"
BUNDLED_SAMPLE_JSON_PATH = RESOURCE_DIR / "pieza.json"
PROMPT_FILE_PATH = resolve_prompt_path()
LAST_LOG_PATH = USER_DATA_DIR / "ultimo_log.txt"


class _GuiLogStream:
    """Redirige print() en tiempo real hacia el cuadro de registro de la GUI y ultimo_log.txt."""

    def __init__(self, app: "Sketch2SolidApp", fallback_stream: Any) -> None:
        self.app = app
        self.fallback_stream = fallback_stream
        self._buffer = ""

    def write(self, data: str) -> int:
        if self.fallback_stream is not None:
            try:
                self.fallback_stream.write(data)
            except Exception:
                pass
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.app.log(line)
        return len(data)

    def flush(self) -> None:
        if self._buffer.strip():
            self.app.log(self._buffer.rstrip("\n"))
            self._buffer = ""
        if self.fallback_stream is not None:
            try:
                self.fallback_stream.flush()
            except Exception:
                pass


def reload_engine_modules() -> None:
    """
    Recarga en caliente los módulos del esquema y motor COM desde disco en modo desarrollo.
    En modo ejecutable empaquetado (PyInstaller/Nuitka, sys.frozen=True) se omite de forma segura.
    """
    if IS_FROZEN:
        return
    importlib.reload(schemas.cad_schema)
    importlib.reload(schemas)
    importlib.reload(sw_engine.compat)
    importlib.reload(sw_engine.versions.base)
    for year in range(2017, 2027):
        mod_name = f"sw_engine.versions.sw_{year}"
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
    importlib.reload(sw_engine.versions)
    importlib.reload(sw_engine.connection)
    importlib.reload(sw_engine.primitives)
    importlib.reload(sw_engine.features)
    importlib.reload(sw_engine)


def clean_json_text(raw_text: str) -> str:
    """
    Limpia el texto copiado desde un chat de IA (ChatGPT, Gemini, Claude, etc.):
    - Quita bloques markdown ```json ... ``` si existen.
    - Extrae el bloque JSON principal entre la primera '{' y la última '}'.
    """
    text = raw_text.strip()

    # Si viene envuelto en ```json ... ``` o ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    # Si tiene texto conversacional antes o después del objeto JSON
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()

    return text


def parse_and_validate_part(raw_text: str) -> Any:
    """Limpia el texto JSON y lo valida contra el esquema Pydantic CADPart."""
    reload_engine_modules()
    cleaned = clean_json_text(raw_text)
    if not cleaned:
        raise ValueError("El texto JSON está vacío.")
    return schemas.cad_schema.CADPart.model_validate_json(cleaned)


def run_from_file(json_path: Path) -> None:
    """Modo consola: lee un archivo JSON, lo valida y construye la pieza en SOLIDWORKS (2017–2026)."""
    if not json_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo JSON: {json_path}")

    raw_text = json_path.read_text(encoding="utf-8")
    part = parse_and_validate_part(raw_text)
    print(f"[OK] Pieza validada: '{part.part_name}' ({len(part.operations)} operaciones)")
    model = sw_engine.features.build_part(part)
    ver_label = sw_engine.connection.get_connected_version_info().display_name
    try:
        doc_title = str(com_call_0(model, "GetTitle"))
    except Exception:
        doc_title = part.part_name
    print(f"[OK] Pieza construida en {ver_label} (Documento: '{doc_title}').")


class Sketch2SolidApp:
    """Interfaz gráfica local para pegar el JSON devuelto por cualquier IA y construirlo en SOLIDWORKS (2017–2026)."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(
            f"Sketch2Solid - Constructor 3D para SOLIDWORKS ({SUPPORTED_SW_MIN_YEAR}–{SUPPORTED_SW_MAX_YEAR})"
        )
        self.root.geometry("900x700")
        self.root.minsize(760, 560)

        self._build_ui()
        self.load_json_file(silent=True)
        self._log_installed_versions_summary()

    def _build_ui(self) -> None:
        # Encabezado con instrucciones rápidas
        header_frame = tk.Frame(self.root, padx=12, pady=8)
        header_frame.pack(fill=tk.X)

        title_lbl = tk.Label(
            header_frame,
            text=f"Sketch2Solid (Modo Chat sin API -> SOLIDWORKS {SUPPORTED_SW_MIN_YEAR}–{SUPPORTED_SW_MAX_YEAR})",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        title_lbl.pack(fill=tk.X)

        steps_lbl = tk.Label(
            header_frame,
            text=(
                "Paso 1: Copia el Prompt Maestro y envíalo junto con la foto de tu croquis a cualquier IA (ChatGPT, Gemini, Claude).\n"
                "Paso 2: Copia el JSON que te responda la IA y pégalo aquí.\n"
                "Paso 3: Con SOLIDWORKS abierto (Windows, 2017–2026), presiona '3. Construir en SOLIDWORKS'."
            ),
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            fg="#333333",
        )
        steps_lbl.pack(fill=tk.X, pady=(4, 0))

        # Barra de botones principales
        btn_frame = tk.Frame(self.root, padx=12, pady=6)
        btn_frame.pack(fill=tk.X)

        btn_copy_prompt = tk.Button(
            btn_frame,
            text="1. Copiar Prompt Maestro",
            command=self.copy_master_prompt,
            bg="#e8f0fe",
            fg="#1a73e8",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
        )
        btn_copy_prompt.pack(side=tk.LEFT, padx=(0, 6))

        btn_paste_json = tk.Button(
            btn_frame,
            text="2. Pegar JSON del Portapapeles",
            command=self.paste_from_clipboard,
            bg="#fef7e0",
            fg="#b06000",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
        )
        btn_paste_json.pack(side=tk.LEFT, padx=(0, 6))

        btn_validate = tk.Button(
            btn_frame,
            text="Validar JSON",
            command=self.validate_current_json,
            font=("Segoe UI", 9),
            padx=10,
            pady=5,
        )
        btn_validate.pack(side=tk.LEFT, padx=(0, 6))

        btn_build = tk.Button(
            btn_frame,
            text="3. Construir en SOLIDWORKS",
            command=self.build_in_solidworks,
            bg="#1e8e3e",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=5,
        )
        btn_build.pack(side=tk.LEFT, padx=(6, 6))

        btn_detect = tk.Button(
            btn_frame,
            text="Detectar SOLIDWORKS",
            command=self.detect_solidworks_connection,
            font=("Segoe UI", 9),
            padx=8,
            pady=5,
        )
        btn_detect.pack(side=tk.RIGHT)

        # Botones secundarios de archivo (pieza.json)
        file_frame = tk.Frame(self.root, padx=12, pady=2)
        file_frame.pack(fill=tk.X)

        tk.Label(
            file_frame,
            text=f"Archivo activo: {DEFAULT_JSON_PATH}",
            font=("Segoe UI", 8),
            fg="#555555",
        ).pack(side=tk.LEFT)

        tk.Button(
            file_frame,
            text="Guardar en pieza.json",
            command=self.save_json_file,
            font=("Segoe UI", 8),
            padx=6,
        ).pack(side=tk.RIGHT, padx=(4, 0))

        tk.Button(
            file_frame,
            text="Recargar pieza.json",
            command=lambda: self.load_json_file(silent=False),
            font=("Segoe UI", 8),
            padx=6,
        ).pack(side=tk.RIGHT)

        # Editor de JSON
        editor_frame = tk.Frame(self.root, padx=12, pady=6)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        self.json_editor = scrolledtext.ScrolledText(
            editor_frame,
            wrap=tk.NONE,
            font=("Consolas", 10),
            undo=True,
            height=20,
        )
        self.json_editor.pack(fill=tk.BOTH, expand=True)

        # Panel inferior de registro / estado
        log_frame = tk.LabelFrame(self.root, text="Estado / Registro de Ejecución", padx=8, pady=6)
        log_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            height=10,
            bg="#f8f9fa",
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.X)

    def _log_installed_versions_summary(self) -> None:
        versions = list_installed_solidworks_versions()
        if versions:
            ver_text = ", ".join(f"SOLIDWORKS {year} (v{major})" for year, major, _ in versions)
            self.log(f"[INFO] SOLIDWORKS detectado en registro de Windows: {ver_text}")
        else:
            self.log(
                "[AVISO] No se detectaron claves SldWorks.Application.<N> en el registro. "
                "Asegúrate de tener SOLIDWORKS (2017–2026) instalado en Windows."
            )

    def detect_solidworks_connection(self) -> None:
        try:
            sw_app = connect_to_solidworks()
            ver = get_connected_version_info()
            adapter = get_connected_adapter()
            consts = get_connected_constants()
            del sw_app
            gc.collect()
            lang = ver.language or "desconocido"
            msg = (
                f"Conexión exitosa con {ver.display_name}\n"
                f"- Adaptador activo: {adapter.name} ({adapter.__class__.__module__})\n"
                f"- ProgID: {ver.prog_id}\n"
                f"- Idioma: {lang}\n"
                f"- Carpeta ejecutable: {ver.executable_dir or '(no informada)'}\n"
                f"- Constantes COM: {consts.source}"
            )
            self.log(
                f"[OK] {ver.display_name} conectado -> {adapter.name} "
                f"(idioma: {lang}, constantes: {consts.source})."
            )
            messagebox.showinfo("SOLIDWORKS Detectado", msg)
        except Exception as exc:
            self.log(f"[ERROR de conexión] {exc}")
            messagebox.showerror("No se pudo conectar a SOLIDWORKS", str(exc))

    def log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        try:
            LAST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LAST_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(message + "\n")
        except Exception:
            pass
        self.root.update_idletasks()

    def copy_master_prompt(self) -> None:
        prompt_path = resolve_prompt_path()
        if not prompt_path.exists():
            messagebox.showerror(
                "Archivo no encontrado",
                f"No se encontró el archivo de prompt en:\n{prompt_path}",
            )
            return

        prompt_content = prompt_path.read_text(encoding="utf-8")
        self.root.clipboard_clear()
        self.root.clipboard_append(prompt_content)
        self.root.update()
        self.log("[OK] Prompt Maestro copiado al portapapeles. Pégalo en tu chat de IA junto con la foto del croquis.")
        messagebox.showinfo(
            "Prompt Copiado",
            "El Prompt Maestro ya está en tu portapapeles.\n\n"
            "Ahora ve a tu chat de IA (ChatGPT, Gemini, Claude, etc.), "
            "sube la foto de tu croquis y pega el prompt (Ctrl + V).",
        )

    def paste_from_clipboard(self) -> None:
        try:
            clip_text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Portapapeles vacío", "No hay texto en el portapapeles para pegar.")
            return

        cleaned = clean_json_text(clip_text)
        self.json_editor.delete("1.0", tk.END)
        self.json_editor.insert("1.0", cleaned)
        self.log("[INFO] JSON pegado desde el portapapeles y limpiado automáticamente.")

    def load_json_file(self, silent: bool = False) -> None:
        source_path = DEFAULT_JSON_PATH
        if not source_path.exists() and BUNDLED_SAMPLE_JSON_PATH.exists():
            source_path = BUNDLED_SAMPLE_JSON_PATH
        if not source_path.exists():
            if not silent:
                messagebox.showwarning("Aviso", f"No existe todavía {DEFAULT_JSON_PATH}")
            return

        content = source_path.read_text(encoding="utf-8")
        self.json_editor.delete("1.0", tk.END)
        self.json_editor.insert("1.0", content)
        if not silent:
            self.log(f"[INFO] Archivo recargado desde {source_path.name}.")

    def save_json_file(self) -> bool:
        raw_text = self.json_editor.get("1.0", tk.END)
        try:
            part = parse_and_validate_part(raw_text)
            formatted = json.dumps(part.model_dump(), indent=2, ensure_ascii=False)
            DEFAULT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_JSON_PATH.write_text(formatted + "\n", encoding="utf-8")
            self.json_editor.delete("1.0", tk.END)
            self.json_editor.insert("1.0", formatted)
            self.log(f"[OK] JSON validado y guardado en {DEFAULT_JSON_PATH}.")
            return True
        except Exception as exc:
            self.log(f"[ERROR de validación] {exc}")
            messagebox.showerror("JSON Inválido", f"El JSON tiene errores de formato o esquema:\n\n{exc}")
            return False

    def validate_current_json(self) -> None:
        raw_text = self.json_editor.get("1.0", tk.END)
        try:
            part = parse_and_validate_part(raw_text)
            formatted = json.dumps(part.model_dump(), indent=2, ensure_ascii=False)
            self.json_editor.delete("1.0", tk.END)
            self.json_editor.insert("1.0", formatted)
            total_shapes = sum(
                len(op.sketch.shapes)
                for op in part.operations
                if getattr(op, "sketch", None) is not None
            )
            msg = (
                f"JSON 100% válido.\n"
                f"- Nombre de pieza: {part.part_name}\n"
                f"- Operaciones 3D: {len(part.operations)}\n"
                f"- Figuras 2D totales: {total_shapes}"
            )
            self.log(f"[OK] {msg.replace(chr(10), ' | ')}")
            messagebox.showinfo("Validación Exitosa", msg)
        except Exception as exc:
            self.log(f"[ERROR de validación] {exc}")
            messagebox.showerror("Error en el JSON", f"El JSON no cumple el esquema:\n\n{exc}")

    def build_in_solidworks(self) -> None:
        raw_text = self.json_editor.get("1.0", tk.END)
        old_stdout = sys.stdout
        try:
            try:
                LAST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                LAST_LOG_PATH.write_text("", encoding="utf-8")
            except Exception:
                pass
            sys.stdout = _GuiLogStream(self, old_stdout)  # type: ignore[assignment]
            self.log("Validando JSON con Pydantic...")
            part = parse_and_validate_part(raw_text)
            formatted = json.dumps(part.model_dump(), indent=2, ensure_ascii=False)
            DEFAULT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_JSON_PATH.write_text(formatted + "\n", encoding="utf-8")
            self.json_editor.delete("1.0", tk.END)
            self.json_editor.insert("1.0", formatted)

            self.log(
                f"Conectando a SOLIDWORKS y construyendo '{part.part_name}' "
                f"({len(part.operations)} operaciones)..."
            )
            model = sw_engine.features.build_part(part)
            ver_label = sw_engine.connection.get_connected_version_info().display_name
            try:
                doc_title = str(com_call_0(model, "GetTitle"))
            except Exception:
                doc_title = part.part_name

            # Liberar referencias COM inmediatamente para que SOLIDWORKS pueda editarse sin bloqueos
            del model
            gc.collect()

            self.log(f"[OK] ¡Pieza '{part.part_name}' creada exitosamente en {ver_label} (Documento: {doc_title})!")
        except Exception as exc:
            tb_str = traceback.format_exc()
            self.log(f"[ERROR] {exc}\n{tb_str}")
            messagebox.showerror(
                "Error al construir en SOLIDWORKS",
                f"Ocurrió un error durante la construcción:\n\n{exc}",
            )
        finally:
            try:
                sys.stdout.flush()
            except Exception:
                pass
            sys.stdout = old_stdout


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Sketch2Solid - Ejecutor de piezas JSON en SOLIDWORKS ({SUPPORTED_SW_MIN_YEAR}–{SUPPORTED_SW_MAX_YEAR})"
    )
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        help="Ruta a un archivo JSON para construir directamente por consola (sin abrir ventana gráfica).",
    )
    args, _ = parser.parse_known_args()

    if args.file:
        run_from_file(args.file)
        return

    root = tk.Tk()
    Sketch2SolidApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
