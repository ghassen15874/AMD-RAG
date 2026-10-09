import os

try:
    import torch
except ImportError:
    torch = None

def get_device():
    if torch is not None and torch.cuda.is_available():
        return torch.device("cuda")
    return "cpu"

def get_dtype():
    if torch is not None and torch.cuda.is_available():
        return torch.bfloat16
    return None

def report_vram():
    if torch is not None and torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        used = (total - free) / (1024**3)
        return used
    return 0.0
