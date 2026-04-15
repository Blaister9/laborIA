"""
ingest_ley1010.py — Ingesta la Ley 1010 de 2006 (Acoso Laboral) al corpus.

Pipeline completo en un solo script:
  1. Artículos codificados con el texto oficial (Diario Oficial 46.160 de 2006-01-23)
  2. Genera chunks en el mismo formato que chunk_corpus.py
  3. Añade los chunks INCREMENTALMENTE a corpus/parsed/chunks.json
  4. Carga los nuevos embeddings en Qdrant (sin resetear la colección)
  5. Valida con la query de prueba

Uso:
    python corpus/scripts/ingest_ley1010.py          # Ingesta completa
    python corpus/scripts/ingest_ley1010.py --dry-run # Solo muestra chunks sin cargar
    python corpus/scripts/ingest_ley1010.py --reset-source # Re-ingesta aunque ya existan

Fuente: Ley 1010 de 2006 — Congreso de Colombia — D.O. 46.160 del 23-enero-2006
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ── Rutas ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
CORPUS_DIR   = SCRIPT_DIR.parent
PARSED_DIR   = CORPUS_DIR / "parsed"
CHUNKS_PATH  = PARSED_DIR / "chunks.json"

QDRANT_HOST       = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT       = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME   = os.getenv("QDRANT_COLLECTION_CST", "cst_articles")
EMBEDDING_MODEL   = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
QDRANT_LOCAL_PATH = str(CORPUS_DIR.parent / "qdrant_local")

LABORIA_UUID_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def chunk_id_to_uuid(chunk_id: str) -> str:
    return str(uuid.uuid5(LABORIA_UUID_NS, chunk_id))


# ═══════════════════════════════════════════════════════════════════════════════
# TEXTO OFICIAL — Ley 1010 de 2006
# Fuente: Diario Oficial 46.160, 23 de enero de 2006
# ═══════════════════════════════════════════════════════════════════════════════

LEY_1010_ARTICLES: list[dict] = [
    {
        "article_number": "1",
        "article_title": "OBJETO DE LA LEY",
        "chapter": "Capítulo I - Disposiciones generales",
        "text": (
            "La presente ley tiene por objeto definir, prevenir, corregir y sancionar "
            "las diversas formas de agresión, maltrato, vejámenes, trato desconsiderado "
            "y ofensivo y en general todo ultraje a la dignidad humana que se ejercen "
            "sobre quienes realizan sus actividades económicas en el contexto de una "
            "relación laboral privada o pública. "
            "Son bienes jurídicos protegidos por la presente ley: el trabajo en "
            "condiciones dignas y justas, la libertad, la intimidad, la honra y la "
            "salud mental de los trabajadores, empleados, la armonía entre quienes "
            "comparten un mismo ambiente laboral y el buen ambiente en la empresa."
        ),
        "topics": ["acoso_laboral", "principios", "dignidad_trabajo"],
        "frequently_consulted": True,
    },
    {
        "article_number": "2",
        "article_title": "DEFINICIÓN Y MODALIDADES DE ACOSO LABORAL",
        "chapter": "Capítulo I - Disposiciones generales",
        "text": (
            "Para efectos de la presente ley se entenderá por acoso laboral toda "
            "conducta persistente y demostrable, ejercida sobre un empleado, trabajador "
            "por parte de un empleador, un jefe o superior jerárquico inmediato o "
            "mediato, un compañero de trabajo o un subalterno, encaminada a infundir "
            "miedo, intimidación, terror y angustia, a causar perjuicio laboral, "
            "generar desmotivación en el trabajo, o inducir la renuncia del mismo. "
            "\n\nEn el contexto del inciso primero de este artículo, el acoso laboral "
            "puede darse, entre otras, bajo las siguientes modalidades generales: "
            "\n\n1. Maltrato laboral. Todo acto de violencia contra la integridad "
            "física o moral, la libertad física o sexual y los bienes de quien se "
            "desempeñe como empleado o trabajador; toda expresión verbal injuriosa o "
            "ultrajante que lesione la integridad moral o los derechos a la intimidad "
            "y al buen nombre de quienes participen en una relación de trabajo de tipo "
            "laboral o todo comportamiento tendiente a menoscabar la autoestima y la "
            "dignidad de quien participe en una relación de trabajo de tipo laboral. "
            "\n\n2. Persecución laboral. Toda conducta cuyas características de "
            "reiteración o evidente arbitrariedad permitan inferir el propósito de "
            "inducir la renuncia del empleado o trabajador, mediante la descalificación, "
            "la carga excesiva de trabajo y cambios permanentes de horario que puedan "
            "producir desmotivación laboral. "
            "\n\n3. Discriminación laboral. Todo trato diferenciado por razones de "
            "raza, género, origen familiar o nacional, credo religioso, preferencia "
            "política o situación social o que carezca de toda razonabilidad desde el "
            "punto de vista laboral. "
            "\n\n4. Entorpecimiento laboral. Toda acción tendiente a obstaculizar el "
            "cumplimiento de la labor o hacerla más gravosa o retardarla con perjuicio "
            "para el trabajador o empleado. Constituyen acciones de entorpecimiento "
            "laboral, entre otras, la privación, ocultación o inutilización de los "
            "insumos, documentos o instrumentos para la labor, la destrucción o pérdida "
            "de información, el ocultamiento de correspondencia o mensajes electrónicos. "
            "\n\n5. Inequidad laboral. Asignación de funciones a menosprecio del "
            "trabajador. "
            "\n\n6. Desprotección laboral. Toda conducta tendiente a poner en riesgo "
            "la integridad y la seguridad del trabajador mediante órdenes o asignación "
            "de funciones sin el cumplimiento de los requisitos mínimos de protección "
            "y seguridad para el trabajador. "
            "\n\nParágrafo 1. La presente ley no se aplicará en el ámbito de las "
            "relaciones civiles y/o comerciales derivadas de los contratos de prestación "
            "de servicios en los cuales no se presenta una relación de jerarquía o "
            "subordinación. Tampoco se aplica a la contratación administrativa. "
            "\n\nParágrafo 2. Una sola conducta hostil bastará para acreditar el acoso "
            "laboral entre empleados, sea superior o subalterno, pero en la relación "
            "entre empleador y empleado se requerirá para su configuración la "
            "persistencia o reiteración de la conducta."
        ),
        "topics": ["acoso_laboral", "maltrato_laboral", "persecución_laboral", "discriminación_laboral"],
        "frequently_consulted": True,
    },
    {
        "article_number": "3",
        "article_title": "CONDUCTAS ATENUANTES",
        "chapter": "Capítulo I - Disposiciones generales",
        "text": (
            "Son conductas atenuantes del acoso laboral: "
            "\na) Haber observado buena conducta anterior. "
            "\nb) Obrar en estado de emoción o pasión excusable, o temor intenso, o "
            "en estado de ira e intenso dolor. "
            "\nc) Procurar voluntariamente, después de realizada la conducta, anular "
            "o disminuir sus consecuencias. "
            "\nd) Reparar, discrecionalmente, el daño ocasionado, aunque no sea en "
            "forma total. "
            "\ne) Las condiciones de inferioridad psíquicas determinadas por la edad "
            "o por circunstancias orgánicas que hayan influido en la realización de "
            "la conducta acosadora. "
            "\nf) Los demás que el funcionario estime como tal, siempre que estén "
            "debidamente sustentados."
        ),
        "topics": ["acoso_laboral", "sanciones"],
        "frequently_consulted": False,
    },
    {
        "article_number": "4",
        "article_title": "CONDUCTAS QUE NO CONSTITUYEN ACOSO LABORAL",
        "chapter": "Capítulo I - Disposiciones generales",
        "text": (
            "No constituyen acoso laboral bajo ninguna de sus modalidades: "
            "\na) Las exigencias y órdenes, necesarias para mantener la disciplina en "
            "los cuerpos que componen las Fuerzas Militares conforme al principio de "
            "jerarquía. "
            "\nb) Los actos destinados a ejercer la potestad disciplinaria que "
            "legalmente corresponde a los superiores jerárquicos sobre sus subalternos. "
            "\nc) La formulación de exigencias razonables de fidelidad laboral o "
            "lealtad empresarial e institucional. "
            "\nd) La formulación de circulares o memorandos de servicio encaminados a "
            "solicitar exigencias técnicas o mejorar la eficiencia laboral y que se "
            "relacionen con la actividad ordinaria del trabajador o empleado. "
            "\ne) La solicitud de cumplir deberes extras de colaboración con la empresa "
            "o institución, cuando sean necesarios para la continuidad del servicio o "
            "para solucionar situaciones difíciles en la operación de la empresa o "
            "institución. "
            "\nf) Las actuaciones administrativas o gestiones encaminadas a dar por "
            "terminado el contrato de trabajo, con base en una causa legal o justa "
            "causa, prevista en el Código Sustantivo del Trabajo o en la legislación "
            "sobre la función pública. "
            "\ng) La exigencia de cumplir con las obligaciones, deberes y prohibiciones "
            "de que trata la relación laboral. "
            "\nh) Las exigencias de cumplir con las estipulaciones contenidas en los "
            "reglamentos y cláusulas de los contratos de trabajo."
        ),
        "topics": ["acoso_laboral", "justa_causa", "reglamento_interno"],
        "frequently_consulted": True,
    },
    {
        "article_number": "5",
        "article_title": "SUJETOS CALIFICANTES DEL ACOSO LABORAL",
        "chapter": "Capítulo I - Disposiciones generales",
        "text": (
            "Sujetos activos o agresores del acoso laboral pueden ser: "
            "\na) La persona natural que se desempeñe como gerente, jefe, director, "
            "supervisor o cualquier otra posición de dirección y mando en una empresa "
            "u organización en la cual haya relaciones laborales regidas por el Código "
            "Sustantivo del Trabajo; "
            "\nb) La persona natural que se desempeñe como superior jerárquico "
            "inmediato o mediato de quien es sujeto pasivo o víctima del acoso; "
            "\nc) La persona natural que se desempeñe en la misma categoría o nivel, "
            "es decir, quien es compañero de trabajo de quien es víctima del acoso. "
            "\n\nParágrafo. Es sujeto pasivo o víctima del acoso laboral el trabajador "
            "o empleado que sufra las conductas descritas en el artículo 2 de la "
            "presente ley."
        ),
        "topics": ["acoso_laboral", "contrato_trabajo"],
        "frequently_consulted": False,
    },
    {
        "article_number": "6",
        "article_title": "MEDIDAS PREVENTIVAS Y CORRECTIVAS DEL ACOSO LABORAL",
        "chapter": "Capítulo II - Medidas preventivas y correctivas",
        "text": (
            "1. Los reglamentos de trabajo de las empresas e instituciones deberán "
            "prever mecanismos de prevención de las conductas de acoso laboral y "
            "establecer un procedimiento interno, confidencial, conciliatorio y "
            "efectivo para superar las que ocurran en el lugar de trabajo. Los "
            "comités de empresa de carácter bipartito, donde existan, podrán ser "
            "parte de ese procedimiento. "
            "\n\n2. La víctima del acoso laboral podrá poner en conocimiento del "
            "Inspector de Trabajo con competencia en el lugar de los hechos, de los "
            "Inspectores Municipales de Policía, de los Personeros Municipales o de "
            "la Defensoría del Pueblo, a prevención, la ocurrencia de estas "
            "situaciones con el fin de que se adelanten las investigaciones "
            "pertinentes y se impongan las sanciones y medidas correctivas del caso. "
            "\n\n3. El empleador deberá adaptar el reglamento de trabajo a los "
            "requerimientos de la presente ley, dentro de los tres (3) meses "
            "siguientes a su promulgación, y su incumplimiento será sancionado "
            "administrativamente por el Inspector del Trabajo con multas de hasta "
            "cien (100) salarios mínimos legales mensuales. "
            "\n\nParágrafo 1. Los comités de convivencia laboral existentes a la "
            "entrada en vigencia de la presente ley deberán ajustarse a los "
            "parámetros establecidos en esta misma ley. "
            "\n\nParágrafo 2. Los empleadores deberán informar a los trabajadores "
            "sobre la Ley de Acoso Laboral y sus mecanismos de prevención."
        ),
        "topics": ["acoso_laboral", "reglamento_interno", "comité_convivencia"],
        "frequently_consulted": True,
    },
    {
        "article_number": "7",
        "article_title": "CONDUCTAS QUE CONSTITUYEN ACOSO LABORAL",
        "chapter": "Capítulo II - Medidas preventivas y correctivas",
        "text": (
            "Se presumirá que hay acoso laboral si se acredita la ocurrencia repetida "
            "y pública de cualquiera de las siguientes conductas: "
            "\na) Los actos de agresión física, independientemente de sus consecuencias; "
            "\nb) Las expresiones injuriosas o ultrajantes sobre la persona, con "
            "utilización de palabras soeces o con alusión a la raza, el género, el "
            "origen familiar o nacional, la preferencia política o el estatus social; "
            "\nc) Los comentarios hostiles y humillantes de descalificación profesional "
            "expresados en presencia de los compañeros o colaboradores; "
            "\nd) Las amenazas reiteradas de despido expresadas en presencia de los "
            "compañeros o colaboradores; "
            "\ne) Las múltiples denuncias disciplinarias de cualquiera de los sujetos "
            "intervinientes en la relación laboral, por hechos que resulten de la mala "
            "fe en la actuación, o por hechos que no hayan podido ser demostrados; "
            "\nf) La descalificación humillante y en presencia de los compañeros de "
            "trabajo de las propuestas u opiniones de trabajo; "
            "\ng) Las burlas sobre la apariencia física o la forma de vestir, "
            "formuladas en público; "
            "\nh) La alusión pública a hechos pertenecientes a la intimidad de la "
            "persona; "
            "\ni) La imposición de deberes ostensiblemente extraños a las obligaciones "
            "laborales, las exigencias abiertamente desproporcionadas sobre el "
            "cumplimiento de la labor encomendada y el brusco cambio del lugar de "
            "trabajo o de la labor contratada sin ningún fundamento objetivo referente "
            "a la necesidad técnica de la empresa; "
            "\nj) La exigencia de laborar en horarios excesivos respecto a la jornada "
            "laboral contratada o legalmente establecida, los cambios sorpresivos del "
            "turno laboral y la exigencia permanente de laborar en dominicales y días "
            "festivos sin ningún fundamento objetivo en las necesidades de la empresa, "
            "o en forma discriminatoria respecto a los demás trabajadores o empleados; "
            "\nk) El trato notoriamente discriminatorio respecto a los demás empleados "
            "en cuanto al otorgamiento de derechos y prerrogativas laborales y la "
            "imposición de deberes laborales; "
            "\nl) La negativa a suministrar materiales e información absolutamente "
            "indispensables para el cumplimiento de la labor; "
            "\nm) La negativa claramente injustificada a otorgar permisos, licencias "
            "por enfermedad, licencias ordinarias y vacaciones, cuando se dan las "
            "condiciones legales, reglamentarias o convencionales para pedirlos; "
            "\nn) El envío de anónimos, llamadas telefónicas y mensajes virtuales con "
            "contenido injurioso, ofensivo o intimidatorio o el sometimiento a una "
            "situación de aislamiento social. "
            "\n\nParágrafo 1. Las anteriores conductas constituirán acoso laboral si "
            "se presentan de manera reiterada y pública, y si con ellas se ocasiona "
            "perjuicio a la víctima. "
            "\nParágrafo 2. Se presumirá que hay acoso laboral si se acredita la "
            "ocurrencia repetida y pública de cualquiera de las conductas descritas "
            "en el inciso primero de este artículo, y la víctima del acoso prueba "
            "daños en su salud, en su vida personal o en su desempeño profesional."
        ),
        "topics": ["acoso_laboral", "maltrato_laboral", "amenazas_despido", "conductas_acoso"],
        "frequently_consulted": True,
    },
    {
        "article_number": "8",
        "article_title": "SANCIONES",
        "chapter": "Capítulo III - Sanciones",
        "text": (
            "Cuando se determine que una conducta constituye acoso laboral, los "
            "correctivos y sanciones que impondrán los inspectores del trabajo, el "
            "Ministerio Público, los responsables del control disciplinario interno "
            "o los jueces competentes, según sea el caso, serán los siguientes: "
            "\n\n1. Como falta disciplinaria gravísima en el Código Disciplinario "
            "Único, cuando su autor sea un servidor público. "
            "\n\n2. Como terminación del contrato sin justa causa, cuando haya dado "
            "lugar a la renuncia o el abandono del trabajo por parte del trabajador "
            "regido por el Código Sustantivo del Trabajo. En tal caso procede la "
            "indemnización en los términos del artículo 64 del Código Sustantivo del "
            "Trabajo. "
            "\n\n3. Con sanción de multa entre dos (2) y diez (10) salarios mínimos "
            "legales mensuales para la persona que lo realice y para el empleador que "
            "lo tolere. "
            "\n\n4. Con la obligación de pagar a las Empresas Prestadoras de Salud y "
            "las Aseguradoras de riesgos profesionales el cincuenta por ciento (50%) "
            "del costo del tratamiento de enfermedades profesionales, alteraciones de "
            "salud y demás secuelas originadas en el acoso laboral. Esta obligación "
            "corre por cuenta del empleador que haya ocasionado el acoso laboral o "
            "que lo haya tolerado, sin perjuicio de la acción de repetición que "
            "incumbe a este contra el autor del acoso."
        ),
        "topics": ["acoso_laboral", "sanciones", "indemnización", "terminación_contrato"],
        "frequently_consulted": True,
    },
    {
        "article_number": "9",
        "article_title": "MEDIDAS DE PROTECCIÓN A LAS VÍCTIMAS DE ACOSO LABORAL",
        "chapter": "Capítulo III - Sanciones",
        "text": (
            "En cualquier momento y sin consideración a la etapa en que se encuentre "
            "la actuación o proceso, las víctimas del acoso laboral podrán pedir al "
            "inspector de trabajo o al juez competente, en forma motivada y seria, la "
            "adopción de una o varias de las siguientes medidas cautelares: "
            "\n\n1. La reubicación en el lugar de trabajo; "
            "\n2. El traslado de quien realiza las conductas constitutivas de acoso "
            "laboral; "
            "\n3. La licencia con o sin remuneración hasta tanto se resuelva la "
            "situación de acoso laboral; "
            "\n4. El otorgamiento de otras medidas encaminadas a hacer cesar las "
            "conductas de acoso laboral. "
            "\n\nParágrafo. Las medidas de protección a que se refiere el presente "
            "artículo no implican el reconocimiento por parte del Ministerio del "
            "Trabajo ni del juez que las decreta, de la existencia del acoso laboral. "
            "Solo buscan conjurar la situación de peligro en que se encuentra la "
            "víctima mientras se adelanta el proceso."
        ),
        "topics": ["acoso_laboral", "protección_trabajador", "medidas_cautelares"],
        "frequently_consulted": True,
    },
    {
        "article_number": "10",
        "article_title": "TRÁMITE DE LAS QUEJAS DE ACOSO LABORAL",
        "chapter": "Capítulo IV - Procedimiento",
        "text": (
            "Quien se considere víctima de una conducta de acoso laboral bajo alguna "
            "de las modalidades descritas en el artículo 2o de la presente ley, podrá "
            "poner en conocimiento del Inspector de Trabajo con competencia en el lugar "
            "de los hechos, de los Inspectores Municipales de Policía, de los "
            "Personeros Municipales o de la Defensoría del Pueblo, a prevención, la "
            "ocurrencia de estas situaciones con el fin de que se adelanten las "
            "investigaciones pertinentes y se impongan las sanciones y medidas "
            "correctivas del caso. "
            "\n\nLa queja podrá ser verbal o escrita y contener: la descripción de "
            "los hechos, la indicación del lugar de trabajo donde ocurrieron, el nombre "
            "de quien o quienes los realizaron y el tiempo de duración de las conductas. "
            "\n\nParágrafo. Los empleados oficiales y los servidores públicos deberán "
            "instaurar la queja de acoso laboral ante el Ministerio Público, lo que no "
            "será impedimento para que el afectado acuda directamente ante el juez "
            "competente. "
            "\n\nNota: El plazo para interponer la queja es de seis (6) meses contados "
            "a partir de la ocurrencia del último hecho constitutivo de acoso laboral "
            "(prescripción de 6 meses — Art. 10 Ley 1010/2006)."
        ),
        "topics": ["acoso_laboral", "prescripción", "queja_laboral", "inspector_trabajo"],
        "frequently_consulted": True,
    },
    {
        "article_number": "11",
        "article_title": "INTERVENCIÓN DE LAS INSPECCIONES DEL TRABAJO",
        "chapter": "Capítulo IV - Procedimiento",
        "text": (
            "Los Inspectores de Trabajo adoptarán las medidas que se impongan de "
            "conformidad con la facultad que les confieren el Código Sustantivo del "
            "Trabajo y las demás normas que lo modifiquen, adicionen o reglamenten. "
            "Podrán también formular recomendaciones para modificar los métodos de "
            "trabajo y deberán asistir al empleador y trabajador en la solución de "
            "las inconformidades que contribuyan al acoso laboral. "
            "\n\nLa intervención de las Inspecciones de Trabajo y la imposición de "
            "sanciones, será sin perjuicio de las acciones que le correspondan "
            "adelantar a las entidades del Ministerio Público o las instancias "
            "judiciales competentes. "
            "\n\nParágrafo. El proceso sancionatorio a que se refiere el presente "
            "artículo se desarrollará de conformidad con los artículos 485 y "
            "siguientes del Código Sustantivo del Trabajo."
        ),
        "topics": ["acoso_laboral", "inspector_trabajo", "sanciones"],
        "frequently_consulted": False,
    },
    {
        "article_number": "12",
        "article_title": "MODIFICA EL CÓDIGO SUSTANTIVO DEL TRABAJO",
        "chapter": "Capítulo V - Disposiciones finales",
        "text": (
            "Adiciónase el Artículo 104 del Código Sustantivo del Trabajo con los "
            "siguientes incisos: "
            "\n'El reglamento interno de trabajo deberá contener un capítulo especial "
            "sobre la prevención del acoso laboral. Dicho capítulo contendrá: "
            "\na) Los mecanismos de prevención de las conductas de acoso laboral; "
            "\nb) Un procedimiento interno confidencial, conciliatorio y efectivo para "
            "superar los que ocurran en el lugar de trabajo; "
            "\nc) Las medidas preventivas y correctivas del acoso laboral. "
            "\nEl incumplimiento de esta disposición será sancionado administrativamente "
            "por el Inspector del Trabajo con multas de hasta cien (100) salarios "
            "mínimos legales mensuales vigentes.'"
        ),
        "topics": ["acoso_laboral", "reglamento_interno", "contrato_trabajo"],
        "frequently_consulted": False,
    },
    {
        "article_number": "13",
        "article_title": "DISPOSICIONES TRANSITORIAS",
        "chapter": "Capítulo V - Disposiciones finales",
        "text": (
            "Los trabajadores que antes de la vigencia de esta ley hayan presentado "
            "situaciones de acoso laboral tendrán un plazo de seis (6) meses para "
            "acogerse al procedimiento establecido en la presente ley. "
            "\n\nDurante este período de transición los trabajadores podrán presentar "
            "las quejas ante el inspector de trabajo competente."
        ),
        "topics": ["acoso_laboral"],
        "frequently_consulted": False,
    },
    {
        "article_number": "14",
        "article_title": "VIGENCIA",
        "chapter": "Capítulo V - Disposiciones finales",
        "text": (
            "La presente ley rige a partir de la fecha de su promulgación y deroga "
            "todas las disposiciones que le sean contrarias. "
            "\n\nPromulgada el 23 de enero de 2006. Diario Oficial Número 46.160."
        ),
        "topics": ["acoso_laboral"],
        "frequently_consulted": False,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Generación de chunks
# ═══════════════════════════════════════════════════════════════════════════════

SOURCE = "Ley_1010"
SOURCE_HEADER = "Ley 1010 de 2006 | Acoso Laboral | Colombia"


@dataclass
class LegalChunk:
    chunk_id: str = ""
    text_for_embedding: str = ""
    source: str = ""
    book: str = ""
    title: str = ""
    chapter: str = ""
    article_number: str = ""
    article_number_int: int = 0
    article_title: str = ""
    text: str = ""
    topics: list = field(default_factory=list)
    modified_by: str = ""
    effective_date: str = ""
    derogated: bool = False
    frequently_consulted: bool = False
    chunk_type: str = "article"
    articles_in_group: list = field(default_factory=list)


def make_chunks() -> list[LegalChunk]:
    """Convierte los artículos codificados en chunks para Qdrant."""
    chunks: list[LegalChunk] = []

    for art in LEY_1010_ARTICLES:
        num_str = art["article_number"]
        try:
            num_int = int(num_str)
        except ValueError:
            num_int = 0

        chapter = art.get("chapter", "")
        art_title = art.get("article_title", "")
        text = art.get("text", "")

        # Header de contexto idéntico al formato de chunk_corpus.py
        header = f"{SOURCE_HEADER} | {chapter}"

        # Texto para embedding: header + título + cuerpo
        text_for_embedding = (
            f"{header}\n\nArtículo {num_str}: {art_title}\n{text}"
            if art_title
            else f"{header}\n\nArtículo {num_str}: {text}"
        )

        chunk = LegalChunk(
            chunk_id=f"ley_1010_art_{num_str}_article",
            text_for_embedding=text_for_embedding,
            source=SOURCE,
            book="Ley 1010 de 2006",
            title="Acoso Laboral",
            chapter=chapter,
            article_number=num_str,
            article_number_int=num_int,
            article_title=art_title,
            text=text,
            topics=art.get("topics", ["acoso_laboral"]),
            modified_by="",
            effective_date="2006-01-23",
            derogated=False,
            frequently_consulted=art.get("frequently_consulted", False),
            chunk_type="article",
        )
        chunks.append(chunk)

    # ── Chunk de grupo: Arts. 2 + 7 (definición + conductas) ─────────────────
    # Cuando alguien pregunta por acoso laboral en general, este chunk combina
    # la definición con el catálogo de conductas — el contexto más relevante.
    art2 = next(c for c in chunks if c.article_number == "2")
    art7 = next(c for c in chunks if c.article_number == "7")

    group_text = (
        f"Artículo 2: {art2.article_title}\n{art2.text}"
        f"\n\nArtículo 7: {art7.article_title}\n{art7.text}"
    )
    group_chunk = LegalChunk(
        chunk_id="ley_1010_group_acoso_2_7",
        text_for_embedding=(
            f"{SOURCE_HEADER} | Definición y conductas de acoso laboral\n\n"
            + group_text
        ),
        source=SOURCE,
        book="Ley 1010 de 2006",
        title="Acoso Laboral",
        chapter="Capítulo I-II — Definición y modalidades",
        article_number="2-7",
        article_number_int=2,
        article_title="Definición, modalidades y conductas constitutivas de acoso laboral",
        text=group_text,
        topics=["acoso_laboral", "maltrato_laboral", "persecución_laboral",
                "conductas_acoso", "amenazas_despido"],
        effective_date="2006-01-23",
        frequently_consulted=True,
        chunk_type="group",
        articles_in_group=["2", "7"],
    )
    chunks.append(group_chunk)

    # ── Chunk de grupo: Arts. 8 + 9 (sanciones + protección víctima) ─────────
    art8 = next(c for c in chunks if c.article_number == "8")
    art9 = next(c for c in chunks if c.article_number == "9")

    group_sanciones_text = (
        f"Artículo 8: {art8.article_title}\n{art8.text}"
        f"\n\nArtículo 9: {art9.article_title}\n{art9.text}"
    )
    group_sanciones = LegalChunk(
        chunk_id="ley_1010_group_sanciones_8_9",
        text_for_embedding=(
            f"{SOURCE_HEADER} | Sanciones y medidas de protección\n\n"
            + group_sanciones_text
        ),
        source=SOURCE,
        book="Ley 1010 de 2006",
        title="Acoso Laboral",
        chapter="Capítulo III — Sanciones y protección",
        article_number="8-9",
        article_number_int=8,
        article_title="Sanciones al acoso laboral y medidas de protección a la víctima",
        text=group_sanciones_text,
        topics=["acoso_laboral", "sanciones", "indemnización", "protección_trabajador"],
        effective_date="2006-01-23",
        frequently_consulted=True,
        chunk_type="group",
        articles_in_group=["8", "9"],
    )
    chunks.append(group_sanciones)

    return chunks


# ═══════════════════════════════════════════════════════════════════════════════
# Actualización de chunks.json (incremental)
# ═══════════════════════════════════════════════════════════════════════════════

def update_chunks_json(new_chunks: list[LegalChunk], reset_source: bool = False) -> int:
    """
    Añade los chunks de Ley_1010 al chunks.json existente.
    Si reset_source=True, elimina primero los chunks de source=Ley_1010.
    Retorna el número de chunks nuevos añadidos.
    """
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if CHUNKS_PATH.exists():
        existing = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
        print(f"chunks.json actual: {len(existing)} chunks")

    if reset_source:
        antes = len(existing)
        existing = [c for c in existing if c.get("source") != SOURCE]
        print(f"  Eliminados {antes - len(existing)} chunks de {SOURCE} (--reset-source)")

    # IDs ya existentes
    existing_ids = {c["chunk_id"] for c in existing}

    added = 0
    for chunk in new_chunks:
        if chunk.chunk_id not in existing_ids:
            existing.append(asdict(chunk))
            added += 1
        else:
            print(f"  [SKIP] Ya existe: {chunk.chunk_id}")

    CHUNKS_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"chunks.json actualizado: {len(existing)} chunks totales (+{added} nuevos)")
    return added


# ═══════════════════════════════════════════════════════════════════════════════
# Carga incremental a Qdrant
# ═══════════════════════════════════════════════════════════════════════════════

def load_to_qdrant(chunks: list[LegalChunk], reset_source: bool = False) -> None:
    """Vectoriza y carga los chunks de Ley_1010 en Qdrant (sin resetear la colección)."""
    try:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
    except ImportError as e:
        print(f"[ERROR] Dependencia faltante: {e}")
        print("  pip install sentence-transformers qdrant-client")
        sys.exit(1)

    # Conectar a Qdrant
    print(f"\nConectando a Qdrant en {QDRANT_HOST}:{QDRANT_PORT}...")
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10)
        info = client.get_collections()
        print(f"  Conectado. Colecciones: {[c.name for c in info.collections]}")
    except Exception as e:
        print(f"  [WARN] Docker Qdrant no disponible ({e})")
        print(f"  Fallback: Qdrant en disco -> {QDRANT_LOCAL_PATH}")
        client = QdrantClient(path=QDRANT_LOCAL_PATH)

    # Verificar que la colección existe
    existing_cols = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing_cols:
        print(f"[ERROR] Colección '{COLLECTION_NAME}' no existe.")
        print("  Ejecuta primero: python corpus/scripts/generate_embeddings.py")
        sys.exit(1)

    col_info = client.get_collection(COLLECTION_NAME)
    print(f"  Colección '{COLLECTION_NAME}': {col_info.points_count} puntos actuales")

    # Si reset_source: eliminar puntos de Ley_1010 existentes
    if reset_source:
        print(f"  Eliminando puntos de source='{SOURCE}'...")
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=SOURCE))]
            ),
        )
        print("  Puntos eliminados.")

    # Verificar qué IDs ya existen para carga incremental
    print("  Verificando IDs existentes...")
    existing_uuids: set[str] = set()
    try:
        scroll_result = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=SOURCE))]
            ),
            limit=500,
            with_payload=False,
            with_vectors=False,
        )
        existing_uuids = {str(p.id) for p in scroll_result[0]}
        print(f"  {len(existing_uuids)} puntos de {SOURCE} ya existen")
    except Exception:
        pass  # Colección sin índice en 'source', continuar

    # Cargar modelo de embeddings
    print(f"\nCargando modelo: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    dim = model.get_sentence_embedding_dimension()
    print(f"  Dimensión: {dim}")

    # Vectorizar y cargar
    to_load = [
        c for c in chunks
        if chunk_id_to_uuid(c.chunk_id) not in existing_uuids
    ]

    if not to_load:
        print("  Todos los chunks ya existen en Qdrant. Nada que cargar.")
        return

    print(f"\nVectorizando {len(to_load)} chunks nuevos...")
    texts = [c.text_for_embedding for c in to_load]
    t0 = time.time()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    print(f"  Embeddings generados en {time.time() - t0:.1f}s")

    points = []
    for chunk, vector in zip(to_load, vectors):
        payload = asdict(chunk)
        payload.pop("text_for_embedding", None)  # No duplicar en payload
        points.append(
            PointStruct(
                id=chunk_id_to_uuid(chunk.chunk_id),
                vector=vector.tolist(),
                payload=payload,
            )
        )

    print(f"Cargando {len(points)} puntos en Qdrant...")
    client.upsert(collection_name=COLLECTION_NAME, points=points)

    col_info_post = client.get_collection(COLLECTION_NAME)
    print(f"✅ Qdrant actualizado: {col_info_post.points_count} puntos totales")


# ═══════════════════════════════════════════════════════════════════════════════
# Validación
# ═══════════════════════════════════════════════════════════════════════════════

def validate(query: str = "mi jefe me grita y me amenaza con despedirme") -> None:
    """Busca la query de validación en Qdrant y muestra los top resultados."""
    try:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient
    except ImportError:
        print("[SKIP] sentence-transformers o qdrant-client no disponibles para validación")
        return

    print(f"\n{'='*60}")
    print(f"VALIDACIÓN — Query: '{query}'")
    print("="*60)

    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
        client.get_collections()
    except Exception:
        client = QdrantClient(path=QDRANT_LOCAL_PATH)

    model = SentenceTransformer(EMBEDDING_MODEL)
    query_vec = model.encode([query], normalize_embeddings=True)[0].tolist()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec,
        limit=5,
        with_payload=True,
    )

    for i, point in enumerate(results.points, 1):
        p = point.payload or {}
        score = getattr(point, "score", 0.0)
        source = p.get("source", "?")
        art_num = p.get("article_number", "?")
        art_title = p.get("article_title", "")
        chunk_type = p.get("chunk_type", "article")
        topics = p.get("topics", [])
        snippet = (p.get("text") or "")[:120].replace("\n", " ")

        marker = "🎯" if source == SOURCE else "  "
        print(
            f"\n{marker} [{i}] {source} Art.{art_num} [{chunk_type}] — score={score:.4f}"
            f"\n     Título: {art_title}"
            f"\n     Topics: {topics}"
            f"\n     Texto:  {snippet}..."
        )

    ley1010_found = any(
        (p.payload or {}).get("source") == SOURCE
        for p in results.points
    )
    print(f"\n{'✅ Ley 1010 aparece en top-5' if ley1010_found else '❌ Ley 1010 NO aparece en top-5 — revisar embeddings'}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta Ley 1010/2006 (Acoso Laboral) al corpus de LaborIA."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Muestra chunks sin modificar chunks.json ni Qdrant",
    )
    parser.add_argument(
        "--reset-source", action="store_true",
        help="Elimina chunks de Ley_1010 existentes antes de reinsertar",
    )
    parser.add_argument(
        "--skip-qdrant", action="store_true",
        help="Solo actualiza chunks.json, no carga a Qdrant",
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Solo ejecuta la validación (asume que ya está cargado)",
    )
    args = parser.parse_args()

    if args.validate_only:
        validate()
        return

    # 1. Generar chunks
    print("=" * 60)
    print("LaborIA — Ingestión Ley 1010 de 2006 (Acoso Laboral)")
    print("=" * 60)

    chunks = make_chunks()
    article_chunks = [c for c in chunks if c.chunk_type == "article"]
    group_chunks   = [c for c in chunks if c.chunk_type == "group"]

    print(f"\nChunks generados:")
    print(f"  Artículos: {len(article_chunks)}")
    print(f"  Grupos:    {len(group_chunks)}")
    print(f"  Total:     {len(chunks)}")

    if args.dry_run:
        print("\n[DRY RUN] Muestra de chunks:")
        for c in chunks[:3]:
            print(f"\n  chunk_id: {c.chunk_id}")
            print(f"  topics:   {c.topics}")
            print(f"  texto:    {c.text_for_embedding[:200]}...")
        print("\n[DRY RUN] Sin cambios en chunks.json ni Qdrant.")
        return

    # 2. Actualizar chunks.json
    print(f"\n[1/3] Actualizando {CHUNKS_PATH}...")
    added = update_chunks_json(chunks, reset_source=args.reset_source)

    if added == 0 and not args.reset_source:
        print("  Todos los chunks ya existen. Usa --reset-source para reinsertar.")

    # 3. Cargar a Qdrant
    if not args.skip_qdrant:
        print("\n[2/3] Cargando en Qdrant...")
        load_to_qdrant(chunks, reset_source=args.reset_source)
    else:
        print("\n[2/3] Qdrant omitido (--skip-qdrant).")

    # 4. Validar
    print("\n[3/3] Validando...")
    validate()

    print("\n✅ Ingestión de Ley 1010 completada.")
    print("   El backend necesita reiniciarse para recargar el índice BM25.")
    print("   Ejecuta: uvicorn app.main:app --port 8080 --reload")


if __name__ == "__main__":
    main()
