BEGIN;

-- Create security tier enum
CREATE TYPE security_tier AS ENUM ('CRITICAL', 'DISRUPTIVE', 'RELIABLE', 'TRUSTED');

-- Create user security table
CREATE TABLE user_security (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    tier security_tier NOT NULL DEFAULT 'RELIABLE',
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE user_security ENABLE ROW LEVEL SECURITY;

-- Create policies
CREATE POLICY "Users can view own security status"
    ON user_security FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Enable insert for service role"
    ON user_security FOR INSERT
    TO service_role
    WITH CHECK (true);

CREATE POLICY "Enable update for service role"
    ON user_security FOR UPDATE
    TO service_role
    USING (true);

-- Create index
CREATE INDEX idx_user_security_tier ON user_security(tier);

-- Create function to update last_updated timestamp
CREATE OR REPLACE FUNCTION update_last_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for last_updated
CREATE TRIGGER trigger_update_last_updated
    BEFORE UPDATE ON user_security
    FOR EACH ROW
    EXECUTE FUNCTION update_last_updated();

-- Create function to handle new user signups
CREATE OR REPLACE FUNCTION handle_new_user_security()
RETURNS trigger SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.user_security (id, tier)
    VALUES (NEW.id, 'RELIABLE')
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for new users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user_security();

-- Create admin user if not exists
DO $$
DECLARE 
    admin_id uuid;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE email = 'admin@sentinel.local') THEN
        INSERT INTO auth.users (
            instance_id,
            id,
            aud,
            role,
            email,
            encrypted_password,
            email_confirmed_at,
            created_at,
            updated_at,
            raw_app_meta_data,
            raw_user_meta_data
        ) VALUES (
            '00000000-0000-0000-0000-000000000000',
            gen_random_uuid(),
            'authenticated',
            'authenticated',
            'admin@sentinel.local',
            crypt('Admin123!@#', gen_salt('bf')),
            NOW(),
            NOW(),
            NOW(),
            '{"provider":"email","providers":["email"]}'::jsonb,
            '{"full_name":"System Administrator"}'::jsonb
        )
        RETURNING id INTO admin_id;

        -- Set admin to trusted tier
        UPDATE user_security 
        SET tier = 'TRUSTED' 
        WHERE id = admin_id;
    END IF;
END
$$;

-- Grant permissions
GRANT ALL ON TABLE user_security TO postgres, service_role;
GRANT SELECT, UPDATE ON TABLE user_security TO authenticated;
GRANT USAGE ON TYPE security_tier TO postgres, service_role, authenticated;
GRANT EXECUTE ON FUNCTION handle_new_user_security TO postgres, service_role;
GRANT EXECUTE ON FUNCTION update_last_updated TO postgres, service_role, authenticated;

COMMIT;
