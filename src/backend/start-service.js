const { spawn, exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const isElevated = require('is-elevated');
const sudoPrompt = require('sudo-prompt');

const SERVICE_PATH = path.join(__dirname, 'sentinel-service.js');
const SERVICE_PORT = process.env.PORT || 3999;

// Keep track of the service process
let serviceProcess = null;

// Install dependencies if they don't exist
function ensureDependencies() {
    try {
        // Check if node_modules exists in the backend directory
        const moduleDir = path.join(__dirname, 'node_modules');
        if (!fs.existsSync(moduleDir)) {
            console.log('Installing backend service dependencies...');
            const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
            const install = spawn(npm, ['install', '--no-audit', '--no-fund', 'express', 'cors', 'is-elevated', 'sudo-prompt'], {
                cwd: __dirname,
                stdio: 'inherit'
            });
            
            return new Promise((resolve) => {
                install.on('close', (code) => {
                    if (code === 0) {
                        console.log('Dependencies installed successfully');
                        resolve(true);
                    } else {
                        console.error(`Failed to install dependencies (exit code: ${code})`);
                        resolve(false);
                    }
                });
            });
        }
        return Promise.resolve(true);
    } catch (error) {
        console.error('Error installing dependencies:', error);
        return Promise.resolve(false);
    }
}

// Check if the service is already running
async function checkServiceRunning() {
    try {
        const response = await fetch(`http://localhost:${SERVICE_PORT}/status`);
        if (response.ok) {
            const data = await response.json();
            return data.running;
        }
    } catch (error) {
        // Service is not running or not responding
        return false;
    }
    return false;
}

// Start the service in normal mode
function startService() {
    console.log('Starting Sentinel service in normal mode...');
    serviceProcess = spawn('node', [SERVICE_PATH], {
        detached: true,
        stdio: 'pipe',  // Changed from 'ignore' to 'pipe' to capture output
        windowsHide: true
    });
    
    // Capture output for debugging
    serviceProcess.stdout.on('data', (data) => {
        console.log(`Service output: ${data.toString().trim()}`);
    });
    
    serviceProcess.stderr.on('data', (data) => {
        console.error(`Service error: ${data.toString().trim()}`);
    });
    
    // Handle exit
    serviceProcess.on('close', (code) => {
        console.log(`Service process exited with code ${code}`);
        serviceProcess = null;
    });
    
    // Don't unref to keep the parent process alive
    // serviceProcess.unref();
    
    console.log(`Sentinel service started with PID: ${serviceProcess.pid}`);
    console.log(`Service will be available at http://localhost:${SERVICE_PORT}`);
    
    return serviceProcess.pid;
}

// Start the service with admin privileges
function startServiceWithAdmin() {
    return new Promise((resolve) => {
        console.log('Requesting admin privileges to start Sentinel service...');
        
        const options = {
            name: 'Sentinel Security Service',
            icns: path.join(__dirname, '..', '..', 'assets', 'sentinalprime.png'), // Optional icon for macOS
        };
        
        const command = process.platform === 'win32'
            ? `start /b node "${SERVICE_PATH}"`
            : `node "${SERVICE_PATH}" &`;
            
        sudoPrompt.exec(command, options, (error, stdout, stderr) => {
            if (error) {
                console.error('Failed to start with admin privileges:', error);
                console.log('Falling back to normal mode...');
                const pid = startService();
                resolve(pid);
            } else {
                console.log('Service started with admin privileges');
                console.log(`Service will be available at http://localhost:${SERVICE_PORT}`);
                if (stdout) console.log('Output:', stdout);
                if (stderr) console.error('Error:', stderr);
                resolve(true);
            }
        });
    });
}

// Kill any existing process using the service port
function killExistingService() {
    return new Promise((resolve) => {
        console.log(`Checking for existing service on port ${SERVICE_PORT}...`);
        
        if (process.platform === 'win32') {
            // Windows command needs to be executed differently
            exec(`netstat -ano | findstr ":${SERVICE_PORT}" | findstr "LISTENING"`, (error, stdout) => {
                if (error || !stdout) {
                    console.log('No existing service found on port.');
                    return resolve();
                }
                
                // Extract PID from the output
                const lines = stdout.trim().split('\n');
                for (const line of lines) {
                    // The PID is the last column
                    const parts = line.trim().split(/\s+/);
                    const pid = parts[parts.length - 1];
                    
                    if (pid && !isNaN(parseInt(pid))) {
                        console.log(`Found process using port ${SERVICE_PORT}: PID ${pid}`);
                        // Kill the process
                        exec(`taskkill /PID ${pid} /F`, (killError, killStdout) => {
                            if (killError) {
                                console.error(`Failed to kill process: ${killError.message}`);
                            } else {
                                console.log(`Successfully killed process with PID ${pid}`);
                                console.log(killStdout);
                            }
                            // Continue after a short delay
                            setTimeout(resolve, 1000);
                        });
                        return;
                    }
                }
                
                console.log('Could not parse PID from netstat output');
                resolve();
            });
        } else {
            // Unix command
            exec(`lsof -i :${SERVICE_PORT} | grep LISTEN | awk '{print $2}' | xargs kill -9`, (error) => {
                if (error) {
                    console.log('No existing service found or could not terminate.');
                } else {
                    console.log('Terminated existing service process.');
                }
                setTimeout(resolve, 1000);
            });
        }
    });
}

// Main function to start the service
async function main() {
    try {
        // Ensure dependencies are installed
        const depsInstalled = await ensureDependencies();
        if (!depsInstalled) {
            console.error('Failed to install required dependencies');
            process.exit(1);
        }
        
        // Check if service is already running
        const isRunning = await checkServiceRunning();
        if (isRunning) {
            console.log('Sentinel service is already running, attempting to terminate it...');
            await killExistingService();
        }
        
        // Check if we have admin privileges
        const elevated = await isElevated;
        
        if (elevated) {
            console.log('Running with admin privileges, starting service...');
            startService();
            
            // Keep the main process alive
            console.log('Monitoring service. Press Ctrl+C to exit.');
        } else {
            // Try to get admin privileges
            await startServiceWithAdmin();
            
            // Keep the main process alive if we started a service
            console.log('Monitoring service. Press Ctrl+C to exit.');
        }
        
        // Prevent the script from exiting
        process.stdin.resume();
        
        // Handle process termination
        process.on('SIGINT', () => {
            console.log('Received SIGINT. Shutting down service...');
            if (serviceProcess) {
                serviceProcess.kill();
            }
            process.exit(0);
        });
        
    } catch (error) {
        console.error('Error starting service:', error);
        process.exit(1);
    }
}

// Run main function
main().catch(console.error); 