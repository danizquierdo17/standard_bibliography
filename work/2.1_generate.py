#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script: 2_generar_biblio_norm_openai.py
Versión: Adaptado a OpenAI Chat Completions; reintentos 429; degradación de modelo; logging; modo blob; DOCX.
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Comprobación de PYPANDOC
try:
    import pypandoc
    PYPANDOC_AVAILABLE = True
except Exception:
    PYPANDOC_AVAILABLE = False

# Excepciones OpenAI fallback
try:
    from openai import RateLimitError, APIError, APITimeoutError
except Exception:
    RateLimitError = Exception
    APIError = Exception
    APITimeoutError = Exception

# -------------------------
# Configuración de rutas
# -------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DOTENV_PATH = SCRIPT_DIR / ".env"
load_dotenv(DOTENV_PATH)

# Carpetas relativas al proyecto
CARPETA_ENTRADA = SCRIPT_DIR / "data/output/notas_al_pie"
CARPETA_SALIDA = SCRIPT_DIR / "data/output/salida_biblio_normalizada_OAI"
CARPETA_LOGS = SCRIPT_DIR / "logs_openai"



# -------------------------
# API Key
# -------------------------
API_KEY = (
    os.getenv("OPENAI_API_KEY")
    or os.getenv("OPENAI_API_KEY".replace("-", "_"))
    or os.getenv("OPENAI_API_KEY".lower())
)
if not API_KEY:
    raise ValueError(f"No se encontró OPENAI_API_KEY en {DOTENV_PATH}")

# -------------------------
# OpenAI SDK
# -------------------------
try:
    from openai import OpenAI
    import openai
    OpenAIClientAvailable = True
except Exception:
    OpenAIClientAvailable = False
    openai = None
    OpenAI = None

if not OpenAIClientAvailable:
    raise RuntimeError("No se pudo importar el cliente de OpenAI. Instala 'openai' >= 1.0.0")

client = OpenAI(api_key=API_KEY)

# -------------------------
# Modelos y parámetros
# -------------------------
MODEL_ORDER_DEFAULT = [
    os.getenv("GENAI_MODEL_PRIMARY", "gpt-4.1-mini"),
    os.getenv("GENAI_MODEL_SECONDARY", "gpt-4o"),
    os.getenv("GENAI_MODEL_TERTIARY", "gpt-4o-mini"),
]

ALIMENTAR_COMO_BLOB_DEFAULT = True

MAX_REINTENTOS = int(os.getenv("GENAI_MAX_RETRIES", "2"))
SLEEP_REINTENTO = float(os.getenv("GENAI_RETRY_SLEEP", "2.0"))
TEMPERATURE = float(os.getenv("GENAI_TEMPERATURE", "0.0"))
TOP_P = float(os.getenv("GENAI_TOP_P", "0.9"))

MAX_OUTPUT_TOKENS_DEFAULT = int(os.getenv("GENAI_MAX_OUTPUT_TOKENS", "4096"))
MAX_OUTPUT_TOKENS_MINI = int(os.getenv("GENAI_MAX_OUTPUT_TOKENS_FLASH", "8192"))

# -------------------------
# Prompts
# -------------------------
PROMPT_BASE = """Te proporciono un archivo de texto llamado notas_al_pie.txt (cada nota al pie de página es una línea, o está numerada).

Quiero que realices dos tareas:

1. Genera la bibliografía completa normalizada  
Procesa una a una (inserta un salto de linea entre cada cita) todas las notas al pie del archivo para extraer únicamente las referencias bibliográficas reales (libros, capítulos, artículos de revista, recursos web, cita de obras literarias, etc.).  
Formatea y normaliza cada referencia siguiendo estrictamente estas reglas extraídas de los ejemplos (muy importante seguirlas al pie de la letra):  
- Autores múltiples: se separan solo por una barra inclinada / sin espacios, y la coma va solo después del último autor. Ejemplo: Gómez Colomer, J.L./Montes Suay, F.,  
- Usa cursiva siempre en los títulos de libros, capítulos de colectáneas, y revistas.  
- Omite "núm.", "vol.", "n." en números de revista (solo el número y año: *InDret*, 2/2018, pp. 1-47.).  
- Mantén el formato y la puntuación de los siguientes modelos (muy importante respetar exactamente el formato y la cursiva):

Ejemplo formatos, ten en cuenta que yo aqui te voy a marcar las cursivas en formato markdown pero necesito que en tu output el texto no venga en markdown sino en el formato definitivo:  

Libro:  
Gómez Colomer, J.L., *El juez-robot (La independencia judicial en peligro)*, Tirant Lo Blanch, Valencia, 2023.  

Capítulo de libro:  
Molina Fernández, F., “Societas peccare non potest...: nec delinquere”, en Bacigalupo Sagesse, S./Feijoo Sánchez, B./Echano Asaldua, J.I. (Coords.), *Estudios de Derecho Penal: homenaje al profesor Miguel Bajo*, Ed. Ramón Areces, Madrid, 2017, pp. 361-416.  

Artículo de revista:  
Martínez Garay, L./Montes Suay, F., “El uso de valoraciones del riesgo de violencia en Derecho Penal: algunas cautelas necesarias”, *InDret*, 2/2018, pp. 1-47.  

Recurso web:  
McCarthy, J./Minsky, M.L./Rochester, N./Shannon, C.E., “A Proposal for the Dartmouth Summer Research Project on Artificial Intelligence”, 31 de Agosto de 1955, disponible en: [http://www-formal.stanford.edu/jmc/history/dartmouth/dartmouth.html](http://www-formal.stanford.edu/jmc/history/dartmouth/dartmouth.html) [Accedido por última vez el 27/03/2024].  

- Usa siempre así las abreviaturas: Ídem, op. cit., N., Ibid., [AA.VV].  
- Cuando falte información para alcanzar el formato modelo en una cita (por ejemplo falta de fuente o similares), márcalo al final de la línea así: (missinformation "información que falta").  
- Ordena la bibliografía por el primer autor (alfabéticamente) y por año en caso de varios trabajos del mismo autor.

2. Genera una tabla de correspondencia entre nota y bibliografía normalizada  
Crea una tabla con las siguientes columnas para cada nota al pie (es decir, para todas, no solo las que sean bibliografía):  
- Número de la nota al pie.  
- Texto del pie exactamente como aparece en el archivo.  
- ¿Se ha incluido como bibliografía? (Sí/No)  
- Cita en bibliografía (si procede, es decir, si corresponde a una referencia real, y en el mismo formato que arriba).  
- Motivo si no está en bibliografía (por ejemplo: “solo remisión”, “falta fuente”, “cita institucional”, etc).  

La estructura de la tabla debe ser así (ejemplo):  

| Nº | Nota al pie extraída | ¿En bibliografía? | Cita en bibliografía | Motivo si no está en bibliografía |  
| --- | --- | --- | --- | --- |  
| 1 | ...texto... | Sí | ...cita normalizada... |   |  
| 2 | ...texto... | No |   | Sólo remisión. |  
| 3 | ...texto... | Sí | ...cita normalizada... |   |

Entrega:  
- Devuélveme la bibliografía completa normalizada (lista definitiva).  
- Devuélveme la tabla de correspondencia.  

No olvides nunca marcar (missinformation "...") cada vez que algún campo requerido no esté presente en la cita resultante.  
Sé muy meticuloso para sacar todas las citas que se recogen en las notas al pie de mi archivo.
"""

PROMPT_SOLO_BIB = """Te proporciono un archivo de texto con notas al pie.
Genera exclusivamente la bibliografía completa normalizada siguiendo las reglas indicadas:
Lista con guiones (- ).
Una cita por línea, sin líneas en blanco.
Usar cursiva en títulos, formato estricto según ejemplos dados.
Marcar (missinformation "...") cuando falte información.
Ordenar alfabéticamente por primer autor y luego por año.
"""

PROMPT_SOLO_TABLA = """Te proporciono un archivo de texto con notas al pie.
Genera exclusivamente la tabla de correspondencia siguiendo la estructura:
| Nº | Nota al pie extraída | ¿En bibliografía? | Cita en bibliografía | Motivo si no está en bibliografía |
Incluye todas las notas al pie, incluso si no son referencias reales.
"""

# -------------------------
# Cliente OpenAI
# -------------------------
if not OpenAIClientAvailable:
    raise RuntimeError("No se pudo importar el cliente de OpenAI. Instala 'openai' >= 1.0.0")

client = OpenAI(api_key=API_KEY)

# -------------------------
# Utilidades
# -------------------------
def asegurar_carpetas() -> None:
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    CARPETA_LOGS.mkdir(parents=True, exist_ok=True)

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_to_jsonable(obj: Any, depth: int = 0, max_depth: int = 4) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if depth >= max_depth:
        return str(obj)
    if isinstance(obj, (list, tuple, set)):
        return [_safe_to_jsonable(x, depth + 1, max_depth) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_to_jsonable(v, depth + 1, max_depth) for k, v in obj.items()}
    try:
        to_dict = getattr(obj, "to_dict", None)
        if callable(to_dict):
            return _safe_to_jsonable(to_dict(), depth + 1, max_depth)
    except Exception:
        pass
    return str(obj)

def _log_guardar(path: Path, data: Dict[str, Any]) -> None:
    try:
        data = dict(data or {})
        data["_logged_at"] = _now_utc_iso()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        fallback = {"fallback_error": str(e), "data_str": str(data), "_logged_at": _now_utc_iso()}
        path.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")

def _gen_config_for(name: str) -> Dict[str, Any]:
    # Ajusta max_tokens según modelo (heurístico)
    max_tokens = MAX_OUTPUT_TOKENS_MINI if ("mini" in name or "small" in name) else MAX_OUTPUT_TOKENS_DEFAULT
    # Clamp de temperatura y top_p por seguridad
    t = max(0.0, min(2.0, TEMPERATURE))
    p = max(0.0, min(1.0, TOP_P))
    return dict(temperature=t, top_p=p, max_tokens=max_tokens)

def _es_markdown_util(texto: str) -> bool:
    if not texto:
        return False
    t = texto.strip()
    if not t:
        return False
    # Aceptar si tiene tablas o listas o parece una bibliografía
    if any(sym in t for sym in ["|", "-", "•", "pp.", "Disponible en", "Ed.", "InDret"]):
        return True
    return True  # fallback: aceptar cualquier texto no vacío


def _extraer_texto_md_from_resp(resp) -> str:
    # print("DEBUG RESP:", resp)
    try:
        if resp and resp.choices and resp.choices[0].message:
            return (resp.choices[0].message.content or "").strip()
        return ""
    except Exception as e:
        return f"[ERROR EXTRAER TEXTO: {e}]"


def markdown_a_docx(markdown_text: str, destino_docx: Path) -> None:
    if not PYPANDOC_AVAILABLE:
        raise RuntimeError("pypandoc/Pandoc no disponible; no se puede convertir a DOCX.")
    pypandoc.convert_text(
        markdown_text,
        to="docx",
        format="markdown",
        outputfile=str(destino_docx),
        extra_args=["--standalone"]
    )

def _es_429_quota(e: Exception) -> bool:
    s = str(e)
    return isinstance(e, RateLimitError) or ("429" in s) or ("rate limit" in s.lower())

def _retry_delay_sugerido(e: Exception) -> float:
    # Backoff simple si no disponemos de headers -> Retry-After
    return 8.0

def _construir_messages(nombre_archivo: str, prompt: str, raw_text: str) -> List[Dict[str, str]]:
    header = (
        f"{prompt}\n\n"
        f"Archivo adjunto: {nombre_archivo}\n"
        f"Procesa el archivo adjunto y devuelve exclusivamente Markdown.\n\n"
        f"---\n[INICIO DEL CONTENIDO {nombre_archivo}]\n{raw_text or ''}\n[FIN DEL CONTENIDO]\n---"
    )
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": "Eres un asistente experto en normalización bibliográfica y tablas. Responde en Markdown válido."},
        {"role": "user", "content": header},
    ]
    return messages

def _llamar_chat(model_name: str, messages: List[Dict[str, str]]):
    cfg = _gen_config_for(model_name)
    resp = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=cfg["temperature"],
        top_p=cfg["top_p"],
        max_tokens=cfg["max_tokens"],
    )
    return resp

def _respuesta_a_dict(resp) -> Dict[str, Any]:
    try:
        d: Dict[str, Any] = {
            "id": getattr(resp, "id", None),
            "model": getattr(resp, "model", None),
            "usage": _safe_to_jsonable(getattr(resp, "usage", None)),
            "choices_meta": [],
        }
        for ch in getattr(resp, "choices", []) or []:
            d["choices_meta"].append({
                "finish_reason": getattr(ch, "finish_reason", None),
                "index": getattr(ch, "index", None),
            })
        texto = _extraer_texto_md_from_resp(resp)
        d["text_length"] = len(texto)
        return d
    except Exception as e:
        return {"parse_error": str(e), "raw_str": str(resp)}

# -------------------------
# Ejecución por archivo
# -------------------------
def procesar_archivo_txt(
    nombre_archivo: str,
    alimentar_como_blob: bool,
    modelos_en_orden: List[str],
    prompt: str = PROMPT_BASE,
    generar_docx: bool = True,
) -> None:
    path = CARPETA_ENTRADA / nombre_archivo
    if not path.exists():
        print(f"[Error] No existe archivo: {path}")
        return

    raw_text = path.read_text(encoding="utf-8", errors="replace")
    messages = _construir_messages(nombre_archivo, prompt, raw_text)

    logs_archivo = CARPETA_LOGS / f"log_{Path(nombre_archivo).stem}_{int(time.time())}.json"
    salida_md = CARPETA_SALIDA / f"{Path(nombre_archivo).stem}_biblio_y_tabla.md"
    salida_docx = CARPETA_SALIDA / f"{Path(nombre_archivo).stem}_biblio_y_tabla.docx"

    # Reintentos con degradación de modelo
    intentos = 0
    errores: List[str] = []
    for model_name in modelos_en_orden:
        # Para cada modelo, intentamos hasta MAX_REINTENTOS
        for intento_modelo in range(MAX_REINTENTOS + 1):
            try:
                print(f"[INFO] Llamando modelo: {model_name} (intento {intento_modelo+1}/{MAX_REINTENTOS+1})")
                resp = _llamar_chat(model_name, messages)
                texto = _extraer_texto_md_from_resp(resp)
                meta = _respuesta_a_dict(resp)
                _log_guardar(logs_archivo, {"model": model_name, "meta": meta})

                if not _es_markdown_util(texto):
                    raise ValueError("La respuesta no parece Markdown utilizable o vino vacía.")

                # Guardar Markdown
                salida_md.write_text(texto, encoding="utf-8")
                print(f"[OK] Guardado Markdown en: {salida_md}")

                # DOCX opcional
                if generar_docx and PYPANDOC_AVAILABLE:
                    try:
                        markdown_a_docx(texto, salida_docx)
                        print(f"[OK] Guardado DOCX en: {salida_docx}")
                    except Exception as e_docx:
                        print(f"[WARN] Falló la conversión a DOCX: {e_docx}")

                return

            except (APITimeoutError, APIError, RateLimitError) as e:
                errores.append(f"{model_name} intento {intento_modelo+1}: {type(e).__name__}: {e}")
                _log_guardar(logs_archivo, {"error": str(e), "model": model_name, "try": intento_modelo + 1})
                if _es_429_quota(e) and intento_modelo < MAX_REINTENTOS:
                    delay = max(SLEEP_REINTENTO, _retry_delay_sugerido(e))
                    print(f"[WARN] 429/Rate limit. Esperando {delay:.1f}s y reintentando...")
                    time.sleep(delay)
                    continue
                elif intento_modelo < MAX_REINTENTOS:
                    print(f"[WARN] Error API. Esperando {SLEEP_REINTENTO:.1f}s y reintentando...")
                    time.sleep(SLEEP_REINTENTO)
                    continue
                else:
                    print(f"[ERROR] Fallaron todos los intentos con {model_name}. Probando siguiente modelo...")
                    break
            except Exception as e:
                errores.append(f"{model_name} intento {intento_modelo+1}: {type(e).__name__}: {e}")
                _log_guardar(logs_archivo, {"error": str(e), "model": model_name, "try": intento_modelo + 1})
                if intento_modelo < MAX_REINTENTOS:
                    print(f"[WARN] Error genérico. Esperando {SLEEP_REINTENTO:.1f}s y reintentando...")
                    time.sleep(SLEEP_REINTENTO)
                    continue
                else:
                    print(f"[ERROR] Fallaron todos los intentos con {model_name}. Probando siguiente modelo...")
                    break

    print("[FATAL] No se pudo obtener respuesta usable de ninguno de los modelos.")
    if errores:
        print("Detalles de errores:")
        for e in errores:
            print(" -", e)
    return

# -------------------------
# CLI
# -------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Procesa notas al pie con OpenAI (Chat Completions).")
    ap.add_argument("--file", "-f", help="Procesar solo este archivo .txt (de la carpeta de entrada).")
    ap.add_argument("--blob", action="store_true", help="Forzar modo blob (incrustar el texto en el prompt).")
    ap.add_argument("--no-blob", action="store_true", help="(No-op) El modo upload no se usa en OpenAI para texto plano.")
    ap.add_argument("--model", "-m", action="append", help="Modelos en orden de preferencia. Se puede repetir.")
    ap.add_argument("--solo-bib", action="store_true", help="Generar solo bibliografía normalizada.")
    ap.add_argument("--solo-tabla", action="store_true", help="Generar solo la tabla de correspondencia.")
    ap.add_argument("--no-docx", action="store_true", help="No generar DOCX (solo Markdown).")
    return ap.parse_args()

# -------------------------
# Función para compilar todas las citas en un único archivo final
# -------------------------
def generar_biblio_final(citas_acumuladas: List[str], salida_final_md: Path, salida_final_docx: Optional[Path] = None):
    # Eliminar duplicados
    citas_unicas = list(set(citas_acumuladas))
    
    # Ordenar alfabéticamente por primer autor y año aproximado
    import re
    def clave_orden(cita: str):
        m = re.match(r"([^\.,]+).*?(\d{4})", cita)
        if m:
            autor, anio = m.groups()
            return (autor.lower(), int(anio))
        return (cita.lower(), 9999)
    
    citas_ordenadas = sorted(citas_unicas, key=clave_orden)
    
    # Añadir guion al inicio de cada cita
    citas_formateadas = [f"- {c}" for c in citas_ordenadas]
    
    # Guardar Markdown
    salida_final_md.write_text("\n".join(citas_formateadas), encoding="utf-8")
    print(f"[OK] Archivo final Markdown con todas las citas: {salida_final_md}")
    
    # DOCX opcional
    if salida_final_docx and PYPANDOC_AVAILABLE:
        try:
            markdown_a_docx("\n".join(citas_formateadas), salida_final_docx)
            print(f"[OK] Archivo final DOCX con todas las citas: {salida_final_docx}")
        except Exception as e:
            print(f"[WARN] Falló la conversión final a DOCX: {e}")



# -------------------------
# Modificación de main()
# -------------------------
def main():
    args = parse_args()
    asegurar_carpetas()

    if not CARPETA_ENTRADA.exists():
        raise FileNotFoundError(f"No existe carpeta de entrada: {CARPETA_ENTRADA}")

    alimentar_como_blob = ALIMENTAR_COMO_BLOB_DEFAULT or args.blob
    modelos_en_orden = args.model if args.model else MODEL_ORDER_DEFAULT
    generar_docx = not args.no_docx

    prompt = PROMPT_BASE
    if args.solo_bib and args.solo_tabla:
        print("[WARN] Se pidieron ambos modos 'solo'; usando prompt completo (BASE).")
    elif args.solo_bib:
        prompt = PROMPT_SOLO_BIB
    elif args.solo_tabla:
        prompt = PROMPT_SOLO_TABLA

    citas_acumuladas: List[str] = []

    archivos = []
    if args.file:
        archivos = [args.file]
    else:
        archivos = sorted([p.name for p in CARPETA_ENTRADA.glob("*.txt")])
        if not archivos:
            print(f"[INFO] No hay .txt en {CARPETA_ENTRADA}")
            return

    for nombre in archivos:
        procesar_archivo_txt(nombre, alimentar_como_blob, modelos_en_orden, prompt=prompt, generar_docx=generar_docx)
        # Intentar leer las citas generadas en cada Markdown individual
        md_path = CARPETA_SALIDA / f"{Path(nombre).stem}_biblio_y_tabla.md"
        if md_path.exists():
            texto = md_path.read_text(encoding="utf-8")
            # Extraemos líneas que parezcan citas (descartando tablas si existieran)
            for line in texto.splitlines():
                line = line.strip()
                if line and not line.startswith("|") and not line.startswith("---"):
                    citas_acumuladas.append(line)

    # Generar archivo final con todas las citas
    salida_final_md = CARPETA_SALIDA / "biblio_final_completa.md"
    salida_final_docx = CARPETA_SALIDA / "biblio_final_completa.docx" if generar_docx else None
    generar_biblio_final(citas_acumuladas, salida_final_md, salida_final_docx)

if __name__ == "__main__":
    main()


