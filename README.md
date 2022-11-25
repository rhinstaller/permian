# Permian

A plugin based universal testing pipeline, that handles execution of various workflows based on events and reporting of interim and final results.

---
## How to

### Build container

```
./build_container
```

### Running tests in container

Execute all or just part of the tests
```
./in_container make test
./in_container make test.lint
./in_container make test.unit
./in_container make test.integration
```

### Build documentation in container

```
./in_container make doc
```

Documentation
-------------
The rendered documentation is located at http://permian.readthedocs.io.

