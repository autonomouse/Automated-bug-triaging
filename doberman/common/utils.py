import ConfigParser
import logging
import json
import os

from doberman.common import pycookiecheat, const, exception

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
        print 'Logging to %s' % logfile
        _logger.addHandler(f)
    else:
        c = logging.StreamHandler()
        c.setFormatter(logging.Formatter(LOG_FORMAT))
        _logger.addHandler(c)

    return _logger


def get_logger(name='doberman', logfile=None):
    if _loggers.get(name):
        # Use the existing logger.
        return _loggers.get(name)

    try:
        conf = get_config()
        if os.getenv('DOBERMAN_DEBUG'):
            level = 'DEBUG'
        else:
            level = conf.get('DEFAULT', 'log_level')
    except exception.InvalidConfig:
        # probably running  in test suite.
        level = 'DEBUG'

    logger = _get_logger(name=name, level=level, logfile=logfile)
    _loggers[name] = logger
    return logger


def find_config(conf=None):
    """Finds config file, allowing users to specify config via CLI or
    environment variable.  If neither, default config is returned

    :param conf: str path to specified config file.

    :returns: str path to found config file
    :raises: exception.InvalidConfig if config file is not found or cannot
             be loaded.
    """
    if conf:
        if os.path.isfile(conf):
            return conf
        else:
            raise exception.InvalidConfig(
                'Specified config file not found at %s' % conf)

    env_conf = os.getenv('DOBERMAN_ROOT', None)
    env_conf = (env_conf and
                os.path.join(env_conf, 'etc', 'doberman', 'doberman.conf'))
    if env_conf and os.path.isfile(env_conf):
        return env_conf

    if os.path.isfile(const.DEFAULT_DOBERMAN_CONFIG):
        return const.DEFAULT_DOBERMAN_CONFIG

    raise exception.InvalidConfig('Could not find config file')


def _load_config(conf_file):
    config = ConfigParser.RawConfigParser()
    loaded = config.read(conf_file)
    if not loaded:
        msg = 'Config not loaded: %s' % conf_file
        raise exception.InvalidConfig(msg)
    return config


def get_config(conf=None):
    if _config and not conf:
        return _config[0]

    conf_file = find_config(conf)
    config = _load_config(conf_file)
    _config.append(config)
    log = get_logger()
    log.debug('Loaded config from: %s' % conf_file)
    return config


def write_cookie_file(url=None, cookie=None):
    log = get_logger('doberman.utils.write_cookie_file')
    cfg = get_config()
    if not url:
        url = cfg.get('DEFAULT', 'jenkins_url')
    if not cookie:
        cookie = cfg.get('DEFAULT', 'cookie_file')
    log.debug('Looking for a chome_cookie...')
    cookies = pycookiecheat.chrome_cookies(url)
    log.info('Writing %s cookies to %s' % (url, cookie))
    with open(cookie, "w") as o:
        o.write(json.dumps(cookies))
        o.close()
