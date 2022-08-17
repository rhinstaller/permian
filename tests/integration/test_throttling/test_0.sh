setup() {
    TEST_REPORT_DIR=$(mktemp -d)
}

test() {
    PIPELINEPLUGINS_ENABLE=test ./pipeline test -o "library.defaultCaseConfigMergeMethod=extension" \
                                                -o "library.directPath=tests/test_library" \
                                                -o "testingPlugin.reportSenderDirectory=$TEST_REPORT_DIR" \
                                                -o "reportSenders.throttleInterval=2" \
                                                --tp 'Throttling test 1'

    #cp -r $TEST_REPORT_DIR $(dirname ${BASH_SOURCE[0]})/test_0_result   # update expected result
    diff -Naur $(dirname ${BASH_SOURCE[0]})/test_0_result $TEST_REPORT_DIR
}

cleanup() {
    rm -rf $TEST_REPORT_DIR
}
