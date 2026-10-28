import {createRequire} from 'node:module';
import {readFile,writeFile,copyFile,readdir} from 'node:fs/promises';
import path from 'node:path';
const require=createRequire(new URL('../../designe 1.0/package.json',import.meta.url));
const sharp=require('sharp');
const dir=import.meta.dirname;
for(const key of ['01-route','02-focus','03-link']){
 const svg=await readFile(path.join(dir,`logo-${key}.svg`));
 await sharp(svg).resize({width:1120}).png().toFile(path.join(dir,`logo-${key}.png`));
}
const social=await sharp(await readFile(path.join(dir,'social-preview.svg'))).png().toBuffer();
for(const app of ['designe 1.0','frontend']){
 const root=path.resolve(dir,'../..',app);
 for(const file of await readdir(dir))if(file.endsWith('.svg')||file.endsWith('.png')||file==='preview.html'||file==='preview.css')await copyFile(path.join(dir,file),path.join(root,'public/brand',file));
 await writeFile(path.join(root,'public/social-preview.png'),social);
 const icon=await readFile(path.join(root,'app/icon.svg'));
 const png=await sharp(icon).resize(32,32).png().toBuffer();
 const head=Buffer.alloc(22);head.writeUInt16LE(1,2);head.writeUInt16LE(1,4);head[6]=32;head[7]=32;head.writeUInt16LE(1,10);head.writeUInt16LE(32,12);head.writeUInt32LE(png.length,14);head.writeUInt32LE(22,18);
 await writeFile(path.join(root,'app/favicon.ico'),Buffer.concat([head,png]));
 await sharp(icon).resize(180,180).png().toFile(path.join(root,'public/apple-touch-icon.png'));
}
await copyFile(path.join(dir,'logo-01-route.svg'),path.resolve(dir,'../../designe 1.0/public/brand/logo.svg'));
console.log('PASS: three transparent logo PNGs, social cards, SVG and ICO favicons');
