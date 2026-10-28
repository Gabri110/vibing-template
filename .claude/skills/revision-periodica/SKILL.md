---
name: revision-periodica
description: Revisión periódica de cómo se trabaja con la IA en el proyecto, mirando atrás desde la última. Busca qué se ha repetido tres veces (candidatas a skill, script o hook) y qué regla del contrato no cumple nadie (se quita o se automatiza). Revisa también cómo han crecido los permisos, los worktrees y ramas huérfanos, la longitud del contrato y el uso real de las skills. Úsala cuando la lance la tarea programada, o cuando el usuario pida la revisión semanal o periódica, qué se está repitiendo o qué reglas no sigue nadie.
argument-hint: [desde qué fecha, si no es desde la última revisión]
---

# Revisión periódica

Una regla que nadie cumple es peor que no tenerla, porque da por cubierto algo que no lo está. Una
skill nace de algo que ya se ha repetido, no de una idea. Esta revisión mira atrás para las dos
cosas y no cambia nada por su cuenta: propone con su evidencia, y la persona decide.

## 1. Desde cuándo

Desde la entrada más reciente "Revisión periódica" de `docs/meeting-log.md`. Si no hay ninguna,
los últimos 14 días. Si la lanza una tarea programada que se retrasó (el ordenador estaba
apagado), el periodo sigue siendo el mismo, porque la fecha de partida sale del registro.

## 2. Qué se mira

1. **Lo repetido.** `git log --since=<fecha> --format='%ad %s' --date=short`, las actas desde esa
   fecha y `docs/backlog.md`. Un procedimiento pedido tres veces, con pasos que se olvidan, es
   candidato. El criterio y lo ya descartado están en `.claude/skills/README.md`: no se vuelve a
   proponer un descarte sin un motivo nuevo.
2. **Las reglas.** Cada línea de `AGENTS.md` y `CLAUDE.md`: qué la sostiene (hook, permiso o
   solo la instrucción) y si hay evidencia de que se incumple (commits directos, ramas de más de
   dos días, cierres sin verificación). La que nadie sigue se propone quitar o automatizar.
3. **Los permisos.** `.claude/settings.json` frente al `settings.local.json` de quien revisa: lo
   que se repite en el local y merece ir al compartido (por commit revisado) y lo que sobra.
4. **Worktrees y ramas.** `git worktree list` y las ramas locales con su última fecha. Las ya
   integradas se proponen para borrar, con el comando.
5. **El contrato.** Líneas de `AGENTS.md` más `CLAUDE.md`, con el límite de 200.
6. **El uso de las skills.** Si existe `~/.claude.json`, su contador `skillUsage` dice cuántas
   veces se invocó cada una en esta máquina. La que no se usa se revisa o se retira.
7. **Observaciones.** Si está instalada la skill `task-observer`, su registro de correcciones y
   pasos repetidos.

## 3. Salida

Una entrada nueva arriba en `docs/meeting-log.md`, "AAAA-MM-DD, Revisión periódica": lo
encontrado, cada propuesta con su evidencia y lo que se decida si la persona está delante. Sin
commits ni cambios de configuración: eso, si se aprueba, es una tarea aparte.
