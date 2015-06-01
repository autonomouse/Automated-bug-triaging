import os
import yaml
import tempfile
import shutil
from doberman.tests.test_utils import DobermanTestBase
from doberman.common import utils
from doberman.__init__ import __version__
from collections import namedtuple
from lxml import etree


class CommonTestMethods(DobermanTestBase):

    mock_data_dir = "./doberman/tests/mock_data/"
    mock_output_data = os.path.abspath(os.path.join(mock_data_dir, "output"))
    DB_files = os.path.abspath(os.path.join(mock_data_dir, "database_files"))
    real_db_yaml = "../../../../samples/mock_database.yml"
    pipeline_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    paabn_info = {'pipeline_deploy': '00001',
                  'pipeline_prepare': '00002',
                  'pipeline_start': '00000',
                  'test_tempest_smoke': '00003'}

    def tidy_up(self):
        files_to_ditch = ["pipelines_processed.yaml",
                          "triage_pipeline_deploy.yml",
                          "triage_pipeline_prepare.yml",
                          "triage_test_tempest_smoke.yml"]
        for filename in files_to_ditch:
            path_to_file = os.path.join(self.reportdir, filename)
            if os.path.exists(path_to_file):
                os.remove(path_to_file)
        if hasattr(self, 'tmpdir'):
            shutil.rmtree(self.tmpdir)

    def get_output_data(self, fname="triage_pipeline_deploy.yml",
                        output_data_dir=mock_output_data):
        with open(os.path.join(output_data_dir, fname),'r') as f:
            output = yaml.load(f)
        try:
            return output['pipeline'][self.pipeline_id]
        except KeyError:
            return {'bugs': {}}

    def populate_cli_var(self, bugs_database, reportdir=mock_output_data):
        cli = namedtuple('CLI', '')
        cli.crude_job = 'pipeline_start'
        cli.database = os.path.join(self.DB_files, bugs_database)
        cli.dont_replace = True
        cli.external_jenkins_url = 'http://oil-jenkins.canonical.com'
        cli.ids = set(['doberman/tests/test_crude.py'])
        cli.jenkins_host = 'http://oil-jenkins.canonical.com'
        cli.job_names = ['pipeline_start', 'pipeline_deploy',
                              'pipeline_prepare', 'test_tempest_smoke']
        cli.keep_data = False
        cli.logpipelines = False
        cli.match_threshold = '0.965'
        cli.netloc = '91.189.92.95'
        cli.offline_mode = True
        cli.reduced_output_text = False
        cli.reportdir = reportdir
        cli.run_remote = True
        cli.tc_host = 'https://oil.canonical.com/api'
        cli.use_date_range = False
        cli.use_deploy = False
        cli.verify = True
        cli.xmls = ['tempest_xunit.xml']

        LOG = utils.get_logger('doberman.analysis')
        LOG.info("Doberman version {0}".format(__version__))
        cli.LOG = LOG
        return cli

    def create_paabn_in_tmp_dir(self):
        tmpdir = tempfile.mkdtemp()
        tmpfile = os.path.join(tmpdir,
                               "pipelines_and_associated_build_numbers.yml")
        paabn = {"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": self.paabn_info}
        with open(tmpfile, 'a+') as f:
            f.write(yaml.safe_dump(paabn, default_flow_style=False))
        return tmpdir

    def create_mock_xml_files(self, add_to_xml_dict):
        dashes = "--------------------"
        larrow = "<<" + dashes
        rarrow = dashes + ">>"
        msg = " begin captured logging " 
        for xml_file in add_to_xml_dict:
            root = etree.Element("root")
            testsuite = etree.SubElement(root, "testsuite")
            for (bug_number, line) in add_to_xml_dict[xml_file]:
                testcase = etree.SubElement(testsuite, "testcase")
                testcase.attrib['classname'] = "fake_class_{}".format(bug_number)
                testcase.attrib['name'] = "fake_testname_{}".format(bug_number)
                failure = etree.SubElement(testcase, "failure")
                failure.attrib['type'] = "fake_type_{}".format(bug_number)
                failure.attrib['message'] =\
                    "{}{}{}\n{}\n{}".format(rarrow, msg, larrow, line, dashes)
        etree.ElementTree(root).write(xml_file, pretty_print=True)

    def replace_or(self, text):
        if '|' not in text:
            return text
        split_up = text.split('|')
        add_to_next = ''
        initial_replace_with = None
        for num in range(0, len(split_up)-1):
            replace_with = split_up[num].split('(')[-1]
            if ')' in split_up[num+1]:
                other = split_up[num+1].split(')')[0]
                if add_to_next != '':
                    other = add_to_next + other
                    add_to_next = ''
            else:
                add_to_next = add_to_next + split_up[num+1] + '|'
            if add_to_next != '':
                if not initial_replace_with:
                    initial_replace_with = replace_with
            else:
                initial_replace_with = (replace_with if initial_replace_with
                                        is None else initial_replace_with)
                replace_this = "(" + initial_replace_with + "|" + other + ")"
                text = text.replace(replace_this, initial_replace_with)
                initial_replace_with = None
        return text

    def strip_caret(self, text):
        return text.replace('^', '')

    def replace_x_asterisk(self, text):
        if '*' not in text:
            return text
        last = text.rfind("*")

        while last != -1:

            if last == 0:
                raise Exception("Invalid regex '%s': nothing to repeat." % (text))

            if text[last - 1] != ')':
                lastchar = text[last - 1]
                repl_char = 'x' if lastchar is '.' else lastchar
                text = text.replace(lastchar + '*', repl_char)
            elif text[last - 1] == ')':
                closed_paren = last - 1
                # repeating a group! need to find the balanced open paren
                # this is a huge hack and won't work in a lot of regexes.
                # it has no idea about escaped parens.
                depth = 1
                open_paren = None
                for i in range(closed_paren - 1, -1, -1):
                    if text[i] == ')':
                        depth += 1
                        continue
                    if text[i] == '(':
                        depth -= 1
                        if depth == 0:
                            open_paren = i
                            break
                        if depth < 0:
                            raise Exception("We can't handle this regex! "
                                            "Check optional group parens balance.")

                if open_paren is not None:
                   text = "".join([
                       text[:open_paren],
                       text[open_paren+1:closed_paren],
                       text[closed_paren+2:]])
                else:
                   raise Exception("We can't handle this regex! "
                                   "Check optional group parens balance.")

            last = text.rfind("*")
        return text


    def replace_x_plus(self, text):
        if '+' not in text:
            return text
        split_up = text.split('+')
        for num in range(0, len(split_up)-1):
            lastchar = split_up[num][-1]
            repl_char = 'x' if lastchar is '.' else lastchar
            text = text.replace(lastchar + '+', repl_char)
        return text

    def replace_n_matching(self, text):
        opening = '.{'
        closing = '}'
        for num in range(0,text.count(opening)):
            try:
                dot_curly = text.split(opening)[1]
            except IndexError:
                dot_curly = 0
            if dot_curly != 0:
                inside = dot_curly.split(closing)[0]
                len_xs = inside if ',' not in inside else inside.split(',')[0]
                replace_this = opening + inside + closing
                text = text.replace(replace_this, 'x' * int(len_xs))
        return text

    def replace_space(self, text):
        if '\s' not in text:
            return text

        result = " ".join(text.split('\s'))
        return result

    def replace_digits(self, text):
        if '\d' not in text:
            return text

        result = "1".join(text.split('\d'))
        return result

    def generate_text_from_regexp(self, regexp):
        text_n = self.replace_n_matching(regexp)
        no_spaces = self.replace_space(text_n)
        no_digits = self.replace_digits(no_spaces)
        text_n_a = self.replace_x_asterisk(no_digits)
        text_n_a_p = self.replace_x_plus(text_n_a)
        text_n_a_p_o = self.replace_or(text_n_a_p)
        text = text_n_a_p_o
        return self.strip_caret(text)

