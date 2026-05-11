/**
 * Shared utilities for annotation frontend.
 * computeSentences: used by POS and Span-Rel for sentence-based rendering.
 */

(function () {
  /**
   * Use newline split when content has multiple lines (sentence-segmented); else regex for legacy.
   */
  function computeSentences(content) {
    if (!content || typeof content !== "string") return [];
    const lines = content.split("\n");
    if (lines.length > 1) {
      const sentences = [];
      let pos = 0;
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const start = pos;
        const end = pos + line.length;
        sentences.push({ start, end, text: line });
        pos = end + (i < lines.length - 1 ? 1 : 0);
      }
      return sentences;
    }
    const sentences = [];
    const regex = /\S[^.?!]*(?:\.|\!|\?)(?!(?:[\d.]|\s*[A-Za-z]\.))\s*(?=\s*[A-Z])/g;
    let lastIndex = 0;
    let match;
    while ((match = regex.exec(content)) !== null) {
      const end = match.index + match[0].length;
      sentences.push({
        start: lastIndex,
        end: end,
        text: content.slice(lastIndex, end).trim()
      });
      lastIndex = end;
    }
    if (lastIndex < content.length) {
      sentences.push({
        start: lastIndex,
        end: content.length,
        text: content.slice(lastIndex).trim()
      });
    }
    return sentences;
  }

  window.computeSentences = computeSentences;
})();
