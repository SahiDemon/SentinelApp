# Create necessary directories
Write-Host "Creating directories..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path "dist/renderer/js"

# Clean the dist directory
Write-Host "Cleaning dist directory..." -ForegroundColor Green
npm run clean

# Run the build process
Write-Host "Building application..." -ForegroundColor Green
node build.js

# Create renderer directory and copy HTML files
Write-Host "Copying HTML files..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path "dist/renderer"
Copy-Item "src/renderer/*.html" "dist/renderer/" -Force

# Create js directory and ensure it exists
New-Item -ItemType Directory -Force -Path "dist/renderer/js"

# Start Electron using npx
Write-Host "Starting Electron..." -ForegroundColor Green
npx electron . --enable-logging
