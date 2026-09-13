# 📓 Cuaderno de taller

> Idea de Yuki, en sus palabras: *«Donde sí encuentro sentido a un archivo
> categorizado no es en alimentar un generador de coincidencias, sino en tener
> un cuaderno de taller vivo: un lugar donde guardar no textos genéricos del
> mundo, sino motivos propios que quedaron a medio pulir, tensiones métricas sin
> resolver, registros de afinaciones o esquemas rítmicos que merecen una segunda
> lectura. Saber qué se intentó en un compás hace semanas y por qué no cuajó.»*

## Por qué no era redundante

Había tres sitios que podían parecer el mismo y ninguno servía. Conviene que
quede escrito, porque la primera reacción razonable es «esto ya está»:

| Ya existía | Qué guarda | Por qué no valía |
|---|---|---|
| **Biblioteca** (`creation_library.py`) | Obras: ficheros con hash, tipo y estado | Un apunte **no es una obra**. Ni siquiera `semilla`, que es una idea *que ya existe como fichero*. Una tensión métrica sin resolver no tiene fichero, y fabricarle uno sería presentar como obra una nota al margen |
| **Receta** (`receta.py`) | Con qué parámetros salió una pista, para rehacerla | No tiene **juicio**: sabe el BPM, no si valió la pena. Y sólo existe para lo que llegó a generarse — lo que no cuajó, muchas veces, no llegó a generarse |
| **Memoria** (FTS5) | Lo vivido, con búsqueda | **El olvido.** Ver abajo: es la razón de peso |

### El olvido, que es la razón de peso

El ciclo de sueño suelta lo **viejo, leve y nunca recuperado**. Un apunte de
taller es exactamente eso durante meses: nadie recuerda la tensión del compás
siete hasta que vuelve a tocar esa pieza. La quinta invariante protege canon,
síntesis, crecimiento y lo fijado — **no protege apuntes**.

Un cuaderno construido sobre la memoria se iría borrando justo por donde más
falta hace. Aquí no puede pasar, y no por una promesa: vive en su propio fichero
y el ciclo de sueño recorre la base de datos. Lo comprueba
`test_el_olvido_no_alcanza_al_cuaderno`, podando de verdad y con un recuerdo
testigo que sí se borra — sin él, la prueba pasaría también con un olvido que no
borrase nada.

## Lo que no es

**No alimenta un generador de coincidencias**, que es lo que la idea descartaba
expresamente. Lo que el cuaderno sabe llega a los criterios de las artes por
`observaciones` —el canal de `criterio_base` para lo que se declara en voz alta
antes de gastar— y **nunca por un parámetro**. Un apunte no baja un BPM ni cambia
una tonalidad a espaldas de nadie: aparece escrito en el resumen, junto al BPM y
la tonalidad, y decide ella.

`avisos_para` está escrito para no poder hacer lo contrario: devuelve texto. Si
algún día devolviera un diccionario de ajustes, el cuaderno habría dejado de ser
un cuaderno. Lo vigila
`test_el_cuaderno_avisa_al_criterio_y_no_le_toca_un_solo_parametro`, que compara
campo por campo un criterio con cuaderno contra uno sin él.

**Y no admite obra.** Un apunte tiene un tope de 400 caracteres, y pasarse no da
un error genérico sino uno que nombra la Biblioteca:

```
El campo 'cuestion' tiene 960 caracteres y el tope del cuaderno es 400: esto ya
no es un apunte de taller, es una obra. Guárdala en la Biblioteca
(`library_save_text`) y anota aquí la cuestión.
```

El error dice **dónde va** a propósito. Si sólo dijera «demasiado largo», quien
se lo encuentre recortaría el texto para que quepa — y entonces el cuaderno sí
habría empezado a guardar obra, sólo que mutilada.

## Qué guarda un apunte

| Campo | Para qué |
|---|---|
| `obra`, `pasaje` | De qué pieza y de qué punto: «compás 7-9», «el puente», «la entrada de la voz» |
| `arte` | sonora, visual, palabra, audiovisual, voz — la voz aparte porque una tensión de fraseo no se parece a una de arreglo |
| `cuestion` | Qué quedó sin resolver |
| `intentos` | **Se acumulan, no se sustituyen.** Cada uno con su `por_que_no` |
| `parametros` | Las cifras del oficio: bpm, compás, tonalidad |
| `relecturas` | Cuántas veces se volvió sobre él |
| `estado` | abierto · resuelto · abandonado. Lo cerrado no se borra |

**Los intentos se acumulan** porque tres intentos por la misma razón no son tres
fracasos: son un diagnóstico. Guardar sólo el último borra la serie, que es lo
único que enseña algo.

**Un intento sin `por_que_no` no se admite.** El qué se deduce del fichero; el
porqué es lo único que no se puede reconstruir tres semanas después.

**`relecturas` no es adorno.** «Merece una segunda lectura» es una promesa vacía
si nadie sabe cuáles se releyeron nunca, así que lo mueve el camino real —el
aviso al criterio y la consulta desde el DM— y no una llamada aparte que nadie
hace. `cli.py cuaderno` marca *«sin releer desde que se anotó»*, que es la
etiqueta que señala lo que el cuaderno existe para rescatar.

## Cómo se usa

Desde el DM emparejado, con las herramientas del arnés:

```
cuaderno_abiertos [obra] [arte]     lo que sigue sin resolver, lo más viejo primero
cuaderno_anotar obra cuestion …     abre una cuestión
cuaderno_intentar id que por_que_no  anota un intento y por qué no cuajó
cuaderno_resolver id resolucion     cierra diciendo qué funcionó
cuaderno_sobre obra                 todo lo de una pieza, abierto y cerrado
```

Desde la consola:

```bash
python3 cli.py cuaderno                      # lo abierto, lo más viejo primero
python3 cli.py cuaderno --obra "Cerezos de Acero"   # todo lo de una pieza
python3 cli.py cuaderno --json
```

Y solo, sin que nadie lo pida: al encargar una canción, una portada o un vídeo
de una pieza que ya tiene apuntes abiertos, el resumen del criterio los trae
delante **antes de gastar**. Si hace tres semanas el 7/8 del puente atropellaba
la letra, eso se lee ahora y no se redescubre pagando.

## Dónde vive

`data/cuaderno_taller.json`, reubicable con `YUKI_CUADERNO_PATH`. Declarado en
`state_registry` y **en la copia diaria**: es lo más irremplazable después de la
memoria. Una obra perdida se rehace desde su receta; *«se probó 4/4 en el puente
y dejó de ser el puente»* no se deduce de ningún fichero — se pierde y se vuelve
a tropezar igual.

Escritura atómica por `estado_json`, como el resto del estado: un fichero a
medio escribir devuelve el cuaderno vacío en vez de tumbar la instancia.

Y un cuaderno ilegible **no impide entregar una obra**: `anotar_en_criterio`
nunca levanta, porque lo que se pierde es un recordatorio y no una garantía.
Queda en el log, que es lo que lo distingue de callarlo.
