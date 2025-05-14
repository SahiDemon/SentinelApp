import { supabase } from './client';

export interface UserProfile {
  id: string;
  email: string;
  created_at: string;
  last_seen?: string;
  metadata?: any;
  is_banned?: boolean;
  security_tier?: string;
  risk_score?: number;
}

interface UserRegistryState {
  users: Map<string, UserProfile>;
  lastSyncTime: Date | null;
  syncing: boolean;
}

/**
 * User Registry class for maintaining a synchronized local cache of users
 * This serves as a central source of truth for user data in the app
 */
class UserRegistry {
  private state: UserRegistryState = {
    users: new Map(),
    lastSyncTime: null,
    syncing: false
  };
  
  // Event listeners
  private listeners: ((users: UserProfile[]) => void)[] = [];
  
  constructor() {
    // Initial sync
    this.sync();
    
    // Set up auto-sync every 15 minutes
    setInterval(() => this.sync(), 15 * 60 * 1000);
  }
  
  /**
   * Sync user data from Supabase
   */
  async sync(): Promise<void> {
    if (this.state.syncing) return;
    
    try {
      this.state.syncing = true;
      
      // Fetch users from Supabase's user view
      const { data: users, error } = await supabase
        .from('user_list')
        .select('*');
      
      if (error) {
        console.error('Error syncing user registry:', error);
        return;
      }
      
      // Fetch security information
      const { data: securityData, error: securityError } = await supabase
        .from('user_security')
        .select('id, tier, risk_score, last_updated');
        
      if (securityError) {
        console.error('Error fetching security data:', securityError);
      }
      
      // Create security lookup map
      const securityMap = new Map();
      if (securityData) {
        securityData.forEach(item => {
          securityMap.set(item.id, {
            security_tier: item.tier,
            risk_score: item.risk_score,
            security_updated: item.last_updated
          });
        });
      }
      
      // Update local cache
      if (users) {
        const userMap = new Map();
        
        users.forEach(user => {
          // Merge with security data
          const securityInfo = securityMap.get(user.id) || {};
          const userData: UserProfile = {
            ...user,
            ...securityInfo
          };
          
          userMap.set(user.id, userData);
        });
        
        this.state.users = userMap;
        this.state.lastSyncTime = new Date();
        
        // Notify listeners
        this.notifyListeners();
      }
    } catch (err) {
      console.error('Unexpected error in user registry sync:', err);
    } finally {
      this.state.syncing = false;
    }
  }
  
  /**
   * Get all users from the registry
   */
  getUsers(): UserProfile[] {
    return Array.from(this.state.users.values());
  }
  
  /**
   * Get a specific user by ID
   */
  getUserById(id: string): UserProfile | undefined {
    return this.state.users.get(id);
  }
  
  /**
   * Update a user's last seen timestamp
   */
  async updateUserActivity(userId: string): Promise<void> {
    try {
      // Update in Supabase
      const { error } = await supabase
        .from('user_activity')
        .upsert({
          user_id: userId,
          last_seen: new Date().toISOString()
        }, {
          onConflict: 'user_id'
        });
        
      if (error) {
        console.error('Error updating user activity:', error);
        return;
      }
      
      // Update local cache
      const user = this.state.users.get(userId);
      if (user) {
        user.last_seen = new Date().toISOString();
        this.state.users.set(userId, user);
      }
    } catch (err) {
      console.error('Error in updateUserActivity:', err);
    }
  }
  
  /**
   * Register an authentication event
   * This helps correlate user sessions across devices
   */
  async registerAuthEvent(userId: string, deviceInfo: any): Promise<string> {
    try {
      // Create a correlation ID
      const correlationId = `${userId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      
      // Register the auth event
      const { error } = await supabase
        .from('auth_events')
        .insert({
          user_id: userId,
          correlation_id: correlationId,
          device_info: deviceInfo,
          timestamp: new Date().toISOString()
        });
        
      if (error) {
        console.error('Error registering auth event:', error);
        return '';
      }
      
      return correlationId;
    } catch (err) {
      console.error('Error in registerAuthEvent:', err);
      return '';
    }
  }
  
  /**
   * Subscribe to user registry changes
   */
  subscribe(callback: (users: UserProfile[]) => void): () => void {
    this.listeners.push(callback);
    
    // Immediately notify with current data
    callback(this.getUsers());
    
    // Return unsubscribe function
    return () => {
      this.listeners = this.listeners.filter(l => l !== callback);
    };
  }
  
  /**
   * Notify all listeners of changes
   */
  private notifyListeners(): void {
    const users = this.getUsers();
    this.listeners.forEach(listener => listener(users));
  }
}

// Create singleton instance
export const userRegistry = new UserRegistry(); 