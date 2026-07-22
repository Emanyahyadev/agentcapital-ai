"""Paragraph-aware chunking with overlap. Chunks break on paragraph
boundaries where possible so a wire instruction or an allocation clause is
never split mid-sentence; overlap preserves context across boundaries."""


def chunk_text(text: str, size: int = 800, overlap: int = 150) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            # carry the tail of the previous chunk forward as overlap
            current = f"{current[-overlap:]}\n\n{para}".strip()
        else:
            # single paragraph longer than size: hard-split it
            for start in range(0, len(para), size - overlap):
                chunks.append(para[start:start + size])
            current = ""
    if current:
        chunks.append(current)
    return chunks
