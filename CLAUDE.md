@AGENTS.md

## Claude Code en este proyecto

- **Worktree por tarea.** Al empezar una tarea que cambie ficheros, `EnterWorktree`; ya dentro,
  `git log -1` para ver de dónde se parte y `git branch -m <prefijo>/<nombre>`. Se integra
  después de `ExitWorktree` con `keep`, desde el checkout principal, porque la rama de
  integración está desplegada allí y git no la deja en dos sitios. Una tarea de una frase (un
  texto, un renombrado) no necesita worktree.
- **Decir dónde se trabaja.** Antes de la primera edición: checkout y rama de partida, worktree y
  rama. Al cerrar: qué se integró y con qué commit, qué se borró y si hubo push.
- **Los enlaces desde un worktree llevan su prefijo** (`.claude/worktrees/<nombre>/docs/x.md`):
  la app los resuelve contra el checkout principal.
- **Hooks** (`.claude/hooks/`): informan al arrancar, frenan commits y merges indebidos en ramas
  protegidas, piden la verificación antes del push y nombran los documentos que describen el
  código tocado. Una denegación trae su motivo y la salida que hay que tomar, y buscar otro
  comando que la esquive cuenta como saltársela.
- **Skills** (`.claude/skills/`, catálogo en su README): `configurar-proyecto`, `verificar`,
  `cerrar-tarea` (solo la lanza la persona), `revision-periodica` y `sincronizar-docs`. Van por
  delante de las genéricas que hagan lo mismo.
- **Subagente o sesión aparte.** Si el resultado vuelve a esta conversación (buscar, leer,
  revisar), subagente; si vuelve al repo por su propia rama, sesión aparte con su worktree.
- **Revisión con contexto limpio** (`/code-review` o un subagente que no escribió el cambio) para
  zonas calientes, diffs grandes y sesiones largas: quien escribió el código ya no lo juzga bien.
- **Memoria automática:** es de esta máquina y no se comparte. Guarda punteros a ficheros del
  repo, nunca el contenido.
- **Al compactar,** se conservan la lista de ficheros modificados, las decisiones tomadas y lo que
  falta por verificar.

<!-- RELLENAR: lo específico de Claude Code en este proyecto (servidores de .claude/launch.json
para verificar en la app, skills propias). Si no hay nada, se borra esta marca. -->
