#!/usr/bin/env bash
set -euo pipefail

# ===============================
# CONFIGURACIÓN DEL PROYECTO
# ===============================
BASE_DIR="$(pwd)/work"                      # Carpeta raíz del proyecto (donde ejecutes el script)
VENV_DIR="$BASE_DIR/venv"              # Entorno virtual
REQ_FILE="$BASE_DIR/requirements.txt"  # Archivo de dependencias

INPUT_DIR="$BASE_DIR/data/input"       # Carpeta de entrada (DOCX)
OUTPUT_DIR="$BASE_DIR/data/output"     # Carpeta de salida (resultados)
LOG_DIR="$BASE_DIR/logs"               # Carpeta de logs
DOCX="documento.docx"                # Nombre del archivo DOCX a procesar

mkdir -p "$INPUT_DIR" "$OUTPUT_DIR" "$LOG_DIR"

timestamp() { date +%Y%m%d-%H%M%S; }

log_step() {
  local name="$1"
  echo "===== [$name] $(date) ====="
}

# ===============================
# 1) Crear y/o activar el entorno virtual
# ===============================
log_step "Configurar venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "No existe el venv, creando en $VENV_DIR ..."
  python3.13 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  echo "Instalando dependencias desde $REQ_FILE ..."
  pip install --upgrade pip
  pip install -r "$REQ_FILE"
else
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
fi

# ===============================
# 2) Ir a la carpeta base del proyecto
# ===============================
log_step "cd BASE_DIR"
cd "$BASE_DIR"

# ===============================
# 3) Ejecutar scripts de procesamiento
# ===============================
STEP1_LOG="$LOG_DIR/1_proceso_extraccion_$(timestamp).log"
log_step "python 1_proceso_extraccion.py $INPUT_DIR/$DOCX"
if python "1_proceso_extraccion.py" "$INPUT_DIR/$DOCX" 2>&1 | tee "$STEP1_LOG"; then
  echo "OK: 1_proceso_extraccion.py"
else
  echo "ERROR en 1_proceso_extraccion.py (ver $STEP1_LOG)" >&2
  exit 1
fi

STEP2_LOG="$LOG_DIR/2.1_generate_$(timestamp).log"
log_step "python 2.1_generate.py"
if python "2.1_generate.py" 2>&1 | tee "$STEP2_LOG"; then
  echo "OK: 2.1_generate.py"
else
  echo "ERROR en 2.1_generate.py (ver $STEP2_LOG)" >&2
  exit 1
fi

echo "Todos los pasos finalizaron correctamente."
