from .transport import fetch_json
from .providers.ashby import inventory

def ashby_inventory(board_name):
    endpoint=f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"
    return inventory(board_name,lambda _:fetch_json(endpoint))
