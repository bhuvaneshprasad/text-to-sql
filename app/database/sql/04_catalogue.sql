BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE SCHEMA IF NOT EXISTS text_to_sql_catalog;

-- ============================================================================
-- 1. Catalogue tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS text_to_sql_catalog.schema_catalog (
    id BIGSERIAL PRIMARY KEY,

    object_type TEXT NOT NULL
        CHECK (object_type IN ('table', 'column')),

    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT,

    data_type TEXT,
    is_nullable BOOLEAN,
    is_primary_key BOOLEAN,

    description TEXT,
    search_text TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        (object_type = 'table' AND column_name IS NULL)
        OR
        (object_type = 'column' AND column_name IS NOT NULL)
    )
);


CREATE TABLE IF NOT EXISTS text_to_sql_catalog.relationship_catalog (
    id BIGSERIAL PRIMARY KEY,

    constraint_name TEXT NOT NULL,

    source_schema TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_column TEXT NOT NULL,

    target_schema TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_column TEXT NOT NULL,

    relationship_type TEXT NOT NULL DEFAULT 'many-to-one'
        CHECK (
            relationship_type IN (
                'one-to-one',
                'one-to-many',
                'many-to-one',
                'many-to-many'
            )
        ),

    description TEXT,
    search_text TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS text_to_sql_catalog.json_path_catalog (
    id BIGSERIAL PRIMARY KEY,

    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,

    json_path TEXT NOT NULL,
    parent_path TEXT,
    key_name TEXT,

    observed_types TEXT[] NOT NULL DEFAULT '{}',

    is_leaf BOOLEAN NOT NULL,
    contains_array BOOLEAN NOT NULL DEFAULT FALSE,

    document_count BIGINT NOT NULL DEFAULT 0
        CHECK (document_count >= 0),

    occurrence_count BIGINT NOT NULL DEFAULT 0
        CHECK (occurrence_count >= 0),

    coverage_ratio NUMERIC(10, 6)
        CHECK (
            coverage_ratio IS NULL
            OR (
                coverage_ratio >= 0
                AND coverage_ratio <= 1
            )
        ),

    distinct_value_count BIGINT
        CHECK (
            distinct_value_count IS NULL
            OR distinct_value_count >= 0
        ),

    example_value TEXT,
    description TEXT,
    search_text TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS text_to_sql_catalog.value_catalog (
    id BIGSERIAL PRIMARY KEY,

    source_kind TEXT NOT NULL
        CHECK (source_kind IN ('column', 'json_path')),

    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,

    json_path TEXT,

    original_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    search_text TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        (source_kind = 'column' AND json_path IS NULL)
        OR
        (source_kind = 'json_path' AND json_path IS NOT NULL)
    )
);


CREATE TABLE IF NOT EXISTS text_to_sql_catalog.value_catalog_config (
    id BIGSERIAL PRIMARY KEY,

    source_kind TEXT NOT NULL
        CHECK (source_kind IN ('column', 'json_path')),

    schema_name TEXT NOT NULL DEFAULT 'public',
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,

    json_path TEXT,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    max_distinct_values INTEGER NOT NULL DEFAULT 200
        CHECK (max_distinct_values > 0),

    max_value_length INTEGER NOT NULL DEFAULT 200
        CHECK (max_value_length > 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        (source_kind = 'column' AND json_path IS NULL)
        OR
        (source_kind = 'json_path' AND json_path IS NOT NULL)
    )
);

-- Make the script compatible with either earlier table variant.
ALTER TABLE text_to_sql_catalog.value_catalog_config
    ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE text_to_sql_catalog.value_catalog_config
    ADD COLUMN IF NOT EXISTS max_value_length INTEGER NOT NULL DEFAULT 200;

-- ============================================================================
-- 2. Catalogue schema, table, and column descriptions
-- ============================================================================

COMMENT ON SCHEMA text_to_sql_catalog IS
'Internal metadata catalogue used by the Text-to-SQL application to identify approved database relations, columns, joins, structured JSON/HSTORE paths, and searchable values. This schema does not contain business transactions and should not be exposed as part of the user-queryable business schema.';

COMMENT ON TABLE text_to_sql_catalog.schema_catalog IS
'Catalogue of approved Text-to-SQL tables, views, and columns. Each row represents either one relation or one column and stores database metadata, business descriptions, key flags, and normalized search text used to match natural-language questions to relevant schema objects.';

COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.id IS
'Surrogate primary key for the catalogue row.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.object_type IS
'Type of catalogued schema object. Allowed values are table and column. Views are represented using object_type table because they are relation-level objects exposed to the Text-to-SQL assistant.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.schema_name IS
'PostgreSQL schema containing the catalogued relation, such as public.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.table_name IS
'Name of the approved source table or view exposed to the Text-to-SQL assistant.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.column_name IS
'Name of the source column. NULL for relation-level rows where object_type is table.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.data_type IS
'PostgreSQL display type of the source column, including relevant modifiers such as character length, numeric precision, arrays, enums, JSONB, or HSTORE. NULL for relation-level rows.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.is_nullable IS
'Whether the source column accepts NULL values. NULL for relation-level rows.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.is_primary_key IS
'Whether the source column participates in the relation primary key. Composite primary keys produce true for each participating column. NULL for relation-level rows.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.description IS
'Business-oriented description copied from PostgreSQL COMMENT metadata on the source relation or column. Used by the agent to understand meaning, relationships, calculation rules, and structured-value contents.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.search_text IS
'Lowercase normalized retrieval text combining relation names, column names, descriptions, data types, and selected business synonyms. Intended for exact, normalized, and trigram schema matching without embeddings.';
COMMENT ON COLUMN text_to_sql_catalog.schema_catalog.created_at IS
'Timestamp when the catalogue row was generated during bootstrap.';

COMMENT ON TABLE text_to_sql_catalog.relationship_catalog IS
'Catalogue of approved foreign-key relationships between Text-to-SQL business tables. Each row represents one source-column to target-column mapping. Composite foreign keys produce multiple rows sharing the same constraint_name and must be joined using every mapped column.';

COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.id IS
'Surrogate primary key for the relationship catalogue row.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.constraint_name IS
'PostgreSQL foreign-key constraint name. Rows with the same constraint_name may represent the column pairs of one composite foreign key.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.source_schema IS
'Schema containing the referencing or child relation.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.source_table IS
'Referencing or child table containing the foreign-key column.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.source_column IS
'Column in the child table that references the target column.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.target_schema IS
'Schema containing the referenced or parent relation.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.target_table IS
'Referenced or parent table.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.target_column IS
'Referenced parent-table column used in the join condition.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.relationship_type IS
'Logical relationship direction from the source row to the target row. The generated catalogue currently uses many-to-one for foreign keys. Allowed values are one-to-one, one-to-many, many-to-one, and many-to-many.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.description IS
'Human-readable join guidance describing the source and target columns and warning when all column pairs of a composite foreign key are required.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.search_text IS
'Lowercase normalized retrieval text combining source and target relation names, columns, and composite-key guidance for relationship lookup.';
COMMENT ON COLUMN text_to_sql_catalog.relationship_catalog.created_at IS
'Timestamp when the relationship catalogue row was generated during bootstrap.';

COMMENT ON TABLE text_to_sql_catalog.json_path_catalog IS
'Catalogue of observed paths inside approved JSON, JSONB, and HSTORE columns. Paths are discovered from existing source data and summarize key names, observed scalar or container types, array traversal, coverage, cardinality, and one representative value.';

COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.id IS
'Surrogate primary key for the structured-path catalogue row.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.schema_name IS
'Schema containing the source relation with the structured column.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.table_name IS
'Approved source table or view containing the JSON, JSONB, or HSTORE column.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.column_name IS
'Source JSON, JSONB, or HSTORE column containing the discovered path.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.json_path IS
'Canonical discovered path beginning at $. Object keys are represented as quoted JSON path components and array elements are represented with [*] instead of individual indexes.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.parent_path IS
'Immediate parent path of json_path. NULL only when no parent path is recorded.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.key_name IS
'Object key represented by the path. NULL for array-element paths such as $[*].';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.observed_types IS
'Distinct JSON value types observed at this path, such as string, number, boolean, object, array, or null.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.is_leaf IS
'Whether at least one observed value at the path is a scalar or JSON null rather than an object or array. Leaf paths are candidates for value catalogue population.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.contains_array IS
'Whether traversal from the structured document root to this path passes through an array.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.document_count IS
'Number of source documents in which the path was observed at least once.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.occurrence_count IS
'Total number of occurrences of the path across all source documents. This can exceed document_count when the path appears in multiple array elements within one document.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.coverage_ratio IS
'Fraction of non-NULL source documents containing the path, calculated as document_count divided by the total structured-document count for that source column.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.distinct_value_count IS
'Number of distinct non-NULL scalar text values observed at the path. Container-only paths may have zero or NULL scalar cardinality.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.example_value IS
'One representative observed scalar value for the path. Intended only as a retrieval hint, not as a complete domain definition.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.description IS
'Generated explanation identifying the structured source column, discovered path, and key name.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.search_text IS
'Lowercase normalized retrieval text combining source relation, structured column, key name, JSON path, source-column description, and a representative observed value.';
COMMENT ON COLUMN text_to_sql_catalog.json_path_catalog.created_at IS
'Timestamp when the structured-path catalogue row was generated during bootstrap.';

COMMENT ON TABLE text_to_sql_catalog.value_catalog IS
'Catalogue of selected low-cardinality values observed in approved relational columns and structured JSON/HSTORE paths. Values are normalized for exact and trigram matching so user wording can be resolved to database values without embeddings.';

COMMENT ON COLUMN text_to_sql_catalog.value_catalog.id IS
'Surrogate primary key for the searchable value row.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.source_kind IS
'Location type of the value. Allowed values are column for ordinary relational columns and json_path for values extracted from JSON, JSONB, or HSTORE paths.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.schema_name IS
'Schema containing the source relation.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.table_name IS
'Approved source table or view containing the value.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.column_name IS
'Source relational or structured column containing the value.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.json_path IS
'Structured path containing the value when source_kind is json_path. NULL when source_kind is column.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.original_value IS
'Original source value converted to text and preserved for use in SQL predicates or response grounding.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.normalized_value IS
'Lowercase whitespace-normalized representation of original_value used for exact and fuzzy matching.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.search_text IS
'Lowercase normalized retrieval text combining source relation, column, optional structured path and key, and the observed value.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog.created_at IS
'Timestamp when the searchable value row was generated during bootstrap.';

COMMENT ON TABLE text_to_sql_catalog.value_catalog_config IS
'Configuration describing which relational columns and structured paths were eligible for value catalogue population during bootstrap. It records enablement and cardinality or length limits for each selected source.';

COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.id IS
'Surrogate primary key for the value-source configuration row.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.source_kind IS
'Configured source type. Allowed values are column and json_path.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.schema_name IS
'Schema containing the configured source relation.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.table_name IS
'Approved source table or view considered for value extraction.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.column_name IS
'Source relational or structured column considered for value extraction.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.json_path IS
'Configured structured path when source_kind is json_path. NULL when source_kind is column.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.enabled IS
'Whether value extraction is enabled for this source configuration.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.max_distinct_values IS
'Maximum allowed number of distinct values for this source to qualify for value catalogue population.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.max_value_length IS
'Maximum allowed character length of an individual value copied into value_catalog.';
COMMENT ON COLUMN text_to_sql_catalog.value_catalog_config.created_at IS
'Timestamp when the value-source configuration row was generated during bootstrap.';

-- ============================================================================
-- 3. Constraints and indexes
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_schema_catalog_object
ON text_to_sql_catalog.schema_catalog (
    object_type,
    schema_name,
    table_name,
    COALESCE(column_name, '')
);

CREATE INDEX IF NOT EXISTS idx_schema_catalog_table
ON text_to_sql_catalog.schema_catalog (
    schema_name,
    table_name
);

CREATE INDEX IF NOT EXISTS idx_schema_catalog_column
ON text_to_sql_catalog.schema_catalog (
    schema_name,
    table_name,
    column_name
);

CREATE INDEX IF NOT EXISTS idx_schema_catalog_search_trgm
ON text_to_sql_catalog.schema_catalog
USING GIN (search_text gin_trgm_ops);


CREATE UNIQUE INDEX IF NOT EXISTS uq_relationship_catalog
ON text_to_sql_catalog.relationship_catalog (
    constraint_name,
    source_schema,
    source_table,
    source_column,
    target_schema,
    target_table,
    target_column
);

CREATE INDEX IF NOT EXISTS idx_relationship_catalog_source
ON text_to_sql_catalog.relationship_catalog (
    source_schema,
    source_table
);

CREATE INDEX IF NOT EXISTS idx_relationship_catalog_target
ON text_to_sql_catalog.relationship_catalog (
    target_schema,
    target_table
);

CREATE INDEX IF NOT EXISTS idx_relationship_catalog_search_trgm
ON text_to_sql_catalog.relationship_catalog
USING GIN (search_text gin_trgm_ops);


CREATE UNIQUE INDEX IF NOT EXISTS uq_json_path_catalog
ON text_to_sql_catalog.json_path_catalog (
    schema_name,
    table_name,
    column_name,
    json_path
);

CREATE INDEX IF NOT EXISTS idx_json_path_catalog_source
ON text_to_sql_catalog.json_path_catalog (
    schema_name,
    table_name,
    column_name
);

CREATE INDEX IF NOT EXISTS idx_json_path_catalog_key
ON text_to_sql_catalog.json_path_catalog (
    key_name
);

CREATE INDEX IF NOT EXISTS idx_json_path_catalog_leaf
ON text_to_sql_catalog.json_path_catalog (
    schema_name,
    table_name,
    column_name,
    is_leaf
);

CREATE INDEX IF NOT EXISTS idx_json_path_catalog_search_trgm
ON text_to_sql_catalog.json_path_catalog
USING GIN (search_text gin_trgm_ops);


CREATE UNIQUE INDEX IF NOT EXISTS uq_value_catalog
ON text_to_sql_catalog.value_catalog (
    source_kind,
    schema_name,
    table_name,
    column_name,
    COALESCE(json_path, ''),
    normalized_value
);

CREATE INDEX IF NOT EXISTS idx_value_catalog_source
ON text_to_sql_catalog.value_catalog (
    source_kind,
    schema_name,
    table_name,
    column_name
);

CREATE INDEX IF NOT EXISTS idx_value_catalog_json_path
ON text_to_sql_catalog.value_catalog (
    schema_name,
    table_name,
    column_name,
    json_path
)
WHERE source_kind = 'json_path';

CREATE INDEX IF NOT EXISTS idx_value_catalog_normalized
ON text_to_sql_catalog.value_catalog (
    normalized_value
);

CREATE INDEX IF NOT EXISTS idx_value_catalog_search_trgm
ON text_to_sql_catalog.value_catalog
USING GIN (search_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_value_catalog_normalized_trgm
ON text_to_sql_catalog.value_catalog
USING GIN (normalized_value gin_trgm_ops);


CREATE UNIQUE INDEX IF NOT EXISTS uq_value_catalog_config
ON text_to_sql_catalog.value_catalog_config (
    source_kind,
    schema_name,
    table_name,
    column_name,
    COALESCE(json_path, '')
);

CREATE INDEX IF NOT EXISTS idx_value_catalog_config_enabled
ON text_to_sql_catalog.value_catalog_config (
    enabled,
    source_kind
);

-- ============================================================================
-- 4. One-time helper functions
-- ============================================================================

CREATE OR REPLACE FUNCTION text_to_sql_catalog._bootstrap_normalize_text(
    input_text TEXT
)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $function$
    SELECT LOWER(
        REGEXP_REPLACE(
            BTRIM(COALESCE(input_text, '')),
            '\s+',
            ' ',
            'g'
        )
    );
$function$;


CREATE OR REPLACE FUNCTION text_to_sql_catalog._bootstrap_discover_json_paths(
    document JSONB
)
RETURNS TABLE (
    json_path TEXT,
    parent_path TEXT,
    key_name TEXT,
    observed_type TEXT,
    is_leaf BOOLEAN,
    contains_array BOOLEAN,
    scalar_value TEXT
)
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $function$
    WITH RECURSIVE json_walk (
        json_path,
        parent_path,
        key_name,
        node,
        contains_array
    ) AS (
        SELECT
            '$'::TEXT,
            NULL::TEXT,
            NULL::TEXT,
            document,
            FALSE
        WHERE document IS NOT NULL

        UNION ALL

        SELECT
            CASE child.edge_type
                WHEN 'key' THEN
                    parent.json_path
                    || '.'
                    || TO_JSON(child.key_name)::TEXT
                ELSE
                    parent.json_path || '[*]'
            END,
            parent.json_path,
            child.key_name,
            child.node,
            parent.contains_array OR child.edge_type = 'array'
        FROM json_walk AS parent
        CROSS JOIN LATERAL (
            SELECT
                'key'::TEXT AS edge_type,
                object_item.key AS key_name,
                object_item.value AS node
            FROM JSONB_EACH(
                CASE
                    WHEN JSONB_TYPEOF(parent.node) = 'object'
                        THEN parent.node
                    ELSE '{}'::JSONB
                END
            ) AS object_item

            UNION ALL

            SELECT
                'array'::TEXT AS edge_type,
                NULL::TEXT AS key_name,
                array_item.value AS node
            FROM JSONB_ARRAY_ELEMENTS(
                CASE
                    WHEN JSONB_TYPEOF(parent.node) = 'array'
                        THEN parent.node
                    ELSE '[]'::JSONB
                END
            ) AS array_item
        ) AS child
    )
    SELECT
        json_path,
        parent_path,
        key_name,
        JSONB_TYPEOF(node) AS observed_type,
        JSONB_TYPEOF(node) NOT IN ('object', 'array') AS is_leaf,
        contains_array,
        CASE
            WHEN JSONB_TYPEOF(node) IN ('string', 'number', 'boolean')
                THEN node #>> '{}'
            ELSE NULL
        END AS scalar_value
    FROM json_walk
    WHERE json_path <> '$';
$function$;

-- ============================================================================
-- 5. Approved relation allow-list
--
-- collect_values controls whether ordinary relational values are sampled.
-- JSON/HSTORE path discovery is controlled separately by physical data type.
-- ============================================================================

CREATE TEMPORARY TABLE allowed_relation_stage (
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    relation_kind TEXT NOT NULL
        CHECK (relation_kind IN ('table', 'view')),
    collect_values BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (schema_name, table_name)
) ON COMMIT DROP;

INSERT INTO allowed_relation_stage (
    schema_name,
    table_name,
    relation_kind,
    collect_values
)
VALUES
    ('public', 'customers', 'table', TRUE),
    ('public', 'addresses', 'table', TRUE),
    ('public', 'categories', 'table', TRUE),
    ('public', 'suppliers', 'table', TRUE),
    ('public', 'products', 'table', TRUE),
    ('public', 'inventory', 'table', TRUE),
    ('public', 'orders', 'table', TRUE),
    ('public', 'order_items', 'table', TRUE),
    ('public', 'reviews', 'table', TRUE),
    ('public', 'v_customer_summary', 'view', TRUE),
    ('public', 'v_product_inventory', 'view', TRUE),
    ('public', 'v_top_selling_products', 'view', TRUE);

-- ============================================================================
-- 6. Clear existing catalogue data
-- ============================================================================

TRUNCATE TABLE
    text_to_sql_catalog.value_catalog,
    text_to_sql_catalog.value_catalog_config,
    text_to_sql_catalog.json_path_catalog,
    text_to_sql_catalog.relationship_catalog,
    text_to_sql_catalog.schema_catalog
RESTART IDENTITY;

-- ============================================================================
-- 7. Populate approved tables/views and columns
-- ============================================================================

INSERT INTO text_to_sql_catalog.schema_catalog (
    object_type,
    schema_name,
    table_name,
    column_name,
    data_type,
    is_nullable,
    is_primary_key,
    description,
    search_text
)
SELECT
    'table',
    namespace.nspname,
    relation.relname,
    NULL,
    NULL,
    NULL,
    NULL,
    OBJ_DESCRIPTION(relation.oid, 'pg_class'),
    text_to_sql_catalog._bootstrap_normalize_text(
        CONCAT_WS(
            ' ',
            relation.relname,
            REPLACE(relation.relname, '_', ' '),
            OBJ_DESCRIPTION(relation.oid, 'pg_class')
        )
    )
FROM pg_class AS relation
JOIN pg_namespace AS namespace
    ON namespace.oid = relation.relnamespace
JOIN allowed_relation_stage AS allowed
    ON allowed.schema_name = namespace.nspname
   AND allowed.table_name = relation.relname
WHERE relation.relkind IN ('r', 'p', 'v');


INSERT INTO text_to_sql_catalog.schema_catalog (
    object_type,
    schema_name,
    table_name,
    column_name,
    data_type,
    is_nullable,
    is_primary_key,
    description,
    search_text
)
SELECT
    'column',
    namespace.nspname,
    relation.relname,
    attribute.attname,
    FORMAT_TYPE(attribute.atttypid, attribute.atttypmod),
    NOT attribute.attnotnull,
    EXISTS (
        SELECT 1
        FROM pg_index AS index_metadata
        WHERE index_metadata.indrelid = relation.oid
          AND index_metadata.indisprimary
          AND attribute.attnum = ANY(index_metadata.indkey)
    ),
    COL_DESCRIPTION(relation.oid, attribute.attnum),
    text_to_sql_catalog._bootstrap_normalize_text(
        CONCAT_WS(
            ' ',
            relation.relname,
            REPLACE(relation.relname, '_', ' '),
            attribute.attname,
            REPLACE(attribute.attname, '_', ' '),
            FORMAT_TYPE(attribute.atttypid, attribute.atttypmod),
            COL_DESCRIPTION(relation.oid, attribute.attnum)
        )
    )
FROM pg_attribute AS attribute
JOIN pg_class AS relation
    ON relation.oid = attribute.attrelid
JOIN pg_namespace AS namespace
    ON namespace.oid = relation.relnamespace
JOIN allowed_relation_stage AS allowed
    ON allowed.schema_name = namespace.nspname
   AND allowed.table_name = relation.relname
WHERE relation.relkind IN ('r', 'p', 'v')
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped;

-- Add business terms without requiring a separate alias table.
UPDATE text_to_sql_catalog.schema_catalog AS catalogue
SET search_text = text_to_sql_catalog._bootstrap_normalize_text(
    CONCAT_WS(
        ' ',
        catalogue.search_text,
        CASE catalogue.table_name
            WHEN 'customers'
                THEN 'customer customers client clients buyer buyers shopper shoppers user users'
            WHEN 'addresses'
                THEN 'address addresses shipping billing location locations'
            WHEN 'categories'
                THEN 'category categories product category taxonomy classification'
            WHEN 'suppliers'
                THEN 'supplier suppliers vendor vendors manufacturer manufacturers'
            WHEN 'products'
                THEN 'product products item items goods merchandise catalogue catalog'
            WHEN 'inventory'
                THEN 'inventory stock warehouse availability available reserved reorder'
            WHEN 'orders'
                THEN 'order orders purchase purchases transaction transactions sale sales checkout'
            WHEN 'order_items'
                THEN 'order item order items line item line items purchased products units sold'
            WHEN 'reviews'
                THEN 'review reviews rating ratings feedback'
            WHEN 'v_customer_summary'
                THEN 'customer summary customer analytics customer metrics spend lifetime value'
            WHEN 'v_product_inventory'
                THEN 'product inventory stock availability stock status'
            WHEN 'v_top_selling_products'
                THEN 'top selling products best sellers product sales product revenue'
            ELSE NULL
        END,
        CASE
            WHEN catalogue.object_type = 'column'
            THEN CASE catalogue.table_name || '.' || catalogue.column_name
                WHEN 'customers.first_name'
                    THEN 'customer first name given name'
                WHEN 'customers.last_name'
                    THEN 'customer last name surname family name'
                WHEN 'v_customer_summary.full_name'
                    THEN 'customer name full name'
                WHEN 'categories.name'
                    THEN 'category name'
                WHEN 'suppliers.company_name'
                    THEN 'supplier name vendor name company'
                WHEN 'products.name'
                    THEN 'product name item name'
                WHEN 'products.price'
                    THEN 'selling price product price unit price'
                WHEN 'products.cost_price'
                    THEN 'cost price product cost'
                WHEN 'products.rating_avg'
                    THEN 'average product rating rating score'
                WHEN 'inventory.quantity'
                    THEN 'stock quantity total stock'
                WHEN 'inventory.reserved_quantity'
                    THEN 'reserved stock reserved quantity'
                WHEN 'orders.status'
                    THEN 'order status order state'
                WHEN 'orders.total_amount'
                    THEN 'order total order value sales revenue customer spend'
                WHEN 'orders.created_at'
                    THEN 'order date purchase date transaction date'
                WHEN 'order_items.quantity'
                    THEN 'units sold item quantity'
                WHEN 'order_items.total_price'
                    THEN 'line total line revenue item sales'
                WHEN 'reviews.rating'
                    THEN 'customer rating review score stars'
                WHEN 'v_customer_summary.total_orders'
                    THEN 'order count number of orders'
                WHEN 'v_customer_summary.lifetime_value'
                    THEN 'customer lifetime value total spent customer spend'
                WHEN 'v_customer_summary.avg_order_value'
                    THEN 'average order value average spend'
                WHEN 'v_product_inventory.available_stock'
                    THEN 'available stock available inventory'
                WHEN 'v_product_inventory.stock_status'
                    THEN 'stock status in stock low stock out of stock'
                WHEN 'v_top_selling_products.units_sold'
                    THEN 'units sold quantity sold'
                WHEN 'v_top_selling_products.revenue'
                    THEN 'product revenue product sales'
                ELSE NULL
            END
            ELSE NULL
        END
    )
);

-- ============================================================================
-- 8. Populate foreign-key relationships
--
-- A relationship is catalogued only when both source and target relations are
-- in the allow-list. Composite foreign keys produce one row per column pair
-- under the same constraint_name.
-- ============================================================================

INSERT INTO text_to_sql_catalog.relationship_catalog (
    constraint_name,
    source_schema,
    source_table,
    source_column,
    target_schema,
    target_table,
    target_column,
    relationship_type,
    description,
    search_text
)
SELECT
    foreign_key.conname,
    source_namespace.nspname,
    source_relation.relname,
    source_attribute.attname,
    target_namespace.nspname,
    target_relation.relname,
    target_attribute.attname,
    'many-to-one',
    CONCAT(
        source_relation.relname,
        '.',
        source_attribute.attname,
        ' references ',
        target_relation.relname,
        '.',
        target_attribute.attname,
        CASE
            WHEN CARDINALITY(foreign_key.conkey) > 1
                THEN CONCAT(
                    ' as part of composite foreign key ',
                    foreign_key.conname,
                    '; all ',
                    CARDINALITY(foreign_key.conkey),
                    ' column pairs must be used in the join'
                )
            ELSE ''
        END
    ),
    text_to_sql_catalog._bootstrap_normalize_text(
        CONCAT_WS(
            ' ',
            source_relation.relname,
            REPLACE(source_relation.relname, '_', ' '),
            source_attribute.attname,
            REPLACE(source_attribute.attname, '_', ' '),
            target_relation.relname,
            REPLACE(target_relation.relname, '_', ' '),
            target_attribute.attname,
            REPLACE(target_attribute.attname, '_', ' '),
            CASE
                WHEN CARDINALITY(foreign_key.conkey) > 1
                    THEN 'composite foreign key use all join columns'
                ELSE NULL
            END
        )
    )
FROM pg_constraint AS foreign_key
JOIN pg_class AS source_relation
    ON source_relation.oid = foreign_key.conrelid
JOIN pg_namespace AS source_namespace
    ON source_namespace.oid = source_relation.relnamespace
JOIN allowed_relation_stage AS allowed_source
    ON allowed_source.schema_name = source_namespace.nspname
   AND allowed_source.table_name = source_relation.relname
JOIN pg_class AS target_relation
    ON target_relation.oid = foreign_key.confrelid
JOIN pg_namespace AS target_namespace
    ON target_namespace.oid = target_relation.relnamespace
JOIN allowed_relation_stage AS allowed_target
    ON allowed_target.schema_name = target_namespace.nspname
   AND allowed_target.table_name = target_relation.relname
JOIN LATERAL UNNEST(
    foreign_key.conkey,
    foreign_key.confkey
) AS key_mapping(
    source_attribute_number,
    target_attribute_number
)
    ON TRUE
JOIN pg_attribute AS source_attribute
    ON source_attribute.attrelid = source_relation.oid
   AND source_attribute.attnum = key_mapping.source_attribute_number
JOIN pg_attribute AS target_attribute
    ON target_attribute.attrelid = target_relation.oid
   AND target_attribute.attnum = key_mapping.target_attribute_number
WHERE foreign_key.contype = 'f';

-- ============================================================================
-- 9. Discover JSON/JSONB/HSTORE keys and paths
--
-- HSTORE values are converted to JSONB only for catalogue discovery.
-- Array indexes are represented using [*], not individual array positions.
-- ============================================================================

CREATE TEMPORARY TABLE json_source_stage (
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    total_documents BIGINT NOT NULL
) ON COMMIT DROP;

CREATE TEMPORARY TABLE json_discovery_stage (
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    document_number BIGINT NOT NULL,

    json_path TEXT NOT NULL,
    parent_path TEXT,
    key_name TEXT,
    observed_type TEXT NOT NULL,
    is_leaf BOOLEAN NOT NULL,
    contains_array BOOLEAN NOT NULL,
    scalar_value TEXT
) ON COMMIT DROP;


DO $bootstrap_json$
DECLARE
    structured_column RECORD;
    structured_expression TEXT;
BEGIN
    FOR structured_column IN
        SELECT
            columns.table_schema,
            columns.table_name,
            columns.column_name,
            columns.data_type,
            columns.udt_name
        FROM information_schema.columns AS columns
        JOIN allowed_relation_stage AS allowed
            ON allowed.schema_name = columns.table_schema
           AND allowed.table_name = columns.table_name
        WHERE (
            columns.data_type IN ('json', 'jsonb')
            OR columns.udt_name = 'hstore'
        )
        ORDER BY
            columns.table_name,
            columns.ordinal_position
    LOOP
        structured_expression := CASE
            WHEN structured_column.udt_name = 'hstore'
                THEN FORMAT(
                    'hstore_to_jsonb(%I)',
                    structured_column.column_name
                )
            ELSE FORMAT(
                '%I::JSONB',
                structured_column.column_name
            )
        END;

        EXECUTE FORMAT(
            $sql$
            INSERT INTO json_source_stage (
                schema_name,
                table_name,
                column_name,
                total_documents
            )
            SELECT
                %L,
                %L,
                %L,
                COUNT(*)
            FROM %I.%I
            WHERE %I IS NOT NULL
            $sql$,
            structured_column.table_schema,
            structured_column.table_name,
            structured_column.column_name,
            structured_column.table_schema,
            structured_column.table_name,
            structured_column.column_name
        );

        EXECUTE FORMAT(
            $sql$
            INSERT INTO json_discovery_stage (
                schema_name,
                table_name,
                column_name,
                document_number,
                json_path,
                parent_path,
                key_name,
                observed_type,
                is_leaf,
                contains_array,
                scalar_value
            )
            SELECT
                %L,
                %L,
                %L,
                source_document.document_number,
                discovered.json_path,
                discovered.parent_path,
                discovered.key_name,
                discovered.observed_type,
                discovered.is_leaf,
                discovered.contains_array,
                discovered.scalar_value
            FROM (
                SELECT
                    ROW_NUMBER() OVER () AS document_number,
                    %s AS document
                FROM %I.%I
                WHERE %I IS NOT NULL
            ) AS source_document
            CROSS JOIN LATERAL
                text_to_sql_catalog._bootstrap_discover_json_paths(
                    source_document.document
                ) AS discovered
            $sql$,
            structured_column.table_schema,
            structured_column.table_name,
            structured_column.column_name,
            structured_expression,
            structured_column.table_schema,
            structured_column.table_name,
            structured_column.column_name
        );
    END LOOP;
END;
$bootstrap_json$;


INSERT INTO text_to_sql_catalog.json_path_catalog (
    schema_name,
    table_name,
    column_name,
    json_path,
    parent_path,
    key_name,
    observed_types,
    is_leaf,
    contains_array,
    document_count,
    occurrence_count,
    coverage_ratio,
    distinct_value_count,
    example_value,
    description,
    search_text
)
SELECT
    discovered.schema_name,
    discovered.table_name,
    discovered.column_name,
    discovered.json_path,
    discovered.parent_path,
    discovered.key_name,

    ARRAY_AGG(
        DISTINCT discovered.observed_type
        ORDER BY discovered.observed_type
    ),

    BOOL_OR(discovered.is_leaf),
    BOOL_OR(discovered.contains_array),

    COUNT(DISTINCT discovered.document_number),
    COUNT(*),

    ROUND(
        COUNT(DISTINCT discovered.document_number)::NUMERIC
        / NULLIF(source.total_documents, 0),
        6
    ),

    COUNT(DISTINCT discovered.scalar_value)
        FILTER (WHERE discovered.scalar_value IS NOT NULL),

    MIN(discovered.scalar_value)
        FILTER (WHERE discovered.scalar_value IS NOT NULL),

    CONCAT(
        'Structured path ',
        discovered.json_path,
        ' in ',
        discovered.table_name,
        '.',
        discovered.column_name,
        CASE
            WHEN discovered.key_name IS NOT NULL
                THEN CONCAT('; key ', discovered.key_name)
            ELSE ''
        END
    ),

    text_to_sql_catalog._bootstrap_normalize_text(
        CONCAT_WS(
            ' ',
            discovered.table_name,
            REPLACE(discovered.table_name, '_', ' '),
            discovered.column_name,
            REPLACE(discovered.column_name, '_', ' '),
            discovered.key_name,
            REPLACE(COALESCE(discovered.key_name, ''), '_', ' '),
            discovered.json_path,
            REGEXP_REPLACE(
                discovered.json_path,
                '[^[:alnum:]_]+',
                ' ',
                'g'
            ),
            physical_column.description,
            MIN(discovered.scalar_value)
                FILTER (WHERE discovered.scalar_value IS NOT NULL)
        )
    )
FROM json_discovery_stage AS discovered
JOIN json_source_stage AS source
    ON source.schema_name = discovered.schema_name
   AND source.table_name = discovered.table_name
   AND source.column_name = discovered.column_name
LEFT JOIN text_to_sql_catalog.schema_catalog AS physical_column
    ON physical_column.object_type = 'column'
   AND physical_column.schema_name = discovered.schema_name
   AND physical_column.table_name = discovered.table_name
   AND physical_column.column_name = discovered.column_name
GROUP BY
    discovered.schema_name,
    discovered.table_name,
    discovered.column_name,
    discovered.json_path,
    discovered.parent_path,
    discovered.key_name,
    source.total_documents,
    physical_column.description;

-- ============================================================================
-- 10. Configure and populate low-cardinality structured values
--
-- Image URLs/alt text are intentionally not copied into value_catalog because
-- they add retrieval noise. Their paths still remain in json_path_catalog.
-- ============================================================================

INSERT INTO text_to_sql_catalog.value_catalog_config (
    source_kind,
    schema_name,
    table_name,
    column_name,
    json_path,
    enabled,
    max_distinct_values,
    max_value_length
)
SELECT
    'json_path',
    schema_name,
    table_name,
    column_name,
    json_path,
    TRUE,
    200,
    200
FROM text_to_sql_catalog.json_path_catalog
WHERE is_leaf = TRUE
  AND distinct_value_count BETWEEN 1 AND 200
  AND observed_types
      && ARRAY['string', 'number', 'boolean']::TEXT[]
  AND column_name <> 'images';


INSERT INTO text_to_sql_catalog.value_catalog (
    source_kind,
    schema_name,
    table_name,
    column_name,
    json_path,
    original_value,
    normalized_value,
    search_text
)
SELECT DISTINCT
    'json_path',
    discovered.schema_name,
    discovered.table_name,
    discovered.column_name,
    discovered.json_path,
    discovered.scalar_value,
    text_to_sql_catalog._bootstrap_normalize_text(
        discovered.scalar_value
    ),
    text_to_sql_catalog._bootstrap_normalize_text(
        CONCAT_WS(
            ' ',
            discovered.table_name,
            REPLACE(discovered.table_name, '_', ' '),
            discovered.column_name,
            REPLACE(discovered.column_name, '_', ' '),
            discovered.key_name,
            REPLACE(COALESCE(discovered.key_name, ''), '_', ' '),
            discovered.json_path,
            REGEXP_REPLACE(
                discovered.json_path,
                '[^[:alnum:]_]+',
                ' ',
                'g'
            ),
            discovered.scalar_value
        )
    )
FROM json_discovery_stage AS discovered
JOIN text_to_sql_catalog.value_catalog_config AS config
    ON config.source_kind = 'json_path'
   AND config.schema_name = discovered.schema_name
   AND config.table_name = discovered.table_name
   AND config.column_name = discovered.column_name
   AND config.json_path = discovered.json_path
   AND config.enabled = TRUE
WHERE discovered.scalar_value IS NOT NULL
  AND BTRIM(discovered.scalar_value) <> ''
  AND LENGTH(discovered.scalar_value) <= config.max_value_length
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 11. Configure and populate low-cardinality relational values
--
-- Included:
--   - character/text columns
--   - boolean columns
--   - PostgreSQL enum columns
--
-- Excluded:
--   - non-allow-listed relations
--   - primary keys and foreign keys
--   - id/uuid columns
--   - passwords, hashes, secrets, tokens, and credentials
--   - long free-text content
--   - more than 200 distinct values
--   - values longer than 200 characters
-- ============================================================================

CREATE TEMPORARY TABLE relational_value_stage (
    value_text TEXT NOT NULL
) ON COMMIT DROP;


DO $bootstrap_relational_values$
DECLARE
    candidate_column RECORD;
    distinct_value_count INTEGER;
    longest_value_length INTEGER;

    maximum_distinct_values CONSTANT INTEGER := 200;
    maximum_value_length CONSTANT INTEGER := 200;
BEGIN
    FOR candidate_column IN
        SELECT
            columns.table_schema,
            columns.table_name,
            columns.column_name
        FROM information_schema.columns AS columns
        JOIN allowed_relation_stage AS allowed
            ON allowed.schema_name = columns.table_schema
           AND allowed.table_name = columns.table_name
           AND allowed.collect_values = TRUE
        JOIN text_to_sql_catalog.schema_catalog AS catalogue_column
            ON catalogue_column.object_type = 'column'
           AND catalogue_column.schema_name = columns.table_schema
           AND catalogue_column.table_name = columns.table_name
           AND catalogue_column.column_name = columns.column_name
        WHERE (
            columns.data_type IN (
                'character varying',
                'character',
                'text',
                'boolean'
            )
            OR EXISTS (
                SELECT 1
                FROM pg_type AS enum_type
                JOIN pg_namespace AS enum_namespace
                    ON enum_namespace.oid = enum_type.typnamespace
                JOIN pg_enum AS enum_value
                    ON enum_value.enumtypid = enum_type.oid
                WHERE enum_namespace.nspname = columns.udt_schema
                  AND enum_type.typname = columns.udt_name
            )
        )
          AND COALESCE(
              catalogue_column.is_primary_key,
              FALSE
          ) = FALSE
          AND columns.column_name !~* '(^id$|_id$|uuid$|_uuid$)'
          AND columns.column_name !~* (
              'password|passwd|hash|secret|token|credential|api[_]?key'
          )
          AND columns.column_name !~* (
              'description|details|notes|comment|content|'
              'message|body|summary|user_agent'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM pg_constraint AS foreign_key
              JOIN pg_class AS relation
                  ON relation.oid = foreign_key.conrelid
              JOIN pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
              JOIN pg_attribute AS attribute
                  ON attribute.attrelid = relation.oid
                 AND attribute.attnum = ANY(foreign_key.conkey)
              WHERE foreign_key.contype = 'f'
                AND namespace.nspname = columns.table_schema
                AND relation.relname = columns.table_name
                AND attribute.attname = columns.column_name
          )
        ORDER BY
            columns.table_name,
            columns.ordinal_position
    LOOP
        TRUNCATE TABLE relational_value_stage;

        EXECUTE FORMAT(
            $sql$
            INSERT INTO relational_value_stage (value_text)
            SELECT DISTINCT %I::TEXT
            FROM %I.%I
            WHERE %I IS NOT NULL
              AND BTRIM(%I::TEXT) <> ''
            LIMIT %s
            $sql$,
            candidate_column.column_name,
            candidate_column.table_schema,
            candidate_column.table_name,
            candidate_column.column_name,
            candidate_column.column_name,
            maximum_distinct_values + 1
        );

        SELECT
            COUNT(*),
            COALESCE(MAX(LENGTH(value_text)), 0)
        INTO
            distinct_value_count,
            longest_value_length
        FROM relational_value_stage;

        IF distinct_value_count BETWEEN 1 AND maximum_distinct_values
           AND longest_value_length <= maximum_value_length
        THEN
            INSERT INTO text_to_sql_catalog.value_catalog_config (
                source_kind,
                schema_name,
                table_name,
                column_name,
                json_path,
                enabled,
                max_distinct_values,
                max_value_length
            )
            VALUES (
                'column',
                candidate_column.table_schema,
                candidate_column.table_name,
                candidate_column.column_name,
                NULL,
                TRUE,
                maximum_distinct_values,
                maximum_value_length
            );

            INSERT INTO text_to_sql_catalog.value_catalog (
                source_kind,
                schema_name,
                table_name,
                column_name,
                json_path,
                original_value,
                normalized_value,
                search_text
            )
            SELECT
                'column',
                candidate_column.table_schema,
                candidate_column.table_name,
                candidate_column.column_name,
                NULL,
                staged.value_text,
                text_to_sql_catalog._bootstrap_normalize_text(
                    staged.value_text
                ),
                text_to_sql_catalog._bootstrap_normalize_text(
                    CONCAT_WS(
                        ' ',
                        candidate_column.table_name,
                        REPLACE(
                            candidate_column.table_name,
                            '_',
                            ' '
                        ),
                        candidate_column.column_name,
                        REPLACE(
                            candidate_column.column_name,
                            '_',
                            ' '
                        ),
                        staged.value_text
                    )
                )
            FROM relational_value_stage AS staged
            ON CONFLICT DO NOTHING;
        END IF;
    END LOOP;
END;
$bootstrap_relational_values$;

-- ============================================================================
-- 12. Remove one-time helper functions
-- ============================================================================

DROP FUNCTION text_to_sql_catalog._bootstrap_discover_json_paths(JSONB);
DROP FUNCTION text_to_sql_catalog._bootstrap_normalize_text(TEXT);

COMMIT;