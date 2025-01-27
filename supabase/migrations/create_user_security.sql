-- Create enum type for security tiers
CREATE TYPE security_tier AS ENUM ('CRITICAL', 'DISRUPTIVE', 'RELIABLE');

-- Create user security table
CREATE TABLE user_security (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    tier security_tier NOT NULL DEFAULT 'RELIABLE',
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    login_attempts INT DEFAULT 0,
    suspicious_activities TEXT[],
    last_activity TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW())
);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc'::text, NOW());
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for updated_at
CREATE TRIGGER update_user_security_updated_at
    BEFORE UPDATE ON user_security
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

-- Create trigger to automatically create user_security entry when a new user signs up
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_security (id)
    VALUES (NEW.id);
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add trigger to auth.users table
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE handle_new_user();

-- Set up row level security
ALTER TABLE user_security ENABLE ROW LEVEL SECURITY;

-- Create policies
CREATE POLICY "Users can view their own security status"
    ON user_security FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Only system can update security status"
    ON user_security FOR UPDATE
    USING (auth.uid() = id);
