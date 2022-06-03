import json
import logging
import random
import string
import time

random.seed(time.time())


LOGGING_LEVEL = {
    'CRITICAL': logging.CRITICAL,
    'FATAL': logging.FATAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
}


def get_logger(name, cfg):
    logger = logging.getLogger(name)
    logger.setLevel(LOGGING_LEVEL[cfg['logging_level']])
    handler = logging.FileHandler(cfg['logging_file'])
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger


def gen_random_string(length=10):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def gen_task_id():
    return str(int(time.time()))


def get_config(filename):
    with open(filename) as f:
        return json.load(f)


def gen_new_cid(old_cid, new_cid, mode):
    if mode == 'split':
        if new_cid is None:
            new_cid = 0
        return f'{old_cid}-{new_cid}'
    elif mode == 'merge':
        if new_cid is None:
            return old_cid
        else:
            return new_cid

