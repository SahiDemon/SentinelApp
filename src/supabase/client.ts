import { createClient } from '@supabase/supabase-js';

const supabaseUrl = 'https://qackdhpbvfbeyhxovlqj.supabase.co';
const supabaseAnonKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhY2tkaHBidmZiZXloeG92bHFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzc5NTUzNzIsImV4cCI6MjA1MzUzMTM3Mn0.JZbYaTngJy3lGFqtvI3efcmxdosdmD48Nv2zgTeaHY0';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
