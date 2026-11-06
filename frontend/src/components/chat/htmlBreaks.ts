/**
 * Models often write "<br>" for a line break inside a table cell. The chat does not render raw HTML (so an
 * answer can never inject markup), which made the tag show up as literal text. Instead the tag is swapped
 * for a private marker before parsing, and a tiny remark plugin turns each marker into a real line break.
 */
const BR_TAG = /<br\s*\/?>/gi;
export const BREAK_MARKER = '\u2028';

/**
 * Inside table rows models also scatter other HTML-ish tags to fake a cell layout: "<t>", "<tab>", "<td>",
 * "<tr>", "<li>", "<p>"... They are not rendered either. Line-like ones become line breaks, "<li>" a bullet,
 * and the rest (including their closing tags) are dropped. Only table rows are touched, and only these
 * names, so placeholders such as <tcode> in normal text are left alone.
 */
const ROW_BREAK_TAGS = /<\/?(?:tr|p|div|ul|ol)\s*>/gi;
const ROW_BULLET_TAG = /<li\s*>/gi;
const ROW_DROP_TAGS = /<\/?(?:t|tab|td|th|li|span|b|i|u|strong|em)\s*>/gi;

const cleanTableRow = (line: string): string =>
  line.replace(ROW_BREAK_TAGS, BREAK_MARKER).replace(ROW_BULLET_TAG, `${BREAK_MARKER}• `).replace(ROW_DROP_TAGS, ' ');

export const markHtmlBreaks = (content: string): string =>
  content
    .split(/\r?\n/)
    .map((line) => (line.trimStart().startsWith('|') ? cleanTableRow(line) : line))
    .join('\n')
    .replace(BR_TAG, BREAK_MARKER);

type MdNode = { type: string; value?: string; children?: MdNode[] };

const splitText = (node: MdNode): MdNode[] => {
  const parts = (node.value ?? '').split(BREAK_MARKER);
  const out: MdNode[] = [];
  parts.forEach((part, index) => {
    if (index > 0) out.push({ type: 'break' });
    if (part) out.push({ type: 'text', value: part });
  });
  return out;
};

const walk = (node: MdNode): void => {
  if (!node.children) return;
  node.children = node.children.flatMap((child) => {
    if (child.type === 'text' && child.value?.includes(BREAK_MARKER)) return splitText(child);
    walk(child);
    return [child];
  });
};

/** remark plugin: marker characters in text become line breaks. */
export const remarkHtmlBreaks = () => (tree: MdNode) => walk(tree);
