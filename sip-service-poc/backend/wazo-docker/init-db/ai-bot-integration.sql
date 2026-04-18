-- AI Bot Database Integration for Wazo Platform
-- This script creates the necessary database schema for AI Bot integration

-- 0. Ensure required extensions are loaded

-- 1. Create AI Bot transcriptions table FIRST (to avoid missing table errors)
-- New simplified structure with JSONB content field containing all transcription data
CREATE TABLE IF NOT EXISTS ai_bot_transcriptions (
    id SERIAL PRIMARY KEY,
    call_id VARCHAR(255) NOT NULL,       -- external call identifier
    content JSONB NOT NULL,              -- JSON containing: question, answer, channel_id, call_id, user_uuid, tenant_uuid, stt_engine, llm_model, token_count, role, timestamp
    created_at TIMESTAMP DEFAULT NOW()
);


-- 2. Create AI Bot extension in Wazo database
-- First, let's check if the extensions table exists and understand its structure
DO $$
BEGIN
    -- Check if extensions table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'extensions') THEN
        -- Check what columns exist in extensions table
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'extensions' AND column_name = 'app') THEN
            -- Insert AI Bot extension if it doesn't exist (with app column)
            INSERT INTO extensions (context, exten, app, appdata, appdata2, priority, enabled)
            VALUES ('default', '1000', 'Stasis', 'voice-bot', '1000', 1, true)
            ON CONFLICT (context, exten, priority) DO NOTHING;
        ELSE
            -- Check if appdata column exists
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'extensions' AND column_name = 'appdata') THEN
                -- Insert AI Bot extension if it doesn't exist (with appdata column)
                INSERT INTO extensions (context, exten, appdata, appdata2, priority, enabled)
                VALUES ('default', '1000', 'voice-bot', '1000', 1, true)
                ON CONFLICT (context, exten, priority) DO NOTHING;
            ELSE
                -- Insert AI Bot extension if it doesn't exist (without appdata column)
                INSERT INTO extensions (context, exten, priority, enabled)
                VALUES ('default', '1000', 1, true)
                ON CONFLICT (context, exten, priority) DO NOTHING;
            END IF;
        END IF;

        RAISE NOTICE 'AI Bot extension 1000 created/verified in extensions table';
    ELSE
        RAISE NOTICE 'Extensions table not found - may need to use different table name';
    END IF;
END $$;

-- 2. Create AI Bot user/device
-- Check for users table and create AI Bot user
DO $$
BEGIN
    -- Check if users table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
        -- Insert AI Bot user if it doesn't exist
        INSERT INTO users (uuid, firstname, lastname, context, enabled, tenant_uuid)
        VALUES (
            gen_random_uuid(),
            'AI',
            'Bot',
            'default',
            true,
            (SELECT tenant_uuid FROM tenant LIMIT 1)
        )
        ON CONFLICT (uuid) DO NOTHING;

        RAISE NOTICE 'AI Bot user created/verified in users table';
    ELSE
        RAISE NOTICE 'Users table not found - may need to use different table name';
    END IF;
END $$;

-- 3. Create AI Bot CDR integration table
CREATE TABLE IF NOT EXISTS ai_bot_calls (
    id SERIAL PRIMARY KEY,
    call_id VARCHAR(255) UNIQUE NOT NULL,
    channel_id VARCHAR(255),
    user_uuid VARCHAR(255),
    tenant_uuid VARCHAR(255),
    user_input TEXT,
    bot_response TEXT,
    conversation_length INTEGER DEFAULT 0, -- in seconds
    speech_recognition_engine VARCHAR(50) DEFAULT 'yandex',
    llm_provider VARCHAR(50) DEFAULT 'openai',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);


-- 4. Create AI Bot configuration table
CREATE TABLE IF NOT EXISTS ai_bot_config (
    id SERIAL PRIMARY KEY,
    tenant_uuid VARCHAR(255) UNIQUE NOT NULL,
    speech_recognition_engine VARCHAR(50) DEFAULT 'yandex',
    llm_provider VARCHAR(50) DEFAULT 'openai',
    llm_model VARCHAR(100) DEFAULT 'gpt-4o-mini',
    default_greeting TEXT DEFAULT 'Здравствуйте! Чем могу помочь?',
    max_conversation_length INTEGER DEFAULT 300, -- seconds
    silence_timeout INTEGER DEFAULT 5, -- seconds
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 5. Create AI Bot call analytics table
CREATE TABLE IF NOT EXISTS ai_bot_analytics (
    id SERIAL PRIMARY KEY,
    call_id VARCHAR(255) REFERENCES ai_bot_calls(call_id),
    user_satisfaction INTEGER CHECK (user_satisfaction >= 1 AND user_satisfaction <= 5),
    conversation_length INTEGER, -- in seconds
    topics_discussed TEXT[],
    resolution_rate DECIMAL(3,2) CHECK (resolution_rate >= 0 AND resolution_rate <= 1),
    speech_recognition_accuracy DECIMAL(3,2) CHECK (speech_recognition_accuracy >= 0 AND speech_recognition_accuracy <= 1),
    response_time_avg DECIMAL(5,2), -- average response time in seconds
    created_at TIMESTAMP DEFAULT NOW()
);

-- 6. Create AI Bot user preferences table
CREATE TABLE IF NOT EXISTS ai_bot_user_preferences (
    id SERIAL PRIMARY KEY,
    user_uuid VARCHAR(255) NOT NULL,
    tenant_uuid VARCHAR(255) NOT NULL,
    preferred_language VARCHAR(10) DEFAULT 'ru',
    voice_speed DECIMAL(3,2) DEFAULT 1.0,
    voice_pitch DECIMAL(3,2) DEFAULT 1.0,
    custom_greeting TEXT,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_uuid, tenant_uuid)
);

-- 7. Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 8. Create triggers for updated_at (only if they don't exist)
DO $$
BEGIN
    -- Check if trigger exists before creating
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ai_bot_calls_updated_at') THEN
        CREATE TRIGGER update_ai_bot_calls_updated_at
            BEFORE UPDATE ON ai_bot_calls
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ai_bot_config_updated_at') THEN
        CREATE TRIGGER update_ai_bot_config_updated_at
            BEFORE UPDATE ON ai_bot_config
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ai_bot_user_preferences_updated_at') THEN
        CREATE TRIGGER update_ai_bot_user_preferences_updated_at
            BEFORE UPDATE ON ai_bot_user_preferences
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- 9. Ensure tenant exists for call_logd (fix foreign key constraint)
DO $$
BEGIN
    -- Check if call_logd_tenant table exists and create default tenant if needed
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'call_logd_tenant') THEN
        -- Check what columns exist in call_logd_tenant table
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'call_logd_tenant' AND column_name = 'name') THEN
            -- Insert default tenant if it doesn't exist (with name column)
            INSERT INTO call_logd_tenant (uuid, name, slug)
            VALUES (
                '701e1f61-8c23-4e62-b564-7a049adf0aef',
                'Default Tenant',
                'default'
            )
            ON CONFLICT (uuid) DO NOTHING;
        ELSE
            -- Check if slug column exists
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'call_logd_tenant' AND column_name = 'slug') THEN
                -- Insert default tenant if it doesn't exist (with slug column)
                INSERT INTO call_logd_tenant (uuid, slug)
                VALUES (
                    '701e1f61-8c23-4e62-b564-7a049adf0aef',
                    'default'
                )
                ON CONFLICT (uuid) DO NOTHING;
            ELSE
                -- Insert default tenant if it doesn't exist (without slug column)
                INSERT INTO call_logd_tenant (uuid)
                VALUES (
                    '701e1f61-8c23-4e62-b564-7a049adf0aef'
                )
                ON CONFLICT (uuid) DO NOTHING;
            END IF;
        END IF;

        RAISE NOTICE 'Default tenant created/verified in call_logd_tenant table';
    END IF;
END $$;

-- 10. Insert default AI Bot configuration for existing tenants
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'auth_tenant') THEN
        INSERT INTO ai_bot_config (tenant_uuid)
        SELECT uuid FROM auth_tenant
        ON CONFLICT (tenant_uuid) DO NOTHING;

        RAISE NOTICE 'AI Bot configuration created from auth_tenant table';
    ELSIF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenant') THEN
        INSERT INTO ai_bot_config (tenant_uuid)
        SELECT uuid FROM tenant
        ON CONFLICT (tenant_uuid) DO NOTHING;

        RAISE NOTICE 'AI Bot configuration created from tenant table';
    ELSE
        RAISE NOTICE 'Neither auth_tenant nor tenant table found, skipping AI Bot configuration';
    END IF;
END $$;

-- 11. Create view for AI Bot call summary (fixed to use correct columns)
CREATE OR REPLACE VIEW ai_bot_call_summary AS
SELECT
    DATE(created_at) as call_date,
    COUNT(*) as total_calls,
    AVG(conversation_length) as avg_conversation_length,
    COUNT(CASE WHEN conversation_length > 0 THEN 1 END) as calls_with_conversation
FROM ai_bot_calls
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY call_date DESC;

-- 12. Grant permissions (adjust as needed based on your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ai_bot_calls TO asterisk;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ai_bot_config TO asterisk;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ai_bot_analytics TO asterisk;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ai_bot_user_preferences TO asterisk;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ai_bot_transcriptions TO asterisk;
-- GRANT SELECT ON ai_bot_call_summary TO asterisk;

-- 13. Create function to log AI Bot call
CREATE OR REPLACE FUNCTION log_ai_bot_call(
    p_call_id VARCHAR(255),
    p_channel_id VARCHAR(255),
    p_user_uuid VARCHAR(255),
    p_tenant_uuid VARCHAR(255),
    p_user_input TEXT DEFAULT NULL,
    p_bot_response TEXT DEFAULT NULL,
    p_conversation_length INTEGER DEFAULT 0
)
RETURNS INTEGER AS $$
DECLARE
    call_record_id INTEGER;
BEGIN
    INSERT INTO ai_bot_calls (
        call_id,
        channel_id,
        user_uuid,
        tenant_uuid,
        user_input,
        bot_response,
        conversation_length
    ) VALUES (
        p_call_id,
        p_channel_id,
        p_user_uuid,
        p_tenant_uuid,
        p_user_input,
        p_bot_response,
        p_conversation_length
    ) RETURNING id INTO call_record_id;

    RETURN call_record_id;
END;
$$ LANGUAGE plpgsql;

-- Success message
SELECT 'AI Bot database integration completed successfully!' as status;
