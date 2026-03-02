-- PLM Enterprise Database Migration
-- Run this after the initial schema.sql to fix issues and add missing features

-- Fix: Vector dimension mismatch (all-MiniLM-L6-v2 uses 384, not 768)
-- Note: If you have existing data, you need to re-embed it after this change
-- ALTER TABLE knowledge_base ALTER COLUMN embedding TYPE VECTOR(384);

-- Add match_knowledge function for vector similarity search
CREATE OR REPLACE FUNCTION match_knowledge(
  query_embedding VECTOR(384),
  match_threshold FLOAT,
  match_count INT,
  org_id UUID
)
RETURNS TABLE (
  id UUID,
  organization_id UUID,
  content TEXT,
  source TEXT,
  metadata JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    kb.id,
    kb.organization_id,
    kb.content,
    kb.source,
    kb.metadata,
    1 - (kb.embedding <=> query_embedding) AS similarity
  FROM knowledge_base kb
  WHERE kb.organization_id = org_id
    AND 1 - (kb.embedding <=> query_embedding) > match_threshold
  ORDER BY kb.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Update vector index for correct dimensions
DROP INDEX IF EXISTS idx_knowledge_embedding;
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding ON knowledge_base
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Add service_role bypass policies so backend can access all data
CREATE POLICY service_role_all_organizations ON organizations
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_users ON users
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_models ON models
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_training_data ON training_data
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_knowledge_base ON knowledge_base
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_queries ON queries
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_fact_checks ON fact_checks
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_audit_logs ON audit_logs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_training_jobs ON training_jobs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY service_role_all_api_keys ON api_keys
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Add RLS policies for organizations table (missing in original)
CREATE POLICY organizations_org_policy ON organizations
  FOR ALL
  USING (id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

-- Add RLS policies for training_jobs
CREATE POLICY training_jobs_org_policy ON training_jobs
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

-- Add RLS policies for api_keys
CREATE POLICY api_keys_org_policy ON api_keys
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

-- Add RLS policies for fact_checks (through queries)
CREATE POLICY fact_checks_org_policy ON fact_checks
  FOR ALL
  USING (query_id IN (
    SELECT q.id FROM queries q
    JOIN users u ON q.organization_id = u.organization_id
    WHERE u.id = auth.uid()
  ));

DO $$
BEGIN
    RAISE NOTICE 'PLM Enterprise migration applied successfully!';
    RAISE NOTICE 'Added: match_knowledge function, service_role policies, missing RLS policies';
END $$;
