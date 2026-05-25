import type { Root, Paragraph, PhrasingContent, Text, Link } from 'mdast';

/**
 * Regex matching inline citation patterns in LLM output:
 * - [1], [2], [3], etc.
 * - Also handles [1,2], [1-3], [1,2,3] patterns
 */
const INLINE_CITATION_RE = /\[(\d+(?:[,-]\d+)*)\]/g;

/**
 * Creates a remark plugin that transforms [N] text patterns into
 * link nodes with href="citation://N". The link rendering is handled by
 * the components.a override in ChatMessageList.
 */
export function createInlineCitationPlugin() {
    return () => (tree: Root) => {
        visitParagraphs(tree);
    };
}

function visitParagraphs(node: Root | Paragraph | PhrasingContent): void {
    if (!('children' in node)) return;
    if (node.type === 'paragraph') {
        transformParagraph(node as Paragraph);
    }
    for (const child of (node as { children: PhrasingContent[] }).children) {
        if ('children' in child) {
            visitParagraphs(child);
        }
    }
}

function transformParagraph(para: Paragraph): void {
    const newChildren: PhrasingContent[] = [];
    for (const child of para.children) {
        if (child.type === 'text') {
            newChildren.push(...splitTextNode(child));
        } else {
            newChildren.push(child);
        }
    }
    para.children = newChildren;
}

function splitTextNode(node: Text): PhrasingContent[] {
    const text = node.value;
    const parts: PhrasingContent[] = [];
    let lastIndex = 0;

    INLINE_CITATION_RE.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = INLINE_CITATION_RE.exec(text)) !== null) {
        // Skip if this looks like a page reference [Page N] or [Pages N-M]
        const precedingText = text.slice(Math.max(0, match.index - 10), match.index);
        if (precedingText.match(/page|pages/i)) {
            continue;
        }

        if (match.index > lastIndex) {
            parts.push({ type: 'text', value: text.slice(lastIndex, match.index) });
        }
        const citationIndices = match[1];
        const link: Link = {
            type: 'link',
            url: `citation://${citationIndices}`,
            children: [{ type: 'text', value: match[0] }],
        };
        parts.push(link);
        lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
        parts.push({ type: 'text', value: text.slice(lastIndex) });
    }

    return parts.length > 0 ? parts : [node];
}
