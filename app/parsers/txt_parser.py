def parse_txt(path):
    chunks = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                text = line.strip()
                if text:
                    chunks.append({"text": text, "line": i})
    except Exception as e:
        print(f"Error parsing TXT {path}: {e}")
    return chunks
