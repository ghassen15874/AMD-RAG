import csv

def parse_csv(path):
    chunks = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if headers:
                for i, row in enumerate(reader, start=1):
                    row_pairs = []
                    for j, cell in enumerate(row):
                        if cell.strip():
                            col_name = headers[j] if j < len(headers) else f"Col{j}"
                            row_pairs.append(f"{col_name}: {cell.strip()}")
                    if row_pairs:
                        chunks.append({"text": f"Row {i}: " + ", ".join(row_pairs)})
    except Exception as e:
        print(f"Error parsing CSV {path}: {e}")
    return chunks
