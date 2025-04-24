import { app, BrowserWindow, protocol, ipcMain, Tray, Menu, nativeImage, dialog } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import os from 'os';
import { spawn, ChildProcess, exec } from 'child_process';
import fs from 'fs';
import http from 'http';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuration for admin requirement
const appConfig = {
    requireAdminPrivileges: false 
};

// Is the app running with admin privileges?
let isRunningAsAdmin = true;

interface CpuTimes {
    user: number;
    nice: number;
    sys: number;
    idle: number;
    irq: number;
}

// Function to check if we have admin privileges
async function checkAdminPrivileges(): Promise<boolean> {
    try {
        // Even in development mode, we should check for admin privileges properly
        if (process.platform === 'win32') {
            // Use exec from the already imported child_process
            // instead of dynamically requiring execSync
            return new Promise((resolve) => {
                exec('powershell -command "([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"', 
                    (error, stdout) => {
                        if (error) {
                            console.error('Error checking admin rights:', error);
                            resolve(false);
                            return;
                        }
                        const isAdmin = stdout.trim() === 'True';
                        console.log(`Admin privileges check result: ${isAdmin}`);
                        resolve(isAdmin);
                    }
                );
            });
        } else if (process.platform === 'darwin' || process.platform === 'linux') {
            // Unix-like: check if user ID is 0 (root)
            const isRoot = typeof process.getuid === 'function' && process.getuid() === 0;
            console.log(`Admin privileges check result (root): ${isRoot}`);
            return isRoot;
        }
        return false;
    } catch (error) {
        console.error('Error checking admin privileges:', error);
        return false;
    }
}

// Function to restart the app with admin privileges
async function restartWithAdminPrivileges(): Promise<boolean> {
    const isAdmin = await checkAdminPrivileges();
    if (isAdmin) {
        isRunningAsAdmin = true;
        return true; // Already running as admin
    }

    if (process.platform === 'win32') {
        console.log('Restarting app with admin privileges...');
        const appPath = process.execPath;
        
        // Fix the PowerShell command format - specifically handle the ArgumentList properly
        const psCommand = `Start-Process -Verb RunAs -FilePath "${appPath}" -ArgumentList "."`;
        
        exec(`powershell -Command "${psCommand}"`, (error) => {
            if (error) {
                console.error('Failed to restart with admin privileges:', error);
                dialog.showErrorBox(
                    'Admin Privileges Required',
                    'This application requires administrator privileges to run properly. Please restart it as administrator.'
                );
            } else {
                // Successfully launched with admin privileges, exit this instance
                isQuitting = true;
                app.quit();
            }
        });
        return false;
    } else {
        console.log('Admin privileges requested but not supported on this platform');
        return false;
    }
}

// System info related functions
function getCpuUsage() {
    const cpus = os.cpus();
    let totalIdle = 0;
    let totalTick = 0;
    cpus.forEach(cpu => {
        const times = cpu.times as CpuTimes;
        for (const type of Object.keys(times)) {
            totalTick += times[type as keyof CpuTimes];
        }
        totalIdle += times.idle;
    });
    return { idle: totalIdle / cpus.length, total: totalTick / cpus.length };
}

let lastCpuUsage = getCpuUsage();

async function getSystemInfo() {
    try {
        // CPU Usage
        const currentCpuUsage = getCpuUsage();
        const idleDifference = currentCpuUsage.idle - lastCpuUsage.idle;
        const totalDifference = currentCpuUsage.total - lastCpuUsage.total;
        const cpuPercentage = 100 - Math.round(100 * idleDifference / totalDifference);
        lastCpuUsage = currentCpuUsage;

        // RAM Usage
        const totalRAM = os.totalmem();
        const freeRAM = os.freemem();
        const usedRAM = totalRAM - freeRAM;
        const ramPercentage = Math.round((usedRAM / totalRAM) * 100);

        // Storage Info - Using available space on root drive
        // For both Windows and Unix, get total memory and available memory
        const totalGB = (os.totalmem() / (1024 * 1024 * 1024)).toFixed(2);
        const freeGB = (os.freemem() / (1024 * 1024 * 1024)).toFixed(2);
        const storageText = `${freeGB}GB free of ${totalGB}GB`;

        return {
            cpu: cpuPercentage,
            ram: ramPercentage,
            storage: storageText
        };
    } catch (error) {
        console.error('Error getting system info:', error);
        return {
            cpu: 0,
            ram: 0,
            storage: 'Error fetching'
        };
    }
}

function createSplashScreen() {
    const splash = new BrowserWindow({
        width: 500,
        height: 400,
        frame: false,
        transparent: true,
        backgroundColor: '#00000000',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, '../preload/preload.js')
        }
    });

    splash.loadFile(path.join(__dirname, '../renderer/splash.html'));
    return splash;
}

function createMainWindow() {
    const mainWindow = new BrowserWindow({
        width: 800,
        height: 650,
        show: false,
        frame: false,
        backgroundColor: '#001529',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, '../preload/preload.js')
        }
    });

    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));

    // Handle page reloads to preserve state
    mainWindow.webContents.on('did-start-loading', () => {
        mainWindow.webContents.send('preserve-state');
    });

    return mainWindow;
}

// Register protocol
app.whenReady().then(() => {
    protocol.registerHttpProtocol('sentinel', (req, cb) => {
        const mainWindow = BrowserWindow.getAllWindows()[0];
        if (mainWindow) {
            const redirectUrl = req.url.replace('sentinel://', 'http://');
            const url = new URL(redirectUrl);
            const hash = url.hash;
            mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'), { hash });
        }
    });
});

// Handle auth callback
app.on('open-url', (event, url) => {
    event.preventDefault();
    const mainWindow = BrowserWindow.getAllWindows()[0];
    if (mainWindow) {
        const redirectUrl = url.replace('sentinel://', 'http://');
        const parsedUrl = new URL(redirectUrl);
        mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'), { hash: parsedUrl.hash });
    }
});

// Handle IPC messages
ipcMain.handle('get-system-info', async () => {
    return await getSystemInfo();
});

ipcMain.on('minimize-window', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (window) window.minimize();
});

ipcMain.on('close-window', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (window) window.close();
});

// Handle the protocol launch for Windows
app.setAsDefaultProtocolClient('sentinel');

let tray: Tray | null = null;
let isQuitting = false;
let exitDialogWindow: BrowserWindow | null = null;

function createTray() {
    const iconPath = path.join(__dirname, '../assets/sentinalprime.png');
    const icon = nativeImage.createFromPath(iconPath);
    tray = new Tray(icon.resize({ width: 16, height: 16 }));

    const contextMenu = Menu.buildFromTemplate([
        {
            label: 'Open',
            click: () => {
                if (mainWindow) {
                    mainWindow.show();
                }
            }
        },
        {
            label: 'Exit',
            click: () => {
                showExitConfirmation();
            }
        }
    ]);

    tray.setToolTip('Sentinel App');
    tray.setContextMenu(contextMenu);
}

function showExitConfirmation() {
    if (exitDialogWindow) {
        exitDialogWindow.focus();
        return;
    }

    exitDialogWindow = new BrowserWindow({
        width: 400,
        height: 320,
        resizable: false,
        frame: false,
        transparent: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, '../preload/preload.js')
        },
        parent: mainWindow || undefined,
        modal: true,
        show: false
    });

    exitDialogWindow.loadFile(path.join(__dirname, '../renderer/exitDialog.html'));

    exitDialogWindow.once('ready-to-show', () => {
        exitDialogWindow?.show();
    });

    exitDialogWindow.on('closed', () => {
        exitDialogWindow = null;
    });
}

ipcMain.on('exit-dialog-response', (_, shouldExit: boolean) => {
    if (shouldExit) {
        isQuitting = true;
        if (mainWindow) {
            mainWindow.destroy();
        }
        app.quit();
    }
    exitDialogWindow?.close();
});

let mainWindow: BrowserWindow | null = null;

app.whenReady().then(async () => {
    // Always check for admin privileges
    const isDev = process.env.NODE_ENV === 'development' || process.defaultApp;
    const isAdmin = await checkAdminPrivileges();
    isRunningAsAdmin = isAdmin;
    
    console.log(`App is running with admin privileges: ${isRunningAsAdmin}`);
    
    // If running as admin, set the environment variable for integrated sentinel
    if (isRunningAsAdmin) {
        process.env.SENTINEL_INTEGRATED = 'true';
        console.log("Setting SENTINEL_INTEGRATED=true for admin mode");
    } else {
        console.log("App is NOT running with admin privileges. Some features may be limited.");
        // In development mode, we'll still allow the app to run without admin
        if (!isDev) {
            // Force requireAdminPrivileges to false in non-admin mode to avoid unnecessary prompts
            appConfig.requireAdminPrivileges = false;
        }
    }
    
    // On Windows in production, check if admin is required based on configuration
    const sentinelRequiresAdmin = process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges;
    
    // Show admin privileges dialog before any window creation
    if (sentinelRequiresAdmin && !isRunningAsAdmin) {
        // Create a temporary window to ensure dialog is modal and centered
        const tempWindow = new BrowserWindow({
            width: 100,
            height: 100,
            show: false,
            frame: false
        });

        const { response } = await dialog.showMessageBox(tempWindow, {
            type: 'warning',
            buttons: ['Exit', 'Restart as Administrator'],
                defaultId: 1,
                title: 'Administrator Privileges Required',
            message: 'Sentinel Security requires administrator privileges.',
            detail: 'For full system monitoring capabilities, this application must run with administrator privileges.',
            noLink: true,
            cancelId: 0
        });
        
        tempWindow.destroy();
            
            if (response === 1) { // "Restart as Administrator"
            console.log("User chose to restart with admin privileges");
                await restartWithAdminPrivileges();
            return;
        } else {
            console.log("User chose not to run with admin privileges, exiting");
            app.quit();
            return;
        }
    } else if (!isRunningAsAdmin) {
        // We're running without admin but not requiring it - show an informational dialog
        const tempWindow = new BrowserWindow({
            width: 100,
            height: 100,
            show: false,
            frame: false
        });

        await dialog.showMessageBox(tempWindow, {
            type: 'info',
            buttons: ['Continue'],
            defaultId: 0,
            title: 'Limited Functionality',
            message: 'Running with limited monitoring capabilities',
            detail: 'Some system monitoring features will be limited without administrator privileges. You can restart as administrator for full functionality.',
            noLink: true
        });
        
        tempWindow.destroy();
    }
    
    // Continue with normal startup
    createTray();
    const splash = createSplashScreen();
    mainWindow = createMainWindow();
    
    // Simulate initialization process
    setTimeout(() => {
        splash.close();
        mainWindow?.show();
        mainWindow?.webContents.send('splash-screen-done');
    }, 6000);
    
    // Normal app setup
    mainWindow?.on('close', (event) => {
        if (!isQuitting) {
            event.preventDefault();
            mainWindow?.hide();
        }
    });

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') {
            app.quit();
        }
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createMainWindow();
        }
    });

    app.on('before-quit', () => {
        isQuitting = true;
    });
});

// Ensure sentinel is stopped when app quits
app.on('quit', async () => {
    console.log("App quitting, ensuring Sentinel is stopped.");
    await stopSentinelMonitor();
    // --- REMOVED backend service kill ---
    // if (backendServiceProcess) {
    //     backendServiceProcess.kill();
    // }
    // --- END REMOVAL ---
});

let sentinelProcess: ChildProcess | null = null;
let sentinelUserId: string | null = null; // Store the current user ID for Sentinel

// Helper function to check if a process is running
async function isProcessRunning(pid: number | undefined): Promise<boolean> {
    if (!pid) return false;
    
    try {
        process.kill(pid, 0);
        return true;
    } catch (e) {
        return false;
    }
}

// Function to start sentinel directly from the main Electron process
async function startSentinelMonitor(userId: string | null) {
    const isDev = process.env.NODE_ENV === 'development' || process.defaultApp;
    // Store the user ID
    sentinelUserId = userId;

    // Ensure previous instance is stopped before starting a new one
    if (sentinelProcess && await isProcessRunning(sentinelProcess.pid)) {
        console.log('Sentinel already running, stopping before restarting...');
        await stopSentinelMonitor(); // stopSentinelMonitor should now reliably set sentinelProcess to null
    } else if (sentinelProcess) {
        // If we have a handle but it's not running, clear the stale handle
        console.log(`Clearing stale Sentinel process handle (PID: ${sentinelProcess.pid})`);
        sentinelProcess = null;
    }
    
    // Don't start if no user ID is provided
    if (!userId) {
        console.log('Cannot start Sentinel: No User ID provided.');
        mainWindow?.webContents.send('sentinel-status-update', { 
            running: false, 
            status: 'Stopped (No User ID)',
            admin: isRunningAsAdmin,
            requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
        });
        return { success: false, message: 'No User ID provided' };
    }
    
    // If the app is running with admin privileges AND the requiresAdmin flag is true,
    // we won't need to spawn a separate sentinel.py process
    const alreadyRunningWithAdmin = isRunningAsAdmin && (process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges);
    
    // If we're already running the whole app with admin privileges, we can avoid spawning a separate process
    if (alreadyRunningWithAdmin && process.env.SENTINEL_INTEGRATED === 'true') {
        console.log('App is already running in admin mode, using integrated monitoring instead of spawning sentinel.py');
        mainWindow?.webContents.send('sentinel-status-update', { 
            running: true, 
            pid: process.pid, 
            userId: userId, 
            status: 'Running (Integrated)',
            admin: isRunningAsAdmin,
            requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
        });
        return { success: true, pid: process.pid, userId: userId, integrated: true };
    }
    
    // Calculate the path to the sentinel.py script
    const appPath = app.getAppPath();
    const pythonScriptPath = path.join(appPath, 'src', 'python', 'sentinel.py');
    console.log(`Sentinel script path: ${pythonScriptPath}`);

    // Check if the script exists
    if (!fs.existsSync(pythonScriptPath)) {
        const errorMsg = `Cannot find sentinel script at: ${pythonScriptPath}`;
        console.error(errorMsg);
        mainWindow?.webContents.send('sentinel-error', errorMsg);
        mainWindow?.webContents.send('sentinel-status-update', { 
            running: false, 
            status: 'Error: Script Missing',
            admin: isRunningAsAdmin,
            requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
        });
        return { success: false, message: errorMsg };
    }

    try {
        // --- Find Python executable path ---
        let pythonExecutable = '';
        const venvDir = path.join(appPath, '.venv'); // Corrected: Use .venv instead of venv

        // Check venv path first
        if (process.platform === 'win32') {
            const venvPath = path.join(venvDir, 'Scripts', 'python.exe');
            if (fs.existsSync(venvPath)) {
                pythonExecutable = venvPath;
            }
        } else { // Linux/macOS
            let venvPath = path.join(venvDir, 'bin', 'python');
            if (fs.existsSync(venvPath)) {
                pythonExecutable = venvPath;
            } else {
                venvPath = path.join(venvDir, 'bin', 'python3');
                if (fs.existsSync(venvPath)) {
                    pythonExecutable = venvPath;
                }
            }
        }

        // If venv Python not found, try system Python
        if (!pythonExecutable) {
            const systemPython = process.platform === 'win32' ? 'python' : 'python3';
            console.warn(`Python executable not found in venv path (${venvDir}). Falling back to system Python: ${systemPython}`);
            mainWindow?.webContents.send('sentinel-warning', `Python executable not found in venv. Trying system Python: ${systemPython}.`);
            
            // Verify system python exists using 'where' or 'which'
            try {
                 const checkCmd = process.platform === 'win32' ? `where ${systemPython}` : `which ${systemPython}`;
                 await new Promise<void>((resolve, reject) => {
                    exec(checkCmd, (error, stdout) => {
                        if (error || !stdout) {
                             console.error(`System Python '${systemPython}' not found in PATH.`);
                             reject(new Error(`System Python '${systemPython}' not found.`));
                        } else {
                             pythonExecutable = systemPython; // Use the command name if found
                             console.log(`Using system Python found at: ${stdout.trim().split('\n')[0]}`);
                             resolve();
                        }
                    });
                 });
            } catch (checkError: any) {
                 const errorMsg = `Failed to find Python in venv or system PATH: ${checkError.message}`;
                 console.error(errorMsg);
                 mainWindow?.webContents.send('sentinel-error', errorMsg);
                 mainWindow?.webContents.send('sentinel-status-update', { running: false, status: 'Error: Python Not Found' });
                 return { success: false, message: errorMsg };
            }
        }
        
        console.log(`Using Python executable: ${pythonExecutable}`);
        
        // Build command arguments
        const args = [pythonScriptPath, '--user-id', userId];
        // Pass admin status correctly based on app's actual privilege level
        if (isRunningAsAdmin) {
             args.push('--admin');
        } else {
             args.push('--no-admin'); // Explicitly tell script it's not admin
        }

        // Prepare spawn options
        let spawnOptions: any = {
            stdio: ['pipe', 'pipe', 'pipe'] as ('pipe' | 'ignore' | 'inherit')[],
            windowsHide: true, // Hide console window on Windows
            detached: false, // Don't detach unless necessary
            env: {
                ...process.env,
                SENTINEL_INTEGRATED: process.env.SENTINEL_INTEGRATED || 'false'
            }
        };
        
        console.log(`Spawning Sentinel process: ${pythonExecutable} ${args.join(' ')}`);
        mainWindow?.webContents.send('sentinel-status-update', { running: false, status: 'Starting...' });

        // Reset sentinelProcess before spawning
        sentinelProcess = null; 
        
        // Spawn the process
        sentinelProcess = spawn(pythonExecutable, args, spawnOptions);
            
        if (!sentinelProcess || !sentinelProcess.pid) {
            const errorMsg = 'Failed to start sentinel process (spawn returned null or no PID)';
            console.error(errorMsg);
            sentinelProcess = null; // Ensure it's null
            mainWindow?.webContents.send('sentinel-error', errorMsg);
            mainWindow?.webContents.send('sentinel-status-update', { running: false, status: 'Error: Spawn Failed' });
            return { success: false, message: errorMsg };
        }
            
        const currentPid = sentinelProcess.pid; // Capture PID for reliable logging
        console.log(`Sentinel process potentially started with PID: ${currentPid} for user: ${userId}`);
        mainWindow?.webContents.send('sentinel-status-update', { 
            running: true, 
            pid: currentPid, 
            userId: userId, 
            status: 'Initializing', // Start as initializing
            admin: isRunningAsAdmin,
            requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
        });

        // Variables to track process state
        let isReady = false;
        let earlyExit = false;
        let detectedIntegratedMode = false;

        // Handle process output
        let capturedStdout = ''; // Store captured stdout
        if (sentinelProcess.stdout) {
            sentinelProcess.stdout.on('data', (data) => {
                if (sentinelProcess?.pid !== currentPid) return; // Ignore output from old processes
                const output = data.toString().trim();
                capturedStdout += output + '\n'; // Store for later analysis
                
                // Check for integrated message
                if (output.includes("SENTINEL_INTEGRATED=true detected")) {
                    console.log("Detected SENTINEL_INTEGRATED message from child process");
                    // Now the process will keep running in integrated mode instead of exiting
                    detectedIntegratedMode = true;
                    
                    // Update UI to show we're using integrated mode
                    mainWindow?.webContents.send('sentinel-status-update', { 
                        running: true, 
                        pid: currentPid, 
                        userId: userId, 
                        status: 'Running (Integrated)',
                        admin: isRunningAsAdmin,
                        requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
                    });
                }
                
                console.log(`[PID ${currentPid}] Sentinel stdout: ${output}`);
                if (output.includes("SENTINEL_READY")) {
                    isReady = true;
                    console.log(`[PID ${currentPid}] Sentinel reported ready.`);
                    
                    // Only update status if not in integrated mode (that was handled above)
                    if (!detectedIntegratedMode) {
                        mainWindow?.webContents.send('sentinel-status-update', { 
                            running: true, 
                            pid: currentPid, 
                            userId: sentinelUserId, 
                            status: 'Running',
                            admin: isRunningAsAdmin,
                            requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
                        });
                    }
                }
                mainWindow?.webContents.send('sentinel-output', output);
            });
        }
        
        if (sentinelProcess.stderr) {
            sentinelProcess.stderr.on('data', (data) => {
                 if (sentinelProcess?.pid !== currentPid) return; // Ignore output from old processes
                const errorOutput = data.toString().trim();
                 console.error(`[PID ${currentPid}] Sentinel stderr: ${errorOutput}`);
                 mainWindow?.webContents.send('sentinel-error', errorOutput);
                 // Update status on critical errors
                 if (errorOutput.includes('FATAL') || errorOutput.includes('CRITICAL') || errorOutput.includes('Traceback')) {
                      mainWindow?.webContents.send('sentinel-status-update', { 
                           running: false, 
                           pid: currentPid, 
                           userId: sentinelUserId, 
                           status: 'Error',
                           error: errorOutput,
                           admin: isRunningAsAdmin,
                           requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
                      });
                }
            });
        }
        
        sentinelProcess.on('close', (code, signal) => {
            console.log(`[PID ${currentPid}] Sentinel process exited with code ${code}, signal ${signal}`);
            earlyExit = true;
            
            // Note: With our updated approach, the sentinel.py process should NOT be exiting
            // in integrated mode. If it does exit, it's an error regardless of the exit code.
            
            // Handle exit based on status
            let status = 'Stopped';
            if (detectedIntegratedMode) {
                // If we detected integrated mode but the process still exited, that's unexpected
                status = 'Error: Integrated Monitor Crashed';
                console.error(`Integrated monitoring process unexpectedly exited with code ${code}`);
            } else {
                // Normal exit handling for non-integrated mode
                status = (code === 0) ? 'Stopped' : `Exited (code ${code}, signal ${signal})`;
            }
            
            // Clear the process variable *only if* it's the current process exiting
            if (sentinelProcess && sentinelProcess.pid === currentPid) {
                sentinelProcess = null;
            }
            
            // Notify renderer
            mainWindow?.webContents.send('sentinel-stopped', { code, signal });
            mainWindow?.webContents.send('sentinel-status-update', { 
                running: false, 
                pid: currentPid, 
                userId: sentinelUserId, 
                status: status,
                admin: isRunningAsAdmin, 
                requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
            });
        });

        sentinelProcess.on('error', (err) => {
            console.error(`[PID ${currentPid}] Error spawning/running sentinel process:`, err);
            earlyExit = true;
            // Clear the process variable *only if* it's the current process erroring
            if (sentinelProcess && sentinelProcess.pid === currentPid) {
                 sentinelProcess = null;
            }
            mainWindow?.webContents.send('sentinel-error', `Spawn/runtime error: ${err.message}`);
            mainWindow?.webContents.send('sentinel-status-update', { 
                running: false, 
                pid: currentPid, 
                userId: sentinelUserId,
                status: 'Failed to Start/Run',
                error: err.message,
                admin: isRunningAsAdmin,
                requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
            });
        });

        // Short delay to check for immediate exit
        await new Promise(resolve => setTimeout(resolve, 1500)); 
        
        // If we're in integrated mode, the process should be running
        if (detectedIntegratedMode) {
            if (sentinelProcess && await isProcessRunning(currentPid)) {
                console.log("Sentinel running in integrated mode");
                return {
                    success: true,
                    integrated: true,
                    pid: currentPid,
                    userId: userId
                };
            } else {
                // This is unexpected - we detected integrated mode but process died
                console.error("Sentinel detected integrated mode but process died unexpectedly");
                return {
                    success: false,
                    message: 'Integrated monitoring process crashed unexpectedly'
                };
            }
        }
        
        // Normal check for non-integrated mode
        if (earlyExit || (sentinelProcess && sentinelProcess.pid === currentPid && !await isProcessRunning(currentPid))) {
            console.error(`[PID ${currentPid}] Sentinel process failed to stay running shortly after start.`);
            // Status should have been updated by 'close' or 'error' handlers
            if (sentinelProcess && sentinelProcess.pid === currentPid) {
                 sentinelProcess = null; // Ensure handle is cleared if check confirms it's dead
            }
            return { 
                success: false, 
                message: 'Sentinel process failed to start or crashed immediately' 
            };
        }
            
        // If it hasn't reported ready yet, keep status as 'Initializing'
        if (!isReady && sentinelProcess && sentinelProcess.pid === currentPid) {
            console.log(`[PID ${currentPid}] Sentinel still initializing...`);
            mainWindow?.webContents.send('sentinel-status-update', { 
                running: true, 
                pid: currentPid, 
                userId: sentinelUserId, 
                status: 'Initializing', // Keep as initializing until SENTINEL_READY
                admin: isRunningAsAdmin,
                requiresAdmin: process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges
            });
        }
        
        return { 
            success: true, 
            pid: currentPid,
            userId: userId
        };
        
    } catch (error: any) {
        console.error('Critical error in startSentinelMonitor:', error);
        sentinelProcess = null; // Ensure cleared on unexpected error
        mainWindow?.webContents.send('sentinel-error', `Critical start error: ${error?.message}`);
        mainWindow?.webContents.send('sentinel-status-update', { running: false, status: 'Start Error' });
        return { 
            success: false, 
            message: error?.message || 'Unknown error starting sentinel' 
        };
    }
}

// Function to stop sentinel
async function stopSentinelMonitor() {
    if (!sentinelProcess) {
        console.log('Stop request: Sentinel is not running.');
         mainWindow?.webContents.send('sentinel-status-update', { 
            running: false, 
            status: 'Stopped',
            admin: isRunningAsAdmin, // Reflect current app admin status
            // Re-evaluate requirement based on config
            requiresAdmin: process.platform === 'win32' && !(process.env.NODE_ENV === 'development' || process.defaultApp) && appConfig.requireAdminPrivileges
         });
        return { success: true, message: 'Sentinel is not running' };
    }

    const pid = sentinelProcess.pid;
    console.log(`Stopping Sentinel process (PID: ${pid})...`);
    
    try {
        if (!pid) {
            console.warn('Stop request: Sentinel process exists but PID is missing.');
            sentinelProcess = null; // Clear the invalid process handle
            return { success: false, message: 'Process PID is undefined' };
        }

        // Add a listener for the close event *before* killing
        // to ensure the status update happens reliably.
        sentinelProcess.removeAllListeners('close'); // Remove previous listeners if any
        sentinelProcess.once('close', (code, signal) => {
             console.log(`Sentinel process (PID: ${pid}) confirmed closed with code ${code}, signal ${signal}.`);
             // Status update is now handled reliably in the 'close' event handler for startSentinelMonitor
             // We can send an additional specific "stopped by user" status if desired.
             mainWindow?.webContents.send('sentinel-status-update', { 
                running: false, 
                pid: pid, 
                userId: sentinelUserId, 
                status: 'Stopped by User',
                admin: isRunningAsAdmin,
                requiresAdmin: process.platform === 'win32' && !(process.env.NODE_ENV === 'development' || process.defaultApp) && appConfig.requireAdminPrivileges
             });
        });
        
        // Use different termination methods based on platform
        if (process.platform === 'win32') {
            // On Windows, use taskkill to ensure child processes are also terminated
            exec(`taskkill /pid ${pid} /f /t`);
        } else {
            // On Unix systems, kill the process
            process.kill(pid, 'SIGTERM');
            // Add a fallback kill after a timeout if SIGTERM is ignored
            setTimeout(() => {
                if (sentinelProcess && sentinelProcess.pid === pid) { // Check if it's still the same process
                    console.warn(`Sentinel process (PID: ${pid}) did not exit after SIGTERM, sending SIGKILL.`);
                    try {
                        process.kill(pid, 'SIGKILL');
                    } catch (killError) {
                         console.error(`Error sending SIGKILL to PID ${pid}:`, killError);
                    }
                }
            }, 3000); // 3 seconds grace period
        }

        // Clear the process variable immediately after initiating kill
        // The 'close' event handler will perform the final status update.
        sentinelProcess = null;
        console.log(`Termination signal sent to Sentinel process (PID: ${pid}).`);
        return { success: true, message: 'Sentinel stop signal sent' };
    } catch (error: any) {
        console.error('Error stopping sentinel:', error);
        return { success: false, message: error?.message || 'Error stopping sentinel' };
    }
}

// Function to check sentinel status
async function checkSentinelStatus(): Promise<{ 
    running: boolean;
    status: string; 
    admin: boolean;
    requiresAdmin: boolean;
    lastError?: string;
    pid?: number | null; 
    userId?: string | null;
}> {
    const isDev = process.env.NODE_ENV === 'development' || process.defaultApp;
    const sentinelRequiresAdmin = process.platform === 'win32' && !isDev && appConfig.requireAdminPrivileges;
    const currentPid = sentinelProcess?.pid ?? null;

    try {
        if (sentinelProcess && currentPid && await isProcessRunning(currentPid)) {
            // Process handle exists and the process is running according to OS.
            // Status might be 'Initializing' or 'Running' based on internal state
            // For simplicity, if we haven't received a specific status update recently,
            // assume 'Running' if we have a valid, running process.
            // More complex state tracking could be added here if needed.
            return {
                running: true,
                status: 'Running', // Assuming 'Running' if process active, UI updates handle more detail
                admin: isRunningAsAdmin,
                requiresAdmin: sentinelRequiresAdmin,
                pid: currentPid,
                userId: sentinelUserId
            };
        } else if (sentinelProcess) {
             // We have a process handle, but the OS says it's not running (or PID is null).
             console.warn(`checkSentinelStatus: Found sentinelProcess handle (PID: ${currentPid}) but process is not running or PID invalid.`);
             const lastPid = sentinelProcess.pid; // Capture PID before clearing
             sentinelProcess = null; // Clear the stale handle
                return {
                 running: false,
                 status: 'Crashed / Stale Handle',
                 admin: isRunningAsAdmin,
                 requiresAdmin: sentinelRequiresAdmin,
                 userId: sentinelUserId, // Keep last known user ID
                 pid: lastPid, // Report the PID of the stale handle
                 lastError: 'Process handle existed but process was not running.'
             };
        } else {
             // sentinelProcess is null, it's definitely stopped.
        return { 
            running: false,
                 status: 'Stopped',
                 admin: isRunningAsAdmin, 
                 requiresAdmin: sentinelRequiresAdmin,
                 userId: sentinelUserId, // Report last known user ID if any
                 pid: null
             };
        }
    } catch (error: any) {
        console.error('Error checking sentinel status:', error);
        return { 
            running: false, 
            status: 'Error Checking Status',
            admin: isRunningAsAdmin,
            requiresAdmin: sentinelRequiresAdmin,
            lastError: error?.message || 'Unknown error during status check' ,
            pid: currentPid // Report PID even if check failed
        };
    }
}

// Add IPC handler to update the user ID for the sentinel monitor
ipcMain.on('update-sentinel-user', async (_, userId: string) => {
    console.log(`IPC: Received request to update Sentinel user to: ${userId}`);
    if (userId && userId.trim() !== '') {
        sentinelUserId = userId.trim(); // Update stored user ID immediately
        // Attempt to start/restart Sentinel
        const result = await startSentinelMonitor(sentinelUserId);

        // No need to handle admin restart here, as the main app.whenReady() flow
        // should have already prompted for admin if required *for the app itself*.
        // startSentinelMonitor now handles the case where it *attempts* to run
        // without required admin, and the Python script should adapt.
        if (!result.success) {
            console.error(`IPC: Failed to start Sentinel for user ${sentinelUserId}: ${result.message}`);
            // Optionally send specific error back to renderer
            mainWindow?.webContents.send('sentinel-start-failed', { userId: sentinelUserId, message: result.message });
        } else {
             console.log(`IPC: Sentinel start initiated successfully for user ${sentinelUserId}.`);
        }

    } else {
        // If userId is empty or null, stop the monitor
        console.log('IPC: Received empty user ID, stopping Sentinel.');
        await stopSentinelMonitor();
        sentinelUserId = null; // Clear stored user ID
    }
});

// Add IPC handler to check sentinel monitor status
ipcMain.handle('check-sentinel-status', async () => {
    return await checkSentinelStatus();
});

// Add this IPC handler after the other IPC handlers
ipcMain.handle('get-sentinel-logs', async () => {
    try {
        const logFilePath = path.join(app.getAppPath(), 'logs', 'sentinel.log');
        
        if (!fs.existsSync(logFilePath)) {
            return { success: false, message: 'Log file does not exist' };
        }
        
        // Read the last 500 lines (or fewer if file is smaller)
        const maxLines = 500;
        const content = fs.readFileSync(logFilePath, 'utf8');
        const lines = content.split('\n');
        const lastLines = lines.slice(Math.max(0, lines.length - maxLines)).join('\n');
        
        return { success: true, logs: lastLines };
    } catch (error: any) {
        console.error('Error reading sentinel log file:', error);
        return { success: false, message: error?.message || 'Unknown error reading log file' };
    }
});

// Also add a handler for Python process logs if available
ipcMain.handle('get-python-logs', async () => {
    try {
        const logOutput: string[] = [];
        
        if (sentinelProcess && sentinelProcess.stdout) {
            // This will only have recent logs if they're being buffered
            // Most logs are written to file, but this might catch some real-time output
            logOutput.push('--- RECENT STDOUT OUTPUT ---');
            if (typeof sentinelProcess.stdout.read === 'function') {
                const stdout = sentinelProcess.stdout.read();
                if (stdout) {
                    logOutput.push(stdout.toString());
                }
            }
        }
        
        // Try to find any Python error logs in temp directory
        const tempDir = os.tmpdir();
        const pythonErrorLogs = fs.readdirSync(tempDir)
            .filter(file => file.startsWith('python') && file.endsWith('.log'))
            .slice(0, 5); // Limit to 5 most recent files
            
        for (const errorLog of pythonErrorLogs) {
            try {
                logOutput.push(`--- ${errorLog} ---`);
                const content = fs.readFileSync(path.join(tempDir, errorLog), 'utf8');
                // Limit to last 100 lines
                const lines = content.split('\n');
                logOutput.push(lines.slice(Math.max(0, lines.length - 100)).join('\n'));
            } catch (err) {
                console.error(`Error reading Python error log ${errorLog}:`, err);
            }
        }
        
        return { 
            success: true, 
            logs: logOutput.join('\n\n') || 'No Python process logs available'
        };
    } catch (error: any) {
        console.error('Error getting Python logs:', error);
        return { success: false, message: error?.message || 'Unknown error getting Python logs' };
    }
});
