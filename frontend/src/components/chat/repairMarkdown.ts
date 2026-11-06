/**
 * Answers stored before the streaming fix lost their line breaks, leaving "...process.Here is ---### Step"
 * on one line. When a long answer has no line break at all, put the obvious Markdown block starts back on
 * their own lines. Answers that already have line breaks are returned untouched.
 */
export function repairCollapsedMarkdown(content: string): string {
  if (content.length < 200 || content.includes('\n')) return content;
  return content
    .replace(/\s*(-{3,})\s*(?=#{2,4}\s)/g, '\n\n---\n\n')
    .replace(/([^\s#-])\s*(#{2,4})\s+(?=\S)/g, '$1\n\n$2 ')
    .replace(/([^\s-])[ \t]*---(?=[ \t]*[^\s#-])/g, '$1\n\n---\n\n')
    .replace(/([.:!?)])\s*(\d{1,2}\.\s+\*\*)/g, '$1\n\n$2')
    .replace(/([.:!?)])\s*-\s+(\*\*)/g, '$1\n- $2');
}
