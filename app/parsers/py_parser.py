import ast

def parse_py(path):
    chunks = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
            
        chunks.append({"text": source, "type": "source_code"})
        
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                            chunks.append({"text": f"{target.id} = {node.value.value}", "type": "constant"})
        except Exception:
            pass
            
    except Exception as e:
        print(f"Error parsing PY {path}: {e}")
    return chunks
