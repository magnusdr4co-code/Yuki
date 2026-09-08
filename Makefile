# Atajos de lo que se hace a diario con Yuki.
#
# Existe porque los comandos importantes están repartidos entre el README, el
# runbook y la cabeza de quien los escribió. Un `make` es más difícil de olvidar
# que una línea en un documento.

.DEFAULT_GOAL := ayuda
PY ?= python3

.PHONY: ayuda instalar pruebas cobertura linter humo humo-ci simulacro restaurar circuito pulso estado albedrio sueno bitacora freno parar soltar todo imagen replica limpiar

ayuda:  ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

instalar:  ## Dependencias mínimas para desarrollar y probar
	$(PY) -m pip install -r requirements-dev.txt

pruebas:  ## La suite completa
	$(PY) -m pytest tests -q

cobertura:  ## Suite con informe de cobertura por fichero
	$(PY) -m pytest tests -q --cov --cov-report=term-missing

linter:  ## Ruff sobre todo el proyecto
	ruff check .

humo:  ## Comprobación de humo (URL=... para incluir el Salón)
	$(PY) scripts/smoke_check.py $(if $(URL),--url $(URL),)

humo-ci:  ## Sólo lo que no depende de credenciales, como en la CI
	$(PY) scripts/smoke_check.py --solo memoria,bitacora,marcado_articulo_50,pulso,caracter

simulacro:  ## Rompe a Yuki a propósito y comprueba las invariantes
	$(PY) scripts/chaos_drill.py

restaurar:  ## Restaura la última copia real y comprueba que sirve
	$(PY) scripts/restore_drill.py

circuito:  ## Fabrica una copia y la restaura: no necesita copia previa
	$(PY) scripts/restore_drill.py --ciclo

todo: linter pruebas simulacro circuito humo-ci  ## Lo que ejecuta la CI, en local

pulso:  ## Signos vitales: ¿corre el proceso, y además vive Yuki?
	$(PY) cli.py pulso

estado:  ## Inventario del estado durable
	$(PY) cli.py estado

albedrio:  ## Carácter, refuerzo y ritmos propios
	$(PY) cli.py albedrio

sueno:  ## Ciclo de sueño en seco (FASE=nrem|rem|olvido|noche)
	$(PY) cli.py sueno --fase $(or $(FASE),nrem) --seco

bitacora:  ## Verifica que nadie tocó el registro de sus actos
	$(PY) cli.py bitacora --verificar

freno:  ## Estado del freno de mano
	$(PY) cli.py freno

parar:  ## Freno al máximo (MOTIVO="..." para dejar constancia)
	$(PY) cli.py freno --nivel todo --motivo "$(or $(MOTIVO),parada manual)"

soltar:  ## Suelta el freno
	$(PY) cli.py freno --soltar

imagen:  ## Construye la imagen de producción
	docker build -t yuki-agent:local .

replica:  ## Levanta la réplica local de la instancia
	docker compose -f deploy/virtual/docker-compose.virtual.yml up --build

limpiar:  ## Borra artefactos locales ignorados por git (no toca lo versionado)
	git clean -X -f output/ data/ || true
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
