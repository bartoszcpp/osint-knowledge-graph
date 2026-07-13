# Infra

Infrastructure assets for the OSINT Knowledge Graph.

## `neo4j/init/`

Cypher scripts that bootstrap the graph schema (uniqueness constraints +
secondary indexes). The same schema is applied programmatically by the API on
startup via `app.db.neo4j.init_schema()`.

Apply manually:

```bash
cat neo4j/init/01_schema.cypher | cypher-shell -u neo4j -p <password>
```
