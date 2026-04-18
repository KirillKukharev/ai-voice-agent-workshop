-- Queue setup for Wazo AI Bot integration
-- This script creates the necessary database entries for queue management

-- Create queue members table if it doesn't exist
CREATE TABLE IF NOT EXISTS queue_members (
    id SERIAL PRIMARY KEY,
    queue_name VARCHAR(255) NOT NULL,
    member_name VARCHAR(255) NOT NULL,
    member_interface VARCHAR(255) NOT NULL,
    penalty INTEGER DEFAULT 0,
    paused INTEGER DEFAULT 0,
    uniqueid VARCHAR(255),
    ringinuse INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create queue table if it doesn't exist
CREATE TABLE IF NOT EXISTS queues (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    strategy VARCHAR(50) DEFAULT 'ringall',
    timeout INTEGER DEFAULT 30,
    retry INTEGER DEFAULT 5,
    maxlen INTEGER DEFAULT 0,
    announce_frequency INTEGER DEFAULT 30,
    announce_holdtime BOOLEAN DEFAULT true,
    announce_position BOOLEAN DEFAULT true,
    joinempty BOOLEAN DEFAULT true,
    leavewhenempty BOOLEAN DEFAULT false,
    ringinuse BOOLEAN DEFAULT false,
    autopause BOOLEAN DEFAULT false,
    autopausedelay INTEGER DEFAULT 0,
    reportholdtime BOOLEAN DEFAULT true,
    memberdelay INTEGER DEFAULT 0,
    weight INTEGER DEFAULT 0,
    timeoutrestart BOOLEAN DEFAULT false,
    musiconhold VARCHAR(255) DEFAULT 'default',
    context VARCHAR(255) DEFAULT 'default',
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create agents table if it doesn't exist
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    agent_id VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    context VARCHAR(255) DEFAULT 'default',
    language VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'UTC',
    wrapuptime INTEGER DEFAULT 10,
    maxloginattempts INTEGER DEFAULT 3,
    logoffaftercall BOOLEAN DEFAULT false,
    ackcall BOOLEAN DEFAULT false,
    endcall BOOLEAN DEFAULT false,
    updatecdr BOOLEAN DEFAULT false,
    autologoff BOOLEAN DEFAULT true,
    autologoffunavail BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert default queues
INSERT INTO queues (name, strategy, timeout, retry, maxlen, announce_frequency, announce_holdtime, announce_position, joinempty, leavewhenempty, ringinuse, autopause, autopausedelay, reportholdtime, memberdelay, weight, timeoutrestart, musiconhold, context, priority)
VALUES
    ('ai-bot-queue', 'ringall', 30, 5, 10, 30, true, true, true, false, false, false, 0, true, 0, 0, false, 'default', 'default', 0),
    ('support-queue', 'ringall', 45, 10, 20, 30, true, true, true, false, false, false, 0, true, 0, 0, false, 'default', 'default', 0)
ON CONFLICT (name) DO NOTHING;

-- Insert default agents
INSERT INTO agents (agent_id, password, name, context, language, timezone, wrapuptime, maxloginattempts, logoffaftercall, ackcall, endcall, updatecdr, autologoff, autologoffunavail)
VALUES
    ('1000', 'changeme', 'AI Bot Agent', 'default', 'en', 'UTC', 10, 3, false, false, false, false, true, true)
ON CONFLICT (agent_id) DO NOTHING;

-- Insert queue members
INSERT INTO queue_members (queue_name, member_name, member_interface, penalty, paused, uniqueid, ringinuse)
VALUES
    ('ai-bot-queue', 'AI Bot Agent', 'PJSIP/1000', 0, 0, 'ai-bot-agent', 0)
ON CONFLICT DO NOTHING;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_queue_members_queue_name ON queue_members(queue_name);
CREATE INDEX IF NOT EXISTS idx_queue_members_member_name ON queue_members(member_name);
CREATE INDEX IF NOT EXISTS idx_queues_name ON queues(name);
CREATE INDEX IF NOT EXISTS idx_agents_agent_id ON agents(agent_id);

-- Create view for queue statistics
CREATE OR REPLACE VIEW queue_stats AS
SELECT
    q.name as queue_name,
    q.strategy,
    q.timeout,
    q.retry,
    q.maxlen,
    COUNT(qm.id) as member_count,
    COUNT(CASE WHEN qm.paused = 0 THEN 1 END) as active_members,
    COUNT(CASE WHEN qm.paused = 1 THEN 1 END) as paused_members,
    q.created_at,
    q.updated_at
FROM queues q
LEFT JOIN queue_members qm ON q.name = qm.queue_name
GROUP BY q.id, q.name, q.strategy, q.timeout, q.retry, q.maxlen, q.created_at, q.updated_at;

-- Create view for agent statistics
CREATE OR REPLACE VIEW agent_stats AS
SELECT
    a.agent_id,
    a.name,
    a.context,
    a.language,
    a.timezone,
    a.wrapuptime,
    a.maxloginattempts,
    a.logoffaftercall,
    a.ackcall,
    a.endcall,
    a.updatecdr,
    a.autologoff,
    a.autologoffunavail,
    a.created_at,
    a.updated_at
FROM agents a;

-- Grant permissions to asterisk user
GRANT SELECT, INSERT, UPDATE, DELETE ON queues TO asterisk;
GRANT SELECT, INSERT, UPDATE, DELETE ON queue_members TO asterisk;
GRANT SELECT, INSERT, UPDATE, DELETE ON agents TO asterisk;
GRANT SELECT ON queue_stats TO asterisk;
GRANT SELECT ON agent_stats TO asterisk;

-- Grant sequence permissions
GRANT USAGE, SELECT ON SEQUENCE queues_id_seq TO asterisk;
GRANT USAGE, SELECT ON SEQUENCE queue_members_id_seq TO asterisk;
GRANT USAGE, SELECT ON SEQUENCE agents_id_seq TO asterisk;
