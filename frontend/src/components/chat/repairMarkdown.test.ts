import { describe, expect, it } from 'vitest';
import { repairCollapsedMarkdown } from './repairMarkdown';

describe('repairCollapsedMarkdown', () => {
  it('restores headings and rules in an answer that lost every line break', () => {
    const collapsed = 'SAP BRIM Billing sits at the heart of Quote-to-Cash. '.repeat(5) + '---### The Workflow#### **Step 1: Setup**Before billing can occur.';
    const out = repairCollapsedMarkdown(collapsed);
    expect(out).toContain('\n\n---\n\n### The Workflow');
    expect(out).toContain('\n\n#### **Step 1: Setup**');
  });

  it('leaves answers that already have line breaks, and short text, alone', () => {
    const fine = 'Intro.\n\n## Heading\n\n' + 'text '.repeat(60);
    expect(repairCollapsedMarkdown(fine)).toBe(fine);
    expect(repairCollapsedMarkdown('C# ### short')).toBe('C# ### short');
  });
});
