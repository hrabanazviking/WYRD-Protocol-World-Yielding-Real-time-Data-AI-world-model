/**
 * build-esm.mjs — second half of `npm run build` for wyrdforge-js.
 *
 * Phase E2 (SDK publishing fixes). The build script declared in
 * package.json has always been:
 *
 *     tsc -p tsconfig.build.json && node scripts/build-esm.mjs
 *
 * but this file did not exist, so the declared dist/ entry points
 * (dist/index.cjs for require, dist/index.mjs for import,
 * dist/index.d.ts for types) could never be produced.
 *
 * What the tsc step leaves in dist/ is CommonJS: index.js,
 * client.js, types.js, plus .d.ts declarations and source maps.
 * This script turns that into the dual package package.json declares:
 *
 *   1. CommonJS: each dist/*.js is rewritten to dist/*.cjs, with its
 *      relative require("./x.js") specifiers rewritten to
 *      require("./x.cjs") so the files resolve under Node's CJS
 *      loader without relying on the (removed) .js intermediates.
 *   2. ESM: tsc is run a second time (module ESNext, via a
 *      temporary tsconfig extending the build config) into a
 *      temporary directory, and each emitted .js is rewritten to
 *      dist/*.mjs with relative "./x.js" specifiers rewritten to
 *      "./x.mjs". The shipped sources use non-erasable TypeScript
 *      syntax, so this is a real compile — Node type-stripping
 *      cannot produce this output.
 *
 * The .d.ts files from the first (CommonJS) tsc pass are left in
 * place; they are the shared types entry for both loaders.
 *
 * Node built-ins only; no extra dependencies.
 */
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const pkgRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const distDir = join(pkgRoot, "dist");

if (!existsSync(join(distDir, "index.js"))) {
  console.error(
    "build-esm: dist/index.js not found — run `tsc -p tsconfig.build.json` first " +
      "(that is the first half of `npm run build`)."
  );
  process.exit(1);
}

const jsFiles = readdirSync(distDir).filter((f) => f.endsWith(".js"));
if (jsFiles.length === 0) {
  console.error("build-esm: no .js files in dist/ — nothing to convert.");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// 1. ESM pass: recompile to a temp dir with module NodeNext, then
//    rewrite each file to dist/<name>.mjs.
// ---------------------------------------------------------------------------
const esmTmp = mkdtempSync(join(pkgRoot, ".esm-build-"));
const esmConfigPath = join(pkgRoot, ".tsconfig.esm.tmp.json");
try {
  // NOTE: `tsc -p <config>` silently ignores --module/--outDir style
  // command-line overrides, so the ESM pass needs its own config file
  // extending the build config (an earlier version of this script
  // passed CLI flags and produced CommonJS files renamed to .mjs —
  // caught by the E2 dist smoke check, never shipped).
  writeFileSync(
    esmConfigPath,
    JSON.stringify({
      extends: "./tsconfig.build.json",
      compilerOptions: {
        // ESNext (not NodeNext): NodeNext emit follows the source
        // package.json's "type" field, and this package has none, so
        // NodeNext would emit CommonJS again. ESNext forces true ESM
        // syntax; Bundler resolution accepts the sources' ".js"
        // specifiers, which this script then rewrites to ".mjs".
        module: "ESNext",
        moduleResolution: "Bundler",
        outDir: esmTmp,
        declaration: false,
        declarationMap: false,
        sourceMap: false,
      },
    })
  );
  const tscBin = join(pkgRoot, "node_modules", "typescript", "bin", "tsc");
  execFileSync(process.execPath, [tscBin, "-p", esmConfigPath], {
    cwd: pkgRoot,
    stdio: "inherit",
  });

  for (const file of readdirSync(esmTmp).filter((f) => f.endsWith(".js"))) {
    const src = readFileSync(join(esmTmp, file), "utf8");
    const rewritten = src.replace(
      /((?:from|import)\s+["'])(\.[^"']+)\.js(["'])/g,
      "$1$2.mjs$3"
    );
    writeFileSync(join(distDir, file.replace(/\.js$/, ".mjs")), rewritten);
  }
} finally {
  rmSync(esmTmp, { recursive: true, force: true });
  rmSync(esmConfigPath, { force: true });
}

// ---------------------------------------------------------------------------
// 2. CommonJS pass: rewrite each dist/*.js to dist/*.cjs with its
//    relative require specifiers pointed at the .cjs siblings.
// ---------------------------------------------------------------------------
for (const file of jsFiles) {
  const jsPath = join(distDir, file);
  const src = readFileSync(jsPath, "utf8");
  const rewritten = src.replace(
    /(require\(["'])(\.[^"']+)\.js(["']\))/g,
    "$1$2.cjs$3"
  );
  const cjsName = file.replace(/\.js$/, ".cjs");
  writeFileSync(join(distDir, cjsName), rewritten);
  rmSync(jsPath);

  // Keep the source map beside its renamed output, with a matching
  // "file" field, so stack traces/debuggers still line up.
  const mapPath = `${jsPath}.map`;
  if (existsSync(mapPath)) {
    const map = JSON.parse(readFileSync(mapPath, "utf8"));
    if (typeof map.file === "string") map.file = cjsName;
    writeFileSync(join(distDir, `${cjsName}.map`), JSON.stringify(map));
    rmSync(mapPath);
  }
}

const produced = readdirSync(distDir).sort();
console.log(`build-esm: dist/ now contains: ${produced.join(", ")}`);
for (const required of ["index.cjs", "index.mjs", "index.d.ts"]) {
  if (!produced.includes(required)) {
    console.error(`build-esm: REQUIRED output missing: dist/${required}`);
    process.exit(1);
  }
}
