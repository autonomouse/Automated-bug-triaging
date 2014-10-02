#! /usr/bin/env python2

import sys
from doberman.common import utils

LOG = utils.get_logger('doberman.oilcookie')


def main():
    url = None
    cookie = None
    if len(sys.argv) > 2:
        url = sys.argv[1]
        cookie = sys.argv[2]
    utils.write_cookie_file(url=url, cookie=cookie)
    return 0


if __name__ == '__main__':
    sys.exit(main())
