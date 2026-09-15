# T8 IT Service Desk

Espacio de trabajo del producto **T8 IT Service Desk** — plataforma de mesa de
servicio agéntica, nativa en ITIL 4 y KCS v6.

Estado actual: **diseño aprobado por revisar, sin código.** El scaffolding de la
Fase 0 comienza únicamente tras la aprobación de `PLAN.md` (PROMPT.md §0.5).

- [`PROMPT.md`](PROMPT.md) — especificación de construcción (documento fuente).
- [`docs/00-architect-response.md`](docs/00-architect-response.md) — respuesta a
  la Sección 14: supuestos, preguntas bloqueantes, postura arquitectónica
  (incluidos los desacuerdos con el documento), plan por fases, lista de ADRs y
  el supuesto más riesgoso con su prueba de la semana uno.
- [`PLAN.md`](PLAN.md) — plan de fases, fronteras de módulos, decisiones
  arquitectónicas con sus trade-offs y la capa de medición.
- [`docs/adr/`](docs/adr/README.md) — ADRs 0001–0019.

## Decisiones tomadas por el product owner

| Pregunta | Respuesta |
|---|---|
| Sistema de registro | Ambos modos (propio y proyección del incumbente), prioridad equivalente desde el día uno |
| Despliegue | SaaS |
| LLM | Anthropic primero, más API pagada por el cliente, MCP del cliente y cualquier opción que aproveche su inversión previa |
| Modelo comercial | Sin definir — medir todo |

## Pendientes

- §13 Q3: export de tickets del design partner y tenant M365 de no producción.
- Confirmación de tres supuestos (`PLAN.md` §2): intake por correo en la Fase 3,
  promoción de autonomía en modo sombra, y diferir el Admin Studio.
