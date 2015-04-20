# These are examples on how to to use this class:
# 1) Pass the launchpad object and the distribution if not oil
# 2) Call the provided methods to retrieve bug information

from doberman.common import utils

LOG = utils.get_logger('doberman.getbugs')


class BugInfo():
    def __init__(self, launchpad, dist="oil"):
        self.launchpad = launchpad
        self.dist = dist
        self.bug = None
        self.bugno = None

    # Method: get_duplicates()
    # Description: Return duplicates for bug number passed in.
    def get_duplicates(self, bugno):
        retdup = []

        bug = self.get_bug(bugno)
        duplicates = bug.duplicates
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

        bug = self.get_bug(bugno)
        ret_tags = bug.tags

        return ret_tags

    # Method: get_description()
    # Description: Return description
    def get_description(self, bugno):
        description = None

        bug = self.get_bug(bugno)
        description = bug.description

        return description

    # Method: get_bugs()
    # Description: return list of bug number that matches tags. Pass list of
    #              tags or a string space separated tags. This can be later
    #              refined if we find a way to access the the oil bugs without
    #              going through searchTasks.
    def get_bugs(self, tags):
        retbugs = []

        # tags passed as a list.
        distobj = self.launchpad.distributions[self.dist]
        bugtasks = distobj.searchTasks()

        # Go through list of bug tasks, and find the bugs that has all
        # the tags passed in.
        for bugtask in bugtasks:

            bugtags = bugtask.bug.tags
            if set(tags) <= set(bugtags):
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
        bug = self.get_bug(bugno)
        tags = bug.tags
        rettags = [tag.replace("category-", "", 1)
                   for tag in tags if tag.startswith("category-")]

        return(rettags)

    # Method: get_affect()
    # Description: return tags affect_
    def get_affects(self, bugno):
        bug = self.get_bug(bugno)
        tags = bug.tags
        rettags = [tag.replace("affects-", "", 1)
                   for tag in tags if tag.startswith("affects-")]

        return(rettags)

    # Method: get_bug()
    # Description: return cached bug or fetches it from launchpad
    def get_bug(self, bugno):
        if (bugno is not self.bugno):
            # cache bug for future use
            try:
                self.bug = self.launchpad.bugs[bugno]
                self.bugno = bugno
            except KeyError:
                msg = "Invalid key"
                LOG.exception(msg)
                raise ValueError(msg)

        return self.bug

    # Method: file_bug()
    # Description: This method will file a bug in launchpad
    def file_bug(self, intitle, indesc, intags='doberman'):
        # pass in tags optionally, default to doberman
        bugtask = self.launchpad.bugs.createBug(
            description=indesc,
            title=intitle,
            target=self.launchpad.distributions[self.dist],
            tags=intags)
        bugno = bugtask.id

        return bugno
