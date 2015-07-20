#! /usr/bin/env python2

import sys
import os
import yaml
import tempfile
from jenkinsapi.custom_exceptions import *
from doberman.analysis.analysis import CrudeAnalysis
from refinery_cli import CLI

# Matplotlib imports - The order is important to generate plots without X
if not os.access(os.environ['HOME'], os.W_OK):
    os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp()

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from pylab import xticks, gca, title


class Plotting(CrudeAnalysis):
    """
    """

    def __init__(self, cli=False):
        """  """
        self.cli = CLI().populate_cli() if not cli else cli

        if 'inputdir' not in self.cli.__dict__:
            self.cli.inputdir = self.cli.reportdir

        unified_bugs_dict_loc = os.path.join(self.cli.inputdir,
                                             'auto-triaged_unfiled_bugs.yml')
        with open(unified_bugs_dict_loc, "r") as f_ubd:
            self.unified_bugs_dict = yaml.load(f_ubd).get('pipelines')

        self.plot_all()
        self.message = 0

    def plot_all(self):
        """
        """
        plt.rcParams['font.size'] = 5.0
        reportdir = self.cli.reportdir
        plot_data = {}

        # Data to plot for job specific bugs:
        bug_rank_files = [bug_rank for bug_rank in
                          os.listdir(self.cli.inputdir) if 'bug_ranking_' in
                          bug_rank]

        for fn in bug_rank_files:
            file_location = os.path.join(self.cli.inputdir, fn)
            with open(file_location, "r") as f:
                jsbugs = yaml.load(f)
            job = ("".join(fn.split('.')[0:-1]).replace('bug_ranking', '')
                   .strip('_'))
            plot_data[job] = {'title': 'Bug_chart__{}.pdf'.format(job),
                              'bug_ids': [bug[0] for bug in jsbugs],
                              'totals': [int(bug[1]) for bug in jsbugs], }

        # Data to plot all unique unfiled bugs:
        # TODO
        # bug_ids = [bug[0] for bug in bugs]
        # totals = [int(bug[1]) for bug in bugs]
        # self.plot_all(bugs, reportdir, 'Unique_Unfiled_Bugs_Chart.pdf')

        # Data to plot each individual bug:
        # TODO - this will probably invole a for statement!
        # bug_ids = [bug[0] for bug in bugs]
        # totals = [int(bug[1]) for bug in bugs]
        # self.plot_all(bugs, reportdir, 'Individual_Bugs_Chart.pdf')

        # (Repeat the above for vendor specific?)

        for chart in plot_data:
            filename = plot_data[chart]['title']
            pdf_path = os.path.join(reportdir, filename)
            pdf = PdfPages(pdf_path)

            self.get_relevant_data(plot_data[chart]['bug_ids'])

            self.plot_bar(plot_data[chart], pdf)
            self.plot_pie(plot_data[chart], pdf)

            self.plot_openstack_version_vs_number_of_bugs(plot_data[chart],
                                                          pdf)

            self.plot_vendor_vs_number_of_bugs(plot_data[chart], pdf)
            self.plot_charm_vs_number_of_bugs(plot_data[chart], pdf)
            self.plot_openstack_version_vs_opsys_of_bugs(plot_data[chart], pdf)
            self.plot_machine_used_vs_number_of_bugs(plot_data[chart], pdf)
            self.plot_slave_used_vs_number_of_bugs(plot_data[chart], pdf)
            self.plot_new_unique_bugs_vs_datetime(plot_data[chart], pdf)
            self.plot_number_of_unfiled_bugs_found_vs_time_of_day(
                plot_data[chart], pdf)
            self.plot_number_of_bug_found_vs_datetime(plot_data[chart], pdf)

            pdf.close()

    def get_relevant_data(self, bug_ids):
        """
        """
        opst_releases = {}
        charm_used = {}
        timestamp = {}

        for pl in self.unified_bugs_dict:
            pipeline = self.unified_bugs_dict[pl]
            for bug in pipeline:
                if bug in bug_ids:
                    charm_used[bug] = pipeline[bug].get('charms')
                    timestamp[bug] = pipeline[bug].get('Jenkins timestamp')
                    info = pipeline[bug].get('additional info')
                    if info:
                        bs_node = info.get('bootstrap_node')
                        try:
                            opst_releases[bug] = \
                                bs_node.get('openstack release')
                        except:
                            opst_releases[bug] = "Unknown"

        # This isn't worth doing until we start filing the tags for what the
        # bug affects, otherwise it's just a collection of machines used
        # (only one of which being the guilty party, so this will discriminate
        # against commonly used vendors). Also, need percentage, not absolute.

        self.opst_releases = opst_releases
        self.charm_used = charm_used
        self.timestamp = timestamp

    def plot_pie(self, plot_data, pdf):
        bug_ids = plot_data['bug_ids']
        totals = plot_data['totals']

        fig = plt.figure()
        # The slices will be ordered and plotted counter-clockwise.
        # colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral']
        # explode = (0, 0.1, 0, 0) # only "explode" the 2nd slice (i.e. 'Hogs')
        # plt.pie(totals, explode=explode, labels=bug_ids, colors=colors,
        plt.pie(totals, autopct='%1.1f%%', shadow=False, startangle=90)
        splot = fig.add_subplot(111)
        bug_ids_with_nums = map(lambda x, y: "{} ({} duplicates)"
                                .format(x, y), bug_ids, totals)
        splot.legend(bug_ids_with_nums, loc=(-0.15, -0.05))
        # Set aspect ratio to be equal so that pie is drawn as a circle.
        plt.axis('equal')
        pdf.savefig(fig)

    def plot_bar(self, plot_data, pdf):
        bug_ids = plot_data['bug_ids']
        totals = plot_data['totals']

        fig = plt.figure()
        width = 0.5
        xloc = [x + width for x in range(0, len(bug_ids), 1)]
        plt.bar(xloc, totals, width=width)
        xticks(xloc, bug_ids)
        title("Bug Ranking")
        gca().get_xaxis().tick_bottom()
        gca().get_yaxis().tick_left()
        pdf.savefig(fig)

    def plot_number_of_unfiled_bugs_found_vs_time_of_day(self, plot_data, pdf):
        # unfiled_bugs = [id for id in plot_data['bug_ids'] if 'unfiled' in id]
        # timestamps = [self.timestamp[unf_bug] for unf_bug in unfiled_bugs]
        # plt.plot(timestamps, unfiled_bugs)
        # We really need a histogram here - bin into datetimes of 1 day and
        # have the number on the y axis
        # TODO

        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO

    def plot_new_unique_bugs_vs_datetime(self, plot_data, pdf):
        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO

    def plot_number_of_bug_found_vs_datetime(self, plot_data, pdf):
        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO

    def plot_openstack_version_vs_number_of_bugs(self, plot_data, pdf):
        bug_ids = plot_data['bug_ids']
        totals = plot_data['totals']

        release_nums = {}
        for idx, bug_id in enumerate(bug_ids):
            os_rel = self.opst_releases.get(bug_id)

            if os_rel:
                if os_rel not in release_nums:
                    release_nums[os_rel] = totals[idx]
                else:
                    release_nums[os_rel] += totals[idx]

        x_values = release_nums.keys()
        y_values = release_nums.values()

        fig = plt.figure()
        width = 0.5
        xloc = [x + width for x in range(0, len(x_values), 1)]
        if xloc:
            plt.bar(xloc, y_values, width=width)
            xticks(xloc, x_values)
            title("Openstack version vs number of bugs")
            gca().get_xaxis().tick_bottom()
            gca().get_yaxis().tick_left()
            pdf.savefig(fig)
        # TODO: Need percentage, not absolute.

    def plot_vendor_vs_number_of_bugs(self, plot_data, pdf):
        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO:

        # pipeline[bug]['vendors']
        # opst_releases = {}
        # for pl in self.unified_bugs_dict:
        #     pipeline = self.unified_bugs_dict[pl]
        #     for bug in pipeline:
        #         if bug in bug_ids:
        #             info = pipeline[bug].get('additional info')
        #             if info:
        #                 bs_node = info.get('bootstrap_node')
        #                 opst_releases[bug] = bs_node.get('openstack release')

        # TODO
        # This isn't worth doing until we start filing the tags for what the
        # bug affects, otherwise it's just a collection of maxchines used
        # (only one of which being the guilty party, so this will discriminate
        # against commonly used vendors). Also, need percentage, not absolute.

    def plot_charm_vs_number_of_bugs(self, plot_data, pdf):
        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO:
        # Also not worth doing until we start filing the tags for what the
        # bug affects. Also, also need percentage, not absolute.

    def plot_openstack_version_vs_opsys_of_bugs(self, plot_data, pdf):
        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO: Bubble chart!!!
        '''
        from pylab import *
        from scipy import *

        # reading the data from a csv file
        durl = 'http://datasets.flowingdata.com/crimeRatesByState2005.csv'
        rdata = genfromtxt(durl,dtype='S8,f,f,f,f,f,f,f,i',delimiter=',')

        rdata[0] = zeros(8) # cutting the label's titles
        rdata[1] = zeros(8) # cutting the global statistics

        x = []
        y = []
        color = []
        area = []

        for data in rdata:
         x.append(data[1]) # murder
         y.append(data[5]) # burglary
         color.append(data[6]) # larceny_theft
         area.append(sqrt(data[8])) # population
         # plotting the first eigth letters of the state's name
         text(data[1], data[5],
              data[0],size=11,horizontalalignment='center')

        # making the scatter plot
        sct = scatter(x, y, c=color, s=area, linewidths=2, edgecolor='w')
        sct.set_alpha(0.75)

        axis([0,11,200,1280])
        xlabel('Murders per 100,000 population')
        ylabel('Burglaries per 100,000 population')
        show()
        '''
        # TODO

    def plot_machine_used_vs_number_of_bugs(self, plot_data, pdf):
        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO

    def plot_slave_used_vs_number_of_bugs(self, plot_data, pdf):
        # bug_ids = plot_data['bug_ids']
        # totals = plot_data['totals']
        pass
        # TODO


def main():
    plotting = Plotting()
    return plotting.message


if __name__ == "__main__":
    sys.exit(main())
