import os
import logging


_config = []
_loggers = {}

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'


def _get_logger(name, level='DEBUG', logfile=None):
    _logger = logging.getLogger(name)
    _logger.propagate = False

    if level == 'DEBUG':
        lvl = logging.DEBUG
    elif level == 'INFO':
        lvl = logging.INFO

    _logger.setLevel(lvl)

    if logfile:
        f = logging.FileHandler(logfile)
        f.setLevel(lvl)
        f.setFormatter(logging.Formatter(LOG_FORMAT))
        print("Logging to {}".format(logfile))
        _logger.addHandler(f)
    else:
        c = logging.StreamHandler()
        c.setFormatter(logging.Formatter(LOG_FORMAT))
        _logger.addHandler(c)

    return _logger


def get_logger(name='weebl_client', logfile=None):
    if _loggers.get(name):
        # Use the existing logger.
        return _loggers.get(name)

    if os.getenv('WEEBL_CLIENT_DEBUG'):
        level = 'DEBUG'
    else:
        level = 'INFO'

    logger = _get_logger(name=name, level=level, logfile=logfile)
    _loggers[name] = logger
    return logger
