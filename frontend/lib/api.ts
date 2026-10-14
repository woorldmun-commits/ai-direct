export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public reason?: string, public requestId?: string) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function api<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('API path must be relative');
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch('/api/v1' + path, { ...options, headers, credentials: 'same-origin', cache: 'no-store' });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(response.status, error?.code ?? 'unavailable', error?.message ?? 'Сервис временно недоступен. Попробуйте позже.', error?.reason, error?.request_id);
  }
  if (response.status === 204) return undefined as T;
  if (body === null) throw new ApiError(response.status, 'invalid_response', 'Сервис вернул некорректный ответ. Попробуйте позже.');
  return body as T;
}

export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Не удалось связаться с сервисом. Проверьте подключение и попробуйте снова.';
}
