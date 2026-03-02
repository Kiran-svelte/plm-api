-- PLM ENTERPRISE DATABASE SCHEMA
-- Complete schema for multi-tenant PLM system with RAG capabilities

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Organizations (Customers)
CREATE TABLE IF NOT EXISTS organizations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  niche TEXT NOT NULL,
  tier TEXT NOT NULL DEFAULT 'professional', -- starter, professional, enterprise
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Users
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'member', -- owner, admin, member
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Models
CREATE TABLE IF NOT EXISTS models (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT '1.0.0',
  status TEXT NOT NULL DEFAULT 'pending', -- pending, training, ready, deployed, failed
  base_model TEXT NOT NULL DEFAULT 'llama-3.2-3b',
  model_path TEXT,
  metrics JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deployed_at TIMESTAMPTZ
);

-- Training Data
CREATE TABLE IF NOT EXISTS training_data (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  model_id UUID REFERENCES models(id) ON DELETE CASCADE,
  instruction TEXT NOT NULL,
  output TEXT NOT NULL,
  input_text TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  quality_score FLOAT,
  validated BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID REFERENCES users(id)
);

-- Knowledge Base (for RAG)
CREATE TABLE IF NOT EXISTS knowledge_base (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  embedding VECTOR(384), -- all-MiniLM-L6-v2 produces 384-dim embeddings
  source TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Queries (for learning and analytics)
CREATE TABLE IF NOT EXISTS queries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  model_id UUID REFERENCES models(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  query TEXT NOT NULL,
  response TEXT NOT NULL,
  confidence FLOAT,
  feedback TEXT, -- good, bad, excellent, null
  response_time_ms INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Fact Checks (for hallucination prevention)
CREATE TABLE IF NOT EXISTS fact_checks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  query_id UUID REFERENCES queries(id) ON DELETE CASCADE,
  claim TEXT NOT NULL,
  verified BOOLEAN,
  confidence FLOAT,
  source TEXT,
  verification_method TEXT, -- multi-model, rag, external-api
  created_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Audit Logs (for accountability)
CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  action TEXT NOT NULL,
  resource_type TEXT,
  resource_id UUID,
  details JSONB DEFAULT '{}'::jsonb,
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Training Jobs
CREATE TABLE IF NOT EXISTS training_jobs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  model_id UUID REFERENCES models(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued', -- queued, running, completed, failed
  progress FLOAT DEFAULT 0,
  training_config JSONB DEFAULT '{}'::jsonb,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- API Keys (for customer API access)
CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', -- active, revoked
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  revoked_at TIMESTAMPTZ,
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(status);
CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_models_org ON models(organization_id);
CREATE INDEX IF NOT EXISTS idx_models_status ON models(status);
CREATE INDEX IF NOT EXISTS idx_training_data_org ON training_data(organization_id);
CREATE INDEX IF NOT EXISTS idx_training_data_model ON training_data(model_id);
CREATE INDEX IF NOT EXISTS idx_training_data_quality ON training_data(quality_score);
CREATE INDEX IF NOT EXISTS idx_queries_org ON queries(organization_id);
CREATE INDEX IF NOT EXISTS idx_queries_model ON queries(model_id);
CREATE INDEX IF NOT EXISTS idx_queries_created ON queries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_org ON knowledge_base(organization_id);
CREATE INDEX IF NOT EXISTS idx_fact_checks_query ON fact_checks(query_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_training_jobs_org ON training_jobs(organization_id);
CREATE INDEX IF NOT EXISTS idx_training_jobs_status ON training_jobs(status);
CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(organization_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);

-- Vector similarity search index for RAG
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding ON knowledge_base
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Row Level Security (RLS) Policies
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE models ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;
ALTER TABLE queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only see their own organization's data
CREATE POLICY users_org_policy ON users
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY models_org_policy ON models
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY training_data_org_policy ON training_data
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY knowledge_base_org_policy ON knowledge_base
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY queries_org_policy ON queries
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY audit_logs_org_policy ON audit_logs
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE id = auth.uid()
  ));

-- Functions for automated workflows

-- Function: Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_organizations_updated_at BEFORE UPDATE ON organizations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_models_updated_at BEFORE UPDATE ON models
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_knowledge_base_updated_at BEFORE UPDATE ON knowledge_base
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function: Log all changes to audit_logs
CREATE OR REPLACE FUNCTION log_audit()
RETURNS TRIGGER AS $$
DECLARE
    _org_id uuid;
BEGIN
    -- For the organizations table, use the row's own id as the org_id.
    -- For all other tables, use the organization_id column.
    IF TG_TABLE_NAME = 'organizations' THEN
        _org_id := COALESCE(NEW.id, OLD.id);
    ELSE
        _org_id := COALESCE(NEW.organization_id, OLD.organization_id);
    END IF;

    INSERT INTO audit_logs (
        organization_id,
        user_id,
        action,
        resource_type,
        resource_id,
        details
    ) VALUES (
        _org_id,
        auth.uid(),
        TG_OP,
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        jsonb_build_object(
            'old', row_to_json(OLD),
            'new', row_to_json(NEW)
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add audit triggers to critical tables
CREATE TRIGGER audit_organizations AFTER INSERT OR UPDATE OR DELETE ON organizations
  FOR EACH ROW EXECUTE FUNCTION log_audit();

CREATE TRIGGER audit_models AFTER INSERT OR UPDATE OR DELETE ON models
  FOR EACH ROW EXECUTE FUNCTION log_audit();

CREATE TRIGGER audit_training_data AFTER INSERT OR UPDATE OR DELETE ON training_data
  FOR EACH ROW EXECUTE FUNCTION log_audit();

-- View: Organization statistics
CREATE OR REPLACE VIEW organization_stats AS
SELECT
    o.id,
    o.name,
    o.niche,
    o.tier,
    COUNT(DISTINCT m.id) as total_models,
    COUNT(DISTINCT CASE WHEN m.status = 'deployed' THEN m.id END) as deployed_models,
    COUNT(DISTINCT td.id) as total_training_examples,
    AVG(td.quality_score) as avg_quality_score,
    COUNT(DISTINCT q.id) as total_queries,
    AVG(q.confidence) as avg_confidence,
    AVG(q.response_time_ms) as avg_response_time_ms,
    COUNT(DISTINCT u.id) as total_users
FROM organizations o
LEFT JOIN models m ON o.id = m.organization_id
LEFT JOIN training_data td ON o.id = td.organization_id
LEFT JOIN queries q ON o.id = q.organization_id
LEFT JOIN users u ON o.id = u.organization_id
GROUP BY o.id, o.name, o.niche, o.tier;

-- View: Model performance metrics
CREATE OR REPLACE VIEW model_metrics AS
SELECT
    m.id,
    m.name,
    m.version,
    m.status,
    o.name as organization_name,
    COUNT(DISTINCT q.id) as total_queries,
    AVG(q.confidence) as avg_confidence,
    AVG(q.response_time_ms) as avg_response_time,
    COUNT(DISTINCT td.id) as training_examples_count,
    AVG(td.quality_score) as avg_training_quality
FROM models m
JOIN organizations o ON m.organization_id = o.id
LEFT JOIN queries q ON m.id = q.model_id
LEFT JOIN training_data td ON m.id = td.model_id
GROUP BY m.id, m.name, m.version, m.status, o.name;

-- Grant permissions for authenticated users
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO authenticated;

-- Grant permissions for service role (backend)
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO service_role;

-- Function: Vector similarity search for RAG knowledge base
-- Called by db_client.py search_knowledge() via self.client.rpc("match_knowledge", ...)
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
    created_at TIMESTAMPTZ,
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
        kb.created_at,
        1 - (kb.embedding <=> query_embedding) AS similarity
    FROM knowledge_base kb
    WHERE kb.organization_id = org_id
      AND 1 - (kb.embedding <=> query_embedding) > match_threshold
    ORDER BY kb.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- RLS Policies for tables that were missing them

-- Organizations: users can see their own org
CREATE POLICY organizations_org_policy ON organizations
  FOR ALL
  USING (id IN (
    SELECT organization_id FROM users WHERE users.id = auth.uid()
  ));

-- Training jobs: users can see their org's jobs
CREATE POLICY training_jobs_org_policy ON training_jobs
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE users.id = auth.uid()
  ));

-- API keys: users can see their org's keys
CREATE POLICY api_keys_org_policy ON api_keys
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE users.id = auth.uid()
  ));

-- Fact checks: users can see fact checks for their org's queries
CREATE POLICY fact_checks_org_policy ON fact_checks
  FOR ALL
  USING (query_id IN (
    SELECT q.id FROM queries q
    WHERE q.organization_id IN (
      SELECT organization_id FROM users WHERE users.id = auth.uid()
    )
  ));

-- ============================================================
-- PLM v2.0 ADDITIONS
-- ============================================================

-- Pet Status (tracks AI pet evolution per org/model)
CREATE TABLE IF NOT EXISTS pet_status (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  model_id UUID REFERENCES models(id) ON DELETE CASCADE,
  stage TEXT NOT NULL DEFAULT 'egg',
  mood TEXT NOT NULL DEFAULT 'hungry',
  xp INTEGER NOT NULL DEFAULT 0,
  training_examples INTEGER NOT NULL DEFAULT 0,
  accuracy FLOAT DEFAULT 0.0,
  personality_prompt TEXT,
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (organization_id, model_id)
);

-- Privacy Audit (logs every sanitization event)
CREATE TABLE IF NOT EXISTS privacy_audit (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  query_hash TEXT NOT NULL,
  entities_stripped JSONB DEFAULT '[]'::jsonb,
  pii_keywords_found JSONB DEFAULT '[]'::jsonb,
  sanitization_applied BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Multi-Modal Queries (tracks queries by modality type)
CREATE TABLE IF NOT EXISTS multi_modal_queries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  model_id UUID REFERENCES models(id) ON DELETE CASCADE,
  query_id UUID REFERENCES queries(id) ON DELETE CASCADE,
  modality TEXT NOT NULL DEFAULT 'text',
  query TEXT NOT NULL,
  response TEXT NOT NULL,
  response_time_ms INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for v2.0 tables
CREATE INDEX IF NOT EXISTS idx_pet_status_org ON pet_status(organization_id);
CREATE INDEX IF NOT EXISTS idx_pet_status_model ON pet_status(model_id);
CREATE INDEX IF NOT EXISTS idx_privacy_audit_org ON privacy_audit(organization_id);
CREATE INDEX IF NOT EXISTS idx_privacy_audit_created ON privacy_audit(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_multi_modal_org ON multi_modal_queries(organization_id);
CREATE INDEX IF NOT EXISTS idx_multi_modal_modality ON multi_modal_queries(modality);
CREATE INDEX IF NOT EXISTS idx_multi_modal_created ON multi_modal_queries(created_at DESC);

-- RLS for v2.0 tables
ALTER TABLE pet_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE multi_modal_queries ENABLE ROW LEVEL SECURITY;

CREATE POLICY pet_status_org_policy ON pet_status
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE users.id = auth.uid()
  ));

CREATE POLICY privacy_audit_org_policy ON privacy_audit
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE users.id = auth.uid()
  ));

CREATE POLICY multi_modal_queries_org_policy ON multi_modal_queries
  FOR ALL
  USING (organization_id IN (
    SELECT organization_id FROM users WHERE users.id = auth.uid()
  ));

-- Grant permissions for v2.0 tables
GRANT ALL ON pet_status TO authenticated;
GRANT ALL ON privacy_audit TO authenticated;
GRANT ALL ON multi_modal_queries TO authenticated;
GRANT ALL ON pet_status TO service_role;
GRANT ALL ON privacy_audit TO service_role;
GRANT ALL ON multi_modal_queries TO service_role;

-- updated_at triggers for v2.0 tables
CREATE TRIGGER update_pet_status_updated_at BEFORE UPDATE ON pet_status
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'PLM Enterprise database schema created successfully!';
    RAISE NOTICE 'Tables: organizations, users, models, training_data, knowledge_base, queries, fact_checks, audit_logs, training_jobs, api_keys';
    RAISE NOTICE 'v2.0 Tables: pet_status, privacy_audit, multi_modal_queries';
    RAISE NOTICE 'Indexes: Optimized for performance with vector search';
    RAISE NOTICE 'RLS: Row Level Security enabled for multi-tenant isolation';
    RAISE NOTICE 'Audit: Automatic logging of all changes';
END $$;
