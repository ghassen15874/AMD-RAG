import re

def is_superseded(filename, content=""):
    tags = {"WITHDRAWN", "SUPERSEDED", "OBSOLETE", "DEPRECATED"}
    upper_name = filename.upper()
    for tag in tags:
        if tag in upper_name:
            return True
    upper_content = content.upper()
    explicit_phrases = [
        "THIS DOCUMENT IS WITHDRAWN",
        "THIS DOCUMENT IS SUPERSEDED",
        "STATUS: WITHDRAWN",
        "STATUS: SUPERSEDED",
        "STATUS: OBSOLETE",
        "STATUS: DEPRECATED",
        "[WITHDRAWN]",
        "[SUPERSEDED]",
    ]
    for phrase in explicit_phrases:
        if phrase in upper_content:
            return True
    return False

def extract_identifiers(text):
    identifiers = set()
    
    # Hyphenated / underscored alphanumeric tokens: TQ-40, ORR-1847, PO-55102, K8S-EAST, CFG-4412, TRK-8819, CHS-301, srv-node-42, IMG-ROCKY-9, pipeline_router
    for match in re.finditer(r'\b[A-Za-z0-9]{1,12}(?:[-_][A-Za-z0-9]{1,12})+\b', text):
        val = match.group(0)
        # Exclude purely lowercase common English hyphenated words like high-pressure, small-batch, burn-in
        if re.search(r'\d', val) or '_' in val or (val.isupper() and len(val) <= 10):
            identifiers.add(val.upper())
        
    # Error codes like E7731
    for match in re.finditer(r'\bE\d{4}\b', text, re.IGNORECASE):
        identifiers.add(match.group(0).upper())
        
    # Versions like 4.3.2
    for match in re.finditer(r'\b\d+\.\d+\.\d+\b', text):
        identifiers.add(match.group(0))
        
    # Revisions like REV-C2
    for match in re.finditer(r'REV-[A-Z0-9]+', text, re.IGNORECASE):
        identifiers.add(match.group(0).upper())
        
    # Pins like B14
    for match in re.finditer(r'\b[A-D]\d{1,2}\b', text):
        identifiers.add(match.group(0))
        
    return identifiers

