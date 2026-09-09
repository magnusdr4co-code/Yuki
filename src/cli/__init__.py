"""
Los comandos de la línea de órdenes, por temas.

`cli.py` había llegado a mil doscientas líneas: veinte comandos y el analizador
de argumentos en el mismo fichero, sin una sola prueba. Aquí viven los comandos
—agrupados por lo que hacen— y allí se queda lo que es de verdad la interfaz:
declarar los argumentos y repartir.

La separación no es estética. Un fichero de mil doscientas líneas se lee por
búsqueda, no por lectura, y eso hace que cada añadido se pegue donde caiga.
"""
