class temp(object):
    ME = None
    U_NAME = None
    B_NAME = None
    BANNED_USERS = []
    BANNED_CHATS = []


def humanbytes(size):
    if not size:
        return "0 B"
    power = 1024
    n = 0
    dic_power_n = {0: '', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + ' ' + dic_power_n[n] + 'B'
