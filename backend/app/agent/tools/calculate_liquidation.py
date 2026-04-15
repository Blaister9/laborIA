"""
calculate_liquidation.py — Calculadora de liquidación laboral colombiana.

Implementa las fórmulas vigentes según:
  - Art. 249-255 CST: Cesantías
  - Art. 99 Ley 50/1990: Intereses sobre cesantías (12% anual)
  - Art. 306 CST: Prima de servicios
  - Art. 186-189 CST: Vacaciones
  - Art. 64 CST (mod. Ley 789/2002): Indemnización por despido sin justa causa
  - Ley 2466/2025: sin cambios en fórmulas de liquidación base (afecta recargos)

Constantes 2025 (Decretos 2484 y 2485 de 2024):
  SMMLV: $1.423.500 COP
  Auxilio de transporte: $200.000 COP
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

# ── Constantes 2025 ──────────────────────────────────────────────────────────
SMMLV_2025: int = 1_423_500      # Decreto 2484 del 31-dic-2024
AUX_TRANSPORTE_2025: int = 200_000  # Decreto 2485 del 31-dic-2024

# Para años anteriores (cálculos históricos parciales se dejan como nota)
SMMLV_ACTUAL = SMMLV_2025
AUX_TRANSPORTE_ACTUAL = AUX_TRANSPORTE_2025


# ── Modelos de datos ─────────────────────────────────────────────────────────

@dataclass
class ConceptoCalculo:
    nombre: str
    valor: float
    formula_usada: str
    base_salarial: float
    dias: float
    articulo: str
    aplica: bool = True
    notas: list[str] = field(default_factory=list)


@dataclass
class ResultadoLiquidacion:
    conceptos: list[ConceptoCalculo]
    total: float
    periodo_texto: str
    dias_calendario: int
    salario_mensual: float
    salario_diario: float
    salario_base_prestaciones: float   # incluye aux_transporte si aplica
    smmlv_referencia: float
    es_salario_integral: bool
    advertencias: list[str]
    referencias_legales: list[str]


# ── Utilidades de fecha ───────────────────────────────────────────────────────

def _periodo_texto(inicio: date, fin: date, dias: int) -> str:
    """Devuelve descripción legible del período trabajado."""
    anios = dias // 365
    resto = dias % 365
    meses = resto // 30
    dias_sueltos = resto % 30
    partes = []
    if anios:
        partes.append(f"{anios} año{'s' if anios > 1 else ''}")
    if meses:
        partes.append(f"{meses} mes{'es' if meses > 1 else ''}")
    if dias_sueltos or not partes:
        partes.append(f"{dias_sueltos} día{'s' if dias_sueltos != 1 else ''}")
    return ", ".join(partes)


def _parse_fecha(s: str | None, default: date | None = None) -> date:
    if not s:
        return default or date.today()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return date.fromisoformat(s) if fmt == "%Y-%m-%d" else \
                   date(*(int(p) for p in s.split(fmt[2])))
        except Exception:
            pass
    # Try ISO format directly
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        raise ValueError(f"Fecha inválida: '{s}'. Usa formato YYYY-MM-DD.")


# ── Calculadora principal ─────────────────────────────────────────────────────

def calcular_liquidacion(
    *,
    salario_mensual: float,
    fecha_inicio: str,
    fecha_retiro: str | None = None,
    tipo_contrato: str = "indefinido",       # indefinido | fijo | obra
    motivo_retiro: str = "despido_sin_justa_causa",  # despido_sin_justa_causa | despido_justa_causa | renuncia | mutuo_acuerdo | fin_contrato
    salario_integral: bool = False,
    incluye_aux_transporte: bool | None = None,  # None = auto-detectar
    dias_restantes_contrato: int | None = None,   # solo para contratos fijos
) -> ResultadoLiquidacion:
    """
    Calcula la liquidación laboral completa.

    Args:
        salario_mensual: Salario mensual bruto en COP.
        fecha_inicio: Fecha de ingreso (YYYY-MM-DD).
        fecha_retiro: Fecha de retiro (YYYY-MM-DD). Default: hoy.
        tipo_contrato: "indefinido", "fijo", u "obra".
        motivo_retiro: Razón del retiro.
        salario_integral: True si el trabajador tiene salario integral (Art. 132 CST).
        incluye_aux_transporte: None = auto (aplica si salario ≤ 2 SMMLV).
        dias_restantes_contrato: Días que restaban en el contrato fijo (para indemnización).

    Returns:
        ResultadoLiquidacion con todos los conceptos desglosados.
    """
    advertencias: list[str] = []

    # ── Fechas y período ─────────────────────────────────────────────────────
    inicio = _parse_fecha(fecha_inicio)
    fin = _parse_fecha(fecha_retiro)

    if fin <= inicio:
        raise ValueError("La fecha de retiro debe ser posterior a la fecha de inicio.")

    dias_total = (fin - inicio).days
    salario_diario = salario_mensual / 30.0

    # ── Auxilio de transporte ─────────────────────────────────────────────────
    if incluye_aux_transporte is None:
        incluye_aux_transporte = salario_mensual <= 2 * SMMLV_ACTUAL

    if salario_integral:
        incluye_aux_transporte = False  # salario integral incluye todo

    aux_transporte = AUX_TRANSPORTE_ACTUAL if incluye_aux_transporte else 0

    # Base para cesantías y prima (Art. 7 Ley 1ª/1963: aux_transporte se
    # asimila a salario para efectos de prestaciones)
    salario_base_prestaciones = salario_mensual + aux_transporte

    # ── Referencias y advertencias ────────────────────────────────────────────
    referencias: list[str] = []

    if salario_integral:
        advertencias.append(
            "Salario integral (Art. 132 CST): no genera cesantías ni prima. "
            "El factor prestacional ya está incluido en el salario."
        )
    if incluye_aux_transporte:
        advertencias.append(
            f"Salario ≤ 2 SMMLV: auxilio de transporte "
            f"(${aux_transporte:,.0f}) se incluye en la base de cesantías y prima "
            "(Art. 7 Ley 1ª/1963 y Decreto 617/1954)."
        )

    conceptos: list[ConceptoCalculo] = []

    # ─────────────────────────────────────────────────────────────────────────
    # 1. CESANTÍAS (Art. 249-255 CST)
    # ─────────────────────────────────────────────────────────────────────────
    if not salario_integral:
        referencias.append("Art. 249-255 CST (Cesantías)")
        valor_ces = (salario_base_prestaciones * dias_total) / 360
        conceptos.append(ConceptoCalculo(
            nombre="Cesantías",
            valor=round(valor_ces, 2),
            formula_usada=f"(${salario_base_prestaciones:,.0f} × {dias_total} días) / 360",
            base_salarial=salario_base_prestaciones,
            dias=dias_total,
            articulo="Art. 249-255 CST",
            notas=[
                "Base incluye auxilio de transporte." if incluye_aux_transporte
                else "Base: salario mensual (sin aux. transporte)."
            ],
        ))
    else:
        conceptos.append(ConceptoCalculo(
            nombre="Cesantías", valor=0, formula_usada="No aplica — salario integral",
            base_salarial=0, dias=0, articulo="Art. 132 CST", aplica=False,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # 2. INTERESES SOBRE CESANTÍAS (Art. 99 Ley 50/1990 — 12 % anual)
    # ─────────────────────────────────────────────────────────────────────────
    if not salario_integral:
        referencias.append("Art. 99 Ley 50/1990 (Intereses cesantías 12% anual)")
        base_ints = conceptos[0].valor  # sobre el saldo de cesantías
        valor_ints = base_ints * 0.12 * (dias_total / 360)
        conceptos.append(ConceptoCalculo(
            nombre="Intereses sobre cesantías",
            valor=round(valor_ints, 2),
            formula_usada=f"${base_ints:,.0f} × 12% × ({dias_total} / 360)",
            base_salarial=base_ints,
            dias=dias_total,
            articulo="Art. 99 Ley 50/1990",
            notas=["Tasa del 12% anual sobre el saldo de cesantías acumulado."],
        ))
    else:
        conceptos.append(ConceptoCalculo(
            nombre="Intereses sobre cesantías", valor=0,
            formula_usada="No aplica — salario integral",
            base_salarial=0, dias=0, articulo="Art. 132 CST", aplica=False,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # 3. PRIMA DE SERVICIOS (Art. 306 CST — 15 días por semestre)
    #    Equivale a: salario × días / 360
    # ─────────────────────────────────────────────────────────────────────────
    if not salario_integral:
        referencias.append("Art. 306 CST (Prima de servicios)")
        valor_prima = (salario_base_prestaciones * dias_total) / 360
        conceptos.append(ConceptoCalculo(
            nombre="Prima de servicios",
            valor=round(valor_prima, 2),
            formula_usada=f"(${salario_base_prestaciones:,.0f} × {dias_total} días) / 360",
            base_salarial=salario_base_prestaciones,
            dias=dias_total,
            articulo="Art. 306 CST",
            notas=["15 días de salario por cada semestre trabajado (proporcional)."],
        ))
    else:
        conceptos.append(ConceptoCalculo(
            nombre="Prima de servicios", valor=0,
            formula_usada="No aplica — salario integral",
            base_salarial=0, dias=0, articulo="Art. 132 CST", aplica=False,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # 4. VACACIONES (Art. 186 CST — 15 días por año)
    #    Base: salario ordinario SIN aux_transporte
    #    Aplica también para salario integral
    # ─────────────────────────────────────────────────────────────────────────
    referencias.append("Art. 186-189 CST (Vacaciones)")
    valor_vac = (salario_mensual * dias_total) / 720
    conceptos.append(ConceptoCalculo(
        nombre="Vacaciones",
        valor=round(valor_vac, 2),
        formula_usada=f"(${salario_mensual:,.0f} × {dias_total} días) / 720",
        base_salarial=salario_mensual,
        dias=dias_total,
        articulo="Art. 186-189 CST",
        notas=[
            "15 días hábiles por año (proporcional). "
            "Base: salario ordinario sin auxilio de transporte.",
            "Si ya disfrutó vacaciones, descontar los días ya tomados.",
        ],
    ))

    # ─────────────────────────────────────────────────────────────────────────
    # 5. INDEMNIZACIÓN (Art. 64 CST — solo si hay despido sin justa causa)
    # ─────────────────────────────────────────────────────────────────────────
    valor_indemnizacion = 0.0
    indemnizacion_notas: list[str] = []
    formula_indemnizacion = "No aplica"
    aplica_indemnizacion = motivo_retiro == "despido_sin_justa_causa"

    if aplica_indemnizacion:
        referencias.append("Art. 64 CST (mod. Art. 28 Ley 789/2002) — Indemnización")

        total_anios_decimal = dias_total / 365.0
        alto_salario = salario_mensual >= 10 * SMMLV_ACTUAL

        if tipo_contrato == "indefinido" or tipo_contrato == "obra":
            if alto_salario:
                dias_primer_anio = 20
                dias_por_anio_adicional = 15
                grupo = "≥ 10 SMMLV"
            else:
                dias_primer_anio = 30
                dias_por_anio_adicional = 20
                grupo = "< 10 SMMLV"

            if total_anios_decimal <= 1:
                dias_indem = dias_primer_anio
                formula_indemnizacion = (
                    f"{dias_primer_anio} días × (${salario_mensual:,.0f} / 30) "
                    f"[≤ 1 año, {grupo}]"
                )
            else:
                fraccion_adicional = total_anios_decimal - 1
                dias_indem = dias_primer_anio + dias_por_anio_adicional * fraccion_adicional
                formula_indemnizacion = (
                    f"({dias_primer_anio} + {dias_por_anio_adicional} × {fraccion_adicional:.4f} años) "
                    f"× (${salario_mensual:,.0f} / 30) [{grupo}]"
                )

            valor_indemnizacion = salario_diario * dias_indem
            indemnizacion_notas = [
                f"Trabajador con salario {grupo} (10 SMMLV = ${10 * SMMLV_ACTUAL:,.0f}).",
                f"Tiempo trabajado: {total_anios_decimal:.2f} años ({dias_total} días).",
            ]

        elif tipo_contrato == "fijo":
            if dias_restantes_contrato and dias_restantes_contrato > 0:
                dias_indem = dias_restantes_contrato
                valor_indemnizacion = salario_diario * dias_indem
                formula_indemnizacion = (
                    f"{dias_indem} días restantes × (${salario_mensual:,.0f} / 30)"
                )
                indemnizacion_notas = [
                    "Contrato a término fijo: indemnización = salarios del tiempo restante (Art. 64 #1 CST).",
                ]
            else:
                valor_indemnizacion = salario_diario * 15  # mínimo legal
                formula_indemnizacion = "15 días (mínimo legal) × salario diario"
                indemnizacion_notas = [
                    "Días restantes no especificados. Se usa el mínimo legal de 15 días.",
                    "Proporcionar los días restantes del contrato para un cálculo exacto.",
                ]
                advertencias.append(
                    "Para contratos fijos, incluya 'dias_restantes_contrato' para calcular "
                    "la indemnización exacta."
                )

        if salario_integral:
            advertencias.append(
                "Salario integral: la indemnización se calcula sobre el 70% del salario integral "
                "(descontando el factor prestacional del 30%). Aquí se usa el salario reportado. "
                "Verifique si corresponde al 70%."
            )

    conceptos.append(ConceptoCalculo(
        nombre="Indemnización por despido sin justa causa",
        valor=round(valor_indemnizacion, 2),
        formula_usada=formula_indemnizacion,
        base_salarial=salario_mensual,
        dias=dias_total,
        articulo="Art. 64 CST",
        aplica=aplica_indemnizacion,
        notas=indemnizacion_notas if aplica_indemnizacion else [
            f"No aplica para motivo: {motivo_retiro}."
        ],
    ))

    # ── Total ────────────────────────────────────────────────────────────────
    total = sum(c.valor for c in conceptos if c.aplica)

    return ResultadoLiquidacion(
        conceptos=conceptos,
        total=round(total, 2),
        periodo_texto=_periodo_texto(inicio, fin, dias_total),
        dias_calendario=dias_total,
        salario_mensual=salario_mensual,
        salario_diario=round(salario_diario, 2),
        salario_base_prestaciones=salario_base_prestaciones,
        smmlv_referencia=SMMLV_ACTUAL,
        es_salario_integral=salario_integral,
        advertencias=advertencias,
        referencias_legales=referencias,
    )


# ── Tool runner (interfaz con el orquestador) ────────────────────────────────

def run_calculate_liquidation(tool_input: dict) -> str:
    """
    Ejecuta el cálculo de liquidación desde el input de Claude.
    Retorna JSON string con el resultado completo.
    """
    try:
        resultado = calcular_liquidacion(
            salario_mensual=float(tool_input["salario_mensual"]),
            fecha_inicio=str(tool_input["fecha_inicio"]),
            fecha_retiro=tool_input.get("fecha_retiro"),
            tipo_contrato=tool_input.get("tipo_contrato", "indefinido"),
            motivo_retiro=tool_input.get("motivo_retiro", "despido_sin_justa_causa"),
            salario_integral=bool(tool_input.get("salario_integral", False)),
            incluye_aux_transporte=tool_input.get("incluye_aux_transporte"),
            dias_restantes_contrato=tool_input.get("dias_restantes_contrato"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    # Serializar para Claude
    output = {
        "resumen": {
            "total_liquidacion": resultado.total,
            "total_formateado": f"${resultado.total:,.0f} COP",
            "periodo": resultado.periodo_texto,
            "dias_trabajados": resultado.dias_calendario,
            "salario_mensual": resultado.salario_mensual,
            "salario_diario": resultado.salario_diario,
            "smmlv_2025": resultado.smmlv_referencia,
        },
        "conceptos": [
            {
                "concepto": c.nombre,
                "valor": c.valor,
                "valor_formateado": f"${c.valor:,.0f} COP",
                "aplica": c.aplica,
                "formula": c.formula_usada,
                "articulo": c.articulo,
                "notas": c.notas,
            }
            for c in resultado.conceptos
        ],
        "advertencias": resultado.advertencias,
        "referencias_legales": resultado.referencias_legales,
    }
    return json.dumps(output, ensure_ascii=False, indent=2)
