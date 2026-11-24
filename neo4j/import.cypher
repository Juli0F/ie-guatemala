// Carga del ecosistema sintético en Neo4j (generado por analisis/generar_red.py)
// Copia data/nodos.csv y data/aristas.csv a la carpeta import/ de Neo4j.
CREATE CONSTRAINT cuenta_id IF NOT EXISTS FOR (c:Cuenta) REQUIRE c.id IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///nodos.csv' AS fila
MERGE (c:Cuenta {id: fila.id})
SET c.plataforma = fila.plataforma, c.grupo = fila.grupo, c.postura = fila.postura,
    c.seguidores = toInteger(fila.seguidores), c.engagement = toFloat(fila.engagement),
    c.pagerank = toFloat(fila.pagerank), c.intermediacion = toFloat(fila.intermediacion),
    c.comunidad = toInteger(fila.comunidad), c.rol = fila.rol;

LOAD CSV WITH HEADERS FROM 'file:///aristas.csv' AS fila
MATCH (a:Cuenta {id: fila.origen}), (b:Cuenta {id: fila.destino})
MERGE (a)-[r:AMPLIFICA {tipo: fila.tipo}]->(b)
SET r.peso = toInteger(fila.peso);

// --- Consultas de análisis -------------------------------------------
// Top 10 nodos de influencia
MATCH (c:Cuenta) RETURN c.id, c.plataforma, c.pagerank, c.rol ORDER BY c.pagerank DESC LIMIT 10;

// Puentes entre comunidades: cuentas con vecinos en 2+ comunidades distintas
MATCH (c:Cuenta)-[:AMPLIFICA]-(v:Cuenta)
WITH c, count(DISTINCT v.comunidad) AS comunidades_tocadas
WHERE comunidades_tocadas >= 3
RETURN c.id, c.comunidad, comunidades_tocadas, c.intermediacion ORDER BY c.intermediacion DESC;

// Camino más corto entre el núcleo emisor y la comunidad vecinal (ruta de difusión)
MATCH (o:Cuenta {grupo:'origen'}), (v:Cuenta {grupo:'vecinos'})
MATCH p = shortestPath((o)-[:AMPLIFICA*..6]->(v))
RETURN p ORDER BY length(p) LIMIT 5;

// Opcional con Graph Data Science: Leiden y PageRank nativos
// CALL gds.graph.project('eco', 'Cuenta', {AMPLIFICA: {orientation:'UNDIRECTED', properties:'peso'}});
// CALL gds.leiden.write('eco', {relationshipWeightProperty:'peso', writeProperty:'leiden'});
// CALL gds.pageRank.write('eco', {relationshipWeightProperty:'peso', writeProperty:'pr_gds'});
