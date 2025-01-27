import { supabase } from '../../supabase/client';
import { shell } from 'electron';

// Using localhost for development, this will be caught by our protocol handler
const SITE_URL = 'http://localhost:3000/auth/callback';
const SUPABASE_STORAGE_KEY = 'sb';

// Helper to get stored session
function getStoredSession() {
    const accessToken = localStorage.getItem(`${SUPABASE_STORAGE_KEY}-access-token`);
    const refreshToken = localStorage.getItem(`${SUPABASE_STORAGE_KEY}-refresh-token`);
    return { accessToken, refreshToken };
}

export async function handleLogin(email: string, password: string): Promise<{ success: boolean; error?: string }> {
    try {
        const { data, error } = await supabase.auth.signInWithPassword({
            email,
            password
        });

        if (error) throw error;

        return { success: true };
    } catch (error: any) {
        return { 
            success: false, 
            error: error?.message || 'An error occurred during login'
        };
    }
}

export async function handleSignup(email: string, password: string): Promise<{ success: boolean; error?: string }> {
    const { accessToken, refreshToken } = getStoredSession();
    try {
        const { data, error } = await supabase.auth.signUp({
            email,
            password,
            options: {
                emailRedirectTo: SITE_URL
            }
        });

        if (error) throw error;

        return { 
            success: true,
            error: 'Signup successful! Please check your email for verification.'
        };
    } catch (error: any) {
        return { 
            success: false, 
            error: error?.message || 'An error occurred during signup'
        };
    }
}

export async function handleLogout(): Promise<void> {
    await supabase.auth.signOut();
}

export async function checkSession(): Promise<boolean> {
    const { data: { session } } = await supabase.auth.getSession();
    return session !== null;
}

export async function getUserSecurityTier(): Promise<{ tier: string; description: string }> {
    try {
        const { data: { user } } = await supabase.auth.getUser();
        
        if (!user) {
            return {
                tier: 'UNKNOWN',
                description: 'Unable to retrieve security status. Please sign in again.'
            };
        }

        const { data: securityData, error } = await supabase
            .from('user_security')
            .select('tier, last_updated')
            .eq('id', user.id)
            .single();

        if (error) {
            console.error('Error fetching security tier:', error);
            return {
                tier: 'ERROR',
                description: 'Unable to retrieve security status. Please try again later.'
            };
        }

        let description = '';
        switch (securityData.tier) {
            case 'RELIABLE':
                description = 'Your system activity indicates normal behavior patterns. Continue maintaining good security practices.';
                break;
            case 'DISRUPTIVE':
                description = 'Some unusual activity has been detected. Please review your recent actions and security settings.';
                break;
            case 'CRITICAL':
                description = 'Critical security concerns detected. Immediate action required. Contact your system administrator.';
                break;
            default:
                description = 'System is monitoring your activity patterns.';
        }

        return {
            tier: securityData.tier,
            description
        };
    } catch (error) {
        console.error('Error in getUserSecurityTier:', error);
        return {
            tier: 'ERROR',
            description: 'Unable to retrieve security status. Please try again later.'
        };
    }
}
