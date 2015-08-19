from doberman.common.CLI import CLI
from doberman.common.base import DobermanBase
from doberman.weebl_tools.weebl import Weebl
from doberman.analysis.crude_jenkins import Jenkins


class SetUpNewEnvironment(DobermanBase):

    def __init__(self, cli=False):
        self.cli = CLI().populate_cli() if not cli else cli
        self.weebl = Weebl(self.cli)
        self.jenkins = Jenkins(self.cli)
        self.weebl.weeblify_environment(self.jenkins.jenkins_api, report=True)

if __name__ == "__main__":
    SetUpNewEnvironment()
