# Catálogo de decisiones

Las decisiones de la primera conversación, en orden. Cada una dice qué se pregunta, las opciones
(la recomendada primero), por qué importa y dónde queda escrita.

## 1. El proyecto

- **Pregunta:** objetivo en dos frases, para quién, fase y fechas clave (entregas, cortes de
  alcance).
- **Entregables:** código en un repo, una app que se instala, informes o documentos, modelos o
  datos, entregables al cliente. Decide si hacen falta releases (10) y qué tiene que mirar
  `/verificar` (7).
- **Dónde:** `AGENTS.md`, "Proyecto".

## 2. Equipo y zonas

- **Pregunta:** quién lleva cada parte del repo.
- **Por qué:** dos sesiones en la misma zona a la vez se pisan. Con zonas, lo que aparece en la de
  otra persona va al backlog y se avisa.
- **Dónde:** `AGENTS.md`, "Equipo y zonas".

## 3. Idiomas

- **Opciones:** código, identificadores y comentarios en inglés, con documentos y commits en
  español (recomendada en equipos de habla hispana), o bien todo en inglés, o todo en español.
- **Entregables:** el idioma del cliente si es otro.
- **Ortografía:** completa en todo lo que va en español (tildes y ñ); los nombres de fichero y los
  identificadores, sin acentos.
- **Dónde:** `AGENTS.md`, "Idiomas". El estilo de escritura, en la decisión 12.

## 4. Lenguajes y comandos

- **Pregunta:** lenguajes, gestor de paquetes, instalación, lint, tipos, tests, build y arranque
  de la app.
- **Dónde:** los pasos de `scripts/check.toml` (lint y tipos con `fast = true`; tests y build en
  la completa), los permisos `allow` de esos comandos en `.claude/settings.json`, `.gitignore`,
  `.worktreeinclude` (`.env` y lo que necesite cada worktree), `AGENTS.md` ("Entorno y
  comandos") y `.claude/launch.json` si hay app que verificar en el navegador.
- **Ejemplos de pasos:**
  - Python con uv: `["uv", "run", "ruff", "check", "."]` y `["uv", "run", "ruff", "format",
    "--check", "."]` rápidos; `["uv", "run", "pytest", "-q"]` en la completa.
  - Node: `["npm", "run", "lint"]` rápido (`npm.cmd` en Windows); `["npx", "tsc", "--noEmit"]`,
    `["npm", "test"]` y `["npm", "run", "build"]` en la completa.
- Los tests del esqueleto (`.claude/tests/`) se quedan como un paso más, porque prueban los hooks.

## 5. Git

- **Rama de integración:** `main` (recomendada si no hay entregas congeladas), o `dev` más una
  rama de entrega si lo entregado se congela y hay que poder decir qué versión tiene el cliente
  (decisión 10).
- **Quién commitea:** Claude cuando se le pide, en ramas de trabajo y en el squash de integración
  (recomendada: un commit es local y se deshace; lo que sale del equipo es el push, y ese siempre
  pregunta); o solo personas en la rama de integración (`human_commit = true`: Claude deja el
  squash preparado y propone el mensaje).
- **Coautoría de Claude en commits y PR:** sí, la línea `Co-Authored-By` que añade por defecto
  (recomendada: es transparente y no cuesta nada); o no, si el cliente o la empresa lo piden
  (`"attribution": {"commit": "", "pr": ""}` en `.claude/settings.json`; con repo del cliente,
  además su hook commit-msg rechaza la línea).
- **Prefijos de rama:** `feature/`, `fix/`, `docs/`.
- **Dónde:** `.claude/project.toml` [branches], `.claude/settings.json`, `scripts/release.toml`
  (`integration`) y `AGENTS.md` (las dos reglas de ramas y la de commits).

## 6. Zonas calientes y restricciones duras

- **Pregunta:** ¿dónde un error no rompe el build pero cambia un número que alguien va a mirar? ¿Qué
  reglas no se pueden romper nunca?
- **Por qué:** en esas zonas hay plan mode obligatorio y el diff se lee entero, y para eso tienen
  que estar escritas.
- **Dónde:** `AGENTS.md` (una línea verificable por regla y la lista de zonas) y una regla por
  ruta por zona en `.claude/rules/<zona>.md`, con `paths:` y el porqué de cada restricción.

## 7. Verificación

- **Pregunta:** qué tiene que pasar para decir que algo está hecho, y contra qué se contrastan las
  cifras (un informe del cliente, una tabla de referencia).
- **Dónde:** `scripts/check.toml`; si hay app, `.claude/launch.json` con sus servidores; el
  criterio de contraste, en `AGENTS.md`.

## 8. Documentación

- **Documentos vivos:** sí, si hay documentación que describe el código (recomendada): cada
  documento va a `docs/manifest.toml` como `living` con su `code`. No: se borran
  `docs/manifest.toml`, `scripts/docs_impact.py`, la skill `sincronizar-docs` y su paso en
  `scripts/check.toml`.
- **Actas y backlog:** `docs/meeting-log.md` y `docs/backlog.md` se quedan siempre: son donde vive
  lo decidido.
- **Dónde:** `docs/manifest.toml` y la tabla "Documentación" de `AGENTS.md`.

## 9. Cliente y frontera

- **Pregunta:** ¿el código se comparte con un cliente que no debe ver material interno (nombres,
  actas, la configuración de la IA)?
- **No** (recomendada si no hay cliente externo): se borran `scripts/boundary/` y la sección
  [boundary] de `.claude/project.toml`.
- **Sí:** este repo pasa a ser el interno y el código del cliente vive en un repo hermano, que
  `setup_code_repo.py` cablea sin versionar nada en él. Se rellenan `leak_rules.toml` (nombres
  del equipo, nombre del repo interno) y [boundary] (rama de integración del cliente, refs que
  pueden salir, coautoría). Hay que avisar de que las tareas en la nube clonan el repo en
  servidores de Anthropic: antes de apuntarlas al repo del cliente, se mira el contrato.

## 10. Releases

- **Pregunta:** ¿se entrega un paquete con versión?
- **Sí:** `python3 scripts/release.py --init`, `scripts/release.toml` (rama de entrega si la hay,
  ficheros que llevan la versión en `also_update`) y que la app enseñe su `manifest.json`
  (`release.py manifest <carpeta del paquete>`).
- **No:** se borran `scripts/release.py` y `scripts/release.toml`.

## 11. Tareas programadas

- **Revisión periódica** (recomendada, semanal): en el proyecto del que sale el esqueleto estaba
  prevista y no corrió nunca, porque nadie la programó. Opciones:
  - tarea de escritorio semanal, con el prompt `/revision-periodica` y la carpeta del proyecto
    (corre en esta máquina, con la app abierta; ve los ficheros locales);
  - `/schedule`, en la nube, si el repo está en GitHub y el contrato con el cliente lo permite;
  - un recordatorio en el calendario, si no se quiere nada automático.
- **Otras recurrentes** (datos que llegan cada semana, un informe): el procedimiento, como skill
  en el repo; la tarea programada solo la invoca.

## 12. Skills y plugins recomendados

- **Estilo de escritura:** en inglés, `humanizer` (plugin `blader/humanizer`) o la `humanizer` de
  anthropic-skills; en español, mejor una skill propia hecha desde la guía de estilo del equipo.
  La elegida va a `[style] skill` de `.claude/project.toml`.
- **Proceso y memoria:** `superpowers` para el proceso (brainstorming, planes, TDD, depuración
  sistemática y revisión), `remember` para la memoria entre sesiones, `skill-creator` para escribir
  skills y `task-observer` para detectar las que faltan.
- **Dónde:** si se quieren para todo el equipo, `enabledPlugins` y `extraKnownMarketplaces` en
  `.claude/settings.json`, y cada persona acepta la instalación al confiar en la carpeta. Si un
  hook depende de una skill, que viva en el repo: lo que hay que instalar en cada máquina falla en
  silencio.
