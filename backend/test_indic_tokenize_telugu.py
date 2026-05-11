from pathlib import Path
import re
import sys

from indicnlp.tokenize import sentence_tokenize


def main() -> None:
    # Ensure Telugu characters print correctly on Windows consoles.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # Optional CLI override: python backend/test_indic_tokenize_telugu.py <path_to_text_file>
    input_path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent / "ntg" / "news.txt"
    )

    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"\s+", " ", text).strip()

    lang = "te"  # Telugu
    sentences = sentence_tokenize.sentence_split(text, lang=lang)

    print(f"Input file: {input_path}")
    print(f"Language: {lang} (Telugu)")
    print(f"Total sentences: {len(sentences)}")
    print("-" * 60)

    for i, sent in enumerate(sentences, start=1):
        cleaned = sent.strip()
        if cleaned:
            print(f"{i:03d}: {cleaned}")


if __name__ == "__main__":
    main()
