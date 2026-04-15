"""
tool_descriptions.py — Esquemas de herramientas para Claude (function calling).

Herramientas disponibles:
  1. search_cst          — Búsqueda semántica en el corpus legal
  2. calculate_liquidation — Calculadora de liquidación laboral
  3. check_deadlines      — Verificador de plazos de prescripción
"""

TOOLS: list[dict] = [
    # ── 1. search_cst ─────────────────────────────────────────────────────────
    {
        "name": "search_cst",
        "description": (
            "Busca artículos relevantes en el Código Sustantivo del Trabajo (CST) "
            "y la Ley 2466/2025. Úsala SIEMPRE que necesites citar normativa antes "
            "de responder. Puedes llamarla varias veces con consultas distintas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Consulta en lenguaje natural. Ejemplos: "
                        "'indemnización por despido sin justa causa', "
                        "'recargo horas extra nocturnas', "
                        "'justa causa para terminar contrato'."
                    ),
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Filtro opcional por temas: "
                        "terminación_contrato, salario, jornada_trabajo, dominical, "
                        "vacaciones, maternidad, paternidad, cesantías, prima_servicios, "
                        "pensión, accidente_trabajo, sindicatos, prescripción, "
                        "acoso_laboral, trabajo_remoto, principios, contrato_trabajo."
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Número de artículos a retornar (1-10, default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },

    # ── 2. calculate_liquidation ──────────────────────────────────────────────
    {
        "name": "calculate_liquidation",
        "description": (
            "Calcula la liquidación laboral completa: cesantías (Art. 249 CST), "
            "intereses sobre cesantías (Art. 99 Ley 50/1990 — 12% anual), "
            "prima de servicios (Art. 306 CST), vacaciones (Art. 186 CST) e "
            "indemnización por despido sin justa causa (Art. 64 CST). "
            "Úsala cuando el usuario pregunte cuánto le deben de liquidación, "
            "cuánto vale el despido, o qué prestaciones le corresponden al retiro. "
            "Infiere los valores del contexto de la conversación; si faltan datos "
            "clave (salario, fecha inicio), pídelos al usuario ANTES de llamar esta herramienta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "salario_mensual": {
                    "type": "number",
                    "description": "Salario mensual bruto en pesos colombianos (COP).",
                },
                "fecha_inicio": {
                    "type": "string",
                    "description": "Fecha de inicio del contrato en formato YYYY-MM-DD.",
                },
                "fecha_retiro": {
                    "type": "string",
                    "description": (
                        "Fecha de retiro en formato YYYY-MM-DD. "
                        "Si no se menciona, usa la fecha de hoy."
                    ),
                },
                "tipo_contrato": {
                    "type": "string",
                    "enum": ["indefinido", "fijo", "obra"],
                    "description": "Tipo de contrato. Default: indefinido.",
                },
                "motivo_retiro": {
                    "type": "string",
                    "enum": [
                        "despido_sin_justa_causa",
                        "despido_justa_causa",
                        "renuncia",
                        "mutuo_acuerdo",
                        "fin_contrato",
                    ],
                    "description": (
                        "Motivo del retiro. Usa 'despido_sin_justa_causa' cuando el "
                        "empleador termina el contrato sin invocar causa legal. "
                        "Default: despido_sin_justa_causa."
                    ),
                },
                "salario_integral": {
                    "type": "boolean",
                    "description": (
                        "True si el salario es integral (Art. 132 CST — mínimo 13 SMMLV). "
                        "Los salarios integrales no generan cesantías ni prima. Default: false."
                    ),
                },
                "incluye_aux_transporte": {
                    "type": "boolean",
                    "description": (
                        "True si el trabajador recibe auxilio de transporte "
                        "(salario ≤ 2 SMMLV = $2.847.000). "
                        "Si no se indica, se detecta automáticamente."
                    ),
                },
                "dias_restantes_contrato": {
                    "type": "integer",
                    "description": (
                        "Solo para contratos a término fijo: días que faltaban para "
                        "terminar el contrato. Necesario para calcular la indemnización exacta."
                    ),
                },
            },
            "required": ["salario_mensual", "fecha_inicio", "motivo_retiro"],
        },
    },

    # ── 3. check_deadlines ────────────────────────────────────────────────────
    {
        "name": "check_deadlines",
        "description": (
            "Verifica los plazos de prescripción y caducidad para reclamaciones "
            "laborales. Calcula si los plazos están vigentes, inminentes o vencidos. "
            "Úsala cuando el usuario pregunte si aún puede reclamar, si ya prescribió "
            "su derecho, o cuánto tiempo tiene para demandar. "
            "Incluye: prescripción laboral general (Art. 488 CST — 3 años), "
            "tutela (6 meses), acoso laboral (Ley 1010/2006), fuero sindical (2 meses), "
            "accidente de trabajo y caducidad contencioso-administrativa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_evento": {
                    "type": "string",
                    "description": (
                        "Fecha del evento laboral en formato YYYY-MM-DD: "
                        "despido, fin de contrato, accidente, acoso, etc."
                    ),
                },
                "tipo_evento": {
                    "type": "string",
                    "enum": [
                        "despido",
                        "fin_contrato",
                        "accidente_trabajo",
                        "acoso_laboral",
                        "fuero_sindical",
                        "pension",
                        "otro",
                    ],
                    "description": "Tipo de evento laboral. Default: despido.",
                },
                "conceptos_a_reclamar": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Conceptos específicos a verificar: "
                        "cesantias, intereses_cesantias, prima, vacaciones, "
                        "salarios, indemnizacion, pension, tutela, "
                        "acoso, fuero_sindical, accidente, contencioso. "
                        "Si se omite, calcula todos los relevantes."
                    ),
                },
                "fecha_consulta": {
                    "type": "string",
                    "description": (
                        "Fecha de referencia para calcular días restantes (YYYY-MM-DD). "
                        "Default: fecha de hoy."
                    ),
                },
            },
            "required": ["fecha_evento"],
        },
    },
]
