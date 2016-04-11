import os

DOBERMAN_ROOT = os.getenv('DOBERMAN_ROOT', '/')
CONFIG_DIR = os.path.join(DOBERMAN_ROOT, 'etc', 'doberman')

# doberman.common.utils
DEFAULT_DOBERMAN_CONFIG = os.path.join(CONFIG_DIR, 'doberman.conf')

DEFAULT_VERSION_FOR_BUILD = "notapplicable"
