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
        self.bugdictionary = {}
        self.bugtasks = None
        self.get_tasks()

    # Method: get_tasks()
    # Description: This returns all the tasks in distribution.
    def get_tasks(self):
        distobj = self.launchpad.distributions[self.dist]
        self.bugtasks = distobj.searchTasks()
        
        # create a dictionary so we can get bug task by bug number.
        for bug in self.bugtasks:
            self.bugdictionary[self.get_bugno(bug)] = bug

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
        
        matchedbug = self.bugdictionary[bugno]

        duplicates = matchedbug.bug.duplicates
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
        
        if (bugno < 1):
            msg = "Invalid bug number."
            LOG.exception(msg)
            raise ValueError(msg)

        ret_tags = self.bugdictionary[bugno].bug.tags

        return ret_tags

    # Method: get_description()
    # Description: Return description
    def get_description(self, bugno):     
        description = None

        if (bugno < 1):
            msg = "Invalid bug number."
            LOG.exception(msg)
            raise ValueError(msg)

        description = self.bugdictionary[bugno].bug.description

        return description

    # Method: get_bugs()
    # Description: return list of bug number that matches tags. Pass list of
    #              tags or a string space separated tags.
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
        bugnum = -1
        title = bugtask.title
        numre = re.search('Bug #(\d+) ', title)
        if (numre is not None):
            numstr = numre.group(1)

        bugnum = int(numstr)

        return(bugnum)

    # Method: get_category()
    # Description: return tags category-
    def get_category(self, bugno):
        # call get_tags() and match category-
        tags = self.bugdictionary[bugno].bug.tags
        rettags = []
        for tag in tags:
            if (tag.find("category-") != -1):
                rettags.append(tag)

        return(rettags)
        

    # Method: get_affects()
    # Description: return tags affect-
    def get_affects(self, bugno):
        # call get_tags() and match affects-
        tags = self.bugdictionary[bugno].bug.tags
        rettags = []
        for tag in tags:
            print(tag)
            if (tag.find("affects-") != -1):
                rettags.append(tag)

        return(rettags) 

