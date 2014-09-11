# These are examples on how to to use this class:
# 1) Pass the launchpad object and the distribution if not oil
# 2) Call the provided methods to retrieve bug information
# Note that this class will keep an internal list of the tasks
# object for each bug and store it as a dictionary.


import re
from doberman.common import utils

LOG = utils.get_logger('doberman.getbugs')


class BugInfo():
    def __init__(self, launchpad, dist="oil"):
        self.launchpad = launchpad
        self.dist = dist
        self.bugtasks = None
        self.get_tasks()

    # Method: get_tasks()
    # Description: This returns all the tasks in distribution.
    def get_tasks(self):
        distobj = self.launchpad.distributions[self.dist]
        self.bugtasks = distobj.searchTasks()

    # Method: get_duplicates()
    # Description: Return duplicates for bug number passed in.
    def get_duplicates(self, bugno):
        retdup = []
        bug = None
        matchedbug = None

        if (self.bugtasks == None) or (self.bugtasks == []):
            msg = "There are no bug tasks to work with."
            LOG.exception(msg)
            raise ValueError(msg)
        
        matchedbug = self.launchpad.bugs[bugno]

        duplicates = matchedbug.duplicates
        for dup in duplicates:
            allowedgroups = ["nobody"]
            newentry = []
            newentry.append(dup.id)
            newentry.append(allowedgroups)
            retdup.append(newentry)

        return retdup

    # Method: get_tags()
    # Description: Return tag object bug number passed in.
    def get_tags(self, bugno):
        ret_tags = []
        
        try:
            ret_tags = self.launchpad.bugs[bugno].tags
        except KeyError as ke:
            msg = "Invalid key"
            LOG.exception(msg)
            raise ValueError(msg)

        return ret_tags

    # Method: get_description()
    # Description: Return description
    def get_description(self, bugno):     
        description = None

        try:
            description = self.launchpad.bugs[bugno].description
        except KeyError as ke:
            msg = "Invalid key"
            LOG.exception(msg)
            raise ValueError(msg)

        return description

    # Method: get_bugs()
    # Description: return list of bug number that matches tags. Pass list of
    #              tags or a string space separated tags. This can be later
    #              refined if we find a way to access the the oil bugs without
    #              going through searchTasks.
    def get_bugs(self, tags):
        retbugs = []
        
        # tags can be passed in as list or string, but we'll operate on list.
        intaglist = tags

        # Go through list of bug tasks, and find the bugs that has all
        # the tags passed in.
        for bugtask in self.bugtasks:
            bugtags = bugtask.bug.tags
            found = 0
            for intag in intaglist:
                for bugtag in bugtags:
                    bugtagstr = str(bugtag)
                    if (bugtagstr.find(intag) != -1):
                        found += 1

            if (found == len(intaglist) and (found != 0)):
                retbugs.append(self.get_bugno(bugtask))


        return retbugs

    # Method: get_bugno()
    # Description: return bug number. I haven't found exact field to read
    #              bug number from, so using regex. If better method found,
    #              replace here.

    def get_bugno(self, bugtask):
        return(bugtask.bug.id)

    # Method: get_category()
    # Description: return tags category-
    def get_category(self, bugno):
        try:
            tags = self.launchpad.bugs[bugno].tags
            rettags = [tag.replace("category-", "", 1) for tag in tags if tag.startswith("category-")]
        except KeyError as ke:
            msg = "Invalid key"
            LOG.exception(msg)
            raise ValueError(msg)
        return(rettags)
        

    # Method: get_affect()
    # Description: return tags affect_
    def get_affects(self, bugno):
        try:
            tags = self.launchpad[bugno].tags
            rettags = [tag.replace("affects-", "", 1) for tag in tags if tag.startswith("affects-")]
        except KeyError as ke:
            msg = "Invalid key"
            LOG.exception(msg)
            raise ValueError(msg)
        return(rettags) 
