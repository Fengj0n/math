// Regenerate the isolated preview's icons from the project's existing Lucide package.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const app = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(app, 'design/question-bank.html'), 'utf8');
const names = new Set([...source.matchAll(/icon\('([^']+)'|data-lucide="([^"]+)"/g)].map(m => m[1] || m[2]).filter(n=>/^[a-z0-9-]+$/.test(n)));
['minimize-2','maximize-2','chevron-left','chevron-right','chevron-down','chevron-up'].forEach(n=>names.add(n));
const nodes = {};
for (const name of names) {
  const file = path.join(app, 'frontend/node_modules/lucide-react/dist/esm/icons', name + '.js');
  const raw = fs.readFileSync(file, 'utf8');
  const body = raw.match(/const __iconNode = ([\s\S]*?);\r?\n/)[1];
  nodes[name] = vm.runInNewContext('(' + body + ')');
}
const runtime = `// Lucide icon nodes, ISC license; see lucide-LICENSE.txt. Local DOM renderer.\n(function(){const nodes=${JSON.stringify(nodes)};window.lucide={createIcons(options={}){document.querySelectorAll('i[data-lucide]').forEach(el=>{const data=nodes[el.dataset.lucide];if(!data)return;const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');const attrs={width:16,height:16,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':2,'stroke-linecap':'round','stroke-linejoin':'round',...(options.attrs||{})};Object.entries(attrs).forEach(([k,v])=>svg.setAttribute(k,v));svg.setAttribute('class',el.className);svg.setAttribute('aria-hidden','true');data.forEach(([tag,attrs])=>{const node=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>{if(k!=='key')node.setAttribute(k,v)});svg.appendChild(node)});el.replaceWith(svg)})}}})();\n`;
fs.writeFileSync(path.join(__dirname, 'static/icons.js'), runtime);
fs.copyFileSync(path.join(app, 'frontend/node_modules/lucide-react/LICENSE'), path.join(__dirname, 'static/lucide-LICENSE.txt'));
console.log('Local icons:', names.size);
