#! /usr/bin/env python2

import sys
from doberman.common import utils

LOG = utils.get_logger('doberman.oilcookie')


def main():
    utils.write_cookie_file()
    return 0


if __name__ == '__main__':
    sys.exit(main())
