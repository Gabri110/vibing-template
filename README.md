# Esqueleto de proyecto con IA

Un punto de partida para trabajar con Claude Code en un proyecto real, con las prácticas ya puestas
y que se sostienen solas: lo que tiene que cumplirse siempre lo vigila un hook o un permiso, no la
memoria de nadie. Sale de dos meses de trabajo de un equipo de dos personas en un proyecto con
cliente. Qué se hizo allí, por qué y qué incidente motivó cada pieza está en
[`docs/practicas.md`](docs/practicas.md); este fichero explica qué hay aquí y cómo se usa.

Requisitos: Claude Code 2.1.277 o superior, git 2.31 o superior, bash (en Windows, Git Bash) y
Python 3.11 o superior. Las herramientas solo usan la biblioteca estándar.

## Empezar

1. **Proyecto nuevo:** se copia esta carpeta sin su `.git` y se hace `git init -b main`.
   **Repo que ya existe:** `python3 scripts/bootstrap.py adopt ../mi-repo` copia lo que falta y
   lista lo que hay que fusionar a mano, sin pisar nada.
2. Se abre Claude Code en la carpeta y se acepta confiar en ella: los hooks del proyecto solo
   corren en carpetas de confianza.
3. El arranque avisa de que el proyecto está sin configurar. Se escribe `/configurar-proyecto`:
   una conversación de 20 a 30 minutos en la que Claude pregunta por objetivos y entregables,
   equipo, idiomas, lenguajes, ramas, quién commitea, coautoría en git, zonas calientes,
   verificación y módulos. Explica cada pieza cuando toca, responde a las dudas, enseña el resumen
   de decisiones, escribe el contrato y la configuración con el sí y apunta cada decisión con su
   porqué en `docs/meeting-log.md`.
4. `python3 scripts/bootstrap.py doctor` comprueba la máquina (qué Python eligen los hooks, bash,
   git, versión de Claude Code, que cada hook responde) y `python3 scripts/check.py` el proyecto.
5. El primer commit lo hace la persona.

En Windows, `py -3` en lugar de `python3`.

## Qué hay

| Pieza | Qué es | Cuándo actúa | Qué tocas tú |
|---|---|---|---|
| `AGENTS.md` y `CLAUDE.md` | El contrato: reglas que cumplen todas las sesiones. `CLAUDE.md` importa `AGENTS.md`, que también leen otras herramientas | Se carga entero al empezar cada sesión | Lo rellena `/configurar-proyecto`. Menos de 200 líneas; cuando una regla cambia, se sustituye |
| `.claude/settings.json` | Permisos (`allow`, `ask`, `deny`), los cuatro hooks y `worktree.baseRef: head` | Siempre: es determinista | Crece solo por commit revisado |
| `.claude/settings.local.json` | Lo personal: modo de arranque, permisos propios, variables | Siempre, por encima del anterior | Lo que quieras; git lo ignora |
| `.claude/project.toml` | Política de ramas, disparadores de skills, skill de estilo, frontera con el cliente | Lo leen los hooks | La conversación guiada, o a mano |
| `.claude/hooks/` | `run.sh` y cuatro hooks | En momentos fijos del ciclo | Nada: es del esqueleto |
| `.claude/rules/` | Reglas por ruta, con cabecera `paths:` | Solo al tocar los ficheros que casan | Una por zona caliente |
| `.claude/skills/` | Cinco skills y su catálogo con el criterio de admisión | Con `/nombre`, o las elige el modelo | Se añaden con el criterio de su README |
| `scripts/check.py` y `check.toml` | La verificación única, con dos velocidades y sello | A mano, y la rápida antes de cada push | Los pasos de tu stack |
| `docs/meeting-log.md`, `docs/backlog.md` | La memoria compartida: decisiones y pendientes | Al cerrar cada tarea | Cada sesión |
| `docs/practicas.md` | El porqué de todo, con los incidentes que lo motivaron | Se lee | Nada |
| `scripts/docs_impact.py`, `scripts/release.py`, `scripts/boundary/` | Módulos: documentación viva, releases y frontera con el cliente | Inertes hasta que se configuran | Se activan o se borran en la conversación guiada |

## Una tarea, de principio a fin

1. **Una tarea por sesión.** `/clear` (o sesión nueva) entre tareas que no tienen que ver.
2. **Un worktree.** Desde fuera, `claude -w fix-texto-columna`; desde una sesión, se le pide que
   trabaje en un worktree (`EnterWorktree`). La rama nace como `worktree-<nombre>`: se renombra
   con `git branch -m fix/<nombre>`. El arranque avisa si se olvida.
3. **Explorar, planificar, ejecutar, verificar.** Primero que lea y explique sin tocar nada. En las
   zonas calientes, plan mode (Shift+Tab) y el plan leído antes de aprobarlo. El encargo lleva su
   criterio de aceptación: no "mejora el cálculo", sino "la fila X debe dar Y con estos datos;
   añade un test que lo fije, hazlo pasar y corre la verificación". Al final, `check.py` en verde
   y, si el cambio se ve, `/verificar` con lo que se espera ver.
4. **Cerrar.** `/cerrar-tarea`: verificación completa, documentos vivos, salida del worktree,
   squash desde el checkout principal, commit según la política y limpieza del worktree y la rama.
5. **Lo decidido, al repo,** antes de cerrar la sesión: a `docs/meeting-log.md`, al contrato si
   cambia una regla o a `docs/backlog.md` si es de otra zona.

Si a la segunda corrección sigue mal, mejor `/clear` y un encargo reescrito con lo aprendido que
arrastrar un contexto contaminado. Esc corta a media respuesta; `/rewind` deshace ediciones, pero
no lo que hizo un comando de shell.

## Los hooks

Un hook es un comando que Claude Code ejecuta en un momento fijo. Es la única pieza determinista:
pasa aunque el modelo no se acuerde. Va a un hook lo que tiene que cumplirse siempre, se puede
comprobar con un comando y cuesta segundos; lo demás es una instrucción del contrato.

| Hook | Evento | Qué hace | Si falla |
|---|---|---|---|
| `session_start.py` | SessionStart | Rama, cambios sin commitear, si estás fuera de un worktree o con la rama sin renombrar, adelanto y retraso frente al remoto (sin `fetch`, con la edad de las referencias), worktrees abiertos, si el proyecto está sin configurar. Una línea para ti y el detalle para el modelo. No toca nada | Calla |
| `pre_bash.py` | PreToolUse (Bash y PowerShell) | Guardián de ramas: en la de integración solo se commitea un squash preparado; en la de entrega, nada a mano; deniega mover ramas protegidas desde fuera. Push: refs permitidas, sello de verificación completa hacia ramas protegidas, tag de release, verificación rápida en el resto. Merge: puerta de documentos vivos y, en el repo del cliente, escáner de fugas | Abierto; en el repo del cliente, cerrado |
| `prompt.py` | UserPromptSubmit | Nombra la skill del proyecto que encaja con el mensaje, si existe | Calla |
| `post_edit.py` | PostToolUse (Write, Edit) | Nombra los documentos vivos que describen el código tocado y, tras editar un documento, la skill de estilo (o avisa de que no está instalada) | Calla |

Detalles que ahorran tiempo:

- **Se prueban a mano con su payload**, igual que los llama Claude Code:
  `echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"},"cwd":"'$PWD'"}' | bash .claude/hooks/run.sh pre_bash.py`.
  Los tests de `.claude/tests/` lo hacen en repos temporales.
- **Corren desde el checkout principal** aunque la sesión esté en un worktree
  (`CLAUDE_PROJECT_DIR` no lo sigue; el `cwd` del payload sí). Un hook cambiado en una rama no
  actúa hasta que llega al checkout principal.
- **No hay hook de cierre de turno (Stop) a propósito:** correr la verificación al final de cada
  respuesta, también de las que no tocan código, es la fricción que hace que alguien lo quite. La
  verificación va antes del push. Si un día hace falta, devuelve `{"decision": "block", "reason":
  ...}` en el nivel superior y respeta `stop_hook_active`.
- **Un hook no puede invocar una skill:** no hay modelo detrás de un script. Lo más que hace es
  meter una línea de contexto en el momento justo, redactada como un hecho y no como una orden.
- **Se quitan** borrando su entrada en `.claude/settings.json`.

## Worktrees

Un worktree es otra carpeta con otra rama del mismo repo, que comparte el `.git`. Uno por tarea,
porque dos sesiones en el mismo checkout se pisan: una cambia de rama y la otra empieza a commitear
donde no debe.

- **De dónde arranca:** `worktree.baseRef: head` hace que salga del `HEAD` del checkout principal
  (la rama de integración). Con el valor por defecto saldría de la rama por defecto del remoto,
  que puede ir muy por detrás.
- **Dentro no se puede `git checkout main`:** la rama de integración está desplegada en el
  checkout principal y git no la deja en dos sitios. Por eso se integra después de `ExitWorktree`,
  desde fuera.
- **Lo que no está en git no viaja:** `.worktreeinclude` copia los ficheros ignorados que cada
  worktree necesita (`.env`); dependencias grandes, se reinstalan o se enlazan.
- **Los enlaces que devuelve Claude desde un worktree** llevan su prefijo
  (`.claude/worktrees/<nombre>/...`), porque la app los resuelve contra el checkout principal.
- **No se limpian solos:** `/cerrar-tarea` los borra con su rama; la revisión periódica busca los
  huérfanos.
- **Una rama que dura más de un día trae la de integración cada mañana:** el contrato y las
  skills se leen del worktree, y una rama vieja corre con los de cuando nació.

## Skills

Procedimientos que se repiten, con nombre. El catálogo, el criterio de admisión (tres repeticiones
con evidencia, pasos que se olvidan y que mantenerla cueste menos que repetirla) y lo descartado
están en [`.claude/skills/README.md`](.claude/skills/README.md).

| Skill | Para qué |
|---|---|
| `/configurar-proyecto` | La primera conversación; también, cambiar una decisión más adelante |
| `/verificar` | Comprobar un cambio en contexto propio: afirmaciones con su prueba, sin arreglar nada |
| `/cerrar-tarea` | Cerrar una rama en orden; solo la lanza la persona |
| `/revision-periodica` | Lo repetido tres veces, reglas que nadie cumple, permisos, worktrees huérfanos |
| `/sincronizar-docs` | Contrastar un documento vivo con el código y corregir el documento |

Dos patrones que conviene copiar: `context: fork` para que juzgue quien no hizo el trabajo, y
`disable-model-invocation: true` para lo que solo debe lanzar una persona.

## Tareas programadas

| | Escritorio | En la nube (`/schedule`) | `/loop` |
|---|---|---|---|
| Dónde corre | En tu máquina, con la app abierta | En servidores de Anthropic | En la sesión abierta |
| Ve tus ficheros | Sí (opción de worktree propio por ejecución) | No: clona el repo de GitHub | Sí |
| Si el ordenador duerme | Se salta, y al despertar hace una de recuperación | Corre igual | Se para con la sesión |

**El procedimiento vive en el repo como skill, y la tarea solo la invoca,** porque la tarea es de
tu máquina o de tu cuenta y la skill viaja con el repo. La que recomienda el esqueleto es la
revisión semanal (prompt `/revision-periodica`). En el proyecto de origen estaba prevista, nadie la
programó y no corrió nunca. Un prompt programado tiene que valer solo y aguantar un retraso ("si
ya es tarde, resume lo pendiente"). Con el repo fuera de GitHub, la nube no sirve; con repo del
cliente, antes de mandarlo a la nube se mira el contrato. Un proceso largo lanzado en segundo
plano muere con la sesión: para eso, una tarea programada o el programador del sistema, y dentro
de una sesión, `Monitor` para vigilarlo.

## Permisos

- `allow` corre sin preguntar, `ask` pregunta siempre, `deny` no corre nunca, en cualquier modo.
- **El límite está en el push, no en el commit:** un commit es local y se deshace con
  `git revert`; lo que sale de la máquina lo ve el resto y deshacerlo cuesta.
- **Nunca `bypassPermissions`:** quita la única barrera entre un error del modelo y un borrado o un
  push. Para menos preguntas, se amplía `allow` con criterio.
- `settings.local.json` crece solo cuando aceptas algo "para siempre"; el compartido, solo por
  commit revisado, para que diga lo que alguien decidió y no lo que alguien aceptó con prisa.
- **Secretos:** nunca en `settings.json` ni en su `env`. Un `deny` de `Read(./.env)` aparta las
  herramientas de fichero, pero no un `cat`: lo secreto vive fuera del árbol.

## Memoria y documentación

El repo es la única fuente compartida. La memoria automática de Claude es de cada máquina y no
viaja: guarda punteros ("esto se decidió así, está en tal fichero"), nunca el contenido. Lo
decidido va a `docs/meeting-log.md`; lo pendiente de otra zona, a `docs/backlog.md`; un cambio de
más de una sesión, a un plan en `docs/planes/`. Una sesión se cierra escribiendo eso: archivarla
sin hacerlo deja lo aprendido en una conversación que nadie va a releer.

## Módulos

**Documentación viva.** `docs/manifest.toml` clasifica cada documento de `docs/` como `record`
(fechado, no caduca) o `living` (tiene que ser verdad hoy), y cada vivo lista el código que
describe. `post_edit.py` lo recuerda al tocar ese código; `docs_impact.py --impact` enseña qué
queda por revisar; la puerta del merge deniega mientras un documento siga en REVISAR. Se resuelve
poniéndolo al día, con `/sincronizar-docs` o tocando su línea «Revisado:».

**Releases.** `python3 scripts/release.py --init` y después `--dry-run` para ver la versión y el
changelog. La release sale de la rama de integración con el árbol limpio: verificación, versión
por commits convencionales, changelog, tag anotado, avance rápido de la rama de entrega si la hay,
y el push impreso para que lo lance una persona. `release.py manifest <carpeta>` deja un
`manifest.json` en el paquete para que la app enseñe su versión y su fecha. El hook no deja llegar
a la rama de entrega un commit sin su tag.

**Frontera con el cliente.** Para cuando el código se comparte con un cliente que no debe ver lo
interno. Este repo pasa a ser el interno y el código vive en un repo hermano, que se cablea con
`python3 scripts/boundary/setup_code_repo.py ../codigo-cliente`:

| Qué escribe en el repo del cliente | Por qué git no lo ve | Para qué |
|---|---|---|
| `git config skeleton.role client` | Es configuración local | Los hooks aplican `[boundary]` y fallan cerrados |
| Un bloque en `.git/info/exclude` | Es local | `.claude/`, `CLAUDE.local.md` y `.remember/` fuera de git |
| `.claude/settings.local.json` | Excluido | Hooks de este repo por ruta absoluta, permisos, coautoría |
| `.claude/skills/<nombre>` | Excluido | Un enlace por skill |
| `.claude/rules/*.md` y `CLAUDE.local.md` | Excluidos | Copias del contrato y las reglas: lo enlazado o importado desde fuera del proyecto no se carga sin una aprobación que puede no aparecer nunca |
| `pre-commit`, `commit-msg`, `pre-push` en sus hooks de git | Viven en `.git` | La garantía que no depende de cómo se abra la sesión: corren con cualquier commit o push, sea de Claude o de una persona |

`--check` dice qué falta o está desfasado (también lo avisa el arranque) y `--remove` lo deshace.
Las reglas de lo que no puede salir están en `scripts/boundary/leak_rules.toml`.

## Skills y plugins recomendados

- **Estilo de escritura.** En inglés, `humanizer` (plugin `blader/humanizer`) o la `humanizer` de
  anthropic-skills, que quitan los patrones típicos de texto generado. En español sirven poco,
  porque su catálogo es inglés: lo que funciona es una skill propia hecha desde la guía de estilo
  del equipo, con lo que se mide en los propios textos ("no es X, es Y", frases sueltas, negrita
  de adorno, rayas). La elegida va a `[style] skill` de `.claude/project.toml`.
- **Proceso y memoria:** `superpowers` para el proceso (brainstorming, planes escritos, TDD,
  depuración sistemática y revisión de código), `remember` para la memoria entre sesiones,
  `skill-creator` para escribir skills y `task-observer` para detectar las que faltan.
- **Ya vienen con Claude Code:** `/code-review` (revisión del diff en una sesión que no lo
  escribió: para zonas calientes, diffs grandes y sesiones largas), `/simplify`,
  `/security-review`, `/compact` con instrucciones de qué conservar, `/btw` para preguntas al
  margen.
- **Lo que hay que instalar en cada máquina falla en silencio en la que no lo tiene,** así que lo
  que un hook necesita vive en el repo y los plugins quedan para comodidad. Para todo el equipo,
  `enabledPlugins` y `extraKnownMarketplaces` en `.claude/settings.json`.

## Qué es del esqueleto y qué es tuyo

`scripts/bootstrap.py` lo lista. Del esqueleto, y no se editan por proyecto: `.claude/hooks/`,
`.claude/tests/`, las cinco skills, `scripts/check.py`, `docs_impact.py`, `release.py`,
`bootstrap.py` y los tres programas de `scripts/boundary/`. Tuyos: el contrato, `settings.json`,
`project.toml`, los `.toml` de `scripts/`, las reglas y los documentos. Para actualizar, se
sustituyen los del esqueleto por los de una versión nueva y se apunta la versión en
`[skeleton] version`; lo tuyo no se toca.

## La segunda persona

Clona, abre Claude Code y confía en la carpeta, pasa `bootstrap.py doctor`, lee el contrato y
`docs/practicas.md`, y empieza su primera tarea en un worktree. Su `settings.local.json` es suyo;
lo que cambie el comportamiento de los dos va por commit y se avisa.

## Problemas frecuentes

- **Los hooks no hacen nada:** `bootstrap.py doctor`. Lo habitual es que no encuentren Python 3.11
  (se fija `SKELETON_PYTHON`) o que la carpeta no sea de confianza.
- **"fatal: 'main' is already used by worktree":** es lo esperado dentro de un worktree; se
  integra desde el checkout principal.
- **Push denegado por el sello:** la verificación completa tiene que haber visto el árbol exacto
  que se empuja; se corre `check.py` después del último commit.
- **Merge denegado por un documento:** se pone al día, se pasa `/sincronizar-docs` o se toca su
  línea «Revisado:».
- **Una skill no aparece o la elige mal:** su carpeta y su `name` tienen que coincidir; una skill
  personal (`~/.claude/skills/`) con el mismo nombre gana a la del proyecto.
- **El contrato no se carga en el repo del cliente:** `setup_code_repo.py --check`.
- **Claude pide permiso para cada cambio dentro de `.claude/`:** es una ruta protegida de Claude
  Code y ninguna regla `allow` lo evita (en modo automático decide el clasificador). Así se ve cada
  cambio de configuración antes de que entre.

## Documentación oficial

[Buenas prácticas](https://code.claude.com/docs/en/best-practices) ·
[Memoria y CLAUDE.md](https://code.claude.com/docs/en/memory) ·
[Hooks](https://code.claude.com/docs/en/hooks) ·
[Skills](https://code.claude.com/docs/en/skills) ·
[Permisos](https://code.claude.com/docs/en/permissions) ·
[Worktrees](https://code.claude.com/docs/en/worktrees) ·
[Tareas programadas](https://code.claude.com/docs/en/desktop-scheduled-tasks)

Revisado: 2026-10-28, versión inicial.
