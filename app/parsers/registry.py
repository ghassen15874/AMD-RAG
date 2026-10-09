import re

def is_superseded(filename, content=""):
    tags = {"WITHDRAWN", "SUPERSEDED", "OBSOLETE", "DEPRECATED"}
    upper_name = filename.upper()
    upper_content = content.upper()
    for tag in tags:
        if tag in upper_name or tag in upper_content:
            return True
    return False

def extract_identifiers(text):
    identifiers = set()
    
    # Tickets like ORR-1847
    for match in re.finditer(r'[A-Z]{3}-\d{3,4}', text):
        identifiers.add(match.group(0))
        
    # Error codes like E7731
    for match in re.finditer(r'E\d{4}', text):
        identifiers.add(match.group(0))
        
    # Part numbers like ORR-FAN-2214-B
    for match in re.finditer(r'[A-Z0-9]{3,}-[A-Z0-9]+-\d+-[A-Z0-9]+', text):
        identifiers.add(match.group(0))
        
    # Versions like 4.3.2
    for match in re.finditer(r'\b\d+\.\d+\.\d+\b', text):
        identifiers.add(match.group(0))
        
    # Revisions like REV-C2 or r2
    for match in re.finditer(r'REV-[A-Z0-9]+', text, re.IGNORECASE):
        identifiers.add(match.group(0).upper())
    for match in re.finditer(r'\br\d+\b', text, re.IGNORECASE):
        identifiers.add(match.group(0).lower())
        
    return identifiers
