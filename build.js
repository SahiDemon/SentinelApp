#!/usr/bin/env node
import * as esbuild from 'esbuild';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs/promises';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function copyAssets() {
    try {
        // Create necessary directories
        await fs.mkdir(path.join(__dirname, 'dist', 'assets'), { recursive: true });
        await fs.mkdir(path.join(__dirname, 'dist', 'renderer', 'css'), { recursive: true });
        
        // Copy CSS files
        await fs.copyFile(
            path.join(__dirname, 'src', 'renderer', 'css', 'styles.css'),
            path.join(__dirname, 'dist', 'renderer', 'css', 'styles.css')
        );
        
        await fs.copyFile(
            path.join(__dirname, 'src', 'renderer', 'css', 'notifications.css'),
            path.join(__dirname, 'dist', 'renderer', 'css', 'notifications.css')
        );
        
        // Copy all files from src/assets to dist/assets if the directory exists
        try {
            const files = await fs.readdir(path.join(__dirname, 'src', 'assets'));
            for (const file of files) {
                await fs.copyFile(
                    path.join(__dirname, 'src', 'assets', file),
                    path.join(__dirname, 'dist', 'assets', file)
                );
            }
        } catch (error) {
            if (error.code !== 'ENOENT') {
                throw error;
            }
            console.log('No assets directory found, skipping asset copy');
        }

        // Copy overlay.css
        await fs.copyFile(
            path.join(__dirname, 'src', 'renderer', 'css', 'overlay.css'),
            path.join(__dirname, 'dist', 'renderer', 'css', 'overlay.css')
        );

        // Copy overlay.js
        await fs.copyFile(
            path.join(__dirname, 'src', 'renderer', 'js', 'overlay.js'),
            path.join(__dirname, 'dist', 'renderer', 'js', 'overlay.js')
        );
        
        console.log('Assets and CSS copied successfully');
    } catch (error) {
        console.error('Error copying assets:', error);
    }
}

async function build() {
    try {
        // Bundle the main process
        await esbuild.build({
            entryPoints: [path.join(__dirname, 'src/main/main.ts')],
            bundle: true,
            platform: 'node',
            format: 'esm',
            target: 'node16',
            outfile: path.join(__dirname, 'dist/main/main.js'),
            external: ['electron']
        });

        // Bundle the preload script
        await esbuild.build({
            entryPoints: [path.join(__dirname, 'src/preload/preload.ts')],
            bundle: true,
            platform: 'node',
            format: 'cjs',
            target: 'node16',
            outfile: path.join(__dirname, 'dist/preload/preload.js'),
            external: ['electron']
        });

        // Bundle the renderer process
        await esbuild.build({
            entryPoints: [
                path.join(__dirname, 'src/renderer/js/auth.ts'),
                path.join(__dirname, 'src/renderer/js/index.ts'),
                path.join(__dirname, 'src/renderer/js/notifications.ts')
            ],
            bundle: true,
            platform: 'browser',
            format: 'esm',
            target: 'es2020',
            outdir: path.join(__dirname, 'dist/renderer/js'),
            external: ['electron']
        });

        // Copy assets
        await copyAssets();

        console.log('Build completed successfully');
    } catch (error) {
        console.error('Build failed:', error);
        process.exit(1);
    }
}

build();
