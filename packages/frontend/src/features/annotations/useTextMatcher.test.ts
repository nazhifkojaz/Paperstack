import { describe, it, expect } from 'vitest'
import { collectTextNodes } from '@/features/viewer/pdfTextUtils'
import {
    buildNormMap,
    normalize,
    tokenize,
    wordLcsMatch,
} from './useTextMatcher'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Create a container div mimicking pdf.js TextLayer structure: each string is a <span>. */
function makeContainer(spans: string[]): HTMLDivElement {
    const div = document.createElement('div')
    for (const text of spans) {
        const span = document.createElement('span')
        span.textContent = text
        div.appendChild(span)
    }
    return div
}

// ─── collectTextNodes ────────────────────────────────────────────────────────

describe('collectTextNodes', () => {
    it('inserts space between span-separated words', () => {
        const container = makeContainer(['relevant', 'study'])
        const { fullText } = collectTextNodes(container)
        expect(fullText).toBe('relevant study')
    })

    it('does not double-space when span already ends with space', () => {
        const container = makeContainer(['word ', 'next'])
        const { fullText } = collectTextNodes(container)
        expect(fullText).toBe('word next')
    })

    it('does not double-space when next span starts with space', () => {
        const container = makeContainer(['word', ' next'])
        const { fullText } = collectTextNodes(container)
        expect(fullText).toBe('word next')
    })

    it('maps text node start/end correctly with injected spaces', () => {
        const container = makeContainer(['hello', 'world'])
        const { textNodes, fullText } = collectTextNodes(container)
        expect(fullText).toBe('hello world')
        expect(textNodes[0].start).toBe(0)
        expect(textNodes[0].end).toBe(5)
        // After injected space at position 5, second node starts at 6
        expect(textNodes[1].start).toBe(6)
        expect(textNodes[1].end).toBe(11)
    })

    it('handles single span with no injected space', () => {
        const container = makeContainer(['single'])
        const { fullText, textNodes } = collectTextNodes(container)
        expect(fullText).toBe('single')
        expect(textNodes).toHaveLength(1)
    })

    it('handles empty container', () => {
        const container = document.createElement('div')
        const { fullText, textNodes } = collectTextNodes(container)
        expect(fullText).toBe('')
        expect(textNodes).toHaveLength(0)
    })

    it('handles many spans simulating a sentence', () => {
        const container = makeContainer(['The', 'quick', 'brown', 'fox'])
        const { fullText } = collectTextNodes(container)
        expect(fullText).toBe('The quick brown fox')
    })

    it('does not inject space between text nodes with the same parent', () => {
        const div = document.createElement('div')
        const span = document.createElement('span')
        span.appendChild(document.createTextNode('hello'))
        span.appendChild(document.createTextNode('world'))
        div.appendChild(span)
        const { fullText } = collectTextNodes(div)
        // Same parent span -> no injected space
        expect(fullText).toBe('helloworld')
    })
})

// ─── normalize ───────────────────────────────────────────────────────────────

describe('normalize', () => {
    it('lowercases text', () => {
        expect(normalize('HELLO')).toBe('hello')
    })

    it('collapses whitespace', () => {
        expect(normalize('a  b\tc')).toBe('a b c')
    })

    it('normalizes smart quotes', () => {
        expect(normalize('\u2018hello\u2019')).toBe("'hello'")
        expect(normalize('\u201Chello\u201D')).toBe('"hello"')
    })

    it('normalizes dashes', () => {
        expect(normalize('a\u2013b\u2014c')).toBe('a-b-c')
    })

    it('normalizes fi ligature', () => {
        expect(normalize('\uFB01nd')).toBe('find')
    })

    it('normalizes fl ligature', () => {
        expect(normalize('\uFB02ow')).toBe('flow')
    })

    it('normalizes ff ligature', () => {
        expect(normalize('\uFB00ect')).toBe('ffect')
    })

    it('strips zero-width chars', () => {
        expect(normalize('he\u200Bllo')).toBe('hello')
    })

    it('trims leading/trailing whitespace', () => {
        expect(normalize('  hello  ')).toBe('hello')
    })
})

// ─── buildNormMap ────────────────────────────────────────────────────────────

describe('buildNormMap', () => {
    it('maps basic ASCII characters correctly', () => {
        const { norm, toOrig } = buildNormMap('hello world')
        expect(norm).toBe('hello world')
        expect(toOrig[0]).toBe(0)
        expect(toOrig[6]).toBe(6) // 'w'
        expect(toOrig.length).toBe(norm.length)
    })

    it('expands fi ligature with correct toOrig positions', () => {
        // \uFB01 is a single char at position 0 in the original
        const { norm, toOrig } = buildNormMap('\uFB01nd')
        expect(norm).toBe('find')
        expect(toOrig[0]).toBe(0) // 'f' maps to original position 0
        expect(toOrig[1]).toBe(1) // 'i' maps to position 1 (past the ligature)
        expect(toOrig[2]).toBe(1) // 'n' maps to position 1
        expect(toOrig[3]).toBe(2) // 'd' maps to position 2
    })

    it('ligature expansion does not produce zero-length ranges', () => {
        const { norm, toOrig } = buildNormMap('pre\uFB01x')
        const fiIdx = norm.indexOf('fi')
        // Second ligature char should map to a position AFTER the first
        expect(toOrig[fiIdx + 1]).toBeGreaterThan(toOrig[fiIdx])
    })

    it('folds curly quotes to straight quotes', () => {
        const { norm } = buildNormMap('\u2018hello\u2019')
        expect(norm).toBe("'hello'")
    })

    it('collapses multiple spaces to single space', () => {
        const { norm } = buildNormMap('a   b')
        expect(norm).toBe('a b')
    })

    it('toOrig positions index into original fullText', () => {
        const orig = 'hello world'
        const { toOrig } = buildNormMap(orig)
        for (const pos of toOrig) {
            expect(pos).toBeGreaterThanOrEqual(0)
            expect(pos).toBeLessThan(orig.length)
        }
    })

    it('handles empty string', () => {
        const { norm, toOrig } = buildNormMap('')
        expect(norm).toBe('')
        expect(toOrig).toHaveLength(0)
    })

    it('skips zero-width characters', () => {
        const { norm } = buildNormMap('he\u200Bllo')
        expect(norm).toBe('hello')
    })

    it('lowercases all output', () => {
        const { norm } = buildNormMap('HELLO World')
        expect(norm).toBe('hello world')
    })

    it('handles em-dash normalization', () => {
        const { norm } = buildNormMap('a\u2014b')
        expect(norm).toBe('a-b')
    })
})

// ─── tokenize ────────────────────────────────────────────────────────────────

describe('tokenize', () => {
    it('tokenizes simple words', () => {
        const words = tokenize('hello world')
        expect(words).toEqual([
            { word: 'hello', start: 0, end: 5 },
            { word: 'world', start: 6, end: 11 },
        ])
    })

    it('handles hyphenated words', () => {
        const words = tokenize("well-known it's")
        expect(words).toEqual([
            { word: "well-known", start: 0, end: 10 },
            { word: "it's", start: 11, end: 15 },
        ])
    })

    it('includes numbers', () => {
        const words = tokenize('page 42 has results')
        expect(words.map(w => w.word)).toEqual(['page', '42', 'has', 'results'])
    })

    it('returns empty for empty string', () => {
        expect(tokenize('')).toEqual([])
    })
})

// ─── wordLcsMatch ────────────────────────────────────────────────────────────

describe('wordLcsMatch', () => {
    it('returns null for needle shorter than 3 words', () => {
        const { norm: haystack, toOrig } = buildNormMap('the quick brown fox')
        const needle = normalize('quick fox')
        const result = wordLcsMatch(haystack, needle, toOrig, 19)
        expect(result).toBeNull()
    })

    it('matches >= 60% in-order words', () => {
        const orig = 'the quick brown fox jumps over the lazy dog'
        const { norm: haystack, toOrig } = buildNormMap(orig)
        // 4 of 5 words match = 80%
        const needle = normalize('quick brown jumps lazy dog')
        const result = wordLcsMatch(haystack, needle, toOrig, orig.length, 0.6)
        expect(result).not.toBeNull()
        expect(result!.start).toBeGreaterThanOrEqual(0)
        expect(result!.end).toBeLessThanOrEqual(orig.length)
    })

    it('rejects when fewer than threshold words match', () => {
        const orig = 'apple banana cherry date elderberry fig grape'
        const { norm: haystack, toOrig } = buildNormMap(orig)
        // Only 2 of 7 words match = 28%
        const needle = normalize('apple banana xyz abc def ghi jkl')
        const result = wordLcsMatch(haystack, needle, toOrig, orig.length, 0.6)
        expect(result).toBeNull()
    })

    it('uses stricter threshold when passed 0.75', () => {
        const orig = 'one two three four five six seven eight'
        const { norm: haystack, toOrig } = buildNormMap(orig)
        // 5 of 8 words = 62.5% — passes 0.6 but not 0.75
        const needle = normalize('one two three four five xxx yyy zzz')
        const result60 = wordLcsMatch(haystack, needle, toOrig, orig.length, 0.6)
        const result75 = wordLcsMatch(haystack, needle, toOrig, orig.length, 0.75)
        expect(result60).not.toBeNull()
        expect(result75).toBeNull()
    })

    it('returns correct span boundaries', () => {
        const orig = 'prefix the important text here suffix'
        const { norm: haystack, toOrig } = buildNormMap(orig)
        const needle = normalize('the important text here')
        const result = wordLcsMatch(haystack, needle, toOrig, orig.length, 0.6)
        expect(result).not.toBeNull()
        // The span should cover "the important text here" within the original
        const matched = orig.slice(result!.start, result!.end)
        expect(matched).toContain('the')
        expect(matched).toContain('here')
    })

    it('rejects spans wildly different from expected length', () => {
        const orig = 'a b c d e f g h i j k l m n o p q r s t u v w x y z'
        const { norm: haystack, toOrig } = buildNormMap(orig)
        // Short needle but matches words scattered across the entire haystack
        const needle = normalize('a z completely different')
        const result = wordLcsMatch(haystack, needle, toOrig, orig.length, 0.6)
        // Should be null because span would be much larger than expected
        expect(result).toBeNull()
    })
})
