.PHONY: rpms test doc

rpms:
test: test.lint test.unit test.integration
test.lint:
	./run_pylint.sh
test.unit:
	./run_unit_tests.py
test.integration:
	./run_integration_tests.sh
doc:
	make -C doc html
clean:
	rm -r *.log *.dump logs xunit-*.xml index.html pipeline_data static || :
