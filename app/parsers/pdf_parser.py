import pypdf

def parse_pdf(path):
    chunks = []
    try:
        reader = pypdf.PdfReader(path)
        if reader.is_encrypted:
            print(f"Skipping encrypted PDF: {path}")
            return []
            
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                chunks.append({"text": text, "page": i + 1})
    except Exception as e:
        print(f"Error parsing PDF {path}: {e}")
    return chunks
