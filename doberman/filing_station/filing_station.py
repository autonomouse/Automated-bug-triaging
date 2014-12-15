#! /usr/bin/env python2

import sys
import os
import yaml
from doberman.analysis.analysis import CrudeAnalysis
from doberman.analysis.crude_jenkins import Jenkins
from doberman.analysis.crude_test_catalog import TestCatalog
from doberman.refinery.refinery import Refinery
from pprint import pprint
from cli import CLI

class FilingStation(CrudeAnalysis):
    """
    A pun too far...?
    
    """

    def __init__(self):
        """ Overwriting CrudeAnalysis' __init__ method """

        self.message = -1
        self.cli = CLI()

        # Download and analyse the crude output yamls:
        self.autofile()

        # Tidy Up:
        #if not self.cli.keep_data:
        #    self.remove_dirs(self.all_build_numbers)

    def autofile(self):
        """ Get and analyse the crude output yamls.
        """
        # Get refinery output
        fname = 'auto-triaged_unfiled_bugs.yml'
        self.test_catalog = TestCatalog(self.cli)
        if not self.cli.offline_mode:
            self.jenkins = Jenkins(self.cli)
            self.build_pl_ids_and_check() # But should be pl_start uilds, not pl_deploy 
            output_folder = self.cli.reportdir
            self.download_unfiled_bugs(fname, output_folder)
            # TODO: Fetch from pipeline_start on jenkins...
        
        else:
            self.cli.LOG.info("*** Offline mode is on. ***")
        self.cli.LOG.info("Working on {0} as refinery output directory"
                          .format(self.cli.reportdir))
        file_location = os.path.join(self.cli.reportdir, fname)
        with open(file_location, "r") as f:
            bugs_to_file = yaml.load(f).get('pipelines')
            
        # File bug on launchpad:
        self.create_lp_bugs(bugs_to_file)
        
    def download_unfiled_bugs(self, fname, output_folder):
        # Also get info from pipeline_deploy? No, this should be in pipeline_start already!!!
        #os.path.join(output_folder, fname)
        #import pdb; pdb.set_trace()
        pass
    
    def create_lp_bugs(self, bugs_to_file):    
        """
        """
        
        for bug in bugs_to_file:        
            bug_to_file = bugs_to_file[bug]
            
            environments = {'91.189.92.95': 'Prodstack', 
                            '10.98.191.145:8080': 'Serverstack'}
            cloud = environments.get(self.cli.netloc, '')
            pipeline = bug_to_file.get('job').split('_')[1]
            title = "[{}] {} ({} fail)".format(cloud, bug, pipeline)
            
            warning = "This bug does not yet have an entry in the bugs database"
            warning += " - remove this line once the bug number and regexp have "
            warning += "been added." 
            
            dup_pipelines = "\n".join([pl for pl in bug_to_file.pop('duplicates')])
                        
            notes = "NOTES \n --------- \n{}\n\n".format(warning)
            link2jen = "LINK TO JENKINS CONSOLE OUTPUT \n ------------------------"
            link2jen += "---------------------- \n "
            link2jen += "\n{}\n\n".format(bug_to_file.pop('link to jenkins'))
            cons_op = "ERRORS, FAILS AND TRACEBACK (NORMALISED) \n"
            cons_op += "------------------------------------ \n"
            cons_op += "\n{}\n\n".format(bug_to_file.pop('match text'))
            example_pl = "EXAMPLE PIPELINE \n --------------------------- \n"
            for buginfo in bug_to_file:
                example_pl +="{}: {}\n".format(buginfo, bug_to_file[buginfo])
            example_pl +="\n"
            affectedpls = "AFFECTED PIPELINES \n --------------------------- \n"
            affectedpls += "\n{}\n\n".format(dup_pipelines)
            
            #import pdb; pdb.set_trace()
            # self.cli.match_threshold
            # all_scores
            # link to pipeline_start
            
            bug_description = notes + link2jen + cons_op + example_pl + affectedpls 
            
            tags = ""
            
            single_file = (title, bug_description, tags)        
        
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
        
        message = "Do you wish to file this bug on launchpad (y/N)\n>"
        user_input = raw_input(message)
        if user_input.lower() == 'y':
            self.file_bugs_on_launchpad(bug_to_file)
        else:
            self.cli.LOG.info("This bug has not been filed")
        
    def file_bugs_on_launchpad(self, bug_to_file):
        """
        """
        msg = "Bug filed on {} with launchpad bug id: {}"
        
        # TODO:  
        #lp = self.cli.launchpad_bug_tracker
        #bug_info = BugInfo(lp, 'oil',)
        #lp_bug_id = bug_info(lp, title, bug_description, tags)
        
        self.cli.LOG.info(msg.format('launchpad', lp_bug_id))
        
def main():
    fs = FilingStation()
    return fs.message


if __name__ == "__main__":
    sys.exit(main())
        
