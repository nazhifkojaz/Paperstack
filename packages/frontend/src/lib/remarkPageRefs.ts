import type { Root, Paragraph, PhrasingContent, Text, Link } from 'mdast';

/**
 * Regex matching page reference patterns in LLM output:
 * - [Page 5]
 * - [Pages 3-5]
 * - [Pages 3-5 · Introduction]
 * - [Page 12 · Methods and Results]
 */
const PAGE_REF_RE = /\[Pages? (\d+)(?:-(\d+))?(?:\s*[·]\s*[^\]]+)?\]/g;

/**
 * Creates a remark plugin that transforms [Page N] text patterns into
 * link nodes with href="page://N". The link rendering is handled by
 * the components.a override in ChatMessageList.
 */
export function createPageRefPlugin() {
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

    PAGE_REF_RE.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = PAGE_REF_RE.exec(text)) !== null) {
        if (match.index > lastIndex) {
            parts.push({ type: 'text', value: text.slice(lastIndex, match.index) });
        }
        const startPage = match[1];
        const link: Link = {
            type: 'link',
            url: `page://${startPage}`,
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
