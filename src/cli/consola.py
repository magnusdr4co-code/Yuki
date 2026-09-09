"""
Lo que comparten los comandos al escribir en la terminal.

La paleta y el banner estaban en `cli.py` y los usaban los veinte comandos; al
repartirlos por temas habrían acabado importándose unos a otros sólo para eso.

Es la misma paleta que `scripts/_consola.py`, y a propósito no se comparte con
él: los guiones de operación pueden ejecutarse sin el paquete instalado, y
hacerles depender de `src/` para pintar un tick sería un acoplamiento pagado por
seis constantes.
"""

from ..core.seasons import get_current_micro_season

MAGENTA = "\033[95m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner() -> None:
    """La cabecera, con la estación del año que atraviesa Yuki al ejecutarse."""
    season = get_current_micro_season()
    print(f"""
{BOLD}{MAGENTA}======================================================================
       ⛩️  YUKI (雪) — DIVA DIGITAL AUTÓNOMA (HERMES AGENT)  ⛩️
======================================================================{RESET}
{DIM}Estación: {season['sekki']} ({season['micro_season_ko']}){RESET}
{DIM}Personalidad Evolutiva (Honcho) | Medios (Nous Portal) | Memoria FTS5 (<113ms){RESET}
""")
