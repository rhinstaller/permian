import yaml
from os import path
from tplib.structures.testplan import Reporting


class ReportSenderFactory():
    reportSender_classes = {}
    original_reportSender_classes = {}

    @classmethod
    def register(cls, name, reportSender_class=None):
        """
        Class decorator used for registering ReportSenders. Use this to assign
        name to the ReportSender. The ReportSender name is used in TestPlan and
        corresponding ReportSender instances are created for those Testplans for
        their reporting. See make method.

        Use this decorator following way::

            @ReportSenderFactory.register('my-super-reportSender')
            class SuperReportSender(libpermian.reportsenders.base.baseReportSender):
                ...

        Another possible use is::

            class SuperReportSender(libpermian.reportsenders.base.BaseReportSender):
                ...
            ReportSenderFactory.register('my-super-reportSender', SuperReportSender)

        :param name: Name under which the reportSender will be recorded
        :type name: str
        :param reportSender_class: When not used as decorator, provide the reportSender class in this argument.
        :type reportSender_class: BaseReportSender, optional
        """
        def decorator(reportSender_class):
            cls.reportSender_classes[name] = reportSender_class
            return reportSender_class
        if reportSender_class is not None:
            return decorator(reportSender_class)
        return decorator

    @classmethod
    def assign(cls, testRuns):
        """
        Create ReportSender instances based on testplans associated to
        caseRunConfigurations in testRuns and based on the reporting structures
        present in the testplans which cover the caseRunConfigurations.

        :param testRuns: TestRuns instance containing settings, event and caseRunConfigurations
        :typer testRuns: libpermian.testruns.TestRuns
        :return: Iterator of created ReportSender instances
        :rtype: Iterator[:class:`BaseReportSender`]
        """
        additional_reporting = cls._get_additional(testRuns.settings.get('reportSenders', 'additional_reporting'), testRuns.library)

        for testPlanId, crcList in testRuns.caseRunConfigurations.by_testplan().items():
            testPlan = testRuns.library.testplans[testPlanId]
            testPlan.reporting._data += additional_reporting
            for reporting in testPlan.reporting:
                reportSenderClass = cls._get_fallback(reporting.type, None, None)
                if reporting.group_by:
                    for values, groupCrcList in crcList.by_configuration(*reporting.group_by).items():
                        yield reportSenderClass(testPlan, reporting, groupCrcList.copy(), testRuns.event, testRuns.settings, testRuns.issueAnalyzerProxy, dict(zip(reporting.group_by, values)))
                else:
                    yield reportSenderClass(testPlan, reporting, crcList.copy(), testRuns.event, testRuns.settings, testRuns.issueAnalyzerProxy)

    @classmethod
    def _get_additional(cls, additional_file, library):
        """ Loads reporters that apply to all testplans

        :param additional_file: path to file with additional reporters
        :type additional_file: string
        :param library: test data library
        :type library: tplib.Library
        :return: list of tplib.testplan.Reporting objects
        :rtype: list
        """
        if additional_file == '':
            return []

        if additional_file.startswith('library://'):
            additional_file = path.join(library.directory, additional_file.replace('library://', '', 1))

        with open(additional_file) as fo:
            data = yaml.safe_load(fo)

        return [ Reporting(rs, library=library, document=None) for rs in data ]

    @classmethod
    def _get_fallback(cls, *args):
        """
        Return class registered under one of the names provided in args where
        the last value of args is default value if no class was registered
        under provided names.
        """
        args = list(args)
        default = args.pop()
        while args:
            try:
                return cls.reportSender_classes[args.pop(0)]
            except KeyError:
                continue
        return default

    @classmethod
    def clear_reportSender_classes(cls):
        """
        Saves currently registered reportSender_classes and replaces it with only builtin classes
        This method should be used only for testing
        """
        cls.original_reportSender_classes = cls.reportSender_classes
        cls.reportSender_classes = {None: cls.original_reportSender_classes[None]}

    @classmethod
    def restore_reportSender_classes(cls):
        """
        Restores reportSender_classes saved by clear_reportSender_classes, must be used after clear_reportSender_classes
        This method should be used only for testing
        """
        cls.reportSender_classes = cls.original_reportSender_classes
