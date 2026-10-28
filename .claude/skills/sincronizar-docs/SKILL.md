---
name: sincronizar-docs
description: Contrasta un documento vivo (o los que `scripts/docs_impact.py --impact` marca como REVISAR) con el código, afirmación por afirmación, y corrige en el documento lo que esté desfasado, cada corrección con su prueba. Corre en contexto propio, no toca código y no da nada por cierto sin comprobarlo. Úsala cuando el usuario pida poner al día o sincronizar documentación, o comprobar si un documento sigue siendo verdad. También cuando la puerta del merge deje documentos en REVISAR.
argument-hint: [documento, o "impact" para los que marque --impact]
context: fork
agent: general-purpose
background: false
---

# Sincronizar un documento con el código

Documentos: **$ARGUMENTS**. Con "impact", los que salgan como REVISAR en
`python3 scripts/docs_impact.py --impact`.

## 1. Qué describe

Su entrada en `docs/manifest.toml` dice qué código describe (`code`). Se lee el documento entero
y ese código.

## 2. Afirmación por afirmación

Para cada afirmación que se pueda comprobar (una ruta, un comando, un valor por defecto, un
umbral, un comportamiento):

- dónde lo decide el código, con `fichero:línea`;
- si se puede ejecutar, se ejecuta (el comando con `--help`, el test, dos líneas de Python);
- y se clasifica: cierta, desfasada (con el valor real) o no comprobable.

## 3. Se corrige el documento, nunca el código

Cada desfase se corrige en el documento con el valor real. Si parece que el equivocado es el
código, no se toca: se apunta como hallazgo para la sesión de trabajo. Al terminar, el documento
lleva al día su línea «Revisado: AAAA-MM-DD, motivo».

## 4. Salida

Los cambios (antes y después, con su prueba), los hallazgos sobre el código y lo que no se pudo
comprobar.
