import time, asyncio
from collections import OrderedDict, defaultdict

SEEN_TTL = 600
SEEN_MAX = 2000
_seen_updates = OrderedDict()
_chat_locks = defaultdict(asyncio.Lock)

def remember_update(update_id: int) -> bool:
    now = time.time()
    while _seen_updates and now - next(iter(_seen_updates.values())) > SEEN_TTL:
        _seen_updates.popitem(last=False)
    if update_id in _seen_updates:
        return False
    _seen_updates[update_id] = now
    while len(_seen_updates) > SEEN_MAX:
        _seen_updates.popitem(last=False)
    return True

def chat_lock(chat_id: int) -> asyncio.Lock:
    return _chat_locks[chat_id]
