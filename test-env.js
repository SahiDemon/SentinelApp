import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables from cred.env (preferred) or .env
function loadEnvironment() {
  const appRoot = process.cwd();
  const credEnvPath = path.join(appRoot, 'cred.env');
  const defaultEnvPath = path.join(appRoot, '.env');
  
  try {
    // Try cred.env first
    if (fs.existsSync(credEnvPath)) {
      console.log('Loading environment from cred.env');
      const envConfig = dotenv.parse(fs.readFileSync(credEnvPath));
      for (const key in envConfig) {
        process.env[key] = envConfig[key];
      }
      return true;
    }
    // Fall back to .env
    else if (fs.existsSync(defaultEnvPath)) {
      console.log('Loading environment from .env');
      const envConfig = dotenv.parse(fs.readFileSync(defaultEnvPath));
      for (const key in envConfig) {
        process.env[key] = envConfig[key];
      }
      return true;
    }
  } catch (error) {
    console.error('Error loading environment files:', error);
  }
  
  console.warn('No environment file (cred.env or .env) found');
  return false;
}

// Load environment variables
const result = loadEnvironment();
console.log(`Load environment result: ${result}`);

// List of environment variables to check
const variables = [
  // Supabase variables
  "SUPABASE_URL",
  "SUPABASE_ANON_KEY",
  "SUPABASE_KEY",
  
  // Sentinel API variables
  "SENTINEL_PRIME_API_URL",
  "SENTINEL_PRIME_API_KEY",
  
  // OpenSearch variables
  "OPENSEARCH_TIMEOUT",
  "OPENSEARCH_RETRY",
  "OPENSEARCH_HOST",
  "OPENSEARCH_PORT",
  "OPENSEARCH_USERNAME",
  "OPENSEARCH_PASSWORD",
  "OPENSEARCH_INDEX",
  
  // System variables
  "SENTINEL_INTEGRATED",
  "PORT"
];

console.log("\nEnvironment variables:");
for (const variable of variables) {
  const value = process.env[variable];
  const maskedValue = value && (variable.endsWith("KEY") || variable.endsWith("ANON_KEY") || variable.endsWith("PASSWORD"))
    ? "***" 
    : value;
  // Use plain console.log with formatting to ensure we see all output
  console.log(`  ${variable.padEnd(25)}: ${maskedValue || 'Not set'}`);
}

// Count how many variables are set
const setCount = variables.filter(variable => process.env[variable]).length;
console.log(`\nVariables set: ${setCount}/${variables.length}`);

// Check if all essential variables are set
const allSet = variables.every(variable => process.env[variable]);
console.log(`All essential variables set: ${allSet}`); 