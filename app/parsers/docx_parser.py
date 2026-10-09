import docx

def parse_docx(path):
    chunks = []
    try:
        doc = docx.Document(path)
        
        # Headers/Footers
        for section in doc.sections:
            if section.header:
                for p in section.header.paragraphs:
                    if p.text.strip():
                        chunks.append({"text": p.text.strip(), "source": "header"})
            if section.footer:
                for p in section.footer.paragraphs:
                    if p.text.strip():
                        chunks.append({"text": p.text.strip(), "source": "footer"})

        # Paragraphs
        for p in doc.paragraphs:
            if p.text.strip():
                chunks.append({"text": p.text.strip()})
                
        # Tables
        for table in doc.tables:
            for row in table.rows:
                row_data = [cell.text.strip() for cell in row.cells]
                text = " | ".join(row_data)
                if text.strip():
                    chunks.append({"text": text, "source": "table"})
    except Exception as e:
        print(f"Error parsing DOCX {path}: {e}")
    return chunks
