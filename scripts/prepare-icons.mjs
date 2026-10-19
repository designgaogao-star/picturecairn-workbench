import { copyFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const root = new URL('../', import.meta.url);
copyFileSync(fileURLToPath(new URL('node_modules/lucide/dist/umd/lucide.js', root)), fileURLToPath(new URL('prototype/lucide.js', root)));
copyFileSync(fileURLToPath(new URL('node_modules/lucide/LICENSE', root)), fileURLToPath(new URL('prototype/lucide.LICENSE', root)));
