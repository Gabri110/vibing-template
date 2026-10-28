# Skills del proyecto

Procedimientos que se repiten, escritos una vez y con nombre. Se invocan con `/nombre`, o el modelo
los elige por su descripción; el hook `prompt.py` le señala la que encaja con cada mensaje, porque
elegir solo por la descripción falla más de lo que parece (medido en el proyecto del que sale
este esqueleto: cuatro de seis skills no se eligieron solas ni una vez en una semana).

## Criterio de admisión

Una skill se justifica solo si se cumplen las tres condiciones:

1. El procedimiento se ha repetido **tres veces**, y hay evidencia de ello (commits, actas).
2. Tiene **pasos que se olvidan** o se hacen distinto cada vez.
3. **Mantenerla cuesta menos que repetirla.** Envolver un comando de una línea no aporta nada: el
   comando ya es el procedimiento.

Y no se escribe lo que ya cubre una regla por ruta (`.claude/rules/`), que se carga sola al tocar
sus ficheros.

## Las que trae el esqueleto

| Skill | Qué resuelve | Cómo se invoca |
|---|---|---|
| `configurar-proyecto` | La primera conversación del proyecto: deja escritos el contrato y la configuración | sola cuando el arranque avisa de que falta, o `/configurar-proyecto` |
| `verificar` | Verificador en contexto propio: afirmaciones con su prueba, sin arreglar nada | `/verificar <qué cambió y qué se espera>`, o la elige el modelo |
| `cerrar-tarea` | Cerrar una rama en orden: verificación, documentos, squash y limpieza | solo la persona, `/cerrar-tarea` |
| `revision-periodica` | Lo repetido, las reglas que nadie cumple, permisos y worktrees huérfanos | la tarea programada, o `/revision-periodica` |
| `sincronizar-docs` | Contrastar un documento vivo con el código y corregir el documento | `/sincronizar-docs <documento>`, o tras la puerta del merge |

Vienen de un proyecto donde pasaron este criterio. En uno nuevo, la que no se use se borra.

## Candidatas, sin skill todavía

| Candidata | Qué haría | Qué la convierte en skill |
|---|---|---|
| `acta-reunion` | Una reunión (transcripción o notas) a `docs/meeting-log.md` con su formato, y lo que salga al backlog y al contrato | tres actas escritas a mano con el mismo formato y los mismos olvidos |
| Release del entregable | Lo que va antes y después de `scripts/release.py`: qué se mira, qué se le dice al cliente | tres entregas con un paso olvidado |

## Descartadas

| Candidata | Motivo |
|---|---|
| Revisión de código | `/code-review` ya lo hace, en una sesión que no escribió el cambio |
| Subagentes propios en `.claude/agents/` | Pedir "usa un subagente para revisar X" da el mismo aislamiento sin mantener un fichero; compensa solo con un papel fijo que se invoca muchas veces |
| Envolver la verificación | `python3 scripts/check.py` ya es el procedimiento |

## Cómo se añade una

Una carpeta `.claude/skills/<nombre>/SKILL.md` con cabecera:

- `name`: igual que la carpeta, en kebab-case y sin tildes.
- `description`: qué hace y cuándo usarla, con las frases que teclea la gente y por delante de qué
  skill genérica va. Es lo que lee el modelo para elegirla, y se corta a 1.536 caracteres.
- `context: fork` (con `agent`) si tiene que juzgar sin el sesgo de quien hizo el trabajo.
- `disable-model-invocation: true` si tiene efectos que solo debe lanzar una persona.

Se apunta en la tabla de arriba con su evidencia, se le da un disparador en `[[skills.trigger]]`
de `.claude/project.toml` y se estrena avisando al resto, porque cambia también sus sesiones. Para
escribirla, la skill `skill-creator` de Anthropic ayuda.
