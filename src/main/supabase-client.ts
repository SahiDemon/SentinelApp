import { createClient } from '@supabase/supabase-js';
import path from 'path';
import fs from 'fs';
import dotenv from 'dotenv';

// Load environment variables from .env file if it exists
let supabaseUrl = process.env.SUPABASE_URL || '';
let supabaseKey = process.env.SUPABASE_ANON_KEY || '';

// Try to load from .env or cred.env file in app root if environment variables not set
if (!supabaseUrl || !supabaseKey) {
    try {
        // Try cred.env first, then fall back to .env
        const credEnvPath = path.resolve(process.cwd(), 'cred.env');
        const defaultEnvPath = path.resolve(process.cwd(), '.env');
        
        // Check for cred.env first
        if (fs.existsSync(credEnvPath)) {
            console.log('Loading credentials from cred.env');
            const envConfig = dotenv.parse(fs.readFileSync(credEnvPath));
            supabaseUrl = envConfig.SUPABASE_URL || '';
            supabaseKey = envConfig.SUPABASE_ANON_KEY || '';
        }
        // If not found or values are still empty, try .env
        else if (fs.existsSync(defaultEnvPath)) {
            console.log('Loading credentials from .env');
            const envConfig = dotenv.parse(fs.readFileSync(defaultEnvPath));
            supabaseUrl = envConfig.SUPABASE_URL || '';
            supabaseKey = envConfig.SUPABASE_ANON_KEY || '';
        }
    } catch (error) {
        console.error('Error loading environment files:', error);
    }
}

// Default values for development (these will be overwritten by .env in production)
if (!supabaseUrl || !supabaseKey) {
    console.warn('No Supabase credentials found in environment, using default development values');
    supabaseUrl = 'https://qackdhpbvfbeyhxovlqj.supabase.co';
    supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhY2tkaHBidmZiZXloeG92bHFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzc5NTUzNzIsImV4cCI6MjA1MzUzMTM3Mn0.JZbYaTngJy3lGFqtvI3efcmxdosdmD48Nv2zgTeaHY0';
}

// Create a single Supabase client for interacting with your database
const supabase = createClient(supabaseUrl, supabaseKey);

export async function getMonitorConfigurations(userId: string | null): Promise<{ [key: string]: boolean } | null> {
    if (!userId) {
        console.error('No user ID provided for getMonitorConfigurations');
        return null;
    }

    try {
        // Debug logs
        console.log('Getting monitor configurations for user ID:', userId);
        
        // Modified query to get both user-specific AND global configurations
        const { data, error } = await supabase
            .from('monitor_configurations')
            .select('*')
            .or('user_id.eq.' + userId + ',scope.eq.global')
            .order('created_at', { ascending: false });

        if (error) {
            console.error('Error fetching monitor configurations:', error);
            return null;
        }

        if (!data || data.length === 0) {
            console.log('No monitor configurations found for user:', userId);
            return null;
        }

        console.log(`Found ${data.length} configurations combining user-specific and global`);
        // Debug: Log first result to see structure
        console.log('Sample configuration:', data[0]);

        // Transform the data into the expected format
        // Combine all configurations with the same monitor_type, using the latest one
        const monitorConfigurations: { [key: string]: boolean } = {};
        const processed = new Set<string>();

        // Process configurations from newest to oldest
        for (const config of data) {
            const monitorType = config.monitor_type;
            
            // Skip if we've already processed this monitor type
            if (processed.has(monitorType)) continue;
            
            // Add to processed set to mark this monitor type as handled
            processed.add(monitorType);
            
            // Add to result with the enabled status - handle both column name possibilities
            const isEnabled = typeof config.is_enabled !== 'undefined' ? 
                config.is_enabled : 
                (typeof config.enabled !== 'undefined' ? config.enabled : true);
                
            monitorConfigurations[monitorType] = isEnabled;
        }

        console.log('Fetched monitor configurations from Supabase:', monitorConfigurations);
        return monitorConfigurations;
    } catch (error) {
        console.error('Exception in getMonitorConfigurations:', error);
        return null;
    }
}

export default supabase; 