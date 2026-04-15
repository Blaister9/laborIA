"""
check_deadlines.py — Verificación de plazos de prescripción y caducidad laboral.

Plazos implementados:
  - Art. 488 CST: prescripción ordinaria laboral (3 años)
  - Art. 489 CST: interrupción de prescripción por reclamación escrita
  - Decreto 2591/1991 + jurisprudencia CC: tutela (máximo 6 meses)
  - Ley 1010/2006 Art. 18: acoso laboral — denuncia interna (6 meses)
  - Ley 1010/2006: acciones penales por acoso (5 años)
  - Fuero sindical Art. 118 CST: acción de reintegro (2 meses)
  - Pensión: prescripción de mesadas (3 años por mesada)
  - Accidente de trabajo / enfermedad laboral (3 años)
  - Caducidad acción de nulidad CPACA Art. 164: 4 meses (entidades públicas)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


# ── Modelos ──────────────────────────────────────────────────────────────────

@dataclass
class Plazo:
    concepto: str
    fecha_inicio: date
    duracion_dias: int
    fecha_limite: date
    dias_restantes: int          # negativo = ya venció
    estado: str                  # "vigente" | "inmiente" | "vencido"
    descripcion: str
    articulo: str
    advertencia: str = ""


@dataclass
class ResultadoPlazos:
    fecha_evento: date
    fecha_consulta: date
    tipo_evento: str
    plazos: list[Plazo]
    alertas_criticas: list[str]
    notas: list[str]


# ── Cálculo de estado ─────────────────────────────────────────────────────────

def _estado(dias_restantes: int) -> str:
    if dias_restantes < 0:
        return "vencido"
    if dias_restantes <= 30:
        return "inminente"
    return "vigente"


def _plazo(
    concepto: str,
    fecha_inicio: date,
    dias: int,
    hoy: date,
    descripcion: str,
    articulo: str,
    advertencia: str = "",
) -> Plazo:
    fecha_limite = fecha_inicio + timedelta(days=dias)
    dias_restantes = (fecha_limite - hoy).days
    return Plazo(
        concepto=concepto,
        fecha_inicio=fecha_inicio,
        duracion_dias=dias,
        fecha_limite=fecha_limite,
        dias_restantes=dias_restantes,
        estado=_estado(dias_restantes),
        descripcion=descripcion,
        articulo=articulo,
        advertencia=advertencia,
    )


# ── Calculadora principal ─────────────────────────────────────────────────────

def verificar_plazos(
    *,
    fecha_evento: str,
    tipo_evento: str = "despido",
    conceptos_a_reclamar: list[str] | None = None,
    fecha_consulta: str | None = None,
) -> ResultadoPlazos:
    """
    Calcula y evalúa todos los plazos relevantes para un evento laboral.

    Args:
        fecha_evento: Fecha del evento (despido, accidente, fin contrato...) YYYY-MM-DD.
        tipo_evento: "despido" | "fin_contrato" | "accidente_trabajo" |
                     "acoso_laboral" | "fuero_sindical" | "pension" | "otro"
        conceptos_a_reclamar: Lista de conceptos específicos. Si None, calcula todos.
        fecha_consulta: Fecha de referencia para calcular días restantes. Default: hoy.
    """
    evento = _parse_fecha(fecha_evento)
    hoy = _parse_fecha(fecha_consulta) if fecha_consulta else date.today()
    dias_transcurridos = (hoy - evento).days

    plazos: list[Plazo] = []
    alertas: list[str] = []
    notas: list[str] = []

    reclamar = set(conceptos_a_reclamar) if conceptos_a_reclamar else None

    # ── Prescripción laboral general (Art. 488 CST) ───────────────────────────
    # Aplica a todos los créditos laborales: salarios, cesantías, prima,
    # vacaciones, indemnizaciones.
    TRES_ANOS = 365 * 3 + 1  # ~3 años (incluye bisiesto)

    conceptos_prescripcion = {
        "cesantias": "Cesantías (Art. 249-255 CST)",
        "intereses_cesantias": "Intereses sobre cesantías (Art. 99 Ley 50/1990)",
        "prima": "Prima de servicios (Art. 306 CST)",
        "vacaciones": "Vacaciones (Art. 186 CST)",
        "salarios": "Salarios adeudados (Art. 132-133 CST)",
        "indemnizacion": "Indemnización por despido sin justa causa (Art. 64 CST)",
        "pension": "Mesadas pensionales (Art. 488 CST)",
    }

    for clave, nombre in conceptos_prescripcion.items():
        if reclamar is None or clave in reclamar:
            p = _plazo(
                concepto=f"Prescripción — {nombre}",
                fecha_inicio=evento,
                dias=TRES_ANOS,
                hoy=hoy,
                descripcion=(
                    f"Plazo para reclamar {nombre.lower()} vence 3 años después "
                    f"del {evento.strftime('%d/%m/%Y')}."
                ),
                articulo="Art. 488 CST",
                advertencia=(
                    "La prescripción se interrumpe una sola vez mediante reclamación "
                    "escrita al empleador (Art. 489 CST), lo que reinicia el plazo de 3 años."
                ) if dias_transcurridos > 365 else "",
            )
            plazos.append(p)

    # ── Tutela ───────────────────────────────────────────────────────────────
    if reclamar is None or "tutela" in reclamar:
        SEIS_MESES = 183
        p = _plazo(
            concepto="Acción de tutela (violación de derechos fundamentales)",
            fecha_inicio=evento,
            dias=SEIS_MESES,
            hoy=hoy,
            descripcion=(
                "La Corte Constitucional ha establecido que la tutela pierde "
                "inmediatez si se interpone después de ~6 meses del hecho vulnerador "
                "(T-1028/2010, SU-173/2015). No hay plazo legal estricto, pero se "
                "puede declarar improcedente por falta de inmediatez."
            ),
            articulo="Art. 86 C.P. / Decreto 2591/1991",
            advertencia="Interponer cuanto antes; no esperar los 6 meses.",
        )
        plazos.append(p)

    # ── Acoso laboral ─────────────────────────────────────────────────────────
    if tipo_evento == "acoso_laboral" or (reclamar and "acoso" in reclamar):
        plazos.append(_plazo(
            concepto="Denuncia ante Comité de Convivencia o Inspector de Trabajo",
            fecha_inicio=evento,
            dias=180,
            hoy=hoy,
            descripcion="Plazo para formular queja interna o ante el inspector (Art. 18 Ley 1010/2006).",
            articulo="Art. 18 Ley 1010/2006",
            advertencia="Transcurridos 6 meses sin denuncia se puede perder la protección.",
        ))
        plazos.append(_plazo(
            concepto="Acción penal por acoso laboral",
            fecha_inicio=evento,
            dias=365 * 5,
            hoy=hoy,
            descripcion="Prescripción de la acción penal por el delito de acoso laboral (5 años).",
            articulo="Art. 220A C.P. / Ley 1010/2006",
        ))

    # ── Fuero sindical ────────────────────────────────────────────────────────
    if tipo_evento == "fuero_sindical" or (reclamar and "fuero_sindical" in reclamar):
        plazos.append(_plazo(
            concepto="Acción de reintegro por despido con fuero sindical",
            fecha_inicio=evento,
            dias=60,  # 2 meses
            hoy=hoy,
            descripcion=(
                "El trabajador con fuero sindical tiene 2 meses para solicitar "
                "su reintegro ante el juez laboral (Art. 118 CST)."
            ),
            articulo="Art. 118 CST",
            advertencia="URGENTE: plazo muy corto. Actuar de inmediato.",
        ))

    # ── Accidente de trabajo / enfermedad laboral ─────────────────────────────
    if tipo_evento == "accidente_trabajo" or (reclamar and "accidente" in reclamar):
        plazos.append(_plazo(
            concepto="Reclamación por accidente de trabajo o enfermedad laboral",
            fecha_inicio=evento,
            dias=TRES_ANOS,
            hoy=hoy,
            descripcion=(
                "3 años desde la fecha del accidente o desde que se calificó la enfermedad "
                "como de origen laboral para reclamar prestaciones económicas y asistenciales."
            ),
            articulo="Art. 488 CST / Art. 6 Ley 776/2002",
        ))

    # ── Caducidad acción ante lo contencioso (empleados públicos) ────────────
    if reclamar and "contencioso" in reclamar:
        plazos.append(_plazo(
            concepto="Caducidad acción de nulidad y restablecimiento (empleados públicos)",
            fecha_inicio=evento,
            dias=120,  # 4 meses
            hoy=hoy,
            descripcion=(
                "Para trabajadores vinculados con el Estado: 4 meses para impugnar "
                "el acto administrativo de desvinculación ante la jurisdicción "
                "contencioso-administrativa (CPACA Art. 164 #2-d)."
            ),
            articulo="Art. 164 #2-d CPACA (Ley 1437/2011)",
            advertencia="Plazo de caducidad: no se interrumpe ni suspende.",
        ))

    # ── Alertas críticas ──────────────────────────────────────────────────────
    for p in plazos:
        if p.estado == "vencido":
            alertas.append(
                f"⚠️  VENCIDO: '{p.concepto}' — venció el {p.fecha_limite.strftime('%d/%m/%Y')} "
                f"(hace {abs(p.dias_restantes)} días)."
            )
        elif p.estado == "inminente":
            alertas.append(
                f"🔴 INMINENTE: '{p.concepto}' — vence el {p.fecha_limite.strftime('%d/%m/%Y')} "
                f"(en {p.dias_restantes} días)."
            )

    # ── Notas generales ───────────────────────────────────────────────────────
    notas.append(
        "La prescripción laboral se interrumpe una sola vez mediante reclamación escrita "
        "al empleador (Art. 489 CST), reiniciando el plazo de 3 años desde esa fecha."
    )
    notas.append(
        "Para mayor seguridad, iniciar el proceso judicial antes de que venza la mitad del plazo."
    )
    if dias_transcurridos > 365 * 2:
        notas.append(
            f"ATENCIÓN: Han transcurrido {dias_transcurridos} días ({dias_transcurridos/365:.1f} años) "
            "desde el evento. Verificar si ya hay prescripción."
        )

    return ResultadoPlazos(
        fecha_evento=evento,
        fecha_consulta=hoy,
        tipo_evento=tipo_evento,
        plazos=plazos,
        alertas_criticas=alertas,
        notas=notas,
    )


def _parse_fecha(s: str) -> date:
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        raise ValueError(f"Fecha inválida: '{s}'. Usa formato YYYY-MM-DD.")


# ── Tool runner ───────────────────────────────────────────────────────────────

def run_check_deadlines(tool_input: dict) -> str:
    """Ejecuta la verificación de plazos desde el input de Claude."""
    try:
        resultado = verificar_plazos(
            fecha_evento=str(tool_input["fecha_evento"]),
            tipo_evento=tool_input.get("tipo_evento", "despido"),
            conceptos_a_reclamar=tool_input.get("conceptos_a_reclamar"),
            fecha_consulta=tool_input.get("fecha_consulta"),
        )
    except (KeyError, ValueError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    output = {
        "fecha_evento": resultado.fecha_evento.isoformat(),
        "fecha_consulta": resultado.fecha_consulta.isoformat(),
        "tipo_evento": resultado.tipo_evento,
        "alertas_criticas": resultado.alertas_criticas,
        "plazos": [
            {
                "concepto": p.concepto,
                "articulo": p.articulo,
                "fecha_limite": p.fecha_limite.isoformat(),
                "dias_restantes": p.dias_restantes,
                "estado": p.estado,
                "descripcion": p.descripcion,
                "advertencia": p.advertencia or None,
            }
            for p in resultado.plazos
        ],
        "notas": resultado.notas,
    }
    return json.dumps(output, ensure_ascii=False, indent=2)
