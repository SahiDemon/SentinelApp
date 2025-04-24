const { spawn } = require('child_process');
const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const app = express();
const port = process.env.PORT || 3999;

// Enable CORS
app.use(cors());
app.use(express.json());

// Store process information
let sentinelProcess = null;
let processInfo = {
    running: false,
    pid: null,
    startTime: null,
    adminMode: false,
    adminRequired: false,
    userId: null,
    monitorStatus: {},
    lastUpdate: null,
    lastError: null
};

// Middleware to log all requests
app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} - ${req.method} ${req.url}`);
    next();
});

// Get application root directory
const findRootDir = () => {
    // Try different possible paths
    const possiblePaths = [
        path.join(__dirname, '..', '..'),
        path.join(__dirname, '..'),
        __dirname
    ];
    
    for (const dir of possiblePaths) {
        if (fs.existsSync(path.join(dir, 'src', 'python', 'sentinel.py'))) {
            return dir;
        }
    }
    
    console.error('Could not find sentinel.py in any of the expected locations');
    return __dirname;
};

const rootDir = findRootDir();
console.log(`Application root directory: ${rootDir}`);

// API endpoints
app.get('/status', (req, res) => {
    // Check if the process is still running
    if (sentinelProcess && processInfo.running) {
        try {
            // Kill with signal 0 just tests if the process exists
            process.kill(sentinelProcess.pid, 0);
            
            // Update last check time
            processInfo.lastUpdate = Date.now();
        } catch (e) {
            // Process doesn't exist anymore
            processInfo.running = false;
            sentinelProcess = null;
            console.log('Process was terminated externally');
        }
    }
    
    res.json({
        ...processInfo,
        uptime: processInfo.startTime ? (Date.now() - processInfo.startTime) / 1000 : 0
    });
});

app.post('/start', (req, res) => {
    const { userId } = req.body || {};
    
    // If process is already running, return its status
    if (sentinelProcess && processInfo.running) {
        // If userId changed, restart the process
        if (userId !== processInfo.userId) {
            stopSentinel();
        } else {
            return res.json({
                success: true,
                message: 'Sentinel is already running',
                ...processInfo
            });
        }
    }
    
    const success = startSentinel(userId);
    if (success) {
        res.json({
            success: true,
            message: 'Sentinel started successfully',
            ...processInfo
        });
    } else {
        res.status(500).json({
            success: false,
            message: 'Failed to start Sentinel',
            ...processInfo
        });
    }
});

app.post('/stop', (req, res) => {
    if (!sentinelProcess) {
        return res.json({
            success: true,
            message: 'Sentinel is not running',
            running: false
        });
    }
    
    const success = stopSentinel();
    res.json({
        success,
        message: success ? 'Sentinel stopped successfully' : 'Failed to stop Sentinel',
        running: !success
    });
});

// Helper functions
function startSentinel(userId = null) {
    try {
        // Check if sentinel.py exists
        const pythonScriptPath = path.join(rootDir, 'src', 'python', 'sentinel.py');
        if (!fs.existsSync(pythonScriptPath)) {
            console.error(`Python script not found at ${pythonScriptPath}`);
            return false;
        }
        
        // Build command arguments
        const args = [pythonScriptPath];
        if (userId) {
            args.push('--user-id', userId);
        }
        
        // Determine Python executable
        const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
        
        console.log(`Starting sentinel with command: ${pythonExecutable} ${args.join(' ')}`);
        
        // Reset admin required flag
        processInfo.adminRequired = false;
        processInfo.lastError = null;
        
        // Spawn the process
        sentinelProcess = spawn(pythonExecutable, args, {
            stdio: 'pipe',
            windowsHide: true,
            detached: false
        });
        
        // Check if process started successfully
        if (!sentinelProcess || !sentinelProcess.pid) {
            console.error('Failed to start sentinel process');
            return false;
        }
        
        // Update process info
        processInfo = {
            running: true,
            pid: sentinelProcess.pid,
            startTime: Date.now(),
            adminMode: false, // Will be updated by the Python script
            adminRequired: false,
            userId: userId,
            monitorStatus: {},
            lastUpdate: Date.now(),
            lastError: null
        };
        
        // Handle process output
        sentinelProcess.stdout.on('data', (data) => {
            const output = data.toString().trim();
            console.log(`Sentinel output: ${output}`);
            
            // Check for admin mode indicator
            if (output.includes('Admin privileges: YES')) {
                processInfo.adminMode = true;
            }
            
            // Check for admin privileges message
            if (output.includes('requires administrator privileges') || 
                output.includes('run as administrator')) {
                processInfo.adminRequired = true;
                processInfo.lastError = 'Administrator privileges required';
            }
            
            // Parse monitor status from output
            if (output.includes('Monitor Status')) {
                const statusLine = output.split('|')[1]?.trim();
                if (statusLine) {
                    const statuses = statusLine.split('|').map(s => s.trim());
                    statuses.forEach(status => {
                        const [name, state] = status.split(':').map(s => s.trim());
                        if (name && state) {
                            processInfo.monitorStatus[name] = state === 'Running';
                        }
                    });
                }
            }
        });
        
        sentinelProcess.stderr.on('data', (data) => {
            const errorOutput = data.toString().trim();
            console.error(`Sentinel error: ${errorOutput}`);
            
            // Check for admin privileges error
            if (errorOutput.includes('requires administrator privileges') || 
                errorOutput.includes('run as administrator')) {
                processInfo.adminRequired = true;
                processInfo.lastError = 'Administrator privileges required';
            } else if (!processInfo.lastError) {
                processInfo.lastError = errorOutput;
            }
        });
        
        sentinelProcess.on('close', (code) => {
            console.log(`Sentinel process exited with code ${code}`);
            processInfo.running = false;
            sentinelProcess = null;
            
            // If process exited with error code but we don't have a specific error
            if (code !== 0 && !processInfo.lastError) {
                processInfo.lastError = `Process exited with code ${code}`;
            }
        });
        
        sentinelProcess.on('error', (err) => {
            console.error(`Error starting sentinel: ${err.message}`);
            processInfo.running = false;
            processInfo.lastError = err.message;
            sentinelProcess = null;
        });
        
        return true;
        
    } catch (error) {
        console.error(`Failed to start sentinel: ${error.message}`);
        processInfo.lastError = error.message;
        return false;
    }
}

function stopSentinel() {
    if (!sentinelProcess) {
        return true;
    }
    
    try {
        // Use different termination methods based on platform
        if (process.platform === 'win32') {
            // On Windows, use taskkill to ensure child processes are also terminated
            spawn('taskkill', ['/pid', sentinelProcess.pid, '/f', '/t']);
        } else {
            // On Unix systems, kill the process group
            process.kill(-sentinelProcess.pid, 'SIGTERM');
        }
        
        // Update process info
        processInfo.running = false;
        sentinelProcess = null;
        
        return true;
    } catch (error) {
        console.error(`Failed to stop sentinel: ${error.message}`);
        return false;
    }
}

// Start the service
app.listen(port, () => {
    console.log(`Sentinel service running on port ${port}`);
});

// Handle process termination
process.on('exit', () => {
    if (sentinelProcess) {
        stopSentinel();
    }
});

// Handle unexpected exceptions
process.on('uncaughtException', (err) => {
    console.error('Uncaught exception:', err);
    if (sentinelProcess) {
        stopSentinel();
    }
    process.exit(1);
}); 