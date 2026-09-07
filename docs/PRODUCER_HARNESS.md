# Ejecución real del DM de producción

El nombre Hermes y `active_role=producer` no otorgan capacidades por sí mismos.
El adaptador comprueba ID y pairing persistente antes de habilitar `producer_tools`.
Los canales públicos no reciben herramientas. El modelo actual es configurado en Vertex.

`ProducerHarness` usa llamadas nativas `tools`/`tool_calls` de la pasarela OpenAI-compatible,
devuelve resultados con el mismo `tool_call_id` y repite hasta una respuesta final
(máximo seis rondas, ocho operaciones por ronda). No hay shell ni autoedición general.
El contexto reciente del usuario se recupera de SQLite, con límites; las promesas
anteriores no son prueba de ejecución. Cada respuesta lleva recibos deterministas.
Un fallo o límite devuelve resultado parcial; no se promete trabajo futuro inexistente.
Model Armor inspecciona el prompt, argumentos y respuesta. La inferencia sale del event loop.

Herramientas: `library_inventory`, `library_list`, `library_save_text`, `library_read`,
`library_set_status`, `terminal_run`, `runtime_config_get`, `runtime_config_set` y
`runtime_config_rollback`. El canon es tipo/estado: sonora, visual, palabra, audiovisual;
semilla, en-desarrollo, terminado. Los originales no se borran. Imports idempotentes
por hash, límite 100 MB por archivo, sin enlaces fuera de output. Simulaciones conocidas
se omiten. JSON de producción permanece en origen; no se etiqueta como obra.

`output/Biblioteca/CANON.md`, `INDEX.md` e `index.json` viven en el volumen persistente
de output. El estado inicial es en-desarrollo: ni la publicación ni un éxito de API
certifican que una obra esté terminada. Guardar otro texto crea una versión por hash.

El flujo específico del Salón archiva presentación y letra y avisa al DM al terminar;
los medios se inventarían al cierre. Un reinicio corta trabajos en memoria:
no existe aún una cola durable que pueda reanudarlos automáticamente.

## Terminal y configuración

`terminal_run` sólo acepta argv sin shell: `pwd`, `git status|diff|log`, `pytest` y
`python -m pytest`, además de lectura limitada (`ls`, `find`, `rg`, `sed`) bajo las rutas
de código y Biblioteca. Tiene 30 segundos, 12 KB de salida y redacción de patrones de
secreto. Niega `data/`, `.git`, `deploy/`, archivos `.env`, red, escritura, instalación,
procesos persistentes y cualquier sintaxis de shell.

La configuración vive como overlay atómico en `data/runtime_overrides.json`; no reescribe
`config.yaml`. Por DM emparejado sólo permite temperatura, `max_tokens` y los modelos
Gemini 3.6/3.7/3.8 Flash definidos en la allowlist. Cada cambio registra actor, motivo y
marca temporal; `runtime_config_rollback` vuelve al valor base. No permite modificar
secretos, permisos/IAM, pairing, Discord, código, red ni infraestructura.

La evolución autónoma se revisa tras la síntesis diaria. Sólo puede ajustar temperatura,
con crecimiento ya registrado (confianza ≥0.80), al menos cinco interacciones y un salto
máximo de 0.15. No recibe terminal ni las herramientas del Productor.
