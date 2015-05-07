#! /usr/bin/env python2

import sys
import os
import yaml
from doberman.analysis.analysis import CrudeAnalysis
from pprint import pprint
from filing_station_cli import CLI


class FilingStation(CrudeAnalysis):
    """
    A pun too far...?

    """

    def __init__(self, cli=False):
        """ Overwriting CrudeAnalysis' __init__ method """
        self.message = -1

        self.cli = CLI().populate_cli() if not cli else cli

        # Download and analyse the crude output yamls:
        self.autofile()

    def autofile(self):
        """ Get and analyse the crude output yamls.
        """
        # Get refinery output
        self.cli.LOG.info("Working on {0} as refinery output directory"
                          .format(self.cli.reportdir))
        unfiled_bugs_yamls = [unf_bugs_file for unf_bugs_file in os.listdir(
                              self.cli.reportdir) if 'auto-triaged_' in
                              unf_bugs_file]
        for fname in unfiled_bugs_yamls:
            file_location = os.path.join(self.cli.reportdir, fname)
            with open(file_location, "r") as f:
                bugs_to_file = yaml.load(f).get('pipelines')

            # File bug on launchpad:
            self.create_lp_bugs(bugs_to_file)

    def create_lp_bugs(self, bugs_to_file):
        """
        """

        for pl in bugs_to_file:
            for bug in bugs_to_file[pl]:
                bug_to_file = bugs_to_file[pl][bug]
                num_dupes = str(len(bug_to_file.get('duplicates')))

            environments = {'91.189.92.95': 'Prodstack',
                            '10.98.191.145:8080': 'Serverstack'}
            # Environments should probably be in an external yaml...?

            cloud = environments.get(self.cli.netloc, '')
            pipeline = bug_to_file.get('job').split('_')[1]
            title = "[{}] {} ({} fail)".format(cloud, bug, pipeline)

            warning = "This bug does not yet have an entry in the bugs "
            warning += "database"
            warning += " - remove this line once the bug number and regexp "
            warning += "have been added."

            dup_pipelines = "\n".join
            ([pl for pl in bug_to_file.pop('duplicates')])

            notes = "NOTES \n --------- \n{}\n\n".format(warning)
            link2jen = "LINK TO JENKINS CONSOLE OUTPUT \n --------------------"
            link2jen += "-------------------------- \n "
            link2jen += "\n{}\n\n".format(bug_to_file.pop('link to jenkins'))
            cons_op = "ERRORS, FAILS AND TRACEBACK (NORMALISED) \n"
            cons_op += "------------------------------------ \n"
            cons_op += "\n{}\n\n".format(bug_to_file.pop('match text'))
            example_pl = "EXAMPLE PIPELINE \n --------------------------- \n"
            for buginfo in bug_to_file:
                # I need to turn this into a nice table eventually...
                txt = bug_to_file[buginfo]
                if not txt:
                    conv_txt = "?"
                elif type(txt) is list:
                    conv_txt = "\n".join(txt)
                elif type(txt) is dict:
                    conv_txt = "\n".join("{}: {}".format(k, v) for k, v in
                                         txt.items())
                else:
                    conv_txt = txt
                example_pl += "{}:\n{}\n\n".format(buginfo, conv_txt)

            example_pl += "\n"
            affectedpls = "AFFECTED PIPELINES \n --------------------------- "
            affectedpls += "\n\n{}\n\n".format(dup_pipelines)

            bug_description = notes + link2jen + cons_op + example_pl
            bug_description += affectedpls

            tags = ""

            single_file = (num_dupes, title, bug_description, tags)

            if not self.cli.autofile_on_launchpad:
                self.interactive_filing(single_file)
            else:
                self.file_bugs_on_launchpad(single_file)

    def interactive_filing(self, bug_to_file):
        """ Interactive mode - confirm with user before filing each bug. """

        print
        print
        pprint("\n".join(bug_to_file).split('\n'))
        print
        print
        self.file_bugs_in_folder(bug_to_file)

    def file_bugs_in_folder(self, bug_to_file):
        """
        For now, we're just going to create a file in a mock launchpad folder.
        """
        msg = "Bug filed on {} with launchpad bug id: {}"

        bug_tracker = '/tmp/mock_launchpad/'  # tmp
        self.mkdir(bug_tracker)  # tmp

        file_me = '{}_{}.yml'.format(bug_to_file[0], bug_to_file[1])
        file_path = os.path.join(bug_tracker, file_me)
        with open(file_path, 'w') as outfile:
            for line in bug_to_file[1:]:
                outfile.write(line + "\n")

        lp_bug_id = bug_to_file[1]  # tmp

        self.cli.LOG.info(msg.format(bug_tracker, lp_bug_id))


def main():
    fs = FilingStation()
    return fs.message


if __name__ == "__main__":
    sys.exit(main())
