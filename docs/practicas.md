# Prácticas de trabajo con IA en un proyecto real

Resumen, a 2026-10-28, de cómo ha trabajado con Claude Code un equipo de dos personas durante dos
meses en un proyecto con cliente: un motor de datos con una app de escritorio, entregas periódicas
y un repo de código que se comparte con el cliente. Está escrito para pasarlo a otros equipos, así
que no lleva nombres de personas ni del cliente, ni datos de negocio. Cada práctica va con el
incidente o la medida que la motivó. El proyecto esqueleto que lo acompaña
(`esqueleto-proyecto-ia`) trae cada práctica ya puesta, y la columna «En el esqueleto» dice dónde.

Cómo leerlo: la columna que más importa es «Qué lo sostiene». Una práctica que solo sostiene la
buena voluntad se acaba olvidando, y donde pasó, se dice. Las cifras de uso salen de los
transcripts de una de las dos máquinas, con algunas sesiones contadas dos veces: valen como orden
de magnitud.

## 1. Principios

1. **El repositorio es la única fuente de verdad compartida.** La memoria automática de Claude es
   de cada máquina. El 31 de agosto el borrado de un perfil se la llevó entera, y el código volvió
   íntegro con un clon.
2. **Claude propone y la persona decide.** No empuja, no fusiona y no borra sin que se le pida, y
   eso lo vigilan permisos y hooks además del contrato.
3. **Nada se da por terminado sin una verificación ejecutada.** Un cambio se cierra con un
   comando en verde y su salida a la vista.
4. **Contexto pequeño y fresco gana a contexto grande y viejo:** una tarea por sesión.
5. **Lo que define comportamiento se versiona; la preferencia personal, no.**
6. **Una regla que nadie cumple es peor que no tenerla,** porque da por cubierto algo que no lo
   está. Por eso cada regla dice qué la sostiene.

## 2. Hooks

Un hook es un comando que Claude Code ejecuta en un momento fijo del ciclo. Es la única pieza
determinista: ocurre aunque el modelo no se acuerde. El criterio para crear uno fue siempre el
mismo: tiene que cumplirse aunque nadie se acuerde, se puede comprobar con un comando y tarda
segundos. Si falta alguna de las tres, es una instrucción del contrato.

| Hook | Evento | Qué hace | Por qué existe | Estado |
|---|---|---|---|---|
| Estado al arrancar | SessionStart | Rama, cambios sin commitear, si la sesión está fuera de un worktree, divergencia entre la rama de entrega y la de integración. Sin `git pull` y sin esperar al `fetch`, que refresca en segundo plano | Un `pull` al arrancar falla o mete una fusión que nadie eligió, y el `fetch` tardaba 10 s por el proxy | Activo desde el 10-sep |
| Commit en la rama de entrega | PreToolUse | Deniega commit, merge, pull, rebase, cherry-pick y revert en la rama que tiene el cliente | Lo entregado no se toca a mano | Activo desde el 14-sep |
| Ramas compartidas del repo del cliente | PreToolUse | En el repo que ve el cliente solo deja preparar `git merge --squash`, y el commit lo hace una persona. Si no sabe en qué rama está, deniega | Lo que entra en la historia del cliente no se puede retirar | Activo desde la separación en dos repos, el 13-oct |
| Verificación antes del push | PreToolUse | La verificación rápida en cualquier push; hacia la rama de entrega, el sello de una completa en verde y el tag de la versión | Es el momento en que el código llega a la otra persona | Activo desde el 14-sep, con sello desde el 9-oct |
| Impacto antes del merge | PreToolUse | Al integrar una rama: documentos vivos sin revisar y escáner de fugas. También deniega cuando no puede comprobar | Los documentos se quedaban atrás días después de cambiar el código | Activo |
| Sugerir la skill | UserPromptSubmit | Lee el mensaje antes que el modelo y nombra la skill del proyecto que encaja | Cuatro de seis skills no se eligieron solas ni una vez en una semana | Activo desde el 17-sep |
| Recordar documentos vivos | PostToolUse | Tras editar código, nombra los documentos que lo describen | Avisar en el momento del cambio, no al cerrar | Activo |
| Recordar el estilo | PostToolUse | Tras editar un documento, pide la pasada de la skill de estilo | Los textos generados repetían los mismos tics | Activo desde el 15-sep |
| Recordar al observador | UserPromptSubmit | Una línea por mensaje: si hay una corrección o un paso repetido, apuntarlo al cerrar | Cargar la skill entera al arrancar costaba 53 KB por sesión | Activo desde el 18-sep |
| Bloquear imágenes | PreToolUse | Denegaba capturas y lecturas de imágenes | La organización cortó con un 403 toda petición con imagen, y la sesión moría entera | Del 25-sep al 1-oct; apagado |
| Verificar al cerrar el turno | Stop | La verificación rápida al acabar cada respuesta | Pensado para "verde antes de integrar" | Escrito y apagado a propósito |

Lo que nos enseñaron:

- **Falla abierto o cerrado.** Los hooks dejan pasar cuando no pueden comprobar, para que un fallo
  de detección no pare el trabajo. La excepción es el repo del cliente: allí un falso permiso deja
  en su historia algo que no se puede retirar, y fallan cerrados.
- **Un hook no invoca una skill.** No hay modelo detrás de un script. Lo más que puede hacer es
  meter una línea de contexto en el momento justo, y el modelo la cumple como una línea del
  contrato.
- **El mayor riesgo son los fallos silenciosos.** Del 15 al 17 de septiembre dos hooks pedían
  skills de terceros que no estaban instaladas: seis "Unknown skill" en los transcripts y nadie lo
  vio. El 30 de septiembre, en el contenedor Linux, los hooks llamaban al Python de Windows y nueve
  fallaban sin avisar, porque un código de salida distinto de 2 no bloquea nada. Desde entonces un
  lanzador, `run.sh`, elige el intérprete según la máquina, y los hooks comprueban que la skill
  existe antes de pedirla.
- **El coste por turno decide si un hook sobrevive.** El de cierre de turno costaba entre 5 y 9 s
  en cada respuesta, también en las que no tocan código, y se quedó apagado: la verificación se
  movió al push. El del observador pasó de cargar 53 KB a una línea de unos 80 tokens.
- **El tiempo máximo de un hook también es una puerta.** En octubre la verificación completa pasó
  de 20 minutos, el hook la cortaba y, como falla abierto, dejaba pasar el push sin verificar.
  Desde el 9 de octubre no la lanza: pide el sello de una completa en verde que cubra ese commit.
- **En modo automático las ediciones van por Bash** (`sed`, heredocs), y un matcher sobre Write y
  Edit no las ve. El recordatorio escucha también Bash, y la garantía está en la puerta del merge.
- **Corren desde el checkout principal** aunque la sesión esté en un worktree, así que un hook
  cambiado en una rama no actúa hasta que llega a la rama de integración. Se prueba a mano con su
  payload antes de fusionar.

## 3. Worktrees

Un worktree es otra carpeta con otra rama del mismo repo, que comparte el `.git`. Uno por tarea es
obligatorio. En una de las dos máquinas hubo unas 175 entradas a worktree desde mediados de
septiembre.

| Qué hicimos | Por qué | Qué lo sostiene | En el esqueleto |
|---|---|---|---|
| Un worktree por tarea, con su rama corta | El 11-sep dos sesiones compartieron el checkout. Una abrió rama y el `HEAD` empezó a responder distinto según quién preguntara. Abrir rama no protege de eso; un worktree, sí | Instrucción en el contrato y aviso al arrancar | `CLAUDE.md`, `session_start.py` |
| `worktree.baseRef: head` | Del 11 al 17-sep los worktrees salían de la rama por defecto del remoto, 33 commits por detrás de la de integración | `settings.json` | `.claude/settings.json` |
| Renombrar la rama `worktree-<nombre>` | El nombre por defecto no dice qué es la rama | Aviso al arrancar | `session_start.py` |
| Integrar desde el checkout principal, tras salir del worktree | La rama de integración está desplegada allí y git no la deja en dos sitios: un `checkout` de esa rama dentro del worktree falla siempre | Lo impone git | `/cerrar-tarea` |
| Comprobar antes del squash que no hay otro proceso a medias | El 15-sep dos sesiones hicieron squash a la vez y una vio en su índice 16 ficheros de la otra | Solo la instrucción | `/cerrar-tarea` |
| Borrar worktree y rama al cerrar | El 17-sep quedaban cuatro worktrees huérfanos y nueve ramas muertas | Solo la instrucción; el script de cierre que se propuso no se escribió | `/cerrar-tarea`, `/revision-periodica` |
| En una rama de más de un día, traer cada mañana la de integración | El contrato y las skills se leen del worktree: una rama del 15-sep no veía una skill que entró cuatro horas después | Instrucción | `AGENTS.md` |
| Enlaces con el prefijo del worktree | La app resuelve los enlaces contra el checkout principal: desde un worktree abrían la copia vieja, o nada | Instrucción | `CLAUDE.md` |
| Rehacer en cada worktree lo que no está en git | Dependencias, `.env` y cachés no viajan | Instrucción, y la verificación avisa | `.worktreeinclude` |

Dos cosas que cada sesión redescubría: si `EnterWorktree` falla a medias, casi siempre el worktree
ya está creado y basta con entrar en él; y dentro de un worktree la propia herramienta rechaza un
comando que combina `cd` con git, así que los comandos van con la ruta escrita entera.

## 4. Skills

Una skill es un procedimiento escrito una vez y guardado con nombre en el repo. Para admitir una
hacía falta que se cumplieran tres condiciones a la vez: tres repeticiones con evidencia, pasos que
se olvidan, y que mantenerla costara menos que repetirla. Lo que ya cubre una regla por ruta no se
convierte en skill.

| Skill, por lo que hace | Evidencia de que se repetía |
|---|---|
| Pasar una reunión al registro de actas, con lo que salga al backlog y al contrato | 55 actas en cuatro meses con el mismo formato, escritas a mano |
| Regenerar en orden los artefactos del motor tras una entrega de datos | Tres veces que se rompió por hacerlo en otro orden |
| Refrescar los datos externos y su emparejado | Cinco rondas en tres meses |
| Sacar la release del entregable, con su prueba | Cuatro entregas; una llegó al cliente con una pantalla vacía |
| Verificar en la app, en contexto propio y sin arreglar nada | Más de 200 commits en la interfaz |
| Un documento entregable con cada afirmación citada contra el código | Pedida expresamente; un comprobador convierte en fallos las citas que faltan y el tiempo futuro |
| Quitar los tics de texto de IA en español | Medido en los documentos: 139 cierres "X, no Y.", 52 "no es X, es Y" y 244 rayas |
| Contrastar un documento vivo con el código | Un umbral desfasado en cuatro documentos cinco días después de cambiarlo |
| La lectura semanal de un experimento en producción | Cada semana, con tres pasos que ya habían fallado |
| Arrancar la app en el contenedor Linux | Admitida con una sola vez, a petición expresa; se retira si no se vuelve a usar |
| Observador de correcciones, de terceros (licencia CC BY 4.0) y copiado al repo | Detectar skills nuevas sin esperar a que se le ocurran a alguien |

Lo que nos enseñaron:

- **Elegir una skill por su descripción es probabilístico,** y la documentación oficial lo
  reconoce. En una semana una skill se eligió sola tres veces, otra dos y cuatro ninguna, sobre
  mensajes que pedían justo lo que hacían; dos peticiones acabaron en skills genéricas. El arreglo
  tuvo dos partes: descripciones con las frases que teclea la gente y que dicen por delante de qué
  skill genérica van, y un hook que nombra la skill al leer el mensaje.
- **Lo que verifica no lo escribió.** Con `context: fork` la skill corre sin la conversación que
  produjo el cambio, y su texto dice que no arregla nada: devuelve afirmaciones con su prueba y
  para. Así no hay bucle de arreglarse y aprobarse a sí misma.
- **Las skills de terceros, dentro del repo.** Las que había que instalar en cada máquina fallaron
  en silencio. La de estilo en inglés se cambió por una propia en español, porque su catálogo no
  casaba con nuestros textos.
- **El procedimiento que viaja al cliente vive en un runbook compartido,** y la skill interna es un
  puntero a él más lo que es solo nuestro.
- **Se mide el uso.** El contador `skillUsage` de `~/.claude.json` dice cuántas veces se invocó
  cada una: en el contenedor, la de estilo 20 veces, la de regenerar 7 y otras casi ninguna.
- **El registro de candidatas y descartes** evita volver a proponer lo que ya se descartó.

## 5. Tareas automatizadas

Contado tal como fue.

| Qué corre solo | Cómo |
|---|---|
| La verificación | Un único script con dos velocidades: la rápida, de unos 10 s, antes de cada push; la completa, para cerrar un cambio. En verde deja un sello con el árbol exacto que vio |
| Las puertas de push y de merge | Los hooks de arriba |
| La release | Un solo comando: comprobaciones previas, verificación completa, versión calculada de los commits convencionales, changelog, tag, avance rápido de la rama de entrega, build, prueba de humo y un sí antes del único push |
| El estado al arrancar y los recordatorios | Hooks |
| El escáner de fugas | En tres sitios: un paso rápido de la verificación, la puerta del merge y el hook de git `pre-commit` del repo del cliente |
| La memoria de sesión | El plugin `remember` resume cada sesión y lo consolida por días |
| Los procesos largos | En segundo plano, vigilados con `Monitor` (unas 18 veces), y `ScheduleWakeup` de respaldo por si el aviso no llegaba |

Lo que no se usó: ninguna tarea programada de Claude Code, ni de escritorio, ni en la nube
(`/schedule`), ni `/loop`. Lo único programado fue un rematch largo con el Programador de tareas
de Windows, porque un proceso en segundo plano muere con la sesión.

La lección está en la revisión periódica de skills y reglas. Estaba prevista, el propio framework
decía que era lo bastante mecánica como para dejarla programada, y no corrió nunca: el registro del
observador dice `last-review-date: never`. Lo que se deja "para revisar cada semana" sin programarlo
no pasa. En el esqueleto la revisión es una skill, y la configuración guiada propone programarla el
primer día.

## 6. Trabajo en paralelo

- **Subagente o sesión aparte.** El criterio es adónde vuelve el resultado. Si vuelve a la
  conversación (buscar, leer, revisar), subagente; si vuelve al repo por su propia rama, sesión
  aparte con su worktree. El explorador se usó unas 83 veces, el de propósito general 53 y el de
  planificación 14.
- **Lo que salía de lado iba a una sesión aparte,** unas 16 veces, en vez de mezclarse con la tarea
  en curso.
- **Auditorías en abanico:** tres exploradores en paralelo antes de separar el repo del cliente;
  diez auditores a la vez sobre documentos y código, y después un encargo a cada uno para aplicar
  lo suyo; cinco agentes reescribiendo en lote rayas y tildes.
- **Desarrollo por subagentes:** cada tarea de un plan la implementaba uno mientras otro revisaba
  en segundo plano la anterior, y al final se revisaba la rama entera.
- **Segunda opinión con contexto limpio:** un revisor rechazó dos veces un cambio grande y lo
  aprobó después de tres arreglos.
- **Descartado:** guardar subagentes propios en `.claude/agents/`. Con dos personas, pedir "usa un
  subagente para revisar X" da el mismo aislamiento sin mantener un fichero.

## 7. Y además

| Qué hicimos | Por qué | Qué lo sostiene | En el esqueleto |
|---|---|---|---|
| Un contrato (`CLAUDE.md`) de menos de 200 líneas, solo con reglas verificables, que se sustituyen en vez de encadenarse | Por encima de ese tamaño el modelo lo lee como ruido. Se podó de 295 a 199 líneas el 1-sep, y hoy vuelve a tener 220: si no se poda, crece | La revisión periódica, cuando corre | `AGENTS.md` y `CLAUDE.md`; la verificación comprueba el límite |
| Reglas por ruta en `.claude/rules/`, con `paths:` | Lo que aplica a una parte del repo no gasta contexto en las demás | Las carga la herramienta | `.claude/rules/` |
| Permisos curados: `allow`, `ask` para push y merge, `deny` para el push forzado y los secretos | El límite razonable es el push, no el commit: un commit es local y se deshace | `settings.json`, versionado | `.claude/settings.json` |
| El fichero de permisos compartido crece por commit revisado; el personal, solo | La lista acumulada a base de "aceptar siempre" tenía entradas muertas y una que autorizaba cualquier cosa | La revisión | `/revision-periodica` |
| Nunca `bypassPermissions` | Es la única barrera entre una alucinación y un borrado o un push | Decisión escrita | `README.md` |
| La memoria automática como índice de punteros | El borrado del perfil del 31-ago se la llevó entera | Instrucción | `CLAUDE.md` |
| Actas y backlog en el repo | El histórico de decisiones lo consulta la otra persona, que no tiene tu memoria | La skill de actas | `docs/meeting-log.md`, `docs/backlog.md` |
| Plan mode obligatorio en las zonas calientes, que están escritas | Hay ficheros donde un error no rompe el build sino que cambia un número que alguien va a mirar | Instrucción; 67 planes presentados para aprobar en una máquina | `AGENTS.md`, `.claude/rules/` |
| El plan de un cambio grande, a un fichero | El plan de plan mode desaparece con la sesión. Hay 17 planes y 2 especificaciones con el flujo de brainstorming y planes de superpowers | Instrucción | `AGENTS.md` (`docs/planes/`) |
| Prompts con criterio de aceptación | Un prompt sin criterio produce algo que parece terminado, y entonces el que comprueba eres tú | Instrucción | `README.md` |
| Cada afirmación con su prueba, o marcada como no verificada | "Debería funcionar" no vale como respuesta; "no he podido comprobarlo", sí | Instrucción y la skill de verificar | `AGENTS.md`, `/verificar` |
| Un fallo en un número empieza por un test que falla, con el valor esperado puesto por una persona | Si nadie dice qué número tiene que salir, el test fija lo que el código hace hoy | Instrucción | `AGENTS.md` |
| Revisión por riesgo, en tres niveles | La regla de leer el diff entero estuvo dos meses escrita sin que nadie la cumpliera | Instrucción | `README.md` |
| Revisión con contexto limpio en zonas calientes, diffs grandes y sesiones largas | Quien escribió el código ya no lo juzga bien | Solo la instrucción: `/code-review` no se invocó nunca | `CLAUDE.md` |
| Squash para la rama corta, `--no-ff` para la de varios días | Los commits intermedios de una sesión no valen nada; los pasos verificados de una rama larga, sí | Instrucción | `/cerrar-tarea` |
| La rama de entrega solo avanza por avance rápido, con un tag por entrega y un manifiesto dentro del paquete | El 18-sep las dos máquinas sacaron la misma versión a la vez y un `git pull` metió un merge en la rama de entrega | Hook, configuración de git y la propia release, solapados a propósito | `scripts/release.py`, `pre_bash.py` |
| Documentación viva: cada documento declara qué código describe | Lo que dice un documento deja de ser verdad sin que nadie lo note | Manifiesto, recordatorio y puerta del merge | `docs/manifest.toml`, `scripts/docs_impact.py` |
| Dos repos: el de código, compartido con el cliente, y el interno, con la configuración de la IA | Lo interno (personas, actas, incidentes, configuración) no puede viajar | Escáner de fugas y hooks de git | `scripts/boundary/` |

Desde el 30 de septiembre una de las máquinas trabaja con Claude Code dentro de un contenedor Linux
que monta la misma carpeta que Windows. Trajo sus trampas: los entornos de Python y de Node son de
Windows y no se tocan desde Linux, y los hooks necesitaron un lanzador que elija el intérprete.

Plugins: `superpowers` (brainstorming, planes, depuración), `remember` (memoria de sesión),
`context-mode` (mucho hasta finales de septiembre y después nada) y `frontend-design`. Instalados y
sin uso: `code-simplifier` y `pyright`.

## 8. Lo que encontramos al revisarlo

Preparar este resumen sirvió de auditoría. Lo que salió, como lección para cualquiera:

- **El contrato no llegaba.** Desde que el código y lo interno se separaron, el `CLAUDE.md` del
  repo de código solo importa el del interno. Esa importación es externa y necesita una aprobación
  por proyecto. En el contenedor no estaba aprobada (`hasClaudeMdExternalIncludesApproved: false`)
  y el diálogo no se había mostrado nunca, así que las sesiones abiertas en el repo de código
  arrancaban sin las reglas del proyecto. Solo los hooks, cableados por ruta absoluta, seguían
  actuando. Que el contrato se carga se comprueba con `/memory` o `/context`, y conviene no
  depender de una importación externa: el esqueleto copia el contrato al repo del cliente en vez
  de importarlo.
- **Las reglas por ruta tampoco cargaban.** Estaban enlazadas con un symlink que apunta fuera del
  repo, y la documentación dice que eso cuenta como importación externa y que, aun aprobada, las
  reglas con `paths:` no se cargan. Lo comprobamos leyendo ficheros que casaban con dos reglas y
  no se cargó ninguna. Las skills enlazadas, en cambio, sí aparecen.
- **Los hooks solo funcionan con Python 3.14,** por una sintaxis nueva (`except A, B:` sin
  paréntesis), y con un Python anterior fallarían todos en silencio. Por eso el esqueleto se
  comprueba contra 3.11.
- **El hook de cierre de turno, el que está apagado, devuelve su decisión en un sitio que la
  documentación no acepta.** Si alguien lo hubiera encendido, habría dejado pasar todo.
- **El recordatorio de documentación aplica su manifiesto a cualquier repo,** también a ficheros de
  otro proyecto que se llaman igual.
- **Hay una clave de API en claro en la configuración de usuario de Claude Code,** en una carpeta
  que además se monta en el contenedor. Los secretos van en variables de entorno, fuera de los
  ficheros de configuración.
- **La revisión periódica sigue pendiente desde finales de septiembre,** igual que la decisión de
  retirar la manual en favor del observador (sección 5).

## 9. Lo descartado

- `bypassPermissions` y el auto-accept total, en ningún caso.
- Subagentes propios en `.claude/agents/`: el aislamiento ya viene de serie.
- Compartir la memoria automática entre máquinas: va contra su diseño.
- Confiar a la memoria una regla de comportamiento, que puede perderse o quedarse vieja.
- Un `git pull` automático al arrancar.
- Un hook que lance `/code-review` en el push. Un hook no puede invocar un comando de barra, y una
  rama se empuja muchas veces al día; si algún día se automatiza, el sitio es el momento de
  integrar.
- Etiquetar en cada push. No todo push es una entrega, y sin integración continua la máquina de
  quien construye es el único sitio donde coinciden el código, los datos y la decisión de entregar.

## 10. Riesgos y cómo quedan cubiertos

| Riesgo | Cómo se cubre |
|---|---|
| Una cifra plausible pero mal conciliada que llega al cliente | El criterio de conciliación en el prompt, un test que fija el número y el contraste por un camino distinto; plan mode en las zonas calientes |
| Que "mi Claude" y "tu Claude" se comporten distinto sin que nadie lo note | La configuración que importa vive en git, y una sesión no se da por cerrada sin escribir lo decidido |
| Un contexto viejo que contradice el presente | Sustituir las reglas en vez de encadenarlas, y comprobar contra el código antes de fiarse de una memoria antigua |
| Permisos acumulados sin criterio | El fichero compartido solo crece por commit revisado |
| Reglas escritas que nadie cumple | Cada regla dice qué la sostiene, y la revisión periódica quita o automatiza la que nadie sigue |
| Una pieza que falla en silencio | En el esqueleto, `bootstrap.py doctor` comprueba qué Python eligen los hooks y que cada uno responde |

Para empezar otro proyecto con todo esto puesto está el esqueleto `esqueleto-proyecto-ia`, que se
configura en una primera conversación con `/configurar-proyecto`.
