import { describe, expect, it } from 'vitest';
import { greet } from './index.js';

describe('greet', () => {
  it('greets with the provided name', () => {
    expect(greet('Codex')).toBe('Hello, Codex!');
  });

  it('handles whitespace and empty names', () => {
    expect(greet('   ')).toBe('Hello!');
  });
});
