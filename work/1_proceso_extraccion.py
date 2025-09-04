#!/usr/bin/env python3
import docx
from docx.oxml.ns import qn
from lxml import etree
import sys
import os
from pathlib import Path

# ===============================
# Configuración de rutas
# ===============================
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.getenv("PROJECT_BASE_DIR", SCRIPT_DIR))

INPUT_DIR = Path(os.getenv("INPUT_DIR", BASE_DIR / "data" / "input"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "data" / "output"))
LOGS_DIR = Path(os.getenv("LOGS_DIR", BASE_DIR / "logs"))

CARPETA_SALIDA = OUTPUT_DIR / "notas_al_pie"
CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)


def get_footnote_page_map(doc):
    """
    Analiza el XML del documento para mapear el ID de cada nota al pie a su número de página.
    """
    page_map = {}
    page_number = 1
    body_xml = doc.part.element.body

    for elem in body_xml.iter():
        if elem.tag == qn('w:lastRenderedPageBreak'):
            page_number += 1

        if elem.tag == qn('w:footnoteReference'):
            footnote_id = elem.get(qn('w:id'))
            if footnote_id:
                page_map[footnote_id] = page_number

    return page_map


def get_footnotes(doc):
    """
    Extrae el texto y el ID de todas las notas al pie de un documento .docx.
    """
    footnotes_data = []
    doc_part = doc.part
    footnotes_part = None

    # localizamos la parte de notas al pie
    for rel in doc_part.rels.values():
        if "footnotes" in rel.target_ref:
            footnotes_part = rel.target_part
            break

    if footnotes_part is None:
        return []

    # Leemos el XML de notas
    footnotes_xml = footnotes_part._blob
    root = etree.fromstring(footnotes_xml)

    ns_map = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

    for fn in root.findall('w:footnote', namespaces=ns_map):
        fn_id = fn.get(qn('w:id'))

        # omitimos automáticas/separadores
        if fn.get(qn('w:type')) or fn_id is None:
            continue

        # texto concatenado de la nota
        text_fragments = [
            node.text for node in fn.xpath('.//w:t', namespaces=ns_map) if node.text
        ]
        nota_texto = "".join(text_fragments)
        footnotes_data.append({'id': fn_id, 'text': nota_texto.strip()})

    return footnotes_data


def guardar_por_bloques(notas, page_map, carpeta_salida, bloque_size=20):
    """
    Guarda las notas en ficheros consecutivos de bloque_size en bloque_size.
    """
    # Ordenar por ID numérico
    notas_ordenadas = sorted(notas, key=lambda x: int(x['id']))

    total = len(notas_ordenadas)
    num_fichero = 1

    for i in range(0, total, bloque_size):
        bloque = notas_ordenadas[i:i+bloque_size]
        nombre_fichero = carpeta_salida / f"notas_al_pie_{num_fichero}.txt"
        with open(nombre_fichero, "w", encoding="utf-8") as f:
            for idx, nota_data in enumerate(bloque, start=1 + i):
                nota_id = nota_data['id']
                nota_texto = nota_data['text']
                pagina = page_map.get(nota_id, '?')
                f.write(f"{idx}. {nota_texto} (p. {pagina})\n\n")
        print(f"Guardado {len(bloque)} notas en {nombre_fichero}")
        num_fichero += 1


def main():
    if len(sys.argv) != 2:
        print("Uso: python 1_proceso_extraccion.py <fichero_entrada.docx>")
        sys.exit(1)

    archivo_entrada = Path(sys.argv[1])

    if not archivo_entrada.exists():
        print(f"Error: el archivo {archivo_entrada} no existe en {INPUT_DIR}")
        sys.exit(1)

    print(f"Abriendo el documento: {archivo_entrada}...")
    try:
        doc = docx.Document(archivo_entrada)
    except Exception as e:
        print(f"Error al abrir el archivo {archivo_entrada}: {e}")
        sys.exit(1)

    print("Mapeando notas al pie a sus páginas...")
    page_map = get_footnote_page_map(doc)

    print("Leyendo notas al pie...")
    notas = get_footnotes(doc)

    if not notas:
        print("No se encontraron notas al pie en el documento.")
        return

    guardar_por_bloques(notas, page_map, CARPETA_SALIDA, bloque_size=20)
    print(f"¡Hecho! {len(notas)} notas extraídas.")


if __name__ == "__main__":
    main()
