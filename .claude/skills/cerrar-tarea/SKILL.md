---
name: cerrar-tarea
description: Cierra la tarea de un worktree o rama corta en orden y con sus comprobaciones: verificación completa en verde, documentos vivos al día, salida del worktree, squash desde el checkout principal, commit según la política del proyecto y limpieza del worktree y la rama. Solo la lanza la persona, con /cerrar-tarea, porque integra en una rama compartida.
argument-hint: [rama o worktree que se cierra]
disable-model-invocation: true
---

# Cerrar una tarea

Rama que se cierra: **$ARGUMENTS** (si no viene, la del worktree actual).

Cuatro pasos que todo el mundo se salta alguna vez. En orden; si una comprobación falla, para y
dilo con su salida.

## 1. Dentro del worktree

1. `git status`: nada sin commitear. Lo que quede se commitea en la rama o se descarta con la
   persona.
2. `python3 scripts/check.py` en verde, la completa: sin eso no se integra.
3. Si existe `docs/manifest.toml`: `python3 scripts/docs_impact.py --impact --base <integración>`.
   Cada REVISAR se pone al día en la rama, se pasa por `/sincronizar-docs` o se toca su línea
   «Revisado:». La puerta del merge lo exige.
4. Qué rama es: corta (squash) o de varios días con commits que valen por sí solos (`--no-ff`).
   Si no está claro, se pregunta.

## 2. Salir del worktree

`ExitWorktree` con `action: "keep"`, porque el trabajo ya está commiteado en su rama. Desde dentro
no se puede integrar: la rama de integración está desplegada en el checkout principal y git no la
deja en dos sitios.

## 3. Integrar, desde el checkout principal

1. En la rama de integración, y con `git pull --ff-only` si hay remoto.
2. Nadie más integrando: no existe `.git/index.lock` y `git status` sale limpio. Ficheros
   preparados que no son de esta rama quieren decir que otra sesión está a medias, y se para hasta
   aclararlo.
3. `git merge --squash <rama>` (o `git merge --no-ff <rama>`). La puerta del merge pasa aquí los
   documentos vivos y, en el repo del cliente, el escáner de fugas.
4. `git diff --cached --stat` tiene que coincidir con `git diff <integración>...<rama> --stat`.
5. El commit, según `[branches] human_commit` de `.claude/project.toml`:
   - `false`: un commit con mensaje convencional de una línea que resuma el cambio lógico.
   - `true`: no se commitea. Se enseña el resumen del diff, se pide la revisión de forma
     explícita y se propone el mensaje en una línea; el commit lo hace la persona.
6. Push solo si la persona lo pide. Hacia una rama protegida el hook pide el sello de una
   verificación completa del árbol exacto que se empuja: `python3 scripts/check.py` aquí, después
   del commit.

## 4. Limpiar

`git worktree remove .claude/worktrees/<nombre>` y `git branch -D <rama>` (con `-D` porque, tras
un squash, git no sabe que la rama está integrada). Si el worktree está bloqueado, antes
`git worktree unlock`. Comprueba que la carpeta ha desaparecido del disco y no solo de
`git worktree list`: lo que no está en git (dependencias, enlaces) git no lo limpia.

## 5. Dejarlo escrito

Lo que se decidió, a `docs/meeting-log.md` o al documento que corresponda; lo pendiente de otra
zona, a `docs/backlog.md`. Y al terminar se dice qué se integró y con qué commit, qué se borró y
si hubo push.
