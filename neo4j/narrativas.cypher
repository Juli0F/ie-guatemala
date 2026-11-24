// Carga del modelo de narrativas en Neo4j (generado por analisis/pipeline_narrativas.py)
// Copia data/cuentas_narrativas.csv y data/publicaciones_clasificadas.csv a la carpeta import/ de Neo4j.
CREATE CONSTRAINT cuenta_id IF NOT EXISTS FOR (c:Cuenta) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT pub_id IF NOT EXISTS FOR (p:Publicacion) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT tema_id IF NOT EXISTS FOR (t:Tema) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT depto_nombre IF NOT EXISTS FOR (d:Departamento) REQUIRE d.nombre IS UNIQUE;

UNWIND ["Alta Verapaz", "Baja Verapaz", "Chimaltenango", "Chiquimula", "El Progreso", "Escuintla", "Guatemala", "Huehuetenango", "Izabal", "Jalapa", "Jutiapa", "Petén", "Quetzaltenango", "Quiché", "Retalhuleu", "Sacatepéquez", "San Marcos", "Santa Rosa", "Sololá", "Suchitepéquez", "Totonicapán", "Zacapa"] AS nombre MERGE (:Departamento {nombre: nombre});

LOAD CSV WITH HEADERS FROM 'file:///cuentas_narrativas.csv' AS f
MERGE (c:Cuenta {id: f.cuenta})
SET c.plataforma = f.plataforma, c.tipo = f.tipo, c.seguidores = toInteger(f.seguidores),
    c.pagerank = toFloat(f.pagerank), c.intermediacion = toFloat(f.intermediacion), c.comunidad = toInteger(f.comunidad)
WITH c, f WHERE f.departamento <> ''
MATCH (d:Departamento {nombre: f.departamento}) MERGE (c)-[:UBICADA_EN {confianza: f.conf_ubicacion}]->(d);

LOAD CSV WITH HEADERS FROM 'file:///publicaciones_clasificadas.csv' AS f
MATCH (a:Cuenta {id: f.cuenta})
MERGE (p:Publicacion {id: f.id_publicacion})
SET p.plataforma = f.plataforma, p.fecha = date(f.fecha), p.subnarrativa = f.subnarrativa,
    p.interaccion = f.interaccion, p.vistas = toInteger(f.vistas), p.engagement = toInteger(f.engagement)
MERGE (a)-[:PUBLICO]->(p)
FOREACH (t IN CASE WHEN f.temas = '' THEN [] ELSE split(f.temas, '|') END |
  MERGE (tm:Tema {id: t}) MERGE (p)-[:TRATA_SOBRE]->(tm))
WITH p, f
CALL { WITH p, f WITH p, f WHERE f.departamento <> ''
  MATCH (d:Departamento {nombre: f.departamento}) MERGE (p)-[:SOBRE_LUGAR {confianza: f.conf_ubicacion}]->(d) }
WITH p, f WHERE f.cuenta_objetivo <> ''
MATCH (a:Cuenta {id: f.cuenta}), (b:Cuenta {id: f.cuenta_objetivo})
MERGE (a)-[r:AMPLIFICA {tipo: f.interaccion}]->(b) ON CREATE SET r.peso = 0 SET r.peso = r.peso + 1;

// --- Consultas de análisis ------------------------------------------------
// Volumen por tema y departamento
MATCH (p:Publicacion)-[:TRATA_SOBRE]->(t:Tema), (p)-[:SOBRE_LUGAR]->(d:Departamento)
RETURN t.id AS tema, d.nombre AS departamento, count(p) AS publicaciones ORDER BY publicaciones DESC;

// Cuentas que conectan varios temas (posibles puentes entre narrativas)
MATCH (c:Cuenta)-[:PUBLICO]->(:Publicacion)-[:TRATA_SOBRE]->(t:Tema)
WITH c, collect(DISTINCT t.id) AS temas WHERE size(temas) >= 3
RETURN c.id, temas, c.intermediacion ORDER BY c.intermediacion DESC LIMIT 20;

// Red de narcopolítica en Petén: quién amplifica a quién
MATCH (a:Cuenta)-[:PUBLICO]->(p:Publicacion)-[:TRATA_SOBRE]->(:Tema {id:'narcopolitica'}),
      (p)-[:SOBRE_LUGAR]->(:Departamento {nombre:'Petén'}), (a)-[r:AMPLIFICA]->(b:Cuenta)
RETURN a.id, b.id, r.tipo, r.peso ORDER BY r.peso DESC LIMIT 25;
