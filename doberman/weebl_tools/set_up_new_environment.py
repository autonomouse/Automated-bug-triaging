from doberman.common.CLI import CLI
from doberman.common.common import Common
from doberman.weebl_tools.weebl import Weebl


class SetUpNewEnvironment(Common):

    def __init__(self, cli=False):
        self.cli = CLI().populate_cli() if not cli else cli
        self.weebl = Weebl(self.cli)

if __name__ == "__main__":
    SetUpNewEnvironment()
