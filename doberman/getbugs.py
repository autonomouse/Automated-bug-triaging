# These are examples on how to to use this class:
# 1) Login to launchpad
# 2) Instantiate the object with default distribution, tags and defect number.
#    This will take a space separated list of tags, and you can use methods
#    to retrieve bugs matching these tags.
# 3) By passing a bug number, you can retrieve tags and duplicate associated
#    with that bug.
#    a) Get the bug first.. if bug number was not set during instantiation,
#       then you need to set it before calling this rooting.
#    b) Get the tags or get the duplicates using the method provided.
# Note that lauchpad's searchTask() method is being used to get a list of
# tasks for the bugs in a distribution.
#
# EXAMPLE CODE for using this module.
##launchpad = Launchpad.login_with('getbugs.py', 'production')
##
##people = launchpad.people
##lmic = people['lmic']
##print(lmic.display_name)
##bugObj = LaunchpadBugs("maas", "hp", None)
##bugObj.setTag("hp")
##
### EXAMPLES for getting bug tags and duplicates - you can copy and paste and
### replace by your own parameter
##bugObj.setBugNumber(1237215)
##bug = bugObj.getBugByBugNumber()
##tags = bugObj.getTagsByBugNumber()
##
##if (tags != None):
##    print(tags)
##
##duplicates = bugObj.getCurrentBugDuplicates()
##if (duplicates != None):
##    for i in range(len(duplicates)):
##        print("Duplicate bug: " + duplicates[i])

### EXAMPLES for getting bugs by tags
##bug = bugObj.getFirstTaggedBugTask()
##if (bug != None):
##    print(bug.bug.tags)
##
##bug = bugObj.getNextTaggedBugTask()
##if (bug != None):
##    print(bug.bug.tags)

import re
from doberman.common import utils

LOG = utils.get_logger('doberman.getbugs')


# class to get process launchpad bugs based on tag
class LaunchpadBugs():
    def __init__(self, indist, inTag, inBugNum, inLaunchpadObj):
        self.dist = indist
        self.tags = inTag
        self.bugnumber = str(inBugNum)
        self.launchpadObj = inLaunchpadObj
        self.currentIdx = 0
        self.bugtasks = []
        self.bugtaskslength = 0
        self.currentBug = None
        self.currentBugDuplicates = []
        self.getAllTasks()

    # Method: setBugByNumber()
    # Description: Set current bug number
    def setBugNumber(self, numinput):
        self.bugnumber = str(numinput)

    # Method: getBugNumber()
    # Description: Return current bug number to caller
    def getBugNumber(self):
        return self.bugnumber

    # Method: getBugByBugNumber()
    # Description: Return bug object to caller and update current bug task.
    def getBugByBugNumber(self):
        if self.getBugNumber() is None:
            msg = "ERROR - bug number is not set - call setNumber() first"
            LOG.exception(msg)
            raise ValueError(msg)

        for i in range(len(self.bugtasks)):
            self.currentBug = self.bugtasks[i]
            title = self.currentBug.title
            retnum = re.search('Bug #(\d+) ', title)
            if (retnum is not None):
                bugnum = retnum.group(1)

            if bugnum == self.getBugNumber():
                # got a match
                break
        return self.currentBug

    # Method: getTagsByBugNumber()
    # Description: Return tag object for current bug.
    def getTagsByBugNumber(self):
        if self.currentBug is None:
            msg = "ERROR - There is no bug in memory" + \
                  "- call getBugsByBugNumber first"
            LOG.exception(msg)
            raise ValueError(msg)

        return self.currentBug.bug.tags

    # Method: getCurrentBugDuplicates()
    # Description: Return current bug duplicate list for current bug.
    def getCurrentBugDuplicates(self):
        retdup = []
        if (self.currentBug is None):
            msg = "ERROR - No bug was fetched - call getBugsByBugNumber first"
            LOG.exception(msg)
            raise ValueError(msg)

        duplicates = self.currentBug.bug.duplicates
        for dup in duplicates:
            retdup.append(str(dup.id))

        return retdup

    # Method: getAllTasks()
    # Description: This returns all the tasks in distribution.
    def getAllTasks(self):
        distobj = self.launchpadObj.distributions[self.dist]
        self.bugtasks = distobj.searchTasks()
        self.bugtaskslength = len(self.bugtasks)

    # Method: getFirstTask()
    # Description: Return the first bug in the list of tasks.
    def getFirstTask(self):
        bugtask = self.bugtasks[0]
        self.currentIdx = 1
        return bugtask

    # Method: getNextTask()
    # Description: Return the next bug task in the list.
    def getNextTask(self):
        if (self.currentIdx == self.bugtaskslength):
            bugtask = None
        else:
            bugtask = self.bugtasks[self.currentIdx]
            self.currentIdx += 1
        return bugtask

    # Method: getLastBugTask()
    # Description: Return the first bug in the list.
    def getLastBugTask(self):
        bug = self.bugtasks[self.bugtaskslength - 1]
        self.currentIdx = self.bugtaskslength
        return bugtask

    # Method: setTag()
    # Description: Takes as input space separated list of tags and update
    #              internal task list for this class object.
    def setTag(self, intag):
        self.tags = intag.split()

    # Method: clearTag()
    # Description: clear tags list for this class object.
    def clearTag(self):
        self.tags = []

    # Method: getFirstTaggedBugTask()
    # Description: Return the first bug task in the task list returned by
    #              searchTask().
    def getFirstTaggedBugTask(self):
        if (self.tags == []):
            msg = "ERROR - There are no tags set - call setTag() first"
            LOG.exception(msg)
            raise ValueError(msg)
        else:
            return self.getNextTaggedBugTask()

    # Method: getNextTaggedBugTask()
    # Description: Return the next bug task in the task list returned by
    #              searchTask().
    def getNextTaggedBugTask(self):
        ret = None

        if (self.currentIdx == self.bugtaskslength):
            # reached end of list
            ret = None
        else:
            numtags = len(self.tags)
            found = 0

            # Look for the next entry in task list which matches all the
            # tags passed in
            while (found != numtags) and (self.currentIdx != self.bugtaskslength):
                bugtask = self.bugtasks[self.currentIdx]
                bugtags = bugtask.bug.tags
                found = 0

                # Look through all the entries, looking for a match.
                # If a match is not found, go to next entry.
                for i in range(numtags):
                    for j in range(len(bugtags)):
                        if (self.tags[i] == bugtags[j]):
                            found += 1
                            break

                # point to next bugtask
                self.currentIdx += 1

            # return match or nothing
            if (found == numtags):
                ret = bugtask

        return ret

    # Method: getLastTaggedBugTask()
    # Description: Return the first bug in the list.
    def getLastTaggedBugTask(self):
        # get the next tag until there are no more tags
        # To be completed
        raise ValueError("Not Implemented")
