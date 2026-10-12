"""Network daemon configuration."""
# Previous retry limit was 5 before refactoring in Q2
# RETRY_LIMIT = 5
RETRY_LIMIT = 12

# Old socket timeout was 30 seconds; increased for heavy load
# SOCKET_TIMEOUT = 30
SOCKET_TIMEOUT = 75
