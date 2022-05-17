setup() {
    TEST_REPORT_DIR=$(mktemp -d)
}

test() {
    PIPELINEPLUGINS_ENABLE=test ./run_subset \
                          -o "library.defaultCaseConfigMergeMethod=extension" \
                          -o "library.directPath=tests/test_library" \
                          -o "testingPlugin.reportSenderDirectory=$TEST_REPORT_DIR" \
                          --testplan 'run_subset plan 2' \
                          --testcase 'testing plugin case 2' \
                          --testcase 'testing plugin case 3' \
                          --configuration 'some:foo' \
                          test \
                          --tp 'run_subset plan 1' \
                          --tp 'run_subset plan 2' \
                          --check-testruns

    #cp -r $TEST_REPORT_DIR $(dirname ${BASH_SOURCE[0]})/test_0_result   # update expected result
    #diff -Naur $(dirname ${BASH_SOURCE[0]})/test_0_result $TEST_REPORT_DIR
}

cleanup() {
    rm -rf $TEST_REPORT_DIR
}
