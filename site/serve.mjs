/**
 * 本地预览：node site/serve.mjs  →  http://127.0.0.1:4321
 * 零依赖，只为在推上去之前看一眼。
 */
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { join, extname, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const PORT = Number(process.env.PORT || 4321)

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.xml': 'application/xml; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
}

async function resolveFile(urlPath) {
  let file = join(ROOT, decodeURIComponent(urlPath.split('?')[0]))
  if (!file.startsWith(ROOT)) return null
  try {
    const info = await stat(file)
    if (info.isDirectory()) file = join(file, 'index.html')
    else return file
  } catch {
    if (!extname(file)) file = join(file, 'index.html')
  }
  try {
    await stat(file)
    return file
  } catch {
    return null
  }
}

createServer(async (req, res) => {
  const file = await resolveFile(req.url || '/')
  if (!file) {
    const notFound = join(ROOT, '404.html')
    try {
      res.writeHead(404, { 'content-type': TYPES['.html'] })
      res.end(await readFile(notFound))
    } catch {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' })
      res.end('404')
    }
    return
  }
  res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream' })
  res.end(await readFile(file))
}).listen(PORT, '127.0.0.1', () => {
  console.log(`预览：http://127.0.0.1:${PORT}`)
})
