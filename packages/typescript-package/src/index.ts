export function greet(name: string): string {
  const trimmed = name.trim();
  return trimmed.length ? `Hello, ${trimmed}!` : 'Hello!';
}
