/** Bound a read request so a stalled backend cannot keep the UI waiting forever. */
export async function requestWithTimeout<T>(request: Promise<T>, milliseconds = 12000): Promise<T> {
 let timer: ReturnType<typeof setTimeout> | undefined;
 try {
  return await Promise.race([
   request,
   new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('行情请求超时')), milliseconds);
   }),
  ]);
 } finally {
  if (timer !== undefined) clearTimeout(timer);
 }
}
