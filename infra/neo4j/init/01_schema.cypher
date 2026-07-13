// ============================================================
// OSINT Knowledge Graph - Neo4j schema bootstrap
// Apply manually:
//   cat 01_schema.cypher | cypher-shell -u neo4j -p <password>
// Constraints create a backing index -> MATCH by key is O(1).
// ============================================================

// ---- Uniqueness constraints (business keys) ----
CREATE CONSTRAINT person_person_name_unique IF NOT EXISTS
FOR (n:Person) REQUIRE n.person_name IS UNIQUE;

CREATE CONSTRAINT organization_org_name_unique IF NOT EXISTS
FOR (n:Organization) REQUIRE n.org_name IS UNIQUE;

CREATE CONSTRAINT location_location_name_unique IF NOT EXISTS
FOR (n:Location) REQUIRE n.location_name IS UNIQUE;

CREATE CONSTRAINT event_event_id_unique IF NOT EXISTS
FOR (n:Event) REQUIRE n.event_id IS UNIQUE;

CREATE CONSTRAINT article_article_url_unique IF NOT EXISTS
FOR (n:Article) REQUIRE n.article_url IS UNIQUE;

// ---- Secondary lookup indexes (filtering / sorting) ----
CREATE INDEX article_published_at_idx IF NOT EXISTS FOR (n:Article) ON (n.published_at);
CREATE INDEX article_source_idx IF NOT EXISTS FOR (n:Article) ON (n.source);
CREATE INDEX event_occurred_at_idx IF NOT EXISTS FOR (n:Event) ON (n.occurred_at);
CREATE INDEX person_canonical_id_idx IF NOT EXISTS FOR (n:Person) ON (n.canonical_id);
CREATE INDEX organization_canonical_id_idx IF NOT EXISTS FOR (n:Organization) ON (n.canonical_id);

// ---- Verify ----
SHOW CONSTRAINTS;
SHOW INDEXES;
