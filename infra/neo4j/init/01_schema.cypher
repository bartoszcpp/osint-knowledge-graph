// ============================================================
// OSINT Knowledge Graph - Neo4j schema bootstrap
// Apply manually:
//   cat 01_schema.cypher | cypher-shell -u neo4j -p <password>
// Constraints create a backing index -> MATCH by key is O(1).
//
// Data model (Phase 4):
//   (:Entity {canonical_id, name, type})   type in {PERSON, ORG, GPE}
//   (:Article {url, article_id, title, published_at, source})
//   (:Entity)-[:MENTIONED_IN {count}]->(:Article)
//   (:Entity)-[:CO_OCCURS_WITH {weight}]-(:Entity)   // undirected
// ============================================================

// ---- Uniqueness constraints (business keys) ----
CREATE CONSTRAINT entity_canonical_id_unique IF NOT EXISTS
FOR (n:Entity) REQUIRE n.canonical_id IS UNIQUE;

CREATE CONSTRAINT article_url_unique IF NOT EXISTS
FOR (n:Article) REQUIRE n.url IS UNIQUE;

// ---- Secondary lookup indexes (filtering / sorting) ----
CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.type);
CREATE INDEX entity_name_idx IF NOT EXISTS FOR (n:Entity) ON (n.name);
CREATE INDEX article_published_at_idx IF NOT EXISTS FOR (n:Article) ON (n.published_at);
CREATE INDEX article_source_idx IF NOT EXISTS FOR (n:Article) ON (n.source);

// ---- Verify ----
SHOW CONSTRAINTS;
SHOW INDEXES;
