import readline from 'node:readline';
import {mathjax} from '@mathjax/src/js/mathjax.js';
import {TeX} from '@mathjax/src/js/input/tex.js';
import {SVG} from '@mathjax/src/js/output/svg.js';
import {liteAdaptor} from '@mathjax/src/js/adaptors/liteAdaptor.js';
import {RegisterHTMLHandler} from '@mathjax/src/js/handlers/html.js';
import '@mathjax/src/js/util/asyncLoad/esm.js';

import '@mathjax/src/js/input/tex/base/BaseConfiguration.js';
import '@mathjax/src/js/input/tex/ams/AmsConfiguration.js';
import '@mathjax/src/js/input/tex/newcommand/NewcommandConfiguration.js';
import '@mathjax/src/js/input/tex/noundefined/NoUndefinedConfiguration.js';

const requestedFont = (process.env.MATHTYPE_MATHJAX_FONT || 'mathjax-termes').toLowerCase();
let FontData;
if (requestedFont === 'mathjax-stix2' || requestedFont === 'stix2') {
  const mod = await import('@mathjax/mathjax-stix2-font/js/svg.js');
  FontData = mod.MathJaxStix2Font;
} else {
  const mod = await import('@mathjax/mathjax-termes-font/js/svg.js');
  FontData = mod.MathJaxTermesFont;
}

const EM = 16;
const EX = 8;
const WIDTH = 100000 * EM;

const adaptor = liteAdaptor({fontSize: EM});
RegisterHTMLHandler(adaptor);

const tex = new TeX({
  packages: ['base', 'ams', 'newcommand', 'noundefined'],
  formatError(jax, err) { throw err; },
});

const svgJax = new SVG({
  fontCache: 'local',
  exFactor: EX / EM,
  fontData: FontData,
  linebreaks: {
    inline: false,
    width: '100000em',
  },
});

const html = mathjax.document('', {
  InputJax: tex,
  OutputJax: svgJax,
});

function extractRootSvg(markup) {
  const start = markup.indexOf('<svg');
  if (start < 0) return '';
  let depth = 0;
  let pos = start;
  while (pos < markup.length) {
    const nextOpen = markup.indexOf('<svg', pos);
    const nextClose = markup.indexOf('</svg>', pos);
    if (nextClose < 0) return '';
    if (nextOpen >= 0 && nextOpen < nextClose) {
      depth += 1;
      pos = nextOpen + 4;
    } else {
      depth -= 1;
      pos = nextClose + 6;
      if (depth === 0) return markup.slice(start, pos);
    }
  }
  return '';
}

const rl = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
for await (const line of rl) {
  if (!line.trim()) continue;
  try {
    const request = JSON.parse(line);
    const latex = String(request.latex || '');
    const node = await html.convertPromise(latex, {
      display: Boolean(request.display),
      em: EM,
      ex: EX,
      containerWidth: WIDTH,
    });
    let svg = extractRootSvg(adaptor.outerHTML(node));
    if (!svg) throw new Error('MathJax did not return an SVG element.');
    svg = svg.replaceAll('currentColor', '#000000');
    process.stdout.write(JSON.stringify({ok: true, svg}) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify({
      ok: false,
      error: String(error?.message || error),
    }) + '\n');
  }
}
