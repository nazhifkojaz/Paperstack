import { describe, it, expect } from 'vitest'
import { createPageRefPlugin } from './remarkPageRefs'
import type { Root, Paragraph } from 'mdast'

function runPlugin(text: string): Paragraph {
  const plugin = createPageRefPlugin()
  const transformer = plugin()
  const tree: Root = {
    type: 'root',
    children: [
      {
        type: 'paragraph',
        children: [{ type: 'text', value: text }],
      },
    ],
  }
  transformer(tree)
  return tree.children[0] as Paragraph
}

describe('remarkPageRefs', () => {
  it('transforms [Page 5] into a page://5 link', () => {
    const para = runPlugin('See [Page 5] for details.')

    expect(para.children).toHaveLength(3)
    expect(para.children[0]).toEqual({ type: 'text', value: 'See ' })
    expect(para.children[1]).toEqual({
      type: 'link',
      url: 'page://5',
      children: [{ type: 'text', value: '[Page 5]' }],
    })
    expect(para.children[2]).toEqual({ type: 'text', value: ' for details.' })
  })

  it('transforms [Pages 3-5] into a page://3 link', () => {
    const para = runPlugin('Discussed in [Pages 3-5].')

    expect(para.children).toHaveLength(3)
    expect(para.children[0]).toEqual({ type: 'text', value: 'Discussed in ' })
    expect(para.children[1]).toEqual({
      type: 'link',
      url: 'page://3',
      children: [{ type: 'text', value: '[Pages 3-5]' }],
    })
    expect(para.children[2]).toEqual({ type: 'text', value: '.' })
  })

  it('transforms [Pages 3-5 · Introduction] with section title', () => {
    const para = runPlugin('See [Pages 3-5 · Introduction].')

    const link = para.children[1]
    expect(link).toEqual({
      type: 'link',
      url: 'page://3',
      children: [{ type: 'text', value: '[Pages 3-5 · Introduction]' }],
    })
  })

  it('transforms [Page 12 · Methods and Results] with section title', () => {
    const para = runPlugin('Methods are in [Page 12 · Methods and Results].')

    const link = para.children[1]
    expect(link).toEqual({
      type: 'link',
      url: 'page://12',
      children: [{ type: 'text', value: '[Page 12 · Methods and Results]' }],
    })
  })

  it('handles multiple page refs in one paragraph', () => {
    const para = runPlugin('See [Page 2] and [Pages 5-7] for more.')

    expect(para.children).toHaveLength(5)
    expect(para.children[0]).toEqual({ type: 'text', value: 'See ' })
    expect(para.children[1]).toEqual({
      type: 'link',
      url: 'page://2',
      children: [{ type: 'text', value: '[Page 2]' }],
    })
    expect(para.children[2]).toEqual({ type: 'text', value: ' and ' })
    expect(para.children[3]).toEqual({
      type: 'link',
      url: 'page://5',
      children: [{ type: 'text', value: '[Pages 5-7]' }],
    })
    expect(para.children[4]).toEqual({ type: 'text', value: ' for more.' })
  })

  it('leaves text unchanged when no page refs match', () => {
    const para = runPlugin('No references here.')

    expect(para.children).toHaveLength(1)
    expect(para.children[0]).toEqual({ type: 'text', value: 'No references here.' })
  })

  it('handles text that is only a page ref', () => {
    const para = runPlugin('[Page 42]')

    expect(para.children).toHaveLength(1)
    expect(para.children[0]).toEqual({
      type: 'link',
      url: 'page://42',
      children: [{ type: 'text', value: '[Page 42]' }],
    })
  })
})
