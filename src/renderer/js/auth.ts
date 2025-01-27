import { supabase } from '../../supabase/client';

const SESSION_KEY = 'sentinel_session';

export interface UserSession {
    email: string | null;
    id: string;
}

export async function handleLogin(email: string, password: string, rememberSession: boolean = false): Promise<{ success: boolean; error?: string }> {
    try {
        const { data, error } = await supabase.auth.signInWithPassword({
            email,
            password
        });

        if (error) throw error;
        
        // Store session if remember me is checked
        if (rememberSession && data.session) {
            localStorage.setItem(SESSION_KEY, JSON.stringify({
                email: data.user?.email || null,
                id: data.user?.id
            }));
        }

        return { success: true };
    } catch (error: any) {
        return { 
            success: false, 
            error: error?.message || 'An error occurred during login'
        };
    }
}

export async function handleLogout(): Promise<void> {
    await supabase.auth.signOut();
    localStorage.removeItem(SESSION_KEY);
}

export async function getCurrentUser(): Promise<UserSession | null> {
    try {
        // First check for session in Supabase
        const { data: { user } } = await supabase.auth.getUser();
        if (user) {
            return {
                email: user.email || null,
                id: user.id
            };
        }
        
        // If no active session, check local storage
        const savedSession = localStorage.getItem(SESSION_KEY);
        if (savedSession) {
            const parsed = JSON.parse(savedSession);
            return {
                email: parsed.email || null,
                id: parsed.id
            };
        }
        
        return null;
    } catch (error) {
        console.error('Error getting current user:', error);
        return null;
    }
}

export async function checkSession(): Promise<boolean> {
    const user = await getCurrentUser();
    return user !== null;
}

export async function getUserSecurityTier(): Promise<{ tier: string; description: string }> {
    try {
        const user = await getCurrentUser();
        
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
