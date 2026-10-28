# <!-- RELLENAR: nombre del proyecto -->

<!-- El contrato del proyecto. Lo cargan todas las sesiones de Claude Code (a través de
CLAUDE.md) y lo leen otras herramientas que entienden AGENTS.md. Reglas que se puedan comprobar,
menos de 200 líneas entre este fichero y CLAUDE.md, y cuando una decisión cambia se sustituye su
línea: el relato va a docs/meeting-log.md. /configurar-proyecto rellena las marcas RELLENAR. -->

## Proyecto

<!-- RELLENAR: objetivo en dos frases, para quién es, fase actual y fechas clave. -->

**Entregables:** <!-- RELLENAR: qué se entrega (código, una app, informes, modelos, documentos
para el cliente), a quién y en qué formato. -->

**Equipo y zonas:** <!-- RELLENAR: quién lleva cada parte del repo. -->
Una sesión no toca la zona de otra persona sin coordinarlo: lo que aparezca allí va a
`docs/backlog.md` y se avisa.

## Reglas que aplican siempre

- **Una tarea, una rama corta, un worktree.** Antes de cambiar ficheros se abre un worktree con
  su rama (`feature/`, `fix/`, `docs/`). La rama vive horas, dos días como mucho; si no cabe, la
  tarea se parte en piezas.
- **Se integra en `<!-- RELLENAR: rama de integración -->` por squash** desde el checkout
  principal: un commit por cambio lógico. Una rama de varios días cuyos commits valen por sí
  solos entra con `git merge --no-ff`.
- **Commits:** <!-- RELLENAR: quién commitea (Claude cuando se le pide, o solo personas en la
  rama de integración), formato (conventional commits) y si llevan coautoría de la herramienta. -->
  El push y el merge piden confirmación cada vez, y nunca se fuerza un push a una rama compartida.
- **Hecho quiere decir verificado.** Un cambio está terminado cuando `python3 scripts/check.py`
  sale en verde. Cada afirmación va con su prueba (la salida del comando, el test, la captura) o
  se marca como no verificada.
- **Un fallo en un número se arregla empezando por un test que falla,** con el valor esperado
  puesto por una persona: primero se ve fallar, después se arregla y se ve pasar.
- **Idiomas:** <!-- RELLENAR: código, identificadores y comentarios; documentos; mensajes de
  commit; entregables. -->
- **El repo es la única fuente compartida.** Lo decidido va a un fichero antes de cerrar la
  sesión: reuniones y decisiones a `docs/meeting-log.md`, lo pendiente a `docs/backlog.md`, y un
  cambio que dure más de una sesión, a un plan en `docs/planes/AAAA-MM-DD-tema.md` (objetivo,
  criterio de aceptación, ficheros que toca y qué no se hace).

## Zonas calientes

<!-- RELLENAR: los ficheros donde un error no rompe el build sino que cambia un número que
alguien va a mirar. En ellos, plan mode obligatorio y diff leído entero por una persona. El
detalle de cada zona va a su regla en .claude/rules/. -->

## Restricciones duras

<!-- RELLENAR: una línea verificable por regla ("los importes, siempre en céntimos enteros").
El porqué y la trampa de cada una, en la regla por ruta de su zona. -->

## Entorno y comandos

```bash
python3 scripts/check.py           # verificación completa: la definición de hecho
python3 scripts/check.py --fast    # solo lo rápido (segundos); corre antes de cada push
```

<!-- RELLENAR: cómo se instala, cómo se arranca la app y los comandos propios del proyecto. -->

## Documentación

| Qué | Dónde |
|---|---|
| Reuniones y decisiones | `docs/meeting-log.md` |
| Pendientes de otras zonas | `docs/backlog.md` |
| Planes de cambios grandes | `docs/planes/` |
| Cómo se trabaja con la IA y por qué | `docs/practicas.md` y `README.md` |

<!-- RELLENAR: los documentos vivos del proyecto; cada uno, en docs/manifest.toml con el código
que describe. -->
