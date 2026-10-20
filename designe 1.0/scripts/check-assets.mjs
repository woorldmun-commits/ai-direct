import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
for(const css of ['fonts.css','inter.css']){
 const source=readFileSync(new URL('../app/'+css,import.meta.url),'utf8');
 for(const match of source.matchAll(/url\(['"]?(\/fonts\/[^)'"\s]+)['"]?\)/g)){
  assert(existsSync(new URL('../public'+match[1],import.meta.url)),'Missing font asset '+match[1]);
 }
}
for(const license of ['Inter-OFL.txt','Manrope-OFL.txt','IBMPlexMono-OFL.txt'])assert(existsSync(new URL('../public/fonts/'+license,import.meta.url)),'Missing font license '+license);
console.log('PASS font stylesheet assets and redistribution licenses exist');
