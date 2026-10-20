import { proxyAuth } from '@/lib/auth-proxy';

async function handle(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxyAuth(request, path.join('/'));
}
export { handle as GET, handle as POST };
