---
name: configurar-proyecto
description: Guía la primera conversación de un proyecto hecho con este esqueleto, o adoptado en un repo que ya existe, y lo deja configurado. Pregunta por objetivos y entregables, equipo, idiomas, lenguajes y comandos, ramas y quién commitea, y coautoría de Claude en git. Sigue con zonas calientes, verificación, documentación, frontera con el cliente, releases, tareas programadas y skills recomendadas. Explica cada pieza (hooks, worktrees, skills, permisos) cuando toca y responde a las preguntas por el camino. Úsala cuando el arranque diga que el proyecto está sin configurar, cuando el usuario pida configurar o arrancar el proyecto, o para cambiar una sola de esas decisiones más adelante.
argument-hint: [vacío la primera vez, o la decisión que se quiere cambiar]
---

# Configurar el proyecto

Encargo: **$ARGUMENTS**. Vacío: la configuración completa. Con algo concreto ("la coautoría",
"añadir TypeScript"): solo eso, como en la última sección.

De esta conversación sale el contrato del proyecto. Tu papel es guiar, explicar lo justo y
escribir lo decidido. La persona decide; tú propones con una recomendación y dices por qué.

## 1. Mirar antes de preguntar

Sin tocar nada:

- `.claude/project.toml` (`configured`), `AGENTS.md` y `CLAUDE.md` con sus marcas `RELLENAR`.
- El stack: `pyproject.toml`, `requirements*.txt`, `package.json`, `go.mod`, `Cargo.toml`,
  `pom.xml`, `*.csproj`, `Makefile`, `.github/workflows/`.
- Git: `git branch -a`, `git remote -v` (GitHub, Bitbucket u otro: decide qué tareas programadas
  sirven) y `git log --oneline -10`.
- En un repo adoptado, su `README`, un `CLAUDE.md` o `AGENTS.md` anterior y sus convenciones.

Resume en cinco líneas lo que has visto y los valores por defecto que vas a proponer.

## 2. La conversación

Recorre las decisiones de `references/decisiones.md` en su orden: una cada vez, o dos juntas si
son cortas y del mismo tema. En cada una:

1. Qué se decide y qué pieza toca, en dos líneas y sin jerga.
2. Tu recomendación, apoyada en lo que viste en el paso 1.
3. La pregunta, con opciones cuando las hay (la recomendada primero), o abierta si es sobre
   objetivos y entregables.

Si la persona pregunta por algo (qué es un hook, para qué un worktree), contesta corto, con un
ejemplo de su proyecto, y vuelve al hilo. Si dice "lo que recomiendes", se apunta como decisión
tuya y se sigue. Lleva la cuenta de lo decidido.

## 3. Antes de escribir

Enseña el resumen en una tabla (decisión, valor, fichero que cambia) y espera un sí explícito.

## 4. Escribir

Con el sí, según la columna «Dónde» del catálogo. Claude Code protege `.claude/`: escribir ahí pide
permiso aunque las ediciones estén aceptadas (en modo automático lo decide el clasificador), y es lo
esperado, porque así la persona ve y aprueba cada cambio de configuración.

- `AGENTS.md` y `CLAUDE.md`: cada marca `RELLENAR` se sustituye por texto, sin dejar la marca.
  Reglas que se puedan comprobar, frases cortas, menos de 200 líneas entre los dos.
- `.claude/project.toml`, `scripts/check.toml`, `scripts/release.toml`, `.claude/settings.json`
  (permisos y `attribution`), `docs/manifest.toml`, `scripts/boundary/leak_rules.toml`,
  `.gitignore` y `.worktreeinclude`, según lo decidido.
- Una regla por ruta para cada zona caliente en `.claude/rules/<zona>.md`; se borra
  `ejemplo-ruta.md`.
- Los módulos que no se usan se retiran borrando sus ficheros (lista en el catálogo), sin dejarlos
  a medias. Los tests del esqueleto que prueban un módulo retirado se saltan solos.
- `README.md` es la guía del esqueleto: pasa a `docs/esqueleto.md` (su entrada en
  `docs/manifest.toml` también) y se escribe un `README.md` corto del proyecto.
- Primera entrada de `docs/meeting-log.md`: "AAAA-MM-DD, configuración del proyecto con la IA",
  con cada decisión y su porqué.
- Al final, `configured = true` en `.claude/project.toml`.

## 5. Comprobar

- `python3 scripts/check.py` en verde: confirma que no quedan marcas, que la configuración se lee
  y que el contrato cabe.
- `python3 scripts/bootstrap.py doctor`.
- Con frontera: `python3 scripts/boundary/setup_code_repo.py <repo del cliente>` y su `--check`.
  Pide permiso antes, porque escribe en ese repo.
- Con revisión programada: créala si la herramienta de tareas programadas está disponible y la
  persona lo aprueba (prompt `/revision-periodica`, carpeta del proyecto, semanal), o explica cómo
  crearla.

La salida dice qué ficheros cambiaron y copia lo que devolvieron las dos comprobaciones.

## 6. La demostración, si la persona quiere

Dos minutos para ver las piezas funcionando, sin dejar cambios: abrir un worktree (`EnterWorktree`),
ver el aviso de la rama `worktree-…` y renombrarla; intentar `git commit` en la rama de
integración y leer la denegación del hook con su motivo; salir con `ExitWorktree` y `remove`.

## Cambiar una sola decisión más adelante

Se lee la configuración actual, se explica el cambio y lo que toca, se pide el sí, se cambia solo
eso, se apunta la decisión con su porqué en `docs/meeting-log.md` y se corre `check.py`.
