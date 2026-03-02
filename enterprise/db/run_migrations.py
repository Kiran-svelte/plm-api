"""Run all database migrations for PLM Enterprise Platform."""
import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fallback to individual connection params
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    if not db_password:
        raise RuntimeError(
            "Database credentials not configured. Set DATABASE_URL or DB_HOST/DB_USER/DB_PASSWORD env vars."
        )
    conn = psycopg2.connect(
        host=db_host, port=int(db_port), dbname=db_name,
        user=db_user, password=db_password,
        sslmode='require', connect_timeout=10
    )
else:
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
conn.autocommit = True
cur = conn.cursor()

migrations = [
    # Phase 1: Organization columns
    "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT false",
    "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS onboarding_step INTEGER DEFAULT 0",

    # Knowledge base columns (Phase 4)
    "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'general'",
    "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'text'",
    "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS file_name TEXT",
    "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS chunk_index INTEGER DEFAULT 0",

    # Conversations table (Phase 2)
    """CREATE TABLE IF NOT EXISTS conversations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        model_id UUID REFERENCES models(id) ON DELETE SET NULL,
        user_id UUID,
        title TEXT NOT NULL DEFAULT 'New Conversation',
        status TEXT NOT NULL DEFAULT 'active',
        assistant_id UUID,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        metadata JSONB DEFAULT '{}'::jsonb
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conversations_org ON conversations(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC)",

    # Messages table (Phase 2)
    """CREATE TABLE IF NOT EXISTS messages (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        query_id UUID,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at ASC)",

    # Add conversation_id to queries
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS conversation_id UUID",
    "CREATE INDEX IF NOT EXISTS idx_queries_conversation ON queries(conversation_id)",

    # Invitations table (Phase 3)
    """CREATE TABLE IF NOT EXISTS invitations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        status TEXT NOT NULL DEFAULT 'pending',
        invited_by UUID,
        token TEXT NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL,
        accepted_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        metadata JSONB DEFAULT '{}'::jsonb
    )""",
    "CREATE INDEX IF NOT EXISTS idx_invitations_org ON invitations(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email)",
    "CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token)",

    # Assistants table (Phase 5)
    """CREATE TABLE IF NOT EXISTS assistants (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        model_id UUID,
        name TEXT NOT NULL,
        description TEXT,
        assistant_type TEXT NOT NULL DEFAULT 'general',
        system_prompt TEXT NOT NULL,
        icon TEXT DEFAULT 'brain',
        temperature FLOAT DEFAULT 0.7,
        use_rag BOOLEAN DEFAULT true,
        knowledge_categories TEXT[] DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        metadata JSONB DEFAULT '{}'::jsonb
    )""",
    "CREATE INDEX IF NOT EXISTS idx_assistants_org ON assistants(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_assistants_type ON assistants(organization_id, assistant_type)",

    # Usage records table (Phase 7)
    """CREATE TABLE IF NOT EXISTS usage_records (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        period TEXT NOT NULL,
        queries_count INTEGER DEFAULT 0,
        knowledge_entries_count INTEGER DEFAULT 0,
        models_count INTEGER DEFAULT 0,
        users_count INTEGER DEFAULT 0,
        storage_bytes BIGINT DEFAULT 0,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(organization_id, period)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_usage_org_period ON usage_records(organization_id, period)",

    # Notifications table (Phase 8)
    """CREATE TABLE IF NOT EXISTS notifications (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        user_id UUID,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT,
        read BOOLEAN DEFAULT false,
        action_url TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        metadata JSONB DEFAULT '{}'::jsonb
    )""",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC)",

    # Webhooks table (Phase 8)
    """CREATE TABLE IF NOT EXISTS webhooks (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        events TEXT[] NOT NULL,
        secret TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        failure_count INTEGER DEFAULT 0,
        last_triggered_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        metadata JSONB DEFAULT '{}'::jsonb
    )""",
    "CREATE INDEX IF NOT EXISTS idx_webhooks_org ON webhooks(organization_id)",

    # Triggers for new tables
    """CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    """CREATE TRIGGER update_assistants_updated_at BEFORE UPDATE ON assistants
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",

    # RLS for new tables
    "ALTER TABLE conversations ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE messages ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE invitations ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE assistants ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE notifications ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY",

    # RLS policies
    """CREATE POLICY conversations_org_policy ON conversations FOR ALL
        USING (organization_id IN (SELECT organization_id FROM users WHERE users.id = auth.uid()))""",
    """CREATE POLICY messages_conv_policy ON messages FOR ALL
        USING (conversation_id IN (
            SELECT c.id FROM conversations c WHERE c.organization_id IN (
                SELECT organization_id FROM users WHERE users.id = auth.uid()
            )
        ))""",
    """CREATE POLICY invitations_org_policy ON invitations FOR ALL
        USING (organization_id IN (SELECT organization_id FROM users WHERE users.id = auth.uid()))""",
    """CREATE POLICY assistants_org_policy ON assistants FOR ALL
        USING (organization_id IN (SELECT organization_id FROM users WHERE users.id = auth.uid()))""",
    """CREATE POLICY notifications_user_policy ON notifications FOR ALL
        USING (user_id = auth.uid())""",
    """CREATE POLICY webhooks_org_policy ON webhooks FOR ALL
        USING (organization_id IN (SELECT organization_id FROM users WHERE users.id = auth.uid()))""",
    """CREATE POLICY usage_records_org_policy ON usage_records FOR ALL
        USING (organization_id IN (SELECT organization_id FROM users WHERE users.id = auth.uid()))""",

    # Knowledge base category indexes
    "CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge_base(organization_id, category)",
    "CREATE INDEX IF NOT EXISTS idx_knowledge_source_type ON knowledge_base(organization_id, source_type)",
]

success = 0
errors = 0
for i, sql in enumerate(migrations, 1):
    try:
        cur.execute(sql)
        success += 1
        label = sql.strip()[:60].replace('\n', ' ')
        print(f'[{i}/{len(migrations)}] OK: {label}')
    except Exception as e:
        err = str(e).strip().split('\n')[0][:80]
        if 'already exists' in err:
            success += 1
            print(f'[{i}/{len(migrations)}] SKIP (exists)')
        else:
            errors += 1
            print(f'[{i}/{len(migrations)}] ERR: {err}')
        conn.rollback()
        conn.autocommit = True

conn.close()
print(f'\nDone: {success} success, {errors} errors')
