import { useState, useEffect } from 'react';
import { userRegistry, UserProfile } from './user-registry';

/**
 * React hook for using the user registry in components
 */
export function useUserRegistry() {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    // Subscribe to registry changes
    const unsubscribe = userRegistry.subscribe((updatedUsers) => {
      setUsers(updatedUsers);
      setLoading(false);
    });
    
    // Trigger a sync to ensure data is up-to-date
    userRegistry.sync().catch(console.error);
    
    // Cleanup on unmount
    return unsubscribe;
  }, []);
  
  return {
    users,
    loading,
    getUser: (id: string) => userRegistry.getUserById(id),
    updateActivity: (userId: string) => userRegistry.updateUserActivity(userId),
    refreshUsers: () => userRegistry.sync()
  };
}

/**
 * Hook for using a specific user's data
 */
export function useUser(userId: string | undefined) {
  const [user, setUser] = useState<UserProfile | undefined>(
    userId ? userRegistry.getUserById(userId) : undefined
  );
  
  useEffect(() => {
    if (!userId) {
      setUser(undefined);
      return;
    }
    
    // Get initial state
    setUser(userRegistry.getUserById(userId));
    
    // Subscribe to changes
    const unsubscribe = userRegistry.subscribe((users) => {
      const updatedUser = users.find(u => u.id === userId);
      setUser(updatedUser);
    });
    
    return unsubscribe;
  }, [userId]);
  
  return {
    user,
    updateActivity: () => userId && userRegistry.updateUserActivity(userId),
    registerAuth: (deviceInfo: any) => userId && userRegistry.registerAuthEvent(userId, deviceInfo)
  };
} 