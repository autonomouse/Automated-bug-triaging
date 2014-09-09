# These are examples on how to to use this class:
# 1) Login to launchpad
# 2) Instantiate the object with default distribution, tags and defect number.
#    This will take a space separated list of tags, and you can use methods
#    to retrieve bugs matching these tags.
# 3) By passing a bug number, you can retrieve tags and duplicate associated
#    with that bug.
#    a) Get the bug first.. if bug number was not set during instantiation, then
#       you need to set it before calling this rooting.
#    b) Get the tags or get the duplicates using the method provided.
#
#
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
##bug = bugObj.getFirstTaggedBug()
##if (bug != None):
##    print(bug.bug.tags)
##    
##bug = bugObj.getNextTaggedBug()
##if (bug != None):
##    print(bug.bug.tags)

from launchpadlib.launchpad import Launchpad
import re

# class to get process launchpad bugs based on tag
class LaunchpadBugs():
    def __init__(self, indist, inTag, inbug):
        self.dist = indist
        self.tags = []
        self.bugnumber = str(inbug)
        self.currentIdx = 0
        self.bugtasks = []
        self.currentBug = None
        self.currentBugDuplicates = []
        self.getAllTasks()
        

    # Method: getBugByNumber()
    # Description: Return current bug
    def setBugNumber(self, numinput):
        self.bugnumber = str(numinput)
        print("Set bug number to " + self.bugnumber)

    # Method: getBugNumber()
    # Description: Return current bug
    def getBugNumber(self):
        return self.bugnumber   

    # Method: getBugByBugNumber()
    # Description: Return current bug
    def getBugByBugNumber(self):
        if (self.getBugNumber() == None):
            print("Bug number is not set - call setNumber() first")
            return None
        
        for i in range(len(self.bugtasks)):
            self.currentBug = self.bugtasks[i]
            title = self.currentBug.title
            retnum = re.search('Bug #(\d+) ', title)
            if (retnum != None):
                bugnum = retnum.group(1)

            if (bugnum == self.getBugNumber()):
                # got a match
                break
        return self.currentBug

    # Method: getTagsByBugNumber()
    # Description: Return current bug
    def getTagsByBugNumber(self):
        if (self.currentBug == None):
            print("No bug was fetch - call getBugsByBugNumber first")
            return None
        return self.currentBug.bug.tags

    # Method: getCurrentBugDuplicates()
    # Description: Return current bug
    def getCurrentBugDuplicates(self):
        retdup = []
        if (self.currentBug == None):
            print("No bug was fetch - call getBugsByBugNumber first")
            return None
    
        duplicates = self.currentBug.bug.duplicates
        for dup in duplicates:
            print(dup.id)
            retdup.append(str(dup.id))
        return retdup

    # Method: getAllTasks()
    # Description: This returns all the bugs in distribution
    # 
    def getAllTasks(self):
        distobj = launchpad.distributions[self.dist]
        self.bugtasks = distobj.searchTasks()
        self.len = len(self.bugtasks)
        print(self.len)

    # Method: getFirstBugByTag()
    # Description: Return the first bug in the list.
    def getFirstBug(self):
        bug = self.bugtasks[0]
        self.currentIdx = 1
        return bug  

    # Method: getNextBugByTag()
    # Description: Return the next bug in the list.
    def getNextBug(self):
        if (self.currentIdx == self.len):
            print("Reached end of list")
            retname = ""
        else:
            bug = self.bugtasks[self.currentIdx]
            self.currentIdx += 1
            
        return bug

    # Method: getLastBug()
    # Description: Return the first bug in the list.
    def getLastBug(self):
        bug = self.bugtasks[self.len-1]
        self.currentIdx = self.len

        return bug


    # Method: setTag()
    # Description: Takes as input space separated list of tags
    def setTag(self, intag):
        self.tags = intag.split()


    # Method: clearTag()
    # Description: setTag
    def clearTag(self):
        self.tags = []

    # Method: getFirstTaggedBug()
    # Description: Return the first bug in the list.
    def getFirstTaggedBug(self):
        if (self.tags == []):
            print("There are no tags set")
            return self.getFirstBug()
        else:
            return self.getNextTaggedBug()       
   

    # Method: getNextTaggedBug()
    # Description: Return the next bug in the list.
    def getNextTaggedBug(self):
        retname = ""
        ret = None
        
        if (self.currentIdx == self.len):
            print("Reached end of list")
            ret = None
        else:
            numtags = len(self.tags)
            found =  0

            # Look for the next entry which matches all the tags passed in
            while (found != numtags) and (self.currentIdx != self.len):
                bug = self.bugtasks[self.currentIdx]
                bugtags = bug.bug.tags
                found = 0

                # Look through all the entries, looking for a match.
                # If a match is not found, go to next entry.
                for i in range(numtags):
                    for j in range(len(bugtags)):
                        if (self.tags[i] == bugtags[j]):
                            found += 1
                            break

                # point to next bug
                self.currentIdx += 1

            # return match or nothing
            if (found == numtags):
                ret = bug
                print("Found next entry: " + bug.title)
                      
        return ret

    # Method: getLastTaggedBug()
    # Description: Return the first bug in the list.
    def getLastTaggedBug(self):
        # get the next tag until there are no more tags
        print("empty")

if __name__ == "__main__":
    launchpad = Launchpad.login_with('getbugs.py', 'production')

    people = launchpad.people
    lmic = people['lmic']
    print(lmic.display_name)  
    bugObj = LaunchpadBugs("maas", "hp", None)
    bugObj.setTag("hp")

    # EXAMPLES for getting bug tags and duplicates - you can copy and paste and
    # replace by your own parameter
    bugObj.setBugNumber(1237215)
    bug = bugObj.getBugByBugNumber()
    tags = bugObj.getTagsByBugNumber()

    if (tags != None):
        print("List of tags:")
        print(tags)

    duplicates = bugObj.getCurrentBugDuplicates()
    if (duplicates != None):
        for i in range(len(duplicates)):
            print("Duplicate bug: " + duplicates[i])
                


