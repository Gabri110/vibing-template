---
paths:
  - "src/core/**"
---

# Zona caliente: `src/core/` (ejemplo)

Esto es una regla por ruta. Solo entra en el contexto cuando la sesión lee o edita un fichero que
casa con `paths`, así que puede llevar el detalle que no cabe en el contrato sin gastar contexto
en las demás tareas.

- **Una línea en el contrato, el detalle aquí.** En `AGENTS.md` va la regla verificable ("los
  importes, siempre en céntimos enteros"); aquí, el porqué, desde cuándo y el bug que la motivó.
- **Plan mode antes de tocar nada.** El plan se lee antes de aprobarlo: es el momento barato de
  corregir.
- **El arreglo de un número empieza por un test que falla,** y el criterio (qué número tiene que
  salir) lo pone la persona.

`/configurar-proyecto` sustituye este ejemplo por las zonas calientes del proyecto, o lo borra.
