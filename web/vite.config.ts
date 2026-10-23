import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
export default defineConfig({ plugins: [react(),{
 name:'srasta-shell-precache',
 writeBundle(options,bundle) {
  const files=[...Object.keys(bundle).filter(name=>name.startsWith('assets/')).map(name=>'/'+name), ...readdirSync('public/figma').filter(name=>/\.(svg|png|woff2)$/.test(name)).map(name=>'/figma/'+name)];
  const source=readFileSync('public/sw.js','utf8').replace('const PRECACHE_ASSETS = [];',`const PRECACHE_ASSETS = ${JSON.stringify(files)};`);
  writeFileSync(resolve(options.dir || 'dist','sw.js'),source);
 }
}], server: { proxy: { '/api': 'http://127.0.0.1:8000', '/demo': 'http://127.0.0.1:8000' } } });
