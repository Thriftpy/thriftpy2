clean:
	rm -vf thriftpy2/protocol/cybin/*.c thriftpy2/protocol/*.so
	rm -vf thriftpy2/transport/*.c thriftpy2/transport/*.so
	rm -vf thriftpy2/transport/*/*.c thriftpy2/transport/*/*.so
	rm -vf dist/*

build_ext: clean
	python setup.py build_ext

build: build_ext
	python setup.py sdist

pre_release: build
	twine upload --verbose --repository-url https://test.pypi.org/legacy/ dist/*

release: build
	twine upload dist/*

.PHONY: package upload
